"""Build a compact acceptance record from retained actual test artifacts."""
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parents[1]
RAW = BASE/'evidence/rafie-20261031'
def main():
    module = (RAW/'module-test.log').read_text()
    event = (RAW/'event-test.log').read_text()
    for name in ['module-asan.log', 'event-asan.log']:
        text = (RAW/name).read_text()
        assert 'PASS' in text and not any(x in text for x in ['ERROR: AddressSanitizer', 'runtime error:', 'Assertion'])
    live_path = sorted((BASE/'evidence').glob('rafie-live-*/RESULTS.json'))[-1]
    live = json.loads(live_path.read_text()); assert live['passed']
    post_path = sorted((BASE/'evidence').glob('rafie-postimport-*/RESULTS.json'))[-1]
    post = json.loads(post_path.read_text()); assert post['passed']
    regression = json.loads((RAW/'csv-regression.json').read_text())
    assert len(regression['results']) == 2 and all(x['passed'] for x in regression['results'])
    bench = json.loads((RAW/'benchmark.jsonl').read_text().splitlines()[0]); assert bench['mismatches'] == 0
    indexed = re.search(r'queries=(\d+) sqlite_s=([\d.]+) cache_s=([\d.]+)', module)
    result = {'date': '2026-10-31', 'scope': 'Rafie adaptation in active HTTP/TLS Policy Server profile',
        'moduleCases': [x[5:] for x in module.splitlines() if x.startswith('PASS ')],
        'actualPolicyHandlerCases': [x[5:] for x in event.splitlines() if x.startswith('PASS ')],
        'moduleAndHandlerSanitizersPassed': True,
        'liveEvidence': str(live_path.relative_to(BASE)), 'live': live,
        'postRestartAndCsvEvidence': str(post_path.relative_to(BASE)), 'postRestartAndCsv': post,
        'bulkCsvPropagation': regression['results'], 'mixedLookupMicrobenchmark': bench,
        'indexedRepeatedMicrobenchmark': {'queries': int(indexed[1]), 'sqliteSeconds': float(indexed[2]), 'cacheSeconds': float(indexed[3])},
        'deployment': json.loads((RAW/'deployment.json').read_text()),
        'activeMode': post['status']['mode'], 'passed': True,
        'limitations': ['Adaptation, not identical original recovered code or thesis hardware/performance',
            'Mixed microbenchmark compares direct SQLite lookups, not full legacy cache or whole system',
            'Indexed repeated SQLite was faster than guarded tiers; speedup is workload-dependent',
            'Updates invalidate all tiers; lazy full rebuild cost under sustained bulk changes remains to benchmark',
            'Service startup replays Kafka history; readiness must be checked before demo/measurement',
            'Experimental original QUIC candidate remains separate; no new QUIC enforcement claim']}
    target = BASE/'test-results/rafie-functional.json'
    target.write_text(json.dumps(result, indent=2), encoding='utf-8', newline='\n')
    print(json.dumps({'passed': True, 'moduleCases': len(result['moduleCases']),
                      'handlerCases': len(result['actualPolicyHandlerCases']), 'activeMode': result['activeMode'],
                      'liveTrials': sum(p['trials'] for r in live['runs'] for p in r['phases']),
                      'postRestartTrials': post['allowTrials']}))
if __name__ == '__main__': main()
