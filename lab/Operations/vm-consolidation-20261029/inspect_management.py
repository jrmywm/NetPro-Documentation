"""Read selected configuration; never print credential values."""
from pathlib import Path
import argparse, datetime, json, os, re, sys
sys.path.insert(0, r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified, run_remote_command, redact
p=argparse.ArgumentParser();p.add_argument('host');p.add_argument('role',choices=['backend','frontend','kafka']);a=p.parse_args()
credential=os.environ.get('NETPRO_LAB_PASSWORD','netpro')
commands={
'backend': r'''systemctl cat netpro-backend
du -sh /home/netpro/NetPro-Backend /var/lib/postgresql /var/log /var/cache/apt/archives
find /home/netpro/NetPro-Backend -maxdepth 2 -name package.json -not -path '*/node_modules/*' -exec cat {} \;
grep -RInE 'kafkaHost|brokers:|bootstrap.servers|KAFKA|192\.168\.31\.3[0-9].*9092' /home/netpro/NetPro-Backend --exclude-dir=node_modules --exclude-dir=.git --exclude=package-lock.json --exclude-dir=logs | head -n 45
find /etc/nginx/sites-enabled -maxdepth 1 -type l -printf '%f\n'
node --version
curl -k -sS --max-time 5 -o /dev/null -w 'API_3000=%{http_code}\n' https://127.0.0.1:3000/npb/npbs || true
curl -k -sS --max-time 5 -o /dev/null -w 'API_80=%{http_code}\n' https://127.0.0.1/npb/npbs || true
cat /home/netpro/NetPro-Backend/src/config/kafkaConfig.js
sed -n '1,180p' /home/netpro/NetPro-Backend/index.js
journalctl -u netpro-backend -n 18 --no-pager -o cat
sed -n '1,140p' /etc/nginx/sites-enabled/default
''',
'frontend': r'''systemctl list-unit-files --no-pager | grep -Ei 'netpro|front|node|pm2'
find /home/netpro/NetPro-Frontend -maxdepth 1 -type f -printf '%f\n'
cat /home/netpro/NetPro-Frontend/package.json
du -sh /home/netpro/NetPro-Frontend /home/netpro/NetPro-Frontend/build /home/netpro/NetPro-Frontend/node_modules 2>/dev/null
systemctl cat netpro-frontend 2>/dev/null || true
git -C /home/netpro/NetPro-Frontend status --short
grep -RInE '192\.168\.|REACT_APP|localhost:3000|socket.io' /home/netpro/NetPro-Frontend/src --exclude='*.map' | head -n 45
grep -E '^(REACT_APP_BASE_URL|PORT|HOST|HTTPS|SSL_CRT_FILE|SSL_KEY_FILE)=' /home/netpro/NetPro-Frontend/.env.local
ls -ld /home/netpro/NetPro-Frontend/node_modules /home/netpro/NetPro-Frontend/build /home/ubuntu/cert
readlink -f /home/netpro/NetPro-Frontend
node --version
curl -k -sS --max-time 5 -o /dev/null -w 'FRONTEND=%{http_code}\n' https://127.0.0.1:3005/
''',
'kafka': r'''systemctl list-unit-files --no-pager | grep -Ei 'kafka|zookeeper'
systemctl cat netpro-kafka netpro-zookeeper
find /opt /home/netpro -maxdepth 3 -iname '*kafka*' -type d 2>/dev/null
ps -eo comm,rss --sort=-rss | head -n 10
java -version 2>&1
grep -Ev '^\s*(#|$)' /home/netpro/kafka_2.13-3.6.1/config/server.properties /home/netpro/kafka_2.13-3.6.1/config/zookeeper.properties
du -sh /home/netpro/kafka_2.13-3.6.1 /tmp/kafka-logs /tmp/zookeeper /var/lib/kafka /var/lib/zookeeper 2>/dev/null || true
du -sh /var/lib/netpro-kafka /var/lib/netpro-zookeeper
readlink -f /usr/bin/java
/home/netpro/kafka_2.13-3.6.1/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe
'''
}
c=None
try:
 c,h=connect_verified(a.host,'netpro',credential,Path(r'C:\Users\jim\.ssh\known_hosts'))
 rc,o,e=run_remote_command(c,commands[a.role],sudo_password=credential,timeout=45)
 o=redact(o)
 o='\n'.join('[credential-related line redacted]' if re.search(r'password|passwd|secret|token|private.key',line,re.I) else line for line in o.splitlines())
 out=Path(__file__).resolve().parent/'evidence'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-inspect-'+a.role)
 out.mkdir(parents=True,exist_ok=False)
 (out/'result.json').write_text(json.dumps({'host':h,'exit':rc,'stdout':o,'stderr':redact(e)},indent=2),encoding='utf-8')
 print('EVIDENCE',out);print(o);print(redact(e))
finally:
 if c:c.close()
