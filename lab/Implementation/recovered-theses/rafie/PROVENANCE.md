# Rafie lookup adaptation

Original code is immutable under the thesis-review archive's `skripsi-bloom-filter-main/skripsi-bloom-filter-main/code/new/`. This working directory is a labelled NetPro adaptation of `counting-bloom-filter-domain-checker.c` and `tiered-domain-checker.c`; it is not a claim that the recovered tiered file already implemented LRU or a Counting Bloom Filter.

Retained design: three polynomial/djb2 hash families, 65,536 packed 4-bit counting cells (32 KiB), tiered domain lookup and SQLite confirmation of filter positives. Matching remains exact and case-sensitive, consistent with the running Policy Server.

Adaptations: full authoritative scan without row caps; bounded real hash-indexed LRU holding both decisions and policy IDs; prepared queries; caller serialization; complete cache invalidation after policy commits; separate-connection change detection with SQLite data_version; restart reconstruction; failure fallback without trusting incomplete filters.

Counting cells saturate rather than wrap. Deletions/updates trigger a complete lazy rebuild, never decrements of saturated cells. This trades update/rebuild time for correctness. Large imports invalidate on every committed event, but only a lookup triggers rebuilding. Concurrent import/traffic performance must be measured separately.

The small preloaded tier contains at most 100 **existing database policies**, selected by ID. It is a deterministic hot set, not a threat ranking or independent hardcoded blocklist. Without risk metadata we do not claim a high-risk classifier.

The SQLite data_version guard runs on every lookup. This adds overhead and is included in comparisons. Functional correctness takes precedence over claiming faster throughput. Microbenchmarks are separate from packet/system measurements and do not reproduce the thesis's hardware/performance results.
