# Virtual TAP monitor-branch test helpers

These host-guarded helpers start/stop the temporary HTTP/TLS endpoints on the Gateway and issue requests from the Client. Review before use; the Gateway helper requires root. It creates temporary listeners with an automatic ten-minute stop, and its stop action removes only the named test units. The Client helper is pinned to the configured client hostname, NIC MAC/address, and test server. Do not repurpose it for other hosts or addresses without reviewing its guards.

The root-controlled test orchestration toggles only monitor NIC `ens36`; these Gateway/Client helpers do not toggle it. The run did not power off the TAP VM or modify bridge ports. Results do not prove hardware TAP fail-open behavior. The run's text evidence is in [`evidence/virtual-tap-live-test`](../../evidence/virtual-tap-live-test/); no PCAP was captured.
