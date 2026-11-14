# QUIC client diagnostics — 7 November 2026

Temporary gateway helper, no original traffic holding/dropping. Actual curl/ngtcp2 debug build used from source build tree; installed prefix curl unchanged. DEBUG_NGTCP2 enabled for build only, original source restored. Active NPB/Policy Server not changed.

First helper had tcpdump buffering: measured 593–1019 ms Initial-to-Close, explaining lack of received Close in client logs. Earlier negative helper tests were therefore insufficient to evaluate prompt corrected injection. Fixed helper with --immediate-mode.

Immediate diagnostic: fixed SCID/PN0 rejected explicitly as mismatched SCID in 5/5 client logs. Correct actual server SCID/PN1: client accepted 507 CONNECTION_CLOSE frames across five curl requests (214,7,8,148,130); each request nevertheless eventually returned HTTP3 200. Distinct connection IDs in accepted frames directly demonstrate repeated connections. Client capture contains injected packets, with Initial-to-Close generally a few milliseconds. Error CONNECTION_REFUSED 0x2.

Changing transport error to PROTOCOL_VIOLATION 0xa did not solve request-level failure: accepted Close counts 104,119,131,4,56; all five requests HTTP3 200. Retrying is therefore not established as exclusive to CONNECTION_REFUSED. Previous commentary attributing retries specifically to that code was too narrow.

This proves prompt corrected Initial Closes can be accepted in this lab. It does not prove reliable policy enforcement: individual connection termination differs from preventing an entire request with retries. Debug logging affects timing; helper is a gateway-local diagnostic, not the full NPB path. Original method/environment reproduction and controlled timing sweep remain outstanding; no architecture-impossibility conclusion is warranted.

Evidence: evidence/state-aware-debug-20261107T010600Z and evidence/state-aware-errorcode-20261107T010753Z, including client.pcap, full per-request stderr in results.json, helper logs and COUNTS.json. Earlier buffered run retained at state-aware-debug-20261107T010402Z.
