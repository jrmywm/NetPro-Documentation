# Inline QUIC validation harness

This is an opt-in, guarded lab orchestrator for the new inline NPV1 QUIC gate. It is isolated from recovered thesis sources and existing Close-only integration. The default mode is read-only preflight. Queue and functional modes require `--execute-reviewed`; use them only after the parent has reviewed the exact current source and authorized that lab run. This implementation has not itself performed a live run.

## Read-only preflight

```powershell
python .\run-inline-validation.py --phase preflight
```

The preflight verifies pinned SSH identities, exact original Policy Server and NPB executable hashes, API/SQLite policy ID baselines, bridge and ingress mirror hooks, gate dependencies and ownership state, HTTP/3 curl, and the existing Caddy `mysite.local` vhost. It records bounded check output without credentials or verdict keys. No lab configuration is changed.

## Parent-reviewed execution

The guarded shakeout is capped at five requests per functional phase:

```powershell
python .\run-inline-validation.py --phase queue --trials 5 --execute-reviewed
python .\run-inline-validation.py --phase functional --trials 5 --execute-reviewed
```

After reviewing shakeout evidence and explicitly approving a longer run, repeat the functional phase with `--trials 20`. Each invocation creates a new evidence directory; choose a fresh `--evidence` path when rerunning.

For an additional bounded latency comparison, opt in only on a reviewed functional invocation with `--benchmark`:

```powershell
python .\run-inline-validation.py --phase functional --trials 20 --benchmark --execute-reviewed
```

This runs 20 fresh-process HTTP/3 requests at concurrency 1, 4, 8, and 16 in both candidate/no-queue and real candidate/queued-allow conditions. It requires every request to be HTTP/3 200, checks gate allow/deny/timeout/unsupported deltas and Caddy access counts for the queued runs, and saves per-request JSON plus a compact result summary. Treat these as bounded latency samples, not throughput or stress-test evidence; 20 requests at concurrency 16 are only one full wave plus a tail.

The queue phase first rolls out only exact-hash-guarded candidates, measures candidate/no-queue HTTP/3 allow, starts the gate and bounded packet captures, then installs the unique owned bridge queue hook only after the gate reports NFQUEUE readiness. It sends synthetic exact-tuple NPV1 ALLOW and DENY verdicts to prove queue release/drop mechanics. These are explicitly marked synthetic and are not Policy Server decisions.

The functional phase removes the mechanism hook, restarts Policy Server with its authenticated publisher enabled but Close transmission disabled, starts a fresh gate/session, and runs candidate queued allow, the same-IP `unrelated-domain.test` specificity control, exact `mysite.local` deny, and allow after policy deletion. Every deny requires matching `policy_deny` gate verdicts, no unsupported/timeout verdicts, HTTP/3 curl failure, and zero matching Caddy access records; a timeout alone never counts as a policy deny. API and SQLite IDs must return to their exact baseline after each temporary policy. Caddy configuration is never changed: the unrelated-domain test is a policy specificity control, not a second served hostname.

## Safety and evidence

Original live executable hashes are fixed in the runner: Policy Server `5892e752bb08395b2b3b1170fc9e45af21ac9251b7dfc9860a7b28dde0865614` and NPB `607a680272458c2dad46e7caf16751990632415c940401f4fbfac68e88196430`. CandidateRollout guards these before replacement and handles bounded restoration. Queue and gate units have exact per-run names; the bridge rule is scoped to client `.80.29` → origin `.80.28` UDP/443. The shared HMAC key is randomly generated in memory and staged to Policy Server and TAP as mode-0600 files; only file paths and fresh session IDs enter service configuration. Key bytes are never passed as command arguments or written to evidence. Exact temporary policy rows, owned queue state, services, candidate overrides, captures, and key files are cleaned up in `finally`; cleanup failures force a failed exit and are reported for operator review.

Evidence includes client-local curl timestamps and `time_total`, HTTP status/version/exit, gate journal snapshots and wait times, publisher counters, Caddy access counts, queue counters, and packet captures named with host and interface. No cross-host timestamp ordering is inferred. The protocol is bounded to this lab's fresh IPv4 QUIC v1 Initial tuple; unsupported versions, fragmentation, ECH, IPv6, migration, established-flow revocation, concurrency/load, and TCP/TLS regression are not covered.

Local checks do not contact VMs:

```powershell
python -m py_compile .\run-inline-validation.py
python .\run-inline-validation.py --phase plan
```

CLI support and local syntax validation do not imply mocked or live benchmark verification. The benchmark option has not been run against the lab by this implementation.
