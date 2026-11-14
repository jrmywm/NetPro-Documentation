# Dokumentasi Pengujian Terpadu NetPro — Kelompok 27

Tanggal kompilasi: 13 Oktober 2026. Dokumen ini menggabungkan hasil yang sudah dicatat; penyusunan dokumen ini tidak menjalankan pengujian baru. Bukti asli tidak diubah. Kondisi setelah pengujian historis bukan jaminan kondisi layanan saat ini.

## 1. Tujuan dan cara membaca hasil

Pengujian memisahkan forwarding/mirroring, pemblokiran TCP/TLS, pelaporan SNMP, mekanisme QUIC, dan regresi. Keberhasilan satu bagian tidak membuktikan seluruh NetPro selesai atau performanya identik dengan skripsi.

- Paket: unit data jaringan. Request: permintaan aplikasi, yang dapat melibatkan banyak paket dan retry.
- Allow: akses diizinkan. Deny: akses ditolak berdasarkan aturan yang sesuai.
- Baseline: kondisi pembanding. Kontrol: kondisi untuk menguji apakah hasil benar disebabkan aturan atau mekanisme yang dimaksud.
- Regresi: pengujian ulang agar perubahan baru tidak merusak fungsi lama; bukan regresi statistik.
- End-to-end: menguji alur sampai hasil aplikasi. Offline/module test: menguji kode atau fungsi terpisah tanpa membuktikan jalur jaringan lengkap.
- Concurrency: jumlah pekerjaan bersamaan. p95: sekitar 95% nilai pengukuran berada pada atau di bawah nilai tersebut.
- HTTP 000 pada curl bukan respons HTTP server; artinya tidak ada status HTTP yang berhasil diperoleh.

## 2. Ringkasan hasil

| Bagian | Pengujian | Hasil tercatat | Batas kesimpulan |
|---|---|---|---|
| Virtual TAP | Monitor-port on, off, lalu on | 12/12 request HTTP/TLS berhasil | Monitor NIC dimatikan, bukan VM bridge atau perangkat fisik |
| Forwarding HTTP/HTTPS | Concurrency 1/4/8/16 | 7.832/7.832 request berhasil | Workload terbatas; bukan kapasitas maksimum dan bukan uji RST |
| TCP/TLS blocking | 32 deny dan 32 allow per concurrency 4/8/16 | 96/96 deny; 96/96 allow | Koneksi TLS baru pada endpoint lokal dan burst terkontrol |
| TLS tersegmentasi | ClientHello terpecah; aturan domain aktif/dihapus | Reset saat deny; HTTP 200 setelah penghapusan | Handshake lokal; bukan dekripsi isi HTTPS atau cakupan seluruh TLS |
| SNMP domain | Fixture HTTP melalui TAP/NPB/PS | 15.010/15.010 trap; tidak ada kehilangan/duplikat pada run | Fixture bukan sesi TCP browser; pengirim diadaptasi |
| SNMP summary | Interval konfigurasi 120 detik | Dispatch pertama sekitar uptime 121,07 detik | Bukan pengukuran latensi jaringan satu arah |
| SNMP polling | Backend ke agent PS | 10 respons GET pada pengujian terpisah | Metrik tingkat VM, bukan otomatis CPU proses PS saja |
| QUIC Close, jalur lengkap | 5 request deny HTTP/3 | 0/5 berhasil diblokir | Paket Close teramati tetapi request tetap berhasil |
| QUIC Close, jalur langsung | Dua run, masing-masing 5 deny | 5/5 lalu 2/5; gabungan 7/10 | Sampel kecil, belum konsisten; bukan metrik performa identik skripsi |
| QUIC gate | Allow, kontrol domain, deny, allow setelah delete | 20/20 sesuai harapan pada tiap fase | Prototipe inline untuk koneksi baru dalam lingkup lab; tidak permanen |
| Regresi TLS setelah eksperimen QUIC | Baseline dipulihkan, deny–allow diulang | 20/20 reset deny dan 20/20 HTTP 200 allow | Bukti fungsi TLS pada saat verifikasi itu, bukan seluruh fitur/protokol |

