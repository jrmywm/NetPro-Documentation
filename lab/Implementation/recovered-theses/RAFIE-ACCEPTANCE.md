# Rafie lookup integration — 31 October 2026

**Fidelity qualification:** this records functional acceptance of an adapted combination of variants. The risk-tier selection, deletion method and missing domain index differ from the thesis. See [the 31 October fidelity audit](THESIS-FIDELITY-AUDIT-2026-10-31.md).

Rafie's recovered lookup architecture is now adapted into the **running HTTP/TLS Policy Server**, with the deployed service left in `NETPRO_LOOKUP_MODE=rafie`. No additional VM is required. This is labelled adapted code, rather than a claim that the recovered tiered checker already had correct LRU/counting behavior.

## What is installed

The exact-domain lookup path now uses:

1. A hash-indexed, preloaded set of up to 100 **existing policies**. These are selected deterministically, not ranked as high risk.
2. A bounded, hash-indexed **true LRU** containing both allowed and blocked decisions and their policy IDs; capacity 20,000 entries.
3. Rafie's three hash families and **65,536 packed four-bit Counting Bloom cells**, occupying 32 KiB.
4. A prepared SQLite query to confirm filter positives. A filter positive alone never blocks a domain.

All authoritative domain rows are loaded; the original 1,000/10,000-row initialization caps are removed. Domain matching remains exact and case-sensitive. Policy IDs are retained so existing hit-count telemetry keeps working. IP enforcement remains the existing path, serialized with policy updates.

Updates invalidate every lookup tier after a successful database commit. The next domain query rebuilds the full filter from a coherent SQLite scan. Counters saturate rather than wrap; deletion uses rebuilding, never decrements of saturated cells. SQLite data/schema versions and same-connection changes invalidate unannounced changes. Failed/incomplete rebuilds fall back to SQLite rather than trusting Bloom negatives.

The Kafka writer has its own connection. Cache operations, mutations and hit collection share a mutex. Policy mutations use bound prepared statements and retry temporary SQLite locks. The service now retains its policy database at graceful shutdown.

## Actual acceptance results

| Test | Observed result |
| --- | --- |
| Module correctness | 12 cases passed: all 15,001 blocked domains and IDs, 2,000 nonmembers, exact LRU eviction, updates, external commits, restart and error paths |
| Saturation/deletion | 100,000-row fixture saturated counters; after 90,000 deletions, all 10,000 surviving domains still blocked correctly |
| Actual compiled Policy Server handler | 4 cases passed: create/replay/rename/delete, 40 add/delete cycles, three concurrent lookup threads against 300 add/delete cycles, temporary reader-lock retry |
| Sanitizers | Module and actual-handler suites passed AddressSanitizer and UndefinedBehaviorSanitizer with leak checking |
| Live shadow mode | 20/20 allow before add; 20/20 deny after add; 20/20 split ClientHello deny; 20/20 allow after delete |
| Live enabled mode | Same four phases: 20/20 each |
| Shadow comparison | 0 decision/ID differences from direct SQLite; actual returned SQLite decisions drove shadow-mode behavior |
| Active cache counters | 80 queries, 40 preloaded hits, 38 LRU hits, 2 Bloom negatives, 3 rebuilds, 0 lookup errors in each four-phase live run |
| Luthfi regression with Rafie enabled | 1,001 CSV policies reached the active Policy Server with exact UUID/domain/IP digest; all removed and exact baseline restored |
| Restart/post-import reconstruction | Kafka caught up; exact four-row baseline retained; another 20/20 TLS requests allowed; filter rebuilt to 4 rows with 0 errors |
| Build | Actual DPDK binary compiled; repository Makefile independently rebuilt the candidate successfully |

These are actual client requests through Client → Virtual TAP → NPB → Policy Server and the configured reset-return path. The active tests deliberately warmed an allow decision before adding a rule and a block decision before removing it. Test policies, accounts and helper processes were cleaned up; the original four SQLite rows and one authoritative backend row remain.

## Performance evidence and its limits

The local **standalone mixed lookup** comparison used the same 15,001-row in-memory database and the same 3,000 queries: 80% repeated listed domains, 20% unique absent domains, no domain index. Every result and returned policy ID was compared; differences: **0**.

