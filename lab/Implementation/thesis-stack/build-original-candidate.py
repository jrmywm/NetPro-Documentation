"""Build recovered QUIC pipeline with documented safety fixes; no rollout."""
from pathlib import Path
import sys,json,datetime,shlex,hashlib
BASE=Path(__file__).resolve().parent; TEST=BASE.parents[1]/'Testing'
sys.path.insert(0,str(TEST/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
OUT=BASE/'evidence'/('original-candidate-build-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
c=None
try:
 c,_=connect_verified('192.168.31.31','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
 rc,root,err=run_remote_command(c,'mktemp -d /home/netpro/incoming/original-thesis-candidate.XXXXXX');root=root.strip()
 if rc:raise RuntimeError(err)
 fixed=json.loads((sorted((TEST/'thesis-replication/evidence').glob('quic-fixed-gate-*'))[-1]/'sources.json').read_text())['directory']
 fixture=sorted((BASE/'evidence').glob('original-parser-*'))[-1]/'curl-initial.bin'
 files=list((BASE/'candidate-policy').glob('*'))+[BASE/'original-parser-gate.c',fixture]
 files=[p for p in files if p.is_file()]
 with c.open_sftp() as s:
  for p in files:s.put(str(p),root+'/'+p.name)
 (OUT/'sources.json').write_text(json.dumps({'remote':root,'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2),encoding='utf-8')
 flags=f'-O1 -g -pthread -I{fixed}/headers/usr/include -I{fixed}/headers/usr/include/x86_64-linux-gnu -L{fixed}/link'
 command=f'''set -eu
cd {shlex.quote(root)}
gcc {flags} -fsanitize=address,undefined -fno-omit-frame-pointer -Dmain=archived_main -c packet-processor.c -o processor-asan.o > build.log 2>&1
gcc {flags} -fsanitize=address,undefined -fno-omit-frame-pointer original-parser-gate.c quicFunctions.c processor-asan.o -lcrypto -o parser-gate >> build.log 2>&1
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 ./parser-gate curl-initial.bin mysite.local prefixes > gate.log 2>&1
gcc {flags} -Dmain=archived_main -c packet-processor.c -o processor.o >> build.log 2>&1
gcc {flags} -DALLOW_EXPERIMENTAL_API $(pkg-config --cflags libdpdk libcurl jansson sqlite3 rdkafka) policyServer.c snmp_reporter.c thesis_monitoring.c thesis_dataplane.c quicFunctions.c processor.o -o policyServer-original-thesis $(pkg-config --libs libdpdk libcurl jansson sqlite3 rdkafka) -lcrypto >> build.log 2>&1
grep -E 'ORIGINAL_|PREFIX_|MUTATION_' gate.log
sha256sum policyServer-original-thesis
'''
 rc,o,e=run_remote_command(c,command,timeout=180)
 (OUT/'build.json').write_text(json.dumps(dict(exit=rc,stdout=o,stderr=e),indent=2),encoding='utf-8')
 with c.open_sftp() as s:
  for name in ['build.log','gate.log','original-close.bin']:
   try:s.get(root+'/'+name,str(OUT/name))
   except OSError:pass
 print('BUILD_EXIT',rc,o,e,'EVIDENCE',OUT,flush=True)
 if rc:raise RuntimeError('Build/gate failed; inspect retained logs')
finally:
 if c:c.close()
