# Briefing latihan: presentasi progres NetPro

**Deck:** 18 slide “Presentasi Progres Desain Proyek 2 — Kelompok 27 NetPro”  
**Durasi:** rencana bicara sekitar 15 menit; jika batas 20 menit termasuk tanya jawab, sisakan 5 menit untuk pertanyaan. Bila slot 15–20 menit hanya untuk paparan, perluas demo/penjelasan sesuai arahan dosen.  
**Tujuan latihan:** jelaskan progres yang terukur, bedakan target proposal dari hasil, lalu minta arahan tentang sasaran replikasi QUIC dan fitur skripsi yang belum ditemukan. PDF sumber tetap utuh; gunakan lembar koreksi untuk memperbarui deck secara manual.

## Pembagian pembicara

Deck memuat lima nama. Pembagian berikut adalah usulan giliran presentasi, bukan klaim kontribusi implementasi: pembicara A slide 1–5, B slide 6–7, C slide 8–11, D slide 12–14, E slide 15–18. Tetapkan nama sesuai kesepakatan tim. Beri bagian hasil kepada anggota yang paling siap menjelaskan retry dan perbedaan metode QUIC. Semua anggota perlu memahami batas klaim.

## Alur 18 slide dan catatan bicara (target ±15 menit)

Waktu di bawah berjumlah kira-kira 15 menit. Jangan membaca semua teks slide; nyatakan satu pesan, bukti, lalu transisi.

1. **Sampul (0:20).** “Kami menyampaikan progres Desain Proyek 2 NetPro: pemantauan dan kebijakan domain dalam lingkungan lab virtual.” Langsung beri konteks bahwa ini progres, bukan klaim siap produksi.
2. **Anggota (0:20).** Perkenalkan anggota sesuai urutan kehadiran. Jangan menyebut pembagian kontribusi kecuali sudah disepakati tim.
3. **Daftar isi (0:25).** “Kami mulai dari tujuan dan rancangan, lalu pengujian, hasil sementara, kendala, dan rencana.”
4. **Permasalahan dan tujuan (0:50).** NetPro memeriksa salinan trafik untuk klasifikasi domain/kebijakan. Sampaikan bahwa eksperimen berjalan di VMware. Hindari kalimat yang menyatakan semua domain/protokol telah diblokir.
5. **Tujuan proyek (0:45).** Fokus awal adalah klasifikasi HTTP/TLS dan TCP Reset, dengan sinkronisasi Kafka serta dashboard. QUIC kini sudah diuji pada jalur lab menggunakan candidate runtime, tetapi belum dipasang sebagai enforcement persisten. TLS SNI diproses tanpa dekripsi isi HTTPS. Parser QUIC membuka header protection dan mendekripsi payload Initial untuk membaca TLS ClientHello/SNI, bukan isi aplikasi HTTPS.
6. **Target kinerja (0:40).** Tabel ini berisi target proposal dan cara ukur, bukan capaian. Jelaskan bahwa RST/T_total/PPS/loss/sinkronisasi dan sumber daya masih memerlukan pengujian masing-masing. Hasil terbatas dibahas nanti.
7. **Arsitektur (0:55).** Jelaskan salinan trafik melalui Virtual TAP dan NPB ke Policy Server; respons aktif seperti TCP RST kembali melalui segmen uji. Kafka/dashboard adalah control/monitoring plane. Pada QUIC, uji baru menunjukkan bahwa hasil berbeda menurut jalur dan mekanisme.
8. **Timeline (0:35).** Pekan 7 memuat retest dan modul SNMP/QUIC; kini ada pengukuran langsung yang lebih baru. “Sesuai” merujuk status timeline internal, bukan validasi integrasi penuh. Presentasi progres berlangsung 14 Oktober.
9. **Persentase progres (0:45).** Angka 84/86% adalah estimasi berbobot komponen pada pekan 6/7 menurut tabel; bukan ukuran independen keberhasilan. Sebut bobot dan basis penilaian, dan pastikan metode penilaian tim bisa dijelaskan. Jika tidak ada rubrik/evidence yang konsisten, tandai sebagai estimasi internal.
10. **Topologi VMware (0:55).** Tunjuk perbedaan jalur utama, tap virtual, NPB, Policy Server, jalur return, dan monitoring. Ini arsitektur lab, bukan perangkat TAP fisik atau deployment produksi.
11. **Perubahan desain (0:50).** Virtual TAP menggantikan TAP fisik sementara; Policy Server diuji di VM, Raspberry Pi tertunda; reassembly TLS dan return path disesuaikan. SNMP/QUIC adalah modul tambahan, tetapi kemajuan modul pada 10 Oktober sudah dilengkapi/di-update oleh pengujian 12–13 Oktober.
12. **Pengujian (0:55).** Daftar ini adalah rencana/riwayat skenario (cold start, TRex, situs nyata, regresi, TAP, TLS, SNMP/QUIC). Bedakan metode tiap uji; request TLS penuh tidak sama dengan jumlah paket RST, dan fixture HTTP bukan sesi client TCP yang sungguh-sungguh.
13. **Hasil stress TLS/HTTP (1:05).** Angka 96/96 deny dan 7.832/7.832 sukses adalah hasil historis untuk run yang ditampilkan di deck; pemblokiran RST diuji terpisah dari beban HTTP/TLS. Jangan ubah menjadi 7.643 tanpa bukti run yang cocok; cantumkan tanggal/run dan metodologi. Jangan jadikan 7.832 sebagai bukti QUIC atau performa semua versi.
14. **Hasil sementara (2:30).** Pisahkan hasil historis P4/P6/P7 dari hasil terbaru. Yang terbaru: HTTP-driven SNMP menerima 15.010/15.010 trap, tanpa loss/duplikasi pada fixture berpacing 100 paket/detik; polling SNMP berhasil 10/10 untuk object guest-wide; Zabbix host dikonfigurasi dan trap smoke test diterima, tetapi history/dashboard/ingestion end-to-end belum diverifikasi. QUIC full path 0/5 deny; direct path 7/10; inline gate terpisah allow 20/20–deny 20/20–allow setelah rule delete 20/20 untuk koneksi baru di lab. Gate saat ini off. Tidak semua hasil ini setara atau bagian dari satu pengujian. Gunakan hasil historis sebagai backup agar slide utama tetap terbaca.
15. **Kendala (0:50).** Soroti fragmentasi TLS, topologi virtual, pemisahan jalur respons, isu policy DB/baseline, dan kode skripsi yang belum ditemukan. Hindari detail koordinasi internal yang tidak membantu keputusan teknis.
16. **Risiko dan mitigasi (0:50).** Jelaskan risiko persistence database, resource, respons terlambat, serta perangkat/kode yang belum tersedia. Uji latensi inline yang terbatas bukan stress test. Jangan berjanji satu VM user menggantikan uji banyak client untuk semua target.
17. **Rencana (0:50).** Prioritas: konfirmasi source/version client dan target replikasi QUIC; verifikasi Zabbix history/dashboard; lanjutkan validasi sesuai alat tersedia; ukur ulang throughput, loss, latency, resource. Rencana tidak sama dengan pekerjaan selesai.
18. **Penutup (0:20).** “Kami meminta arahan: apakah prioritas berikutnya reproduksi eksperimen QUIC standalone, keandalan deny pada jalur penuh NetPro, atau keduanya sebagai hasil terpisah? Apakah ada source/version client/topologi uji asli yang dapat kami cocokkan?”

