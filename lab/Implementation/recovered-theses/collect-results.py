"""Create a compact, credential-free acceptance summary for local version control."""
import json
from pathlib import Path
import re

BASE=Path(__file__).resolve().parent
EVIDENCE=BASE/'evidence'
def load(name):return json.loads((EVIDENCE/name).read_text(encoding='utf-8'))
def cases(name):
    data=load(name)
    return {'evidence':name,'passed':sum(bool(x['passed']) for x in data['results']),
        'failed':sum(not x['passed'] for x in data['results']),
        'cases':[{'name':x['name'],'passed':x['passed']} for x in data['results']]}
def main():
    results={'scope':'Luthfi functional integration; not a claim of identical thesis performance',
        'frontend':{'interactiveBrowserVerified':False,'blocker':'lab self-signed certificate requires user acceptance'},
        'backend_adapter':cases('stage4-authoritative-adapter.json'),
        'integrated_csv':cases('csv-dashboard-integration.json'),
        'live_load':cases('csv-live-load.json'),
        'deployed_health':load('final-health.json')}
    text=(EVIDENCE/'frontend-tests.log').read_text(encoding='utf-8',errors='replace')
    summary=re.search(r'Test Suites:\s*(\d+) passed,\s*(\d+) total\s*Tests:\s*(\d+) passed,\s*(\d+) total',text)
    if not summary:raise RuntimeError('Frontend suite is not entirely passing')
    results['frontend'].update({'suitesPassed':int(summary[1]),'suitesTotal':int(summary[2]),'testsPassed':int(summary[3]),'testsTotal':int(summary[4]),'productionBuild':'passed'})
    restart=load('live-csv-restart.json');socket=load('live-csv-socket.json')
    results['real_restart']={'passed':restart['passed'],'checkpoint':restart['restartCheckpoint'],
        'rowsValidated':restart['fixture']['valid'],'duplicates':restart['fixture']['duplicate'],'invalid':restart['fixture']['invalid']}
    results['real_socket']={'passed':socket['passed'],'ownerEvents':socket['ownerEvents'],
        'otherOwnerEvents':socket['otherOwnerEvents'],'unauthenticatedRejected':socket['unauthenticatedRejected']}
    packet=sorted(EVIDENCE.glob('csv-packets-*/results.json'))[-1];data=json.loads(packet.read_text(encoding='utf-8'))
    results['packet_blocking']={'passed':data['passed'],'evidence':str(packet.relative_to(BASE)),
        'phases':[{'name':r['name'],'passed':r['passed'],'trials':20} for r in data['results']],
        'baselineRestored':data['baseline_restored'],'cleanup':data['cleanup'][-1]['status']}
    results['limitations']=['No automatic PS enforcement acknowledgement; published means Kafka acknowledged',
        'Use template CSV and current consumer-compatible domains; IPv4 optional, no URL/wildcard import',
        'Original legacy dependency versions retained; no internet-production security audit',
        'Whole-file activation uses durable batches and can be partial until complete; use retry/owned removal',
        'Rafie integration and thesis-performance replication are separate work']
    target=BASE/'test-results';target.mkdir(exist_ok=True)
    (target/'luthfi-functional.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps({'summary':str(target/'luthfi-functional.json'),'frontendTests':results['frontend']['testsPassed'],
        'backendCases':results['backend_adapter']['passed'],'csvCases':results['integrated_csv']['passed'],
        'packetPhasesPassed':all(x['passed'] for x in results['packet_blocking']['phases'])}))
if __name__=='__main__':main()
