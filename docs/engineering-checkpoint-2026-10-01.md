# Engineering checkpoint — 2 October 2026

This checkpoint records the current segmented TLS ClientHello work and keeps completed observations distinct from pending verification. The lab policy layout is the simultaneous three-port design: HTTP input, TLS input, and a dedicated RST output. The historical selectable two-port procedure remains useful only for old builds and rollback.

## Segmented TLS ClientHello path

The NPB change at `edefaf0` forwards segmented TLS ClientHello packets. Policy change `c936484` reassembles the TLS handshake data used for SNI matching. Reassembly is in-order: gaps and inconsistent overlaps are rejected; general out-of-order reassembly is not implemented or claimed.

On 26 September, a live SNI-only blocking check used a dummy blocked-list IP `192.0.2.123` while the actual server was `192.168.80.128:8443`; the client was `192.168.80.131`. With MTU 128, TSO/GSO disabled, and GRO disabled, the ClientHello arrived in three segments of 76, 76, and 75 bytes. `curl` returned error 35 while the SNI policy was present. After deleting that policy entry, the same request returned HTTP 200. This demonstrates that the decision followed SNI rather than a match against the server IP.

After the 26 September check, the gateway was cleaned: forwarding was disabled, NAT rules were absent, and no test listener remained. This records the post-test cleanup, not a fresh gateway inspection on 2 October. Do not describe the live test as validation of general out-of-order behavior.

## Build and regression status

On 1 October, forced default builds (`make -B`) compiled successfully on both VMs. The NPB default static binary SHA-256 is `607a680272458c2dad46e7caf16751990632415c940401f4fbfac68e88196430`; its build log and backups are in `/tmp/netpro-normal-build.YelWcD/` (`make.log`). The Policy default shared binary SHA-256 is `5892e752bb08395b2b3b1170fc9e45af21ac9251b7dfc9860a7b28dde0865614`; its build log and backups are in `/tmp/netpro-normal-build.nJDGng/` (`make.log`).

The NPB Makefile target dependencies omit `tls_record_tracker.h`; `make -B` ensured this build compiled the current header. Until dependency tracking is fixed, force a rebuild after header-only changes.

### Runtime handoff and mixed traffic — 2 October Taipei (1 October UTC)

The rebuilt default binaries were selected for a controlled live test. NPB ran as PID `4286`, selector `packetBroker-static`, SHA-256 `607a680272458c2dad46e7caf16751990632415c940401f4fbfac68e88196430`. `/home/netpro/netpro-runtime-handoff.iOZLlD` is an empty handoff directory; the script did not copy the executable there. The rollback executable remains at `build/packetBroker-split-clienthello-shared`. Policy ran as PID `4781`, selector `policyServer-shared`, SHA-256 `5892e752bb08395b2b3b1170fc9e45af21ac9251b7dfc9860a7b28dde0865614`; rollback binary `build/policyServer-split-clienthello-shared` and database backup `/home/netpro/netpro-runtime-handoff.RZkRiD/policy.db.before` were retained. All four Policy ID/domain/IP rows were identical and database integrity was `ok`. No policy or source changes were made.

The mixed HTTP/TLS/UDP run used the existing TRex test directory and exited `0` after eight seconds, from `2026-10-01 16:04:06` through `16:04:14 UTC` (`2 October Taipei`):

```bash
PYTHONPATH=/opt/trex/v3.04/automation/trex_control_plane/interactive \
  python3 npb_testing_http_https_udp.py --sizes 256 --pps_values 1000 2000 1000
```

Using pre-test baselines NPB packet ID `157326` and Policy packet ID `154953`, active rows were NPB `157393`–`157401` and Policy `155020`–`155028`. NPB totals were 2,001 HTTP out, 2,001 TLS out, and 12,005 no-match packets. Policy totals were 1,999 HTTP in, 2,001 TLS in, 4,000 client RSTs, 4,000 server RSTs, 8,002 transmitted, and 8,003 received on its output. This includes a two-packet HTTP out/in delta and 8,000 generated RSTs versus 8,002 transmitted. Steady intervals showed 250 HTTP and 250 TLS packets with 500 RSTs in each direction and 1,000 Policy transmissions.

The TRex JSON for `2026-10-01T16:04:15` recorded 8,003 transmitted, 2,001 received, and zero errors. A 25 September result showed a similar receive-count ratio (8,027 transmitted, 2,007 received, zero errors), suggesting the discrepancy may predate this rebuild; its cause is unverified. These sampled counters are not exact packet-delivery accounting and do not prove loss-free reset delivery or identify a regression. Investigation of the TRex receive path/destination MAC remains open. The test confirms that the rebuilt NPB and Policy binaries handled the mixed workload, with delivery accounting still unresolved.

