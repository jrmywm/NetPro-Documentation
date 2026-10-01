# TRex profile MAC correction and mixed retest — 2 October 2026

At 23:22:04–23:22:12 UTC on 1 October (07:22:04–07:22:12 Taipei on 2 October), the corrected profiles completed the eight-second mixed HTTP/TLS/UDP test at 1,000 pps. The five generator profiles now specify only the two explicit MAC override arguments across nine streams; rates, timing, and payloads were unchanged. The original five files were clean before deployment and backed up under `/tmp/netpro-mac-profile-backup.VCd3af`.

Command, run from the TRex `npb` directory:

```bash
PYTHONPATH=/opt/trex/v3.04/automation/trex_control_plane/interactive \
  python3 npb_testing_http_https_udp.py --sizes 256 --pps_values 1000 2000 1000
```

TRex JSON totals were TX 8,019, RX 4,010, errors 0; stream TX counts were HTTP 2,005, TLS 2,005, UDP 4,009. Latency-flow RX was zero, as expected for these reset-response profiles. The first telemetry query returned no rows while ingestion was pending. Later, nine rows per service appeared: NPB `176934`–`176942`, Policy `174560`–`174568`. NPB classified/output totals were HTTP 2,005 and TLS 2,005; Policy input totals were HTTP 2,005 and TLS 2,005, with 4,010 client RSTs, 4,010 server RSTs, and 8,020 TX packets. The aggregate 4,010 TRex RX matches the client-RST total; it does not prove server-directed delivery or loss-free behavior at higher load. No full mixed PCAP was captured.

TRex PID `17706` was stopped; NPB and Policy remained active and Policy DB integrity was `ok` with four rows. TLS/UDP fixture hashes were unchanged. The copies, manifest, deployment helper, and read-only telemetry query are in [`scripts/trex-profile-mac-fix`](../scripts/trex-profile-mac-fix/README.md); run outputs are in [`evidence/trex-profile-mac-fix`](../evidence/trex-profile-mac-fix/).
