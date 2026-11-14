from pathlib import Path
import json,hashlib,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
OUT=Path(__file__).parent/'evidence'/'tap-stress-20261010T125304Z'
summary=json.loads((OUT/'summary.json').read_text())
lines=['protocol,concurrency,attempted,success,failure,requests_per_second,p95_ms,p99_ms']
for s in summary['stages']:
    lines.append(','.join(str(s[k]) for k in ('protocol','concurrency','requests','success','failure','completed_rps','p95_ms','p99_ms')))
(OUT/'stage-results.csv').write_text('\n'.join(lines)+'\n')
report=(OUT/'RESULTS.md').read_text()
report+='\n## Evidence retention qualification\nThe initial ten-second one-client stage summaries are retained in summary.json. Their remote raw JSONL filenames were reused by the three-second recovery probes, so the corresponding client-http-c1.jsonl and client-https-c1.jsonl files contain recovery requests, not the original ten-second stages. Other stage raw files are intact. The repeatable runner has been corrected to download stage-prefixed raw evidence before recovery. This retention defect does not change the observed stage summary, but prevents independent recalculation of those two stages from raw rows.\n'
report+='\n## Final cleanup verification\n'
for role,ip in summary['hosts'].items():
    c,_=connect_verified(ip,'netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
    cmd='systemctl is-active netpro-virtual-tap-mirror netpro-npb netpro-policy; ss -ltn; true'
    if role in ('gateway','tap','client'):
        cmd+='; systemctl list-units --all --no-legend "'+summary['run']+'*"'
    rc,out,err=run_remote_command(c,cmd);c.close()
    (OUT/f'cleanup-verified-{role}.txt').write_text(out+err)
    if role=='gateway':
        assert ':18080' not in out and ':18443' not in out
        report+='- Gateway temporary ports 18080 and 18443 are no longer listening.\n'
    if role in ('tap','npb','policy'):
        assert 'active' in out.splitlines()[:3]
        report+=f'- {role} main service remains active.\n'
(OUT/'RESULTS.md').write_text(report)
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='SHA256.json'}
(OUT/'SHA256.json').write_text(json.dumps(manifest,indent=2))
print('verified',len(manifest),'evidence files; total stage requests',sum(x['requests'] for x in summary['stages']))
print(report.split('## Resources and observed counters')[1].split('## Recovery and cleanup')[0])
