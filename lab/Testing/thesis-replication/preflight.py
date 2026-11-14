"""Read-only lab checks before thesis replication. Strict SSH host verification."""
from pathlib import Path
import sys,json,datetime
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
OUT=BASE/'evidence'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
OUT.mkdir(parents=True,exist_ok=True)
commands={
 'policy-state':'hostname; systemctl is-active netpro-policy; readlink /home/netpro/NetPro-Policy-Server/build/policyServer; free -m; ip -br addr',
 'database':'sqlite3 -readonly /home/ubuntu/NetPro-Policy-Server/policy.db "PRAGMA integrity_check; SELECT id,domain,ip_address FROM policies;"',
 'module-files':'find /home/netpro/incoming -maxdepth 2 -type f \\( -name "*candidate*" -o -name "*validation.sh" -o -name "test-v5*" -o -name "*reporter*" \\) -printf "%p\\n"',
 'snmp-environment':'command -v snmptrap || true; command -v snmptrapd || true; pkg-config --modversion netsnmp 2>/dev/null || true; apt-cache show snmp | head -n 14; find /home/netpro/incoming/isolated-snmp-receiver-20261010 -maxdepth 5 -type f -name snmptrapd -print | head -n 2; true',
}
if '--all' in sys.argv:
 hosts={'192.168.31.31':'policy-server-vm','192.168.31.32':'kafka-broker-vm','192.168.31.33':'npb-vm','192.168.31.34':'packet-generator-vm','192.168.31.35':'backend-vm','192.168.31.36':'frontend-vm','192.168.31.37':'netpro-test-gateway','192.168.31.38':'netpro-virtual-tap','192.168.31.39':'netpro-test-client'}
 from concurrent.futures import ThreadPoolExecutor
 def check(item):
  ip,name=item;c=None
  try:
   alias={'192.168.31.34':'192.168.31.134','192.168.31.36':'192.168.31.136'}.get(ip)
   c,_=connect_verified(ip,'netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'),trusted_host_alias=alias)
   cmd='hostname; systemctl is-active netpro-policy netpro-npb netpro-backend postgresql netpro-frontend kafka zookeeper netpro-virtual-tap-mirror; ip -4 -br addr; uptime; true'
   rc,out,err=run_remote_command(c,cmd,timeout=15)
   result={'ip':ip,'host':name,'reachable':True,'stdout':out,'stderr':err}
  except Exception as e:result={'ip':ip,'host':name,'reachable':False,'error':str(e)}
  finally:
   if c:c.close()
  return result
 with ThreadPoolExecutor(max_workers=4) as pool:
  results=list(pool.map(check,hosts.items()))
 (OUT/'all-hosts.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
 for r in results:print(r['host'],r['ip'],'SSH_OK' if r['reachable'] else r['error'],r.get('stdout','').encode('ascii','replace').decode())
 print('Evidence:',OUT)
 sys.exit(0)
c=None
try:
 c,_=connect_verified('192.168.31.31','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
 for name,cmd in commands.items():
  rc,out,err=run_remote_command(c,cmd,'netpro',timeout=15)
  (OUT/(name+'.json')).write_text(json.dumps({'exit':rc,'stdout':out,'stderr':err},indent=2),encoding='utf-8')
  print(name,'exit',rc,out[:1800].encode('ascii','replace').decode(),err[:300])
finally:
 if c:c.close()
 print('Evidence:',OUT)
