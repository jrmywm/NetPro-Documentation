# Mirrored capture independence demo

Environment-specific, repeatable helpers for the Gateway and Client in the [demo procedure](../../docs/passive-capture-independence-demo.md). They check hostnames, MAC addresses, and expected static addresses; review them before any use. They do not change Policy data or restart Policy. Start/stop repeatability was verified without leftover demo state.

On the Gateway, run as root (`sudo bash gateway.sh start`), then use `status`, `down`, `up`, and finally `stop` for cleanup. `start` installs a narrowly scoped Client forwarding/NAT path, mirrors `ens37` ingress to `ens38`, drops all `ens38` ingress, and arms a 10-minute automatic cleanup timer. `stop` removes the demo filters/rules, restores the original IP-forwarding state, and leaves `ens38` down with promiscuous mode off. The script refuses to start if its required baseline state is absent.

On the Client, run `bash client.sh 142.251.152.119 PHASE` once per phase (`connected`, `disabled`, `reconnected`). It uses a temporary `/32` route via `192.168.80.28` on `ens37`, forces source `192.168.80.29`, disables proxies, and uses `--resolve` for a fresh `www.google.com` HTTPS request. A route created by the script is removed on exit. Confirm no conflicting route exists first.

The phases are one connected request, Gateway `down` plus one request, then Gateway `up` plus one request. Always run Gateway `stop` after the test. Record actual output; do not describe this software mirror as a hardware TAP or a Gateway-failure test.
