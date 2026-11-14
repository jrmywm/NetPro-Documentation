"""Windows orchestrator: actual guarded backend -> Kafka -> active PS SQLite, then cleanup."""
import datetime
import getpass
import json
import os
from pathlib import Path
import re
import shlex
import sys
import time

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified, run_remote_command
KNOWN = Path(r'C:\Users\jim\.ssh\known_hosts')
password = os.environ.get('NETPRO_SSH_PASSWORD') or getpass.getpass('NetPro lab SSH password: ')
def command(client, text):
    rc, out, err = run_remote_command(client, text, sudo_password=password, timeout=45)
    if rc: raise RuntimeError('Remote command failed: ' + err[-600:])
    return out
def policies(client):
    code = "import sqlite3,json; c=sqlite3.connect('file:/home/ubuntu/NetPro-Policy-Server/policy.db?mode=ro',uri=True); c.row_factory=sqlite3.Row; print(json.dumps([dict(r) for r in c.execute('SELECT id,domain,ip_address FROM policies ORDER BY id')]))"
    out = command(client, 'python3 -c ' + shlex.quote(code))
    return json.loads(out or '[]')
def main():
    management, mh = connect_verified('192.168.31.35', 'netpro', password, KNOWN)
    ps, ph = connect_verified('192.168.31.31', 'netpro', password, KNOWN)
    results = []; receipt = None; attempted = False; baseline = policies(ps)
    program = 'python3 /home/netpro/recovered-theses-20261030/backend-candidate/ops/live-fixture.py '
    try:
        attempted = True
        receipt = json.loads(command(management, program + 'create'))
        ids = {r['id'] for r in receipt['created']['rows']}
        if len(ids) != 2 or not all(re.fullmatch(r'[0-9a-f-]{36}', i) for i in ids): raise RuntimeError('Unexpected fixture IDs')
        expected = {r['domain']: r['ip_add'] or '' for r in receipt['rows']}
        for _ in range(40):
            actual = [r for r in policies(ps) if r['id'] in ids]
            if len(actual) == 2 and {r['domain']: r['ip_address'] for r in actual} == expected: break
            time.sleep(1)
        else: raise RuntimeError('Kafka-published rules not applied to active PS SQLite')
        results.append({'name': 'guarded authoritative API stores/replays two stable UUIDs and awaits Kafka publication', 'passed': True})
        results.append({'name': 'active Policy Server applied explicit-IP and domain-only rules from the live topic', 'passed': True})
        if receipt['status']['applicationVerified'] is not False: raise RuntimeError('API incorrectly claims application acknowledgement')
        print('PASS authoritative PostgreSQL/API -> live Kafka -> active Policy Server SQLite (IP + domain-only)')
    except Exception as error:
        results.append({'name': str(error), 'passed': False})
        raise
    finally:
        try:
            if attempted:
                cleanup = json.loads(command(management, program + 'cleanup'))
                if not cleanup.get('backendBaselinePreserved'): raise RuntimeError('Backend baseline was not verified')
                for _ in range(40):
                    current = policies(ps)
                    if current == baseline: break
                    time.sleep(1)
                else: raise RuntimeError('PS baseline not restored after owned-rule cleanup; inspect pending deletion events')
                results.append({'name': 'owned fixture deletion applied and exact previous PS baseline restored', 'passed': True})
                print('PASS owned-rule cleanup and exact PS baseline restoration')
        finally:
            management.close(); ps.close()
            (BASE / 'evidence').mkdir(exist_ok=True)
            (BASE / 'evidence/stage4-live-policy-e2e.json').write_text(json.dumps({
                'date': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'management': mh, 'policyServer': ph,
                'baseline': baseline, 'receipt': receipt, 'results': results,
                'packetBlockingTested': False, 'dashboardUploadTested': False
            }, indent=2), encoding='utf-8')
if __name__ == '__main__': main()
