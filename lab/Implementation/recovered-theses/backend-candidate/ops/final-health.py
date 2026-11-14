"""Read-only deployed CSV acceptance checks; never prints private credentials."""
import json
from pathlib import Path
import re
import ssl
import subprocess
import urllib.error
import urllib.request

def run(args):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=30).stdout.strip()

def main():
    services = {name: run(['systemctl', 'is-active', name]) for name in
                ['netpro-backend', 'postgresql', 'netpro-kafka', 'nginx']}
    context = ssl.create_default_context(cafile='/home/ubuntu/cert/server.crt')
    context.check_hostname = False
    def status(path):
        try:
            with urllib.request.urlopen('https://127.0.0.1:3005' + path, context=context, timeout=10) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
    responses = {path: status(path) for path in
                 ['/dashboard/imports', '/api/npb/npbs', '/api/ps/csv-imports']}
    assert list(responses.values()) == [200, 200, 401], responses
    nginx = Path('/etc/nginx/conf.d/netpro-frontend.conf').read_text()
    root = Path(re.search(r'root\s+([^;]+);', nginx)[1])
    env = Path('/etc/netpro/bulk-import.env').read_text()
    token = re.search(r'^NETPRO_BULK_IMPORT_TOKEN=(.+)$', env, re.M)[1].strip().strip('"\'')
    assert token and not any(token.encode() in p.read_bytes() for p in root.rglob('*.js'))
    sql = "SELECT json_build_object('baselinePolicies', (SELECT count(*) FROM ps_blocked_list), 'pendingEvents', (SELECT count(*) FROM netpro_bulk_policy_events WHERE published_at IS NULL))"
    counts = json.loads(run(['runuser', '-u', 'postgres', '--', 'psql', '-d', 'test', '-Atc', sql]))
    assert counts == {'baselinePolicies': 1, 'pendingEvents': 0}, counts
    result = {'passed': True, 'services': services, 'http': responses, 'frontendRoot': str(root),
              'serviceTokenAbsentFromFrontend': True, **counts}
    target = Path('/home/netpro/recovered-theses-20261030/luthfi/evidence/final-health.json')
    target.write_text(json.dumps(result, indent=2))
    print(json.dumps(result))

if __name__ == '__main__':
    main()
