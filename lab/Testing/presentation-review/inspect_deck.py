from pathlib import Path
import json
import subprocess
import sys
from pypdf import PdfReader
sys.stdout.reconfigure(encoding='utf-8')

source = Path(r'C:\Users\jim\.codex\attachments\44db7525-d616-4a57-acb6-ae2354cb1e5f\Presentasi Progres Despro 2_Kelompok 27.pdf')
out = Path(r'C:\Users\jim\Documents\NetPro\Testing\presentation-review\2026-10-14')
out.mkdir(parents=True, exist_ok=True)
doc = PdfReader(source)
pages = []
for index, page in enumerate(doc.pages):
    text = page.extract_text() or ''
    pages.append({'slide': index + 1, 'text': text})
    print(f'{index+1}: ' + ' / '.join(text.splitlines()[:4]))
(out / 'slides-text.json').write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding='utf-8')
subprocess.run([r'C:\Users\jim\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe', '-r', '80', '-png', str(source), str(out / 'slide')], check=True)
print(f'Pages: {len(doc.pages)}; extracted text and rendered pages saved.')