## Angka dan batas yang harus konsisten

- **SNMP HTTP fixture:** 15.010 paket menghasilkan 15.010 trap, loss 0%, duplikasi 0. Pacing 100 paket/detik; sender asynchronous berbeda dari pendekatan shell-per-trap pada skripsi. Reset capture bukan bukti client ditolak.
- **SNMP polling:** sepuluh GET berhasil; OID memori dan CPU adalah metrik guest-wide. CPU berupa counter mentah (bukan persen), sebagian nilai awal nol/cache. Tidak membuktikan telemetry proses Policy Server.
- **Zabbix:** host dikonfigurasi dengan enam item polling dan satu trap item; trap smoke test diterima dan HTTP 200. Ingestion berkelanjutan, history, dashboard, dan alerting belum sepenuhnya diverifikasi.
- **QUIC CONNECTION_CLOSE:** jalur penuh 0/5 request deny meski Close terlihat di capture; mean Initial-to-Close sekitar 1,86 ms, sehingga jangan klaim Close selalu terlambat. Jalur langsung 5/5 pada putaran pertama, 2/5 pada pengulangan, total 7/10. Retry, library/client, timing, dan perubahan observasi/injeksi belum diisolasi; ini bukan rasio paket skripsi.
- **Gate QUIC:** extension inline: allow 20/20, domain kontrol berbeda pada IP sama 20/20, deny 20/20, allow setelah penghapusan rule 20/20. Empat puluh datagram deny berasal dari retry 20 koneksi. Close TX dimatikan. Perbandingan 160 request berhasil pada concurrency 1/4/8/16; concurrency 1 median 9,365 vs 12,265 ms. Sampel deskriptif, bukan stress test atau overhead kausal presisi. Hanya QUIC v1, client `.29` ke origin `.28` UDP/443, koneksi baru; gate sudah off dan layanan asli dipulihkan.
- **Kesetiaan replikasi:** eksperimen Ibrahim menggunakan VM Proxmox dan virtual bridge flooding (bridge ageing 0), bukan bukti physical passive TAP; replikasi eksperimen dan validasi integrasi NetPro penuh adalah pertanyaan berbeda.
- **Audit kode:** implementasi asli Luthfi/Rafie belum ditemukan setelah audit delapan repositori dan sebelumnya ditunda oleh dosen. Minta petunjuk repository/arsip secara netral.

