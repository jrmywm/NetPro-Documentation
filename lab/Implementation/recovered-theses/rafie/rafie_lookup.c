/* Derived architecture/hashes from Rafie's code/new counting and tiered checkers.
 * Full-set rebuild, true LRU and durable-update integration are new adaptations.
 * Exact, case-sensitive matching preserves the current NetPro policy contract. */
#include "rafie_lookup.h"
#include <stdlib.h>
#include <string.h>

#define COUNTERS 65536u
#define HOT_SLOTS 256u
#define HOT_LIMIT 100u
#define NONE (-1)
typedef struct {
    char domain[RAFIE_DOMAIN_BYTES], id[RAFIE_ID_BYTES];
    int blocked, bucket_next, newer, older;
} entry;
struct rafie_lookup {
    sqlite3 *db;
    sqlite3_stmt *query, *version_query;
    entry *entries, hot[HOT_SLOTS];
    int *buckets, head, tail;
    unsigned capacity, used, bucket_count;
    unsigned char counters[COUNTERS / 2];
    int valid, total_changes;
    uint64_t version;
    rafie_stats stats;
};

/* Original three hash families, unsigned bytes and defined uint32 overflow. */
static void hashes(const char *s, uint32_t out[3]) {
    out[0] = out[2] = 0; out[1] = 5381;
    for (const unsigned char *p = (const unsigned char *)s; *p; ++p) {
        out[0] = out[0] * 31u + *p;
        out[1] = out[1] * 33u + *p;
        out[2] = out[2] * 101u + *p;
    }
}
static unsigned counter_get(rafie_lookup *c, uint32_t pos) {
    return (c->counters[pos / 2] >> ((pos & 1u) * 4)) & 15u;
}
static void bloom_add(rafie_lookup *c, const char *domain) {
    uint32_t h[3]; hashes(domain, h);
    for (unsigned k = 0; k < 3; ++k) {
        uint32_t p = h[k] % COUNTERS; unsigned n = counter_get(c, p);
        if (n == 15) { ++c->stats.counter_saturations; continue; }
        unsigned shift = (p & 1u) * 4;
        c->counters[p / 2] = (unsigned char)((c->counters[p / 2] & ~(15u << shift)) | ((n + 1) << shift));
    }
}
static int bloom_maybe(rafie_lookup *c, const char *domain) {
    uint32_t h[3]; hashes(domain, h);
    for (unsigned k = 0; k < 3; ++k) if (!counter_get(c, h[k] % COUNTERS)) return 0;
    return 1;
}
static int data_version(rafie_lookup *c, uint64_t *version) {
    sqlite3_reset(c->version_query);
    int rc = sqlite3_step(c->version_query);
    if (rc == SQLITE_ROW) *version = ((uint64_t)(uint32_t)sqlite3_column_int(c->version_query, 0) << 32)
        | (uint32_t)sqlite3_column_int(c->version_query, 1);
    sqlite3_reset(c->version_query);
    return rc == SQLITE_ROW;
}
static void clear_accelerators(rafie_lookup *c) {
    c->valid = 0; c->used = 0; c->head = c->tail = NONE;
    memset(c->hot, 0, sizeof(c->hot));
    for (unsigned i = 0; i < c->bucket_count; ++i) c->buckets[i] = NONE;
}
void rafie_lookup_changed(rafie_lookup *c) {
    if (c) { clear_accelerators(c); ++c->stats.invalidations; }
}
static int copy_column(sqlite3_stmt *s, int col, char *dest, size_t size) {
    const char *text = (const char *)sqlite3_column_text(s, col);
    int bytes = sqlite3_column_bytes(s, col);
    if (!text || bytes <= 0 || (size_t)bytes >= size || memchr(text, 0, (size_t)bytes)) return 0;
    memcpy(dest, text, (size_t)bytes); dest[bytes] = 0; return 1;
}
static int rebuild(rafie_lookup *c) {
    sqlite3_stmt *scan = NULL; uint64_t before, after; int rc, ok = 0; unsigned hot_count = 0;
    clear_accelerators(c); memset(c->counters, 0, sizeof(c->counters));
    c->stats.loaded_rows = 0;
    if (!data_version(c, &before)) goto done;
    /* One SQLite SELECT holds a coherent read snapshot until finalized. */
    if (sqlite3_prepare_v2(c->db, "SELECT domain,id FROM policies ORDER BY id", -1, &scan, NULL) != SQLITE_OK) goto done;
    while ((rc = sqlite3_step(scan)) == SQLITE_ROW) {
        char domain[RAFIE_DOMAIN_BYTES], id[RAFIE_ID_BYTES];
        /* Empty domains (IP-only policies) do not participate in domain lookup. */
        if (sqlite3_column_type(scan, 0) == SQLITE_NULL || sqlite3_column_bytes(scan, 0) == 0) continue;
        if (!copy_column(scan, 0, domain, sizeof(domain)) || !copy_column(scan, 1, id, sizeof(id))) goto done;
        bloom_add(c, domain); ++c->stats.loaded_rows;
        if (hot_count < HOT_LIMIT) {
            uint32_t h[3]; hashes(domain, h); unsigned pos = h[1] % HOT_SLOTS;
            while (c->hot[pos].domain[0] && strcmp(c->hot[pos].domain, domain)) pos = (pos + 1) % HOT_SLOTS;
            if (!c->hot[pos].domain[0]) {
                strcpy(c->hot[pos].domain, domain); strcpy(c->hot[pos].id, id); ++hot_count;
            }
        }
    }
    if (rc != SQLITE_DONE) goto done;
    sqlite3_finalize(scan); scan = NULL;
    if (!data_version(c, &after) || before != after) goto done;
    c->version = after; c->total_changes = sqlite3_total_changes(c->db);
    c->valid = 1; ++c->stats.rebuilds; ok = 1;
done:
    sqlite3_finalize(scan);
    if (!ok) { clear_accelerators(c); ++c->stats.errors; }
    return ok;
}
static void detach(rafie_lookup *c, int i) {
    entry *e = &c->entries[i];
    if (e->newer != NONE) c->entries[e->newer].older = e->older; else c->head = e->older;
    if (e->older != NONE) c->entries[e->older].newer = e->newer; else c->tail = e->newer;
}
static void front(rafie_lookup *c, int i) {
    entry *e = &c->entries[i]; e->newer = NONE; e->older = c->head;
    if (c->head != NONE) c->entries[c->head].newer = i; else c->tail = i;
    c->head = i;
}
static int cached(rafie_lookup *c, const char *domain, uint32_t hash, char *id) {
    for (int i = c->buckets[hash % c->bucket_count]; i != NONE; i = c->entries[i].bucket_next) {
        entry *e = &c->entries[i];
        if (!strcmp(e->domain, domain)) {
            detach(c, i); front(c, i); strcpy(id, e->id); ++c->stats.lru_hits; return e->blocked;
        }
    }
    return -2;
}
static void remember(rafie_lookup *c, const char *domain, uint32_t hash, const char *id, int blocked) {
    if (!c->capacity) return;
    int i;
    if (c->used < c->capacity) i = (int)c->used++;
    else {
        i = c->tail; entry *old = &c->entries[i]; uint32_t h[3]; hashes(old->domain, h);
        int *link = &c->buckets[h[1] % c->bucket_count];
        while (*link != i) link = &c->entries[*link].bucket_next;
        *link = old->bucket_next; detach(c, i); ++c->stats.evictions;
    }
    entry *e = &c->entries[i]; strcpy(e->domain, domain); strcpy(e->id, id); e->blocked = blocked;
    unsigned b = hash % c->bucket_count; e->bucket_next = c->buckets[b]; c->buckets[b] = i; front(c, i);
}
static int database_lookup(rafie_lookup *c, const char *domain, char *id) {
    ++c->stats.sqlite_queries; sqlite3_reset(c->query); sqlite3_clear_bindings(c->query);
    if (sqlite3_bind_text(c->query, 1, domain, -1, SQLITE_TRANSIENT) != SQLITE_OK) return -1;
    int rc = sqlite3_step(c->query), result = -1;
    if (rc == SQLITE_DONE) result = 0;
    else if (rc == SQLITE_ROW && copy_column(c->query, 0, id, RAFIE_ID_BYTES)) result = 1;
    sqlite3_reset(c->query);
    if (result < 0) ++c->stats.errors;
    return result;
}
int rafie_lookup_domain(rafie_lookup *c, const char *domain, char id[RAFIE_ID_BYTES]) {
    if (!c || !id) return -1;
    id[0] = 0;
    if (!domain || !domain[0] || strlen(domain) >= RAFIE_DOMAIN_BYTES) { ++c->stats.errors; return -1; }
    ++c->stats.queries;
    uint64_t version;
    if (!data_version(c, &version)) { clear_accelerators(c); return database_lookup(c, domain, id); }
    if (c->valid && (version != c->version || sqlite3_total_changes(c->db) != c->total_changes)) rafie_lookup_changed(c);
    if (!c->valid && !rebuild(c)) return database_lookup(c, domain, id);
    uint32_t h[3]; hashes(domain, h); unsigned hot = h[1] % HOT_SLOTS;
    while (c->hot[hot].domain[0]) {
        if (!strcmp(c->hot[hot].domain, domain)) { strcpy(id, c->hot[hot].id); ++c->stats.hot_hits; return 1; }
        hot = (hot + 1) % HOT_SLOTS;
    }
    int result = cached(c, domain, h[1], id);
    if (result != -2) return result;
    if (!bloom_maybe(c, domain)) { ++c->stats.bloom_negatives; remember(c, domain, h[1], "", 0); return 0; }
    result = database_lookup(c, domain, id);
    if (result == 0) ++c->stats.bloom_false_positives;
    if (result >= 0) remember(c, domain, h[1], id, result);
    return result;
}
rafie_lookup *rafie_lookup_create(sqlite3 *db, unsigned capacity) {
    if (!db || capacity > 200000) return NULL;
    rafie_lookup *c = calloc(1, sizeof(*c)); if (!c) return NULL;
    c->db = db; c->capacity = capacity; c->bucket_count = capacity ? capacity * 2 + 1 : 1;
    c->entries = capacity ? calloc(capacity, sizeof(entry)) : NULL;
    c->buckets = malloc(c->bucket_count * sizeof(int));
    if ((capacity && !c->entries) || !c->buckets ||
        sqlite3_prepare_v2(db, "SELECT id FROM policies WHERE domain=?1 ORDER BY id LIMIT 1", -1, &c->query, NULL) != SQLITE_OK ||
        sqlite3_prepare_v2(db, "SELECT (SELECT data_version FROM pragma_data_version), (SELECT schema_version FROM pragma_schema_version)", -1, &c->version_query, NULL) != SQLITE_OK) {
        rafie_lookup_destroy(c); return NULL;
    }
    clear_accelerators(c); return c;
}
void rafie_lookup_destroy(rafie_lookup *c) {
    if (!c) return;
    sqlite3_finalize(c->query); sqlite3_finalize(c->version_query); free(c->entries); free(c->buckets); free(c);
}
const rafie_stats *rafie_lookup_stats(const rafie_lookup *c) { return c ? &c->stats : NULL; }
void rafie_lookup_report(const rafie_lookup *c, FILE *out) {
    if (!c || !out) return;
    const rafie_stats *s = &c->stats;
    fprintf(out, "{\"enabled\":true,\"filterValid\":%s,\"capacity\":%u,\"queries\":%llu,\"hotHits\":%llu,\"lruHits\":%llu,\"bloomNegatives\":%llu,\"sqliteQueries\":%llu,\"falsePositives\":%llu,\"rebuilds\":%llu,\"invalidations\":%llu,\"errors\":%llu,\"evictions\":%llu,\"loadedRows\":%llu,\"counterSaturations\":%llu}\n",
        c->valid ? "true" : "false", c->capacity,
        (unsigned long long)s->queries, (unsigned long long)s->hot_hits, (unsigned long long)s->lru_hits,
        (unsigned long long)s->bloom_negatives, (unsigned long long)s->sqlite_queries,
        (unsigned long long)s->bloom_false_positives, (unsigned long long)s->rebuilds,
        (unsigned long long)s->invalidations, (unsigned long long)s->errors, (unsigned long long)s->evictions,
        (unsigned long long)s->loaded_rows, (unsigned long long)s->counter_saturations);
}
