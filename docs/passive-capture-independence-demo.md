# Mirrored capture-branch independence demo

## Scope and method

The Gateway remains the inline NAT router; NPB and Policy receive a software-mirrored branch. This tests independence from that branch, not a physical passive TAP or transparency to Gateway failure.

The test used Gateway `192.168.31.37` / `192.168.80.28`, Client `192.168.31.39` / `192.168.80.29`, and target `142.251.152.119` pinned to `www.google.com`. Policy was not restarted and its data was not changed. Gateway `ens38` ingress had a structurally installed drop-all guard to prevent RST return; it counted zero packets throughout because the target was unblocked. This was not a blocked-Policy/RST test.

The environment-specific helpers and invocation are in [`scripts/passive-demo/README.md`](../scripts/passive-demo/README.md). The Client helper pins the route/source and removes its temporary `/32` route on exit. The Gateway helper arms a 10-minute cleanup timer.

## Observed results — 1 October UTC / 2 October Taipei

| Phase | Time (UTC / Taipei) | Client HTTPS result | NPB evidence |
| --- | --- | --- | --- |
| `ens38` connected | 22:35:11 / 06:35:11 | HTTP 200, exit 0, 0.233153 s | Row `174121` at 22:35:12 UTC: HTTPS 1, RX 57, TLS TX 1 |
| `ens38` down | 22:36:11 / 06:36:11 | HTTP 200, exit 0, 0.170660 s | No row matched the request time. Fourteen nonzero rows existed above baseline `173689`; last was `174222`. |
| `ens38` reconnected | 22:36:47 / 06:36:47 | HTTP 200, exit 0, 0.159134 s | Row `174217` at 22:36:48 UTC: HTTPS 1, RX 38, TLS TX 1 |

The client request succeeded in all three phases, and NPB telemetry resumed after reconnection. `tc` mirror counters after the phases were 59 packets / 3,449 bytes / 0 overlimits; 101 / 6,117 / 42; and 141 / 8,692 / 44. The `dropped` field was zero in all samples. `overlimits` here reflects mirror failures while the target was down, not the `dropped` counter; two additional overlimits accrued while down before reconnection. These counters do not quantify lost client traffic.

## Cleanup and limits

Cleanup was verified: `ip_forward=0`, `ens38` down with promiscuous mode off, no test `tc` filters, no owned iptables rules, and no cleanup timer. The Client had no temporary host route and was back to gateway `192.168.31.2` with source `192.168.31.39`. Policy and NPB remained active; TRex remained stopped. No PCAP was generated for this test.

This demonstrates that the client request succeeded while the mirrored NPB/Policy branch was unavailable and that observation resumed after reconnection. It does not test Gateway failure, hardware TAP behavior, or blocked-policy reset delivery.
