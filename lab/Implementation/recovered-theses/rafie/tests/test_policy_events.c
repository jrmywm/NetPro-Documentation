/* Compile the actual DPDK candidate; exercise its real Kafka-event handler in memory. */
#define main archived_policy_main
#include "../policy-candidate/policyServer.c"
#undef main
#include <assert.h>
#include <sys/stat.h>
#include <unistd.h>

static void event(const char *type, const char *id, const char *domain) {
    const char *key = !strcmp(type, "create") ? "createdBlockedList" : !strcmp(type, "update") ? "updatedBlockedList" : "deletedBlockedList";
    json_t *root = json_pack("{s:s,s:{s:s,s:s,s:s}}", "type", type, key, "id", id, "domain", domain, "ip_add", "");
    char *payload = json_dumps(root, 0); rd_kafka_message_t message = {0};
    message.payload = payload; message.len = strlen(payload); msg_consume(&message, db);
    free(payload); json_decref(root);
}
typedef struct { int count; } work;
static void *lookups(void *argument) {
    work *w = argument;
    for (int i = 0; i < w->count; ++i) { domain_checker("concurrent.test"); domain_checker("absent.test"); }
    return NULL;
}
static void *release_reader(void *argument) {
    usleep(200000);
    assert(sqlite3_exec(argument, "COMMIT", NULL, NULL, NULL) == SQLITE_OK);
    return NULL;
}
int main(void) {
    mkdir("logs", 0700);
    strcpy(log_file_name, "/tmp/netpro-rafie-event-test.log");
    assert(sqlite3_open(":memory:", &db) == SQLITE_OK);
    assert(sqlite3_exec(db, "CREATE TABLE policies(id TEXT PRIMARY KEY, domain TEXT, ip_address TEXT)", NULL, NULL, NULL) == SQLITE_OK);
    domain_lookup = rafie_lookup_create(db, 2); assert(domain_lookup); lookup_mode = 1;
    assert(!domain_checker("first.test")); event("create", "one", "first.test"); assert(domain_checker("first.test"));
    event("create", "one", "first.test"); assert(domain_checker("first.test"));
    event("update", "one", "renamed.test"); assert(!domain_checker("first.test")); assert(domain_checker("renamed.test"));
    event("delete", "one", "renamed.test"); assert(!domain_checker("renamed.test"));
    event("create", "quoted", "quote's.test"); assert(domain_checker("quote's.test"));
    event("delete", "quoted", "quote's.test"); assert(!domain_checker("quote's.test"));
    assert(shadow_mismatches == 0);
    puts("PASS actual Kafka handler create/replay/rename/delete, prepared quoting, shadow oracle and hit-ID path");
    lookup_mode = 2;
    for (int i = 0; i < 40; ++i) {
        event("create", "one", "first.test"); assert(domain_checker("first.test"));
        event("delete", "one", "first.test"); assert(!domain_checker("first.test"));
    }
    puts("PASS enabled actual Policy Server wrappers across 40 alternating create/delete cycles");
    lookup_mode = 1; pthread_t readers[3]; work w = {1500};
    for (int i = 0; i < 3; ++i) assert(!pthread_create(&readers[i], NULL, lookups, &w));
    for (int i = 0; i < 300; ++i) { event("create", "concurrent", "concurrent.test"); event("delete", "concurrent", "concurrent.test"); }
    for (int i = 0; i < 3; ++i) pthread_join(readers[i], NULL);
    assert(!domain_checker("concurrent.test")); assert(shadow_mismatches == 0);
    puts("PASS actual serialized policy updates with 3 concurrent reader threads: zero shadow divergences");
    rafie_lookup_report(domain_lookup, stdout);
    rafie_lookup_destroy(domain_lookup); domain_lookup = NULL; sqlite3_close(db); db = NULL;
    char path[] = "/tmp/netpro-rafie-lock-XXXXXX"; int fd = mkstemp(path); assert(fd >= 0); close(fd);
    assert(sqlite3_open(path, &db) == SQLITE_OK);
    assert(sqlite3_exec(db, "CREATE TABLE policies(id TEXT PRIMARY KEY,domain TEXT,ip_address TEXT)", NULL, NULL, NULL) == SQLITE_OK);
    sqlite3 *reader; sqlite3_stmt *scan; assert(sqlite3_open(path, &reader) == SQLITE_OK);
    assert(sqlite3_exec(reader, "BEGIN", NULL, NULL, NULL) == SQLITE_OK);
    assert(sqlite3_prepare_v2(reader, "SELECT count(*) FROM policies", -1, &scan, NULL) == SQLITE_OK);
    assert(sqlite3_step(scan) == SQLITE_ROW); sqlite3_finalize(scan);
    pthread_t release; assert(!pthread_create(&release, NULL, release_reader, reader));
    event("create", "locked", "locked.test"); pthread_join(release, NULL);
    domain_lookup = rafie_lookup_create(db, 2); lookup_mode = 2; assert(domain_checker("locked.test"));
    puts("PASS actual Kafka mutation retries temporary SQLite reader lock instead of dropping policy event");
    rafie_lookup_destroy(domain_lookup); domain_lookup = NULL; sqlite3_close(reader); sqlite3_close(db); db = NULL; unlink(path);
    return 0;
}
