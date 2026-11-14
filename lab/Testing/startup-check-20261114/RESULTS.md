# NetPro startup verification — 14 November 2026 (Asia/Taipei)

Started the six required VMs from a powered-off state using VMware vmrun. Left all six running. Legacy Kafka, Frontend and Packet Generator VMs remain off because they are not required for these checks.

| Check | Result |
|---|---|
| Six VMs reachable by verified SSH | PASS |
| Persistent Policy Server and NPB services | PASS |
| Virtual TAP forwarding and both mirror counters increasing | PASS |
| Gateway return service and scoped 15 ms delay | PASS |
| Backend, PostgreSQL, Kafka and nginx | PASS |
| CSV page and NPB API | HTTP 200 |
| Unauthenticated CSV API | HTTP 401 as expected |
| Pending policy publication events | 0 |
| Rafie cache | ready, filter valid, zero lookup errors and shadow mismatches |
| SQLite domain index | idx_policies_domain present |
| Net-SNMP receiver and Zabbix | active; fresh blocked-domain events received |
| curl allow–deny–allow, HTTP/3, TLS, fallback enabled | 18/18 PASS |
| Chromium plus curl browser acceptance | 14/15 PASS |

## Outstanding issue

Forced HTTP/3 in Chromium bypassed the block rule (page loaded). Chromium with TCP/TLS and its normal-mode probe were blocked. The previously tested browser reassembly/zero-SCID candidate is not part of the current persistent deployment. No candidate binaries were installed or promoted during this check.

The 15 ms delay remains an explicit lab condition. These are short functional checks, not a new load benchmark or a full CSV import workflow test. Dashboard HTTP availability was checked; no interactive dashboard session was exercised.

All temporary test policies were removed through the API, synchronization was verified, and the original API/SQLite policy baseline was restored after both test suites. Three pre-existing SQLite-only legacy policies are preserved.

## Evidence

- health.json — final VM and service observations
- management.json — management health, monitoring services and domain index
- acceptance.json — 18 live curl probes
- active-baseline-*.json — guarded policy creation, synchronization and cleanup
- Browser evidence: C:\Users\jim\Documents\NetPro\Implementation\thesis-stack\evidence\browser-persistent-20261113T214346Z
