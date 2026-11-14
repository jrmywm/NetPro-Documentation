# NetPro: konsolidasi enam VM dan pengurangan RAM

Pengerjaan: 28–29 Oktober 2026, Asia/Taipei. Dokumen ini mencatat perubahan nyata, bukan rencana saja. Bukti tersimpan dalam subfolder `evidence/`. Tidak ada repository upstream yang di-push dan tidak ada VM yang dihapus.

## Susunan akhir

| VM | Peran | RAM |
|---|---|---:|
| Backend-VM / Management | Backend, PostgreSQL, Kafka 3.6.1, ZooKeeper, frontend statis/nginx, SNMP receiver, Zabbix | 4 GiB |
| NPB-VM | Klasifikasi/forwarding DPDK | 2 GiB |
| Policy-Server-VM | Pemeriksaan kebijakan DPDK | 2 GiB |
| NetPro-Virtual-TAP | Bridge/mirror, topologi tidak diubah | 1 GiB |
| NetPro-Test-Gateway | Gateway/server uji | 1 GiB |
| Client-VM | Client uji | 1 GiB |
| **Total normal** | **6 VM** | **11 GiB** |

Frontend-VM dan Kafka-Broker-VM lama dimatikan, tetapi seluruh disk dan konfigurasi asal dipertahankan. Packet-Generator-VM tetap mati dan belum dioptimalkan; alokasinya masih 6.0625 GiB.

Pembanding konfigurasi normal sebelumnya adalah delapan VM (tanpa generator), 30 GiB. Pengurangan menjadi 11 GiB berarti 19 GiB atau sekitar 63,3% pengurangan RAM yang **dialokasikan**. Ini bukan pengukuran penghematan working set Windows dengan semua kondisi aplikasi identik. Inventori awal sembilan VM termasuk generator berjumlah 36.0625 GiB.

## Alamat layanan

- Dashboard baru: **https://192.168.31.35:3005**.
- API tetap: https://192.168.31.35:3000.
- Frontend memakai `/api` pada origin yang sama, diproxy nginx ke API loopback. Hal ini tidak memindahkan API lama atau mengganti model autentikasinya.
- Kafka yang diiklankan: `192.168.31.35:9092`.
- Bootstrap backend: `127.0.0.1:9092`.
- Alias kompatibilitas: `192.168.0.90/32` pada ens33 Management. Binary PS masih berisi alamat lama tersebut. Data/NIC/binary pemrosesan paket tidak dibangun ulang.
- Alamat management PS/NPB/TAP/Gateway/Client tetap `.31/.33/.38/.37/.39` pada subnet `192.168.31.0/24`.

**Jangan menyalakan Kafka-Broker-VM lama bersamaan dengan alias kompatibilitas Management.** Alamat IP akan berkonflik dan kedua broker berisi salinan state yang sama. Launcher menolak kondisi legacy VM sedang hidup.

Sertifikat lab tetap self-signed. Perubahan origin dashboard dapat memerlukan login kembali. Pemeriksaan frontend pada pekerjaan ini mencakup build, asset/route HTTP dan API proxy; bukan audit interaksi seluruh halaman dalam browser.

## Perubahan yang diterapkan

1. Source frontend aktif, termasuk perubahan uncommitted/untracked, dicadangkan. Build production memakai `REACT_APP_BASE_URL=/api`; file source dan `.env.local` asal tidak diganti. nginx menyajikan build tersebut tanpa React development-server process.
2. PostgreSQL `test` dan globals dicadangkan sebelum migrasi Kafka. Backend dihentikan saat snapshot broker dibuat.
3. Kafka dan ZooKeeper dihentikan lalu distribution/configuration/data disalin bersama. Topic ID `dpdk-blocked-list` tetap `E03SI_rbSiusgoqscaR-rA`, sama dengan sumber.
4. Download JRE dari repository Ubuntu timeout. Runtime Java 17 yang bekerja di VM Kafka disalin terpisah ke `/opt/netpro-runtime/java-17-openjdk-amd64`. Tidak mengganti system Java. Runtime ini belum dikelola pembaruan paket apt di Management dan perlu ditinjau pembaruannya kemudian.
5. Heap Kafka dibatasi 512 MiB, ZooKeeper 128 MiB. Unit backend menunggu pemeriksaan kesiapan broker saat startup. nginx dapat tersedia lebih awal daripada API; satu pemeriksaan segera setelah reboot mendapat 502, lalu pemeriksaan setelah startup selesai lulus.
6. RAM NPB/PS diturunkan bertahap 6 → 3 → 2 GiB. Pool hugepages diturunkan dari 2 GiB menjadi 1 GiB setelah terlihat hanya sekitar 60 MiB digunakan. Pada konfigurasi akhir masing-masing memiliki 512 hugepage 2 MiB, 482 bebas pada pemeriksaan. Ring/mbuf/core/NIC/binary tetap.
7. TAP/Gateway/Client masing-masing diturunkan dari 2 ke 1 GiB. Management tetap 4 GiB untuk headroom.