## 3. Virtual TAP: forwarding dan independensi cabang monitor

### Mekanisme

Virtual TAP adalah VM Ubuntu dengan Linux software bridge dan aturan mirroring. Bridge meneruskan trafik asli antara client dan gateway. Interface monitor mengirim salinan ke NPB. NPB meneruskan trafik relevan ke Policy Server.

### Metode yang terdokumentasi, 3 Oktober 2026

1. Monitor `ens36` aktif: dua request HTTP dan dua TLS 1.2.
2. Hanya monitor `ens36` dimatikan: dua request HTTP dan dua TLS 1.2.
3. Monitor dipulihkan: dua request HTTP dan dua TLS 1.2.
4. Interface bridge `ens34`/`ens35` tidak diubah.
5. Hasil client dibandingkan dengan telemetry NPB sebelum, selama, dan sesudah monitor mati.

Semua 12 request menghasilkan HTTP 200. Telemetry mendukung bahwa input pengamatan tidak muncul selama monitor down dan kembali muncul setelahnya. Tidak ada PCAP pada run ini.

Kesimpulan: gangguan monitor-port tidak menghentikan aplikasi pada jalur utama saat bridge tetap berjalan. Ini bukan bukti fail-open fisik atau forwarding ketika TAP VM dimatikan. Gate QUIC pada bagian 7 adalah mekanisme berbeda yang sengaja menahan trafik.

[Laporan Virtual TAP asli](C:/Users/jim/Documents/Codex/2026-09-11/referenced-chatgpt-conversation-this-is-an-2/NetPro-Documentation-current/docs/virtual-tap-independence-test-2026-10-03.md).

## 4. Beban HTTP/HTTPS dan TCP/TLS blocking

### 4.1 Beban forwarding

Run `tap-stress-20261010T131056Z` memakai tahap HTTP dan HTTPS, masing-masing concurrency 1/4/8/16 dengan durasi diminta 10 detik per tahap.

| Protokol | Concurrency | Berhasil/percobaan | Request/detik | p95 ms |
|---|---:|---:|---:|---:|
| HTTP | 1 | 546/546 | 54,56 | 25,28 |
| HTTP | 4 | 1.195/1.195 | 119,20 | 48,49 |
| HTTP | 8 | 1.384/1.384 | 137,76 | 83,98 |
| HTTP | 16 | 1.467/1.467 | 146,01 | 150,34 |
| HTTPS | 1 | 366/366 | 36,50 | 37,51 |
| HTTPS | 4 | 873/873 | 86,99 | 59,73 |
| HTTPS | 8 | 992/992 | 98,48 | 107,23 |
| HTTPS | 16 | 1.009/1.009 | 100,10 | 217,46 |

Total 7.832/7.832. Angka 7.643 berasal dari run terdahulu yang berbeda; jangan menggabungkan keduanya. Ini bukan pengujian deny 7.832 koneksi.

[Hasil beban dan bukti](C:/Users/jim/Documents/NetPro/Testing/tap-stress/evidence/tap-stress-20261010T131056Z/RESULTS.md).

### 4.2 TCP/TLS deny–allow

Jalur: Client → Virtual TAP → Gateway; salinan → NPB → Policy Server; paket tindakan melalui jalur NetPro-RST.

Aturan SNI-only memakai `netpro-tap.test` dengan dummy IP tidak terkait `192.0.2.123`, sehingga tidak mengandalkan kecocokan IP endpoint. Setiap concurrency 4/8/16 memakai 32 koneksi TLS 1.2 baru per fase, dengan jeda satu detik antar-burst dan reset policing yang tetap aktif.

- Deny diterima sebagai hasil benar bila curl exit 35/56, HTTP 000, durasi <2,5 detik, dan RST menuju client tertangkap untuk setiap port percobaan.
- Allow harus HTTP 200 dan tidak memiliki RST menuju client pada capture fase tersebut.
- Hasil: 96/96 deny dan 96/96 allow. Capture kernel drops nol pada fase yang dicatat.

