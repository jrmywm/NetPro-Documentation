# Recovered variant alignment — 6 November 2026

Verified against the preserved recovered-code-20261029 archive and extracted Rafie thesis.

## Source findings

`code/new/tiered-domain-checker.c` defines BLOOM_SIZE=65536 bits and BLOOM_BYTES=BLOOM_SIZE/8: ordinary Bloom storage is 8192 bytes. Its high-risk initializer (lines 348–377) scans SELECT domain FROM policies without ORDER BY, with an overall 10,000-row cap. It adds a domain to the high-risk tier only when the scan counter is below 100 and the domain contains the case-sensitive substring phish, malware, trojan or exploit. Therefore this is a keyword heuristic over the first 100 scanned domains, not a separate curated threat dataset, nor the first 100 qualifying domains. The checking function scans that list linearly.

`code/new/counting-bloom-filter-domain-checker.c` defines BLOOM_SIZE=65536 counters and COUNTER_MAX=15, packed two four-bit counters per byte: 32768 bytes. This is a separate recovered implementation, not the bit filter used by the recovered tiered file.

Thesis abstract/extraction lines 310/350 describes Counting Bloom, 65,536 bits and LRU 20,000; table near lines 2458–2460 gives 8 KiB. Thus a single consistent final variant cannot be inferred by treating bits and counting cells as interchangeable. Preserve both actual source variants in comparison results.

## Current adaptation

Combines a 32 KiB counting filter with real LRU, full database coverage and ID-ordered first-100 preloading. The preload does not implement the recovered keyword selection. Safe full rebuild on deletion differs from incremental counter decrement. These remain labelled adaptations. The domain index has now been added and verified separately.

## Next controlled comparison

Use the recovered tiered bit-filter implementation as its own source baseline and the recovered counting-filter implementation as a separate baseline. Give both the same indexed SQLite dataset and query trace; record filter memory units, initialization caps, correctness, cache behavior and query counts alongside latency. Test fixtures should include qualifying/nonqualifying names both before and after scan position 100 to expose the source selection rule. Synthetic names are test fixtures, not a claim to reproduce a missing curated dataset.

Keep source files unchanged. Record source defects (including scan caps and actual replacement behavior) separately from the working adaptation. Do not silently replace the active counting filter with the bit variant merely to satisfy the thesis's inconsistent prose. A subsequent integration change can reproduce the recovered keyword heuristic while preserving policy IDs and complete filter coverage, but must be explicitly identified as a corrected adaptation rather than unmodified source replication.
