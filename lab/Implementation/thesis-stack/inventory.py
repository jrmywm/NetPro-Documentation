"""Read-only current VM/package inventory for original thesis integration."""
from pathlib import Path
import sys,json,datetime,concurrent.futures
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parents[1]/'Testing/snmp-quic-integration'))
from remote import connect_verified,run_remote_command
OUT=BASE/'evidence'/('inventory-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
command='''hostname
. /etc/os-release; printf 'OS=%s %s\\n' "$ID" "$VERSION_ID"
nproc
free -m
df -h / /opt
ip -4 route
systemctl is-active netpro-policy netpro-npb netpro-backend postgresql tinyproxy caddy zabbix-server zabbix-agent snmpd snmptrapd nginx apache2 || true
dpkg-query -W -f='${Package} ${Version} ${Status}\\n' snmp snmpd snmptrapd caddy curl zabbix-server-pgsql zabbix-agent zabbix-frontend-php nginx php-fpm 2>/dev/null || true
curl -V
ss -H -ltnu
apt-cache policy snmp snmpd snmptrapd caddy curl zabbix-server-pgsql zabbix-agent zabbix-frontend-php libnghttp3-dev libngtcp2-crypto-gnutls-dev
'''
def check(host):
 c=None
 try:
  c,a=connect_verified(host,'netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'));rc,o,e=run_remote_command(c,command,timeout=20)
  r={'ip':host,'hostname':a,'exit':rc,'stdout':o,'stderr':e}
 except Exception as e:r={'ip':host,'error':str(e)}
 finally:
  if c:c.close()
 (OUT/(host+'.json')).write_text(json.dumps(r,indent=2),encoding='utf-8')
 print(host,r.get('hostname'),r.get('error','OK'),flush=True);return r
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:r=list(pool.map(check,['192.168.31.31','192.168.31.35','192.168.31.37','192.168.31.39']))
(OUT/'summary.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print('EVIDENCE:',OUT)
