"""Protect legacy SQLite lifecycle before a graceful VM shutdown."""
from pathlib import Path
import sys,json,datetime,shlex
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parents[1]/'Testing'/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
out=BASE/'evidence'/('policy-shutdown-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
out.mkdir(parents=True)
c,h=connect_verified('192.168.31.31','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
try:
    rc,root,err=run_remote_command(c,'mktemp -d /home/netpro/incoming/direct-topology-backup.XXXXXX');root=root.strip()
    if rc:raise RuntimeError(err)
    db='/home/ubuntu/NetPro-Policy-Server/policy.db'
    command=f'''set -eu
test "$(sqlite3 -readonly {db} 'PRAGMA integrity_check;')" = ok
sqlite3 {db} ".backup '{root}/policy-before.db'"
sqlite3 -readonly {root}/policy-before.db 'SELECT id FROM policies ORDER BY id;' > {root}/ids-before.txt
systemctl stop netpro-policy
if test ! -e {db}; then install -o netpro -g netpro -m 0644 {root}/policy-before.db {db}; fi
test "$(sqlite3 -readonly {db} 'PRAGMA integrity_check;')" = ok
sqlite3 -readonly {db} 'SELECT id FROM policies ORDER BY id;' > {root}/ids-after.txt
cmp {root}/ids-before.txt {root}/ids-after.txt
echo DATABASE_BACKUP_RESTORE_VERIFIED
systemctl is-active netpro-policy || true
'''
    rc,o,e=run_remote_command(c,command,sudo_password=__import__('os').environ['NETPRO_LAB_PASSWORD'],timeout=45)
    (out/'result.json').write_text(json.dumps(dict(remote=root,exit=rc,stdout=o,stderr=e),indent=2),encoding='utf-8')
    print('EXIT',rc,o,e,'EVIDENCE',out)
    if rc:raise RuntimeError('Database protection failed; do not power off VM')
finally:c.close()
