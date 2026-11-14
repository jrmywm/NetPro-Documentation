# Inline QUIC enforcement — results (13 October 2026)

## Scope and status

This is a functional check of a prototype inline gate for new QUIC v1 connections over UDP/443 from the lab client (`192.168.80.29`) to Caddy at `192.168.80.28`, using `mysite.local` and an unrelated-domain/same-origin-IP control. It is not evidence of physical TAP fail-open behavior. Candidate Policy/NPB services were temporarily switched in under a guarded runtime override, then the original services were restored. Close transmission was disabled so enforcement results are attributable to the gate, not injected Close packets. Scope is the tested lab path and new connections; this does not establish established-flow revocation or general QUIC coverage.

## Functional run 02

Run `3654d7be51ca` reports `passed: true`, with five HTTP/3-only requests in each principal phase. Results: no-queue allow 5/5 returned HTTP 200; queued allow 5/5 returned HTTP 200 and all five reached Caddy; an unrelated domain sharing the origin IP also returned 200 in 5/5; policy deny produced five curl timeouts (exit 28), no completed Caddy requests, and zero timeout/unsupported gate outcomes; after deleting the temporary rule, HTTP/3 returned 200 in 5/5.

Initial five-request run `3654d7be51ca` recorded 25 gate-wait samples (median 0.85 ms, p95 1.63 ms). Its deny counter recorded ten retry-related deny events for five requests—not ten independent trials. See [run 02 summary](evidence/inline-functional-parent-20261013-02/inline-summary.json).

## 20-request functional run and bounded comparison

Run `05b74a6ed709` passed each principal phase at 20 requests: no-queue allow 20/20; queued allow 20/20 with 20 Caddy records; unrelated domain on the same origin IP 20/20; denied `mysite.local` 20/20 timed out (curl exit 28), with zero Caddy records; and after policy deletion 20/20 returned HTTP 200. Gate outcome counters recorded 40 deny events for the 20 denied requests (retries); unsupported and timeout outcomes were zero. Across 180 gate-wait samples, median was 0.79 ms and p95 1.66 ms. See [run 03 summary](evidence/inline-functional-parent-20261013-03/inline-summary.json).

Offline packet correlation matched all 40 final gate `policy_deny` datagrams to the mirrored TAP capture by tuple, UDP payload length and payload hash: 20 denied source ports, each with two retry datagrams. The gateway origin-facing capture had zero exact matches and no UDP/443 packet on those 20 deny ports. This supports the scoped drop-path result; no cross-host packet timing comparison is claimed. Captures are in the run 03 evidence folder.

The bounded HTTP/3 comparison attempted 20 requests at each concurrency, with no failures in any of the eight runs (160 requests total). Request times are milliseconds:

| Concurrency | No-queue median / p95 | Gated median / p95 | Median delta |
| ---: | ---: | ---: | ---: |
| 1 | 9.36 / 12.67 | 12.26 / 14.72 | +2.90 |
| 4 | 13.65 / 20.80 | 15.79 / 19.38 | +2.14 |
| 8 | 15.93 / 28.30 | 23.12 / 34.55 | +7.19 |
| 16 | 23.61 / 50.65 | 23.92 / 44.72 | +0.31 |

These are descriptive deltas from a short sample, not causal proof or a stress/load result. Raw files are `benchmark-*.json` in the run 03 evidence directory.

## Separate queue-mechanism check

Queue run `1c2e9a341906` is a manual synthetic mechanism test, not a Policy Server decision: one matching NPV1 ALLOW released a request (HTTP 200); one matching synthetic DENY dropped a request (curl exit 28, no Caddy access record). Its gate-wait statistic has only three samples (median/p95 192.14 ms). It must not be pooled with the production-policy functional phases or described as stress testing. See [queue evidence summary](evidence/inline-queue-parent-20261013-04/inline-summary.json).

Independent post-run verification confirmed the original Policy (`5892e752…`) and NPB (`607a6802…`) binaries active, Policy SQLite integrity `ok` with the four baseline rows intact, no owned TAP nftables state, no listener on port 19191, and no gate unit. All six local PCAP hashes matched their recorded values. The evidence supports only the scoped new-connection behavior above. It does not establish immediate revocation of established QUIC sessions, behavior under meaningful load, or physical inline failure transparency, and it should not be presented as identical to thesis results.

## Reproduction command

For a reviewed five-trial reproduction in PowerShell:

```powershell
Set-Location 'C:\Users\jim\Documents\NetPro\Implementation\thesis-stack'
$evidence = "evidence/inline-functional-$((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))"
python .\inline-validation\run-inline-validation.py --phase functional --trials 5 --execute-reviewed --evidence $evidence
```

The runner prompts for the lab password with `getpass`; do not put credentials on the command line or in evidence. `--execute-reviewed` activates a guarded, temporary lab workflow; it does not permanently enable production enforcement. The separate synthetic queue check in run 02/03 remains a manual mechanism test, not a Policy decision or stress test.
