# Inline Policy Server verdict prototype

This directory is an isolated copy of the experimental candidate sources plus
the Policy Server verdict publisher. It preserves the existing
`thesis_quic_domain()` parser, `domain_checker()` policy lookup and the
independent Close notification. It does not modify `candidate-policy/` or
deploy anything.

## Classification

The publisher is scoped to IPv4 UDP from `192.168.80.29` to `192.168.80.28`
with destination port 443. Each matching datagram produces one decision:

- `ALLOW` (1): the existing parser extracts a hostname and the real
  `domain_checker()` returns false.
- `DENY` (2): the parser extracts a hostname and the real policy lookup
  returns true. The existing Close notification is still attempted
  independently.
- `UNSUPPORTED` (3): the datagram is in scope, but the existing parser cannot
  classify it, or the domain policy lookup did not complete with a valid
  result. This is not counted as a policy deny.

The QUIC branch distinguishes the legacy boolean lookup result from lookup
validity. A populated policy row is DENY; a completed query with no row is
ALLOW. Missing database, SQLite prepare/bind/step/finalize errors, and rows with
an empty policy ID produce UNSUPPORTED. This preserves `domain_checker()`'s
boolean result for existing non-QUIC paths while preventing a lookup failure
from becoming an inline ALLOW.

The parser supports the candidate's narrow IPv4/QUIC v1 Initial path. It does
not reassemble fragmented CRYPTO. IP fragments are outside this publisher's
correlation scope; the gate detects and rejects those separately. QUIC Initial
retransmissions are parsed and published again; the gate correlates a decision
using the directional tuple, UDP payload length and SHA-256 of the exact UDP
payload. An identical retransmission matches again; a retransmission with
different packet bytes is classified as a new datagram. QUIC CID bytes are
covered by that payload hash. The publisher does not maintain connection
state; new connection attempts remain gate decisions. Policy generation is
`0` until the system has a synchronized generation source.

## NPV1 wire format

All integer fields are unsigned big-endian except IPv4 addresses and ports,
which are copied in network byte order from the observed packet.

| Offset | Length | Field |
| ---: | ---: | --- |
| 0 | 4 | ASCII `NPV1` |
| 4 | 1 | version = 1 |
| 5 | 1 | type = 1 (verdict) |
| 6 | 1 | decision: 1 allow, 2 deny, 3 unsupported |
| 7 | 1 | reserved = 0 |
| 8 | 16 | random per-run session ID |
| 24 | 8 | monotonic publication sequence |
| 32 | 8 | policy generation = 0 (reserved) |
| 40 | 8 | issued Unix milliseconds |
| 48 | 8 | expiry Unix milliseconds (issued + 2000) |
| 56 | 4 | source IPv4 |
| 60 | 4 | destination IPv4 |
| 64 | 2 | source UDP port |
| 66 | 2 | destination UDP port |
| 68 | 2 | UDP payload length |
| 70 | 32 | SHA-256 of exact UDP payload bytes |
| 102 | 32 | HMAC-SHA256 over bytes 0 through 101 |

Total message length: 134 bytes. The sender uses a nonblocking UDP socket and
drops/counts a publication on send failure. Destination port is fixed at
19191; bind and peer IPv4 addresses are explicit configuration.

## Runtime configuration

The publisher remains disabled unless every required value is present and
valid. Set these on the Policy Server before startup:

```sh
NETPRO_VERDICT_HMAC_KEY_FILE=/path/to/0600/verdict.key
NETPRO_VERDICT_SESSION_ID=<32 hex characters>
NETPRO_VERDICT_BIND_IPV4=192.168.31.31
NETPRO_VERDICT_PEER_IPV4=192.168.31.38
```

`NETPRO_INLINE_CLOSE_ENABLE=0` disables only the recovered QUIC Close packet
transmission, allowing gate-only enforcement measurements. The default keeps
the existing Close behavior. The domain-deny SNMP notification remains
independent.

The key file contains exactly 64 hexadecimal characters (one final newline is
accepted) and must not grant group or other permissions. A direct
`NETPRO_VERDICT_HMAC_KEY` value is available for isolated local experiments;
do not place it in a broadly readable service drop-in. Key/session values are
never logged. Missing or invalid configuration disables publication without
stopping the Policy Server. Metrics include `verdict_sent`, `verdict_disabled`
and `verdict_errors`.

The gate and Policy Server must be provisioned with the same session and key
for a run. The gate must also validate message age locally, enforce a bounded
pending table, reject replayed publication sequences and accept packets only
from the Policy Server management address.

## Build and check

The staged build helper reads the newest fixed-header manifest used by
`../build-original-candidate.py`, copies this directory's source into a new
`/home/netpro/incoming/npv1-policy-build.*` directory on `192.168.31.31`, and
builds the binary there. It saves source hashes, the binary hash and compiler
log and SQLite lookup fixture result under `evidence/build-*`. It does not
install or launch the binary. The
loopback helper builds the small DPDK publisher fixture and checks its records
with the actual `../inline-gate/gate.py` parser; it also checks that missing
configuration or a group/world-readable key file emits nothing:

```powershell
python .\build_inline_policy.py
python .\run_inline_verdict_test.py
```

The full build compiles `packet-processor.c` separately with
`-Dmain=archived_main`, then links the policy process against DPDK, curl,
Jansson, SQLite, librdkafka and `-lcrypto`. For a manual build, set `FIXED` to
the recovered fixed-header directory recorded in
`Testing/thesis-replication/evidence/quic-fixed-gate-*/sources.json` and add
`inline_verdict.c` to the final link inputs:

```sh
gcc -O1 -g -pthread -DALLOW_EXPERIMENTAL_API \
  -I"$FIXED/headers/usr/include" \
  -I"$FIXED/headers/usr/include/x86_64-linux-gnu" \
  -L"$FIXED/link" \
  $(pkg-config --cflags libdpdk libcurl jansson sqlite3 rdkafka) \
  policyServer.c snmp_reporter.c thesis_monitoring.c thesis_dataplane.c \
  inline_verdict.c quicFunctions.c processor.o -o policyServer-inline \
  $(pkg-config --libs libdpdk libcurl jansson sqlite3 rdkafka) -lcrypto
```

`processor.o` is built from `packet-processor.c` using the same fixed header and
library paths, `-Dmain=archived_main`, and `-pthread`, matching the recovered
candidate builder. Do not replace the running binary as part of this prototype;
parent review, deployment and integration tests are separate steps.
