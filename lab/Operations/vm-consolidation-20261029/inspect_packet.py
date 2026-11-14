from pathlib import Path
import argparse,datetime,json,os,sys
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified,run_remote_command,redact
p=argparse.ArgumentParser();p.add_argument('role',choices=['policy','npb','tap','gateway','client']);a=p.parse_args()
roles={'policy':('192.168.31.31','/home/netpro/NetPro-Policy-Server'),'npb':('192.168.31.33','/home/netpro/NetPro-Network-Packet-Broker'),'tap':('192.168.31.38',''),'gateway':('192.168.31.37',''),'client':('192.168.31.39','')}
ip,root=roles[a.role];cred=os.environ.get('NETPRO_LAB_PASSWORD','netpro')
cmd='''hostname; free -m; grep -E 'HugePages_|Hugepagesize' /proc/meminfo; ip -4 -br addr
systemctl list-units --type=service --all --no-pager --plain | grep -Ei 'netpro|tinyproxy|caddy|snmp' || true
'''
if root:
 cmd+=fr'''cat {root}/config/config.cfg
readlink -f {root}/build/{'policyServer' if a.role=='policy' else 'packetBroker'}
git -C {root} status --short
systemctl cat {'netpro-policy' if a.role=='policy' else 'netpro-npb'}
systemctl cat {'netpro-dpdk-prepare' if a.role=='policy' else 'netpro-npb-dpdk-prepare'}
grep -nE 'hugepages|nr_hugepages' /usr/local/sbin/netpro* 2>/dev/null | head -n 25 || true
grep -n 'KAFKA_BROKER\|bootstrap.servers' {root}/{'policyServer.c' if a.role=='policy' else 'packetBroker.c'} || true
strings {root}/build/{'policyServer' if a.role=='policy' else 'packetBroker'} | grep -E '192\.168\..*:9092' || true
'''
 if a.role=='policy':
  cmd+='''sqlite3 -header -column /home/ubuntu/NetPro-Policy-Server/policy.db 'SELECT id,domain,ip_address FROM policies ORDER BY id;'
sqlite3 /home/ubuntu/NetPro-Policy-Server/policy.db 'PRAGMA integrity_check;'
grep -nE 'DELETE FROM|delete_all|DELETE_ALL|initial|allBlocked|truncate|strcmp.*type' /home/netpro/NetPro-Policy-Server/policyServer.c | head -n 25
'''
else:
 cmd+='''ip -4 route; bridge link; tc filter show dev ens36 egress 2>/dev/null || true
find /usr/local/libexec /home/netpro/netpro-demo -maxdepth 3 -type f -name '*.sh' 2>/dev/null | head -n 25
'''
c=None
try:
 c,h=connect_verified(ip,'netpro',cred,Path(r'C:\Users\jim\.ssh\known_hosts'))
 rc,o,e=run_remote_command(c,cmd,sudo_password=cred,timeout=40)
 out=Path(__file__).resolve().parent/'evidence'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-packet-'+a.role);out.mkdir(parents=True)
 (out/'result.json').write_text(json.dumps({'exit':rc,'stdout':redact(o),'stderr':redact(e)},indent=2),encoding='utf-8')
 print('EVIDENCE',out);print(redact(o));print(redact(e))
finally:
 if c:c.close()
