# Domain index and packet regression — 6 November 2026

Added idx_policies_domain on policies(domain) to the active Policy Server SQLite database after a backup. EXPLAIN QUERY PLAN confirms that the exact-domain SELECT uses this index. Integrity check passes and baseline policy rows are preserved.

Initial pre-index regression (evidence/domain-index-20261106T150533Z): four phases of 20 requests passed: allow before addition, deny after addition, deny segmented ClientHello, allow after deletion. The index was then created; the script's verification incorrectly assumed domain column ordinal 1 instead of actual ordinal 2. The check was corrected to verify the column name. This assertion error did not undo the committed index.

First repeat (150608Z): the first four phases passed with the index already present. In the next deny phase, 11 requests were denied, request 12 returned HTTP 200, and the remaining 8 were not attempted. Capture retained; no kernel capture drops reported. This is a real intermittent enforcement failure, not merely missing capture evidence. The run does not establish that indexing caused it.

Final repeat (150714Z): all eight phases, 20 trials each, passed (160/160). Both blocks labelled before-index and after-index in this repeat had the index present: they verify idempotent index installation and repeated traffic behavior, not an unindexed/indexed performance comparison. All temporary rules and test helpers were cleaned up by the existing guarded workflow.

Conclusion: the domain-index alignment step is completed and indexed traffic regression passes on the final repeat. Reliable universal 100% reset blocking is not established because the failed run remains part of the evidence. No performance improvement is claimed from the four-row live database; equivalent indexed benchmarks remain pending.
