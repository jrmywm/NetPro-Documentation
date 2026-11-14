# QUIC enforcement plan — 13 October 2026

## Objective and scope

Make new HTTP/3 connections obey the actual NetPro domain policy without relying on an injected Close beating the origin handshake. Keep the recovered Ibrahim implementation and its replication results unchanged as a separate baseline. An inline decision gate is a proposed NetPro extension, not an original thesis feature or a passive hardware TAP.

Current evidence: allow controls succeed; Close-only deny still permits HTTP/3 200; a scoped static UDP drop prevents completion. The static drop is only a control and does not prove that policy-driven enforcement is implemented. A captured, authenticated Close does not establish acceptance by the client's QUIC stack.

## 1. Preserve baseline and improve evidence

- Snapshot source/binary hashes, VM network mappings, exact policy rows, TAP bridge/mirror configuration and existing firewall state.
- Preserve recovered source; use separate candidate builds and guarded rollback. Do not push to upstream repositories.
- Give captures host-and-interface filenames so Gateway captures cannot overwrite each other.
- Use client-local packet and curl timestamps for packet ordering. Record host/guest clock offsets; do not compare different clocks directly.
- Re-run a short allow–deny–allow Close-only baseline. Count completed HTTP requests separately from Initial packets, retries and Close transmissions.

Checkpoint: restore the exact baseline after the run and retain raw traces/captures.

## 2. Prove the interception point, without changing production defaults

First choice: the existing Virtual TAP bridge, because it precedes the origin. Inspect its real interfaces/hooks before selecting rules. Prototype a narrowly scoped Netfilter userspace queue (NFQUEUE), subject to verifying bridge support and packet ordering on the installed kernel. Gateway INPUT is acceptable only as a local-Caddy diagnostic, not the final general-network design.

For selected lab client traffic: create the observation copy before holding the original. Verify that NPB/Policy Server receives that copy while the origin does not receive the queued original. Never assume the existing mirror and queue hooks execute in the required order.

Limit initial rules to the known client, Caddy address and UDP/443. Keep management, ARP and unrelated traffic untouched. Use queue limits, a bounded watchdog and automatic removal of only test-owned configuration.

Checkpoint: manually release one queued request and observe HTTP/3 200; manually drop it and observe no origin delivery. This remains a mechanism test, not a policy test.

## 3. Couple the queue to the real Policy Server

Keep the existing TAP → NPB → Policy Server observation path and recovered QUIC parser/policy lookup. Add a separate, restricted verdict channel back to the gate. Do not use Kafka telemetry as the synchronous verdict path.

The Policy Server must emit explicit ALLOW, DENY or UNSUPPORTED decisions, not only the current positive-deny notification. Correlate decisions using a request identifier, tuple, the client SCID from the QUIC Initial and policy generation. A first/new client SCID Initial must wait for a verdict before release. An allowed continuation Initial with the same client tuple and same non-empty SCID may pass under that decision; a different SCID on a reused tuple is a new flow and must be reclassified, not inherit the prior allowance. An empty client SCID is unsupported and must receive an explicit UNSUPPORTED outcome (never an implicit allow). Bound decision lifetimes and reject stale/unmatched messages. Restrict the channel to the gate and Policy Server.

- ALLOW: release held packets once, preserving order; keep bounded state for a same-tuple, same-SCID Initial continuation. A changed SCID requires a fresh verdict.
- DENY: discard held packets and prevent retries from escaping. New connections must be classified again. Retain the thesis Close path as a separately measured notification, not the condition for successful blocking.
- UNSUPPORTED/timeout: report an explicit outcome; never silently label it ALLOW or a successful SNI deny. For the scoped enforcement test, use a clearly documented fail-closed default; assess fail-open separately and do not claim both guaranteed availability and guaranteed blocking.

Start with fresh connections and the parser's currently supported Initial format. Fragmented CRYPTO, unsupported QUIC versions, empty client SCID, ECH, IPv6 and connection migration need explicit UNSUPPORTED/scope results, not implicit support claims. Do not assume all UDP/443 traffic is QUIC. This gate does not immediately revoke an already-established or previously allowed QUIC connection when policy changes; established-flow revocation is separate work and must not be promised by this prototype.

Checkpoint: adding/removing the real backend policy changes the gate's decision without manually adding a per-domain firewall rule. An allowed and denied domain sharing an origin IP must behave differently.

## 4. Functional verification

Use actual Caddy and HTTP/3-enabled curl with --http3-only, not HTTP/2 fallback. Run at least 20 fresh requests per main phase:

1. No rule: 20/20 HTTP/3 200.
2. For a new client SCID, verify the first Initial is held for a verdict. With an allowed verdict, verify a same-tuple/same-SCID continuation Initial passes; with a changed SCID on the same tuple, verify it is reclassified and waits for a new verdict.
3. Add denied-domain policy and verify Policy Server synchronization: 20/20 denied, zero denied requests completed at Caddy.
4. Keep that rule and request an allowed domain on the same IP: 20/20 HTTP/3 200.
5. Verify empty-SCID Initials return UNSUPPORTED and are not silently allowed. Delete the rule and confirm synchronization: 20/20 HTTP/3 200 for new SCIDs.
6. Repeat switching and concurrent clients to check stale decisions, retries, queue limits and cross-flow leakage. Treat established-flow revocation separately; passing this new-connection gate does not demonstrate immediate revocation.

Capture both sides of the gate, origin traffic and relevant return traffic; save verdicts, policy generation, queue/drop counters, curl results and Caddy request logs. Test policy-worker disconnection and queue saturation separately. Confirm existing TCP/TLS blocking and Bintang SNMP/Zabbix integration still operate. Measure Close-only and gate-only modes separately so success is attributed to the actual mechanism.

Existing established HTTP/3 connections are a separate revocation test. Do not promise immediate browser-tab blocking from a new-connection-only prototype. Test a normal browser only after the controlled HTTP/3-only tests pass, including fallback and connection reuse.

## 5. Load, documentation and demo

After functional acceptance, repeat the same workload at concurrency 1, 4, 8 and 16. Record request success/deny rates, throughput, p50/p95/p99 latency, verdict delay, queue occupancy/drops and CPU/RAM. Compare against the Close-only baseline using the same lab hardware and workload; do not claim identical thesis performance.

Deliver a repeatable start/test/stop workflow, raw evidence, rollback verification, topology diagram and demo commands. Clearly distinguish: original thesis replication, integrated observation/Close injection, and new inline enforcement extension. No new VM is planned. Do not migrate to OVS or two-port architecture in this workstream.

## Technical references

- NFQUEUE's userspace accept/drop verdict model: https://netfilter.org/projects/libnetfilter_queue/doxygen/html/
- QUIC connection and migration behavior: https://www.rfc-editor.org/rfc/rfc9000.html

Status: scoped inline-gate extension functionally verified on the lab path above, with five- and 20-request phases plus a bounded concurrency 1/4/8/16 comparison. Candidate runtime overrides were temporary and original services were restored. This does not establish physical TAP fail-open behavior, meaningful load performance, general QUIC coverage or established-session revocation; continue with the remaining validation items above.
