"""Summarize the current bounded load run without changing raw evidence."""
from pathlib import Path
import argparse,json,statistics
p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
root=a.run
summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
stages=summary['stages'];resources={};raw_checks=[]
for s in stages:
    label=s.get('phase',s['stage']);f=root/('stage-'+label+'.jsonl')
    raw=[json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
    raw_checks.append({'phase':label,'rows_match':len(raw)==s['requests'],
                       'success_match':sum(r['body_ok'] for r in raw)==s['success']})
for role in summary['hosts']:
    f=root/(role+'-resource.jsonl')
    if not f.exists():resources[role]={'missing':True};continue
    rows=[json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
    cpus=[r['cpu_busy_pct'] for r in rows if r.get('cpu_busy_pct') is not None]
    probes=[r['management_api'] for r in rows if 'management_api' in r]
    resources[role]={
        'samples':len(rows),'duration_s':rows[-1]['utc']-rows[0]['utc'],
        'min_available_mib':min(r['memory_kib']['MemAvailable'] for r in rows)/1024,
        'max_swap_used_mib':max(r['memory_kib']['SwapTotal']-r['memory_kib']['SwapFree'] for r in rows)/1024,
        'initial_swap_used_mib':(rows[0]['memory_kib']['SwapTotal']-rows[0]['memory_kib']['SwapFree'])/1024,
        'swap_out_pages_delta':rows[-1]['vmstat']['pswpout']-rows[0]['vmstat']['pswpout'],
        'swap_in_pages_delta':rows[-1]['vmstat']['pswpin']-rows[0]['vmstat']['pswpin'],
        'oom_kill_delta':rows[-1]['vmstat']['oom_kill']-rows[0]['vmstat']['oom_kill'],
        'cpu_mean_pct':statistics.mean(cpus) if cpus else None,
        'cpu_max_pct':max(cpus) if cpus else None,
        'api_probes':len(probes),'api_success':sum(x['exit']==0 and x['http']=='200' for x in probes),
    }
total=sum(s['requests'] for s in stages);success=sum(s['success'] for s in stages)
data={'run':summary['run'],'status':summary['status'],'stages_completed':len(stages),'stages_planned':16,
      'requests':total,'success':success,'failure':total-success,'resources':resources,'raw_checks':raw_checks}
data['accepted']=summary['status']=='completed' and len(stages)==16 and total==success and all(
    x['rows_match'] and x['success_match'] for x in raw_checks) and all(
    not r.get('missing') and r['oom_kill_delta']==0 and r['max_swap_used_mib']==0 and r['min_available_mib']>=128 for r in resources.values())
data['accepted']=data['accepted'] and all(r['api_success']==r['api_probes'] for r in resources.values())
data['accepted']=data['accepted'] and resources.get('management',{}).get('api_probes',0)>0
data['functional_pass']=summary['status']=='completed' and len(stages)==16 and total==success and all(x['rows_match'] and x['success_match'] for x in raw_checks)
data['runtime_resource_bounds_pass']=all(not r.get('missing') and r['oom_kill_delta']==0 and r['min_available_mib']>=128 and r['max_swap_used_mib']<=64 and r['api_success']==r['api_probes'] for r in resources.values())
data['no_new_swap_out']=all(not r.get('missing') and r['swap_out_pages_delta']==0 for r in resources.values())
(root/'REDUCED-RAM-SUMMARY.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
lines=['# Pengujian intensif terbatas NetPro — konfigurasi 11 GiB', '',
       '## Metode',
       'Enam VM: Management 4 GiB, NPB/Policy masing-masing 2 GiB dengan hugepage 1 GiB, TAP/Gateway/Client masing-masing 1 GiB. Tidak memakai Packet Generator atau website publik.',
       'Sepuluh tahap HTTP/TLS 1.2 pada concurrency 1/4/8/16/32, masing-masing 30 detik, kemudian enam tahap HTTPS c16 masing-masing 30 detik. Setiap request memakai proses curl baru dan memeriksa HTTP 200 serta SHA-256 isi respons. Server uji Python memakai port lokal 18080/18443.',
       'Resource keenam VM disampel sekitar tiap detik. API Management diperiksa sekitar tiap lima detik. Guard setelah tahap menghentikan kenaikan beban jika request gagal, guest MemAvailable <128 MiB, swap >64 MiB, host available RAM <512 MiB, atau service utama tidak aktif.',
       '', '## Hasil',f'Status: {summary["status"]}; tahap selesai {len(stages)}/16. Request berhasil {success}/{total}.',
       '| Fase | Concurrency | Berhasil/percobaan | Request/detik | p95 ms | p99 ms |',
       '|---|---:|---:|---:|---:|---:|']
for s in stages:
    lines.append(f'| {s.get("phase",s["stage"])} | {s["concurrency"]} | {s["success"]}/{s["requests"]} | {s["completed_rps"]:.2f} | {s["p95_ms"] or 0:.2f} | {s["p99_ms"] or 0:.2f} |')
lines += ['', '## Memori dan kondisi VM', '| VM | Sampel | Minimum available MiB | Maksimum swap MiB | OOM kill delta | CPU rata-rata % |', '|---|---:|---:|---:|---:|---:|']
for role,r in resources.items():
    if r.get('missing'):lines.append(f'| {role} | Tidak tersedia | — | — | — | — |');continue
    lines.append(f'| {role} | {r["samples"]} | {r["min_available_mib"]:.1f} | {r["max_swap_used_mib"]:.1f} | {r["oom_kill_delta"]} | {r["cpu_mean_pct"] or 0:.1f} |')
r=resources.get('management',{})
lines += ['',f'API Management: {r.get("api_success",0)}/{r.get("api_probes",0)} probe menghasilkan HTTP 200.',
          '', '## Batas kesimpulan',
          'Ini pengujian lebih panjang untuk profil RAM rendah, bukan pengukuran kapasitas maksimum/wire-rate atau jaminan operasi produksi. Curl-per-request, server Python, dan resource host bersama memengaruhi throughput/latensi. CPU DPDK dapat tinggi akibat polling.',
          'Load allow ini terpisah dari pengujian concurrent TLS deny–allow. Tidak menguji QUIC gate/Close, HTTP/3, bandwidth saturasi, hardware fail-open, atau seluruh fitur frontend/Zabbix.',
          'File raw stage, resource.jsonl, snapshot sebelum/sesudah, recovery, dan summary dipertahankan. Semua tahap dibaca ulang untuk mencocokkan jumlah hasil raw dengan ringkasannya.',
          f'Kriteria penerimaan otomatis terpenuhi: {data["accepted"]}.']
lines += ['', '## Catatan swap dan kriteria penerimaan',
          f'Fungsi/request: {data["functional_pass"]}. Batas resource runtime (minimum available 128 MiB, swap <=64 MiB, tanpa OOM dan probe API berhasil): {data["runtime_resource_bounds_pass"]}. Tidak ada swap-out baru: {data["no_new_swap_out"]}.',
          'Field accepted memakai pemeriksaan tambahan yang lebih ketat, yaitu swap absolut nol. Jika swap sudah terpakai sebelum load, accepted tetap false walaupun fungsi lulus dan penggunaan swap tidak bertambah. Nilai ini tidak diubah menjadi lulus dengan mengabaikan baseline.',
          '| VM | Swap awal MiB | Swap maksimum MiB | Halaman swap-out baru | Halaman swap-in |', '|---|---:|---:|---:|---:|']
for role,r in resources.items():
    if not r.get('missing'):lines.append(f'| {role} | {r["initial_swap_used_mib"]:.2f} | {r["max_swap_used_mib"]:.2f} | {r["swap_out_pages_delta"]} | {r["swap_in_pages_delta"]} |')
(root/'METHODS-AND-RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in data.items() if k not in ('raw_checks','resources')},indent=2))
print(json.dumps(resources,indent=2))
