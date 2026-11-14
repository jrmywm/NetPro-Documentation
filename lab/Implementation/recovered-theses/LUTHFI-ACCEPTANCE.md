# Luthfi CSV import integration — acceptance record

**Fidelity qualification:** this records functional acceptance of an adaptation, not faithful execution of the original better-queue/10,000-row workflow. See [the 31 October fidelity audit](THESIS-FIDELITY-AUDIT-2026-10-31.md) for material replacements and outstanding alignment.

Implemented and deployed on 30–31 October 2026. This is a functional adaptation of the recovered Luthfi application into the running NetPro dashboard/backend, rather than a separate upload demonstration. The immutable recovered thesis sources were not changed. Rafie's caching work is outside this acceptance record.

## Operator workflow

1. Open `https://192.168.31.35:3005/dashboard/imports` and sign in with the existing dashboard account. The sidebar CSV entry and blocked-list **Import CSV** button also open this page.
2. Download the CSV template; use its columns and plain domains (no URL or wildcard). IPv4 is optional. Upload up to five CSV files, each at most 25 MB.
3. Watch upload and validation progress. Review the valid, duplicate and invalid counts, row preview and downloadable failed-row CSV. Uploading alone does not activate any policy.
4. Explicitly confirm activation. If invalid rows exist, first acknowledge that only valid rows will be activated. Activation uses durable batches and may be partial until it finishes; retry resumes the saved checkpoint.
5. Watch stored and Kafka-published counts. **Published means Kafka acknowledged the message, not that Policy Server acknowledged enforcement.** Existing policies are labelled unverified. Application was checked separately against the active Policy Server database during acceptance.
6. If removal is needed, confirm removal of policies created by that import. Existing/shared policies are protected; policies manually edited after activation cause removal to stop for review.

Progress uses authenticated Socket.IO, with polling fallback. Each user's jobs and progress are scoped to that user's existing JWT account. The internal service token remains server-side.

## Acceptance results

| Check | Observed result |
| --- | --- |
| Authoritative backend adapter | 10/10 checks passed: atomic writes/outbox, replay, concurrency, failure retry, wire compatibility and removal protections |
| Integrated HTTP CSV pipeline | 7/7 checks passed, including owner isolation, failed rows, explicit activation and checkpoint recovery |
| Frontend | 6 suites / 25 tests passed; production build passed |
| Real backend restart during validation | Restart after 1,000 committed rows; resumed to 100,000 valid, 0 duplicate, 0 invalid |
| Real Socket.IO through nginx | Owner received 3 events; other owner received 0; unauthenticated connection rejected |
| Live policy propagation | 1,001 unique CSV policies matched the active Policy Server's UUID/domain/IP digest; all removed afterward |
| Full TLS path, before activation | 20/20 requests returned HTTP 200 |
| Full TLS path, CSV policy activated | 20/20 requests were reset |
| Split TCP ClientHello, CSV policy activated | 20/20 requests were reset; segmentation checked in capture |
| Full TLS path, CSV policies removed | 20/20 requests returned HTTP 200 |
| Cleanup | Exact policy baseline restored; temporary accounts removed; packet test helpers stopped and client MTU/offloads restored |
| Original-source integrity | 203 extracted original files and source ZIP hashes verified unchanged |

The packet checks exercised Client → Virtual TAP → NPB → Policy Server and the configured reset-return path. They created the policy through authenticated CSV APIs; no legacy single-rule create endpoint substituted for CSV activation.

**Interactive browser click-through is not yet verified:** the browser available to the agent stopped at the lab's self-signed certificate. User certificate acceptance is needed before that final manual check. Frontend component tests, deployed HTTP routes, WebSocket delivery and the actual packet path were verified separately; they do not replace this remaining browser check.

## Implementation and provenance

- `luthfi/` retains the labelled corrected standalone application and test fixtures. The original fast-csv 5.0.2, multer 1.4.5-lts.1 and Socket.IO 4.8.1 versions are pinned in the integration runtime.
- `backend-candidate/` adapts the upload flow to NetPro's authoritative `ps_blocked_list` and existing Kafka/Policy Server contract. The original in-memory queue is replaced here with PostgreSQL-backed job checkpoints and a transactional publication outbox.
- Parsing/staging commits batches of 1,000; activation/publication uses batches of 100. The dashboard flow has no 20-row demonstration limit.
- Additive tables hold jobs, staged rows, validation failures, policy ownership receipts and pending publication events. Schema migrations are explicit; ordinary startup does not drop or rebuild policy tables.
- Stable policy/event IDs support at-least-once publication and retry. This is not an exactly-once guarantee. A whole file is not one atomic activation transaction.
- Domain/IP validation follows the current consumer's capacity. Oversized rules are rejected rather than silently truncated. Legacy JWT/dependency choices remain inherited; this acceptance is not a production hardening or identical thesis-performance claim.

## Deployment and evidence

Management VM: `192.168.31.35`; backend source `/home/netpro/NetPro-Backend`; service `netpro-backend`.

Final frontend root: `/var/www/netpro-frontend-csv-final-20261030T161236Z`.

Backups on Management:

- `/root/netpro-bulk-import-20261030T142616Z/` — original bulk adapter deployment and PostgreSQL dump.
- `/root/netpro-csv-dashboard-20261030T152903Z/` — CSV/dashboard deployment, source, nginx and PostgreSQL dump.
- `/root/netpro-csv-readiness-20261030T154629Z/` — startup readiness fix.
- `/root/netpro-csv-removal-safety-20261030T155640Z/` — edited-policy removal guard.
- `/root/netpro-csv-final-20261030T161236Z/` — final bounded job responses and progress/display fixes.

Feature configuration is `/etc/netpro/bulk-import.env`, root-only. It contains the private service token and must not be copied into screenshots or the frontend.

Local compact results: `test-results/luthfi-functional.json`. Detailed raw results, test logs and packet captures are under this directory's ignored `evidence/`. Deployment command logs are retained under sibling `thesis-stack/evidence/`. Remote test evidence is `/home/netpro/recovered-theses-20261030/luthfi/evidence/`.

Live backend local commits: `782ec04` (integrated CSV import workflow) and `af5e7c0` (bounded public job responses). Source and this record are also committed in this local integration directory. No Network-Laboratory repository was pushed. Existing unrelated backend changes were preserved. No handoff file was updated.
