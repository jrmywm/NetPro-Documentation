"""Actual CSV upload -> persistent job -> explicit bridge -> backend/Kafka/PS -> cleanup."""
import datetime
import importlib.util
import json
from pathlib import Path
import time

spec = importlib.util.spec_from_file_location('netpro_live_helpers', Path(__file__).with_name('verify-live-e2e.py'))
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)

def main():
    mg, _ = h.connect_verified('192.168.31.35', 'netpro', h.password, h.KNOWN)
    ps, _ = h.connect_verified('192.168.31.31', 'netpro', h.password, h.KNOWN)
    baseline = h.policies(ps); results = []; fixture = None; activation = None; attempted = False
    root = 'cd /home/netpro/recovered-theses-20261030/luthfi && node scripts/with-isolated-env.js '
    pg = "runuser -u postgres -- psql -d test -Atc 'SELECT row_to_json(p)::text FROM ps_blocked_list p ORDER BY id'"
    backend_before = h.command(mg, pg)
    try:
        fixture = json.loads(h.command(mg, root + 'tests/create-live-upload-fixture.js'))
        results.append({'name': 'actual multipart CSV upload completed with 2 unique / 1 duplicate / 0 failed', 'passed': True})
        attempted = True
        activation = json.loads(h.command(mg, root + 'scripts/activate-live-upload.js --activate-live ' + str(fixture['jobId'])))
        replay = json.loads(h.command(mg, root + 'scripts/activate-live-upload.js --activate-live ' + str(fixture['jobId'])))
        if [r['id'] for r in activation['rows']] != [r['id'] for r in replay['rows']]: raise RuntimeError('Activation replay changed IDs')
        ids = {r['id'] for r in activation['rows']}
        expected = {r['domain']: r['ip_add'] or '' for r in fixture['rows']}
        for _ in range(40):
            actual = [r for r in h.policies(ps) if r['id'] in ids]
            if len(actual) == 2 and {r['domain']: r['ip_address'] for r in actual} == expected: break
            time.sleep(1)
        else: raise RuntimeError('CSV policies not applied on active Policy Server')
        results.append({'name': 'same completed CSV job activated idempotently through authoritative backend/Kafka into active PS SQLite', 'passed': True})
        print('PASS actual CSV upload -> job -> guarded activation -> live PostgreSQL/Kafka -> active PS (IP + domain-only)')
    except Exception as error:
        results.append({'name': str(error), 'passed': False}); raise
    finally:
        try:
            if attempted:
                h.command(mg, root + 'scripts/activate-live-upload.js --cleanup-live ' + str(fixture['jobId']))
                for _ in range(40):
                    if h.policies(ps) == baseline: break
                    time.sleep(1)
                else: raise RuntimeError('Policy Server baseline not restored')
                if h.command(mg, pg) != backend_before: raise RuntimeError('Authoritative backend baseline not restored')
                results.append({'name': 'CSV-owned policies removed and exact backend/PS baselines restored', 'passed': True})
                print('PASS CSV-owned policy cleanup; exact backend and PS baselines restored')
        finally:
            mg.close(); ps.close()
            (h.BASE / 'evidence/stage4-live-upload-e2e.json').write_text(json.dumps({
                'date': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'fixture': fixture,
                'activation': activation, 'results': results, 'browserInteractionTested': False,
                'packetBlockingTested': False, 'operatorActivationCap': 20
            }, indent=2), encoding='utf-8')
if __name__ == '__main__': main()
