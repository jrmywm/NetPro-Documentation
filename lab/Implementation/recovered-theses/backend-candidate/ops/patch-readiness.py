import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess

root=Path('/home/netpro/NetPro-Backend'); candidate=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if os.geteuid()!=0 or socket.gethostname()!='backend-vm':raise RuntimeError('Expected root on Management')
    expected=json.loads((candidate/'ops/csv-upgrade-manifest.json').read_text())['candidate']['index.js']
    if sha(root/'index.js')!=expected:raise RuntimeError('Live index changed; inspect before patching')
    subprocess.run(['node','--check',str(candidate/'index.js')],check=True)
    backup=Path('/root/netpro-csv-readiness-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700);shutil.copy2(root/'index.js',backup/'index.js')
    owner=(root/'index.js').stat();shutil.copy2(candidate/'index.js',root/'index.js');os.chown(root/'index.js',owner.st_uid,owner.st_gid)
    subprocess.run(['systemctl','restart','netpro-backend'],check=True,timeout=120)
    print(json.dumps({'patched':True,'backup':str(backup),'indexSha256':sha(root/'index.js')}))
if __name__=='__main__':main()
