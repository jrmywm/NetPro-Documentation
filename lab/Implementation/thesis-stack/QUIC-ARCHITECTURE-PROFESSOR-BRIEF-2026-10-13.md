# Catatan arsitektur dan kendala replikasi QUIC NetPro

Tanggal: 13 Oktober 2026. Catatan ini merangkum bukti pengujian yang tersimpan; tidak mengubah konfigurasi VM.

## 1. Perbedaan konsep dan topologi eksperimen skripsi

Dalam konsep NetPro, salinan trafik diteruskan dari TAP/mirror ke NPB lalu Policy Server. Policy Server memeriksa domain dan melakukan intervensi aktif melalui paket pemblokiran. Jalur trafik asli tidak ditahan oleh mekanisme pengamatan pasif tersebut.

Eksperimen Ibrahim menggunakan VM pada Proxmox dan virtual bridge dengan bridge ageing 0 untuk flooding trafik. Policy Server dapat menerima salinan trafik dan melakukan injeksi langsung melalui jaringan uji tersebut. Eksperimen ini menggunakan emulasi penyalinan trafik berbasis software, bukan bukti penggunaan perangkat physical passive TAP. Namun, tidak tepat menyebutnya tanpa pengamatan pasif: bridge mengemulasikan fungsi distribusi salinan paket, sedangkan injeksi CONNECTION_CLOSE merupakan tindakan aktif.

Topologi eksperimen tersebut bukan demonstrasi lengkap integrasi seluruh komponen NetPro pada jaringan produksi. Replikasi eksperimen dan validasi integrasi penuh perlu dilaporkan sebagai dua pengujian berbeda.

Sumber: [review skripsi Ibrahim](C:/Users/jim/Documents/Codex/2026-09-11/referenced-chatgpt-conversation-this-is-an-2/work/thesis-review-2021/notes/ibrahim.md), bagian Architecture, capture, and session behavior; rujukan ekstraksi B0617–B0632.

## 2. Mekanisme yang diharapkan

Client mengirim QUIC Initial menuju server. Policy Server menerima salinannya, mengambil SNI dan memeriksa block list. Apabila cocok, Policy Server mengirim encrypted CONNECTION_CLOSE ke client sebelum client melanjutkan handshake server. Percobaan ulang juga perlu dihentikan. Dalam eksperimen skripsi, TCP fallback pada server dinonaktifkan agar client tidak berpindah ke TCP/443.

Ini merupakan pemblokiran pada tahap awal koneksi, bukan bukti pemutusan seluruh sesi QUIC yang sudah terbentuk.

## 3. Hasil pengujian kita

| Pengaturan | Hasil deny per request lengkap | Catatan |
| --- | --- | --- |
| Jalur terintegrasi: TAP mirror → NPB → Policy Server; Close kembali melalui gateway redirect | 0/5 terblokir; seluruhnya HTTP/3 200 | Rata-rata Initial-to-Close sekitar 1,86 ms pada capture client. |
| Jalur observasi dan injeksi Policy Server langsung pada segmen client | Putaran pertama 5/5 terblokir; putaran kedua 2/5; gabungan 7/10 | Rata-rata Initial-to-Close sekitar 0,42 dan 0,39 ms. Ini perbandingan VMware yang lebih pendek, bukan replika persis flooding Proxmox. |
| Extension inline gate pada Virtual TAP, keputusan dari Policy Server | Allow 20/20; deny 20/20; allow setelah hapus rule 20/20 | Close TX dimatikan untuk mengisolasi gate. Nol request Caddy saat deny. |

Pada gate, 40 datagram Initial yang ditolak berasal dari 20 koneksi dengan retry. Seluruh 40 datagram cocok dengan capture mirror TAP berdasarkan tuple, panjang UDP payload, dan SHA-256; tidak ada yang cocok pada capture origin-facing gateway. Jumlah paket retry tidak boleh dianggap sebagai jumlah request independen.

Perbandingan latensi gate menggunakan 20 request per concurrency 1/4/8/16 untuk setiap pengaturan, total 160 request berhasil. Pada concurrency 1, median waktu request tanpa gate 9,365 ms dan dengan gate 12,265 ms. Selisih sekitar 2,9 ms ini bersifat deskriptif dari sampel pendek, bukan hasil stress test, estimasi kapasitas, atau pembuktian overhead kausal yang presisi.

## 4. Kesimpulan yang dapat dan tidak dapat diambil

