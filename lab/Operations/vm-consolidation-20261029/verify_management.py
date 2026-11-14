"""Read-only consolidated management and baseline checks."""
from pathlib import Path
import datetime,json,os,sys
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified,run_remote_command,redact
out=Path(__file__).resolve().parent/'evidence'/('management-verify-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
cred=os.environ.get('NETPRO_LAB_PASSWORD','netpro');c=None
try:
 c,_=connect_verified('192.168.31.35','netpro',cred,Path(r'C:\Users\jim\.ssh\known_hosts'))
 cmd='''set -eu
hostname
uptime
systemctl is-active netpro-kafka-compatibility-ip netpro-zookeeper netpro-kafka netpro-backend nginx postgresql netpro-snmptrapd zabbix-server
free -m
ip -4 -br addr show ens33
for route in / /dashboard /npb /ps; do curl -kfsS --max-time 10 -o /dev/null -w "PAGE_${route}=%{http_code}\\n" "https://127.0.0.1:3005$route"; done
for route in /npb/npbs /ps/pss /ps/blocked-list; do printf '\\nAPI_%s=' "$route"; curl -kfsS --max-time 10 "https://127.0.0.1:3005/api$route"; done
printf '\\n'
JAVA_HOME=/opt/netpro-runtime/java-17-openjdk-amd64 KAFKA_HEAP_OPTS='-Xms32m -Xmx128m' /home/netpro/kafka_2.13-3.6.1/bin/kafka-topics.sh --bootstrap-server 127.0.0.1:9092 --describe --topic dpdk-blocked-list
sudo -u postgres psql -d test -Atc 'SELECT count(*) FROM ps_blocked_list;'
systemctl cat netpro-snmptrapd
test -r /var/www/netpro-frontend-20261028T153203Z/index.html
'''
 rc,o,e=run_remote_command(c,cmd,sudo_password=cred,timeout=90)
 (out/'result.json').write_text(json.dumps({'exit':rc,'stdout':redact(o),'stderr':redact(e)},indent=2),encoding='utf-8')
 print('EXIT',rc,'EVIDENCE',out);print(redact(o));print(redact(e));sys.exit(rc)
finally:
 if c:c.close()
