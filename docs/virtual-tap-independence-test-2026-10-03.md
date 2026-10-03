# Virtual TAP monitor-branch independence test — 3 October 2026

A controlled local HTTP/TLS test verified that the client-to-Gateway application path continued when only the TAP VM's monitor NIC (`ens36`) was administratively down. This tests monitor-NIC failure independence; it does not establish physical TAP fail-open behavior or transparency when the TAP VM itself is powered off.

The client (`192.168.80.29`) sent two HTTP requests to Gateway `192.168.80.28:8080` and two TLS 1.2 requests to `netpro-tap.test:8443` in each phase. The on-before phase at `16:33:02–03 UTC` returned HTTP 200 for all four requests. With `ens36` down (`16:33:29–48 UTC`), all four again returned HTTP 200. After restoring `ens36` (`16:33:49 UTC`), all four returned HTTP 200. Total: 12/12 successful requests. The `ens34`/`ens35` bridge ports were not changed.

NPB telemetry baseline was packet ID `213659` at `16:32:38 UTC`. Querying at `16:34:19 UTC` showed no row with received-input counts during the monitor-down interval. Before/after rows showed the expected HTTP/TLS activity (e.g. IDs `213723` and `213769`, each with HTTP 2 and TLS 2). This supports mirror-branch independence; it is not a packet-capture proof. No PCAP was recorded. Host counters/capture timestamps do not establish packet-level loss or latency.

Cleanup stopped the named temporary HTTP/TLS services and restore timer, cleared the test state, and left the Gateway with forwarding disabled, the TAP monitor restored/up, and the mirrored bridge operational. NPB and Policy remained active. A root-private test certificate directory was retained on the Gateway and was not copied here. No policy was changed.

The host-guarded test helpers and text evidence are in [`scripts/virtual-tap-live-test`](../scripts/virtual-tap-live-test/) and [`evidence/virtual-tap-live-test`](../evidence/virtual-tap-live-test/).
