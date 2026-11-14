from pathlib import Path
import sys,datetime,shlex,json,re,hashlib
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
OUT=BASE/'evidence'/('snmp-sender-bench-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
c=None
try:
 c,_=connect_verified('192.168.31.31','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
 rc,out,err=run_remote_command(c,'bash /home/netpro/incoming/isolated-snmp-receiver-20261010/run-private-validation.sh',timeout=45)
 if rc:raise RuntimeError('receiver dependency validation failed '+err)
 match=re.search(r'Private run evidence: (\S+)',out)
 if not match:raise RuntimeError('missing validated runtime')
 private=match.group(1)+'/root'
 rc,root,err=run_remote_command(c,'mktemp -d /home/netpro/incoming/snmp-replication-bench.XXXXXX')
 if rc:raise RuntimeError(err)
 root=root.strip()
 files=[BASE/'snmp_sender_gate.c',BASE/'snmp_receiver_bench.py']
 with c.open_sftp() as s:
  for f in files:s.put(str(f),root+'/'+f.name)
 (OUT/'sources.json').write_text(json.dumps({'remote_directory':root,'scope':'isolated branch-style SNMP sender only, not full thesis replication','hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2),encoding='utf-8')
 cmd='set -eu; cd '+shlex.quote(root)+'; cp -a '+shlex.quote(private)+' private; apt-get download snmp=5.8+dfsg-2ubuntu2.9 > download.log 2>&1; meta="$(apt-cache show snmp=5.8+dfsg-2ubuntu2.9)"; deb=snmp_5.8+dfsg-2ubuntu2.9_amd64.deb; test "$(sha256sum "$deb" | cut -d\' \' -f1)" = "$(printf \'%s\\n\' "$meta" | awk \'$1=="SHA256:" {print $2;exit}\')"; dpkg-deb -x "$deb" private; gcc -O2 -Wall -Wextra -Werror snmp_sender_gate.c -o sender; timeout --signal=TERM --kill-after=5s 600s python3 -u snmp_receiver_bench.py'
 (OUT/'commands.sh').write_text(cmd,encoding='utf-8')
 print('Benchmark started:',root,flush=True)
 rc,out,err=run_remote_command(c,cmd,timeout=650)
 (OUT/'execution.json').write_text(json.dumps({'exit':rc,'stdout':out,'stderr':err},indent=2),encoding='utf-8')
 with c.open_sftp() as s:
  for f in ('download.log','receiver.log','results.json','cleanup.json')+tuple(f'sender-{i}.log' for i in range(1,6)):
   try:s.get(root+'/'+f,str(OUT/f))
   except OSError:pass
 print('Benchmark exit:',rc,out[:3000],err[:500],flush=True)
 print('EVIDENCE:',OUT,flush=True)
finally:
 if c:c.close()
