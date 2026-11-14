# Chromium QUIC persistent deployment â€” 14 November 2026

## Change

The QUIC path previously rejected zero-length client source connection IDs in the NPB and reply builder. It also expected a ClientHello in one Initial packet. Chromium supplies a zero-length source CID and can split the CRYPTO stream across Initial packets. The candidate accepts zero-length SCIDs and authenticates/reassembles bounded IPv4/QUIC-v1 ClientHello data before domain lookup. It retains the existing HTTP/TLS path, Rafie policy lookup and monitoring integration.

The reassembly table has 128 slots, a 4096-byte ClientHello limit, a 3-second idle timeout and per-thread state. Duplicate data must agree; malformed or unauthenticated data does not produce a domain match. This does not extend support to every QUIC version, ECH or arbitrary IP fragmentation.

## Installed artifacts

- Policy Server candidate SHA-256: `132c7650d01400a6726a359c06994963b8636893930d417e394cc86028016f1d`.
- NPB candidate SHA-256: `977736f0989f396a9401c8fe3e487271bf1f978dc778c10b1d88e590b9bae46f`.
- Candidate executables: `/usr/local/libexec/netpro-policy-browser-quic` and `/usr/local/libexec/netpro-npb-browser-quic`.
- Persistent overrides: `96-browser-quic.conf` beneath the respective `/etc/systemd/system/<unit>.service.d/` directories.
- Prior `95-combined-prototype.conf` overrides and binaries are retained.

`deploy-browser-persistent.py install` verifies the running old build and candidate hashes, backs up the policy database online, installs overrides and arms boot-enabled 20-minute rollback timers. Acceptance verifies both running hashes before disarming the timers. Rollback removes only a hash-matching owned override and restarts the previous build; it restores the database backup only if the database is absent.

## Test method

`test-persistent-browser.py` runs allowâ€“denyâ€“allow against `mysite.local` at `192.168.80.28:443`. Each trial uses a fresh Chromium profile and tests forced HTTP/3, forced TCP/TLS and normal negotiation, plus forced HTTP/3 and TLS curl. Successful allow requires the expected page or HTTP 200 with the expected curl protocol version. Browser deny requires no page content and a peer-close/reset event in target-specific NetLog records. A timeout alone is not enough to classify browser blocking.

`NETPRO_BROWSER_REPEATS` sets 1â€“10 trials per phase; 2 yields 30 total probes. `NETPRO_BROWSER_SCREENSHOTS=1` captures actual Chromium pages through CDP. `NETPRO_BROWSER_CAPTURE=1` captures the lab-only client interface traffic. Raw captures/NetLogs remain local.

The first repeated candidate run returned **29/30**: both Chromium HTTP/3 deny probes blocked, but one curl HTTP/3 deny probe loaded the page. No packet capture was collected for that escaped request, so its precise cause is unconfirmed. It is retained as a failed trial, not omitted from the results. A subsequent captured run passed **30/30**. The known timing dependence of injected close packets remains relevant; passing a later run does not erase that escape.

## Conditions

The scoped gateway delay remains **15 ms**, unchanged. No inline gate, UDP drop rule, proxy block, client retry suppression or certificate verification bypass for unrelated sites was added. Chromium trusts only the lab certificate public-key pin. This is bounded lab validation, not a guarantee of blocking on a delay-free physical network.

## Restart verification

All six VMs were gracefully rebooted. Changed Linux boot IDs were recorded for Management, Policy Server, NPB, Gateway, Virtual TAP and Client. New Policy Server/NPB executables were verified by SHA-256 after reboot.

Post-reboot browser/curl acceptance passed **30/30** with two trials per phase. A separate curl suite passed **18/18**, covering forced HTTP/3, TLS and fallback-enabled curl. Temporary rules were deleted and the original policy baseline was restored after each suite. Cache synchronization/filter health and management services passed; fresh blocked-domain events reached Zabbix.

The promotion is accepted and both automatic rollback timers are disabled. The 96-browser-quic.conf overrides remain installed and enabled application services start the new binaries at boot. Previous builds remain available for explicit rollback.

Evidence directories:

- First candidate repeat: `evidence/browser-persistent-20261114T095402Z` — 29/30.
- Captured candidate repeat: `evidence/browser-persistent-20261114T095651Z` — 30/30.
- Accepted deployment: `evidence/browser-deployment-20261114T095842Z/deployment.json`.
- Post-reboot browser: `evidence/browser-persistent-20261114T100144Z` — 30/30, with actual browser screenshots.
- Reboot IDs and 18 curl probes: `Testing/startup-check-20261114/` (the evidence bundle preserves these post-deployment snapshots separately).

## Commands after deployment

Run from the thesis-stack directory with NETPRO_LAB_PASSWORD set for your lab account. Unset NETPRO_BROWSER_BUILD to test the installed binaries. Set NETPRO_BROWSER_REPEATS=2 and NETPRO_BROWSER_SCREENSHOTS=1, then run `python test-persistent-browser.py`. This creates and removes its own temporary policy through the Backend API; its baseline guards refuse conflicting pre-existing policies.

For explicit rollback use `python deploy-browser-persistent.py rollback <deployment.json>` with the accepted deployment manifest above. Run subsequent tests against the restored old build with the expectation that Chromium forced HTTP/3 remains unsupported there. Do not rerun the original installer over an accepted deployment; it intentionally refuses existing candidate overrides.
