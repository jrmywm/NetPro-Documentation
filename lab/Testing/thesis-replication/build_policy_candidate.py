"""Compile/test private thesis integration; do not deploy or restart services."""
from pathlib import Path
import sys,json,datetime,hashlib,shlex
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
WORK=Path('C:/Users/jim/Documents/Codex/2026-09-11/referenced-chatgpt-conversation-this-is-an-2/work')
OUT=BASE/'evidence'/('policy-thesis-build-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
c=None
try:
 c,_=connect_verified('192.168.31.31','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
 rc,root,err=run_remote_command(c,'mktemp -d /home/netpro/incoming/policy-thesis-candidate.XXXXXX');root=root.strip()
 if rc:raise RuntimeError(err)
 fixed=json.loads((sorted((BASE/'evidence').glob('quic-fixed-gate-*'))[-1]/'sources.json').read_text())['directory']
 original=WORK/'thesis-review-2021/repository-audit/sources/NetPro-Policy-Server/quic-dev/quic-processor'
 parser=WORK/'snmp-quic-integration/quic-offline/linux-bundle-v5'
 fixture=sorted((BASE/'evidence').glob('quic-endpoint-*'))[-1]/'client-initial-1.bin'
 files=list((BASE/'candidate-policy').glob('*'))+[original/'quicFunctions.c',original/'quicFunctions.h',BASE/'quic-fixed-candidate/packet-processor.c',parser/'quic_initial.c',parser/'quic_initial.h',fixture]
 with c.open_sftp() as s:
  for p in files:s.put(str(p),root+'/'+p.name)
 (OUT/'sources.json').write_text(json.dumps({'remote':root,'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2),encoding='utf-8')
 cmd='cd '+shlex.quote(root)+' && set -eu\n'+f"flags='-O1 -g -DALLOW_EXPERIMENTAL_API -pthread -I{fixed}/headers/usr/include -I{fixed}/headers/usr/include/x86_64-linux-gnu -L{fixed}/link'\n"+r'''
! grep -q 'remove(db_path)' policyServer.c
gcc $flags -Dmain=archived_main -c packet-processor.c -o crafter.o >build.log 2>&1
gcc $flags $(pkg-config --cflags libdpdk libcurl jansson sqlite3 rdkafka) policyServer.c snmp_reporter.c thesis_dataplane.c quic_initial.c quicFunctions.c crafter.o -o policyServer-thesis-candidate $(pkg-config --libs libdpdk libcurl jansson sqlite3 rdkafka) -lcrypto >>build.log 2>&1
gcc $flags $(pkg-config --cflags libdpdk) test_thesis_dataplane.c thesis_dataplane.c snmp_reporter.c quic_initial.c quicFunctions.c crafter.o -o dataplane-gate $(pkg-config --libs libdpdk) -lcrypto >>build.log 2>&1
timeout 20s ./dataplane-gate client-initial-1.bin close-test.bin >gate.log 2>&1
sha256sum policyServer-thesis-candidate
systemctl is-active netpro-policy
'''
 rc,out,err=run_remote_command(c,cmd,timeout=60)
 (OUT/'execution.json').write_text(json.dumps({'exit':rc,'stdout':out,'stderr':err,'command':cmd},indent=2),encoding='utf-8')
 with c.open_sftp() as s:
  for name in ('build.log','gate.log','close-test.bin'):
   try:s.get(root+'/'+name,str(OUT/name))
   except OSError:pass
 print('Build/test:',rc,out,err[:300]);print('EVIDENCE:',OUT)
 if rc:raise SystemExit(1)
 print((OUT/'gate.log').read_text()[-1500:])
finally:
 if c:c.close()
