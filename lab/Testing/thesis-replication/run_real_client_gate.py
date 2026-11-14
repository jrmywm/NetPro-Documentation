"""Generate fresh aioquic Initials and test candidate Close consumption, off-path."""
from pathlib import Path
import sys,json,datetime,base64,shlex,hashlib
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
WORK=Path('C:/Users/jim/Documents/Codex/2026-09-11/referenced-chatgpt-conversation-this-is-an-2/work')
OUT=BASE/'evidence'/('quic-real-client-gate-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
ps=client=None
try:
 fixed=json.loads((sorted((BASE/'evidence').glob('quic-fixed-gate-*'))[-1]/'sources.json').read_text())['directory']
 endpoint=json.loads((sorted((BASE/'evidence').glob('quic-endpoint-*'))[-1]/'directories.json').read_text())['client']
 ps,_=connect_verified('192.168.31.31','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
 client,_=connect_verified('192.168.31.39','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
 rc,root,err=run_remote_command(ps,'mktemp -d /home/netpro/incoming/quic-real-client-gate.XXXXXX');root=root.strip()
 if rc:raise RuntimeError(err)
 parser=WORK/'snmp-quic-integration/quic-offline/linux-bundle-v5'
 files=[parser/'quic_initial.c',parser/'quic_initial.h',BASE/'quic_fixture_close.c']
 with ps.open_sftp() as s:
  for p in files:s.put(str(p),root+'/'+p.name)
 with client.open_sftp() as s:s.put(str(BASE/'quic_endpoint.py'),endpoint+'/quic_endpoint.py')
 command='cd '+shlex.quote(root)+' && gcc -O1 -g -I'+shlex.quote(fixed+'/headers/usr/include')+' -I'+shlex.quote(fixed+'/headers/usr/include/x86_64-linux-gnu')+' -I'+shlex.quote(fixed)+' quic_initial.c quic_fixture_close.c '+shlex.quote(fixed+'/normal-packet.o')+' '+shlex.quote(fixed+'/quicFunctions.c')+' -L'+shlex.quote(fixed+'/link')+' -lcrypto -pthread -o fixture-close'
 rc,out,err=run_remote_command(ps,command,timeout=30)
 (OUT/'build.json').write_text(json.dumps({'command':command,'exit':rc,'stdout':out,'stderr':err,'remote':root},indent=2),encoding='utf-8')
 if rc:raise RuntimeError('candidate build failed: '+err)
 results=[]
 for i in range(1,6):
  stdin,stdout,stderr=client.exec_command('cd '+shlex.quote(endpoint)+' && timeout 20s venv/bin/python -u quic_endpoint.py close-gate',timeout=25)
  initial=base64.b64decode(stdout.readline().strip(),validate=True)
  (OUT/f'initial-{i}.bin').write_bytes(initial)
  with ps.open_sftp() as s:
   with s.file(root+'/initial.bin','wb') as f:f.write(initial)
  rc,out,err=run_remote_command(ps,'cd '+shlex.quote(root)+' && ./fixture-close initial.bin close.bin',timeout=8)
  if rc:stdin.close();raise RuntimeError('fixture gate failed: '+out+err)
  with ps.open_sftp() as s:
   with s.file(root+'/close.bin','rb') as f:close=f.read()
  (OUT/f'close-{i}.bin').write_bytes(close)
  stdin.write(base64.b64encode(close).decode()+'\n');stdin.flush();stdin.close()
  result=json.loads(stdout.readline());result.update(trial=i,classifier=out,client_exit=stdout.channel.recv_exit_status(),stderr=stderr.read().decode())
  results.append(result);print(json.dumps(result),flush=True)
  (OUT/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
  if not result['passed']:raise RuntimeError('client did not accept Close')
 (OUT/'source-hashes.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files+[BASE/'quic_endpoint.py']},indent=2),encoding='utf-8')
except Exception as e:
 (OUT/'failure.txt').write_text(str(e),encoding='utf-8');print('STOP:',str(e));raise
finally:
 if ps:ps.close()
 if client:client.close()
 print('EVIDENCE:',OUT)
