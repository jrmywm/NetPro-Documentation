"""Guarded final response-size/progress-label deployment; no schema or policy changes."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess

root=Path('/home/netpro/NetPro-Backend');candidate=Path(__file__).resolve().parents[1]
rel='src/integration/csv-imports.js';nginx=Path('/etc/nginx/conf.d/netpro-frontend.conf')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args):return subprocess.run(args,capture_output=True,text=True,check=True,timeout=120)
def main():
    if os.geteuid()!=0 or socket.gethostname()!='backend-vm':raise RuntimeError('Expected root on Management')
    expected=json.loads((candidate/'ops/csv-upgrade-manifest.json').read_text())['candidate'][rel]
    if sha(root/rel)!=expected:raise RuntimeError('Live CSV service changed; inspect before updating')
    run(['node','--check',str(candidate/rel)])
    tag=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=Path('/root/netpro-csv-final-'+tag);backup.mkdir(mode=0o700)
    shutil.copy2(root/rel,backup/'csv-imports.js');shutil.copy2(nginx,backup/'nginx.conf')
    try:
        owner=(root/rel).stat();shutil.copy2(candidate/rel,root/rel);os.chown(root/rel,owner.st_uid,owner.st_gid)
        run(['systemctl','restart','netpro-backend'])
        build=candidate.parent/'frontend-candidate/build';target=Path('/var/www/netpro-frontend-csv-final-'+tag)
        shutil.copytree(build,target)
        text,count=re.subn(r'root\s+[^;]+;','root '+str(target)+';',nginx.read_text(),count=1)
        if count!=1:raise RuntimeError('Frontend root directive missing')
        nginx.write_text(text);run(['nginx','-t']);run(['systemctl','reload','nginx'])
        result={'deployed':True,'backup':str(backup),'frontendRoot':str(target),'csvSourceSha256':sha(root/rel)}
        (backup/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    except Exception:
        shutil.copy2(backup/'csv-imports.js',root/rel);shutil.copy2(backup/'nginx.conf',nginx)
        run(['systemctl','restart','netpro-backend']);run(['nginx','-t']);run(['systemctl','reload','nginx']);raise
if __name__=='__main__':main()
