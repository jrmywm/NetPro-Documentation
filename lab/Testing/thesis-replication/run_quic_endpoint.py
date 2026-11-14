"""Prepare private dependency environments and bounded echo endpoint baseline."""
from pathlib import Path
import sys,json,datetime,shlex
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
OUT=BASE/'evidence'/('quic-endpoint-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
connections={};roots={};pid=None;failed=False
def run(role,cmd,timeout=30):
 rc,out,err=run_remote_command(connections[role],cmd,timeout=timeout)
 with (OUT/(role+'-operations.jsonl')).open('a',encoding='utf-8') as f:f.write(json.dumps({'command':cmd,'exit':rc,'stdout':out,'stderr':err})+'\n')
 if rc:raise RuntimeError(role+': '+err[-700:]+' '+out[-500:])
 return out.strip()
try:
 for role,ip in [('gateway','192.168.31.37'),('client','192.168.31.39')]:
  connections[role],_=connect_verified(ip,'netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
  roots[role]=run(role,'mktemp -d /home/netpro/quic-replication.XXXXXX')
  with connections[role].open_sftp() as s:s.put(str(BASE/'quic_endpoint.py'),roots[role]+'/quic_endpoint.py')
  print('Preparing private QUIC environment:',role,roots[role],flush=True)
  run(role,'cd '+shlex.quote(roots[role])+" && python3 -m venv --without-pip venv && curl --fail --silent --show-error --max-time 30 https://bootstrap.pypa.io/pip/pip.pyz -o pip.pyz && sha256sum pip.pyz >bootstrap.sha256 && venv/bin/python pip.pyz --isolated --disable-pip-version-check install --only-binary=:all: --index-url https://pypi.org/simple 'aioquic==1.3.0' >install.log 2>&1 && venv/bin/python pip.pyz --isolated freeze >requirements.lock",timeout=180)
 (OUT/'directories.json').write_text(json.dumps(roots,indent=2),encoding='utf-8')
 run('gateway','cd '+shlex.quote(roots['gateway'])+" && openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 1 -subj /CN=netpro-quic.test >certificate.log 2>&1 && venv/bin/python -c 'import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind((\"192.168.80.28\",18443)); s.close()'")
 pid=int(run('gateway','cd '+shlex.quote(roots['gateway'])+' || exit 1; nohup timeout 45s venv/bin/python -u quic_endpoint.py server >server.log 2>&1 < /dev/null & echo $!'))
 # Readiness is observed, rather than assuming process creation means a bound port.
 run('gateway',"for i in 1 2 3 4 5; do if ss -lun | awk '/192.168.80.28:18443/ {found=1} END {exit !found}'; then exit 0; fi; sleep 1; done; exit 1")
 for trial in range(1,6):
  out=run('client','cd '+shlex.quote(roots['client'])+f' && venv/bin/python quic_endpoint.py client --initial initial-{trial}.bin',timeout=12)
  result=json.loads(out);(OUT/f'trial-{trial}.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print('Trial',trial,out,flush=True)
except Exception as e:failed=True;print('STOP:',str(e),flush=True);(OUT/'failure.txt').write_text(str(e),encoding='utf-8')
finally:
 if pid and 'gateway' in connections:
  # timeout owns a process group. Do not kill a reused PID or an unrelated command.
  try:run('gateway',f"if test -r /proc/{pid}/cmdline && tr '\\0' ' ' </proc/{pid}/cmdline | grep -F 'quic_endpoint.py server' >/dev/null; then kill -TERM {pid}; fi")
  except Exception as e:print('Cleanup warning:',str(e))
 for role,c in connections.items():
  try:
   with c.open_sftp() as s:
    for name in ('requirements.lock','bootstrap.sha256','install.log','server.log')+tuple(f'initial-{i}.bin' for i in range(1,6)):
     try:s.get(roots[role]+'/'+name,str(OUT/(role+'-'+name)))
     except OSError:pass
  finally:c.close()
 print('EVIDENCE:',OUT,flush=True)
raise SystemExit(1 if failed else 0)
