"""Restore only the three known SQLite-only baseline rows from a verified backup."""
from pathlib import Path
import argparse,datetime,json,os,sys
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified,run_remote_command,redact
p=argparse.ArgumentParser();p.add_argument('--restore',action='store_true');a=p.parse_args()
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=Path(__file__).resolve().parent/'evidence'/('policy-baseline-recovery-'+stamp);out.mkdir(parents=True)
script=r'''from pathlib import Path
import hashlib,json,sqlite3
expected={'kafka-persistence-test','netpro-http-facebook-001','netpro-tls-ui-001','7f3fbb19-4064-432c-b9b9-72363c5c1cd9'}
api_id='7f3fbb19-4064-432c-b9b9-72363c5c1cd9'
db=Path('/home/ubuntu/NetPro-Policy-Server/policy.db')
def rows(p):
 with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as c:
  assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  return c.execute('SELECT id,ip_address,domain FROM policies ORDER BY id').fetchall()
current=rows(db);assert {r[0] for r in current}=={api_id}, 'Unexpected live baseline; refusing'
candidates=sorted(Path('/home/netpro/incoming').glob('*/policy-before.db'),key=lambda p:p.stat().st_mtime,reverse=True)
selected=None
for p in candidates:
 try:r=rows(p)
 except Exception:continue
 if {x[0] for x in r}==expected and [x for x in r if x[0]==api_id]==current:
  selected=(p,r);break
assert selected is not None,'No matching original baseline backup'
source,original=selected
print(json.dumps({'source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'original_rows':original,'current_rows':current}))
if __RESTORE__:
 folder=Path('/root/netpro-policy-consolidation-recovery/STAMP');folder.mkdir(mode=0o700,parents=True,exist_ok=False)
 with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as c:
  with sqlite3.connect(str(folder/'before.db')) as b:c.backup(b)
 with sqlite3.connect(str(db),timeout=10) as c:
  c.execute('BEGIN IMMEDIATE')
  assert c.execute('SELECT id,ip_address,domain FROM policies ORDER BY id').fetchall()==current
  c.executemany('INSERT INTO policies(id,ip_address,domain) VALUES(?,?,?)',[r for r in original if r[0]!=api_id])
 assert rows(db)==original
 print('RESTORED_ONLY_THREE_MISSING_ROWS; integrity ok; existing API row unchanged')
'''.replace('__RESTORE__','True' if a.restore else 'False').replace('STAMP',stamp)
# The literal replacement above is restricted to the boolean marker and stamp.
cmd="python3 - <<'PY'\n"+script+'\nPY'
cred=os.environ.get('NETPRO_LAB_PASSWORD','netpro');c=None
try:
 c,_=connect_verified('192.168.31.31','netpro',cred,Path(r'C:\Users\jim\.ssh\known_hosts'))
 rc,o,e=run_remote_command(c,cmd,sudo_password=cred,timeout=40)
 (out/'result.json').write_text(json.dumps({'exit':rc,'restore':a.restore,'stdout':redact(o),'stderr':redact(e)},indent=2),encoding='utf-8')
 print('EXIT',rc,'EVIDENCE',out);print(redact(o));print(redact(e));sys.exit(rc)
finally:
 if c:c.close()
