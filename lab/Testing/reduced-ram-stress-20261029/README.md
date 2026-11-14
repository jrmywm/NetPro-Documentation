# Pengujian lebih intensif: NetPro 6 VM / 11 GiB

Tanggal: 29 Oktober 2026, Asia/Taipei. Semua target adalah server lokal lab. Pengujian ini mengevaluasi konfigurasi RAM rendah, bukan penggunaan pada jaringan produksi atau reproduksi performa skripsi.

## Metode

1. Inventori enam VM dan host diperiksa sebelum load.
2. HTTP dan TLS 1.2: concurrency 1/4/8/16/32, masing-masing 30 detik per protokol.
3. Soak TLS: enam tahap 30 detik pada concurrency 16. Ada jeda pemeriksaan kesehatan singkat antar-tahap; bukan soak tanpa jeda.
4. Isi setiap respons diverifikasi SHA-256; sukses mensyaratkan curl exit 0, HTTP 200, dan isi benar.
5. Memori, swap, CPU, counter interface, dan counter OOM pada keenam VM direkam sekitar tiap detik. API Management diprobe sekitar setiap lima detik. Controller memeriksa kesehatan setelah setiap tahap, bukan watchdog real-time pada setiap paket.
6. Concurrent deny–allow dijalankan terpisah: 32 koneksi per fase pada concurrency 4/8/16; capture RST diperiksa. Monitoring keenam VM diulang pada fase ini.
7. Layanan, database, telemetry mirror/NPB/PS dan cleanup listener diperiksa sesudahnya.

Tidak ada perubahan permanen aturan blocking. Workflow deny–allow hanya membuat dan menghapus aturan miliknya, dengan baseline ID yang dijaga. Listener dan monitor sementara memakai unit unik dengan batas waktu dan cleanup. Jangan menghapus aturan pengguna untuk memaksa guard lulus jika baseline telah berubah.

## Hasil dan bukti

Ringkasan utama: [RESULTS.md](RESULTS.md). Semua 43.992 request load serta 96 deny/96 allow lulus. Flag strict swap-absolut-nol tidak terpenuhi karena swap Gateway/Client sudah ada sebelum workload; tidak ada swap-out baru. Flag asli tetap disimpan, bukan diganti menjadi all-pass.

Lihat subfolder `evidence/`:

- `reduced-ram-stress-*/METHODS-AND-RESULTS.md`: tabel tahap dan resource.
- `reduced-ram-stress-*/REDUCED-RAM-SUMMARY.json`: penerimaan dan pemeriksaan ulang file raw.
- `reduced-ram-stress-*/POSTFLIGHT.json`: verifikasi akhir dan telemetry window.
- `rst-stress-*/RESULTS.md`: hasil concurrent deny–allow.
- `blocking-monitor-*/summary.json`: resource selama blocking.
- JSONL, PCAP, snapshot sebelum/sesudah dan SHA terkait tetap dipertahankan.

Ringkasan hasil tidak boleh ditafsirkan sebagai dukungan 1 GiB untuk semua beban. Kenaikan latensi atau throughput yang tidak lagi meningkat dapat disebabkan batas client/server Python, proses curl per request, CPU DPDK polling, atau penjadwalan host. Tidak menguji wire-rate maksimum, QUIC/HTTP3, seluruh interaksi frontend, kegagalan fisik TAP, atau seluruh integrasi Zabbix.

## Mengulang

Jalankan hanya saat tidak ada demo/pengujian lain memakai endpoint atau rule yang sama. Keenam VM harus aktif, broker/Frontend lama dan Packet Generator tetap mati. Python/Paramiko serta helper SSH terverifikasi yang sudah ada diperlukan.

```powershell
python -u .\run_stress.py
```

Setelah selesai, pilih direktori run yang baru dan ringkas hasilnya:

```powershell
python .\summarize.py .\evidence\reduced-ram-stress-TIMESTAMP
```

Uji blocking dijalankan setelah load selesai, bukan bersamaan:

```powershell
python -u .\run_blocking.py
```

Kemudian gunakan direktori load yang sama:

```powershell
python .\postflight.py .\evidence\reduced-ram-stress-TIMESTAMP
```

Ganti `TIMESTAMP` dengan nama aktual. Runner load memiliki guard dan cleanup, tetapi exit process saja tidak cukup untuk menerima hasil: periksa `status`, seluruh tahap, raw counts, resource, serta recovery. Password tidak disimpan di bukti. Sertifikat self-signed hanya dilewati untuk endpoint lab pada perintah pengujian.
