# Recovered thesis integration checkpoints

**31 October — Rafie accepted:** [RAFIE-ACCEPTANCE.md](RAFIE-ACCEPTANCE.md) and `test-results/rafie-functional.json` cover the enabled lookup tiers, full shadow/enabled packet tests, SQLite-lock/replay corrections, CSV regression and measured microbenchmarks. The experimental QUIC profile remains separate.

**Current acceptance:** see [LUTHFI-ACCEPTANCE.md](LUTHFI-ACCEPTANCE.md) and `test-results/luthfi-functional.json` for the deployed dashboard CSV integration, restart/load tests and four passing live TLS phases. Entries below preserve earlier checkpoints and may describe stages that have since been superseded.

Started: 30 October 2026. Originals remain under the existing thesis-review source archive; this directory holds labelled adaptations, not original thesis code.

## Latest: authoritative backend and CSV propagation verified — 30 October 2026

This supersedes earlier statements that live backend integration had not started. The guarded adapter is now deployed on Management, while the legacy frontend remains unchanged.

### Implemented and deployed

- New private `/ps/import-policy-batch` API: authorization token stays server-side, maximum 100 rows per API batch, deterministic replay by import key/domain, conflict rejection and protection of pre-existing policies.
- Authoritative `ps_blocked_list` writes and publication records commit in the same transaction. The new `netpro_bulk_policy_keys` and `netpro_bulk_policy_events` tables are additive; startup only checks schema readiness.
- A background worker awaits Kafka acknowledgement, retains pending failures, and sends stable policy/event IDs with at-least-once semantics. `published` is not `applied`; API application acknowledgement remains explicitly false/null.
- Source-key-owned cleanup atomically creates deletion events and removes only newly created, exclusively owned policies. Adopted pre-existing policies are not deleted. Cross-import references block automatic deletion.
- PostgreSQL null IP is translated to an **empty string only in the Kafka wire payload** for the existing Policy Server's string-only JSON parser. No fake address or DNS resolution is introduced.
- Rules exceeding the existing consumer's 256-byte SQL-message capacity are rejected explicitly rather than silently dropped. A consumer-side prepared-statement upgrade remains future work.
- Backend SIGINT cleanup no longer deletes Kafka topics; SIGINT/SIGTERM stop the publication worker before disconnecting producers. Existing dirty Kafka configuration and unrelated files were preserved.

Deployment backup: `/root/netpro-bulk-import-20261030T142616Z/` on Management, including a full PostgreSQL `test` dump, prior source/configuration and policy-baseline snapshot. Deployment verified original-source hashes before replacing `index.js`/`src/app.js`; added code is under `/home/netpro/NetPro-Backend/src/integration/`.

Private feature settings: `/etc/netpro/bulk-import.env` (root-only token), enabled through `/etc/systemd/system/netpro-backend.service.d/bulk-import.conf`. **Do not put this token into browser code, screenshots or reports.** No upstream repository was pushed. The first-deployment script refuses an existing deployment and is not a generic redeploy command.

### Actual verification

| Test | Result / scope |
| --- | --- |
| Backend adapter isolated integration | 9 checks pass: atomic rollback, replay UUIDs, concurrent imports, broker/ack fault injection, wire mapping, authorization, protected cleanup and conflict/size rejection |
| Authoritative live API → Kafka → active PS | Two labelled rules, one explicit IP and one domain-only, appeared with matching UUID/domain/IP in active PS SQLite; cleanup restored exact PS and PostgreSQL baselines |
| Actual multipart CSV → durable job → explicit bridge → live backend/Kafka/PS | Three input rows produced two unique / one duplicate / zero failed; same upload activated twice with stable UUIDs; both policies applied; owned cleanup restored exact backend/PS baselines |
| Backend controlled restart | Authoritative policy and outbox full-row hashes preserved; private API returned; both Kafka topic IDs unchanged |
| Bulk-fixture activation guard | Existing large completed import rejected before a live activation request |
| Final health | Backend/PostgreSQL/Kafka and PS active; backend/dashboard HTTP 200; no staging listener remains on 18080 |