Kernel capture drops nol bukan bukti seluruh interface DPDK tanpa kehilangan. Pengujian ini tidak membuktikan revocation koneksi lama, seluruh variasi TLS, QUIC, atau kapasitas reset tanpa batas.

[Hasil RST lengkap](C:/Users/jim/Documents/NetPro/Testing/tap-stress/evidence/rst-stress-20261010T130008Z/RESULTS.md).

### 4.3 ClientHello tersegmentasi

NPB melacak aliran agar segmen lanjutan tetap diteruskan. Policy Server menyusun kembali data ClientHello untuk memperoleh SNI. Uji lokal yang telah dicatat menunjukkan payload 76, 76, dan 75 byte, reset saat aturan domain aktif, dan HTTP 200 setelah aturan dihapus.

Ini merupakan bukti kasus lokal yang tersegmentasi, bukan klaim dukungan seluruh kemungkinan urutan ulang, overlap, atau fragmentasi TCP. Pemeriksaan offline tambahan dijelaskan pada bagian 8.

## 5. SNMP dan Zabbix

### Metode dan hasil

Fixture paket HTTP dikirim melalui Client → Virtual TAP → NPB → temporary Policy Server candidate → receiver Net-SNMP terpisah pada Backend VM.

Run terdiri dari 10 paket awal, lima trial masing-masing 1.000 paket, dan satu trial 10.000 paket; total 15.010. Pengiriman diatur sekitar 100 paket/detik. Semua 15.010 trap domain diterima, tanpa kehilangan atau duplikat pada run.

Summary pertama diterima sekitar agent uptime 121,07 detik dengan interval konfigurasi 120 detik. Pengujian polling terpisah menerima 10 respons GET.

### Batas dan status

- Fixture tidak membentuk sesi TCP lengkap. Capture reset membuktikan pembangkitan/pengiriman reset, bukan 15.010 koneksi client berhasil ditolak.
- Interval penerimaan trap bukan latensi jaringan satu arah.
- Candidate memakai pengirim BER asynchronous terbatas; berbeda dari pendekatan shell-per-trap yang dijelaskan dalam skripsi. Hasil harus diberi label adaptasi, bukan reproduksi performa identik.
- Zabbix kemudian dipasang dan dikonfigurasi. Pernyataan lama pada laporan SNMP bahwa Zabbix masih outstanding harus dibaca bersama bukti konfigurasi yang lebih baru.
- Alur blocking nyata → stored history → tampilan/alert Zabbix masih belum terverifikasi lengkap.

[Hasil trap domain](C:/Users/jim/Documents/NetPro/Testing/thesis-replication/evidence/snmp-live-http-20261012T233321Z/RESULTS.md).

[Hasil polling](C:/Users/jim/Documents/NetPro/Testing/thesis-replication/evidence/snmp-polling-20261012T235944Z/RESULTS.md).

[Bukti konfigurasi Zabbix](C:/Users/jim/Documents/NetPro/Implementation/thesis-stack/evidence/zabbix-host-configure-final-20261013T010750Z/result.json).

## 6. QUIC berbasis CONNECTION_CLOSE

### Jalur lengkap

Client/server memakai HTTP/3. Salinan Initial melewati TAP → NPB → Policy Server; Close kembali melalui NetPro-RST dan gateway. Lima request deny tetap berhasil sebagai HTTP/3 200: 0/5 berhasil diblokir.

Capture menunjukkan paket Close yang terautentikasi. Ini membuktikan paket dihasilkan dan teramati, bukan bahwa client pasti menutup koneksi. Jumlah paket akibat retry bukan jumlah trial independen.

### Perbandingan jalur langsung

Adapter pengamatan dan injeksi PS sementara dihubungkan ke segmen sisi client, menghilangkan jalur NPB untuk observasi dan redirection gateway untuk injeksi. Ini bukan replikasi persis flooding bridge Proxmox pada skripsi.

Run pertama: 5/5 deny. Run ulang: 2/5 deny, 3/5 lolos HTTP/3 200. Gabungan 7/10; seluruh 20 allow controls candidate berhasil.

