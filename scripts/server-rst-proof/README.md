# Server-directed RST proof helpers

These are environment-specific helpers for the controlled VM test documented in [the proof report](../../docs/server-directed-rst-proof-2026-10-02.md). Review the scripts before use and adapt addresses/interfaces only with the lab owner. The Gateway helper requires root privileges; the client helper requires an interactive sudo prompt. Do not run concurrently with other packet-path tests. The tested run used a temporary policy which was removed afterward; it did not modify production source or startup configuration.

Captured packets, command results, cleanup checks, and telemetry are preserved under [`evidence/server-rst-proof`](../../evidence/server-rst-proof/).

[`preflight.sql`](preflight.sql) is a read-only backend query for the temporary proof policy and current NPB/Policy packet-ID baselines. The packet captures are workstation-local, gitignored evidence; they are not included in repository commits.
