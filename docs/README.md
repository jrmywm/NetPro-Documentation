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
- [Policy Server VM setup](policy-server-vm-setup.md) - verified, including two-port mode switching, systemd startup, and telemetry fix
- [Kafka Broker VM setup](kafka-broker-vm-setup.md) - verified
- [NPB VM setup](npb-vm-setup.md) - HTTP and TLS classification verified
- [Packet Generator VM setup](packet-generator-vm-setup.md) - repository HTTP and TLS tests verified
- [End-to-end HTTP and TLS validation](end-to-end-http-validation.md) - policy matching, TCP-reset return, and HTTP/TLS telemetry verified
- [Repeatable live Google block/allow validation](repeatable-live-google-test.md) - pinned-IP HTTPS block, isolated Edge check, cache-invalidation rollback, and helper scripts
- [Backend VM setup](backend-vm-setup.md) - PostgreSQL, HTTPS API, Kafka, and Policy synchronization verified
- [Frontend VM setup](frontend-vm-setup.md) - HTTPS dashboard, authentication, device pairing, service startup, and reboot persistence verified
- [Setup obstacles and fixes](setup-obstacles-and-fixes.md) - consolidated incident record, resolutions, and remaining validation

The component repositories under `repos/` are read-only baselines for these guides unless a separate source-code change is intentionally requested. The only verified source fixes are the local Policy commit `d658fa2` (two-port telemetry mapping) and the local Backend commit `bd3c3fc` (15-second heartbeat status checks); neither should be pushed as part of a lab rebuild. VM files, captures, generated output, secrets, certificates, binaries, logs, and `*.before-*` backups are local-only.