## Temuan dan perlindungan database PS

Regresi setelah reboot berhenti karena ID baseline SQLite berubah dari empat ke satu. Kode PS yang sudah ada memanggil `delete_database()` pada graceful exit dan menghapus file SQLite. Kafka memulihkan satu aturan backend-managed, tetapi tiga aturan SQL-only historis tidak dipulihkan otomatis.

Tiga baris yang hilang dipulihkan dari backup yang tepat (`/home/netpro/incoming/thesis-rollout.0twmEQ/policy-before.db`, SHA-256 `39bf3b1e51f9f6f6a21894d1ea3d9b49fd014cb91dbf05e10384c6a6643904b3`), setelah kecocokan empat ID dan nilai baris backend diverifikasi. Database saat itu dicadangkan sebelum INSERT. Baris backend tidak diubah dan tidak ada aturan baru yang diciptakan.

Guard `/usr/local/libexec/netpro-policy-db-guard` serta drop-in `/etc/systemd/system/netpro-policy.service.d/consolidation-database.conf` membuat snapshot sebelum controlled stop dan memulihkan file hanya jika hilang setelah cleanup binary. Snapshot disimpan privat di `/var/lib/netpro-policy-db-guard/`. Restart service diverifikasi mempertahankan empat ID dan integritas `ok`.

Guard bukan solusi lengkap crash-consistency, rekonsiliasi Kafka, atau keselarasan SQL-only dengan PostgreSQL. Ia tidak menimpa database yang masih ada. Perilaku penghapusan database pada source masih ada karena binary tidak diubah.

## Verifikasi

| Pemeriksaan | Hasil yang dicatat |
|---|---|
| Frontend build dari source aktif | Lulus |
| nginx route dan API proxy | HTTP 200; list NPB/PS serta baseline rule dapat diambil |
| Kafka topic identity | Topic ID sama dengan sebelum migrasi |
| Management reboot | Alias, ZooKeeper, Kafka, backend, nginx, PostgreSQL, receiver SNMP dan Zabbix kembali aktif; API lulus setelah startup selesai |
| TLS awal pada 13 GiB | 20/20 deny reset dan 20/20 allow HTTP 200 |
| TLS segmented awal pada 13 GiB | 20/20 deny dan 20/20 allow; profile/capture diverifikasi workflow |
| NPB/PS boot pada 2 GiB | Service aktif; pool 1 GiB; swap terpakai nol saat diperiksa |
| SNMP smoke setelah reboot Management | Satu trap berlabel dikirim PS dan marker ditemukan pada receiver Management |
| Restart PS dengan DB guard | Empat ID tetap ada; integrity `ok` |
| TLS normal konfigurasi akhir | 20/20 deny dan 20/20 allow; bukti `active-baseline-20261029T123530-900e4d6a.json` |
| TLS segmented konfigurasi akhir | 20/20 deny dan 20/20 allow; bukti `active-baseline-20261029T123646-c007ec0b.json` |

Kedua workflow konfigurasi akhir selesai tanpa failure dan mencatat cleanup `completed_or_auto_verified`. Temporary policy/RST/listener/MTU/offload dimiliki dan dibersihkan oleh workflow guarded yang sudah ada.

Bukti utama lain:

