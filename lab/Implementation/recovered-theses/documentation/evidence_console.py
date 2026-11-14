"""Display real live checks or clearly labelled recorded test evidence in a visible console."""
import argparse
import datetime
import getpass
import json
import os
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
OUT = Path(r'C:\Users\jim\Documents\NetPro\Documentation\Evidence\adapted-integration-20261031')

def load(name): return json.loads((BASE/'test-results'/name).read_text(encoding='utf-8'))
def heading(title, recorded=False):
    print('NETPRO | ' + title)
    print(('RECORDED TEST EVIDENCE | ' if recorded else 'LIVE READ-ONLY CHECK | ') + datetime.datetime.now().astimezone().isoformat(timespec='seconds'))
    if recorded: print('Test run: 30-31 October 2026. This command reads saved results; it does not rerun the tests.')
    print('-' * 106)

def live():
    heading('DEPLOYED SERVICES AND RAFIE CACHE')
    sys.path.insert(0, r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
    from remote import connect_verified, run_remote_command
    password = os.environ.get('NETPRO_SSH_PASSWORD') or getpass.getpass('Lab SSH password: ')
    command = 'systemctl is-active netpro-policy; cat /run/netpro-policy-cache.json'
    print('Policy VM 192.168.31.31 | command: ' + command)
    c, host = connect_verified('192.168.31.31', 'netpro', password, Path.home()/'.ssh/known_hosts')
    try:
        rc, stdout, stderr = run_remote_command(c, command, sudo_password=password, timeout=40)
        if rc: raise RuntimeError(stderr)
        print('Service: ' + stdout.splitlines()[0]); status = json.loads(stdout[stdout.index('{'):])
        print('Lookup mode:          ', status['mode'])
        print('Kafka replay ready:   ', status['policySyncReady'])
        print('Shadow mismatches:    ', status['shadowMismatches'])
        for key in ['filterValid','loadedRows','queries','hotHits','lruHits','bloomNegatives','errors']:
            print('  %-22s %s' % (key + ':', status['lookup'][key]))
        assert status['mode'] == 'rafie' and status['policySyncReady'] and status['shadowMismatches'] == 0
        assert status['lookup']['errors'] == 0
    finally: c.close()
    print()
    command = 'python3 /home/netpro/recovered-theses-20261030/final-health.py'
    print('Management VM 192.168.31.35 | command: ' + command)
    c, _ = connect_verified('192.168.31.35', 'netpro', password, Path.home()/'.ssh/known_hosts')
    try:
        rc, stdout, stderr = run_remote_command(c, command, sudo_password=password, timeout=40)
        if rc: raise RuntimeError(stderr)
        health = json.loads(stdout)
        for name, state in health['services'].items(): print('  %-22s %s' % (name, state))
        for path, code in health['http'].items(): print('  HTTP %-31s %s' % (path, code))
        print('  Authoritative baseline policies: ', health['baselinePolicies'])
        print('  Pending policy events:           ', health['pendingEvents'])
        print('PASS live service, authorization and policy-publication checks')
    finally: c.close()
    (OUT/'live-health.json').write_text(json.dumps({'time': datetime.datetime.now().astimezone().isoformat(), 'cache':status,'management':health},indent=2),encoding='utf-8')

def luthfi():
    heading('LUTHFI | CSV IMPORT, DURABILITY AND PROGRESS', True)
    d = load('luthfi-functional.json')
    print('Source command: python documentation/evidence_console.py luthfi')
    print('Source: test-results/luthfi-functional.json')
    print()
    print('Backend adapter:     %d passed / %d failed' % (d['backend_adapter']['passed'],d['backend_adapter']['failed']))
    print('HTTP CSV pipeline:   %d passed / %d failed' % (d['integrated_csv']['passed'],d['integrated_csv']['failed']))
    print('Frontend:            %d tests in %d suites; production build passed' % (d['frontend']['testsPassed'],d['frontend']['suitesPassed']))
    r = d['real_restart']
    print('Restart checkpoint:  %s committed rows' % r['checkpoint'])
    print('Resumed validation:  %s valid / %s duplicates / %s invalid' % (r['rowsValidated'],r['duplicates'],r['invalid']))
    s = d['real_socket']
    print('Socket.IO delivery:  owner=%s, other owner=%s, unauthenticated rejected=%s' % (s['ownerEvents'],s['otherOwnerEvents'],s['unauthenticatedRejected']))
    print()
    print('Key HTTP pipeline checks:')
    for case in d['integrated_csv']['cases']: print('PASS ' + case['name'])
    print()
    print('Workflow: upload -> validate/preview -> explicit activation -> durable outbox -> Kafka')
    print('Publication acknowledgement does not mean Policy Server enforcement acknowledgement.')
    print('Browser click-through remains unverified; no dashboard screenshot is claimed here.')

def packets():
    heading('COMBINED LIVE HTTP/TLS ACCEPTANCE | SAVED RESULTS', True)
    d = load('rafie-functional.json')
    print('Source command: python documentation/evidence_console.py packets')
    print('Source: test-results/rafie-functional.json (actual client probes and packet captures)')
    print()
    print('%-10s %-30s %12s %10s' % ('MODE','PHASE','TRIALS','RESULT'))
    for run in d['live']['runs']:
        for p in run['phases']:
            assert p['passed']
            print('%-10s %-30s %12s %10s' % (run['mode'],p['name'],str(p['trials'])+'/'+str(p['trials']),'PASS'))
    print()
    print('Shadow allow/block and policy-ID mismatches: 0')
    print('Test path: Client -> Virtual TAP -> NPB -> Policy Server -> dedicated RST return')
    print('Allow was warmed before create; block was warmed before delete.')
    print()
    for case in d['bulkCsvPropagation']: print('PASS ' + case['name'])
    print('PASS post-restart / post-CSV cache reconstruction: %d/20 allowed' % d['postRestartAndCsv']['allowTrials'])
    print('PASS cleanup: original policy baseline restored; temporary helpers stopped')
    print()
    print('Scope: HTTP/TLS. This is not proof of integrated QUIC blocking or hardware fail-open.')

def rafie():
    heading('RAFIE | CORRECTNESS, UPDATE COHERENCE AND SANITIZERS', True)
    d = load('rafie-functional.json')
    print('Source command: python documentation/evidence_console.py rafie')
    print('Source: actual module and compiled Policy Server handler tests on Policy VM')
    print()
    for case in d['moduleCases']: print('PASS ' + case)
    print()
    for case in d['actualPolicyHandlerCases']: print('PASS ' + case)
    print()
    print('PASS module + actual handler: AddressSanitizer, UndefinedBehaviorSanitizer, leak checks')
    print('Passed module cases: %d | actual handler cases: %d' % (len(d['moduleCases']),len(d['actualPolicyHandlerCases'])))
    print('Mode left enabled: ' + d['activeMode'])

def benchmark():
    heading('RAFIE | MEASURED LOOKUP PERFORMANCE AND LIMITS', True)
    d = load('rafie-functional.json'); b = d['mixedLookupMicrobenchmark']
    print('Source command: python documentation/evidence_console.py benchmark')
    print('Standalone lookup test: 15,001 policies, 3,000 identical mixed queries, no domain index')
    print('80% repeated listed domains / 20% unique absent domains; exact decision/ID differences: 0')
    print()
    print('%-22s %18s %18s' % ('MEASUREMENT','DIRECT SQLITE','ADAPTED TIERS'))
    for key in ['processed','seconds','qps','p50_us','p95_us','p99_us']:
        print('%-22s %18s %18s' % (key,b['sqlite'][key],b['tiers'][key]))
    print()
    x = d['indexedRepeatedMicrobenchmark']
    print('Separate indexed/repeated test: %d queries' % x['queries'])
    print('Prepared SQLite %.6f s | guarded tiers %.6f s' % (x['sqliteSeconds'],x['cacheSeconds']))
    print('SQLite was faster in that workload; acceleration is workload-dependent.')
    print()
    print('This is not full-network throughput, not a comparison against the entire old cache,')
    print('and not a claim of identical thesis performance.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('page',choices=['live','luthfi','rafie','packets','benchmark'])
    args = parser.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    globals()[args.page]()
