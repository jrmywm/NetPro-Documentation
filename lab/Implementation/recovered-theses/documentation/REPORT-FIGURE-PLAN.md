# Figure layout for the next kelompok and individu reports

User preference recorded on 31 October 2026: preserve the original supplied diagrams, but split their content into readable figures when preparing the group and individual report documents. Do not shrink the whole architecture or the tall lookup flow until the text is unreadable. This is a layout plan; no report DOCX has been created or edited by this step.

Original assets are in `C:\Users\jim\Documents\NetPro\Documentation\Evidence\adapted-integration-20261031\screenshots\`:

- `12-full-adapted-architecture.png`: full six-VM overview.
- `13-rafie-lookup-decision-flow.png`: detailed domain decision flow.
- `11-csv-validation-preview-and-failures.png`: actual dashboard validation evidence, ready for review with no activation yet.

## Kelompok report

Use three main architecture figures, redrawn from the existing Mermaid source where possible so labels remain readable:

1. **Jalur trafik, mirroring, dan pengiriman reset.** Client, Virtual TAP, Gateway, NPB, Policy Server and dedicated NetPro-RST return. Distinguish original packets, copies and injected resets. Show the management system only as a compact external reference.
2. **Alur impor dan distribusi kebijakan — adaptasi Luthfi.** Dashboard → validation/preview → explicit activation → PostgreSQL policies/outbox → publisher → Kafka → Policy Server consumer/SQLite. Include authenticated progress back to the dashboard and invalidation at the Policy Server boundary.
3. **Alur pemeriksaan domain — adaptasi Rafie.** Preloaded set → LRU → Counting Bloom → exact SQLite confirmation; distinguish allow/block and retain policy IDs. Include full-set invalidation/rebuild after committed changes.

Keep the complete architecture as an appendix or a landscape reference page if readable. If the detailed lookup still needs splitting, use panel (a) for invalidation/rebuild and preloaded/LRU checks, and panel (b) for Bloom/SQLite/cache update and final decisions. Give connector points matching labels, and repeat the incoming context on the continuation panel. Do not cut arrow labels or leave unexplained dangling connections.

## Individu report

Use the compact overall traffic figure for context, then the detailed import or lookup figure relevant to the person's reported contribution. Do not attribute all recovered thesis work or all integration work to one member without the group's confirmed task allocation. Use the same diagram labels and scope as the kelompok report.

## Evidence and layout rules

- Preserve the original PNGs; any resized exports or figure panels are separate derived files.
- Prefer logical component diagrams or vector exports over arbitrary rectangular crops of the giant image.
- Use Indonesian captions consistently. Keep readable text at the report's final printed width.
- Refer to figures in the surrounding explanation; label continuation panels explicitly.
- Keep the HTTP/TLS scope, software Virtual TAP limitation and separate experimental QUIC profile visible in the report text.
- Dashboard image 11 proves validation and review: 4 rows, 2 valid, 1 duplicate, 1 invalid. It does not prove activation or blocking: stored and Kafka-published counts are both 0. Obtain the later activation/removal views if those outcomes need visual evidence.
