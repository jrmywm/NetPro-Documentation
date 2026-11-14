#define main policy_server_embedded_main
#include "policyServer.c"
#undef main

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int fail(const char *case_name)
{
	fprintf(stderr, "POLICY_LOOKUP_FAIL %s\n", case_name);
	return 1;
}

static void clear_domain_cache(void)
{
	memset(domain_cache, 0, sizeof(domain_cache));
	memset(hitCount, 0, sizeof(hitCount));
	domainCacheSize = 0;
	hitCounter = 0;
}

static int sql_exec(const char *sql)
{
	return sqlite3_exec(db, sql, NULL, NULL, NULL) == SQLITE_OK ? 0 : -1;
}

static int interrupt_progress(void *unused)
{
	(void)unused;
	return 1;
}

int main(void)
{
	clear_domain_cache();
	db = NULL;
	if (domain_checker("missing-db.example") || domain_lookup_valid ||
	    inline_verdict_policy_result(false, domain_lookup_valid) != INLINE_VERDICT_UNSUPPORTED)
		return fail("missing_database_not_unsupported");
	if (domain_checker("") || domain_lookup_valid)
		return fail("empty_domain_not_unsupported");

	if (sqlite3_open(":memory:", &db) != SQLITE_OK) return fail("open_db");
	if (sql_exec("CREATE TABLE policies(domain TEXT, id TEXT);"
		     "INSERT INTO policies VALUES('deny.fixture', 'rule-1');"
		     "INSERT INTO policies VALUES('null-id.fixture', NULL);") != 0)
		return fail("create_fixture");
	if (domain_checker("allow.fixture") || !domain_lookup_valid ||
	    inline_verdict_policy_result(false, domain_lookup_valid) != INLINE_VERDICT_ALLOW)
		return fail("confirmed_miss_not_allow");
	if (!domain_checker("deny.fixture") || !domain_lookup_valid ||
	    inline_verdict_policy_result(true, domain_lookup_valid) != INLINE_VERDICT_DENY)
		return fail("confirmed_hit_not_deny");
	if (domain_checker("null-id.fixture") || domain_lookup_valid ||
	    inline_verdict_policy_result(false, domain_lookup_valid) != INLINE_VERDICT_UNSUPPORTED)
		return fail("empty_policy_id_not_unsupported");
	sqlite3 *saved_db = db;
	db = NULL;
	if (!domain_checker("deny.fixture") || !domain_lookup_valid)
		return fail("cache_hit_not_valid");
	db = saved_db;

	if (sqlite3_close(db) != SQLITE_OK) return fail("close_db");
	db = NULL;
	clear_domain_cache();
	if (sqlite3_open(":memory:", &db) != SQLITE_OK) return fail("open_prepare_error_db");
	if (domain_checker("prepare.error") || domain_lookup_valid ||
	    inline_verdict_policy_result(false, domain_lookup_valid) != INLINE_VERDICT_UNSUPPORTED)
		return fail("prepare_error_not_unsupported");
	if (sqlite3_close(db) != SQLITE_OK) return fail("close_prepare_error_db");
	db = NULL;

	if (sqlite3_open(":memory:", &db) != SQLITE_OK) return fail("open_bind_error_db");
	if (sql_exec("CREATE TABLE policies(domain TEXT, id TEXT);") != 0)
		return fail("create_bind_error_table");
	(void)sqlite3_limit(db, SQLITE_LIMIT_LENGTH, 48);
	if (domain_checker("a-domain-long-enough-to-fail-the-bind-limit.example") ||
	    domain_lookup_valid ||
	    inline_verdict_policy_result(false, domain_lookup_valid) != INLINE_VERDICT_UNSUPPORTED)
		return fail("bind_error_not_unsupported");
	if (sqlite3_close(db) != SQLITE_OK) return fail("close_bind_error_db");
	db = NULL;

	if (sqlite3_open(":memory:", &db) != SQLITE_OK) return fail("open_step_error_db");
	if (sql_exec("CREATE TABLE policies(domain TEXT, id TEXT);") != 0)
		return fail("create_step_error_table");
	sqlite3_progress_handler(db, 1, interrupt_progress, NULL);
	if (domain_checker("step.error") || domain_lookup_valid ||
	    inline_verdict_policy_result(false, domain_lookup_valid) != INLINE_VERDICT_UNSUPPORTED)
		return fail("step_error_not_unsupported");
	sqlite3_progress_handler(db, 0, NULL, NULL);
	if (sqlite3_close(db) != SQLITE_OK) return fail("close_step_error_db");
	db = NULL;

	char lock_path[] = "/tmp/inline-policy-lock-XXXXXX";
	int lock_fd = mkstemp(lock_path);
	if (lock_fd < 0) return fail("create_lock_fixture");
	close(lock_fd);
	if (sqlite3_open(lock_path, &db) != SQLITE_OK) return fail("open_lock_db");
	if (sql_exec("CREATE TABLE policies(domain TEXT, id TEXT);") != 0)
		return fail("create_lock_table");
	sqlite3 *locker = NULL;
	if (sqlite3_open(lock_path, &locker) != SQLITE_OK) return fail("open_locker");
	if (sqlite3_exec(locker, "BEGIN EXCLUSIVE", NULL, NULL, NULL) != SQLITE_OK)
		return fail("acquire_exclusive_lock");
	if (domain_checker("locked.db") || domain_lookup_valid ||
	    inline_verdict_policy_result(false, domain_lookup_valid) != INLINE_VERDICT_UNSUPPORTED)
		return fail("locked_database_not_unsupported");
	(void)sqlite3_exec(locker, "ROLLBACK", NULL, NULL, NULL);
	if (sqlite3_close(locker) != SQLITE_OK) return fail("close_locker");
	if (sqlite3_close(db) != SQLITE_OK) return fail("close_lock_db");
	db = NULL;
	(void)unlink(lock_path);

	puts("POLICY_LOOKUP=PASS missing-db=UNSUPPORTED prepare-error=UNSUPPORTED bind-error=UNSUPPORTED step-error=UNSUPPORTED locked-db=UNSUPPORTED null-id=UNSUPPORTED confirmed-miss=ALLOW confirmed-hit=DENY cache-hit=DENY");
	return 0;
}
