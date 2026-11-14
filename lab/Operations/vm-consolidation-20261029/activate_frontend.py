"""Activate staged static frontend using an isolated nginx configuration."""
from pathlib import Path
import datetime,json,os,sys
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified,run_remote_command,redact
base=Path(__file__).resolve().parent
stages=sorted((base/'evidence').glob('frontend-stage-*/stage.json'))
if not stages:raise SystemExit('No completed frontend stage')
stage=json.loads(stages[-1].read_text(encoding='utf-8'));root=stage['static_root']
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=base/'evidence'/('frontend-activate-'+stamp);out.mkdir(parents=True)
credential=os.environ.get('NETPRO_LAB_PASSWORD','netpro')
conf=f'''server {{
    listen 3005 ssl;
    server_name _;
    ssl_certificate /home/ubuntu/cert/server.crt;
    ssl_certificate_key /home/ubuntu/cert/server.key;
    root {root};
    index index.html;
    location /api/ {{
        proxy_pass https://127.0.0.1:3000/;
        proxy_ssl_verify off;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }}
    location / {{ try_files $uri $uri/ /index.html; }}
}}
'''
(out/'netpro-frontend.conf').write_text(conf,encoding='utf-8')
c=None
try:
 c,h=connect_verified('192.168.31.35','netpro',credential,Path(r'C:\Users\jim\.ssh\known_hosts'))
 dest=f'/home/netpro/consolidation-stage/{stage["stamp"]}/netpro-frontend.conf'
 with c.open_sftp() as s:s.put(str(out/'netpro-frontend.conf'),dest)
 command=f'''set -eu
test ! -e /etc/nginx/conf.d/netpro-frontend.conf
test -s {root}/index.html
install -m 0644 {dest} /etc/nginx/conf.d/netpro-frontend.conf
if ! nginx -t; then mv /etc/nginx/conf.d/netpro-frontend.conf /etc/nginx/conf.d/netpro-frontend.conf.failed-{stamp}; exit 1; fi
systemctl reload nginx
curl -kfsS --max-time 10 https://127.0.0.1:3005/ -o /tmp/netpro-consolidation-index-{stamp}.html
grep -q '<div id="root">' /tmp/netpro-consolidation-index-{stamp}.html
curl -kfsS --max-time 10 https://127.0.0.1:3005/dashboard -o /dev/null
curl -kfsS --max-time 10 https://127.0.0.1:3005/api/npb/npbs
curl -kfsS --max-time 10 https://127.0.0.1:3005/api/ps/pss
'''
 rc,o,e=run_remote_command(c,command,sudo_password=credential,timeout=45)
 (out/'result.json').write_text(json.dumps({'exit':rc,'stdout':redact(o),'stderr':redact(e),'url':'https://192.168.31.35:3005'},indent=2),encoding='utf-8')
 print('EXIT',rc,'EVIDENCE',out);print(redact(o));print(redact(e));sys.exit(rc)
finally:
 if c:c.close()
