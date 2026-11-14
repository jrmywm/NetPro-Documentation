# Direct Policy Server comparison — 13 October 2026

## Purpose and bounded topology change

Test whether removing NPB observation and gateway injection redirection makes
the recovered Ibrahim QUIC mechanism reproduce its functional timeout result.
No new VM, Proxmox migration, inline gate, server delay or UDP firewall drop.

Only Policy-Server-VM changed, while powered off gracefully:

- Adapter 3 / ethernet2: NetPro-TLS -> NetPro-TAP-Client (direct observation).
- Adapter 4 / ethernet3: NetPro-RST -> NetPro-TAP-Client (direct injection).

Management and HTTP adapters, all other VMs and the TAP bridge configuration
were left unchanged. Direct observation was empirically verified by PS receive
counters and authenticated client captures; it was not assumed from VMware
promiscuous-mode behavior. This is a shorter VMware comparison, not an exact
recreation of Proxmox's shared flooding bridge.

The NPB service remained on its original binary; QUIC traffic reached PS
directly rather than through NPB. Existing PS binary restored after each
candidate run. Original adapter mappings restored after both tests.

## Test settings

- Local Caddy `mysite.local`, 192.168.80.28:443.
- Actual HTTP3-enabled curl with `--http3 --max-time 5 -k -v`.
- Test client 192.168.80.29; bind and resolve options fix the intended lab path.
- TCP fallback blocked only from that client to the local Caddy TCP/443.
- Temporary SNI policy uses unrelated IP 192.0.2.124; no IP-match shortcut.
- Client-facing original Close only; 0x02 CONNECTION_REFUSED retained.
- SNMP hooks disabled to isolate Ibrahim's standalone QUIC workload.
- Original crypto/parser/crafter plus documented bounds/allocation/thread-key
  compatibility fixes. Candidate SHA:
  85849e8369a83a88c4cc070084c4dbb75925622ccd4d180b6c072cd0551ffa35.

## Complete request outcomes

| Run | Candidate allow before rule | Deny with rule | Allow after deleting rule |
| --- | --- | --- | --- |
| 024214Z | 5/5 HTTP 200, version 3 | 5/5 HTTP 000, curl 28 timeout | 5/5 HTTP 200, version 3 |
| 024422Z | 5/5 HTTP 200, version 3 | 2/5 timeout; 3/5 escaped with HTTP 200, version 3 | 5/5 HTTP 200, version 3 |

Combined: 7/10 complete requests denied; 20/20 candidate allow controls passed.
Six additional original-binary allow controls also passed. This small sample
is not a reliability estimate under load or a match to thesis performance.

## Client-capture timing and authentication

| Run | Captured authenticated Close connections | Mean Initial-to-Close | Mean Initial-to-Handshake | Handshake before/same timestamp as Close |
| --- | --- | --- | --- | --- |
| 024214Z | 10,139 | 0.421723 ms | 5.569515 ms | 1 |
| 024422Z | 6,542 | 0.393799 ms | 3.946510 ms | 5 |

All analyzed Close packets authenticated; zero authentication errors. Final
PS counters exactly matched captured Close counts in both runs, with zero TX
errors. Delays use one client capture clock. Distinct connections are grouped
by client SCID to avoid confusing reused UDP source ports.

Thousands of events are curl retries inside ten scripted deny requests, NOT
thousands of independently successful deny requests. Handshake timing uses
explicit QUIC v1 Handshake identification, including coalesced Initial plus
Handshake datagrams. Same capture timestamp cannot determine processing order.

The previous longer-topology profile averaged 1.857761 ms to Close and failed
all five deny requests. The shorter path markedly improved observed Close
timing, but changes both observation and injection paths together; this does
not isolate a separate cost for NPB, gateway redirection or VM scheduling.
Server timing/workload also differed because retry behavior changed.

## Interpretation

The first round reproduced the thesis's functional timeout. The repeat showed
that this is not yet dependable. Average speed is insufficient: curl retries
many times, so a rare timing escape can still complete a whole HTTP request.
No evidence justifies claiming VMware itself is the root cause or migrating
the entire project to Proxmox now.

Further thesis-fidelity checks should investigate original client-library
versions/retry behavior, original flooding topology and timing tails, while
separately reporting Close-TX ratio and complete request denial. Do not present
7/10 here as comparable to the thesis's packet-level 87.8–98.1% metric.

## Evidence and recovery

- `evidence/live-direct-profile-20261013T024214Z/`
- `evidence/live-direct-profile-20261013T024422Z/`
- Both contain client PCAP, authenticated close analysis, timing summary,
  trial summary, candidate rollout and API/SQLite cleanup evidence.
- Original VMX saved under `evidence/direct-topology-vmx-20261013/`.
- Protected SQLite online backups and ID/integrity checks before both VM
  shutdowns: `evidence/policy-shutdown-20261013T024013Z/` and `...T024606Z/`.
- Policy VM adapters restored to NetPro-TLS and NetPro-RST; VM restarted.
- Temporary policies, fallback firewall rules and owned test timers removed.
- No upstream repository push; installed thesis tools remain available.
- Post-restoration TLS regression evidence is recorded separately under
  `evidence/tls-regression-after-direct-20261013/`.
  Workflow exit 0: 20/20 expected TLS resets and 20/20 HTTP 200 allow results.
  Original binary hashes, SQLite integrity/IDs and restored adapter segments
  were verified in `evidence/direct-topology-vmx-20261013/postflight.json`.
