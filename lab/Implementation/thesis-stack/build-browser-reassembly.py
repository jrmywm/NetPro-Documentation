"""Build a staged reassembly candidate and verify real Chromium datagrams."""
import datetime,json,os,runpy,shlex,sys
from pathlib import Path
B=Path(__file__).resolve().parent
T=B.parents[1]/'Testing'
sys.path.insert(0,str(T/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
O=B/'evidence'/('chromium-reassembly-build-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
O.mkdir()
source=B/'evidence/original-candidate-build-20261106T231128Z'
remote=json.loads((source/'sources.json').read_text())['remote']
parser=runpy.run_path(str(B/'analyze-close-capture.py'))
fixture=B/'evidence/browser-persistent-20261107T094307Z/chromium-initial.pcap'
initials=[p for _,_,_,p in parser['packets'](fixture) if len(p)>7 and p[0]&0xf0==0xc0]
assert len(initials)==2
gate=r"""
#include "quic_initial_reassembly.h"
#include <assert.h>
#include <stdio.h>
static size_t read_fixture(const char *path,uint8_t *data) {
    FILE *f=fopen(path,"rb");
    assert(f);
    size_t n=fread(data,1,4096,f);
    fclose(f);
    return n;
}
int main(void) {
    uint8_t a[4096],b[4096],tuple[12]={0};
    QuicCryptoKeys keys;
    size_t an=read_fixture("initial-0.bin",a),bn=read_fixture("initial-1.bin",b);
    for (int reverse=0;reverse<2;reverse++) {
        ++tuple[0];
        uint8_t *first=reverse?b:a,*last=reverse?a:b;
        size_t firstn=reverse?bn:an,lastn=reverse?an:bn;
        assert(!quic_initial_sni(first,firstn,tuple,1,&keys));
        assert(!quic_initial_sni(first,firstn,tuple,2,&keys));
        char *sni=quic_initial_sni(last,lastn,tuple,3,&keys);
        assert(sni && !strcmp(sni,"mysite.local"));
        free(sni);
    }
    ++tuple[0];
    assert(!quic_initial_sni(a,an,tuple,1,&keys));
    b[100]^=1;
    assert(!quic_initial_sni(b,bn,tuple,2,&keys));
    puts("PASS captured Chromium Initials in order, reordered, duplicated, and tampered");
    return 0;
}
"""
c,_=connect_verified('192.168.31.31','netpro',os.environ['NETPRO_LAB_PASSWORD'],Path.home()/'.ssh/known_hosts')
try:
 rc,work,err=run_remote_command(c,'mktemp -d /home/netpro/incoming/chromium-reassembly.XXXXXX')
 assert rc==0,err
 work=work.strip()
 files=['policyServer.c','rafie_lookup.c','rafie_lookup.h','thesis_monitoring.c','thesis_monitoring.h','thesis_dataplane.c','thesis_dataplane.h','quicFunctions.c','quicFunctions.h','packet-processor.c','snmp_reporter.c','snmp_reporter.h']
 with c.open_sftp() as s:
  for name in files:s.get(remote+'/'+name,str(O/name))
  p=O/'policyServer.c'
  code=p.read_text()
  assert code.count('static char *tls_clienthello_sni(')==1
  p.write_text(code.replace('static char *tls_clienthello_sni(','char *tls_clienthello_sni('),encoding='utf-8')
  p=O/'thesis_dataplane.c'
  code=p.read_text().replace('/* Narrow IPv4/v1 Initial integration. No CRYPTO fragmentation/reassembly. */','/* IPv4 QUIC v1 Initial integration with bounded ClientHello reassembly. */')
  code=code.replace('#include "quicFunctions.h"','#include "quicFunctions.h"\n#include "quic_initial_reassembly.h"\n#include <time.h>')
  old='memset(&packet_keys,0,sizeof(packet_keys));char *name=getDomain(p+u+8,(int)ulen-8,true,&packet_keys);'
  code=code.replace('if(!sl||sl>20||o+sl>n)','if(sl>20||o+sl>n)')
  assert code.count(old)==1
  code=code.replace(old,'''struct timespec now;
 if(clock_gettime(CLOCK_MONOTONIC,&now)!=0)return 0;
 uint8_t tuple[12];
 memcpy(tuple,p+26,8);
 memcpy(tuple+8,p+u,4);
 memset(&packet_keys,0,sizeof(packet_keys));
 char *name=quic_initial_sni(p+u+8,ulen-8,tuple,(uint64_t)now.tv_sec*1000+now.tv_nsec/1000000,&packet_keys);''')
  p.write_text(code,encoding='utf-8')
  (O/'gate.c').write_text(gate,encoding='utf-8')
  for i,p in enumerate(initials):(O/f'initial-{i}.bin').write_bytes(p)
  for p in list(O.iterdir())+[B/'candidate-policy/quic_initial_reassembly.h']:s.put(str(p),work+'/'+p.name)
 fixed=json.loads((sorted((T/'thesis-replication/evidence').glob('quic-fixed-gate-*'))[-1]/'sources.json').read_text())['directory']
 flags=f'-O1 -g -pthread -I{fixed}/headers/usr/include -I{fixed}/headers/usr/include/x86_64-linux-gnu -L{fixed}/link'
 cmd=f"""set -eu
cd {shlex.quote(work)}
gcc {flags} -ffunction-sections -fdata-sections -Dmain=policy_main -DALLOW_EXPERIMENTAL_API $(pkg-config --cflags libdpdk libcurl jansson sqlite3 rdkafka) -c policyServer.c -o gate-policy.o >build.log 2>&1
gcc {flags} -fsanitize=address,undefined -ffunction-sections -Wl,--gc-sections gate.c quicFunctions.c gate-policy.o -lcrypto -o gate >>build.log 2>&1
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 ./gate
gcc {flags} -Dmain=archived_main -c packet-processor.c -o processor.o >>build.log 2>&1
gcc {flags} -DALLOW_EXPERIMENTAL_API $(pkg-config --cflags libdpdk libcurl jansson sqlite3 rdkafka) policyServer.c rafie_lookup.c snmp_reporter.c thesis_monitoring.c thesis_dataplane.c quicFunctions.c processor.o -o policyServer-browser $(pkg-config --libs libdpdk libcurl jansson sqlite3 rdkafka) -lcrypto >>build.log 2>&1
sha256sum policyServer-browser
"""
 rc,out,err=run_remote_command(c,cmd,timeout=180)
 with c.open_sftp() as s:s.get(work+'/build.log',str(O/'build.log'))
 (O/'build-result.json').write_text(json.dumps(dict(remote=work,stdout=out,stderr=err,rc=rc),indent=2),encoding='utf-8')
 print(out,err,O)
 if rc:raise SystemExit(rc)
finally:c.close()
