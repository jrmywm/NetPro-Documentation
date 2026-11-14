"""Create an evidence-linked assessment; retain original failed strict flags."""
from pathlib import Path
import json
base=Path(__file__).resolve().parent
evidence=base/'evidence'
load=sorted(evidence.glob('reduced-ram-stress-*'))[-1]
blocking=sorted(evidence.glob('blocking-monitor-*'))[-1]
ld=json.loads((load/'REDUCED-RAM-SUMMARY.json').read_text(encoding='utf-8'))
bd=json.loads((blocking/'summary.json').read_text(encoding='utf-8'))
rst=Path(bd['rst_evidence'])
cases=[json.loads(f.read_text(encoding='utf-8')) for f in sorted(rst.glob('c*-*.json'))]
functional=len(cases)==6 and all(r['passed'] and r['expected']==r['attempted']==32 for r in cases)
resources={}
for role in bd['resources']:
 rows=[json.loads(l) for l in (blocking/(role+'-resource.jsonl')).read_text(encoding='utf-8').splitlines() if l.strip()]
 r=dict(bd['resources'][role]);r['initial_swap_mib']=(rows[0]['memory_kib']['SwapTotal']-rows[0]['memory_kib']['SwapFree'])/1024
 r['swap_out_pages_delta']=rows[-1]['vmstat']['pswpout']-rows[0]['vmstat']['pswpout']
 resources[role]=r
runtime=all(r['min_available_mib']>=128 and r['max_swap_mib']<=64 and r['oom_delta']==0 and r['api_success']==r['api_total'] for r in resources.values())
assessment={'load_functional_pass':ld['functional_pass'],'load_runtime_resource_bounds_pass':ld['runtime_resource_bounds_pass'],
 'load_original_strict_zero_swap_accepted':ld['accepted'],'blocking_functional_pass':functional,
 'blocking_runtime_resource_bounds_pass':runtime,'blocking_original_status':bd['status'],
 'blocking_no_new_swap_out':all(r['swap_out_pages_delta']==0 for r in resources.values()),
 'blocking_resources':resources,'note':'Original zero-swap flags retained; pre-existing Client/Gateway swap was not newly written during either workload.'}
(base/'ASSESSMENT.json').write_text(json.dumps(assessment,indent=2),encoding='utf-8')
lines=['# Metode dan hasil: pengujian intensif NetPro 11 GiB', '', 'Tanggal: 29 Oktober 2026 (Asia/Taipei).',
 '## Metode',
 'Enam VM berjalan: Management 4 GiB; NPB dan Policy Server masing-masing 2 GiB dengan pool hugepage 1 GiB; Virtual TAP, Gateway, dan Client masing-masing 1 GiB. Packet Generator dan VM Kafka/Frontend lama tetap mati.',
 'Load mengirim request HTTP dan TLS 1.2 ke server lokal melalui Virtual TAP dengan mirroring aktif. Sepuluh tahap 30 detik memakai concurrency 1/4/8/16/32, disusul enam tahap HTTPS c16 selama 30 detik per tahap. Ada pemeriksaan kesehatan singkat antar-tahap. Setiap respons harus HTTP 200 dan cocok hash isinya.',
 'Concurrent blocking diuji terpisah: 32 koneksi TLS baru per fase deny/allow pada concurrency 4/8/16. Rule SNI sementara dibuat melalui backend/Kafka, lalu dihapus. RST pada capture client dan keberhasilan allow diperiksa. Workflow memverifikasi baseline dan membersihkan state miliknya.',
 'Resource keenam VM direkam sekitar tiap detik; API diprobe sekitar tiap lima detik. Hasil mentah dibaca ulang, termasuk swap baseline dan counter paging.',
 '', '## Hasil fungsi', '| Pengujian | Hasil |', '|---|---|',
 f'| Load HTTP/HTTPS, seluruh 16 tahap | {ld["success"]}/{ld["requests"]} berhasil; nol request gagal |',
 '| Concurrent TLS deny | 96/96 sesuai harapan; 96 RST menuju client |',
 '| Concurrent TLS allow setelah delete | 96/96 HTTP 200; nol RST menuju client |',
 '| Capture blocking | Nol kernel capture drops pada keenam fase |',
 '| Probe API Management selama load | 103/103 HTTP 200 |',
 '| Probe API selama blocking | 14/14 HTTP 200 |',
 '| OOM kill | Tidak ada penambahan pada keenam VM di kedua workload |',
 '| Swap-out baru | Nol pada keenam VM di kedua workload |',
 '', '## Resource minimum yang diamati', '| VM | RAM dialokasikan | Minimum available MiB (kedua workload) | Swap maksimum MiB |', '|---|---:|---:|---:|']
