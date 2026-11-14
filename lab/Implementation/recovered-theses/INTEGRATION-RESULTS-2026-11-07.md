# Integration results — 7 November 2026

## Outcome

The Rafie comparison and recovered Luthfi worker baseline have now been run. Bintang monitoring is merged into the active Rafie/retry build: actual TLS domain events reach Net-SNMP and Zabbix. Live CSV propagation and CSV-driven TLS regression pass on that build. The combined recovered QUIC candidate compiles and parses traffic, but its full-path blocking acceptance fails; it was restored to the accepted HTTP/TLS build after testing. This is not completion of all five requested acceptance steps.

## 1. Preserved baseline

Six VMs remain in use. Management services, Kafka, PostgreSQL, nginx, Net-SNMP receiver and Zabbix are active at final check. Policy Server mode is rafie, policySyncReady=true, filterValid=true, loadedRows=4, shadowMismatches=0 and errors=0. Temporary accounts, policy rules and packet helpers from the CSV test were cleaned up. Original source archives remain unchanged.

Kafka bootstrap in the merged build now uses consolidated Management 192.168.31.35:9092, rather than historical 192.168.0.90. Startup retry remains included. The temporary rollout helper now tolerates transient SQLite locks and can wait for replay readiness. These are integration/test-harness corrections, not QUIC algorithm changes.

## 2. Rafie variant comparison

The unchanged recovered tiered and counting implementations were invoked through a wrapper that renames their CLI main only. Their lookup/initialization functions were not rewritten. Indexed in-memory SQLite, dataset and 3,000-query trace are identical for each process: 80% listed domains, alternating low and high IDs, and 20% absent domains. Three independent process runs were performed per variant/dataset. Initialization and lookup times are separate; values below are median lookup QPS, not packet throughput.

| Rows | Indexed SQLite | Recovered tiered bit filter | Recovered counting filter | Adapted guarded tiers |
|---|---:|---:|---:|---:|
| 1,000 | 237,077 | 505,658 | 1,959,630 | 272,814 |
| 15,001 | 288,897 | 1,013,479* | 2,157,047* | 282,745 |

All variants make zero wrong decisions on 1,000 rows. At 15,001 rows, recovered tiered makes 930 wrong decisions and recovered counting makes 1,200 in the 3,000-query trace. Their rates marked * are therefore not valid correct-lookup speedups. Initialization scan caps cause incomplete filter coverage; Bloom negatives can incorrectly allow listed domains. The adaptation and SQLite match on all tested queries. This indexed workload does not show a universal adaptation speedup.

Recovered tiered uses 65,536 bits (8 KiB); recovered counting uses 65,536 four-bit counters (32 KiB). The recovered high-risk tier is a case-sensitive phish/malware/trojan/exploit substring heuristic limited to the first 100 scanned domains, not a missing curated dataset. The live adaptation still combines corrected counting/LRU/full-coverage behavior and ID-selected preloading; it is explicitly an adaptation, not unchanged replication. Do not deploy the source variants with known false negatives merely to match a filename. The final intended thesis variant/high-risk behavior needs an explicit research-design choice before calling strict replication complete.

Evidence: evidence/variant-comparison-20261106T230122Z; source SHA256 values and wrappers retained. Active domain index was previously installed and EXPLAIN verified.

## 3. Bintang monitoring integrated

Active build: policyServer-monitoring-20261106T230726Z. It includes current Rafie lookup, startup retry and recovered Net-SNMP CLI count/summary mechanism. The missing per-domain function remains labelled reconstructed, as does the lab Zabbix configuration. The bounded asynchronous domain worker is assigned to control CPU 0 so its CLI subprocesses do not inherit the packet-processing lcore affinity. Queue acceptance is not treated as delivery acknowledgement.

Actual blocked netpro-tap.test events appeared in the Management SNMP trap log and Zabbix history_log (six matching fresh history records in the sampled check). These were real policy-triggered events, not an injected test notification. Additional normal/split TLS regressions retained intermittent failures; these are not erased by the later passing run.

Fresh authenticated CSV load test applied all 1,001 policies with exact UUID/domain/IP digest, then removed all of them and restored the exact baseline. Final CSV-driven packet regression passed 20/20 in each phase: allow before activation, deny after CSV activation, deny segmented ClientHello, allow after CSV removal (80/80 total). Final cache had 80 queries, zero mismatches/errors, four loaded rows. This verifies the combined monitoring/cache build remains functional on the tested path; it does not establish universal reset reliability.

