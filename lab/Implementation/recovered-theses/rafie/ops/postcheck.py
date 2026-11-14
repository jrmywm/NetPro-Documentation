"""Verify lazy reconstruction after restart and the large CSV add/remove regression."""
import datetime
import getpass
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0, r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from active_baseline import ActiveBaseline, POLICY_HOST

def main():
    password = os.environ.get('NETPRO_SSH_PASSWORD') or getpass.getpass('NetPro lab SSH password: ')
    out = Path(__file__).resolve().parents[2]/'evidence'/('rafie-postimport-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True); w = ActiveBaseline(password, out, Path.home()/'.ssh/known_hosts')
    result = {'passed': False}
    try:
        w.connect_all(); w.baseline(); w.start_gateway_server()
        assert w.run_probe('allow')
        time.sleep(3)
        _, text, _ = w.command(POLICY_HOST, 'cache-status', 'cat /run/netpro-policy-cache.json', sudo=True)
        status = json.loads(text)
        assert status['mode'] == 'rafie' and status['policySyncReady'] and status['shadowMismatches'] == 0
        assert status['lookup']['queries'] >= 20 and status['lookup']['loadedRows'] == 4
        assert status['lookup']['filterValid'] and status['lookup']['errors'] == 0
        result = {'passed': True, 'allowTrials': 20, 'status': status}
    finally:
        w.cleanup(); result['cleanup'] = w.document['cleanup'][-1]
        (out/'RESULTS.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result)); print('Evidence:', out)
if __name__ == '__main__': main()
