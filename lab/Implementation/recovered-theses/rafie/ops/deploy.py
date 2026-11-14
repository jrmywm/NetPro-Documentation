"""Guarded shadow rollout of validated lookup; retains previous binary and database."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import time

ROOT = Path('/home/netpro/NetPro-Policy-Server')
WORK = Path('/home/netpro/incoming/rafie-integration-20261031')
DB = '/home/ubuntu/NetPro-Policy-Server/policy.db'
DROP = Path('/etc/systemd/system/netpro-policy.service.d/rafie-cache.conf')
FILES = ['policyServer.c', 'Makefile', 'rafie_lookup.h', 'rafie_lookup.c']

def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=90).stdout.strip()
def rows():
    with sqlite3.connect('file:' + DB + '?mode=ro', uri=True) as c:
        return c.execute('SELECT id,domain,ip_address FROM policies ORDER BY id').fetchall()
def main():
    if os.geteuid() or socket.gethostname() != 'policy-server-vm': raise RuntimeError('Expected root on Policy VM')
    if DROP.exists(): raise RuntimeError('Existing rollout found; inspect instead of overwriting')
    if hashlib.sha256((ROOT/'policyServer.c').read_bytes()).hexdigest() != 'bf51e1c98b1d2c3a323270fa87e0bebc1759f6d5b5032c316c6c2e302438d819':
        raise RuntimeError('Live source differs from verified preflight')
    if os.readlink(ROOT/'build/policyServer') != 'policyServer-shared': raise RuntimeError('Live binary selection changed')
    for name in ['module-test.log', 'module-asan.log', 'event-test.log', 'event-asan.log']:
        text = (WORK/name).read_text()
        if 'PASS' not in text or any(x in text for x in ['ERROR: AddressSanitizer', 'runtime error:', 'Assertion']):
            raise RuntimeError('Test evidence did not pass: ' + name)
    baseline = rows()
    if len(baseline) != 4: raise RuntimeError('Expected restored four-row baseline before rollout')
    tag = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = Path('/root/netpro-rafie-' + tag); backup.mkdir(mode=0o700)
    (backup/'baseline.json').write_text(json.dumps(baseline))
    for name in FILES:
        if (ROOT/name).exists(): shutil.copy2(ROOT/name, backup/name)
    (backup/'binary-link.txt').write_text(os.readlink(ROOT/'build/policyServer'))
    shutil.copy2(ROOT/'build/policyServer-shared', backup/'previous-binary')
    with sqlite3.connect('file:' + DB + '?mode=ro', uri=True) as old, sqlite3.connect(backup/'policy.db') as snapshot:
        old.backup(snapshot)
    target = ROOT/('build/policyServer-rafie-' + tag)
    try:
        run(['systemctl', 'stop', 'netpro-policy'])
        for name in FILES:
            source = WORK/'rafie'/('policy-candidate/' + name if name in ['policyServer.c', 'Makefile'] else name)
            shutil.copy2(source, ROOT/name)
            owner = (backup/'policyServer.c').stat(); os.chown(ROOT/name, owner.st_uid, owner.st_gid)
        shutil.copy2(WORK/'policyServer-rafie-shared', target); target.chmod(0o755)
        link = ROOT/'build/policyServer'; link.unlink(); link.symlink_to(target.name)
        DROP.parent.mkdir(exist_ok=True)
        DROP.write_text('[Service]\nEnvironment=NETPRO_LOOKUP_MODE=shadow\n')
        run(['systemctl', 'daemon-reload']); run(['systemctl', 'start', 'netpro-policy'])
        for _ in range(120):
            if run(['systemctl', 'is-active', 'netpro-policy']) == 'active' and rows() == baseline:
                status = Path('/run/netpro-policy-cache.json')
                if status.exists():
                    details = json.loads(status.read_text())
                    if details.get('mode') == 'shadow' and details.get('policySyncReady'): break
            time.sleep(1)
        else: raise RuntimeError('Service readiness/baseline did not return')
        result = {'deployed': True, 'mode': 'shadow', 'backup': str(backup), 'binary': str(target),
                  'baselinePreserved': True, 'binarySha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                  'sourceSha256': {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in FILES}}
        (backup/'deployment.json').write_text(json.dumps(result, indent=2))
        (WORK/'deployment.json').write_text(json.dumps(result, indent=2)); print(json.dumps(result))
    except Exception:
        run(['systemctl', 'stop', 'netpro-policy'])
        for name in FILES:
            if (backup/name).exists(): shutil.copy2(backup/name, ROOT/name)
        link = ROOT/'build/policyServer'; link.unlink(); link.symlink_to((backup/'binary-link.txt').read_text())
        DROP.unlink(missing_ok=True); run(['systemctl', 'daemon-reload']); run(['systemctl', 'start', 'netpro-policy'])
        # Never overwrite live policy data from a backup during code rollback.
        raise

if __name__ == '__main__': main()
