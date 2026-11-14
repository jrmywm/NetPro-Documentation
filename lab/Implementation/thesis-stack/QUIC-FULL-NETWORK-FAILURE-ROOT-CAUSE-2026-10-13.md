# QUIC full-network deny failure — 2026-10-13

## Finding

The policy match and packet transmission are working, but the end-to-end QUIC deny is not reliable. The strongest supported cause is the architecture: the virtual TAP mirrors the original Client Initial; it does not stop that packet from reaching Caddy. The client-side capture shows the policy Close and Caddy's own handshake response on the same flow, while the request still completes. This is a race, and the mirror-only path has no mechanism to prevent the origin's response or later client retries from winning.

The isolated tests also show the problem is not explained by just one extra hop: bypassing NPB observation alone and bypassing the gateway return alone both still produced 0/5 denied requests. The exact reason the QUIC client does not reliably act on the captured Close is not yet proven: a packet capture proves arrival at the interface, not acceptance by curl's QUIC stack. It does show same-flow Initial retransmissions several seconds after the Close, consistent with either the Close being discarded or another attempt winning.

One code detail needed careful interpretation: the candidate includes `BLOCKED_BY_POLICY_SERVER` in a transport `CONNECTION_CLOSE` (`0x1c`) sent in Initial. RFC 9000 §10.2.3's MUST-clear-Reason-Phrase rule applies when converting an application `CONNECTION_CLOSE` (`0x1d`) to `0x1c`; this code constructs `0x1c` directly, so the non-empty phrase alone is **not** enough evidence to call this packet malformed. The capture decodes the frame, error code, reason, connection IDs, and valid checksums. [RFC 9000 §10.2.3](https://www.rfc-editor.org/rfc/rfc9000.html#section-10.2.3) permits a close in Initial during the handshake and describes when sending it at multiple protection levels is appropriate.

## Evidence

- Two isolated profiles, each with 5 deny probes and 5 allow-after-delete probes:
  - Bypassed NPB observation, retained gateway return: **0/5 denied**; allows passed.
  - Retained NPB observation, bypassed gateway return: **0/5 denied**; allows passed.
- In both profiles, policy-server counters showed thousands of QUIC matches and Close transmissions with zero transmit errors. For the direct-injection profile: `quic_positive=2784`, `close_sent=2779`, `close_errors=0`; these cumulative counters include the five successful allow probes run before the deny rule was installed.
- Client-side capture decodes the injected packet as a QUIC Initial `CONNECTION_CLOSE`, error code 2, with reason `BLOCKED_BY_POLICY_SERVER`. It uses the expected client tuple/CID and its IPv4 and UDP checksums validate.
- The client retransmits an Initial on the same UDP source port several seconds after receiving the Close. Caddy's Initial/Handshake packets are also present on the client leg. This means a Close was emitted and reached the captured interface, but the end-to-end request still completed.
- Bypassing either NPB observation or the gateway return path alone did not make the deny reliable, so neither extra hop by itself explains the failure.

Evidence directories:

- `evidence/isolated-paths-20261013T031319Z/`
- `evidence/live-direct-observe-20261013T031451Z/`
- `evidence/live-direct-inject-20261013T031653Z/`

## Next diagnostic test

Run one denied request at a time with curl's QUIC qlog/verbose trace and a synchronized client capture. Confirm whether curl's QUIC stack processes the Close, or whether it retries/reconnects after it. Then compare a Close at the current Initial level with a controlled candidate that sends the appropriate Close at additional available protection levels. Keep the five-request allow/deny regression after each candidate change. For reliable blocking, the original Client Initial and retries need an inline drop/redirect in addition to passive observation; do not describe the passive mirror alone as reliable active enforcement.

## Recovery / current state

The isolation controller now waits up to 180 seconds for SSH after reboot and restores the original VMX adapters without requiring SSH during cleanup. Full TLS and RST networks are restored; the Policy Server and NPB services are active. The policy database was restored from the exact pre-test snapshot after the test workflow left only one of the four original rows. SQLite integrity is `ok`, and the four pre-test rule IDs are present again. Gateway `ens38` is down as expected.

## Single-request QUIC trace follow-up — 2026-10-13

The next diagnostic was run with one HTTP/3-only curl invocation under a temporary SNI deny rule, with a client pcap, curl trace, gateway return counters, and candidate counters. The policy used the actual Caddy address (`192.168.80.28`). Allow-before, allow-with-candidate, and allow-after-delete all returned HTTP/3 200. The deny request also returned HTTP/3 200, so the end-to-end deny still fails.

