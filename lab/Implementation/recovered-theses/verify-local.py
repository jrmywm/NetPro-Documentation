"""Repeat local safety/syntax/import/provenance checks; does not start the app."""
import hashlib
import ast
import json
from pathlib import Path
import re
import subprocess
import zipfile

BASE = Path(__file__).resolve().parent
APP = BASE / 'luthfi'
MANIFEST = Path(r'C:\Users\jim\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an-2\work\thesis-review-2021\sources\recovered-code-20261029\IMPORT-MANIFEST.json')
out = BASE / 'evidence'
out.mkdir(exist_ok=True)
result = {'syntax_errors': [], 'relative_import_errors': [], 'original_integrity_errors': [], 'original_files_verified': 0}
unit_files = [str(p.relative_to(APP)) for p in sorted((APP / 'tests').glob('*.test.js'))]
unit = subprocess.run(['node', '--test', *unit_files], cwd=APP, capture_output=True, text=True)
(out / 'startup-unit.tap').write_text(unit.stdout + unit.stderr, encoding='utf-8')
result['unit_exit'] = unit.returncode
files = [p for p in APP.rglob('*.js') if 'node_modules' not in p.parts]
for p in files:
    check = subprocess.run(['node', '--check', str(p)], capture_output=True, text=True)
    if check.returncode:
        result['syntax_errors'].append(str(p.relative_to(APP)))
    for relative in re.findall(r'require\([\'"](\.[^\'"]+)[\'"]\)', p.read_text(encoding='utf-8')):
        target = p.parent / relative
        candidates = [target, Path(str(target) + '.js'), target / 'index.js']
        if not any(c.is_file() and c.name in [x.name for x in c.parent.iterdir()] for c in candidates if c.parent.exists()):
            result['relative_import_errors'].append([str(p.relative_to(APP)), relative])
result['javascript_files_checked'] = len(files)
backend_files = list((BASE / 'backend-candidate').rglob('*.js'))
for p in backend_files:
    check = subprocess.run(['node', '--check', str(p)], capture_output=True, text=True)
    if check.returncode:
        result['syntax_errors'].append(str(p.relative_to(BASE)))
result['backend_javascript_files_checked'] = len(backend_files)
result['python_syntax_errors'] = []
for p in (BASE / 'backend-candidate/ops').glob('*.py'):
    try:
        ast.parse(p.read_text(encoding='utf-8'))
    except SyntaxError as error:
        result['python_syntax_errors'].append([p.name, str(error)])
manifest = json.loads(MANIFEST.read_text(encoding='utf-8-sig'))
for archive in manifest['Archives']:
    p = Path(archive['Archive'])
    if hashlib.sha256(p.read_bytes()).hexdigest().upper() != archive['SHA256']:
        result['original_integrity_errors'].append('Archive SHA mismatch: ' + p.name)
    with zipfile.ZipFile(p) as z:
        for entry in z.infolist():
            if entry.is_dir() or entry.filename in archive['SkippedMetadata']:
                continue
            extracted = Path(archive['Destination']) / entry.filename
            if not extracted.is_file() or hashlib.sha256(extracted.read_bytes()).digest() != hashlib.sha256(z.read(entry)).digest():
                result['original_integrity_errors'].append(entry.filename)
            else:
                result['original_files_verified'] += 1
result['passed'] = not (unit.returncode or result['syntax_errors'] or result['relative_import_errors'] or result['original_integrity_errors'] or result['python_syntax_errors'])
(out / 'local-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['passed'] else 1)
