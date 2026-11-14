# Automatic gateway controller and shared IP test

14 November 2026. The temporary controller automatically observed the actual applied Policy Server policy and updated gateway rules across three add/delete cycles. Shared-IP collateral blocking was confirmed. This experiment does not establish general selective domain enforcement.

## Results

| Observation | Result |
|---|---|
| Automatic policy creation and gateway activation | 3/3 cycles |
| Automatic policy deletion and gateway rule removal | 3/3 cycles |
| HTTP/3 and TLS target denial after activation | 18/18 blocked |
| Access before policy and after removal, both hostnames | 72/72 HTTP 200 |
| Unblocked hostname during target deny on shared IP | 18/18 also blocked, an undesired side effect |
| Origin requests during each deny phase | 0 additional requests |
| Controller errors | 0 |
| Owned DROP rules | Exactly two, with nonzero UDP and TCP counters |

108 observations matched the anticipated behavior, but calling them 108 successful selective-domain blocks would be wrong: 18 explicitly demonstrate collateral damage. The two hostnames mysite.local and allowed-router.test shared 198.18.0.2 and were both served by Caddy. Only mysite.local was added as a policy. IP-based enforcement nevertheless blocked both.

## Controller

A temporary Python worker on the Windows management workstation polls the actual Policy Server SQLite database over verified SSH about every 250 ms plus command duration. Its own SSH sessions are independent of the test harness. It only watches the exact lab domain/IP and verifies a unique UUID. It creates or removes source/destination/port-scoped TCP/UDP FORWARD drops over verified SSH, using existence checks to avoid duplicates. The test driver changes policies only through the Backend API and waits for the worker to confirm gateway state; it does not call the firewall update function itself.

The worker ran during this experiment, not as an installed boot service. It is not a generic policy distribution API. On error it reports failure and retains the last rule state until the experiment cleanup or rollback timer. Production authentication/authorization design, persistence, expiration, failure behavior and restart recovery still require implementation and testing. A preliminary startup failed because the Policy VM sqlite3 CLI lacked JSON output; the controller was changed to a read-only Python SQLite query before the measured run.

## Timing

The interval from starting the API creation to confirmed gateway enforcement was 0.405, 0.301 and 0.276 seconds. API deletion to confirmed removal was 0.320, 0.542 and 0.405 seconds. These are six end-to-end control-plane observations including API, publication, Policy Server state checks and SSH reconciliation. They are not per-packet latency, a propagation SLA or measurements of the first request during propagation. Probes start after gateway state is confirmed; exposure during updates remains untested.

## Topology and mechanism isolation

The client routed through the existing gateway to an isolated Caddy network namespace on that VM. TCP/UDP traversed FORWARD. There was no artificial response delay on this origin; injected QUIC Close from that origin was suppressed. The gateway's original 15 ms setting applied only to its original origin and was not used by this routed experiment.

Three cycles each tested before/deny/after with three probes per hostname and protocol. Cumulative origin request counts were 12/12/24, 36/36/48 and 60/60/72, showing no increase during deny. Gateway counters and origin counts support actual traffic dropping.

## Cleanup

Controller stopped; temporary policies, route, firewall rules, origin, namespace and veth were removed. Live checks confirmed no owned rules/route/namespace remained, original ip_forward=0 and the persistent scoped 15 ms configuration were intact, and original-origin HTTP/3 returned HTTP 200. Policy synchronization and filter were valid with zero lookup errors and shadow mismatches.

## Verdict

Automatic dedicated-IP enforcement is feasible in this lab. It is not appropriate as a general domain blocker for shared hosting. The next design task is domain-to-flow identification with scoped flow rules, or an explicitly different enforcement mechanism. Neither was implemented by this experiment. Established sessions, migration and ECH remain outside the tested scope.
