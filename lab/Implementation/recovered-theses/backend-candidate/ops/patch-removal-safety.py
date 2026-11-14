import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
root=Path('/home/netpro/NetPro-Backend');candidate=Path(__file__).resolve().parents[1];rel='src/integration/bulk-policy.js'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if os.geteuid()!=0 or socket.gethostname()!='backend-vm':raise RuntimeError('Expected root on Management')
    expected=json.loads((candidate/'ops/csv-upgrade-manifest.json').read_text())['candidate'][rel]
    if sha(root/rel)!=expected:raise RuntimeError('Live bulk service changed; inspect before patching')
    subprocess.run(['node','--check',str(candidate/rel)],check=True)
    backup=Path('/root/netpro-csv-removal-safety-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir(mode=0o700)
    shutil.copy2(root/rel,backup/'bulk-policy.js');owner=(root/rel).stat()
    shutil.copy2(candidate/rel,root/rel);os.chown(root/rel,owner.st_uid,owner.st_gid)
    subprocess.run(['systemctl','restart','netpro-backend'],check=True,timeout=120)
    print(json.dumps({'patched':True,'backup':str(backup),'sha256':sha(root/rel)}))
if __name__=='__main__':main()