Two setup issues were corrected before traffic generation: the installed `sqlite3` did not support `-json`, so the inspection script was changed to use a supported output format; a non-interactive shell lacked the TRex module path, so `PYTHONPATH` was set for the test command. Neither issue altered Policy data or source.

For repeatable paired row and total queries, see [`scripts/tls-regression/mixed-results.sql`](../scripts/tls-regression/mixed-results.sql); provide the NPB and Policy pre-test IDs with `psql -v npb_baseline=... -v ps_baseline=... -f mixed-results.sql`.

Final verification showed NPB active at PID `4286` with selector `packetBroker-static` and Policy active at PID `4781` with selector `policyServer-shared`; Policy DB integrity remained `ok` with four rows. TRex PID `4139` was stopped gracefully after the run, and RPC ports `4500` and `4501` were no longer listening, restoring the initially stopped TRex state. No service restart, policy change, or source change was made as cleanup.

The offline regression harness completed with exit code 0: six parser scenarios and two tracker checks passed. The harness verified the parser and tracker source hashes and reconstructed a 517-byte fixture; the fixture itself is not hash-pinned. This is a bounded regression result, not a general out-of-order guarantee. Gaps are rejected; inconsistent overlaps are rejected; arbitrary out-of-order segment reconstruction remains unsupported. The portable harness and invocation are documented under [`scripts/tls-regression`](../scripts/tls-regression/README.md).

Four frontend chart tests passed and the test process exited successfully. `npm run build` exited successfully with existing dependency and lint warnings, and `netpro-frontend` is active. The frontend source change is local commit `e4a947a`.

## VM network identity and static addressing — 2 October 2026

An initial check reported two VMs with the same Linux machine-id (`cf5c76ab092042a6b98fa7ee449eb8e7`) despite different MAC addresses, and duplicate DHCP assignments/conflicts were observed for `192.168.31.138` and `192.168.80.132`. A follow-up audit verified unique IDs for the six core service VMs; the separate Gateway/Client pair still share the reported machine-id. VMware's DHCP pool covers `.128`–`.254` on both subnets.

Static IPv4 configuration is now applied with `/24` masks: NAT addresses are on `ens33`, lab-link addresses are on `ens37`, and default gateway/DNS `192.168.31.2` is on `ens33` only:

| VM | `ens33` NAT address | `ens37` lab-link address | Default gateway and DNS on `ens33` |
| --- | --- | --- | --- |
| Gateway | `192.168.31.37/24` | `192.168.80.28/24` | `192.168.31.2` |
| Client | `192.168.31.39/24` | `192.168.80.29/24` | `192.168.31.2` |

Validation passed: both VMs pinged `1.1.1.1`, resolved `example.com`, and the gateway pinged the client's `192.168.80.29` address. No automatic rollback timers remain. Cloud-init network generation is disabled through `99-netpro-disable-network-config.cfg`; original configuration files are preserved in `/var/tmp/netpro-static.3u3z9r` on the gateway and `/var/tmp/netpro-static.9GqRLs` on the client. A second duplicate-client backup exists at `/var/tmp/netpro-static.lRsxfk`; the original client backup is `9GqRLs`.

The address configuration has not been reboot-tested. Existing proxy and test references may still point at the old addresses and must be updated before use. Tinyproxy was inactive during this change.

The six service-VM NAT addresses are now applied and verified; see the [static-addressing audit and migration record](static-addressing-2026-10-02.md). Their reboot persistence remains unverified.

## Passive capture and reset-return findings — 2 October Taipei

The client received HTTP 200 with Gateway mirror `ens38` up, down, then up; NPB telemetry appeared in the connected phases and no request-matched row appeared while down. Cleanup returned the Gateway to `ip_forward=0`, `ens38` down, no demo filters/rules/timer, and the Client to its default route. This demonstrates mirror-branch independence only, not a physical TAP or Gateway-failure transparency; no PCAP was produced. Details are in the [demo record](passive-capture-independence-demo.md).

The TRex receive test confirmed that temporary MAC normalization restored 100 TLS client-directed RSTs: the original profile returned 100 HTTP RSTs only, while the normalized profile returned 100 HTTP and 100 TLS RSTs. Policy accepted both 100-packet flows and generated 400 total client/server RSTs per case; server-directed resets were not expected at the TRex receive port. The test supports the stale TLS fixture-MAC diagnosis but was a TRex endpoint capture, not an independent wire capture or production fix. See the [reset-return MAC diagnosis](reset-return-mac-diagnosis-2026-10-02.md). No production source or fixture changed; TRex remains stopped.

## Repository boundary

The upstream `Network-Laboratory-UI` component repositories must never be pushed. The personal `jrmywm` documentation repository exists. The three personal component repositories do not currently exist; their creation or use is pending a user decision. Local commit identifiers in this checkpoint document lab state and do not authorize publishing component changes.

## Next verification

1. Review a production-profile correction separately; the temporary normalized-MAC result is diagnostic only and changed no source or fixture.
