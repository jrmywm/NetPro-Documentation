# Metode dan Hasil Pengujian NetPro

Dokumen ini merangkum pengujian yang telah dicatat hingga 13 Oktober 2026. Tidak ada pengujian baru dilakukan saat penyusunan.

## 1. Virtual TAP: forwarding dan mirroring

### Metode

Virtual TAP menggunakan Linux software bridge pada VM Ubuntu. Trafik asli diteruskan dari client ke gateway, sedangkan salinannya dikirim melalui interface monitor ke NPB.

Pengujian dilakukan dalam tiga kondisi: monitor aktif, monitor dimatikan, lalu monitor diaktifkan kembali. Setiap kondisi menjalankan dua request HTTP dan dua request TLS 1.2. Interface bridge tetap aktif. Hasil client dan telemetry NPB diperiksa.

### Hasil

| Kondisi monitor | Request berhasil |
|---|---:|
| Aktif sebelum pengujian | 4/4 |
| Dimatikan | 4/4 |
| Diaktifkan kembali | 4/4 |
| **Total** | **12/12** |

Seluruh request menghasilkan HTTP 200. Telemetry NPB menunjukkan aktivitas sebelum dan sesudah monitor dimatikan, serta tidak menunjukkan input pada interval monitor mati.

Hasil ini mendukung independensi forwarding terhadap monitor-port saat bridge tetap berjalan. Pengujian tidak mematikan VM TAP dan tidak membuktikan fail-open fisik. Tidak ada PCAP pada run ini.

## 2. Beban HTTP dan HTTPS

### Metode

Client mengirim request melalui Virtual TAP menuju server lokal. HTTP dan HTTPS diuji terpisah dengan concurrency 1, 4, 8, dan 16. Durasi yang diminta adalah 10 detik per tahap. Jumlah request, keberhasilan, throughput, dan waktu respons dicatat.

### Hasil

| Protokol | Concurrency | Berhasil/percobaan | Request/detik | p95 waktu respons (ms) |
|---|---:|---:|---:|---:|
| HTTP | 1 | 546/546 | 54,56 | 25,28 |
| HTTP | 4 | 1.195/1.195 | 119,20 | 48,49 |
| HTTP | 8 | 1.384/1.384 | 137,76 | 83,98 |
| HTTP | 16 | 1.467/1.467 | 146,01 | 150,34 |
| HTTPS | 1 | 366/366 | 36,50 | 37,51 |
| HTTPS | 4 | 873/873 | 86,99 | 59,73 |
| HTTPS | 8 | 992/992 | 98,48 | 107,23 |
| HTTPS | 16 | 1.009/1.009 | 100,10 | 217,46 |

Total **7.832/7.832 request berhasil** pada run `tap-stress-20261010T131056Z`. Pengujian ini menilai akses/forwarding pada workload tersebut, bukan kapasitas maksimum atau pemblokiran RST.

## 3. Pemblokiran TCP/TLS: deny–allow

### Metode

Trafik client melewati Virtual TAP menuju server TLS lokal. Salinan dikirim ke NPB dan Policy Server. Paket RST dikirim melalui jalur NetPro-RST.

Aturan domain `netpro-tap.test` memakai dummy IP yang berbeda dari server untuk menguji pencocokan SNI. Setiap concurrency 4, 8, dan 16 menjalankan 32 koneksi TLS 1.2 baru pada fase deny dan 32 pada fase allow setelah aturan dihapus. Terdapat jeda satu detik antar-burst; reset policing tetap aktif.

Deny dinilai benar jika curl mengalami reset dengan HTTP 000 dan RST menuju client tertangkap untuk setiap percobaan. Allow harus menghasilkan HTTP 200 tanpa RST menuju client pada capture fase tersebut.

### Hasil

| Concurrency | Deny sesuai harapan | Allow sesuai harapan | RST pada fase deny | Capture kernel drops |
|---|---:|---:|---:|---:|
| 4 | 32/32 | 32/32 | 32 | 0 |
| 8 | 32/32 | 32/32 | 32 | 0 |
| 16 | 32/32 | 32/32 | 32 | 0 |
| **Total** | **96/96** | **96/96** | **96** | **0** |

