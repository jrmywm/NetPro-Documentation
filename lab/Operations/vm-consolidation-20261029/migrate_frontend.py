"""Build the existing frontend and stage a static copy on Backend-VM.

Source changes are retained, no dependencies are downloaded, and the source VM
is not shut down by this script. nginx activation is a separate reviewed step.
"""
from pathlib import Path
import datetime, hashlib, json, os, sys
sys.path.insert(0, r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified, run_remote_command, redact

base=Path(__file__).resolve().parent
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=base/'evidence'/('frontend-stage-'+stamp);out.mkdir(parents=True)
credential=os.environ.get('NETPRO_LAB_PASSWORD','netpro')
known=Path(r'C:\Users\jim\.ssh\known_hosts')
clients=[]
def run(c,label,command,sudo=False,timeout=60):
 rc,o,e=run_remote_command(c,command,sudo_password=credential if sudo else None,timeout=timeout)
 (out/(label+'.json')).write_text(json.dumps({'exit':rc,'stdout':redact(o),'stderr':redact(e)},indent=2),encoding='utf-8')
 print(label,'exit',rc,flush=True)
 if rc: raise RuntimeError(label+' failed: '+redact(e[-1200:]))
 return o
try:
 front,_=connect_verified('192.168.31.36','netpro',credential,known);clients.append(front)
 back,_=connect_verified('192.168.31.35','netpro',credential,known);clients.append(back)
 # Keep the complete current source, including uncommitted changes, on source VM.
 run(front,'source-backup',f'''set -eu
umask 077
test -d /home/netpro/NetPro-Frontend/src
mkdir -p /home/netpro/consolidation-backups/{stamp}
tar --exclude='./node_modules' --exclude='./build' --exclude='./.git' -czf /home/netpro/consolidation-backups/{stamp}/frontend-source.tar.gz -C /home/netpro/NetPro-Frontend .
git -C /home/netpro/NetPro-Frontend diff --binary > /home/netpro/consolidation-backups/{stamp}/frontend-working-tree.patch
''',timeout=90)
 # /api is supplied only to this build; .env.local and source are unchanged.
 run(front,'production-build',r'''set -eu
cd /home/netpro/NetPro-Frontend
CI=false GENERATE_SOURCEMAP=false REACT_APP_BASE_URL=/api npm run build
test -s build/index.html
''',timeout=300)
 run(front,'archive-build',f'''set -eu
umask 077
tar -czf /home/netpro/consolidation-backups/{stamp}/frontend-build.tar.gz -C /home/netpro/NetPro-Frontend/build .
sha256sum /home/netpro/consolidation-backups/{stamp}/frontend-build.tar.gz
''',timeout=60)
 with front.open_sftp() as s:
  s.get(f'/home/netpro/consolidation-backups/{stamp}/frontend-build.tar.gz',str(out/'frontend-build.tar.gz'))
  s.get(f'/home/netpro/consolidation-backups/{stamp}/frontend-source.tar.gz',str(out/'frontend-source.tar.gz'))
 archive=out/'frontend-build.tar.gz';digest=hashlib.sha256(archive.read_bytes()).hexdigest()
 run(back,'prepare-stage',f'''set -eu
umask 077
mkdir -p /home/netpro/consolidation-stage/{stamp}
''')
 with back.open_sftp() as s:s.put(str(archive),f'/home/netpro/consolidation-stage/{stamp}/frontend-build.tar.gz')
 run(back,'install-static-stage',f'''set -eu
printf '%s  %s\n' '{digest}' '/home/netpro/consolidation-stage/{stamp}/frontend-build.tar.gz' | sha256sum -c -
test ! -e /var/www/netpro-frontend-{stamp}
install -d -m 0755 /var/www/netpro-frontend-{stamp}
tar -xzf /home/netpro/consolidation-stage/{stamp}/frontend-build.tar.gz -C /var/www/netpro-frontend-{stamp}
chown -R root:root /var/www/netpro-frontend-{stamp}
find /var/www/netpro-frontend-{stamp} -type d -exec chmod 0755 {{}} +
find /var/www/netpro-frontend-{stamp} -type f -exec chmod 0644 {{}} +
test -s /var/www/netpro-frontend-{stamp}/index.html
''',sudo=True)
 (out/'stage.json').write_text(json.dumps({'stamp':stamp,'static_root':f'/var/www/netpro-frontend-{stamp}','archive_sha256':digest,'activated':False},indent=2),encoding='utf-8')
 print('STAGED',out,flush=True)
finally:
 for c in clients:c.close()