- Mirroring bekerja; kegagalan pada jalur penuh adalah kegagalan mencegah request selesai, bukan kegagalan memperoleh salinan paket.
- Close yang tiba di capture client dan dapat diautentikasi tidak membuktikan client menerima atau menindaklanjuti Close tersebut.
- Tidak benar bahwa Close selalu datang terlambat. Rata-rata kedatangannya pada satu pengujian jalur penuh lebih awal dari rata-rata handshake, tetapi request tetap dapat berhasil melalui retry.
- Jalur yang lebih pendek memperbaiki waktu kedatangan dan hasil deny, tetapi belum konsisten. Perubahan observasi dan injeksi dilakukan bersama sehingga kontribusi NPB, gateway, dan scheduling VM belum terisolasi.
- Timing, state QUIC, dan perilaku retry/client merupakan faktor yang perlu diteliti; akar penyebab tunggal belum terbukti. Tidak ada dasar untuk menyimpulkan VMware pasti penyebabnya atau Proxmox pasti menyelesaikannya.
- Angka deny request kita tidak dapat langsung dibandingkan dengan rasio paket pemblokiran pada skripsi.
- Gate berhasil pada lingkup uji, tetapi mengubah arsitektur menjadi inline enforcement: paket asli ditahan lalu diteruskan atau dibuang. Gate bukan perbaikan yang sudah terbukti terhadap mekanisme CONNECTION_CLOSE asli, bukan fitur asli skripsi, dan bukan bukti physical fail-open.

## 5. Status setelah pengujian terakhir

Gate merupakan prototype terbatas untuk koneksi QUIC v1 baru dari client 192.168.80.29 menuju origin 192.168.80.28 UDP/443. Revokasi sesi established, migrasi koneksi, serta cakupan QUIC umum belum dibuktikan.

Setelah pengujian terakhir, candidate Policy/NPB service overrides dilepas dan service original dipulihkan. Rule block-list pengujian dan hook queue TAP dibuang; gate tidak ditinggalkan aktif. Hash binary original, empat baseline policy IDs, integritas SQLite, penghapusan state gate, dan enam hash PCAP diverifikasi. Ini berarti gate telah diuji, tetapi belum dipasang sebagai enforcement persisten.

## 6. Hal yang perlu dikonsultasikan kepada dosen

1. Apakah target penilaian adalah reproduksi eksperimen standalone Ibrahim, keandalan deny pada integrasi NetPro penuh, atau keduanya?
2. Apakah konfigurasi bridge, versi curl/QUIC library, dan source asli pengujian dapat diperoleh untuk memperkecil perbedaan replikasi?
3. Apakah kita boleh menguji flooding bridge software pada TAP VM di VMware sebagai pendekatan terhadap topologi skripsi? Ini masih usulan, belum dilakukan sebagai replika persis.
4. Apakah extension inline gate dapat menjadi pengembangan terpisah, dengan konsekuensi latency, ketersediaan, dan failure behaviour dilaporkan secara eksplisit?
5. Bagaimana jalur injeksi yang dimaksud untuk deployment NetPro nyata? Gateway redirect kita adalah pengaturan pengiriman lab, bukan desain produksi yang telah divalidasi.

## Ringkasan untuk disampaikan

Pak, eksperimen QUIC pada skripsi Ibrahim menggunakan virtual bridge flooding di Proxmox untuk menerima salinan trafik dan melakukan injeksi langsung, bukan pengujian physical passive TAP maupun integrasi lengkap jalur NPB. Pada pengujian terintegrasi kami, mirroring dan pengiriman CONNECTION_CLOSE bekerja, tetapi lima request deny tetap berhasil mengakses server. Saat jalur Policy Server dipersingkat, tujuh dari sepuluh request terblokir, sehingga mekanisme belum konsisten. Kami belum dapat menyatakan bahwa penyebabnya hanya keterlambatan NPB atau gateway, karena retry dan penerimaan Close oleh client juga belum terisolasi. Sebagai extension terpisah, inline gate berhasil menjalankan allow–deny–allow masing-masing 20 request, tetapi metode ini menahan trafik asli dan berbeda dari mekanisme skripsi. Kami ingin mengonfirmasi target replikasi serta konfigurasi dan versi software pengujian asli sebelum menentukan arsitektur akhir.

## Bukti pendukung

- [Profil jalur penuh](THESIS-PROFILE-2026-10-13.md)
- [Perbandingan jalur langsung](DIRECT-TOPOLOGY-RESULTS-2026-10-13.md)
- [Temuan diagnostik dan koreksi atribusi timing](QUIC-FULL-NETWORK-FAILURE-ROOT-CAUSE-2026-10-13.md)
- [Hasil extension inline gate dan perintah reproduksi](INLINE-QUIC-RESULTS-2026-10-13.md)
