"""Upgrade the already guarded adapter and deploy the built dashboard; no rule activation."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path('/home/netpro/NetPro-Backend')
CANDIDATE = Path(__file__).resolve().parents[1]
FRONTEND = CANDIDATE.parent / 'frontend-candidate/build'
ENVFILE = Path('/etc/netpro/bulk-import.env')
NGINX = Path('/etc/nginx/conf.d/netpro-frontend.conf')
MANIFEST = json.loads((CANDIDATE / 'ops/csv-upgrade-manifest.json').read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args, **kw): return subprocess.run(args, capture_output=True, text=True, check=True, timeout=120, **kw)
def policies(): return run(['runuser','-u','postgres','--','psql','-d','test','-Atc','SELECT row_to_json(p)::text FROM ps_blocked_list p ORDER BY id']).stdout
def main():
    if os.geteuid() != 0 or socket.gethostname() != 'backend-vm': raise RuntimeError('Expected root on Management')
    if 'NETPRO_CSV_UPLOAD_ENABLED=1' in ENVFILE.read_text(): raise RuntimeError('CSV feature already deployed; use a reviewed incremental update')
    if not (FRONTEND / 'asset-manifest.json').exists(): raise RuntimeError('Production frontend build is missing')
    for rel, expected in MANIFEST['expected'].items():
        if sha(ROOT / rel) != expected: raise RuntimeError('Live source changed: ' + rel)
    for rel, expected in MANIFEST['candidate'].items():
        if sha(CANDIDATE / rel) != expected: raise RuntimeError('Candidate changed: ' + rel)
    tag = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = Path('/root/netpro-csv-dashboard-' + tag); backup.mkdir(mode=0o700)
    before = policies(); kafka_sha = sha(ROOT / 'src/config/kafkaConfig.js')
    for rel in MANIFEST['candidate']:
        if (ROOT / rel).exists():
            target = backup / rel; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(ROOT / rel, target)
    shutil.copy2(ENVFILE, backup / 'bulk-import.env'); shutil.copy2(NGINX, backup / 'nginx.conf')
    with (backup / 'postgres-test.dump').open('wb') as output:
        subprocess.run(['runuser','-u','postgres','--','pg_dump','-Fc','-d','test'], stdout=output, stderr=subprocess.PIPE, check=True, timeout=120)
    (backup / 'policies-before.jsonl').write_text(before)
    modified = False
    try:
        env = dict(os.environ, NODE_PATH=str(ROOT / 'node_modules'), NETPRO_ALLOW_LIVE_SCHEMA='1')
        run(['node', str(CANDIDATE / 'ops/migrate-csv-live.js'), '--apply-live-additive-schema'], env=env)
        owner = ROOT.stat()
        data = Path('/var/lib/netpro-imports'); data.mkdir(mode=0o700, exist_ok=True); os.chown(data, owner.st_uid, owner.st_gid)
        modified = True
        for rel in MANIFEST['candidate']:
            target = ROOT / rel; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(CANDIDATE / rel, target); os.chmod(target, 0o644); os.chown(target, owner.st_uid, owner.st_gid)
        runtime = ROOT / 'src/integration/runtime'
        if (runtime / 'node_modules').exists(): raise RuntimeError('Unexpected existing CSV runtime; inspect before replacing dependencies')
        shutil.copytree(CANDIDATE / 'src/integration/runtime/node_modules', runtime / 'node_modules', symlinks=True)
        os.chown(ROOT / 'src/integration', owner.st_uid, owner.st_gid); os.chown(runtime, owner.st_uid, owner.st_gid)
        ENVFILE.write_text(ENVFILE.read_text().rstrip() + '\nNETPRO_CSV_UPLOAD_ENABLED=1\n'); os.chmod(ENVFILE, 0o600)
        run(['systemctl', 'restart', 'netpro-backend'])
        context = ssl.create_default_context(cafile='/home/ubuntu/cert/server.crt'); context.check_hostname = False
        for _ in range(60):
            try: urllib.request.urlopen('https://127.0.0.1:3000/ps/csv-imports', context=context, timeout=3)
            except urllib.error.HTTPError as e:
                if e.code == 401: break
            except Exception: pass
            time.sleep(1)
        else: raise RuntimeError('Authenticated CSV API did not become ready')
        with urllib.request.urlopen('https://127.0.0.1:3000/import-socket/socket.io.js', context=context, timeout=5) as r:
            if r.status != 200: raise RuntimeError('Socket.IO client unavailable')
        build_root = Path('/var/www/netpro-frontend-csv-' + tag)
        shutil.copytree(FRONTEND, build_root)
        config, count = re.subn(r'root\s+[^;]+;', 'root ' + str(build_root) + ';', NGINX.read_text(), count=1)
        if count != 1: raise RuntimeError('Frontend root directive not found')
        config = config.replace('server {', 'server {\n    client_max_body_size 130m;', 1)
        config = config.replace('location /api/ {', '''location /api/ {
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_request_buffering off;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;''', 1)
        NGINX.write_text(config); run(['nginx','-t']); run(['systemctl','reload','nginx'])
        for path in ['/dashboard/imports','/api/import-socket/socket.io.js']:
            with urllib.request.urlopen('https://127.0.0.1:3005' + path, context=context, timeout=10) as r:
                if r.status != 200: raise RuntimeError('Dashboard route unavailable')
        if policies() != before: raise RuntimeError('Policy baseline changed during deployment')
        if sha(ROOT / 'src/config/kafkaConfig.js') != kafka_sha: raise RuntimeError('Unrelated Kafka config changed')
        result = {'deployed': True, 'backup': str(backup), 'frontendRoot': str(build_root), 'policiesPreserved': True,
            'websocketProxyEnabled': True, 'auth': 'existing user JWT; private import token never sent to browser',
            'files': {rel: sha(ROOT / rel) for rel in MANIFEST['candidate']}}
        (backup / 'result.json').write_text(json.dumps(result, indent=2)); print(json.dumps(result, indent=2))
    except Exception:
        if modified:
            run(['systemctl','stop','netpro-backend'])
            for rel in MANIFEST['candidate']:
                if (backup / rel).exists(): shutil.copy2(backup / rel, ROOT / rel)
            shutil.copy2(backup / 'bulk-import.env', ENVFILE); shutil.copy2(backup / 'nginx.conf', NGINX)
            run(['systemctl','start','netpro-backend']); run(['nginx','-t']); run(['systemctl','reload','nginx'])
        print('Rollback applied; additive tables, source backup and any unused build retained:', backup)
        raise
if __name__ == '__main__': main()
