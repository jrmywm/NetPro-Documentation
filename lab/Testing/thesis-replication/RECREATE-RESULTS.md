# Recreate the adapted Bintang/Ibrahim experiments

Run in **Windows PowerShell on the VMware host**, not inside a VM. Evidence is written below this folder with UTC run timestamps. Local report date is Asia/Taipei (UTC+8).

```powershell
Set-Location 'C:\Users\jim\Documents\NetPro\Testing\thesis-replication'
```

## 1. Bintang: live HTTP-driven SNMP

```powershell
python -u .\run_live_snmp.py
python .\summarize_live_snmp.py
$snmpRun = Get-ChildItem .\evidence -Directory -Filter 'snmp-live-http-*' |
    Sort-Object Name | Select-Object -Last 1
Get-Content -LiteralPath (Join-Path $snmpRun.FullName 'results.json') -Raw |
    ConvertFrom-Json |
    Select-Object trial, sent_packets, traps_received, duplicates_delta, snmp_overflow_delta, passed |
    Format-Table -AutoSize
Get-Content -LiteralPath (Join-Path $snmpRun.FullName 'run-cleanup.json')
```

For the retained successful run, use the exact folder `evidence\snmp-live-http-20261012T233321Z` rather than selecting the latest. Expected retained data: 10-event smoke, five 1,000-event trials and 10,000-event trial, all domain traps delivered. Real aggregate summary at agent uptime 121.07 s. Capture shows 15,007 client-directed resets, not 15,010; retain the discrepancy.

This is an adapted test with paced raw HTTP segments and an asynchronous sender, not established HTTP client sessions, original shell-per-trap performance, Zabbix polling, or proof of client TCP denial.

## 2. Ibrahim: real HTTP/3 and 15 load trials

For a short functional demo plus client-side packet timing, without the 15-trial load benchmark:

```powershell
python -u .\run_live_quic.py --functional-only
python .\analyze_quic_timing.py
```

```powershell
python -u .\run_live_quic.py
python .\summarize_live_quic.py
$quicRun = Get-ChildItem .\evidence -Directory -Filter 'quic-live-http3-*' |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'results.json') } |
    Sort-Object Name | Select-Object -Last 1
Get-Content -LiteralPath (Join-Path $quicRun.FullName 'functional.json') -Raw |
    ConvertFrom-Json |
    Select-Object mode, trial, protocol, class, handshake, tcp_fallback |
    Format-Table -AutoSize
Import-Csv -LiteralPath (Join-Path $quicRun.FullName 'trials.csv') |
    Format-Table configured_pps, trial, started_requests, achieved_request_starts_per_s, policy_close, http_200, timeout -AutoSize
Get-Content -LiteralPath (Join-Path $quicRun.FullName 'cleanup.json')
```

Configured levels: 100/200/500/1000/1500 fresh connection starts/s; each runs 30 seconds three times. Do not describe the configured rate as achieved PPS: examine actual starts and authenticated positive Initial counters. A QUIC retransmission can count as another positive Initial. A Close submitted to the NIC is not the same as client-confirmed blocking.

## 3. Supplemental actual packet input and same-clock timing

Run only after the prior run has finished and cleanup is verified; do not run controllers concurrently.

```powershell
python -u .\run_live_quic.py --packet-replay
python .\summarize_quic_replay.py
$replayRun = Get-ChildItem .\evidence -Directory -Filter 'quic-replay-dataplane-*' |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'results.json') } |
    Sort-Object Name | Select-Object -Last 1
python .\analyze_quic_timing.py $replayRun.FullName
Get-Content -LiteralPath (Join-Path $replayRun.FullName 'RESULTS.md')
Get-Content -LiteralPath (Join-Path $replayRun.FullName 'packet-timing.json')
Get-Content -LiteralPath (Join-Path $replayRun.FullName 'cleanup.json')
```

Packet replay reuses one authenticated Initial fixture, with varying source ports, to isolate packet-processing throughput from the Python fresh-client CPU ceiling. It is **not** 45,000 independent HTTP/3 requests and has no client-confirmed denial percentage. The functional portion preceding replay still uses fresh live clients, and its full gateway capture permits same-clock packet timing. Functional client elapsed time includes draining timers and is not packet latency.

## Safety and prerequisites

Optional cross-VM system-object polling (private read-only agent, ten samples; not Zabbix):

```powershell
python -u .\run_snmp_polling.py
```

- All VMs needed for the existing TAP/NPB/PS/Kafka/backend path must already be powered on and reachable at their saved static IPs.
- Existing known-host keys, private aioquic runtimes, verified candidate build directories and baseline policy IDs are checked. A changed binary or occupied owned test port causes a stop rather than an automatic overwrite.
- Scripts temporarily override the PS/NPB systemd executable with timer-guarded candidates; no source or permanent executable symlink is changed. These are lab experiments, not a production rollout.
- Temporary blocked rules are created/deleted through the Backend API using the exact returned UUID; legacy policies are preserved.
- Each run has cleanup evidence. If `errors` is nonempty, inspect it before rerunning. Do not force-remove unrelated rules or services.
- QUIC server uses UDP 18443 and a private test certificate. There is no TCP fallback. Return filtering is narrowly limited to the test flow.
- Source safety fixes and different hardware/endpoints mean results need not numerically match the theses. Retain unexpected HTTP 200 escapes and failed trials.

## Presentation screenshots

Capture the actual visible PowerShell terminal after displaying the functional table, the load table and cleanup JSON. For SNMP show the seven workload rows and summary reception. Include `RESULTS.md` tables for exact metric definitions; do not label loopback/offline module tests as end-to-end system tests. Zabbix/polling and matching thesis hardware remain separate outstanding work.
