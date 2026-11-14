"""Upgrade the labelled rollout to expose actual Kafka catch-up readiness."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

ROOT = Path('/home/netpro/NetPro-Policy-Server')
WORK = Path('/home/netpro/incoming/rafie-integration-20261031')
DROP = Path('/etc/systemd/system/netpro-policy.service.d/rafie-cache.conf')
def run(args): return subprocess.run(args, check=True, capture_output=True, text=True, timeout=90).stdout.strip()
def rows():
    c = sqlite3.connect('file:/home/ubuntu/NetPro-Policy-Server/policy.db?mode=ro', uri=True)
    try: return c.execute('SELECT id,domain,ip_address FROM policies ORDER BY id').fetchall()
    finally: c.close()
def main():
    if os.geteuid(): raise RuntimeError('Expected root')
    record = json.loads((WORK/'deployment.json').read_text()); baseline = rows()
    if len(baseline) != 4: raise RuntimeError('Wait for four-row baseline before upgrading')
    if hashlib.sha256((ROOT/'policyServer.c').read_bytes()).hexdigest() != record['sourceSha256']['policyServer.c']:
        raise RuntimeError('Live source changed')
    tag = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = Path('/root/netpro-rafie-readiness-' + tag); backup.mkdir(mode=0o700)
    shutil.copy2(ROOT/'policyServer.c', backup/'policyServer.c'); shutil.copy2(DROP, backup/'mode.conf')
    old_link = os.readlink(ROOT/'build/policyServer'); (backup/'binary-link.txt').write_text(old_link)
    target = ROOT/('build/policyServer-rafie-' + tag)
    try:
        run(['systemctl', 'stop', 'netpro-policy'])
        shutil.copy2(WORK/'rafie/policy-candidate/policyServer.c', ROOT/'policyServer.c')
        shutil.copy2(WORK/'policyServer-rafie-shared', target); target.chmod(0o755)
        link = ROOT/'build/policyServer'; link.unlink(); link.symlink_to(target.name)
        DROP.write_text('[Service]\nEnvironment=NETPRO_LOOKUP_MODE=shadow\n')
        run(['systemctl', 'daemon-reload']); run(['systemctl', 'start', 'netpro-policy'])
        for _ in range(120):
            status = json.loads(Path('/run/netpro-policy-cache.json').read_text())
            if status.get('policySyncReady') and status.get('mode') == 'shadow' and rows() == baseline: break
            time.sleep(1)
        else: raise RuntimeError('Replay did not finish with baseline preserved')
        record.update({'binary': str(target), 'readinessBackup': str(backup), 'status': status,
                       'binarySha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        record['sourceSha256']['policyServer.c'] = hashlib.sha256((ROOT/'policyServer.c').read_bytes()).hexdigest()
        (WORK/'deployment.json').write_text(json.dumps(record, indent=2)); (backup/'result.json').write_text(json.dumps(record, indent=2))
        print(json.dumps(record))
    except Exception:
        run(['systemctl', 'stop', 'netpro-policy']); shutil.copy2(backup/'policyServer.c', ROOT/'policyServer.c')
        shutil.copy2(backup/'mode.conf', DROP); link = ROOT/'build/policyServer'; link.unlink(); link.symlink_to(old_link)
        run(['systemctl', 'daemon-reload']); run(['systemctl', 'start', 'netpro-policy']); raise
if __name__ == '__main__': main()
