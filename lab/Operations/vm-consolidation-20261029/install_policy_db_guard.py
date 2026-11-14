from pathlib import Path
import datetime,json,os,sys
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified,run_remote_command,redact
base=Path(__file__).resolve().parent;stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=base/'evidence'/('policy-db-guard-'+stamp);out.mkdir(parents=True)
dropin='''[Service]
ExecStartPre=/usr/local/libexec/netpro-policy-db-guard restore-if-missing
ExecStop=/usr/local/libexec/netpro-policy-db-guard snapshot
ExecStopPost=/usr/local/libexec/netpro-policy-db-guard restore-if-missing
'''
(out/'consolidation-database.conf').write_text(dropin,encoding='utf-8')
cred=os.environ.get('NETPRO_LAB_PASSWORD','netpro');c=None
try:
 c,_=connect_verified('192.168.31.31','netpro',cred,Path(r'C:\Users\jim\.ssh\known_hosts'))
 with c.open_sftp() as s:
  s.put(str(base/'policy_db_guard.py'),'/home/netpro/netpro-policy-db-guard.py')
  s.put(str(out/'consolidation-database.conf'),'/home/netpro/consolidation-database.conf')
 cmd='''set -eu
test ! -e /usr/local/libexec/netpro-policy-db-guard
test ! -e /etc/systemd/system/netpro-policy.service.d/consolidation-database.conf
test "$(sqlite3 /home/ubuntu/NetPro-Policy-Server/policy.db 'SELECT count(*) FROM policies;')" = 4
install -d /usr/local/libexec
install -m 0755 /home/netpro/netpro-policy-db-guard.py /usr/local/libexec/netpro-policy-db-guard
/usr/local/libexec/netpro-policy-db-guard snapshot
install -d /etc/systemd/system/netpro-policy.service.d
install -m 0644 /home/netpro/consolidation-database.conf /etc/systemd/system/netpro-policy.service.d/consolidation-database.conf
systemctl daemon-reload
systemctl restart netpro-policy
systemctl is-active netpro-policy
sqlite3 /home/ubuntu/NetPro-Policy-Server/policy.db 'PRAGMA integrity_check; SELECT id FROM policies ORDER BY id;'
'''
 rc,o,e=run_remote_command(c,cmd,sudo_password=cred,timeout=65)
 (out/'result.json').write_text(json.dumps({'exit':rc,'stdout':redact(o),'stderr':redact(e)},indent=2),encoding='utf-8')
 print('EXIT',rc,'EVIDENCE',out);print(redact(o));print(redact(e));sys.exit(rc)
finally:
 if c:c.close()