Tidak ada RST menuju client pada fase allow. Hasil berlaku untuk koneksi baru dan burst terkontrol yang diuji, bukan seluruh variasi TLS atau kapasitas reset tanpa batas. Pengujian ini terpisah dari pengujian beban 7.832 request.

## 4. TLS ClientHello tersegmentasi

### Metode

Client mengakses server TLS lokal dengan MTU kecil dan segmentation offload dinonaktifkan. GRO pada interface capture gateway juga dinonaktifkan untuk mengamati segmen.

NPB melacak aliran dan meneruskan segmen lanjutan. Policy Server menyusun kembali ClientHello untuk membaca SNI. Aturan domain diuji dengan IP yang tidak sama dengan IP server, kemudian aturan dihapus dan akses diulang.

### Hasil

Capture menunjukkan ClientHello terbagi menjadi tiga payload TCP: **76, 76, dan 75 byte**.

| Kondisi | Hasil client |
|---|---|
| Aturan domain aktif | Connection reset; curl exit 35; HTTP 000 |
| Aturan dihapus | curl exit 0; HTTP 200 |

Hasil mendukung pemrosesan ClientHello tersegmentasi pada kasus lokal tersebut. Ini bukan dekripsi isi HTTPS atau bukti dukungan seluruh kemungkinan reassembly TCP.

## 5. SNMP: trap domain, summary, dan polling

### Metode

Fixture paket HTTP dikirim melalui client → Virtual TAP → NPB → Policy Server candidate. Policy Server mengirim trap ke receiver Net-SNMP pada Backend VM.

Pengujian terdiri dari 10 paket awal, lima trial masing-masing 1.000 paket, dan satu trial 10.000 paket. Trafik diatur sekitar 100 paket/detik. Jumlah trap diterima dan duplikat diperiksa. Summary memakai interval 120 detik. Polling SNMP dilakukan pada pengujian terpisah.

### Hasil

| Pengujian | Hasil |
|---|---|
| 10 paket awal | 10/10 trap diterima |
| Lima trial × 1.000 paket | 5.000/5.000 trap diterima |
| Satu trial × 10.000 paket | 10.000/10.000 trap diterima |
| **Total trap domain** | **15.010/15.010** |
| Kehilangan/duplikat trap pada run | 0 / 0 |
| Summary pertama | Agent uptime sekitar 121,07 detik |
| Polling terpisah | 10 respons GET |

Fixture tidak membentuk sesi TCP lengkap, sehingga hasil trap bukan bukti 15.010 koneksi berhasil diblokir. Pengirim trap menggunakan implementasi asynchronous yang diadaptasi, bukan metode shell-per-trap identik dengan skripsi. Metrik polling mencakup kondisi VM, bukan otomatis proses Policy Server saja.

Zabbix telah dipasang dan dikonfigurasi, tetapi alur lengkap kejadian blocking sampai tersimpan dan tampil pada Zabbix belum terverifikasi.

## 6. QUIC: injeksi CONNECTION_CLOSE

### Metode

Client curl dengan dukungan HTTP/3 mengakses server Caddy lokal. Aturan SNI diuji tanpa mengandalkan kecocokan IP server. TCP fallback dibatasi pada skenario uji agar tidak menyamarkan hasil QUIC.

Dua konfigurasi dibandingkan:

- **Jalur lengkap:** salinan melalui TAP → NPB → Policy Server; Close kembali melalui jalur NetPro-RST dan gateway.
- **Jalur langsung:** pengamatan dan injeksi Policy Server sementara dihubungkan ke segmen sisi client, tanpa jalur observasi NPB dan redirection gateway.

Hasil request dan capture client diperiksa. Konfigurasi awal dipulihkan setelah pengujian.

### Hasil

