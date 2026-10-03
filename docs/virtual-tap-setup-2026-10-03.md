# Virtual TAP setup — 3 October 2026

An isolated Ubuntu 24.04 VM, `netpro-virtual-tap`, is configured as a software mirror bridge. This is a virtual capture-path prototype, not a physical TAP or fail-open appliance: powering off the VM interrupts the bridge datapath.

| Interface | Role | Verified state |
| --- | --- | --- |
| `ens33` | NAT management | `192.168.31.38/24`, gateway/DNS `192.168.31.2`; fresh SSH connection verified |
| `ens34`, `ens35` | Bridge ports | Attached to `br-tap`; bridge up, STP enabled |
| `ens36` | Monitoring | Up, no carrier, no IP addresses; incoming monitor-port traffic is dropped, while mirrored copies egress here |

The mirror service is enabled and active; start/stop replay passed without taking `br-tap` down. Netplan generation and both helper syntax checks passed. DNS resolution and gateway ping passed. An isolated network-namespace smoke test passed with mirroring on, off, then restored: endpoint pings succeeded in all phases, with four observed mirrored ICMP packets when on and none when off. This was not real client traffic.

Rollback was canceled only after fresh SSH and service/address checks. The original Netplan backup is `/var/tmp/netpro-virtual-tap.GwWPvi`; manual rollback is available through `/usr/local/libexec/netpro-virtual-tap/setup.sh rollback`. Cloud-init network generation is disabled. A new machine-id was verified. A guest-only reboot completed on 3 October Taipei; afterward the pinned-key SSH connection, sole static default route, enabled/active mirror service, ingress mirror rules, and monitor-drop rule were restored, with no rollback timer. Bridge ports reached forwarding state and the gateway ping passed. This verifies the TAP VM's reboot persistence, not end-to-end traffic.

Historical note: the initial wiring-pending status was superseded after this installation record. The later [live monitor-branch test](virtual-tap-independence-test-2026-10-03.md) exercised local HTTP/TLS traffic from Client to Gateway with the monitor branch on, off, then restored: 12/12 requests returned HTTP 200, and matching NPB samples were observed before/after but not during the monitor-off interval. This verifies the bounded monitor-branch check only. It does not prove VM-power-off transparency, physical TAP fail-open behavior, or packet-level loss/latency; no PCAP was recorded. The separate [active-blocking attempt failed its safety check](virtual-tap-active-blocking-test-2026-10-03.md) and must not be repeated on shared `NetPro-RX`.

See the [helper README](../scripts/virtual-tap/README.md) and [install/test evidence](../evidence/virtual-tap/).
