# Captured follow-up, 14 November 2026

45/45 allow-deny-allow probes passed using the persistent deployment and unchanged 15 ms delay. Three trials per phase covered Chromium forced HTTP/3, TCP/TLS and normal negotiation, plus HTTP/3/TLS curl. Temporary policies were removed and the baseline restored. No escape reproduced. Packet capture authenticated injected Close packets; timing-summary.json records client Initial-to-first-Close latency. These timings describe this passing run and do not explain the earlier uncaptured escape. No binaries or network settings changed.
