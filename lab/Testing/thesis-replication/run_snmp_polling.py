"""Private read-only Net-SNMP agent and cross-VM system-counter polling.
No production snmpd config/package installation. Not a Zabbix deployment and
not custom PS process telemetry. Agent port/community restricted to Backend.
"""
from pathlib import Path
import sys,json,datetime,shlex,time,re
BASE=Path(__file__).resolve().parent;sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
OUT=BASE/'evidence'/('snmp-polling-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
clients={};root=None;unit=None;failed=False;errors=[];rows=[];q=shlex.quote
def command(host,label,code,sudo=False,timeout=30):
 rc,o,e=run_remote_command(clients[host],code,sudo_password=__import__('os').environ['NETPRO_LAB_PASSWORD'] if sudo else None,timeout=timeout)
 with (OUT/'commands.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'host':host,'label':label,'command':code,'exit':rc,'stdout':o,'stderr':e})+'\n')
 if rc:raise RuntimeError(label+': '+e[-400:]+o[-400:])
 return o.strip()
try:
 for host in ['192.168.31.31','192.168.31.35']:clients[host],_=connect_verified(host,'netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
 private='/home/netpro/incoming/snmp-replication-bench.SFH9aM/private'
 root=command('192.168.31.31','private_agent_directory','mktemp -d /home/netpro/incoming/thesis-snmp-agent.XXXXXX')
 script='''set -eu
cd ROOT
cp -a PRIVATE private
apt-get download snmpd=5.8+dfsg-2ubuntu2.9 >download.log 2>&1
deb=snmpd_5.8+dfsg-2ubuntu2.9_amd64.deb
test "$(sha256sum "$deb" | cut -d' ' -f1)" = "$(apt-cache show snmpd=5.8+dfsg-2ubuntu2.9 | awk '$1=="SHA256:" {print $2;exit}')"
dpkg-deb -x "$deb" private
mkdir persistent home
'''.replace('ROOT',q(root)).replace('PRIVATE',q(private))
 command('192.168.31.31','verified_private_agent_package',script,timeout=60)
 conf='agentaddress udp:192.168.31.31:11625\nrocommunity public 192.168.31.35\nsysLocation NetPro-isolated-thesis-polling\n'
 with clients['192.168.31.31'].open_sftp() as s:
  with s.file(root+'/snmpd.conf','w') as f:f.write(conf)
 command('192.168.31.31','guard_agent_port',"test -z \"$(ss -H -lun 'sport = :11625')\"")
 unit='netpro-'+Path(root).name
 env='LD_LIBRARY_PATH='+root+'/private/usr/lib/x86_64-linux-gnu:'+root+'/private/lib/x86_64-linux-gnu'
 command('192.168.31.31','start_bounded_private_agent','systemd-run --quiet --collect --unit='+unit+' --uid=netpro --property=RuntimeMaxSec=90 /usr/bin/env '+q(env)+' MIBS= SNMP_PERSISTENT_DIR='+q(root+'/persistent')+' HOME='+q(root+'/home')+' '+q(root+'/private/usr/sbin/snmpd')+' -f -C -c '+q(root+'/snmpd.conf')+' -Lo -p '+q(root+'/snmpd.pid'),sudo=True)
 time.sleep(1)
 snmp=BASE/'evidence/snmp-live-http-20261012T233321Z'
 doc=json.loads(next(snmp.glob('active-baseline*.json')).read_text())
 rxroot=next(e['stdout'].strip() for e in doc['events'] if e.get('label')=='receiver_private_directory')
 clientprivate=rxroot+'/private'
 names={'1.3.6.1.2.1.1.3.0':'sys_uptime','1.3.6.1.4.1.2021.4.5.0':'mem_total_real_kib','1.3.6.1.4.1.2021.4.6.0':'mem_available_real_kib','1.3.6.1.4.1.2021.11.50.0':'cpu_raw_user','1.3.6.1.4.1.2021.11.52.0':'cpu_raw_system','1.3.6.1.4.1.2021.11.53.0':'cpu_raw_idle'}
 clientenv='LD_LIBRARY_PATH='+clientprivate+'/usr/lib/x86_64-linux-gnu:'+clientprivate+'/lib/x86_64-linux-gnu'
 for i in range(10):
  raw=command('192.168.31.35','poll_'+str(i+1),'env '+q(clientenv)+' MIBS= '+q(clientprivate+'/usr/bin/snmpget')+' -v2c -c public -On -t 2 -r 1 udp:192.168.31.31:11625 '+' '.join(names),timeout=8)
  if 'No Such' in raw:raise RuntimeError('A requested monitoring OID is unsupported; do not report a complete polling pass')
  row={'sample':i+1,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'raw':raw,'values':{}}
  for line in raw.splitlines():
   oid=line.split(' = ')[0].lstrip('.')
   if oid in names:row['values'][names[oid]]=line.split(' = ',1)[1]
  if len(row['values'])!=len(names):raise RuntimeError('Missing polling varbinds')
  rows.append(row);(OUT/'samples.json').write_text(json.dumps(rows,indent=2),encoding='utf-8');print('poll',i+1,json.dumps(row['values']),flush=True)
  time.sleep(2)
except Exception as e:
 failed=True;(OUT/'failure.txt').write_text(str(e),encoding='utf-8');print('STOP:',e,flush=True)
finally:
 if unit:
  try:command('192.168.31.31','stop_private_agent','systemctl stop '+unit+' || test "$(systemctl show '+unit+' -p LoadState --value)" = not-found',sudo=True)
  except Exception as e:errors.append(str(e))
 if clients.get('192.168.31.31'):
  try:command('192.168.31.31','released_private_port',"test -z \"$(ss -H -lun 'sport = :11625')\"")
  except Exception as e:errors.append(str(e))
 (OUT/'cleanup.json').write_text(json.dumps({'failed':failed,'errors':errors,'successful_samples':len(rows)},indent=2),encoding='utf-8')
 for c in clients.values():c.close()
 print('EVIDENCE:',OUT,flush=True)
raise SystemExit(1 if failed or errors else 0)
