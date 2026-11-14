import os,sys,json,datetime,time
from pathlib import Path
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from active_baseline import ActiveBaseline,POLICY_HOST
from remote import connect_verified,run_remote_command
root=Path(__file__).resolve().parents[2]
out=root/'evidence'/('domain-index-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
password=os.environ['NETPRO_LAB_PASSWORD']
result={'passed':False,'phases':[]}
def regression(label):
 w=ActiveBaseline(password,out/label,Path.home()/'.ssh/known_hosts');original=w.run_id
 try:
  w.connect_all();w.baseline();w.start_gateway_server();w.start_return_helper()
  def probe(name,expect):
   w.run_id=original+'-'+name
   ok=w.run_probe(expect);result['phases'].append({'stage':label,'phase':name,'trials':20,'passed':ok});print(label,name,ok,flush=True)
   if not ok:raise RuntimeError('Packet regression failed')
  probe('allow-before','allow');w.create_policy();probe('deny','deny');w.configure_split_profile();probe('deny-split','deny');w.delete_policy_exactly();probe('allow-after','allow')
 finally:w.cleanup()
 if any(x.get('status')=='error' for x in w.document['cleanup']):raise RuntimeError('Cleanup needs review')
def index():
 c,_=connect_verified(POLICY_HOST,'netpro',password,Path.home()/'.ssh/known_hosts')
 cmd='''python3 - <<'PY'
import sqlite3,json,datetime
p='/home/ubuntu/NetPro-Policy-Server/policy.db'
c=sqlite3.connect(p,timeout=10)
before=c.execute('select id,domain,ip_address from policies order by id').fetchall()
b=sqlite3.connect('/home/netpro/policy-before-domain-index-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.db');c.backup(b);b.close()
old=c.execute('pragma index_list(policies)').fetchall()
c.execute('CREATE INDEX IF NOT EXISTS idx_policies_domain ON policies(domain)');c.commit()
assert [r[2] for r in c.execute('pragma index_info(idx_policies_domain)')]==['domain']
assert c.execute('select id,domain,ip_address from policies order by id').fetchall()==before
plan=c.execute('EXPLAIN QUERY PLAN SELECT id FROM policies WHERE domain=?',('netpro-tap.test',)).fetchall()
assert any('idx_policies_domain' in str(row) for row in plan),plan
assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
print(json.dumps({'before':old,'after':c.execute('pragma index_list(policies)').fetchall(),'queryPlan':plan,'rowsPreserved':True}))
PY'''
 try:
  rc,a,b=run_remote_command(c,cmd,sudo_password=password,timeout=60)
  if rc:raise RuntimeError(a+b)
  return json.loads(a)
 finally:c.close()
try:
 regression('before-index');result['index']=index();regression('after-index');result['passed']=True
finally:
 (out/'RESULTS.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print('Evidence:',out,flush=True)