The captures make the race more specific. During the deny request, the client repeatedly opened QUIC connections after curl logged `QUIC connect ... failed: Weird server reply`. The Policy Server recorded 122 blocked QUIC Initials, crafted and sent 122 Close packets with zero send errors, and the Gateway return filter delivered all 122. The client capture independently authenticates the Close frames and confirms their destination connection IDs match the corresponding client Initials. On the flow that completed (client UDP port 46772), Caddy's handshake response arrived at 433.934 ms; the injected Close arrived at 435.214 ms; the client continued sending handshake/application data at 436.894 ms and received HTTP/3 200. Thus the return path works, but the passive-mirror design lets the original Initial reach Caddy, whose response can progress before the injected Close takes effect. The single deny transfer ultimately succeeds despite many rejected connection attempts.

The earlier premature metrics check sampled the periodic stats file before its next refresh; the final candidate snapshot and packet capture agreed at 122 Close transmissions. The guarded validator now supports a one-request trace mode, an explicit target-IP override, and a bounded wait for that periodic metrics refresh. Evidence is in `evidence/live-thesis-profile-20261013T034337Z/` (`client-curl-deny.trace`, both client/gateway pcaps, `close-analysis.json`, and `active-baseline-*.json`).

After cleanup, the Policy Server and NPB services are active and their original binary hashes are restored. The Policy Server database integrity is `ok` and the same four baseline policy IDs are present. The temporary policy is deleted, Gateway `ens38` is down, its temporary return filter and TCP fallback rule are absent, and IPv4 forwarding is off.

## Updated interpretation / next step

The captures establish that the Gateway return path delivers authenticated, decodable Close packets to the client interface. They do not establish acceptance by the client's QUIC stack or rule out every protocol issue. On the successful traced flow, the server handshake preceded the Close: this supports a timing/architecture race, but does not establish it as the sole defect. The inline-drop isolation control below confirms that preventing client UDP/443 from reaching Caddy makes this one test fail closed; a static drop alone does not validate policy-coupled enforcement. Keep the passive mirror for observation, but it is not itself an inline enforcement point.

## Inline-drop isolation control — 2026-10-13

To isolate that race, a temporary, narrowly scoped Gateway INPUT drop matched only Client `192.168.80.29` → Caddy `192.168.80.28` UDP destination port 443. The rollback timer was armed before insertion. During the deny probe, curl exited 28 with HTTP 000 after its 3-second connect timeout; its trace shows 940 `Weird server reply` retries and no HTTP/3 200. The Gateway counted 941 matching UDP drops. The Policy Server independently matched 941 QUIC packets and sent 941 Close packets with zero send errors; the Gateway return filter delivered all 941 with zero drops. The client capture authenticated the Close frames. The sole server-handshake packet in the client capture occurred before the inline drop was inserted; no server handshake was captured during the deny interval. After the test rule was removed and the policy deleted, the allow-after-delete control returned HTTP/3 200.

After removing the temporary Gateway drop and deleting the test policy, the allow-after-delete request returned HTTP/3 200. This is an isolation/control result: a static, temporary firewall rule—not a policy-driven NetPro inline decision—prevented Caddy from receiving the original traffic. It proves that suppressing the origin path removes the observed race, but it does **not** mean NetPro's policy engine is already wired to an inline enforcement point.

Evidence is in `evidence/live-inline-drop-20261013T034747Z/`, including the curl trace, client/Gateway captures, counter snapshots, and `summary.json`. The guarded validator now has an opt-in `THESIS_INLINE_DROP_DIAGNOSTIC=1` mode for this control. Cleanup was verified: test firewall rules and rollback timer are absent, Gateway `ens38` is down with forwarding off, original Policy Server/NPB hashes are restored, and SQLite integrity plus all four baseline policy IDs are unchanged.

## Next implementation question

Timing clarification: the earlier statement that the sole captured server-handshake packet occurred before drop insertion is withdrawn. Host command timestamps and guest capture timestamps are not directly comparable without clock-offset measurements. Use client-local curl trace and capture timestamps for attribution; the denied curl trace contains no HTTP/3 200.

Design and test a policy-coupled inline enforcement mechanism: how a verified SNI deny decision at the NPB/Policy Server reaches an inline point that can stop the original Initial and retries before Caddy. Keep this static-drop result labeled as a control only; do not present it as completed NetPro active blocking.

