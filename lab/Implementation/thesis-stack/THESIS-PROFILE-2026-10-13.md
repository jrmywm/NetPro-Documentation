# Closest client/workload profile, 13 October 2026

Evidence: `evidence/live-thesis-profile-20261013T020834Z`.

Used actual Caddy and HTTP3-enabled curl with `--http3 --max-time 5 -k -v`.
Only test-client TCP/443 fallback to the local Caddy address was temporarily
blocked. No UDP drop, server delay or inline policy gate was introduced.
SNMP notification hooks were disabled for this isolated Ibrahim test.
Client-only original Close mode restored; bidirectional experiment removed.
Source compatibility/memory bounds fixes remain labelled in candidate code.

## Results

- Original allow control: 3/3 HTTP 200, HTTP/3.
- Candidate allow: 5/5 HTTP 200, HTTP/3.
- Deny: 0/5 blocked; all five returned HTTP 200, HTTP/3.
- Allow after policy deletion: 5/5 HTTP 200, HTTP/3.
- PS counters: 489 blocked Initial events, 489 Close crafted/sent, no TX errors.
- Independent client-capture decryption authenticated all 489 captured Close
  packets. UDP port reuse is grouped by client SCID, not port alone.
- Mean Initial-to-Close: 1.857761 ms (min 0.867, max 4.478).
- Mean Initial-to-server-Handshake for matched connections: 3.491845 ms.
- Handshake arrived before or in the same capture timestamp as Close in 13
  connections. Same timestamps do not establish processing order.
- Curl automatic retries eventually escaped injection in every complete test.

These 489 Close events are not 489 independently scripted HTTP requests.
They include curl's retries inside the five functional deny probes.
Thesis Close-TX/positive-packet percentages must not be reported as complete
request-denial percentages. Captures use a single client clock for both delays.
Capture processing can affect timestamps; these are observed lab measurements.

## Remaining topology difference

Thesis: shared/flooding Proxmox bridge, direct PS ingress and injection.
Current: client -> Linux TAP bridge -> gateway, and TAP mirror -> NPB -> PS;
Close returns PS -> NetPro-RST -> gateway redirect -> TAP -> client.
The extra NPB and gateway-return path is absent from the standalone thesis test.
Its precise contribution to delay has not yet been isolated.

## Proposed direct comparison (not yet performed)

Temporarily connect only the Policy Server's TLS input (VMware Network Adapter
3, ethernet2) and injection output (Network Adapter 4, ethernet3) to
`NetPro-TAP-Client`. This is the existing client-side test LAN segment, not a
new VM, inline gate, or physical TAP. Verify promiscuous delivery first rather
than assume VMware LAN-segment behavior exactly matches Proxmox flooding.

Keep management, HTTP adapter and every other VM adapter unchanged. Protect
SQLite before any PS service/VM shutdown; recovered baseline shutdown can
unlink policy.db. Save exact VMX and segment mappings. Use a bounded test
window and restore Adapter 3 to NetPro-TLS and Adapter 4 to NetPro-RST.
Do not change a running VMX file underneath VMware.

This temporarily bypasses NPB for standalone QUIC comparison. Passing it would
not establish that the combined NPB/PS/SNMP system passes; integration must
then be tested separately. No NIC rewiring was performed in this run.

## Cleanup

Temporary policy removed; owned TCP fallback rule and UDP return rule removed;
gateway return interface returned DOWN; original NPB and PS binaries restored.
Installed Caddy/Net-SNMP/Zabbix/curl remain installed. No upstream push.
