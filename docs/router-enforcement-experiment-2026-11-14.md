# Gateway enforcement experiment 14 November 2026

## Result

A temporary Linux gateway firewall enforced the applied test policy by dropping original packets, rather than relying on the client accepting an injected QUIC Close. No additional VM was needed. This is an experimental extension, not a reproduction of the four theses' injected-packet method, and it is not permanently enabled.

## Two tests

1. Gateway-local Caddy: five HTTP/3 requests in each allow/deny/allow phase. The added response delay was set to zero and injected QUIC Close packets were suppressed at ens38. All 15 HTTP/3 checks passed. An additional 15 TCP/TLS checks exercised existing TCP reset behavior, not the new UDP firewall mechanism. Final corrected suite passed 30/30.
2. Actual transit: a temporary network namespace on the gateway hosted a separate Caddy origin at 198.18.0.2:443. A veth link provided the origin network, and the client routed this host through 192.168.80.28. Thus original packets traversed the gateway FORWARD hook. No extra delay applied to this origin. QUIC Close injection from that origin was suppressed.

Transit results:

| Phase | HTTP/3 | TLS | Origin request count cumulative |
|---|---|---|---|
| Before policy | 5/5 HTTP 200 | 5/5 HTTP 200 | 10 |
| Applied policy and gateway rule | 5/5 blocked | 5/5 blocked | 10 |
| Policy and gateway rule removed | 5/5 HTTP 200 | 5/5 HTTP 200 | 20 |

Both UDP and TCP FORWARD drop counters increased (10 UDP packets, 10 TCP packets). The origin received zero additional requests during deny. These are packet counters, not counts of independent requests. Overall transit acceptance passed 30/30.

## How the policy controls the router

The test creates its own policy through the Backend API and waits for the exact rule to appear at the Policy Server. An explicit reconciliation function reads the rule from Policy Server SQLite, checks its ID/domain/IP, then installs two source/destination/port-scoped gateway drops. After deletion reaches Policy Server, reconciliation removes them. This demonstrates a policy-to-firewall control path.

This is NOT an autonomous always-running controller and does not install rules based on individual packet-inspection events. It is dedicated-IP enforcement of TCP/UDP port 443, not selective SNI enforcement for multiple domains sharing an IP. Requests are tested after rule installation is confirmed; first-request exposure during propagation and synchronization latency remain unmeasured. Existing established flows, QUIC migration and ECH are not evaluated.

## Cleanup and original deployment

Rollback timers were armed before mutations. The temporary policy, FORWARD/INPUT rules, client route, injection-suppression filters, origin service, network namespace and veth were removed. The original ip_forward=0 and persistent 15 ms lab configuration were restored. Fresh verification confirmed gateway/client cleanup. The original deployment then passed its separate 18/18 HTTP/3/TLS/fallback allow-deny-allow suite.

Two preliminary harness issues were retained in local evidence: the first local test incorrectly expected TLS to remain allowed despite the existing domain policy, and the first transit attempt started before Caddy's UDP listener was ready. Readiness checking and cleanup robustness were corrected before the final transit acceptance.

## Scripts and evidence

- `lab/Testing/router-enforcement/try_gateway_enforcement.py`: temporary local gateway experiment.
- `lab/Testing/router-enforcement/try_transit_router.py`: routed Caddy experiment with exact policy guards and rollback.
- `evidence/router-enforcement-2026-11-14/local/`: final local results.
- `evidence/router-enforcement-2026-11-14/transit/`: routed results, firewall counters and cleanup checks.
- Local raw command records remain in Testing/router-enforcement/evidence. These scripts require verified SSH host keys, NETPRO_LAB_PASSWORD, and this lab's paths/interfaces. Do not use them unchanged on other networks.

The next implementation step is a reviewed controller with authenticated updates, idempotent reconciliation, rule expiry/deletion and measurements of policy propagation. Domain-specific flow enforcement would need additional flow identification and management. No persistent controller was installed in this experiment.

## Allowed traffic timing

A separate 800-request ABBA comparison measured allowed traffic on the same routed topology. See [latency methods and results](router-enforcement-latency-2026-11-14.md).
