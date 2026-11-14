from pathlib import Path
import subprocess,shutil,json,hashlib,re
SRC=Path(r'C:\Users\jim\Documents\NetPro')
DST=Path(r'C:\Users\jim\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an-2\NetPro-Documentation-current')
manifest=[]
def copy(src,dest):
 dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
 manifest.append({'path':dest.relative_to(DST).as_posix(),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'bytes':dest.stat().st_size})
p=SRC/'Implementation/recovered-theses'
for name in subprocess.check_output(['git','-C',str(p),'ls-files'],text=True).splitlines():
 if name=='.gitignore':continue
 copy(p/name,DST/'implementation/recovered-theses'/name)
blocked={'evidence','__pycache__','node_modules','.git','work','build','dist','retained-inputs'}
allowed={'.py','.ps1','.sh','.c','.h','.md','.conf'}
for root,target in [('Implementation/thesis-stack','implementation/thesis-stack'),('Testing','scripts/testing'),('Operations','scripts/operations')]:
 p=SRC/root
 for f in p.rglob('*'):
  rel=f.relative_to(p)
  if not f.is_file() or any(part in blocked for part in rel.parts):continue
  if f.suffix in allowed or f.name in {'Caddyfile','SOURCE-PINS.json'}:copy(f,DST/target/rel)
for week in ['Pekan-10','Pekan-11']:
 for f in (SRC/'Documentation/Reports'/week).glob('*.docx'):copy(f,DST/'reports'/week/f.name)
for f in (SRC/'Documentation/Reports/Deployment-Evidence').glob('*.png'):copy(f,DST/'evidence/deployment-browser-2026-11-07'/f.name)
p=SRC/'Testing/startup-check-20261114'
for name in ['RESULTS.md','health.json','management.json','acceptance.json']:
 copy(p/name,DST/'evidence/startup-2026-11-14'/name)
p=SRC/'Implementation/thesis-stack/evidence'
for folder,names in {
 'persistent-prototype-20261107T080925Z':['deployment.json'],
 'browser-persistent-20261107T100339Z':['browser-results.json'],
 'browser-persistent-20261113T214346Z':['browser-results.json'],
 'chromium-reassembly-build-20261107T095606Z':['build-result.json','npb-build-result.json'],
}.items():
 for name in names:
  f=p/folder/name
  if f.exists():copy(f,DST/'evidence/thesis-integration'/folder/name)
(DST/'docs/integration-source-manifest-2026-11-14.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
print('Copied',len(manifest),'files;',round(sum(x['bytes'] for x in manifest)/1048576,2),'MiB')
patterns=[r'(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_\-]{12,}',r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',r'(?i)(?:password|passwd|PGPASSWORD)\s*[=:]\s*[\"\x27][^\"\x27]{2,}[\"\x27]']
findings=[]
for item in manifest:
 f=DST/item['path']
 if f.suffix in {'.png','.docx'}:continue
 try:s=f.read_text(encoding='utf8')
 except UnicodeDecodeError:continue
 for i,line in enumerate(s.splitlines(),1):
  if any(re.search(pat,line) for pat in patterns):findings.append(f'{item["path"]}:{i}')
print('Credential-like lines for review (values omitted):\n'+'\n'.join(findings[:100]))
