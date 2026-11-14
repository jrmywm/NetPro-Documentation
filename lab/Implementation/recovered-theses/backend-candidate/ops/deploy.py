"""Guarded live deployment. Root only; makes backups and rolls code back on failure."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import ssl
import subprocess
import time
import urllib.request

ROOT = Path('/home/netpro/NetPro-Backend')
CANDIDATE = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((CANDIDATE / 'ops/deployment-manifest.json').read_text())
DROPIN = Path('/etc/systemd/system/netpro-backend.service.d/bulk-import.conf')
ENVFILE = Path('/etc/netpro/bulk-import.env')
FILES = ['index.js', 'src/app.js', 'src/integration/bulk-policy.js', 'src/integration/bootstrap.js', 'src/integration/policy-contract.js']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def command(args, **kwargs): return subprocess.run(args, check=True, capture_output=True, text=True, timeout=90, **kwargs)

def main():
    if os.geteuid() != 0 or socket.gethostname() != 'backend-vm': raise RuntimeError('Expected root on backend-vm')
    if DROPIN.exists() or ENVFILE.exists(): raise RuntimeError('Import deployment already exists; inspect before redeploying')
    for rel, expected in MANIFEST['original'].items():
        if sha(ROOT / rel) != expected: raise RuntimeError('Live source changed: ' + rel)
    for rel, expected in MANIFEST['candidate'].items():
        if sha(CANDIDATE / rel) != expected: raise RuntimeError('Candidate artifact changed: ' + rel)
    for rel in FILES[2:]:
        if (ROOT / rel).exists(): raise RuntimeError('Refusing to overwrite existing integration file: ' + rel)
    backup = Path('/root/netpro-bulk-import-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700)
    kafka_hash = sha(ROOT / 'src/config/kafkaConfig.js')
    for rel in ['index.js', 'src/app.js', 'src/config/kafkaConfig.js']:
        dest = backup / rel; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(ROOT / rel, dest)
    with (backup / 'postgres-test.dump').open('wb') as output:
        subprocess.run(['runuser', '-u', 'postgres', '--', 'pg_dump', '-Fc', '-d', 'test'], stdout=output, stderr=subprocess.PIPE, check=True, timeout=120)
    policy_before = command(['runuser', '-u', 'postgres', '--', 'psql', '-d', 'test', '-Atc', 'SELECT row_to_json(p)::text FROM ps_blocked_list p ORDER BY id']).stdout
    (backup / 'policies-before.jsonl').write_text(policy_before)
    modified = False
    try:
        env = dict(os.environ, NODE_PATH=str(ROOT / 'node_modules'), NETPRO_ALLOW_LIVE_SCHEMA='1')
        command(['node', str(CANDIDATE / 'ops/migrate-live.js'), '--apply-live-additive-schema'], env=env)
        modified = True
        for rel in FILES:
            target = ROOT / rel; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(CANDIDATE / rel, target); os.chmod(target, 0o644)
            os.chown(target, ROOT.stat().st_uid, ROOT.stat().st_gid)
        ENVFILE.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        token = secrets.token_hex(32)
        fd = os.open(str(ENVFILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as output: output.write('NETPRO_BULK_IMPORT_ENABLED=1\nNETPRO_BULK_IMPORT_TOKEN=' + token + '\n')
        DROPIN.parent.mkdir(parents=True, exist_ok=True)
        DROPIN.write_text('[Service]\nEnvironmentFile=/etc/netpro/bulk-import.env\n')
        command(['systemctl', 'daemon-reload']); command(['systemctl', 'restart', 'netpro-backend'])
        context = ssl.create_default_context(cafile='/home/ubuntu/cert/server.crt')
        context.check_hostname = False  # Exact loopback endpoint, pinned lab certificate.
        for _ in range(60):
            try:
                req = urllib.request.Request('https://127.0.0.1:3000/ps/import-policy-batch/deployment-preflight', headers={'Authorization': 'Bearer ' + token})
                with urllib.request.urlopen(req, context=context, timeout=3) as response: result = json.load(response)
                if result.get('stored') == 0: break
            except Exception: time.sleep(1)
        else: raise RuntimeError('Guarded adapter readiness timed out')
        after = command(['runuser', '-u', 'postgres', '--', 'psql', '-d', 'test', '-Atc', 'SELECT row_to_json(p)::text FROM ps_blocked_list p ORDER BY id']).stdout
        if after != policy_before: raise RuntimeError('Policy baseline changed during deployment')
        if sha(ROOT / 'src/config/kafkaConfig.js') != kafka_hash: raise RuntimeError('Unrelated Kafka configuration changed')
        result = {'deployed': True, 'backup': str(backup), 'policyRowsPreserved': True, 'kafkaConfigPreserved': True,
            'privateTokenPrinted': False, 'liveRulesCreated': 0, 'files': {rel: sha(ROOT / rel) for rel in FILES}}
        (backup / 'deployment-result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
    except Exception:
        if modified:
            command(['systemctl', 'stop', 'netpro-backend'])
            for rel in ['index.js', 'src/app.js']: shutil.copy2(backup / rel, ROOT / rel)
            if DROPIN.exists(): DROPIN.unlink()  # Only the new file created by this deployment.
            command(['systemctl', 'daemon-reload']); command(['systemctl', 'start', 'netpro-backend'])
            print('Code rolled back. Additive tables and backup retained:', backup)
        raise

if __name__ == '__main__': main()
