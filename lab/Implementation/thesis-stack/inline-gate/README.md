# Inline QUIC gate prototype

This is the isolated gate component for the planned TAP experiment. It has not
been installed or activated on the TAP. `gate.py` holds only the selected
forwarded IPv4 flow (`192.168.80.29` → `192.168.80.28`, UDP destination 443),
correlates an exact UDP-payload hash with an authenticated NPV1 decision, and
fails closed after 500 ms. An ALLOW is associated with the directional 5-tuple
and the client's nonempty QUIC v1 SCID. A same-SCID Initial continuation or
retransmission reuses that decision; a new SCID on the same tuple is classified
again. ALLOW records a 30-second, bounded inactivity entry for subsequent
packets; recognized packets refresh its expiry. This is new-connection policy
enforcement; it does not revoke an already allowed connection after a policy
change. DENY,
UNSUPPORTED, malformed QUIC headers, and unknown short-header flows are dropped.
Timeouts and unsupported outcomes have separate counters and structured logs.

The NPV1 wire record is 134 bytes, network byte order. Bytes 0–101 are signed
with HMAC-SHA256; bytes 102–133 contain the MAC. Field offsets are defined in
`gate.py` and must stay in sync with the Policy Server implementation. The gate
accepts only UDP replies from `192.168.31.31` to `192.168.31.38:19191`, with the
run's 16-byte session ID and a 32-byte key read from an owner-only file. The key
file contains 64 hex characters and a newline. Absolute issued/expiry times are
checked with 100 ms tolerance (the measured PS/TAP clock difference was about
11 ms); callback and cache lifetimes use monotonic time. Publication sequences
may arrive out of order within a 4096-record replay window.

The callback waits synchronously for a verdict, so the current single queue
consumer serializes packet callbacks during the 500 ms decision window. Queue
saturation and concurrency testing are required before any throughput claim;
this is a lab prototype, not a production performance result.

The gate recognizes QUIC v1 long-header Initial packets and validates their
header/length encoding before asking the Policy Server. QUIC v2, malformed
headers, and unknown short-header flows are unsupported. A non-QUIC UDP payload
passes through. Short headers have no self-describing connection ID length, so
the prototype recognizes fixed-bit candidates only at 18 bytes or longer and
requires a prior ALLOW for the same directional 5-tuple. This is a scoped lab
heuristic, not a general UDP classifier; arbitrary UDP payloads can resemble
short-header candidates. IP fragments from the selected client
to origin are dropped because non-initial fragments do not expose a UDP port.
IPv6, connection migration, established-flow revocation, QUIC Retry semantics,
and fragmented CRYPTO are outside this prototype's claim.

## Local verification

Run `python -m unittest -v test_gate.py` from this directory. The tests cover
NPV1 authentication/scope/expiry, packet parsing, queue correlation, replay
handling, bounded caches, and explicit allow/deny/unsupported paths.

`send_manual_verdict.py` can exercise the queue accept/drop mechanism with a
synthetic HMAC-signed verdict. Run it from the Policy Server host, with a
separate session ID and clearly labeled evidence. Its result proves only queue
handling; it is not a live Policy Server policy decision. Gate event logs expose
the exact payload length/hash and tuple needed for this scoped mechanism test.

`bench_http3.py` is an import-safe, local helper to run later from client .39.
Each request runs in its own curl process, so it cannot reuse a previous
request's connection.
It prints a JSON summary and per-request results without saving files or
changing policy. Example invocations after the gate phase is ready:

```sh
python3 bench_http3.py --requests 20 --concurrency 1 --expect allow
python3 bench_http3.py --requests 20 --concurrency 4 --expect deny
```

It uses the fixed custom curl path, client address, Caddy address, and hostname;
`--curl` can override only the executable path. The helper has not been run
against the lab. Its mock-output unit tests do not start network requests.

## TAP prerequisites

Read-only inspection found Ubuntu 24.04-era kernel `6.8.0-142-generic` with
`CONFIG_BRIDGE_NETFILTER=m`, `CONFIG_NETFILTER_NETLINK_QUEUE=m`,
`CONFIG_NFT_QUEUE=m`, and `CONFIG_NETFILTER_XT_TARGET_NFQUEUE=m`; module files
exist. `iptables-nft` exists; `nft`, the NFQUEUE Python binding, and the
`nfqueue` modules were not installed/loaded at inspection time. The bridge is
`br-tap` with `ens34` and `ens35`; ingress `tc` filters on both mirror to
`ens36`, which should precede a later bridge-forward hook, but actual mirror vs
queue ordering has not been verified with traffic.

Expected runtime dependencies are `nftables`, `python3-netfilterqueue`, and the
kernel modules `nfnetlink_queue` and `nft_queue`. These dependencies and the
setup scripts have not been applied on the TAP. The rule staging scripts only
touch the unique `bridge netpro_quic_gate` nftables table and arrange a 20-minute
systemd rollback. Parent review and a live ordering check are required before
activation.

The staged rule matches IPv4 source/destination and UDP destination port only.
The observed ingress mirroring copies packets toward `ens36`, but this does not
yet prove that the Policy Server observes the same exact bytes before the
queued original is held. That ordering must be established before this gate can
be called integrated enforcement.

The TAP dependency installation completed on 2026-10-13: Ubuntu packages
`nftables 1.0.9-1ubuntu0.1`, `build-essential 12.10ubuntu1`,
`python3-dev 3.12.3-0ubuntu2.1`, `python3-venv 3.12.3-0ubuntu2.1`, and
`libnetfilter-queue-dev 1.0.5-4build1` (plus declared apt dependencies) are
present. An isolated environment at `/opt/netpro/inline-gate-venv` contains
`NetfilterQueue==1.1.0`; the import succeeded. The nftables binary is present.
No firewall hook was created and no NFQUEUE modules were loaded by this setup.
