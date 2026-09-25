# NetPro Documentation Index

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
- [Policy Server VM setup](policy-server-vm-setup.md) - historical two-port mode-switching setup and telemetry fix; retained as historical evidence
- [Kafka Broker VM setup](kafka-broker-vm-setup.md) - verified
- [NPB VM setup](npb-vm-setup.md) - HTTP and TLS classification verified
- [Packet Generator VM setup](packet-generator-vm-setup.md) - repository HTTP and TLS tests verified
- [End-to-end HTTP and TLS validation](end-to-end-http-validation.md) - historical sequential two-port validation; current concurrent validation is in the three-port runbook
- [Repeatable live Google block/allow validation](repeatable-live-google-test.md) - pinned-IP HTTPS block, isolated Edge check, cache-invalidation rollback, and helper scripts
- [Backend VM setup](backend-vm-setup.md) - PostgreSQL, HTTPS API, Kafka, and Policy synchronization verified
- [Frontend VM setup](frontend-vm-setup.md) - HTTPS dashboard, authentication, device pairing, service startup, and reboot persistence verified
- [Setup obstacles and fixes](setup-obstacles-and-fixes.md) - consolidated incident record, resolutions, and remaining validation

The component repositories under `repos/` are read-only baselines for these guides unless a separate source-code change is intentionally requested. Verified local source history includes Policy commits `d658fa2` (historical two-port telemetry mapping) and `e75c9f2` (three-port concurrent HTTP/TLS processing), plus Backend commit `bd3c3fc` (15-second heartbeat status checks); these are lab evidence, not instructions to push upstream. The three-port Policy layout and mixed traffic were verified after a Policy VM reboot on 25 September 2026. VM files, captures, generated output, secrets, certificates, binaries, logs, and `*.before-*` backups are local-only.
