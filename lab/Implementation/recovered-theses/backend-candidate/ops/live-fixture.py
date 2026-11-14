"""Run on Management as root. Only creates/removes labelled rules owned by this test key."""
import datetime
import json
import os
from pathlib import Path
import secrets
import ssl
import sys
import time
import urllib.request

RECEIPT = Path('/home/netpro/recovered-theses-20261030/live-policy-test-receipt.json')
context = ssl.create_default_context(cafile='/home/ubuntu/cert/server.crt')
context.check_hostname = False  # Exact loopback endpoint, pinned lab certificate.
environment = dict(line.split('=', 1) for line in Path('/etc/netpro/bulk-import.env').read_text().splitlines() if '=' in line)
token = environment['NETPRO_BULK_IMPORT_TOKEN']
def api(path, method='GET', body=None):
    req = urllib.request.Request('https://127.0.0.1:3000' + path, method=method,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req, context=context, timeout=10) as response: return json.load(response)
def save(data):
    fd = os.open(str(RECEIPT), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as out: json.dump(data, out, indent=2)
def main():
    if os.geteuid() != 0: raise RuntimeError('Root required to read private import token')
    mode = sys.argv[1]
    if mode == 'create':
        if RECEIPT.exists() and not json.loads(RECEIPT.read_text()).get('cleanupRequested'): raise RuntimeError('Previous fixture receipt still active; inspect or clean it first')
        suffix = secrets.token_hex(6)
        data = {'importKey': 'netpro-live-import-' + suffix, 'rows': [
            {'domain': 'bulk-ip-' + suffix + '.example', 'ip_add': '192.0.2.241', 'name': 'NetPro bulk integration owned fixture', 'category': 'Other'},
            {'domain': 'bulk-domain-' + suffix + '.example', 'ip_add': None, 'name': 'NetPro bulk domain-only owned fixture', 'category': 'Other'}],
            'cleanupRequested': False}
        data['backendBaseline'] = api('/ps/blocked-list')
        save(data)  # Persist ownership before an uncertain HTTP result.
        created = api('/ps/import-policy-batch', 'POST', {'importKey': data['importKey'], 'rows': data['rows']})
        data['created'] = created; save(data)
        replay = api('/ps/import-policy-batch', 'POST', {'importKey': data['importKey'], 'rows': data['rows']})
        if [r['id'] for r in replay['rows']] != [r['id'] for r in created['rows']]: raise RuntimeError('Replay UUID mismatch')
        for _ in range(30):
            status = api('/ps/import-policy-batch/' + data['importKey'])
            if status['stored'] == 2 and status['published'] == 2: break
            time.sleep(1)
        else: raise RuntimeError('Publication acknowledgement timeout; receipt retained for cleanup')
        data['status'] = status; save(data)
        print(json.dumps(data))
    elif mode == 'cleanup':
        if not RECEIPT.exists(): print(json.dumps({'cleanupRequested': False, 'reason': 'No owned receipt'})); return
        data = json.loads(RECEIPT.read_text())
        if not data['importKey'].startswith('netpro-live-import-'): raise RuntimeError('Refusing an unowned source key')
        result = api('/ps/import-policy-batch/' + data['importKey'], 'DELETE')
        after = api('/ps/blocked-list')
        def canonical(value):
            if isinstance(value, list): value = sorted(value, key=lambda row: row['id'])
            return json.dumps(value, sort_keys=True)
        if canonical(after) != canonical(data.get('backendBaseline')): raise RuntimeError('Backend baseline changed; owned deletion requested, inspect before further writes')
        data['cleanupRequested'] = True; data['cleanupResult'] = result; save(data)
        print(json.dumps({'importKey': data['importKey'], 'backendBaselinePreserved': True, **result}))
    else: raise RuntimeError('Expected create or cleanup')
if __name__ == '__main__': main()
