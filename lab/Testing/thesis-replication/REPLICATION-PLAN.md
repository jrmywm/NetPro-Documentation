# Thesis replication checkpoint — 13 October 2026 (Asia/Taipei)

## Active scope

Per the professor's instruction, run Bintang and Ibrahim first. Luthfi and Rafie are deferred; their missing sources do not block the current two-thesis work.

## Success criterion

Reproduce the experiment's workload, measurement definitions and output tables. Collect our own results, including failures. Matching the author's numerical performance is not a predetermined pass criterion on different hardware. Never substitute target PPS for achieved PPS, generated injection packets for client-confirmed blocking, or module tests for live integration.

## Source-grounded experiment matrix

| Thesis | Experiment to reproduce | Measurements | Current gap |
|---|---|---|---|
| Bintang | Blocked-domain HTTP events: 1,000 packets, repeated runs; extended 10,000-packet timing scenario; summary at 120 seconds; SNMP polling of PS/NPB/monitoring host | Input events, traps attempted/sent/received, duplicate/missing traps, RST observations, elapsed time and intervals, CPU/RSS; polling evidence | Existing verified reporter emits aggregate counters. Domain-event traps and Zabbix polling have not been demonstrated. Original Bintang branch must be evaluated in isolation. |
| Ibrahim | Local QUIC v1 endpoint, 30-second trials at configured 100/200/500/1,000/1,500 PPS, 3 trials each | Actual positive Initial packets, Connection Close sent/captured, per-trial ratio, mean/sample SD, CPU/RSS, achieved PPS | Offline parser is insufficient. Requires Connection Close generation, QUIC client/server, classifier forwarding and candidate dataplane integration. Original branch is available in saved audit sources. |
| Luthfi | CSV bulk upload, chunk size 10,000; sizes 100/1k/10k/100k/500k/1M/5M/10M; repetition plan of 10; validation/progress and concurrency cases | End-to-end/API time, imported/rejected/duplicate rows, throughput, WebSocket completion, CPU/RSS sampled every 2 seconds | Bulk/chunk/progress source not found in audited repositories. Original code needed for faithful replication; separately authorized reimplementation would be labelled reconstructed. Reset only a dedicated test database, never existing project policies. |
| Rafie | Eight lookup variants; indexed/nonindexed SQLite, Bloom/Counting Bloom Filter, multi-tier LRU; dataset sizes through 10M; uniform and Zipf workloads of 100k unique domains/1M requests, alpha 0.8/1.0/1.2, bursts 3x/5x/10x | Correct allow/block results, lookup throughput/batch latency, cache hit/miss, SQLite query reduction, false positives, memory, CPU, deletion consistency | Original implementation, precise workload generator and raw datasets not found. Same-code numerical replication is blocked until source is supplied. Reconstructed benchmark needs distinct labelling. |

## Discrepancies to retain

- Bintang's 1,000/10,000 trap narrative and interval totals do not fully specify one reproducible procedure. Keep each scenario separate and disclose missing parameters rather than invent them.
- Ibrahim's thesis success metric counts Close packets sent, not guaranteed client denial. Record that ratio plus client outcomes separately.
- Rafie's memory and false-positive summary statements disagree with detailed tables. Preserve table definitions and report independently measured values.
- Luthfi's large chunk=1 comparison includes estimates. Do not present estimates as replicated measurements.
- Linux/VMware results differ in platform from thesis test hosts. Record CPU, assigned RAM, OS, software versions, configuration, source and binary hashes.

## Execution sequence and safeguards

1. Start required VMs with existing settings; record VMware outcomes. Check strict SSH identities, memory pressure, services, interfaces and topology.
2. Preserve the current SQLite four-ID baseline and backend rules. The existing binary has a known shutdown deletion hazard. A compiled lifecycle candidate exists, but service-level restart validation is still pending. Back up and validate before any candidate rollout; restore narrowly, never wipe existing DBs.
3. Establish original HTTP/TLS/TAP baseline after cold boot; record exact binaries/configuration. Resolve unexpected symlink or service state before calling the old result current.
4. Prepare isolated SNMP event and periodic tests. Verify receiver receipt and timing; do not replace the production service merely to get trap counts.
5. Prepare isolated QUIC v1 endpoint and candidate path. Gate on authenticated packet correctness and low-rate functional Close capture before the 15 load trials. Stop on resource or correctness failure.
6. Defer Luthfi/Rafie until the professor requests them. If resumed, obtain original sources or explicitly label separately authorized reconstructions; use only dedicated disposable databases.
7. Export raw JSON/CSV/logs/PCAP, source hashes, commands, tables and limitations. Only mark a row replicated when the actual experiment has run.

## Status at creation

The original checkpoint was created before experiments ran. For subsequent measured results and remaining gaps, see FINDINGS-2026-10-13.md. No source changes are pushed to Network-Laboratory-UI repositories.
