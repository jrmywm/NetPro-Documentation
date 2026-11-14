import os,sys,json,datetime
from pathlib import Path
BASE=Path(r'C:\Users\jim\Documents\NetPro')
sys.path[:0]=[str(BASE/'Testing/snmp-quic-integration'),str(BASE/'Testing/thesis-replication')]
import active_baseline as ab
ab.TEST_DOMAIN='mysite.local';ab.TEST_IP='192.168.80.28'
OUT=Path(__file__).resolve().parent
w=ab.ActiveBaseline(os.environ['NETPRO_LAB_PASSWORD'],OUT,Path.home()/'.ssh/known_hosts')
results=[]
def probe(phase,mode):
 opt={'h3':'--http3-only','tls':'--http1.1','fallback':'--http3'}[mode]
 for trial in (1,2):
  shell=f"/home/netpro/netpro-thesis/http3/prefix/bin/curl {opt} --noproxy '*' --interface 192.168.80.29 --resolve mysite.local:443:192.168.80.28 -k --max-time 5 -sS -o /dev/null -w 'HTTP %{{http_code}} VERSION %{{http_version}}\\n' https://mysite.local/; rc=$?; echo CURL_EXIT=$rc"
  _,out,_=w.command('192.168.31.39',f'{phase}-{mode}-{trial}',shell,timeout=15)
  rc=int(out.split('CURL_EXIT=')[-1].strip())
  ok=(rc in (28,35,56) and 'HTTP 000' in out) if phase=='deny' else (rc==0 and 'HTTP 200' in out and (mode!='h3' or 'VERSION 3' in out))
  row=dict(phase=phase,mode=mode,trial=trial,passed=ok,output=out)
  results.append(row); print(json.dumps(row),flush=True)
try:
 w.connect_all();w.baseline()
 for m in ('h3','tls','fallback'):probe('before',m)
 if not all(r['passed'] for r in results):raise RuntimeError('Allow baseline failed')
 w.create_policy()
 try:
  for m in ('h3','tls','fallback'):probe('deny',m)
 finally:w.delete_policy_exactly()
 for m in ('h3','tls','fallback'):probe('after',m)
 w.baseline()
 print('BASELINE RESTORED',flush=True)
finally:
 try:
  if w.policy_id:w.delete_policy_exactly()
 finally:
  (OUT/'acceptance.json').write_text(json.dumps(results,indent=2),encoding='utf8');w.save()
  for c in w.clients.values():c.close()
print('PASS',sum(r['passed'] for r in results),'/',len(results),flush=True)
if not all(r['passed'] for r in results):sys.exit(1)
