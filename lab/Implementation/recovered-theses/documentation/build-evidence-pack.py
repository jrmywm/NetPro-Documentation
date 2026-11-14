"""Package existing public test evidence and fresh health data; no fabricated screenshots."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

BASE = Path(__file__).resolve().parents[1]
OUT = Path(r'C:\Users\jim\Documents\NetPro\Documentation\Evidence\adapted-integration-20261031')

GUIDE = r'''# Evidence pack — adapted Luthfi + Rafie integration

Prepared 31 October 2026. This pack documents the accepted HTTP/TLS architecture. It does not establish fully adapted QUIC enforcement, physical-TAP fail-open behavior, or identical thesis performance.

## What this pack contains

| Item | Evidence | What it establishes |
| --- | --- | --- |
| `live-health.json` | Fresh read-only checks from the deployed VMs | Rafie mode enabled; Kafka replay ready; zero cache errors; backend/PostgreSQL/Kafka/nginx active; import routes enforce authentication |
| `luthfi-functional.json` + `02-luthfi.txt` | Recorded 30–31 October tests | CSV review/activation pipeline, 100,000-row restart recovery, user-scoped progress, frontend tests |
| `rafie-functional.json` + `03-rafie.txt` | Recorded 31 October tests | Correct filter coverage, LRU, mutation invalidation, saturation/deletion, actual handler concurrency and sanitizer checks |
| `04-packets.txt` | Recorded client tests with underlying PCAP references | Four 20-request phases in each of shadow and enabled modes; zero shadow mismatches; 1,001 CSV policies propagated and removed |
| `05-benchmark.txt` | Recorded standalone lookup comparison | Exact processed counts and latency/QPS; workload-dependent results and explicit limits |
| Acceptance reports + architecture | Methods, implementation, backups and scope | Context for explaining what is adapted and what remains separate |

The text pages are output from a real Python command reading retained test artifacts. They are labelled **RECORDED TEST EVIDENCE**, not presented as freshly rerun packet tests. The separate live health JSON contains its actual check timestamp.

## Screenshot commands — Windows Terminal on the host PC

Use your existing Windows Terminal. Maximize it, run one page, and capture the actual visible output. These commands only show evidence; they do not add/delete block rules or rerun active packet tests.

```powershell
Set-Location 'C:\Users\jim\Documents\NetPro\Implementation\recovered-theses'
```

### Screenshot 1 — currently deployed services and cache

```powershell
& .\documentation\Open-Evidence.ps1 -Page live
```

Enter the lab SSH password if prompted. It is not echoed. Include `mode: rafie`, replay readiness, cache counters, zero errors and service health. HTTP 401 on an unauthenticated CSV route is expected and demonstrates access control.

Caption: **“Pemeriksaan layanan aktif menunjukkan mode lookup Rafie telah digunakan pada Policy Server. Sinkronisasi Kafka telah selesai, tidak terdapat error lookup, dan layanan backend, PostgreSQL, Kafka, serta nginx aktif.”**

### Screenshot 2 — Luthfi's CSV/durability evidence

```powershell
& .\documentation\Open-Evidence.ps1 -Page luthfi
```

Include the 100,000-row recovery result, checkpoint 1,000, scoped Socket.IO results, pipeline checks and the recorded-evidence label.

Caption: **“Hasil pengujian adaptasi unggah CSV menunjukkan 100.000 baris berhasil divalidasi setelah proses dilanjutkan dari checkpoint saat backend dimulai ulang. Pengujian juga memverifikasi peninjauan sebelum aktivasi, progres terpisah per pengguna, retry, serta penghapusan kebijakan milik impor.”**

### Screenshot 3 — Rafie's correctness and update handling

```powershell
& .\documentation\Open-Evidence.ps1 -Page rafie
```

Include coverage beyond 10,000 rows, saturation/deletion, LRU eviction, concurrent updates, temporary database-lock retry and sanitizer results.

Caption: **“Pengujian modul dan handler Policy Server memverifikasi kesesuaian keputusan dengan SQLite, penggantian entri berdasarkan LRU, invalidasi setelah perubahan kebijakan, serta ketepatan filter ketika counter jenuh dan kebijakan dihapus. Pengujian sanitizer selesai tanpa temuan pada cakupan uji tersebut.”**

### Screenshot 4 — combined allow, deny and removal

```powershell
& .\documentation\Open-Evidence.ps1 -Page packets
```

This is the strongest combined functional-evidence page. Include all eight passing phases and the 1,001-policy CSV propagation/removal result.

Caption: **“Pada jalur Client–Virtual TAP–NPB–Policy Server, setiap fase berhasil 20 dari 20 percobaan: akses diizinkan sebelum aturan ditambahkan, direset setelah aturan aktif, tetap diblokir pada ClientHello tersegmentasi, dan kembali diizinkan setelah aturan dihapus. Hasil konsisten pada mode shadow dan mode Rafie aktif.”**

### Screenshot 5 — optional performance evidence

```powershell
& .\documentation\Open-Evidence.ps1 -Page benchmark
```

Retain the workload description and limitations in the image. Do not crop out the indexed-workload result or relabel this as packet throughput.

Caption: **“Perbandingan lookup mandiri menggunakan dataset dan urutan kueri yang sama menunjukkan peningkatan pada beban campuran yang diuji, dengan nol perbedaan keputusan. Hasil bergantung pada beban; pada pengujian kueri berulang dengan indeks, SQLite lebih cepat. Angka ini bukan throughput jaringan penuh atau replikasi identik performa skripsi.”**

## Keeping the mouse pointer out

Move the pointer onto the taskbar or another window before capturing. `Open-Evidence.ps1` hides the console's text caret where supported; it does not control the mouse. For a manual capture, use Snipping Tool's window/rectangle capture and select only the terminal. Inspect the saved image before using it. Do not paint over the pointer or alter result text afterward.

Original terminal and dashboard screenshots supplied by the user are saved unchanged under `screenshots/`. See `screenshots/README.md` for the index and scope notes. The agent did not generate or retouch these images. The initial CSV dashboard page is documented; interactive upload/activation verification remains separate from merely displaying the page.

## Dashboard evidence to add once browser access is available

Open `https://192.168.31.35:3005/dashboard/imports` and sign in with the normal account. Any browser-generated certificate warning must be handled by the user. Useful actual UI images are the CSV entry/upload controls, a validated preview with counts/failed rows, and a completed import's stored/published counts. Record what the UI actually shows; do not describe Kafka publication as an enforcement acknowledgement. Browser click-through remains a separately outstanding check.

## Raw rerun commands — Policy Server VM

These rerun isolated tests against disposable databases, not the live policy table:

```bash
cd /home/netpro/incoming/rafie-integration-20261031
./lookup-test
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 ./lookup-asan
./policy-event-test
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 ./policy-event-asan
```

For current status only:

```bash
systemctl is-active netpro-policy
sudo cat /run/netpro-policy-cache.json | python3 -m json.tool
```

Full active packet reruns are under the implementation directory's `rafie/ops/run-live.py`; they temporarily alter demo policy/service state and retain their own detailed evidence. They are not invoked merely to display the saved pages.

## Integrity and source

`SHA256SUMS.txt` covers files in this package. Original raw packet captures remain in the implementation evidence directories referenced by the versioned JSON summaries. Source, test scripts and acceptance records are locally versioned; no upstream push is part of this evidence collection.
'''

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    for name in ['luthfi-functional.json','rafie-functional.json']:
        shutil.copy2(BASE/'test-results'/name, OUT/name)
    for name in ['LUTHFI-ACCEPTANCE.md','RAFIE-ACCEPTANCE.md','ARCHITECTURE-ADAPTED.md']:
        shutil.copy2(BASE/name, OUT/name)
    shutil.copy2(BASE/'THESIS-FIDELITY-AUDIT-2026-10-31.md',OUT/'THESIS-FIDELITY-AUDIT-2026-10-31.md')
    shutil.copy2(BASE/'documentation/REPORT-FIGURE-PLAN.md',OUT/'REPORT-FIGURE-PLAN.md')
    for number,page in enumerate(['luthfi','rafie','packets','benchmark'],2):
        p=subprocess.run([sys.executable,'-X','utf8',str(BASE/'documentation/evidence_console.py'),page],check=True,capture_output=True,text=True,encoding='utf-8')
        (OUT/('%02d-%s.txt'%(number,page))).write_text(p.stdout,encoding='utf-8',newline='\n')
    raw=OUT/'raw';raw.mkdir(exist_ok=True)
    for name in ['module-test.log','module-asan.log','event-test.log','event-asan.log','benchmark.jsonl','csv-regression.json','deployment.json']:
        shutil.copy2(BASE/'evidence/rafie-20261031'/name,raw/name)
    (OUT/'README.md').write_text(GUIDE,encoding='utf-8',newline='\n')
    (BASE/'documentation/REPORT-EVIDENCE.md').write_text(GUIDE,encoding='utf-8',newline='\n')
    files=sorted(p for p in OUT.rglob('*') if p.is_file() and p.name not in ['SHA256SUMS.txt'] and p.suffix!='.zip')
    checks=['%s  %s'%(hashlib.sha256(p.read_bytes()).hexdigest(),p.relative_to(OUT).as_posix()) for p in files]
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n',encoding='utf-8',newline='\n')
    archive=OUT.parent/(OUT.name+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file():z.write(p,OUT.name+'/'+p.relative_to(OUT).as_posix())
    print(json.dumps({'directory':str(OUT),'archive':str(archive),'evidenceFiles':len(files)+1,'savedScreenshots':len(list((OUT/'screenshots').glob('*.png')))}))
if __name__=='__main__':main()
