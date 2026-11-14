"""Read-only checks and telemetry for the completed load window."""
from pathlib import Path
import argparse,datetime,json,os,shlex,sys
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified,run_remote_command,redact
p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();root=a.run
summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
start=min(s['start_utc_epoch'] for s in summary['stages']);end=max(s['end_utc_epoch'] for s in summary['stages'])
cred=os.environ.get('NETPRO_LAB_PASSWORD','netpro');clients=[];results={}
queries={
 'management':('192.168.31.35',f'''set -eu
systemctl is-active netpro-kafka-compatibility-ip netpro-zookeeper netpro-kafka netpro-backend nginx postgresql netpro-snmptrapd zabbix-server
curl -kfsS --max-time 10 https://127.0.0.1:3005/api/ps/blocked-list
sudo -u postgres psql -d test -c "SELECT COUNT(*) AS samples,SUM(http_count) AS http,SUM(https_count) AS tls,SUM(rx_i_count) AS rx,SUM(tx_o_http_count) AS tx_http,SUM(tx_o_tls_count) AS tx_tls FROM npb_packet WHERE time >= to_timestamp({start}) AND time <= to_timestamp({end});"
sudo -u postgres psql -d test -c "SELECT COUNT(*) AS samples,SUM(rx_i_http_count) AS http,SUM(rx_i_tls_count) AS tls FROM ps_packet WHERE time >= to_timestamp({start}) AND time <= to_timestamp({end});"
'''),
 'policy':('192.168.31.31',r'''set -eu
systemctl is-active netpro-policy netpro-dpdk-prepare
sqlite3 /home/ubuntu/NetPro-Policy-Server/policy.db 'PRAGMA integrity_check; SELECT id FROM policies ORDER BY id;'
free -m
grep -E 'HugePages_|Hugepagesize' /proc/meminfo
'''),
 'npb':('192.168.31.33',r'''set -eu
systemctl is-active netpro-npb netpro-npb-dpdk-prepare
free -m
grep -E 'HugePages_|Hugepagesize' /proc/meminfo
'''),
 'gateway':('192.168.31.37',r'''set -eu
test ! -e /run/netpro-tap-live-test
test ! -e /run/netpro-dedicated-rst-return
if ss -H -ltn | awk '$4 ~ /:(18080|18443|8080|8443)$/ {found=1} END {exit !found}'; then echo UNEXPECTED_TEST_LISTENER; exit 1; fi
echo NO_OWNED_TEST_LISTENERS
free -m
''')
}
try:
 for role,(ip,cmd) in queries.items():
  c,h=connect_verified(ip,'netpro',cred,Path(r'C:\Users\jim\.ssh\known_hosts'));clients.append(c)
  rc,o,e=run_remote_command(c,cmd,sudo_password=cred,timeout=45)
  results[role]={'exit':rc,'stdout':redact(o),'stderr':redact(e)}
  print(role,'EXIT',rc);print(redact(o));print(redact(e))
 (root/'POSTFLIGHT.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
 sys.exit(0 if all(r['exit']==0 for r in results.values()) else 1)
finally:
 for c in clients:c.close()