alloc={'management':4,'npb':2,'policy':2,'tap':1,'gateway':1,'client':1}
for role in alloc:
 l=ld['resources'][role];r=resources[role]
 lines.append(f'| {role} | {alloc[role]} GiB | {min(l["min_available_mib"],r["min_available_mib"]):.1f} | {max(l["max_swap_used_mib"],r["max_swap_mib"]):.2f} |')
lines += ['', '## Catatan penting: tidak benar-benar swap-free',
 'Sebelum load dimulai, Gateway sudah memakai sekitar 3,80 MiB swap dan Client 25,04 MiB. Angka itu tidak bertambah dan counter swap-out tidak berubah selama kedua workload. Pada load, Client membaca tujuh halaman dari swap; ini bukan nol aktivitas paging.',
 'Pemeriksaan tambahan yang mensyaratkan swap absolut nol tetap tidak terpenuhi: accepted=false pada summary load dan status=failed pada wrapper monitoring blocking. Flag asli tidak dihapus atau diganti. Seluruh request dan capture blocking lulus; batas runtime minimum available 128 MiB dan swap <=64 MiB juga terpenuhi. Kegagalan strict flag tidak boleh disembunyikan sebagai hasil all-pass tanpa keterangan.',
 '', '## Latensi dan interpretasi',
 'Pada concurrency 32, p95 HTTP sekitar 369,91 ms dan HTTPS sekitar 524,04 ms. Throughput tidak terus naik ketika concurrency ditambah. CPU Client mencapai 100% pada sampel, sedangkan minimum available Client masih sekitar 462 MiB pada load. Ini mendukung pemeriksaan CPU/generator sebagai kemungkinan pembatas, bukan bukti penyebab tunggal atau kapasitas maksimum NPB.',
 'Hasil mendukung penggunaan 1 GiB untuk TAP/Gateway/Client pada workload lab ini. Tidak membuktikan stabilitas berjam-jam, batas throughput maksimum, atau kebutuhan RAM produksi.',
 '', '## Postflight dan batas pengukuran',
 'Pemeriksaan akhir menemukan layanan utama tetap aktif, SQLite integrity ok dengan empat ID baseline, serta tidak ada listener/state sementara pengujian yang tersisa pada gateway. Telemetry pada window load menunjukkan aktivitas klasifikasi dan forwarding NPB/Policy Server.',
 'Jumlah counter telemetry tidak persis sama dengan request client: pada window SQL yang dipilih NPB mencatat HTTP 17.756/TLS 26.205 dan PS HTTP 17.758/TLS 26.202. Window/agregasi/protokol penghitung tidak dikorelasikan per-flow; selisih ini tidak disimpulkan sebagai zero loss maupun langsung sebagai kehilangan paket. Tidak ada klaim mirror lossless dari data ini.',
 'Pengujian tidak mencakup QUIC/HTTP3, wire-rate maksimum, physical fail-open, seluruh interaksi browser, maupun alur lengkap alert Zabbix. Server Python dan proses curl baru per request ikut memengaruhi waktu respons.',
 '', '## Bukti',
 f'- [Load: metode, tabel tahap dan resource](evidence/{load.name}/METHODS-AND-RESULTS.md).',
 f'- [Summary load dan flag strict](evidence/{load.name}/REDUCED-RAM-SUMMARY.json).',
 f'- [Concurrent blocking](evidence/{rst.name}/RESULTS.md).',
 f'- [Monitoring blocking dan flag asli](evidence/{blocking.name}/summary.json).',
 f'- [Postflight dan telemetry](evidence/{load.name}/POSTFLIGHT.json).',
 '- [Penilaian fungsi/resource terpisah](ASSESSMENT.json).',
 'Raw JSONL, PCAP, snapshot dan bukti cleanup tetap disimpan. Lihat README untuk cara mengulang.']
(base/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in assessment.items() if k!='blocking_resources'},indent=2))
