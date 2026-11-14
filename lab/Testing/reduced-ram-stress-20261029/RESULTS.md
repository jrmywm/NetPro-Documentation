# Metode dan hasil: pengujian intensif NetPro 11 GiB

Tanggal: 29 Oktober 2026 (Asia/Taipei).
## Metode
Enam VM berjalan: Management 4 GiB; NPB dan Policy Server masing-masing 2 GiB dengan pool hugepage 1 GiB; Virtual TAP, Gateway, dan Client masing-masing 1 GiB. Packet Generator dan VM Kafka/Frontend lama tetap mati.
Load mengirim request HTTP dan TLS 1.2 ke server lokal melalui Virtual TAP dengan mirroring aktif. Sepuluh tahap 30 detik memakai concurrency 1/4/8/16/32, disusul enam tahap HTTPS c16 selama 30 detik per tahap. Ada pemeriksaan kesehatan singkat antar-tahap. Setiap respons harus HTTP 200 dan cocok hash isinya.
Concurrent blocking diuji terpisah: 32 koneksi TLS baru per fase deny/allow pada concurrency 4/8/16. Rule SNI sementara dibuat melalui backend/Kafka, lalu dihapus. RST pada capture client dan keberhasilan allow diperiksa. Workflow memverifikasi baseline dan membersihkan state miliknya.
Resource keenam VM direkam sekitar tiap detik; API diprobe sekitar tiap lima detik. Hasil mentah dibaca ulang, termasuk swap baseline dan counter paging.

## Hasil fungsi
| Pengujian | Hasil |
|---|---|
| Load HTTP/HTTPS, seluruh 16 tahap | 43992/43992 berhasil; nol request gagal |
| Concurrent TLS deny | 96/96 sesuai harapan; 96 RST menuju client |
| Concurrent TLS allow setelah delete | 96/96 HTTP 200; nol RST menuju client |
| Capture blocking | Nol kernel capture drops pada keenam fase |
| Probe API Management selama load | 103/103 HTTP 200 |
| Probe API selama blocking | 14/14 HTTP 200 |
| OOM kill | Tidak ada penambahan pada keenam VM di kedua workload |
| Swap-out baru | Nol pada keenam VM di kedua workload |

## Resource minimum yang diamati
| VM | RAM dialokasikan | Minimum available MiB (kedua workload) | Swap maksimum MiB |
|---|---:|---:|---:|
| management | 4 GiB | 2687.7 | 0.00 |
| npb | 2 GiB | 467.5 | 0.00 |
| policy | 2 GiB | 371.1 | 0.00 |
| tap | 1 GiB | 488.8 | 0.00 |
| gateway | 1 GiB | 448.9 | 3.80 |
| client | 1 GiB | 462.2 | 25.04 |

## Catatan penting: tidak benar-benar swap-free
Sebelum load dimulai, Gateway sudah memakai sekitar 3,80 MiB swap dan Client 25,04 MiB. Angka itu tidak bertambah dan counter swap-out tidak berubah selama kedua workload. Pada load, Client membaca tujuh halaman dari swap; ini bukan nol aktivitas paging.
Pemeriksaan tambahan yang mensyaratkan swap absolut nol tetap tidak terpenuhi: accepted=false pada summary load dan status=failed pada wrapper monitoring blocking. Flag asli tidak dihapus atau diganti. Seluruh request dan capture blocking lulus; batas runtime minimum available 128 MiB dan swap <=64 MiB juga terpenuhi. Kegagalan strict flag tidak boleh disembunyikan sebagai hasil all-pass tanpa keterangan.

## Latensi dan interpretasi
Pada concurrency 32, p95 HTTP sekitar 369,91 ms dan HTTPS sekitar 524,04 ms. Throughput tidak terus naik ketika concurrency ditambah. CPU Client mencapai 100% pada sampel, sedangkan minimum available Client masih sekitar 462 MiB pada load. Ini mendukung pemeriksaan CPU/generator sebagai kemungkinan pembatas, bukan bukti penyebab tunggal atau kapasitas maksimum NPB.
Hasil mendukung penggunaan 1 GiB untuk TAP/Gateway/Client pada workload lab ini. Tidak membuktikan stabilitas berjam-jam, batas throughput maksimum, atau kebutuhan RAM produksi.

## Postflight dan batas pengukuran
Pemeriksaan akhir menemukan layanan utama tetap aktif, SQLite integrity ok dengan empat ID baseline, serta tidak ada listener/state sementara pengujian yang tersisa pada gateway. Telemetry pada window load menunjukkan aktivitas klasifikasi dan forwarding NPB/Policy Server.
Jumlah counter telemetry tidak persis sama dengan request client: pada window SQL yang dipilih NPB mencatat HTTP 17.756/TLS 26.205 dan PS HTTP 17.758/TLS 26.202. Window/agregasi/protokol penghitung tidak dikorelasikan per-flow; selisih ini tidak disimpulkan sebagai zero loss maupun langsung sebagai kehilangan paket. Tidak ada klaim mirror lossless dari data ini.
Pengujian tidak mencakup QUIC/HTTP3, wire-rate maksimum, physical fail-open, seluruh interaksi browser, maupun alur lengkap alert Zabbix. Server Python dan proses curl baru per request ikut memengaruhi waktu respons.

## Bukti
- [Load: metode, tabel tahap dan resource](evidence/reduced-ram-stress-20261029T125749Z/METHODS-AND-RESULTS.md).
- [Summary load dan flag strict](evidence/reduced-ram-stress-20261029T125749Z/REDUCED-RAM-SUMMARY.json).
- [Concurrent blocking](evidence/rst-stress-20261029T130711Z/RESULTS.md).
- [Monitoring blocking dan flag asli](evidence/blocking-monitor-20261029T130703Z/summary.json).
- [Postflight dan telemetry](evidence/reduced-ram-stress-20261029T125749Z/POSTFLIGHT.json).
- [Penilaian fungsi/resource terpisah](ASSESSMENT.json).
Raw JSONL, PCAP, snapshot dan bukti cleanup tetap disimpan. Lihat README untuk cara mengulang.