Evidence: evidence/monitoring-merge-20261106T230726Z, evidence/csv-live-load-20261106T231628Z.json, evidence/csv-packets-20261106T231700Z. Earlier failed packet runs: domain-index-20261106T230545Z, 230641Z and 230746Z. No failed trial is counted as a pass. The genuine periodic summary was also received at 23:17:38 UTC, with its original payload reporting zero in that sampled cycle; it is not interpreted as a cumulative blocked-domain total.

## 4. Luthfi recovered processing baseline

The actual recovered better-queue 3.8.12 queue and unchanged job.service.js ran with CHUNK_SIZE=10000, original transactions and built-in two-second chunk delays. Only database binding was injected into a fresh isolated PostgreSQL database; no application index.js or force-sync startup was invoked against live data. Original models and service files were preserved. Progress was collected through an emit fixture; this is not an original-browser or original-Socket.IO acceptance claim.

| Identical CSV input | Recovered queue/service | Adapted bounded processing core |
|---|---:|---:|
| 10,000 rows | 3.655 s; 10,000 inserted | 0.866 s; 10,000 inserted |
| 100,000 rows | 33.597 s; 100,000 inserted | 6.809 s; 100,000 inserted |

Input SHA256 values match exactly across both runs: 40a9db9502609ac20b20943d4b5ee976440f9f9e8fee4faa2a2e3e0ca766d18b and ea006e16ac870c132ec58bc7bb74b291fc1846252c9ca50bbbb291f566e27e08. The adapted run invokes the 1,000-row worker directly; it excludes persistent queue scheduling, HTTP upload, activation, Kafka and enforcement. Original timings include actual better-queue and deliberate per-chunk sleeps. This is a processing-baseline comparison, not equivalent full-pipeline performance or the thesis's 10-million-domain result. It does not justify removing durable jobs/outbox from the running system. Retain both implementations as separately labelled baselines.

Evidence: evidence/luthfi-original-20261106230840 and evidence/luthfi-adapted-20261106231017. Isolated databases are retained as evidence; they are not live policy stores.

## 5. Combined QUIC candidate acceptance — failed

Built a temporary candidate from the active monitoring/Rafie/retry source plus the recovered original parser/crypto/Close path. Real Caddy and HTTP/3 curl were used. Parser/SNI and Close crafting pass; ASan/UBSan gate rejects 1,200 truncated prefixes and passes 256 mutation-safety cases.

Full-path outcome:
- Original build allow: 3/3 HTTP/3 requests succeeded.
- Combined candidate allow: 5/5 succeeded.
- Deny rule: 0/5 denied; all five HTTP/3 requests completed.
- After rule deletion: 5/5 succeeded.
- Dedicated return path sent Close packets; independent capture analysis authenticates 29 corresponding Close flows with zero authentication failures.
- Median Initial-to-Close delay was 2.691 ms (range 2.000–10.175 ms). Server handshake preceded or coincided with Close on eight flows; Close preceded handshake on the other 21 captured pairs.

Therefore neither malformed Close authentication nor a blanket claim that every Close arrives after the handshake explains these results. Repeated attempts and client state/timing must be considered; one curl invocation is not necessarily one QUIC connection. No permanent QUIC rollout was made, because functional acceptance fails. The successful inline gate from earlier work remains separate and was not used to claim this result.

Candidate build and gate: sibling thesis-stack/evidence/original-candidate-build-20261106T231128Z. Full run, pcaps and independent timing: sibling thesis-stack/evidence/live-thesis-profile-20261106T231503Z. Automatic rollback restored NPB and Policy Server; subsequent CSV/TLS acceptance ran on the restored monitoring build.

## Remaining decisions and work

1. Strict Rafie source replication requires deciding which contradictory bit/counter specification and high-risk behavior is authoritative; corrected full-coverage adaptation remains the working system.
2. Monitoring integration is functional; 120-second summary semantics and broader load/reliability should be reported separately from the tested domain-event path. Bounded queue overflow/delivery failure monitoring still deserves coverage.
3. Luthfi original worker baseline now exists; a full original-vs-durable pipeline comparison must add identical scheduling/HTTP/publication scope, repeat counts and failure-recovery workload before choosing a replacement.
4. QUIC full-path injection is not accepted. Continue protocol/client retry diagnosis or explicitly choose an inline enforcement architecture. Do not relabel gate success as successful original passive Close injection.
