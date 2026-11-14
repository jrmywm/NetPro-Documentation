# Thesis fidelity audit — 31 October 2026

## Verdict

**Functional integration acceptance is not equivalent to faithful reproduction of the four theses.** Luthfi's and Rafie's adaptations are deployed and passed the recorded HTTP/TLS tests. Significant algorithm/workflow differences remain. Bintang's and Ibrahim's experimental integrations are not compiled into the currently selected Policy Server binary. Do not describe the present six-VM system as all four original thesis implementations running together unchanged.

This was a read-only, targeted fidelity audit, not another complete test run or exhaustive re-review of every thesis page. It compared the extracted thesis passages, recovered code, labelled adaptations, existing evidence and fresh deployed source hashes/service state. No runtime code, policy or configuration was changed.

## Luthfi — working adapted feature, with a substituted worker

Thesis evidence: extracted `sources/luthfi/full-text.md`, lines 4363/4542 describes better-queue; line 4518 identifies an optimal chunk size of 10,000 in that experiment. The recovered application's package declares better-queue, fast-csv, multer, PostgreSQL/Sequelize and Socket.IO.

Deployed feature retains CSV upload, validation, duplicate/failure reporting, batch processing and Socket.IO progress. The integrated runtime pins fast-csv 5.0.2, multer 1.4.5-lts.1 and Socket.IO 4.8.1.

Material differences:

- The deployed CSV pipeline is substantially rewritten integration code. It does **not** execute the original better-queue worker; it uses PostgreSQL-backed job/checkpoint state.
- Validation/staging batches are 1,000 and activation/publication batches 100, rather than the original 10,000-record experiment.
- Explicit reviewed activation, authoritative UUID/IP mapping, transactional outbox and ownership-aware removal are additional integration behavior.

The 100,000-row/restart/Socket.IO/packet results demonstrate the adapted implementation's behavior. They do not reproduce the thesis's queue implementation, 10-million-domain workload or reported throughput. These replacements must be disclosed, not described merely as dependency compatibility fixes.

## Rafie — adapted combination of recovered variants, with new mechanisms

Thesis evidence: `sources/rafie/full-text.md` lines 2449–2461 describes a high-risk tier, 20,000-entry LRU and a 65,536-bit/8 KiB Bloom filter. Lines 3715–3736 call the third tier Counting Bloom with 65,536 bits and require a SQLite B-tree index on domain. Line 5359 also discusses efficient Counting Bloom deletion as future exploration. The thesis is internally inconsistent about ordinary versus counting filters; this needs clarification against the intended final variant.

Recovered source evidence:

- `tiered-domain-checker.c` uses 65,536 ordinary Bloom bits (8 KiB), a maximum-100 high-risk list and a cache without actual LRU bookkeeping.
- `counting-bloom-filter-domain-checker.c` separately uses 65,536 packed four-bit counters (32 KiB) and a counter-decrement removal function.

Current adaptation preserves those three hash families and uses 65,536 four-bit counting cells, a new true LRU, SQLite confirmation and full database coverage. It combines and corrects the separate recovered variants; it is not the original tiered file running unmodified.

Material differences:

- The preloaded 100-policy tier is selected from database policies by ID. It is **not the thesis's risk-selected high-risk list**.
- Deletion invalidates all tiers and triggers lazy full rebuilding. It does **not** use the recovered incremental decrement algorithm, because saturated counters made that algorithm unsafe without further work.
- LRU is implemented with hash buckets and a linked recency structure, rather than the thesis's stated linear probing arrangement.
- Fresh `PRAGMA index_list(policies)` on the active database showed only `sqlite_autoindex_policies_1` for the primary key: **no dedicated domain index exists**, contrary to the thesis's indexed SQLite setup.
- The adaptation adds per-query SQLite data/schema-version checks and serialized mutations. These affect memory/latency and must be included in a valid comparison.

The mixed benchmark with no domain index is a measured microbenchmark of this adaptation, not a faithful reproduction of the thesis's indexed baseline. The separately reported indexed/repeated comparison was slower with guarded tiers. Correctness fixes for incomplete filter initialization and stale caches remain justified, but the remaining research-design changes require explicit disclosure or alignment.

## Bintang — real tools recovered/tested, reconstruction remains; not in current binary

