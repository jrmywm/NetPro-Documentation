from pathlib import Path
import hashlib,json
p=Path(__file__).parent/'evidence'/'tap-stress-20261010T125304Z'
(p/'SHA256.json').write_text(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.iterdir() if f.is_file() and f.name!='SHA256.json'},indent=2))
print('Evidence manifest refreshed')
