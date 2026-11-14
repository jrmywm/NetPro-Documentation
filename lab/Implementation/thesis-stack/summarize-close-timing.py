"""Summarize authenticated Close timing using one client capture clock."""
from pathlib import Path
import json,sys,statistics,subprocess
base=Path(__file__).resolve().parent;evidence=Path(sys.argv[1])
subprocess.run([sys.executable,str(base/'analyze-close-capture.py'),str(evidence)],check=True,capture_output=True)
rows=json.loads((evidence/'close-analysis.json').read_text());flows={}
for row in rows:
    if 'connection_id' not in row:continue
    flow=flows.setdefault(row['connection_id'],{})
    for key,flag in [('initial','client_initial'),('close','authenticated'),('handshake','server_handshake')]:
        if row.get(flag):flow.setdefault(key,row['relative_ms'])
pairs=[f for f in flows.values() if 'initial' in f and 'close' in f]
close=[f['close']-f['initial'] for f in pairs]
handshake=[f['handshake']-f['initial'] for f in pairs if 'handshake' in f]
report={'close_connections':len(pairs),'bad_auth':sum('authentication_error' in r for r in rows)}
if close:report.update(close_ms_mean=statistics.mean(close),close_ms_median=statistics.median(close),close_ms_min=min(close),close_ms_max=max(close))
if handshake:report.update(handshake_ms_mean=statistics.mean(handshake),handshake_before_or_same_as_close=sum(f.get('handshake',float('inf'))<=f['close'] for f in pairs))
(evidence/'timing-summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
