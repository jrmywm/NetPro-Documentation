"""Back up and narrowly reduce the next-boot hugepage reservation."""
from pathlib import Path
import datetime,json,os,sys
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified,run_remote_command,redact
role=sys.argv[1]
roles={'policy':('192.168.31.31','/usr/local/sbin/netpro-dpdk-prepare.sh'),'npb':('192.168.31.33','/usr/local/sbin/netpro-npb-dpdk-prepare.sh')}
ip,path=roles[role];stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=Path(__file__).resolve().parent/'evidence'/('hugepage-'+role+'-'+stamp);out.mkdir(parents=True)
cred=os.environ.get('NETPRO_LAB_PASSWORD','netpro');c=None
try:
 c,_=connect_verified(ip,'netpro',cred,Path(r'C:\Users\jim\.ssh\known_hosts'))
 cmd=f'''set -eu
test -f {path}
cp -a {path} {path}.before-consolidation-{stamp}
python3 - <<'PY'
from pathlib import Path
p=Path('{path}');s=p.read_text()
assert s.count('--setup 2G')==1
p.write_text(s.replace('--setup 2G','--setup 1G'))
PY
grep -n hugepages {path}
'''
 rc,o,e=run_remote_command(c,cmd,sudo_password=cred,timeout=30)
 (out/'result.json').write_text(json.dumps({'exit':rc,'stdout':redact(o),'stderr':redact(e),'backup':path+'.before-consolidation-'+stamp},indent=2),encoding='utf-8')
 print('EXIT',rc,'EVIDENCE',out);print(redact(o));print(redact(e));sys.exit(rc)
finally:
 if c:c.close()