| Measurement | Direct SQLite | Adapted tiers |
| --- | ---: | ---: |
| Queries actually processed | 3,000 | 3,000 |
| Total time | 1.743924 s | 0.084388 s |
| Queries/s | 1,720 | 35,550 |
| p50 | 584.941 µs | 3.135 µs |
| p95 | 999.891 µs | 8.268 µs |
| p99 | 1,207.816 µs | 662.772 µs |

The optimized measurement includes initial filter construction. Its 52 Bloom false positives were checked against SQLite and correctly allowed. The 4,880 KiB peak RSS belongs to the **entire standalone benchmark process**, not just the filter or deployed DPDK service.

This comparison is **not** against the complete old Policy Server cache, does not measure full-network throughput/latency, and does not reproduce the thesis hardware/results. A separate repeated-hit benchmark **with a domain index** processed 30,000 queries in 0.111214 s with prepared SQLite versus 0.139319 s with guarded tiers: the extra consistency checks can cost more than an already cheap indexed lookup. We therefore claim measured functional integration and workload-dependent lookup improvement, not universal speedup.

Still to measure: sustained imports while forwarding traffic, representative larger datasets/workloads, cache memory at full occupancy, update/rebuild latency, and complete-system performance. The separately built experimental original QUIC implementation has not been ported to this new lookup adapter; these tests add no new QUIC blocking claim.

## Findings fixed during this integration

- A schema change could evade same-connection row-change tracking. Schema-version checking now prevents stale cached results after DDL/errors.
- The first shadow rollout found skipped deletion events during SQLite lock contention. That rollout automatically reverted; the exact baseline returned. The accepted version waits/retries, and a dedicated actual-handler lock test reproduces and verifies the correction.
- A freshly started service could momentarily have the expected baseline **before** replaying old Kafka events. Readiness now includes the startup Kafka high-water mark and consumed offset. Test/mode-switch scripts wait for catch-up and exact baseline preservation. Startup replay itself remains inherited behavior; zero-interruption restart enforcement is not established.
- The inherited logger could dereference a null file handle during test-log rotation. A guard prevents that crash.

## Deployed paths, modes and evidence

Policy VM: `192.168.31.31`; source: `/home/netpro/NetPro-Policy-Server`; service: `netpro-policy`.

Active binary: `build/policyServer-rafie-20261031T023646Z`, selected by `build/policyServer`.

Mode configuration: `/etc/systemd/system/netpro-policy.service.d/rafie-cache.conf`.

Current status/counters:

```bash
sudo cat /run/netpro-policy-cache.json | python3 -m json.tool
```

`policySyncReady: true` confirms the startup historical Kafka replay has caught up. `filterValid: false` immediately after restart is expected until the first lookup performs lazy reconstruction. `mode` distinguishes enforcement from shadow comparison.

For controlled comparisons, the guarded mode selector accepts `legacy`, `shadow` and `rafie`. **It restarts Policy Server**, so run it outside an active test:

```bash
sudo python3 /home/netpro/incoming/rafie-integration-20261031/select-mode.py shadow
sudo python3 /home/netpro/incoming/rafie-integration-20261031/select-mode.py rafie
```

`legacy` disables the new lookup tiers while retaining the corrected mutation/lifecycle code. It is not a byte-for-byte rollback to the old binary.

Accepted rollout backups:

- `/root/netpro-rafie-20261031T023327Z/` — previous source, binary, symlink and SQLite snapshot.
- `/root/netpro-rafie-readiness-20261031T023646Z/` — readiness upgrade rollback source/binary selection.

Code rollback must preserve current policy data; do not overwrite live SQLite with a historical snapshot as a routine rollback step.

Raw evidence: local `evidence/rafie-20261031/`, `evidence/rafie-live-20261031T023723Z/`, and `evidence/rafie-postimport-20261031T024027Z/`. Remote build/test logs: `/home/netpro/incoming/rafie-integration-20261031/`. Deployment command logs remain under sibling `thesis-stack/evidence/`.

Compact, versioned acceptance: `test-results/rafie-functional.json`. Module provenance and deviations: `rafie/PROVENANCE.md`. Immutable thesis sources remain unchanged.

Policy Server local commit: `57a45ea`. No upstream push; unrelated configuration, logs and pre-existing backup files were preserved. No handoff file was updated.
