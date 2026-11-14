# Kafka startup synchronization recovery — 6 November 2026

The initial Kafka watermark query previously ran once. If Kafka was unavailable, its failure became INT64_MAX, which prevented policySyncReady from becoming true after later successful consumption.

The active candidate now represents an unknown watermark as -1, retries the query with a bounded one-second timeout in the consumption loop, and freezes the first successful replay target. Readiness stays false until that target is known and consumed. The existing cache remains lazy-built on the first lookup.

Validation on the six-VM lab:
- Normal startup reached watermark 4194, offset 4193 and readiness true.
- Kafka was stopped and Policy Server restarted. Readiness remained false and target -1 while the broker was unavailable.
- Kafka was started again. The same Policy Server process recovered readiness automatically, without another Policy Server restart.
- All four baseline policy rows were identical before and after; shadow mismatches and lookup errors remained zero.

Active binary: policyServer-startup-20261106T150154Z. Previous binary and source retained in /home/netpro/incoming/startup-retry-20261106T150154Z on Policy VM. JSON results and build log are in evidence/startup-retry-20261106T150154Z locally. This test verifies startup/replay recovery; packet-level deny–allow regression and the domain-index change remain separate pending work.
