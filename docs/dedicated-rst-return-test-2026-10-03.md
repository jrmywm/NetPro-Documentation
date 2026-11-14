# Dedicated-segment RST return-path test — 3 October 2026

This report records a single bounded TLS test over a VM network segment separate from shared `NetPro-RX`. A later full VMX membership audit found that this segment also contains Packet Generator Adapter 4 (`ethernet3`), in addition to Policy's RST-output adapter and Gateway `ens38`; the segment is not exclusive to the two test endpoints. This membership caveat does not invalidate the recorded five-request result, but the isolation membership gate was incomplete. No further traffic was run after the extra adapter was discovered. Before any further active test, confirm Packet Generator Adapter 4's intended capture-only role or disconnect it and re-audit membership. This report is separate from the earlier failed shared-`NetPro-RX` active-injection attempt and does not make active injection safe there.

## Post-test wiring follow-up

The user subsequently confirmed Packet Generator Adapter 4 was disconnected. VMX inspection showed `ethernet3` still assigned to the RST segment but configured `startConnected=FALSE`; this verifies the saved startup setting, not the VM's live cable state. Gateway `ens38` was read back DOWN/non-promiscuous with `ip_forward=0`, helper state absent, and timer inactive. No RST retest followed, so this follow-up does not alter the historical five-request membership caveat or prove runtime disconnection of the Generator adapter.

## Bounded result

At approximately 02:14:31–02:14:32 UTC, five TLS requests to the controlled Gateway listener were denied: all five client curls returned exit 35 with HTTP status `000`. The Gateway return filters each counted exactly five packets/230 bytes, with zero drops and zero overlimits; the catch-all counter remained zero.

The Gateway delivery capture contained five client-directed and five server-directed RSTs. Offline sequence analysis matched all ten resets to the triggering ClientHello: the client reset used the ClientHello ACK sequence, and the server reset used the ClientHello sequence plus its payload length. The Client-side capture contained five RSTs, all matching the expected ACK sequence. This is packet-path evidence for these five test transactions and their sequence fields; it is not a general guarantee of reset race behavior or server-application acceptance.

After the temporary Policy rule was removed, five TLS requests succeeded with HTTP 200 and curl exit 0 while the return filters were still installed; both RST filter counters remained zero. Cleanup then removed the helper-owned filters, returned Gateway `ens38` to DOWN/non-promiscuous, and left `ip_forward=0`. Final Gateway checks reported no helper state, an inactive timer, and no test listeners on ports 8080/8443. The TAP monitor (`ens36`), NPB, and Policy services were active. Post-cleanup checks found no temporary Policy test rows in Backend or Policy SQLite.

The initial trial with reversed `tc police conform-exceed` actions is excluded from the pass result: it dropped all five legitimate resets in each direction, and the requests returned HTTP 200. The action order was corrected to drop excess and pass conforming packets before the successful bounded repeat.

## Capture and evidence limits

The passive capture gate initially saw zero frames when it used a direct ingress drop. The reviewed capture helper was changed to mirror ingress frames to a temporary dummy interface, then drop the originals; the bounded capture saw two reset frames with the expected client/Gateway-facing Ethernet endpoints. The return test used a temporary rate-limited RST-only path and a catch-all drop on Gateway `ens38`.

PCAPs are lab-specific and remain local-only; they are not included in this repository. The companion [evidence note](../evidence/dedicated-rst-return/README.md) records byte/record counts, SHA-256 hashes, local paths, and offline analysis. The reviewed helper sources are in [`scripts/dedicated-rst-return`](../scripts/dedicated-rst-return/).

## What this does not establish

- It does not repair or supersede the failed active-injection test on shared `NetPro-RX`; do not repeat active injection there.
- It does not test a physical TAP, TAP-VM power-off/fail-open, guaranteed reset timing, segmented ClientHello, concurrent traffic, or high-load behavior.
- The test covered five TLS requests on the controlled local listener. It does not demonstrate a broad deployment procedure or server acceptance beyond the captured TCP sequence evidence.
- No component source, startup configuration, production policy, or service configuration was changed. The temporary test rule/listener and Gateway path were removed.