Waktu rata-rata Initial-to-Close pada capture client sekitar 0,42 dan 0,39 ms, dibanding sekitar 1,86 ms pada jalur lebih panjang. Kedua jalur diubah sekaligus, sehingga pengukuran tidak mengisolasi biaya NPB, gateway, atau scheduling secara terpisah. Tidak semua Close selalu lebih lambat dari Handshake.

Kesimpulan: jalur lebih pendek memperbaiki hasil tetapi belum konsisten. Jangan menyebut VMware sebagai penyebab tunggal atau menyatakan Proxmox pasti memperbaikinya. Metrik request 7/10 tidak langsung sebanding dengan persentase paket pada skripsi.

[Diagnosis jalur lengkap](C:/Users/jim/Documents/NetPro/Implementation/thesis-stack/QUIC-FULL-NETWORK-FAILURE-ROOT-CAUSE-2026-10-13.md).

[Hasil jalur langsung](C:/Users/jim/Documents/NetPro/Implementation/thesis-stack/DIRECT-TOPOLOGY-RESULTS-2026-10-13.md).

## 7. QUIC gate: pengembangan tambahan

Gate menahan Initial koneksi baru hingga keputusan Policy Server diterima. ALLOW meneruskan; DENY membuang. Close transmission dinonaktifkan pada eksperimen ini agar hasil berasal dari gate.

Lingkup: QUIC v1 baru, IPv4, client `192.168.80.29` ke Caddy `192.168.80.28`, UDP/443, domain `mysite.local`.

Run 20 request per fase:

| Fase | Hasil |
|---|---|
| Tanpa queue, allow | 20/20 HTTP 200 |
| Gate aktif, allow | 20/20 HTTP 200; 20 catatan Caddy |
| Aturan domain lain, IP server sama | 20/20 HTTP 200 |
| Aturan domain yang sesuai | 20/20 timeout curl 28; nol catatan Caddy |
| Setelah aturan dihapus | 20/20 HTTP 200 |

Capture correlation menemukan semua 40 datagram deny pada mirror dan nol kecocokan pada interface sisi origin. Itu 20 request dengan retry, bukan 40 trial. Gate timeout/unsupported outcomes nol. Median 180 sampel wait 0,79 ms; p95 1,66 ms. Timeout client saat deny bukan waktu pemrosesan keputusan.

Perbandingan terbatas dengan/tanpa gate pada concurrency 1/4/8/16 menghasilkan 160/160 allow sukses. Sampelnya pendek dan tidak membuktikan kapasitas atau biaya overhead yang berlaku umum.

Setelah eksperimen, gate dihentikan, aturan sementara dibersihkan, dan binary/configuration baseline dipulihkan. Ini prototipe inline, bukan passive mirror, dan belum membuktikan revocation sesi berjalan, migration, seluruh QUIC, atau fail-open fisik.

[Laporan gate, pengukuran, dan perintah reproduksi](C:/Users/jim/Documents/NetPro/Implementation/thesis-stack/INLINE-QUIC-RESULTS-2026-10-13.md).

## 8. Regresi NPB dan Policy Server

### Arti dan tujuan

Regresi adalah pengujian ulang fungsi lama setelah perubahan kode/topologi. Contoh: setelah eksperimen QUIC, TCP/TLS harus tetap dapat diblokir dan kembali diizinkan setelah rule delete.

Untuk NPB, pemeriksaan mencakup forwarding/klasifikasi dan pelacakan segmen lanjutan. Untuk PS, pemeriksaan mencakup parsing SNI, lookup kebijakan, hasil deny, dan hasil allow. Keberhasilan aplikasi melalui jalur lengkap mendukung kombinasi komponen; tidak selalu mengisolasi setiap fungsi NPB secara individual.

### Regresi live yang tercatat

Setelah kedua eksperimen direct-topology QUIC, adapter dikembalikan ke NetPro-TLS/NetPro-RST dan baseline dipulihkan. Verifikasi menghasilkan 20/20 reset TLS yang diharapkan serta 20/20 HTTP 200 pada allow. Hash binary, integritas SQLite, ID baseline, dan segmen adapter diperiksa.

