"""Private NPB compile and routing-hint tests. No service restart/deployment."""
from pathlib import Path
import sys,json,datetime,shlex,hashlib
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
OUT=BASE/'evidence'/('npb-quic-candidate-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
c=None
try:
 c,_=connect_verified('192.168.31.33','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
 rc,root,err=run_remote_command(c,'mktemp -d /home/netpro/incoming/npb-quic-candidate.XXXXXX');root=root.strip()
 if rc:raise RuntimeError(err)
 fixture=sorted((BASE/'evidence').glob('quic-endpoint-*'))[-1]/'client-initial-1.bin'
 files=list((BASE/'candidate-npb').glob('*'))+[fixture]
 with c.open_sftp() as s:
  for p in files:s.put(str(p),root+'/'+p.name)
 (OUT/'sources.json').write_text(json.dumps({'remote':root,'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2),encoding='utf-8')
 cmd='cd '+shlex.quote(root)+r''' && set -eu
gcc -O1 -g -Wall -Wextra test_quic_classifier.c -o hint-normal >hint-build.log 2>&1
./hint-normal client-initial-1.bin >hint-normal.log 2>&1
gcc -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer test_quic_classifier.c -o hint-sanitized >>hint-build.log 2>&1
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 ./hint-sanitized client-initial-1.bin >hint-sanitized.log 2>&1
gcc -O2 -DALLOW_EXPERIMENTAL_API -pthread $(pkg-config --cflags libdpdk libcurl jansson) packetBroker.c -o packetBroker-quic-candidate $(pkg-config --libs libdpdk libcurl jansson) -lhs -lstdc++ -lm >candidate-build.log 2>&1
sha256sum packetBroker-quic-candidate
systemctl is-active netpro-npb
'''
 rc,out,err=run_remote_command(c,cmd,timeout=60)
 (OUT/'execution.json').write_text(json.dumps({'command':cmd,'exit':rc,'stdout':out,'stderr':err},indent=2),encoding='utf-8')
 print('Candidate build:',rc,out,err)
 with c.open_sftp() as s:
  for name in ('hint-build.log','hint-normal.log','hint-sanitized.log','candidate-build.log'):
   try:s.get(root+'/'+name,str(OUT/name))
   except OSError:pass
 for p in OUT.glob('hint-*.log'):
  if 'build' not in p.name:print(p.name,p.read_text())
 if rc:raise RuntimeError('candidate build/test failed; inspect retained logs')
finally:
 if c:c.close()
 print('EVIDENCE:',OUT)
