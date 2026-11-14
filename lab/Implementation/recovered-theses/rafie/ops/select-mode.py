"""Select guarded lookup mode and confirm service/baseline readiness; no policy writes."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

def main():
    mode = sys.argv[1]
    if os.geteuid() or mode not in ['legacy', 'shadow', 'rafie']: raise RuntimeError('Expected root and known mode')
    record = json.loads(Path('/home/netpro/incoming/rafie-integration-20261031/deployment.json').read_text())
    binary = Path('/home/netpro/NetPro-Policy-Server/build/policyServer').resolve()
    if str(binary) != record['binary']: raise RuntimeError('Unexpected live binary selection')
    drop = Path('/etc/systemd/system/netpro-policy.service.d/rafie-cache.conf')
    previous = drop.read_text()
    def rows():
        with sqlite3.connect('file:/home/ubuntu/NetPro-Policy-Server/policy.db?mode=ro', uri=True) as c:
            return c.execute('SELECT id,domain,ip_address FROM policies ORDER BY id').fetchall()
    baseline = rows()
    try:
        drop.write_text('[Service]\nEnvironment=NETPRO_LOOKUP_MODE=' + mode + '\n')
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'stop', 'netpro-policy'], check=True, timeout=90)
        Path('/run/netpro-policy-cache.json').unlink(missing_ok=True)
        subprocess.run(['systemctl', 'start', 'netpro-policy'], check=True, timeout=90)
        for _ in range(120):
            p = Path('/run/netpro-policy-cache.json')
            if p.exists():
                status = json.loads(p.read_text())
                if status.get('mode') == mode and status.get('policySyncReady') and rows() == baseline:
                    print(json.dumps({'mode': mode, 'baselinePreserved': True, 'status': status})); return
            time.sleep(1)
        raise RuntimeError('Readiness or baseline did not return')
    except Exception:
        drop.write_text(previous); subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'restart', 'netpro-policy'], check=True, timeout=90); raise

if __name__ == '__main__': main()
