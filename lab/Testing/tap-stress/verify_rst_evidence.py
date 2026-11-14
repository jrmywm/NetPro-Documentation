from pathlib import Path
import json,hashlib
p=Path(__file__).parent/'evidence'/'rst-stress-20261010T130008Z'
for f in p.glob('active-baseline-*.json'):
    x=json.loads(f.read_text());assert not x.get('failure'),x.get('failure')
    assert not any(c.get('status') in ('error','needs_review') for c in x['cleanup'])
    assert all(x['outcomes'][m]['passed'] for m in ('deny','allow'))
    print(f.name,'outcomes passed; cleanup completed')
(p/'SHA256.json').write_text(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.iterdir() if f.is_file() and f.name!='SHA256.json'},indent=2))
print('RST evidence manifest saved')
