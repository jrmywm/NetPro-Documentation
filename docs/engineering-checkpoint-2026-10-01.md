# Engineering checkpoint — 1 October 2026

This checkpoint records the current segmented TLS ClientHello work and keeps completed observations distinct from pending verification. The lab policy layout is the simultaneous three-port design: HTTP input, TLS input, and a dedicated RST output. The historical selectable two-port procedure remains useful only for old builds and rollback.

## Segmented TLS ClientHello path

The NPB change at `edefaf0` forwards segmented TLS ClientHello packets. Policy change `c936484` reassembles the TLS handshake data used for SNI matching. Reassembly is in-order: gaps and inconsistent overlaps are rejected; general out-of-order reassembly is not implemented or claimed.

On 26 September, a live SNI-only blocking check used a dummy blocked-list IP `192.0.2.123` while the actual server was `192.168.80.128:8443`; the client was `192.168.80.131`. With MTU 128, TSO/GSO disabled, and GRO disabled, the ClientHello arrived in three segments of 76, 76, and 75 bytes. `curl` returned error 35 while the SNI policy was present. After deleting that policy entry, the same request returned HTTP 200. This demonstrates that the decision followed SNI rather than a match against the server IP.

After the 26 September check, the gateway was cleaned: forwarding was disabled, NAT rules were absent, and no test listener remained. This records the post-test cleanup, not a fresh gateway inspection on 1 October. Do not describe the live test as validation of general out-of-order behavior.

## Build and regression status

The current VM services are active using the `split-clienthello-shared` binaries. A normal `make` build has not yet been verified.

The offline regression harness completed with exit code 0: six parser scenarios and two tracker checks passed. The harness verified the parser and tracker source hashes and reconstructed a 517-byte fixture; the fixture itself is not hash-pinned. This is a bounded regression result, not a general out-of-order guarantee. Gaps are rejected; inconsistent overlaps are rejected; arbitrary out-of-order segment reconstruction remains unsupported. The portable harness and invocation are documented under [`scripts/tls-regression`](../scripts/tls-regression/README.md).

Four frontend chart tests passed and the test process exited successfully. `npm run build` exited successfully with existing dependency and lint warnings, and `netpro-frontend` is active. The frontend source change is local commit `e4a947a`.

## Repository boundary

The upstream `Network-Laboratory-UI` component repositories must never be pushed. The personal `jrmywm` documentation repository exists. The three personal component repositories do not currently exist; their creation or use is pending a user decision. Local commit identifiers in this checkpoint document lab state and do not authorize publishing component changes.

## Next verification

1. Verify a normal build for the affected NPB and Policy components and record exact commands and outcomes.
2. Update this checkpoint with any further results only after the evidence is available.
