#define _POSIX_C_SOURCE 200809L
#include "../rafie_lookup.h"
#include <assert.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

#define QUERIES 3000
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec/1e9; }
static int order(const void *a,const void *b) { double x=*(const double *)a,y=*(const double *)b; return (x>y)-(x<y); }
static void workload(unsigned i,char *domain) {
    if (i % 5) snprintf(domain,256,"domain-%06u.test",10000+i%31);
    else snprintf(domain,256,"not-listed-%u.test",i);
}
static void metrics(const char *label,double seconds,double *samples) {
    qsort(samples,QUERIES,sizeof(double),order);
    printf("\"%s\":{\"processed\":%u,\"seconds\":%.9f,\"qps\":%.3f,\"p50_us\":%.3f,\"p95_us\":%.3f,\"p99_us\":%.3f}",label,QUERIES,seconds,QUERIES/seconds,samples[1499],samples[2849],samples[2969]);
}
int main(void) {
    sqlite3 *db; sqlite3_stmt *stmt; assert(sqlite3_open(":memory:",&db)==SQLITE_OK);
    assert(sqlite3_exec(db,"CREATE TABLE policies(id TEXT PRIMARY KEY,domain TEXT,ip_address TEXT); BEGIN",NULL,NULL,NULL)==SQLITE_OK);
    assert(sqlite3_prepare_v2(db,"INSERT INTO policies VALUES(?1,?2,'')",-1,&stmt,NULL)==SQLITE_OK);
    for(unsigned i=0;i<15001;++i) { char id[64],domain[256]; snprintf(id,64,"id-%06u",i);snprintf(domain,256,"domain-%06u.test",i);
        sqlite3_bind_text(stmt,1,id,-1,SQLITE_TRANSIENT);sqlite3_bind_text(stmt,2,domain,-1,SQLITE_TRANSIENT);
        assert(sqlite3_step(stmt)==SQLITE_DONE);sqlite3_reset(stmt); }
    sqlite3_finalize(stmt);assert(sqlite3_exec(db,"COMMIT",NULL,NULL,NULL)==SQLITE_OK);
    static double plain_us[QUERIES],cache_us[QUERIES];static int expected[QUERIES];static char expected_id[QUERIES][64];
    double start=now();
    for(unsigned i=0;i<QUERIES;++i) { char domain[256];workload(i,domain);double a=now();
        assert(sqlite3_prepare_v2(db,"SELECT id FROM policies WHERE domain=?1",-1,&stmt,NULL)==SQLITE_OK);
        sqlite3_bind_text(stmt,1,domain,-1,SQLITE_TRANSIENT);int rc=sqlite3_step(stmt);assert(rc==SQLITE_ROW||rc==SQLITE_DONE);
        expected[i]=rc==SQLITE_ROW;if(expected[i])snprintf(expected_id[i],64,"%s",sqlite3_column_text(stmt,0));sqlite3_finalize(stmt);
        plain_us[i]=(now()-a)*1e6;
    }
    double plain=now()-start;rafie_lookup *c=rafie_lookup_create(db,20000);assert(c);unsigned mismatches=0;start=now();
    for(unsigned i=0;i<QUERIES;++i) { char domain[256],id[64];workload(i,domain);double a=now();int got=rafie_lookup_domain(c,domain,id);
        cache_us[i]=(now()-a)*1e6;if(got!=expected[i]||(got==1&&strcmp(id,expected_id[i])))++mismatches; }
    double cached=now()-start;struct rusage usage;assert(getrusage(RUSAGE_SELF,&usage)==0);
    printf("{\"scope\":\"standalone exact SQLite versus adapted tiers; 15001 rows, no domain index, 80 percent repeated listed/20 percent unique absent\",\"mismatches\":%u,\"processMaxRssKiB\":%ld,",mismatches,usage.ru_maxrss);
    metrics("sqlite",plain,plain_us);putchar(',');metrics("tiers",cached,cache_us);puts("}");
    rafie_lookup_report(c,stdout);assert(!mismatches);rafie_lookup_destroy(c);sqlite3_close(db);return 0;
}
