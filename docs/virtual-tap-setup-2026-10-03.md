# Virtual TAP setup — 3 October 2026

An isolated Ubuntu 24.04 VM, `netpro-virtual-tap`, is configured as a software mirror bridge. This is a virtual capture-path prototype, not a physical TAP or fail-open appliance: powering off the VM interrupts the bridge datapath.

| Interface | Role | Verified state |
| --- | --- | --- |
| `ens33` | NAT management | `192.168.31.38/24`, gateway/DNS `192.168.31.2`; fresh SSH connection verified |
| `ens34`, `ens35` | Bridge ports | Attached to `br-tap`; bridge up, STP enabled |
| `ens36` | Monitoring | Up, no carrier, no IP addresses; incoming monitor-port traffic is dropped, while mirrored copies egress here |

The mirror service is enabled and active; start/stop replay passed without taking `br-tap` down. Netplan generation and both helper syntax checks passed. DNS resolution and gateway ping passed. An isolated network-namespace smoke test passed with mirroring on, off, then restored: endpoint pings succeeded in all phases, with four observed mirrored ICMP packets when on and none when off. This was not real client traffic.

Rollback was canceled only after fresh SSH and service/address checks. The original Netplan backup is `/var/tmp/netpro-virtual-tap.GwWPvi`; manual rollback is available through `/usr/local/libexec/netpro-virtual-tap/setup.sh rollback`. Cloud-init network generation is disabled. A new machine-id was verified. A guest-only reboot completed on 3 October Taipei; afterward the pinned-key SSH connection, sole static default route, enabled/active mirror service, ingress mirror rules, and monitor-drop rule were restored, with no rollback timer. Bridge ports reached forwarding state and the gateway ping passed. This verifies the TAP VM's reboot persistence, not end-to-end traffic.

VMware wiring remains pending: connect only the new TAP VM's Adapter 4 to the existing `NetPro-RX` segment; its Adapter 4 is currently disconnected. The client and gateway Adapter 2 links to `NetPro-TAP-Client` and `NetPro-TAP-Gateway` are not yet changed. Thus external VM-to-VM traffic and NPB telemetry remain unverified. Existing NPB/Policy services were not changed.

See the [helper README](../scripts/virtual-tap/README.md) and [install/test evidence](../evidence/virtual-tap/).
