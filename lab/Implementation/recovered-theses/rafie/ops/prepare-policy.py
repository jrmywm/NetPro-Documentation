"""Adapt a verified live-source snapshot; never writes the immutable originals."""
import hashlib
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE / 'policy-candidate/policyServer.c'
EXPECTED = 'bf51e1c98b1d2c3a323270fa87e0bebc1759f6d5b5032c316c6c2e302438d819'

def main():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise RuntimeError('Source snapshot changed; inspect before generating candidate')
    s = raw.decode()
    s = s.replace('#include <sqlite3.h>', '#include <sqlite3.h>\n#include <pthread.h>\n#include "rafie_lookup.h"', 1)
    s = s.replace('FILE *file = fopen(log_file_name, "a");', 'FILE *file = fopen(log_file_name, "a");\n\tif (!file) return;', 1)
    s = s.replace('static sqlite3 *db;', '''static sqlite3 *db;
/* Serialize cache decisions, policy commits and hit-counter collection. */
static pthread_mutex_t policy_lookup_lock = PTHREAD_MUTEX_INITIALIZER;
static rafie_lookup *domain_lookup;
static int lookup_mode; /* 0 legacy, 1 shadow, 2 rafie */
static uint64_t shadow_mismatches;
static int policy_sync_ready;
static int64_t policy_sync_highwater, policy_sync_offset = -1;
static void cache_status(void)
{
    FILE *f = fopen("/run/netpro-policy-cache.json.tmp", "w");
    if (!f) return;
    fprintf(f, "{\\"mode\\":\\"%s\\",\\"shadowMismatches\\":%llu,\\"policySyncReady\\":%s,\\"initialHighwater\\":%lld,\\"lastOffset\\":%lld,\\"lookup\\":", lookup_mode == 2 ? "rafie" : lookup_mode == 1 ? "shadow" : "legacy", (unsigned long long)shadow_mismatches, policy_sync_ready ? "true" : "false", (long long)policy_sync_highwater, (long long)policy_sync_offset);
    if (domain_lookup) rafie_lookup_report(domain_lookup, f); else fputs("null", f);
    fputs("}\\n", f); fclose(f);
    rename("/run/netpro-policy-cache.json.tmp", "/run/netpro-policy-cache.json");
}''', 1)
    start = s.index('\t// Update SQLite database', s.index('void msg_consume('))
    end = s.index('\ncleanup:', start)
    s = s[:start] + '''
    /* Prepared mutation and accelerator invalidation share the decision lock. */
    const char *query = strcmp(type_str, "create") == 0
        ? "INSERT INTO policies(id,domain,ip_address) VALUES(?1,?2,?3) ON CONFLICT(id) DO UPDATE SET domain=excluded.domain,ip_address=excluded.ip_address"
        : strcmp(type_str, "update") == 0
        ? "UPDATE policies SET domain=?2,ip_address=?3 WHERE id=?1"
        : "DELETE FROM policies WHERE id=?1";
    pthread_mutex_lock(&policy_lookup_lock);
    sqlite3_stmt *mutation = NULL;
    int rc = sqlite3_prepare_v2(db, query, -1, &mutation, NULL);
    if (rc == SQLITE_OK) rc = sqlite3_bind_text(mutation, 1, id_str, -1, SQLITE_TRANSIENT);
    if (rc == SQLITE_OK && strcmp(type_str, "delete")) rc = sqlite3_bind_text(mutation, 2, domain_str, -1, SQLITE_TRANSIENT);
    if (rc == SQLITE_OK && strcmp(type_str, "delete")) rc = sqlite3_bind_text(mutation, 3, ip_str, -1, SQLITE_TRANSIENT);
    if (rc == SQLITE_OK) {
        do {
            rc = sqlite3_step(mutation);
            if (rc == SQLITE_BUSY || rc == SQLITE_LOCKED) {
                sqlite3_reset(mutation);
                usleep(10000);
            }
        } while ((rc == SQLITE_BUSY || rc == SQLITE_LOCKED) && !force_quit);
    }
    sqlite3_finalize(mutation);
    if (rc == SQLITE_DONE) {
        rafie_lookup_changed(domain_lookup);
        memset(domain_cache, 0, sizeof(domain_cache)); domainCacheSize = 0;
        memset(ip_cache, 0, sizeof(ip_cache)); ipCacheSize = 0;
    } else {
        logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Policy mutation failed: %s\\n", sqlite3_errmsg(db));
    }
    pthread_mutex_unlock(&policy_lookup_lock);
''' + s[end:]
    # The synchronization worker must not replace or close the packet reader's handle.
    start = s.index('lcore_sync_database()')
    end = s.index('static uint16_t resolve_policy_port', start)
    segment = s[start:end]
    segment = segment.replace('rd_kafka_t *rk;', 'sqlite3 *sync_db = NULL;\n\trd_kafka_t *rk;', 1)
    segment = segment.replace('sqlite3_open(db_path, &db)', 'sqlite3_open(db_path, &sync_db)')
    segment = segment.replace('sqlite3_errmsg(db)', 'sqlite3_errmsg(sync_db)')
    segment = segment.replace('msg_consume(rkmessage, db)', 'msg_consume(rkmessage, sync_db)')
    segment = segment.replace('sqlite3_close(db)', 'sqlite3_close(sync_db)')
    segment = segment.replace('// Start consuming messages', 'sqlite3_busy_timeout(sync_db, 5000);\n\t// Start consuming messages', 1)
    segment = segment.replace('// Loop to consume messages', '''int64_t lowwater, highwater;
    if (rd_kafka_query_watermark_offsets(rk, KAFKA_TOPIC, 0, &lowwater, &highwater, 10000) != RD_KAFKA_RESP_ERR_NO_ERROR)
        highwater = INT64_MAX;
    pthread_mutex_lock(&policy_lookup_lock);
    policy_sync_highwater = highwater; policy_sync_ready = highwater == 0;
    pthread_mutex_unlock(&policy_lookup_lock);
    // Loop to consume messages''', 1)
    segment = segment.replace('msg_consume(rkmessage, sync_db);', '''msg_consume(rkmessage, sync_db);
            if (!rkmessage->err) {
                pthread_mutex_lock(&policy_lookup_lock);
                policy_sync_offset = rkmessage->offset;
                if (policy_sync_offset + 1 >= policy_sync_highwater) policy_sync_ready = 1;
                pthread_mutex_unlock(&policy_lookup_lock);
            }''', 1)
    s = s[:start] + segment + s[end:]
    # Close prepared lookup statements before closing the reader; never delete policies.
    start = s.index('void delete_database()')
    end = s.index('static inline bool ip_checker', start)
    s = s[:start] + '''void delete_database()
{
    rafie_lookup_destroy(domain_lookup); domain_lookup = NULL;
    if (db) { sqlite3_close(db); db = NULL; }
    logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Persistent policy database retained.\\n");
}

''' + s[end:]
    s = s.replace('static inline bool ip_checker(', 'static inline bool legacy_ip_checker(', 1)
    s = s.replace('static inline bool domain_checker(', 'static inline bool legacy_domain_checker(', 1)
    start = s.index('static inline bool legacy_domain_checker(')
    end = s.index('static inline void\nlcore_stats_process', start)
    # Insert wrappers after complete legacy domain function and before stats definition.
    s = s[:end] + '''static int plain_domain_lookup(const char *domain, char id[RAFIE_ID_BYTES])
{
    sqlite3_stmt *stmt = NULL; id[0] = 0;
    if (!domain || !*domain || !db) return -1;
    int result = -1;
    if (sqlite3_prepare_v2(db, "SELECT id FROM policies WHERE domain=?1 ORDER BY id LIMIT 1", -1, &stmt, NULL) == SQLITE_OK &&
        sqlite3_bind_text(stmt, 1, domain, -1, SQLITE_TRANSIENT) == SQLITE_OK) {
        int rc = sqlite3_step(stmt);
        if (rc == SQLITE_DONE) result = 0;
        else if (rc == SQLITE_ROW) {
            const char *value = (const char *)sqlite3_column_text(stmt, 0);
            if (value && strlen(value) < RAFIE_ID_BYTES) { strcpy(id, value); result = 1; }
        }
    }
    sqlite3_finalize(stmt); return result;
}
static inline bool ip_checker(struct rte_mbuf *packet)
{
    pthread_mutex_lock(&policy_lookup_lock);
    bool result = legacy_ip_checker(packet);
    pthread_mutex_unlock(&policy_lookup_lock); return result;
}
static inline bool domain_checker(char *domain)
{
    if (!domain || !*domain) return false;
    pthread_mutex_lock(&policy_lookup_lock);
    if (!lookup_mode) {
        bool result = legacy_domain_checker(domain);
        pthread_mutex_unlock(&policy_lookup_lock); return result;
    }
    char id[RAFIE_ID_BYTES], expected_id[RAFIE_ID_BYTES];
    int decision = rafie_lookup_domain(domain_lookup, domain, id);
    if (lookup_mode == 1) {
        int expected = plain_domain_lookup(domain, expected_id);
        if (decision != expected || (expected == 1 && strcmp(id, expected_id))) {
            ++shadow_mismatches;
            logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Rafie shadow decision mismatch\\n");
        }
        decision = expected; strcpy(id, expected_id);
    } else if (decision < 0) decision = plain_domain_lookup(domain, id);
    if (decision == 1) {
        if (hitCounter < CACHE_SIZE) {
            strncpy(hitCount[hitCounter], id, MAX_STRINGS - 1);
            hitCount[hitCounter++][MAX_STRINGS - 1] = 0;
        } else countFlag = 1;
    }
    pthread_mutex_unlock(&policy_lookup_lock); return decision == 1;
}

''' + s[end:]
    s = s.replace('\t\tcountStrings(hitCount, hitCounter);', '''        pthread_mutex_lock(&policy_lookup_lock);
        countStrings(hitCount, hitCounter);
        if (run_stats) cache_status();
        pthread_mutex_unlock(&policy_lookup_lock);''', 1)
    s = s.replace('\tinit_database();', '''    init_database();
    const char *cache_mode = getenv("NETPRO_LOOKUP_MODE");
    if (cache_mode && (!strcmp(cache_mode, "rafie") || !strcmp(cache_mode, "shadow"))) {
        domain_lookup = rafie_lookup_create(db, CACHE_SIZE);
        if (!domain_lookup) rte_exit(EXIT_FAILURE, "Rafie lookup initialization failed\\n");
        lookup_mode = !strcmp(cache_mode, "rafie") ? 2 : 1;
    }
    cache_status();''', 1)
    SOURCE.write_text(s, encoding='utf-8', newline='\n')
    print('Prepared labelled Policy Server candidate; default legacy mode')

if __name__ == '__main__': main()