Kafka topic IDs preserved across restart: `logging-dashboard=BKvXowIIQTqzFxsUfXNvBw`, `dpdk-blocked-list=E03SI_rbSiusgoqscaR-rA`.

Evidence files: `stage4-authoritative-adapter.json`, `stage4-live-policy-e2e.json`, `stage4-live-upload-e2e.json`, `live-backend-restart.json` under `evidence/`; command logs under `../thesis-stack/evidence/authoritative-backend-deploy-*`, `authoritative-backend-restart-proof-*`, `live-bulk-final-*`, and `live-upload-cap-proof-*`.

### State, limits and next work

- Management and Policy Server were started and remain running. NPB/TAP/Gateway/Client were not needed for propagation and were not started in this stage.
- The active PS database is **`/home/ubuntu/NetPro-Policy-Server/policy.db`**, not the empty/stale same-named file in `/home/netpro/NetPro-Policy-Server/`. Use read-only connections. Baseline has the original four known IDs.
- The CSV side still runs as the retained-upload candidate with isolated job/storage tables. The explicit operator bridge `luthfi/scripts/activate-live-upload.js` links a completed job to the authoritative backend and is capped at **20 rows** during verification. The large benchmark fixtures were not published.
- Dashboard upload/activation controls, proper user-scoped authorization, automatic applied acknowledgements and scalable whole-file activation are **not yet implemented**. Keep the private token out of frontend assets.
- These live tests prove **rule propagation/application to the active Policy Server database**, not packet-level blocking. Packet/TLS regressions of this newly connected CSV path still need the full test topology. Older blocking tests remain separate evidence.
- Idempotency/concurrency tests cover the new bulk path. Legacy single-rule endpoints are not converted to transactional outbox writes, and a concurrent legacy writer does not share the bulk adapter's advisory lock. Do not claim global exactly-once policy updates.
- Rafie cache integration has not started; it still follows the correctness/invalidation gate.

Windows repeaters (they create only their own small labelled rules and request cleanup):

```powershell
Set-Location 'C:\Users\jim\Documents\NetPro\Implementation\recovered-theses'
python .\backend-candidate\ops\verify-live-e2e.py
python .\backend-candidate\ops\verify-upload-e2e.py
python .\verify-local.py
```

Do not rerun `ops/deploy.py` on the already deployed backend. For manual small-job activation, the explicit bridge requires an operator context on Management that can read the root-only private token, the retained job ID, and `--activate-live`; it does not expose credentials to a browser. Its matching `--cleanup-live` uses the owned receipt. Consult the live test scripts before reproducing these steps manually.

## Verification gates

1. **Luthfi startup safety and Ubuntu loading.** Dedicated isolated database/role, loopback-only test listener; no schema mutation at startup; reject live configuration; preserve records across restart. Explicit empty-database schema bootstrap is a test tool, not a production migration.
2. **Luthfi upload correctness and bounded memory.** Validate inserted/duplicate/failed counts, large batches, retry input retention, multiple jobs and restart recovery. No frontend or live policy activation before this passes.
3. **NetPro policy adapter and progress.** Confirm backend records, delivered policy updates, dashboard progress and actual allow/deny behavior agree. Preserve originals and baseline behavior.
4. **Rafie standalone correctness.** Complete-list filter initialization, defined cache semantics, safe live changes/deletion and per-domain SQLite oracle. Fix benchmark methodology before comparing performance.
5. **Policy Server integration.** Feature flag, synchronization/thread ownership and enabled/disabled decision equivalence.
6. **System regression/performance.** TAP, split TLS, policy lifecycle, SNMP and existing QUIC cases; then throughput/latency/memory under concurrent uploads and traffic. Existing QUIC limitations must not be hidden.