- `frontend-stage-20261028T153203Z/`, `frontend-activate-20261028T153412Z/`.
- `kafka-copy-20261029T121149Z/`, `kafka-activate-20261029T121303Z/`.
- `management-verify-20261029T122522Z/` dan pemeriksaan lebih baru.
- `snmp-smoke-20261029T122906Z/`.
- `policy-baseline-recovery-20261029T123435Z/`, `policy-db-guard-20261029T123506Z/`.
- `host-final-20261029T122950Z.json`: enam VM, 11 GiB; host available saat sampel sekitar 2,84 GiB.
- `management-verify-20261029T123945Z/` dan `host-final-20261029T123958Z.json`: pemeriksaan akhir lulus; enam VM, 11 GiB; host available sekitar 2,47 GiB pada sampel terakhir.

Tidak dilakukan uji kapasitas besar atau pengulangan QUIC gate/Close pada pekerjaan ini. Konsolidasi tidak memperbaiki atau mengubah kesimpulan QUIC sebelumnya. SNMP smoke bukan verifikasi seluruh history/alert Zabbix.

## Mengoperasikan

Dari direktori yang berisi file ini, jalankan PowerShell:

```powershell
.\Start-NetPro.ps1
```

Launcher menyalakan enam VM jika belum hidup. Keberhasilan menyalakan VM bukan jaminan semua aplikasi langsung siap. Buka dashboard setelah startup selesai.

Untuk graceful shutdown enam VM:

```powershell
.\Stop-NetPro.ps1
```

Script stop disediakan tetapi belum diuji sebagai satu operasi shutdown lengkap pada akhir sesi, karena keenam VM ditinggalkan hidup. Tidak memakai hard stop/reset. Packet Generator tidak dihidupkan atau dimatikan oleh operasi normal. Opsi `-IncludePacketGenerator` pada launcher memerlukan minimal 7 GiB host memory tersedia; total resource pengujian beban harus diperiksa tersendiri.

Perubahan frontend selanjutnya memerlukan build production dan deployment ulang. Menyunting source pada Frontend-VM lama tidak otomatis mengubah dashboard yang sedang dilayani Management.

## Backup dan rollback

- Source dan build frontend ada di `/home/netpro/consolidation-backups/20261028T153203Z/` pada Frontend-VM serta arsip lokal dalam evidence stage.
- Snapshot Kafka ada di Kafka-VM `/home/netpro/consolidation-backups/20261029T121149Z/kafka-state.tar.gz`, salinan lokal evidence, dan staging Management. Disk VM asli tetap utuh.
- PostgreSQL dan konfigurasi backend awal ada pada Management `/root/netpro-consolidation-20261028T153544Z/`. Backup konfigurasi saat activation ada di `/root/netpro-consolidation-20261029T121303Z/`.
- Konfigurasi RAM sebelum tahap pertama ada di `memory-stage/*.original.vmx`; sebelum tahap kedua ada di `memory-final-stage/*.original.vmx`. Jangan menyalakan file VMX cadangan sebagai VM baru atau mengganti konfigurasi VM yang sedang hidup.
- Backup script hugepage ada di PS `/usr/local/sbin/netpro-dpdk-prepare.sh.before-consolidation-20261029T122639Z` dan NPB `/usr/local/sbin/netpro-npb-dpdk-prepare.sh.before-consolidation-20261029T122648Z`.

Rollback broker harus terkontrol: hentikan backend dan broker baru, lepaskan/nonaktifkan alias kompatibilitas, baru hidupkan broker lama dan kembalikan endpoint backend. Broker lama adalah snapshot sebelum perubahan baru, jadi jangan melakukan rollback mentah setelah ada update kebijakan tanpa menyelaraskan data terlebih dahulu. Jangan pernah menghidupkan dua broker dengan alamat/state identitas yang sama sekaligus.

Rollback frontend dapat memakai VM lama dan URL `.36:3005`, tetapi pastikan konfigurasi API frontend tetap menunjuk ke backend aktif. Rollback RAM memerlukan graceful shutdown dan pengembalian hanya setting yang dimaksud; bukan overwrite VMX tanpa memeriksa perubahan lain.
