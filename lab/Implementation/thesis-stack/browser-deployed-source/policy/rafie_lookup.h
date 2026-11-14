/* Labelled NetPro adaptation of Rafie's recovered counting/tiered checkers.
 * See PROVENANCE.md. Caller must serialize lookup, changes and destruction. */
#ifndef NETPRO_RAFIE_LOOKUP_H
#define NETPRO_RAFIE_LOOKUP_H
#include <stdint.h>
#include <stdio.h>
#include <sqlite3.h>

#define RAFIE_DOMAIN_BYTES 256
#define RAFIE_ID_BYTES 64
typedef struct rafie_lookup rafie_lookup;
typedef struct {
    uint64_t queries, hot_hits, lru_hits, bloom_negatives, sqlite_queries;
    uint64_t bloom_false_positives, rebuilds, invalidations, errors, evictions;
    uint64_t loaded_rows, counter_saturations;
} rafie_stats;
/* Capacity bounds memory; zero disables LRU, not database lookup. */
rafie_lookup *rafie_lookup_create(sqlite3 *db, unsigned capacity);
void rafie_lookup_destroy(rafie_lookup *lookup);
/* 1 block, 0 allow, -1 SQLite/input error. IDs are returned on every block. */
int rafie_lookup_domain(rafie_lookup *lookup, const char *domain, char id[RAFIE_ID_BYTES]);
/* Call after each committed policy event; never decrement saturated counters. */
void rafie_lookup_changed(rafie_lookup *lookup);
const rafie_stats *rafie_lookup_stats(const rafie_lookup *lookup);
void rafie_lookup_report(const rafie_lookup *lookup, FILE *output);
#endif
