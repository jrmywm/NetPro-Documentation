# Current NetPro integration status — 14 November 2026

This is the current operating record. Earlier setup documents describe historical topologies and remain for traceability.

## Active six-VM architecture

| VM | Management IP | Role |
|---|---|---|
| Policy Server | 192.168.31.31 | HTTP/TLS and QUIC inspection, policy cache, monitoring events |
| NPB | 192.168.31.33 | Mirrored-packet classification and forwarding |
| Management (Backend-VM) | 192.168.31.35 | Backend, PostgreSQL, Kafka, nginx/dashboard, Net-SNMP/Zabbix |
| Gateway | 192.168.31.37 | Local Caddy server, dedicated injection return, scoped delay |
| Virtual TAP | 192.168.31.38 | Software bridge forwards originals and mirrors copies to NPB |
| Client | 192.168.31.39 | curl and Chromium probes |

Dashboard: https://192.168.31.35:3005/ . The old separate Kafka, Frontend and Packet Generator VMs are not required for this acceptance test. The software TAP does not establish physical fail-open behavior.

## Adaptations and deployment

- Luthfi: reviewed CSV upload, validation, progress, explicit activation, durable PostgreSQL jobs and policy outbox. The recovered better-queue/10,000-row baseline is retained separately. The adapted worker uses different batch sizes; this is not an identical thesis implementation.
- Rafie: preloaded policies, LRU and Counting Bloom Filter with exact SQLite confirmation, invalidation/rebuild and retained policy IDs. The SQLite domain index is installed. Filter variant/high-risk list differences are described in the fidelity audit.
- Bintang: actual Policy Server events reach Net-SNMP and Zabbix. Missing per-domain/reporting portions are reconstructed and labelled in code and output.
- Ibrahim: recovered QUIC Initial inspection and injected CONNECTION_CLOSE are combined with HTTP/TLS in the persistent prototype. Lab results rely on an explicit scoped 15 ms server-response delay; they are not delay-free deployment evidence.

Persistent services are netpro-policy, netpro-npb and netpro-quic-lab.service. Browser reassembly/zero-SCID fixes remain a separately tested candidate and are not permanently deployed.

## Latest verification

On 14 November all six VMs were started from powered off. All six were reachable. Management services and protected API behavior passed, policy publication had no pending events, and cache synchronization was ready with zero errors or shadow mismatches. Both TAP mirror counters increased and fresh blocked-domain monitoring events arrived.

- Live curl allow–deny–allow: **18/18 passed**, covering forced HTTP/3, TLS and fallback-enabled curl.
- Chromium/curl suite: **14/15 passed**. Forced HTTP/3 Chromium loaded the page during deny. TCP/TLS and normal-mode browser probes blocked. The browser candidate previously passed 15/15 in its temporary deployment on 7 November.
- Temporary rules were removed and original API/SQLite IDs restored. Three legacy SQLite-only policies remain preserved.
- No fresh bulk CSV import, interactive dashboard workflow, or stress benchmark was run on 14 November.

See [startup evidence](../evidence/startup-2026-11-14/RESULTS.md) and the retained [browser results](../evidence/thesis-integration/browser-persistent-20261113T214346Z/browser-results.json).

## Repository contents

- [Adapted architecture](../lab/Implementation/recovered-theses/ARCHITECTURE-ADAPTED.md)
- [Thesis fidelity audit](../lab/Implementation/recovered-theses/THESIS-FIDELITY-AUDIT-2026-10-31.md)
- [Deployment and delay findings](../lab/Implementation/thesis-stack/DELAY-ASSISTED-QUIC.md)
- `lab/Implementation/recovered-theses/`: versioned backend/frontend, Luthfi, Rafie, monitoring and supporting tests (source repository commit dbca0be).
- `lab/Implementation/thesis-stack/`: combined candidates, QUIC diagnostics, persistent installer and browser candidate builders/tests.
- `lab/Testing/` and `lab/Operations/`: test methods and operations scripts.
- `reports/Pekan-10/` and `reports/Pekan-11/`: final group and individual reports. Reports describe evidence available at their own dates; this status supersedes them for live deployment readiness.
- `evidence/deployment-browser-2026-11-07/`: actual captured terminal and browser screenshots.
- [Source manifest](integration-source-manifest-2026-11-14.json): exported file hashes. Raw captures, credentials, dependencies, VM disks, browser NetLogs and generated binaries remain local.

The lab snapshot retains the original directory relationship between Implementation and Testing. Some historical scripts still reference machine-specific source paths and pinned binaries; review their guards and configure NETPRO_LAB_PASSWORD before use. Installers and older diagnostics are not safe to rerun indiscriminately over the accepted deployment. The snapshot is an archive of the tested implementation, not a new one-command installer.

## Next step

Review and promote the browser reassembly/zero-SCID candidate only after repeated acceptance and rollback checks, then repeat startup verification. Keep the 15 ms timing condition explicit in results.