Each checkpoint needs actual test evidence. Passing syntax/unit tests alone does not establish upload or end-to-end system functionality. No checkpoint below is assumed passed until evidence is recorded.

## Earlier checkpoint — queue/HTTP integration, 30 October 2026

### Further progress: isolated policy/outbox integration

The subsequent phase-three prototype has now passed **eight checks**, saved in [stage3-outbox.json](evidence/stage3-outbox.json). Its explicit v3 migration creates only candidate-policy, import-link and outbox tables in the guarded isolated database. It does not change live `ps_blocked_list`.

Verified:

- Candidate policy and its pending-publication event commit atomically; injected persistence failure rolls both back.
- Repeated imports reuse the same policy ID/event instead of creating duplicate records. Conflicting fields require an explicit update rather than silent overwrite.
- A completed retained CSV upload maps into idempotent candidate policies; duplicate and invalid rows are handled. The staging operation is explicit and is not an automatic live rule activation.
- Simulated broker failure leaves durable pending work. Simulated interruption after acknowledgement but before database commit causes a retry with the same event/policy IDs.
- A **real Kafka** event was acknowledged and consumed from `netpro-integration-test-outbox-20261030`, with matching policy/event IDs and the existing NetPro message structure.
- The publisher rejects `dpdk-blocked-list`: only isolated integration-test topics are allowed in this prototype.
- Status distinguishes stored/published and explicitly reports `applied: null`, `applicationVerified: false`.

Important limits: delivery is **at least once**, not exactly once. Existing consumers still require idempotent handling of stable policy IDs. Fault-injection tests and the real-broker round trip are separate checks. No Policy Server consumed this isolated test topic; no live enforcement, authoritative backend write or dashboard activation has been demonstrated by this prototype.

The CSV-to-outbox staging currently commits per policy. A failed staging run may leave a partial set of unpublished candidate policies, which can be retried idempotently; it is not an atomic whole-file activation. An activation/completeness gate and scalable batch staging are required before enabling automatic publication from uploads.

Code: `luthfi/app/services/policy-outbox.service.js`; explicit migration: `scripts/migrate-isolated-v3.js`; retained-upload staging CLI: `scripts/stage-upload-policies.js`. No publication worker is enabled at boot. Test policies/messages remain in isolated tables/topic for inspection. No live policy was added or removed.

Run on **Management**, only in the isolated candidate directory:

```sh
cd /home/netpro/recovered-theses-20261030/luthfi
node scripts/with-isolated-env.js scripts/migrate-isolated-v3.js --apply
node scripts/with-isolated-env.js tests/stage3-outbox.js
# Optional explicit candidate-only staging of a known completed retained upload:
# node scripts/with-isolated-env.js scripts/stage-upload-policies.js JOB_ID
```

The real-Kafka test reuses the existing backend's installed KafkaJS library without importing backend application/configuration code. It creates only its isolated test topic, retains its records, and does not delete any Kafka topics. Last local verification: 48 JS files parse, 20 unit tests pass, 203 original extracted files plus both archive hashes unchanged. Backend/dashboard remain HTTP 200 after this stage.

Next gate remains **authoritative backend deployment and actual Policy Server verification**, then frontend integration. The outbox pattern has been demonstrated; it has not yet been deployed into the authoritative backend transaction.

The isolated candidate now uses the bounded core through real HTTP upload routes and a persistent PostgreSQL queue. This supersedes the first-checkpoint notes below about HTTP wiring and automatic recovery being pending.

| Verification | Latest result |
| --- | --- |
| Startup and policy-contract unit tests | 20/20 pass on Windows and Ubuntu |
| HTTP/Socket.IO/durable queue integration | 10/10 pass on Ubuntu |
| Bounded processing regression | 8/8 pass, including another 100,000-row PostgreSQL import |
| Additive migration replay | Pass: twice preserves full-row hashes/counts of all three data tables |
| Source syntax/import audit | 44 JavaScript files pass syntax; no relative-import casing errors |
| Original-source integrity | All 203 extracted original files and both original archive hashes match |
| Existing live backend/dashboard | Both HTTP 200 after testing; backend/PostgreSQL active |

