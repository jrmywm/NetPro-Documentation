"""Preserve recovered original branch files and auditable content fingerprints."""
from pathlib import Path
import json, shutil, hashlib
BASE = Path(__file__).resolve().parent
AUDIT = Path(r'C:\Users\jim\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an-2\work\thesis-review-2021\repository-audit')
archive = json.loads((AUDIT / 'NetPro-Policy-Server-archive.json').read_text(encoding='utf-8'))
records = []
for branch in archive['branches']:
 if branch['name'] not in ['Bintang-Monitoring-Platform', 'quic-dev']: continue
 source = AUDIT / 'sources/NetPro-Policy-Server' / branch['name']
 destination = BASE / 'original' / branch['name']
 if destination.exists(): raise RuntimeError('Refusing to overwrite original source snapshot')
 shutil.copytree(source, destination)
 files = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file()}
 records.append(dict(repository=archive['fullName'], branch=branch['name'], commit=branch['sha'], files=files))
(BASE / 'SOURCE-PINS.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
for record in records: print(record['branch'], record['commit'], 'files', len(record['files']))
