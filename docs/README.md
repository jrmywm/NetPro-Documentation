# NetPro Documentation Index

> Current state: [six-VM deployment, thesis adaptations and 14 November checks](current-integration-status-2026-11-14.md). Older topology instructions below are historical.

This documentation is a rebuild runbook for the complete six-VM lab. Build each VM with Adapter 1 left on VMware NAT so SSH, package installation, and certificate distribution remain available. Add the stable `192.168.0.90`-`192.168.0.95` control addresses as secondary addresses; bridged/external networking is an optional phase after the lab is working.

## Rebuild order and acceptance gates

1. Create the six VMs and verify the NAT/management adapters and LAN segments in [the workspace record](../NETPRO_WORKSPACE.md).
2. Build Kafka and confirm ZooKeeper/Kafka and the durable `dpdk-blocked-list` topic.
3. Build Backend/PostgreSQL and Frontend, then verify HTTPS, certificate trust, and dashboard login.
4. Build Policy and NPB, install their local DPDK preparation and application services, and reboot-test both.
5. Build TRex last. Start it with `/usr/local/sbin/netpro-trex-start` before running either traffic generator.
6. Run the HTTP and TLS procedures in [end-to-end validation](end-to-end-http-validation.md), including the telemetry/database checkpoints.

Every VM guide has a reboot checkpoint. Do not advance to packet-path testing until the relevant service, address, hugepages, bindings, and certificate checks pass.

- [Workspace, repository, and laptop-switch workflow](../NETPRO_WORKSPACE.md)
- [Current three-port Policy Server runbook](policy-three-port-upgrade.md) - concurrent HTTP/TLS processing and mixed-traffic telemetry verified before and after Policy VM reboot
- [Engineering checkpoint (2 October)](engineering-checkpoint-2026-10-01.md) - segmented TLS ClientHello evidence, offline regression, and historical source/runtime notes; see the current checkpoint below for latest status
- [Current project checkpoint](current-project-checkpoint-2026-10-03.md) - latest lab/service state, frontend validation, TAP results, failed active test, and repository boundary
- [Professor video demonstration guide](professor-video-demo-guide.md) - dashboard-led 6â€“10 minute demo, preflight gates, safe local traffic, cleanup, and stop criteria
- [Professor discussion: OVS mirroring](professor-discussion-ovs.md) - official OVS mirror behavior and acceptance/design questions; no OVS implementation decision
- [Frontend chart and passive-capture design plan](frontend-chart-and-passive-capture-plan.md) - verified chart timestamp fix and capture/enforcement architecture decision
- [Frontend time-window update](frontend-time-window-2026-10-03.md) - live NPB verification, test/build results, and remaining UI limitations
- [Frontend chart layout](frontend-chart-layout-2026-10-03.md) - chart visibility, columns, expand/collapse, persistence, and Policy Server UI verification
- [Mirrored capture-branch independence demo](passive-capture-independence-demo.md) - measured up/down/up client test and limitations
- [TRex reset-return MAC diagnosis](reset-return-mac-diagnosis-2026-10-02.md) - original/normalized receive captures and Policy telemetry comparison
- [TRex profile MAC correction and mixed retest](trex-profile-mac-fix-2026-10-02.md) - corrected five profiles and controlled eight-second HTTP/TLS/UDP result
- [Server-directed RST proof](server-directed-rst-proof-2026-10-02.md) - controlled routed-backend capture confirms server-directed reset path; bounded VM test only
- [Dedicated-segment RST return-path test](dedicated-rst-return-test-2026-10-03.md) - bounded five-request TLS proof on a segment separate from shared RX; VMX audit found Packet Generator Adapter 4 also attached
- [Virtual TAP VM setup](virtual-tap-setup-2026-10-03.md) - installation/reboot record with initial wiring-pending statement marked historical; see current bounded [live test report](virtual-tap-independence-test-2026-10-03.md)
- [Virtual TAP monitor-branch test](virtual-tap-independence-test-2026-10-03.md) - 12/12 local HTTP/TLS requests succeeded with the monitor NIC on, off, and restored; bounded to monitor-NIC independence
- [Virtual TAP active-blocking test](virtual-tap-active-blocking-test-2026-10-03.md) - failed safety validation with an escaped request and probable reset feedback loop; passive mirroring remains recommended
- [Policy Server VM setup](policy-server-vm-setup.md) - historical two-port mode-switching setup and telemetry fix; retained as historical evidence
- [Kafka Broker VM setup](kafka-broker-vm-setup.md) - verified
- [NPB VM setup](npb-vm-setup.md) - HTTP and TLS classification verified
- [Packet Generator VM setup](packet-generator-vm-setup.md) - repository HTTP and TLS tests verified
- [End-to-end HTTP and TLS validation](end-to-end-http-validation.md) - historical sequential two-port validation; current concurrent validation is in the three-port runbook
- [Repeatable live Google block/allow validation](repeatable-live-google-test.md) - pinned-IP HTTPS block, isolated Edge check, cache-invalidation rollback, and helper scripts
- [Backend VM setup](backend-vm-setup.md) - PostgreSQL, HTTPS API, Kafka, and Policy synchronization verified
- [Frontend VM setup](frontend-vm-setup.md) - HTTPS dashboard, authentication, device pairing, service startup, and reboot persistence verified
- [Setup obstacles and fixes](setup-obstacles-and-fixes.md) - consolidated incident record, resolutions, and remaining validation

The component repositories under `repos/` are read-only baselines for these guides unless a separate source-code change is intentionally requested. Verified local source history includes Policy commits `d658fa2` (historical two-port telemetry mapping), `e75c9f2` (three-port concurrent HTTP/TLS processing), `6784d46` (blocked-IP enforcement baseline), and `c936484` (TLS ClientHello reassembly for SNI); NPB commit `edefaf0` forwards segmented TLS ClientHello packets. Backend commit `bd3c3fc` enables 15-second heartbeat status checks. These are lab evidence, not instructions to push upstream. The three-port Policy layout and mixed traffic were verified after a Policy VM reboot on 25 September 2026. VM files, captures, generated output, secrets, certificates, binaries, logs, and `*.before-*` backups are local-only. For current status, see the [3 October project checkpoint](current-project-checkpoint-2026-10-03.md); the engineering checkpoint remains historical context.
