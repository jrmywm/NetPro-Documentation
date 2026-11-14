# Dedicated RST return-path evidence summary

Raw PCAPs are private, lab-specific evidence and are intentionally excluded from this repository. The local raw files used for the offline review were:

- `work/dedicated-rst-return/evidence/capture-only.pcap` — 176 bytes, 2 records, 2 TCP RSTs; SHA-256 `2b974e72f1abca9c4300ce7cd9f91a0f3b6aa78a9fe53dcb517975c07bb2d2a3`.
- `work/dedicated-rst-return/evidence/delivery.pcap` — 4,029 bytes, 35 records, 10 TCP RSTs; SHA-256 `9f2fdcd0f64baa1ccb62e9baa6e512daa8c7cbde33fad0c1c54e901ddce7e306`.
- `work/dedicated-rst-return/evidence/client.pcap` — 3,649 bytes, 30 records, 5 TCP RSTs; SHA-256 `a5b19bfd2179d9058ab34d54d54e39e4dbe9a819f46ccc28d163e6483a1ec2cd4ee`.

Offline analysis found the two passive-gate frames had the expected Ethernet endpoints. In `delivery.pcap`, five client-directed and five server-directed RST sequence values matched the triggering ClientHello: client resets matched the Hello ACK sequence; server resets matched the Hello sequence plus payload length. All five RSTs in `client.pcap` matched the expected ClientHello ACK sequence. These are findings from the bounded captures, not a claim of general or loss-free behavior.

The successful run recorded five matched packets/230 bytes on each of the two return filters, with zero drops and zero overlimits; the catch-all counter remained zero. A later VMX audit found Packet Generator Adapter 4 also attached to the segment; no additional traffic was run after this membership caveat was discovered. See the [test report](../../docs/dedicated-rst-return-test-2026-10-03.md) for request results, cleanup state, and limitations. Do not copy private captures into Git or treat these hashes as packet fixtures.