| Konfigurasi | Request deny | Berhasil ditolak | Tetap berhasil mengakses |
|---|---:|---:|---:|
| Jalur lengkap | 5 | 0 | 5 |
| Jalur langsung, run pertama | 5 | 5 | 0 |
| Jalur langsung, run kedua | 5 | 2 | 3 |
| **Gabungan jalur langsung** | **10** | **7** | **3** |

Seluruh 20 request allow kontrol pada dua run candidate jalur langsung berhasil. Rata-rata Initial-to-Close pada capture client sekitar **1,86 ms** pada jalur lengkap dan **0,42/0,39 ms** pada kedua run langsung.

Paket Close terautentikasi teramati, tetapi pemblokiran request belum konsisten. Tidak semua Close terbukti selalu terlambat. Perubahan kedua jalur sekaligus tidak mengisolasi penyebab tunggal. Jumlah paket akibat retry bukan jumlah request independen, dan hasil ini tidak langsung sebanding dengan metrik paket pada skripsi.

## 7. QUIC: prototipe inline gate

### Metode

Gate menahan Initial koneksi QUIC baru sampai keputusan Policy Server diterima. ALLOW meneruskan paket; DENY membuang paket. Injeksi Close dinonaktifkan untuk mengisolasi hasil gate.

Pengujian memakai QUIC v1/IPv4 dari client `192.168.80.29` menuju Caddy `192.168.80.28`, UDP/443, domain `mysite.local`. Setiap fase menjalankan 20 request. Hasil client, catatan Caddy, capture mirror, dan capture sisi origin dibandingkan.

### Hasil

| Fase | Hasil |
|---|---|
| Tanpa queue, allow | 20/20 HTTP 200 |
| Gate aktif, allow | 20/20 HTTP 200; 20 catatan Caddy |
| Aturan domain lain dengan IP server sama | 20/20 HTTP 200 |
| Aturan domain yang sesuai | 20/20 timeout curl 28; nol catatan Caddy |
| Setelah aturan dihapus | 20/20 HTTP 200 |

Semua 40 datagram deny akibat 20 request dan retry ditemukan pada capture mirror; tidak ada kecocokan pada sisi origin. Gate timeout/unsupported outcomes nol.

Dari 180 sampel, median waktu tunggu keputusan **0,79 ms** dan p95 **1,66 ms**. Perbandingan allow terbatas dengan/tanpa gate pada concurrency 1/4/8/16 menghasilkan **160/160 request berhasil**.

Gate adalah pengembangan inline tambahan, bukan passive mirroring atau mekanisme asli injeksi. Setelah eksperimen, gate dinonaktifkan dan baseline dipulihkan. Hasil belum membuktikan kapasitas produksi, seluruh variasi QUIC, atau pencabutan akses koneksi yang sudah berjalan.

## 8. Regresi NPB dan Policy Server

### Metode

Regresi berarti menguji ulang fungsi lama setelah perubahan kode atau topologi. Setelah eksperimen jalur langsung QUIC, adapter dan layanan dikembalikan ke baseline. Pengujian TLS deny–allow diulang melalui jalur sistem. Hash binary, integritas SQLite, ID aturan baseline, dan segmen adapter diperiksa.

### Hasil

| Pemeriksaan setelah pemulihan | Hasil |
|---|---|
| TLS deny | 20/20 reset sesuai harapan |
| TLS allow | 20/20 HTTP 200 |
| Integritas SQLite | OK |
| Binary dan adapter | Baseline diverifikasi |

Hasil mendukung bahwa fungsi TCP/TLS tetap bekerja setelah eksperimen QUIC pada saat verifikasi. Pengujian jalur lengkap ini tidak mengisolasi setiap fungsi NPB secara individual dan tidak membuktikan seluruh protokol bebas regresi.

Tersedia pula harness offline untuk parser ClientHello dan tracker, dengan kasus urutan normal, retransmission, overlap, gap/out-of-order, dan sequence wrap. Harness merupakan pemeriksaan modul tanpa jaringan. Keberadaan harness bukan bukti run PASS tertentu; hasil offline tidak digabungkan dengan angka pengujian live di atas.
