# TRex reset-return MAC diagnostic — 2 October 2026

At 23:00:37 UTC on 1 October (07:00:37 Taipei on 2 October), a controlled TRex receive test compared original and temporary normalized MAC handling. No production source was changed.

| Case | Packets sent | TRex received | RX bytes | Errors |
| --- | ---: | ---: | ---: | ---: |
| Original | 200 | 100 HTTP RST, 0 TLS RST | 6,800 | 0 |
| Normalized | 200 | 100 HTTP RST, 100 TLS RST | 13,600 | 0 |

Both cases showed Policy telemetry of 100 HTTP and 100 TLS inputs, 200 client-directed RSTs, 200 server-directed RSTs, and 400 TX packets. The configured lab Ethernet pair is NPB `00:0c:29:ba:d7:5a` → TRex `00:0c:29:c5:4f:e8`. The original PCAPs are `netpro-mac-return-original-16025-1790895638065107894.pcap` and `netpro-mac-return-normalized-16025-1790895640140755668.pcap` in `work/reset-diagnosis`; their TRex RX captures are authoritative because the executed counter script omitted packet-count keys. Fix the helper before future comparisons.

This supports the diagnosis that normalizing the TLS return MACs restores client-directed TLS RST reception. It proves client-RST receive behavior only; server-directed reset delivery was not tested at TRex. TRex is stopped; Policy and NPB are active; Policy DB integrity is `ok` with four rows. Next: fix the profiles and repeat the full mixed-traffic test.
