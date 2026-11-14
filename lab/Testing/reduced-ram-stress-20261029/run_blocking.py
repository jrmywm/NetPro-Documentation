"""Monitor all six guests while executing the existing bounded RST workload."""
from pathlib import Path
from datetime import datetime,timezone
import json,os,subprocess,sys
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified,run_remote_command,redact
base=Path(__file__).resolve().parent
run='blocking-monitor-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=base/'evidence'/run;out.mkdir(parents=True)
hosts={'management':'192.168.31.35','npb':'192.168.31.33','policy':'192.168.31.31','tap':'192.168.31.38','gateway':'192.168.31.37','client':'192.168.31.39'}
cred=os.environ.get('NETPRO_LAB_PASSWORD','netpro');clients={};folders={};units=[]
status='failed';test_run=None;error=None
def command(role,cmd,sudo=False):
 rc,o,e=run_remote_command(clients[role],cmd,sudo_password=cred if sudo else None,timeout=30)
 if rc:raise RuntimeError(role+': '+redact(e[-900:]))
 return o
try:
 for role,ip in hosts.items():
  clients[role],_=connect_verified(ip,'netpro',cred,Path(r'C:\Users\jim\.ssh\known_hosts'))
  folder=command(role,'mktemp -d /home/netpro/incoming/ram-blocking.XXXXXXXX').strip()
  assert folder.startswith('/home/netpro/incoming/ram-blocking.')
  folders[role]=folder
  with clients[role].open_sftp() as s:s.put(str(base/'lab_worker.py'),folder+'/lab_worker.py')
  unit=run+'-'+role
  command(role,f'systemd-run --quiet --collect --unit={unit} --property=RuntimeMaxSec=600 --property=User=netpro /usr/bin/python3 {folder}/lab_worker.py monitor --folder {folder}',sudo=True)
  units.append((role,unit))
 before=set((base/'evidence').glob('rst-stress-*'))
 print('Concurrent TLS blocking: 32 deny and 32 allow at concurrency 4/8/16',flush=True)
 env=dict(os.environ,PYTHONIOENCODING='utf-8')
 result=subprocess.run([sys.executable,'-u',str(base/'run_rst_stress.py')],env=env,timeout=360)
 created=set((base/'evidence').glob('rst-stress-*'))-before
 assert len(created)==1,'Unexpected RST evidence directory count'
 test_run=created.pop()
 results=json.loads((test_run/'summary.json').read_text(encoding='utf-8'))
 assert result.returncode==0 and len(results)==3 and all(r['exit']==0 for r in results),'RST trial workflow did not pass all three levels'
 cases=[json.loads(f.read_text(encoding='utf-8')) for f in sorted(test_run.glob('c*-*.json'))]
 assert len(cases)==6 and all(r['passed'] for r in cases),'Concurrent trial/capture acceptance failed'
 status='passed'
except Exception as exc:
 error=redact(str(exc));print('STOP',error,flush=True)
finally:
 for role,unit in units:
  try:command(role,f'systemctl stop {unit}.service',sudo=True)
  except Exception as exc:error=(error or '')+'; cleanup '+role+': '+redact(str(exc));status='failed'
 for role,folder in folders.items():
  try:
   with clients[role].open_sftp() as s:s.get(folder+'/resource.jsonl',str(out/(role+'-resource.jsonl')))
  except Exception as exc:error=(error or '')+'; evidence '+role+': '+redact(str(exc));status='failed'
 for c in clients.values():c.close()
 resources={}
 for role in hosts:
  f=out/(role+'-resource.jsonl')
  if not f.exists():continue
  rows=[json.loads(l) for l in f.read_text().splitlines() if l.strip()]
  probes=[r['management_api'] for r in rows if 'management_api' in r]
  resources[role]={'samples':len(rows),'min_available_mib':min(r['memory_kib']['MemAvailable'] for r in rows)/1024,'max_swap_mib':max(r['memory_kib']['SwapTotal']-r['memory_kib']['SwapFree'] for r in rows)/1024,'oom_delta':rows[-1]['vmstat']['oom_kill']-rows[0]['vmstat']['oom_kill'],'api_success':sum(p['exit']==0 and p['http']=='200' for p in probes),'api_total':len(probes)}
  resources[role]['initial_swap_mib']=(rows[0]['memory_kib']['SwapTotal']-rows[0]['memory_kib']['SwapFree'])/1024
  resources[role]['swap_out_pages_delta']=rows[-1]['vmstat']['pswpout']-rows[0]['vmstat']['pswpout']
  if resources[role]['oom_delta'] or resources[role]['max_swap_mib'] or resources[role]['min_available_mib']<128 or resources[role]['api_success']!=len(probes):status='failed'
 (out/'summary.json').write_text(json.dumps({'status':status,'error':error,'rst_evidence':str(test_run) if test_run else None,'resources':resources},indent=2),encoding='utf-8')
 print('BLOCKING_STATUS',status,'EVIDENCE',out,flush=True)
sys.exit(0 if status=='passed' else 1)