[Bukti regresi setelah pemulihan](C:/Users/jim/Documents/NetPro/Implementation/thesis-stack/evidence/tls-regression-after-direct-20261013).

[Laporan induk yang mencatat hasil regresi](C:/Users/jim/Documents/NetPro/Implementation/thesis-stack/DIRECT-TOPOLOGY-RESULTS-2026-10-13.md).

### Harness offline: tujuan berbeda

Harness menguji fungsi ClientHello yang diekstrak dari sumber PS dan tracker NPB, dengan input yang dipin SHA-256. Kasus mencakup urutan normal, retransmission duplikat, overlap, gap/out-of-order, dan wrap sequence TCP. Gap/out-of-order pada parser produksi diperlakukan sebagai rejection; jangan mengklaim arbitrary TCP reassembly.

Harness tidak menjalankan layanan atau mengirim trafik. README mendokumentasikan cara menjalankannya; keberadaan harness tidak otomatis membuktikan semua kasus baru saja dijalankan atau lulus. Gunakan output run terkait jika mengutip hasil PASS.

[Petunjuk harness offline](C:/Users/jim/Documents/Codex/2026-09-11/referenced-chatgpt-conversation-this-is-an-2/NetPro-Documentation-current/scripts/tls-regression/README.md).

## 9. Bukti untuk presentasi dan pengulangan

| Bagian | Bukti yang ditampilkan |
|---|---|
| TAP | Hasil on/off/on dan status monitor; jelaskan bridge tetap hidup |
| TCP/TLS | Tabel deny–allow, hasil curl, RST capture, rule aktif/hapus |
| Load | Delapan tahap final run; tampilkan total 7.832 dan concurrency |
| SNMP | Tabel sent/received, log receiver, summary; label fixture/adaptasi |
| QUIC Close | Request outcome full/direct; jangan hanya menampilkan counter Close |
| Gate | Lima fase, bukti sisi origin, wait samples, catatan cleanup |
| Regresi | Hasil live 20 deny/20 allow dan baseline postflight; offline output dilabel terpisah |

[Panduan screenshot](C:/Users/jim/Documents/NetPro/Testing/tap-stress/SCREENSHOTS.md).

[Panduan reproduksi thesis-related](C:/Users/jim/Documents/NetPro/Testing/thesis-replication/RECREATE-RESULTS.md).

Sebelum mengulang: periksa VM/IP/interface, listener/port yang sudah digunakan, versi runner, source/binary, dan baseline rule. Perintah lama pada laporan dapat merujuk folder workspace lama; jangan menyalinnya tanpa memeriksa lokasi. Uji deny/gate mengubah state sementara sehingga perlu dilakukan terkontrol, bukan saat demo lain sedang memakai jalur yang sama.

Simpan untuk setiap run: waktu/timezone, konfigurasi, trial count, request outcome, log, capture bila ada, versi/hash, dan cleanup. Jangan merekam password. Bukti historis yang link-nya ada tidak berarti layanan saat ini aktif.

## 10. Pernyataan kesimpulan untuk laporan

> Forwarding dan mirroring melalui Virtual TAP berbasis software telah diuji, termasuk independensi jalur aplikasi terhadap monitor-port yang dimatikan. Pengujian beban HTTP/HTTPS dan deny–allow TLS menunjukkan hasil sesuai harapan pada workload yang dicatat. Trap SNMP berhasil diterima pada pengujian fixture terkontrol, tetapi reproduksi metode asli dan alur monitoring Zabbix lengkap belum selesai. Pemblokiran QUIC melalui CONNECTION_CLOSE belum konsisten pada jaringan lengkap. Gate inline berhasil pada koneksi baru dalam lingkup lab, tetapi merupakan prototipe tambahan yang tidak diterapkan permanen. Regresi TLS setelah pemulihan mendukung bahwa fungsi lama tetap bekerja pada saat verifikasi.

Dokumen ini adalah indeks dan rangkuman bukti, bukan pengganti file mentah atau klaim bahwa seluruh sistem siap produksi. Tidak ada push repository atau pengujian baru dilakukan saat kompilasi ini.
