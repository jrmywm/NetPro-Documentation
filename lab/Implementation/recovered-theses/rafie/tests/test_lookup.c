#define _POSIX_C_SOURCE 200809L
#include "../rafie_lookup.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static void sql(sqlite3 *db, const char *text) {
    char *error = NULL; int rc = sqlite3_exec(db, text, NULL, NULL, &error);
    if (rc != SQLITE_OK) { fprintf(stderr, "SQLite fixture: %s\n", error); sqlite3_free(error); abort(); }
}
static void expect(rafie_lookup *c, const char *domain, int decision, const char *id) {
    char actual[RAFIE_ID_BYTES]; int got = rafie_lookup_domain(c, domain, actual);
    if (got != decision || (id && strcmp(actual, id))) {
        fprintf(stderr, "Mismatch %s expected %d/%s got %d/%s\n", domain, decision, id ? id : "", got, actual); abort();
    }
}
static void seed(sqlite3 *db, unsigned count) {
    sql(db, "BEGIN"); sqlite3_stmt *s;
    assert(sqlite3_prepare_v2(db, "INSERT INTO policies VALUES(?1,?2,'')", -1, &s, NULL) == SQLITE_OK);
    for (unsigned i = 0; i < count; ++i) {
        char id[64], name[256]; snprintf(id, sizeof(id), "id-%06u", i); snprintf(name, sizeof(name), "domain-%06u.test", i);
        sqlite3_bind_text(s, 1, id, -1, SQLITE_TRANSIENT); sqlite3_bind_text(s, 2, name, -1, SQLITE_TRANSIENT);
        assert(sqlite3_step(s) == SQLITE_DONE); sqlite3_reset(s);
    }
    sqlite3_finalize(s); sql(db, "COMMIT");
}
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec / 1e9; }
int main(void) {
    sqlite3 *db; assert(sqlite3_open(":memory:", &db) == SQLITE_OK);
    sql(db, "CREATE TABLE policies(id TEXT PRIMARY KEY,domain TEXT,ip_address TEXT); CREATE INDEX domains ON policies(domain)");
    seed(db, 15001); rafie_lookup *c = rafie_lookup_create(db, 64); assert(c);
    for (unsigned i = 0; i < 15001; ++i) {
        char id[64], domain[256]; snprintf(id, sizeof(id), "id-%06u", i); snprintf(domain, sizeof(domain), "domain-%06u.test", i);
        expect(c, domain, 1, id);
    }
    assert(rafie_lookup_stats(c)->loaded_rows == 15001);
    puts("PASS all 15001 blocked rows match exact IDs, including beyond original 1000/10000 caps");
    for (unsigned i = 0; i < 2000; ++i) { char d[64]; snprintf(d, sizeof(d), "allowed-%u.test", i); expect(c, d, 0, ""); }
    puts("PASS 2000 nonmembers match SQLite ground truth, including Bloom false positives");
    expect(c, "Case.test", 0, ""); expect(c, "domain-010000.test", 1, "id-010000");
    expect(c, "domain-010000.test", 1, "id-010000");
    assert(rafie_lookup_stats(c)->lru_hits && rafie_lookup_stats(c)->hot_hits);
    puts("PASS preloaded tier and repeated positive LRU preserve policy IDs");
    expect(c, "new.test", 0, ""); expect(c, "new.test", 0, "");
    sql(db, "INSERT INTO policies VALUES('new-id','new.test','')"); rafie_lookup_changed(c); expect(c, "new.test", 1, "new-id");
    sql(db, "UPDATE policies SET domain='renamed.test' WHERE id='new-id'"); rafie_lookup_changed(c);
    expect(c, "new.test", 0, ""); expect(c, "renamed.test", 1, "new-id");
    sql(db, "DELETE FROM policies WHERE id='new-id'"); rafie_lookup_changed(c); expect(c, "renamed.test", 0, "");
    puts("PASS cached allow/block invalidated after create, rename and delete");
    sql(db, "INSERT INTO policies VALUES('implicit','implicit.test','')"); expect(c, "implicit.test", 1, "implicit");
    puts("PASS same-connection unannounced mutation detected by total_changes");
    sql(db, "INSERT INTO policies VALUES('null-domain',NULL,'192.0.2.1'); INSERT INTO policies VALUES('empty-domain','','192.0.2.2')");
    expect(c, "domain-015000.test", 1, "id-015000");
    puts("PASS IP-only policies do not invalidate complete domain-filter coverage");
    char id[64], long_domain[258]; memset(long_domain, 'a', sizeof(long_domain)); long_domain[257] = 0;
    assert(rafie_lookup_domain(c, long_domain, id) == -1 && rafie_lookup_domain(c, NULL, id) == -1);
    sql(db, "DROP TABLE policies"); assert(rafie_lookup_domain(c, "domain-015000.test", id) == -1);
    puts("PASS malformed input and database errors never become cached allow decisions");
    rafie_lookup_destroy(c); sqlite3_close(db);

    assert(sqlite3_open(":memory:", &db) == SQLITE_OK);
    sql(db, "CREATE TABLE policies(id TEXT PRIMARY KEY,domain TEXT,ip_address TEXT); CREATE INDEX domains ON policies(domain)");
    c = rafie_lookup_create(db, 2); assert(c);
    expect(c, "a.test", 0, ""); expect(c, "b.test", 0, ""); expect(c, "a.test", 0, ""); expect(c, "c.test", 0, "");
    uint64_t hits = rafie_lookup_stats(c)->lru_hits;
    expect(c, "a.test", 0, ""); assert(rafie_lookup_stats(c)->lru_hits == hits + 1);
    hits = rafie_lookup_stats(c)->lru_hits;
    expect(c, "b.test", 0, ""); assert(rafie_lookup_stats(c)->lru_hits == hits);
    assert(rafie_lookup_stats(c)->evictions == 2);
    puts("PASS true LRU evicts least recently used entry, not most recently touched");
    rafie_lookup_destroy(c); seed(db, 100000); c = rafie_lookup_create(db, 32); assert(c);
    expect(c, "domain-099999.test", 1, "id-099999"); assert(rafie_lookup_stats(c)->counter_saturations > 0);
    sql(db, "DELETE FROM policies WHERE id < 'id-090000'"); rafie_lookup_changed(c);
    for (unsigned i = 90000; i < 100000; ++i) {
        char name[64], key[64]; snprintf(name, sizeof(name), "domain-%06u.test", i); snprintf(key, sizeof(key), "id-%06u", i);
        expect(c, name, 1, key);
    }
    expect(c, "domain-000001.test", 0, "");
    puts("PASS saturated counters plus 90000 removals produce no false negatives in 10000 survivors");
    rafie_lookup_destroy(c); sqlite3_close(db);

    char filename[] = "/tmp/netpro-rafie-XXXXXX"; int fd = mkstemp(filename); assert(fd >= 0); close(fd);
    sqlite3 *writer; assert(sqlite3_open(filename, &db) == SQLITE_OK); assert(sqlite3_open(filename, &writer) == SQLITE_OK);
    sql(db, "CREATE TABLE policies(id TEXT PRIMARY KEY,domain TEXT,ip_address TEXT)");
    c = rafie_lookup_create(db, 0); assert(c); expect(c, "external.test", 0, "");
    sql(writer, "INSERT INTO policies VALUES('external','external.test','')"); expect(c, "external.test", 1, "external");
    sql(writer, "DELETE FROM policies"); expect(c, "external.test", 0, "");
    puts("PASS separate-connection commits invalidate filter/cache through SQLite data_version");
    rafie_lookup_destroy(c); c = rafie_lookup_create(db, 8); expect(c, "external.test", 0, "");
    puts("PASS fresh module restart reconstructs current policy state without stale cache");
    rafie_lookup_destroy(c); sqlite3_close(writer); sqlite3_close(db); unlink(filename);

    assert(sqlite3_open(":memory:", &db) == SQLITE_OK);
    sql(db, "CREATE TABLE policies(id TEXT PRIMARY KEY,domain TEXT,ip_address TEXT); CREATE INDEX domains ON policies(domain)"); seed(db, 15001);
    c = rafie_lookup_create(db, 64); assert(c); expect(c, "domain-010000.test", 1, "id-010000");
    const unsigned queries = 30000; sqlite3_stmt *s;
    assert(sqlite3_prepare_v2(db, "SELECT id FROM policies WHERE domain=?1 ORDER BY id LIMIT 1", -1, &s, NULL) == SQLITE_OK);
    double start = now();
    for (unsigned i = 0; i < queries; ++i) { sqlite3_bind_text(s, 1, "domain-010000.test", -1, SQLITE_STATIC); assert(sqlite3_step(s) == SQLITE_ROW); sqlite3_reset(s); }
    double baseline = now() - start; start = now();
    for (unsigned i = 0; i < queries; ++i) expect(c, "domain-010000.test", 1, "id-010000");
    double optimized = now() - start;
    printf("BENCH repeated-blocked in-memory queries=%u sqlite_s=%.6f cache_s=%.6f (microbenchmark only)\n", queries, baseline, optimized);
    rafie_lookup_report(c, stdout); sqlite3_finalize(s); rafie_lookup_destroy(c); sqlite3_close(db);
    puts("PASS benchmark processed every requested query with exact expected decision");
    return 0;
}