The candidate `thesis_monitoring.c` identifies recovered shell/CLI trap behavior and explicitly labels the missing per-domain notification as reconstructed. The original Zabbix export was unavailable; reconstructed configuration is not an original author export. Later experiments used actual Net-SNMP snmptrap and Zabbix, rather than treating the earlier custom packet encoder as a thesis replica.

Fresh Management service inspection shows NetPro's Net-SNMP trap receiver and Zabbix Server active. Policy VM snmpd is also active. **Those service states do not prove native per-domain Policy Server event delivery.**

The currently deployed Policy Server source contains neither the `thesis_monitoring` integration hook nor a `snmptrap` call. The monitoring candidate therefore must remain separately qualified; its previous test results do not establish that its hooks are present in the currently active Rafie-enabled binary.

## Ibrahim — recovered original path tested separately; full integration incomplete

The separately built candidate uses the recovered QUIC parser/crypto/Close implementation with labelled bounds, compatibility and key-ownership corrections. Real Caddy and HTTP/3-enabled curl were installed and used in the later tests; those later runs were not merely an offline substitute parser.

However:

- The original thesis's shared/flooding Proxmox bridge differs from the current TAP → NPB → Policy Server observation path and gateway-return delivery arrangement.
- Recorded full-path Close tests did not reliably deny complete HTTP/3 requests. The 13 October closest-profile run recorded 0/5 denied; a direct shortened path later recorded 7/10 denied, still inconsistent.
- The successful inline gate is a separate extension that holds/drops original datagrams. It is not a replication of the original passive-observation plus injected Close mechanism and was not left active.
- The current deployed Policy Server source lacks the `thesis_quic` hook. QUIC remains a separate experimental profile, not an accepted part of the current HTTP/TLS binary.

## Fresh deployed evidence

- Active Policy Server binary: `/home/netpro/NetPro-Policy-Server/build/policyServer-rafie-20261031T023646Z`.
- Live `policyServer.c` SHA-256: `c770eb18afcfdb07a2650ab09c17f09d95ae74c02937dc2ae00b743f46db6ff8`.
- Live `rafie_lookup.c` SHA-256: `bef11b30ae5e690c0b87da683e8acda15eb4580835a250e51b798f497df5be70`.
- Current status: mode `rafie`, replay ready, shadow mismatches 0, lookup errors 0.
- Current source hook check: Rafie lookup present; thesis monitoring, snmptrap and thesis QUIC hooks absent.
- Management CSV source hashes match the accepted deployed adaptation; the worker does not reference better-queue.

Raw read-only audit outputs are retained under sibling `thesis-stack/evidence/thesis-fidelity-*` timestamped directories, including the policy index and hook check. Thesis text references are to the preserved local extraction, not a claim of fresh online source verification.

## What can be stated to the professor

> Fitur impor CSV dan lookup bertingkat telah diadaptasi serta diuji bersama pada jalur HTTP/TLS. Namun, hasil ini belum merupakan replikasi penuh keempat skripsi. Masih terdapat perubahan pada mekanisme antrean dan ukuran chunk Luthfi, pemilihan tier awal serta pembaruan filter Rafie, dan konfigurasi indeks database. Integrasi monitoring Bintang memuat bagian rekonstruksi dan hook-nya belum berada pada binary Policy Server yang sedang aktif. Implementasi QUIC Ibrahim telah diuji memakai kode dan perangkat uji asli yang tersedia, tetapi tetap menjadi profil eksperimen terpisah dan pemblokiran pada jalur penuh belum konsisten.

## Next fidelity work, before declaring full thesis replication

1. Establish a source-preserving Luthfi baseline using its original better-queue and 10,000-row chunk design, alongside rather than silently replacing the accepted durable pipeline. Compare equivalent workloads and clearly separate required fixes from redesigned workflow.
2. Resolve Rafie's final intended variant, high-risk dataset and bit/counter units against the source/thesis. Add/verify the intended domain index before equivalent baseline measurements; explicitly decide whether safe incremental deletion or rebuilt-filter adaptation is the acceptance target.
3. Build one reviewed candidate that includes the recovered Bintang monitoring hooks and current lookup changes; retain reconstruction labels and verify real event-to-Zabbix delivery, not just daemon availability.
4. Continue Ibrahim topology/client-state testing separately. Do not present gate success as proof of the injected Close method. Merge only after its intended functional acceptance passes.

Earlier HTTP/TLS test results remain valid for the actual code tested. The correction concerns fidelity and integration scope, not a finding that those recorded tests failed.
