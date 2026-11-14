"""Actual TAP/NPB/PS/reset regressions with cached allow before create and deny before delete."""
import datetime
import getpass
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from active_baseline import ActiveBaseline, POLICY_HOST
from remote import connect_verified, run_remote_command

BASE = Path(__file__).resolve().parents[2]
def main():
    password = os.environ.get('NETPRO_SSH_PASSWORD') or getpass.getpass('NetPro lab SSH password: ')
    target = BASE/'evidence'/('rafie-live-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    target.mkdir(parents=True)
    c, _ = connect_verified(POLICY_HOST, 'netpro', password, Path.home()/'.ssh/known_hosts')
    report = {'runs': [], 'passed': False}; success = False
    def command(text):
        rc, out, err = run_remote_command(c, text, sudo_password=password, timeout=180)
        if rc: raise RuntimeError('Guarded policy operation failed: ' + err[-600:] + out[-600:])
        return out
    def status():
        return json.loads(command('cat /run/netpro-policy-cache.json'))
    def mode(value):
        return json.loads(command('python3 /home/netpro/incoming/rafie-integration-20261031/select-mode.py ' + value))
    try:
        for value in ['shadow', 'rafie']:
            mode(value); w = ActiveBaseline(password, target/value, Path.home()/'.ssh/known_hosts')
            original = w.run_id; phases = []; packet_success = False
            try:
                w.connect_all(); w.baseline(); w.start_gateway_server(); w.start_return_helper()
                def probe(label, expected):
                    w.run_id = original + '-' + label
                    ok = w.run_probe(expected)
                    phases.append({'name': label, 'passed': ok, 'trials': 20})
                    print(('PASS ' if ok else 'FAIL ') + value + '/' + label, flush=True)
                    if not ok: raise RuntimeError('Live packet phase failed')
                probe('allow-before-add', 'allow'); w.create_policy(); probe('deny-after-add', 'deny')
                w.configure_split_profile(); probe('deny-split-clienthello', 'deny')
                w.delete_policy_exactly(); probe('allow-after-delete', 'allow')
                packet_success = True
            finally:
                w.cleanup()
            assert packet_success and not any(x.get('status') == 'error' for x in w.document['cleanup'])
            time.sleep(3); detail = status()
            assert detail['mode'] == value and detail['shadowMismatches'] == 0
            assert detail['lookup']['queries'] >= 40 and detail['lookup']['errors'] == 0
            report['runs'].append({'mode': value, 'phases': phases, 'status': detail, 'cleanup': w.document['cleanup'][-1]})
        # Same binary/mode restart must keep policy data and rebuild empty in-memory state.
        restarted = mode('rafie'); assert restarted['baselinePreserved']
        report['restart'] = restarted
        report['passed'] = success = True
    except Exception as e:
        report['failure'] = {'type': type(e).__name__, 'message': str(e)}
        raise
    finally:
        if not success:
            try: report['failureMode'] = mode('legacy')
            except Exception as e: report['rollbackError'] = str(e)
        c.close(); (target/'RESULTS.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('Evidence:', target, flush=True)
    if not success: raise RuntimeError('Rafie live acceptance did not pass')

if __name__ == '__main__': main()