Actual application-kill test: upload accepted via HTTP, progress delivered over a real Socket.IO connection, application killed after **1,000 of 50,000 rows** had committed, application restarted, retained job automatically found and completed with exactly **50,000 inserted / 0 duplicate / 0 failed**. This is now automatic recovery, not the earlier manually supplied worker-resume test.

Other HTTP checks: multi-file routing, zero-row completion, missing/unsupported file rejection, HTTP 413 for oversized input, rejection of a second worker instance, retained-file checksum rejection, successful retry after restoring the verified input, and refusal to retry an already completed job.

The additive v2 migration introduces nullable retained-path, SHA-256 and batch-size columns. Startup does not run this migration. Migration replay preserved hashes/counts across 150,036 blacklist rows, 12 jobs and 3 failed rows present at that test point; subsequent tests add more isolated fixtures. It did not touch the live NetPro database.

Latest parser-process RSS observation: **124.64 MiB** during the 100,000-row fixed-width parser fixture, maximum yielded batch 1,000. This is not a universal memory guarantee or a throughput benchmark.

Evidence: [HTTP/queue tests](evidence/stage2-http-queue.json), [bounded-core tests](evidence/stage2-bounded.json), [migration test](evidence/migration-v2.json), [local verification](evidence/local-verification.json). Detailed run output is also retained under `../thesis-stack/evidence/recovered-queue-regressions-20261030T133100Z/` and `recovered-queue-final-health-20261030T133307Z/`.

### State left behind

- Management was initially powered off. Only Management was started for these tests; packet-processing VMs were not started.
- Candidate source/dependencies and private retained test inputs remain for reproduction. No candidate service is enabled at boot, and no candidate listener remains on port 18080 after the tests.
- Live backend/frontend services and their source were not modified. Their read-only source snapshot is under `backend-contract/`; it must not be confused with a deployed candidate.
- The normal host SSH connection works. The context-filtering subprocess timed out against the guest, so remote runs used the established direct terminal helper instead. No network configuration was changed.
- A pre-change candidate source backup exists on Management as `/home/netpro/recovered-theses-20261030/before-queue-integration.tar.gz` (credentials/dependencies/retained inputs excluded).
- Rejected request-owned temporary files are removed; accepted job inputs are deliberately retained, including failed/completed jobs. A retention/cleanup policy is still needed before sustained use.

### Next gate: authoritative policy integration

The candidate is still isolated. A CSV import **does not yet create live NetPro block rules**. The existing dashboard is not yet connected to this candidate, and an actual interactive-browser upload has not been tested.

The read-only backend review found:

1. Authoritative policy creation uses `/ps/blocked-list` with `{ name, domain, ip_add, category }`, a UUID ID and fixed category enum. `ip_add` is nullable in the backend model; actual Policy Server behavior for null IP must still be verified.
2. `src/controllers/psController.js` calls `producer.send(...)` without awaiting it before HTTP success. Therefore API success alone does not prove Kafka delivery or Policy Server application.
3. A separate issue exists in the recovered live backend's `SIGINT` handler: it deletes the two Kafka topics. This handler was not invoked or changed here. Future backend deployment must preserve topics and pending publication state rather than use this destructive cleanup.

A read-only mapping adapter and eight unit tests now cover category normalization, domain-only input, explicit IPv4 validation and exclusion of standalone IDs/historical counters. Unknown categories are rejected rather than silently reclassified. The preview tool publishes nothing.

Next implementation: durable/idempotent authoritative policy writes plus publication tracking, separate **stored / published / applied** meanings, actual Policy Server verification, then dashboard wiring. Do not label Kafka acknowledgement as proof of policy enforcement. Keep test imports isolated; never publish the 100,000-row test fixtures to the live blocklist.

