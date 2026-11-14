"""Stage recovered QUIC on top of current monitoring/cache/retry build; no rollout."""
from pathlib import Path
import os,sys,json,datetime,hashlib,shlex
BASE=Path(__file__).resolve().parent;TEST=BASE.parents[1]/'Testing'
sys.path.insert(0,str(TEST/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
out=BASE/'evidence'/('original-candidate-build-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
c,_=connect_verified('192.168.31.31','netpro',os.environ['NETPRO_LAB_PASSWORD'],Path.home()/'.ssh/known_hosts')
try:
 rc,work,e=run_remote_command(c,'mktemp -d /home/netpro/incoming/combined-thesis-candidate.XXXXXX');work=work.strip();assert rc==0
 with c.open_sftp() as s:
  live=s.open('/home/netpro/NetPro-Policy-Server/policyServer.c').read().decode()
  old=(BASE/'candidate-policy/policyServer.c').read_text()
  block=old[old.index('\t\t\t\tif(input_port == tls_port && thesis_quic_is_udp'):old.index('\n\t\t\t\tpacket_type =',old.index('if(input_port == tls_port && thesis_quic_is_udp'))]
  live=live.replace('#include "thesis_monitoring.h"','#include "thesis_monitoring.h"\n#include "thesis_dataplane.h"')
  live=live.replace('\t\t\t\tpacket_type = input_port',block+'\n\t\t\t\tpacket_type = input_port',1)
  live=live.replace('collect_stats();','collect_stats();\n            thesis_metrics_report();',1)
  (out/'policyServer.c').write_text(live)
  for n in ['rafie_lookup.c','rafie_lookup.h','thesis_monitoring.c','thesis_monitoring.h']:
   s.get('/home/netpro/NetPro-Policy-Server/'+n,str(out/n))
  for p in [*out.glob('*.c'),*out.glob('*.h'),BASE/'original-parser-gate.c',*[BASE/'candidate-policy'/n for n in ['thesis_dataplane.c','thesis_dataplane.h','quicFunctions.c','quicFunctions.h','packet-processor.c','snmp_reporter.c','snmp_reporter.h']]]:s.put(str(p),work+'/'+p.name)
  fixture=sorted((BASE/'evidence').glob('original-parser-*'))[-1]/'curl-initial.bin';s.put(str(fixture),work+'/curl-initial.bin')
 fixed=json.loads((sorted((TEST/'thesis-replication/evidence').glob('quic-fixed-gate-*'))[-1]/'sources.json').read_text())['directory']
 flags=f'-O1 -g -pthread -I{fixed}/headers/usr/include -I{fixed}/headers/usr/include/x86_64-linux-gnu -L{fixed}/link'
 cmd=f'''set -eu
cd {shlex.quote(work)}
gcc {flags} -fsanitize=address,undefined -fno-omit-frame-pointer -Dmain=archived_main -c packet-processor.c -o processor-asan.o >build.log 2>&1
gcc {flags} -fsanitize=address,undefined -fno-omit-frame-pointer original-parser-gate.c quicFunctions.c processor-asan.o -lcrypto -o parser-gate >>build.log 2>&1
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 ./parser-gate curl-initial.bin mysite.local prefixes >gate.log 2>&1
gcc {flags} -Dmain=archived_main -c packet-processor.c -o processor.o >>build.log 2>&1
gcc {flags} -DALLOW_EXPERIMENTAL_API $(pkg-config --cflags libdpdk libcurl jansson sqlite3 rdkafka) policyServer.c rafie_lookup.c snmp_reporter.c thesis_monitoring.c thesis_dataplane.c quicFunctions.c processor.o -o policyServer-original-thesis $(pkg-config --libs libdpdk libcurl jansson sqlite3 rdkafka) -lcrypto >>build.log 2>&1
grep -E 'ORIGINAL_|PREFIX_|MUTATION_' gate.log
sha256sum policyServer-original-thesis
'''
 rc,a,e=run_remote_command(c,cmd,timeout=180)
 (out/'sources.json').write_text(json.dumps({'remote':work,'scope':'current Rafie/monitoring/retry source plus recovered QUIC candidate'},indent=2))
 (out/'build.json').write_text(json.dumps({'exit':rc,'stdout':a,'stderr':e},indent=2))
 with c.open_sftp() as s:
  for n in ['build.log','gate.log']:s.get(work+'/'+n,str(out/n))
 print('Combined candidate build',rc,a,'Evidence',out,flush=True)
 if rc:raise RuntimeError('Combined QUIC candidate build failed')
finally:c.close()
