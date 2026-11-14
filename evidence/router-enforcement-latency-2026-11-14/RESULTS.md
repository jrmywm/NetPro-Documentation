# Allowed traffic latency with gateway enforcement

14 November 2026. All 800 measured requests succeeded; 40 warm-up requests were excluded.

| Protocol | Condition | Samples | Median ms | p95 ms | p99 ms |
|---|---|---:|---:|---:|---:|
| HTTP/3 | Baseline | 200 | 10.420 | 13.115 | 13.813 |
| HTTP/3 | Firewall rules enabled | 200 | 10.835 | 13.217 | 14.736 |
| TLS HTTP/1.1 | Baseline | 200 | 10.919 | 12.830 | 19.528 |
| TLS HTTP/1.1 | Firewall rules enabled | 200 | 10.296 | 13.220 | 14.553 |

HTTP/3 observed median difference was +0.415 ms (about 4.0%); TLS difference was -0.623 ms. These are observed differences, not isolated estimates of firewall CPU processing. HTTP/3 paired batch median differences ranged from -0.790 to +1.686 ms. A stable latency penalty was not established by this short run; the lower TLS values should not be interpreted as firewall acceleration. Tail percentiles are descriptive with only 200 observations per condition/protocol.

## Method

The identical client-to-gateway-to-network-namespace Caddy topology was retained in both conditions. There was no intentional delay on the benchmark origin. Baseline retained the same routing and scoped ACCEPT rules. Enforcement added two nonmatching FORWARD DROP rules for an unrelated dedicated IP (198.18.0.3, TCP/UDP 443). Allowed traffic targeted 198.18.0.2. Both measured conditions kept the same unrelated blocked-router.test policy loaded at the Policy Server, so only the gateway rules were toggled. Warm-up preceded measurement.

ABBA ABBA ordering alternated baseline and enabled batches. Each batch made 50 fresh HTTP/3 and 50 fresh TLS connections, sequentially, using curl time_total. This records full request completion including handshake and server response, excludes SSH transport latency, and does not measure steady-state reused-connection latency, throughput, propagation latency, blocked-request timeout or overhead under load. The test measures two simple IP/port deny rules, not a large ruleset or a future automatic controller.

The control function deliberately toggles the test gateway rules while the unrelated policy remains loaded for calibration. This is an A/B benchmark, not the behavior of a production policy reconciler. No inline hold or automatic per-domain flow classifier was added.

## Cleanup

Temporary policies, namespace origin, veth, route and firewall rules were removed. Live checks confirmed original ip_forward=0 and the original scoped 15 ms deployment configuration. An original-origin HTTP/3 request returned HTTP 200 after cleanup. The initial harness attempt failed on an overly strict rule-removal assertion and was cleaned up before the measured run; it contributed no measured samples.

## Artifacts

measure_allowed_latency.py contains the experiment. results.json retains individual curl timings; latency-summary.json contains aggregates and paired block differences. cleanup-verification.json records final restoration. Raw command evidence remains local.
