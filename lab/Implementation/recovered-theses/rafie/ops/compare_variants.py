"""Isolated, identical indexed workload for unchanged recovered lookup functions."""
import os,paramiko,pathlib,datetime,json,hashlib,shlex
root=pathlib.Path(__file__).resolve().parents[2]
src=pathlib.Path(r'C:\Users\jim\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an-2\work\thesis-review-2021\sources\recovered-code-20261029\skripsi-bloom-filter-main\skripsi-bloom-filter-main\code\new')
tag=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=root/'evidence'/('variant-comparison-'+tag);out.mkdir(parents=True)
code=r'''
#define _POSIX_C_SOURCE 200809L
#if defined(TIERED) || defined(COUNTING)
#define main recovered_main
#ifdef TIERED
#include "tiered-domain-checker.c"
#else
#include "counting-bloom-filter-domain-checker.c"
#endif
#undef main
#else
#include "rafie_lookup.h"
static sqlite3 *db;
#endif
#include <assert.h>
#include <time.h>
static double tick(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
int main(int argc,char **argv){int rows=atoi(argv[1]);sqlite3_stmt *s;assert(sqlite3_open(":memory:",&db)==0);
assert(sqlite3_exec(db,"CREATE TABLE policies(id TEXT PRIMARY KEY,domain TEXT,ip_address TEXT);CREATE INDEX idx_domain ON policies(domain);BEGIN",0,0,0)==0);
assert(sqlite3_prepare_v2(db,"INSERT INTO policies VALUES(?1,?2,'')",-1,&s,0)==0);
for(int i=0;i<rows;i++){char id[64],d[64];snprintf(id,64,"id-%06d",i);snprintf(d,64,"domain-%06d.test",i);sqlite3_bind_text(s,1,id,-1,SQLITE_TRANSIENT);sqlite3_bind_text(s,2,d,-1,SQLITE_TRANSIENT);assert(sqlite3_step(s)==SQLITE_DONE);sqlite3_reset(s);}sqlite3_finalize(s);assert(sqlite3_exec(db,"COMMIT",0,0,0)==0);
double start=tick();
#ifdef TIERED
init_bloom_filter();
#elif defined(COUNTING)
init_counting_bloom_filter();
#elif defined(ADAPTED)
rafie_lookup *cache=rafie_lookup_create(db,20000);assert(cache);char warm_id[64];assert(rafie_lookup_domain(cache,"domain-000000.test",warm_id)==1);
#else
assert(sqlite3_prepare_v2(db,"SELECT id FROM policies WHERE domain=?1 ORDER BY id LIMIT 1",-1,&s,0)==0);
#endif
double init=tick()-start;int wrong=0,denied=0;start=tick();
for(int i=0;i<3000;i++){char d[64];int member=i%5!=0;int idx=(i%2)?(rows-31+i%31):(i%31);if(member)snprintf(d,64,"domain-%06d.test",idx);else snprintf(d,64,"absent-%06d.test",i);int got;
#ifdef TIERED
int source;got=domain_checker(d,&source);
#elif defined(COUNTING)
got=domain_checker(d);
#elif defined(ADAPTED)
char id[64];got=rafie_lookup_domain(cache,d,id);
#else
sqlite3_bind_text(s,1,d,-1,SQLITE_TRANSIENT);int rc=sqlite3_step(s);assert(rc==SQLITE_ROW||rc==SQLITE_DONE);got=rc==SQLITE_ROW;sqlite3_reset(s);
#endif
wrong+=(got!=member);denied+=got==1;
}double seconds=tick()-start;printf("RESULT {\"rows\":%d,\"queries\":3000,\"mismatches\":%d,\"blocked\":%d,\"init_seconds\":%.9f,\"lookup_seconds\":%.9f,\"qps\":%.3f}\n",rows,wrong,denied,init,seconds,3000/seconds);return 0;}
'''
(out/'wrapper.c').write_text(code,encoding='utf-8')
c=paramiko.SSHClient();c.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'));c.connect('192.168.31.31',username='netpro',password=os.environ['NETPRO_LAB_PASSWORD'],timeout=10)
def run(cmd):
 _,a,b=c.exec_command(cmd,timeout=120);s=a.read().decode();e=b.read().decode();rc=a.channel.recv_exit_status()
 if rc:raise RuntimeError(s[-1000:]+e[-1500:])
 return s
remote='/home/netpro/incoming/variant-comparison-'+tag;run('mkdir -p '+remote)
files=[src/'tiered-domain-checker.c',src/'counting-bloom-filter-domain-checker.c',root/'rafie/rafie_lookup.c',root/'rafie/rafie_lookup.h',out/'wrapper.c']
with c.open_sftp() as s:
 for p in files:s.put(str(p),remote+'/'+p.name)
results=[]
try:
 for variant in ['sqlite','tiered','counting','adapted']:
  flags='' if variant=='sqlite' else '-D'+variant.upper()
  extra='rafie_lookup.c' if variant in ['sqlite','adapted'] else ''
  run(f'cd {remote} && cc -O3 {flags} wrapper.c {extra} -lsqlite3 -o {variant}')
  for rows in [1000,15001]:
   for repeat in range(3):
    raw=run(f'{remote}/{variant} {rows}');(out/f'{variant}-{rows}-{repeat}.log').write_text(raw)
    rec=json.loads(next(x[7:] for x in raw.splitlines() if x.startswith('RESULT ')));rec.update(variant=variant,repeat=repeat);results.append(rec)
   print(variant,rows,'mismatches',rec['mismatches'],flush=True)
 (out/'RESULTS.json').write_text(json.dumps({'scope':'isolated indexed in-memory SQLite; same 3000 queries; 80% listed, alternating low and high IDs; no live database writes','results':results,'sourceHashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2))
finally:c.close()
print('Evidence',out,flush=True)
