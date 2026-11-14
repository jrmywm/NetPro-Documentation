from pathlib import Path
import datetime,json,os,sys
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified,run_remote_command,redact
cred=os.environ.get('NETPRO_LAB_PASSWORD','netpro');out=Path(__file__).resolve().parent/'evidence'/('policy-startup-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
c=None
try:
 c,_=connect_verified('192.168.31.31','netpro',cred,Path(r'C:\Users\jim\.ssh\known_hosts'))
 cmd='''hostname
find /home/netpro/NetPro-Policy-Server -maxdepth 2 -type f -name '*.c' -print
grep -RInE 'DROP TABLE|DELETE FROM policies|remove.*policy.db|unlink.*policy.db' /home/netpro/NetPro-Policy-Server --include='*.c' --exclude-dir=build
grep -nE 'sqlite|database|DROP|remove|unlink' /usr/local/sbin/netpro-dpdk-prepare.sh
grep -nE 'sqlite3_open|DROP TABLE|CREATE TABLE|remove.*db|policy.db' /home/netpro/NetPro-Policy-Server/policyServer.c
sed -n '1450,1550p' /home/netpro/NetPro-Policy-Server/policyServer.c
grep -n 'close_database\|cleanup_database\|delete_database' /home/netpro/NetPro-Policy-Server/policyServer.c
find /home/netpro /root -maxdepth 5 -type f \\( -name '*.db' -o -name '*.sqlite' -o -name '*policy*backup*' -o -name '*policy*.bak' \\) 2>/dev/null | head -n 45
'''
 rc,o,e=run_remote_command(c,cmd,sudo_password=cred,timeout=45)
 (out/'result.json').write_text(json.dumps({'exit':rc,'stdout':redact(o),'stderr':redact(e)},indent=2),encoding='utf-8')
 print('EVIDENCE',out);print(redact(o));print(redact(e))
finally:
 if c:c.close()
