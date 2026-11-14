import json,concurrent.futures,shlex,os
from pathlib import Path
import paramiko
OUT=Path(__file__).resolve().parent
jobs={
'management':(35,'python3 /home/netpro/recovered-theses-20261030/final-health.py',True),
'monitoring-config':(35,"systemctl list-units --all --no-legend '*snmp*' '*zabbix*'; ss -lunp | grep ':162 '; systemctl --failed --no-legend",True),
'policy-schema':(31,"python3 - <<'PY'\nimport sqlite3,json\nc=sqlite3.connect('file:/home/ubuntu/NetPro-Policy-Server/policy.db?mode=ro',uri=True)\nprint('Domain indices:',c.execute(\"SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='policies'\").fetchall())\nprint('Policy rows:',c.execute('SELECT COUNT(*) FROM policies').fetchone()[0])\nPY",True)
}
def run(item):
 label,(n,cmd,sudo)=item;c=paramiko.SSHClient();c.load_host_keys(str(Path.home()/'.ssh/known_hosts'))
 try:
  c.connect('192.168.31.'+str(n),username='netpro',password=os.environ['NETPRO_LAB_PASSWORD'],timeout=10)
  i,o,e=c.exec_command(('sudo -S -p "" bash -c '+shlex.quote(cmd) if sudo else cmd),timeout=40)
  if sudo:i.write(os.environ['NETPRO_LAB_PASSWORD']+'\n');i.flush()
  out=o.read().decode();err=e.read().decode();rc=o.channel.recv_exit_status()
  return dict(label=label,rc=rc,stdout=out,stderr=err)
 finally:c.close()
with concurrent.futures.ThreadPoolExecutor() as p:rs=list(p.map(run,jobs.items()))
(OUT/'management.json').write_text(json.dumps(rs,indent=2),encoding='utf8')
for r in rs:print(json.dumps(r))