Repeat queue tests on **Management VM**, in an SSH terminal:

```sh
cd /home/netpro/recovered-theses-20261030/luthfi
node scripts/with-isolated-env.js tests/migration-v2.js
node scripts/with-isolated-env.js tests/stage2-http-queue.js
node scripts/with-isolated-env.js tests/stage2-bounded.js
node --test tests/startup.test.js tests/policy-contract.test.js
```

The VM-private environment runner loads existing isolated credentials without printing them. Do not run concurrent test suites on the same port/database. Each HTTP queue run retains another 50,000-row fixture; each bounded-core run retains another 100,000-row import. These commands are repeatable but consume disk, so use a deliberate test-data retention plan.

## First checkpoint — historical notes, 30 October 2026

- **Gate 1 passed:** 12 startup unit tests; seven Ubuntu/PostgreSQL integration checks. Application loads all routes, returns HTTP 200, rejects a live database name, refuses bootstrap of a populated database, and preserves seeded blacklist/job rows and timestamps across two starts/stops.
- **Gate 2 processing core passed; complete gate still pending:** seven isolated checks include exact mixed-row accounting, completed-job replay, empty input, forced worker-process exit and retained-input resume, overlapping jobs, bounded 100,000-row parsing and a real 100,000-row PostgreSQL import.
- The bounded core is explicitly **not yet wired to HTTP upload routes**. The recovered route implementation remains legacy code inside the loopback-only staging copy. Do not describe the browser-upload feature as integrated.
- The restart test supplies the same retained file explicitly to a new worker. It does **not** prove automatic queue restart recovery, immutable-input verification, or retained-path retry behavior. Those are the next Gate 2 tasks before frontend/policy integration.
- Observed parser-process peak RSS during that fixed-width 100,000-row fixture: **125.26 MiB**, with at most 1,000 rows per yielded application batch. This is not an overall application memory guarantee or a throughput benchmark; it includes prior activity in the test process.
- Post-test live backend and dashboard both returned HTTP 200; backend/PostgreSQL services remained active. No staging listener remained on port 18080 after the tests.
- Rafie integration has not started. Its original source remains unchanged.

Evidence: [stage-one Linux checks](evidence/stage1-linux.json), [bounded-core checks](evidence/stage2-bounded.json), [local safety and provenance checks](evidence/local-verification.json), [unit output](evidence/startup-unit.tap).

Working copy: `C:\Users\jim\Documents\NetPro\Implementation\recovered-theses\luthfi`.
Ubuntu staging copy: `/home/netpro/recovered-theses-20261030/luthfi` on Management (`192.168.31.35`).
Test database: `netpro_luthfi_test_stage1_20261030`, owned by the dedicated non-superuser test role. Test data and dependencies are retained for reproducibility; no service is enabled at boot. Private test credentials remain in a mode-0600 file on the VM and are excluded from evidence.

Repeat local checks in PowerShell:

```powershell
Set-Location 'C:\Users\jim\Documents\NetPro\Implementation\recovered-theses'
python .\verify-local.py
```

The stage-one Linux runner requires a fresh, empty, dedicated test database for its bootstrap-success case. Deliberately do not rerun its initialization against the populated retained database. The bounded-core test uses unique fixture prefixes and can be repeated, but each repetition retains another 100,000-row test import; do not run it repeatedly without a retention plan.

## Scope safeguards

- Current working copy: `luthfi/`; recovered source is unchanged.
- Stage-one app refuses non-isolated configuration and privileged PostgreSQL roles.
- Allowed database names start `netpro_luthfi_test_`; dedicated role is `netpro_luthfi_test`.
- Application listens only on `127.0.0.1:18080..18089` during staging.
- Existing NetPro services, database and frontend routes are not switched to the candidate.
- Startup checks existing schema. A separate explicit bootstrap refuses a non-empty database and never uses `force` or `alter`.
- Changes must be tracked with evidence before deployment; no Network-Laboratory repositories are pushed.