## Tanya jawab: 12 jawaban siap latihan

1. **Apakah semua target sudah tercapai?** Belum. Tabel target adalah proposal; hasil tiap subsistem dan integrasi harus dinilai terpisah.
2. **Apakah sistem mendekripsi HTTPS?** Tidak mendekripsi isi aplikasi HTTPS. TLS SNI dapat dibaca dari handshake; parser QUIC membuka header protection dan mendekripsi payload Initial yang memuat ClientHello/SNI.
3. **Apakah QUIC sudah terintegrasi?** Sudah diuji pada jalur lab melalui candidate runtime. Close-based deny belum konsisten. Gate terpisah berhasil pada scope uji, lalu dinonaktifkan setelah cleanup. Belum ada deployment QUIC persisten yang telah divalidasi.
4. **Apakah QUIC berhasil diblokir?** Full path 0/5; direct path 7/10; gate inline 20/20 pada scope uji. Beda topologi dan mekanisme, tidak digabung jadi satu angka.
5. **Apakah Close selalu terlambat?** Tidak. Rata-rata 1,86 ms di full path, tetapi request tetap lolos; capture tidak membuktikan client memproses atau mengabaikannya.
6. **Apa penyebab lolosnya request?** Belum terbukti tunggal. Retry, timing, state/library client, dan perubahan jalur observasi/injeksi perlu diisolasi.
7. **Mengapa 7/10 belum reliabel?** Sampel kecil: hasil berubah antara 5/5 dan 2/5 deny; bukan estimasi keandalan umum.
8. **Harus pindah ke Proxmox?** Belum ada bukti. Perbandingan langsung adalah jalur VMware yang lebih pendek, bukan replika persis virtual bridge Proxmox.
9. **Apakah gate metode skripsi?** Bukan. Gate menahan/meneruskan atau membuang paket asli; Close mengirim paket aktif setelah mengamati salinan. Gate adalah extension dan kini off.
10. **Apakah 40 deny berarti 40 request?** Tidak; 40 datagram Initial, termasuk retry, dari 20 koneksi pada run gate.
11. **Apakah SNMP menunjukkan CPU Policy Server?** Tidak. Polling guest-wide; counter CPU mentah bukan persen dan bukan metrik proses.
12. **Apakah Zabbix sudah punya dashboard valid?** Belum dikonfirmasi. Host/item dan smoke test trap terbukti, persistence/history/dashboard/alert belum penuh.

## Persiapan tampilan dan demo

Gunakan hasil tersimpan sebagai bukti utama. Pilih tangkapan layar ringkas dari `QUIC-ARCHITECTURE-PROFESSOR-BRIEF-2026-10-13.md`, `DIRECT-TOPOLOGY-RESULTS-2026-10-13.md`, `INLINE-QUIC-RESULTS-2026-10-13.md`, dua `RESULTS.md` SNMP di folder evidence tanggal 12 Oktober, serta dua JSON smoke/config Zabbix tanggal 13 Oktober. Sensor nilai sensitif; jangan tampilkan credential. Jangan buka log panjang atau hitung retry sebagai trial.

Untuk demo live, siapkan dan uji runner yang telah ditinjau sebelum presentasi. Jelaskan bahwa runner mengaktifkan candidate dan gate secara sementara lalu memulihkannya. Jangan mengimprovisasi perubahan jaringan saat presentasi. Gate terakhir diverifikasi off setelah cleanup; bila lab tidak siap, tunjukkan bukti tersimpan dan sebutkan tanggalnya. Latih alur sekitar 15 menit dengan timer, siapkan hingga lima menit Q&A bila total slot 20 menit, dan minta persetujuan tim atas angka progres serta pembagian bicara.

### Perintah menampilkan hasil gate tersimpan

PowerShell pada laptop, tanpa menghubungi atau mengubah VM:

```powershell
Set-Location 'C:\Users\jim\Documents\NetPro\Implementation\thesis-stack'
$result = Get-Content '.\evidence\inline-functional-parent-20261013-03\inline-summary.json' -Raw | ConvertFrom-Json
"Saved run: $($result.run_id), passed: $($result.passed)"
$result.phases | Where-Object { $_.expected } | ForEach-Object {
    [pscustomobject]@{
        Phase = $_.name
        Requests = $_.rows.Count
        HTTP200 = @($_.rows | Where-Object { $_.http_code -eq 200 }).Count
        CaddyRequests = $_.caddy_access_records
    }
} | Format-Table -AutoSize
```

Ini peninjauan hasil tersimpan, bukan eksekusi uji baru. Capture correlation dan laporan detail tersedia di direktori evidence yang sama.
