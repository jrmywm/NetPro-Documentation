#!/usr/bin/python3
"""Preserve SQLite across the original binary's destructive graceful exit.

Used only by systemd on controlled stops; does not change packet processing.
Missing-file recovery is not a complete crash-consistency or Kafka replay fix.
"""
from pathlib import Path
import datetime,os,sqlite3,sys

os.umask(0o077)
db=Path('/home/ubuntu/NetPro-Policy-Server/policy.db')
state=Path('/var/lib/netpro-policy-db-guard')
state.mkdir(mode=0o700,parents=True,exist_ok=True)
snapshot=state/'latest.db'
mode=sys.argv[1]
if mode=='snapshot':
    if not db.is_file():
        raise SystemExit('Refusing snapshot: live database is missing')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    archived=state/(stamp+'.db')
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=10) as source:
        if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise SystemExit('Live SQLite integrity check failed')
        with sqlite3.connect(str(archived)) as dest:source.backup(dest)
    temp=state/'latest.db.tmp'
    with sqlite3.connect('file:'+str(archived)+'?mode=ro',uri=True) as source:
        with sqlite3.connect(str(temp)) as dest:source.backup(dest)
    os.replace(temp,snapshot)
    print('Policy database snapshot retained:',archived)
elif mode=='restore-if-missing':
    if db.exists():
        print('Existing policy database left unchanged')
    elif snapshot.is_file():
        temp=db.with_name('policy.db.guard-restore')
        with sqlite3.connect('file:'+str(snapshot)+'?mode=ro',uri=True) as source:
            if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise SystemExit('Snapshot integrity check failed')
            with sqlite3.connect(str(temp)) as dest:source.backup(dest)
        os.chmod(temp,0o600)
        os.replace(temp,db)
        print('Policy database restored after original binary cleanup')
    else:
        raise SystemExit('Missing live policy database and no guarded snapshot')
else:
    raise SystemExit('Unknown mode')
