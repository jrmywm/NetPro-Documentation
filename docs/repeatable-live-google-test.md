# Repeatable live Google block/allow validation

> Status: verified with the Policy source fix `6784d46`, ten blocked curl attempts, an isolated Edge check, and no-restart rollback to HTTP 200.

This runbook validates a real HTTPS browser destination through the live Tinyproxy → NPB → Policy path. It uses a temporary `www.google.com` policy pinned to the address resolved by the gateway, so it does not alter the Windows system proxy or default route. The gateway helpers mirror the proxy traffic and return Policy-generated TCP resets to Tinyproxy.

## Verified source behavior

Policy commit `6784d46`:

- activates the existing `ip_checker` before domain parsing;
- invalidates the IP cache when a blocked-list row is updated or deleted;
- guards the hit counter from overflow; and
- frees extracted domain strings.

The test still has an intentional limitation: a domain-only policy with a mismatched or stale IP can miss a segmented TLS ClientHello SNI. Full TCP/TLS reassembly remains future work. Pin the current resolved IPv4 address for this test and treat a miss with a stale address as inconclusive rather than as proof that enforcement failed.

## Prerequisites and helper installation

The existing `netpro-proxy-mirror-start`, `netpro-proxy-mirror-stop`, Tinyproxy configuration, and gateway VM network mappings must already be installed. The gateway uses `192.168.80.128:8888` for Tinyproxy.

From Windows, copy the supplied helpers to the gateway:

```powershell
scp .\scripts\repeatable-live-test\netpro-google-test-start netpro@192.168.80.128:/tmp/
scp .\scripts\repeatable-live-test\netpro-google-test-stop netpro@192.168.80.128:/tmp/
```

On the gateway:

```bash
sudo install -m 0755 /tmp/netpro-google-test-start /usr/local/sbin/netpro-google-test-start
sudo install -m 0755 /tmp/netpro-google-test-stop /usr/local/sbin/netpro-google-test-stop
```

The Windows harness is [Test-NetProGoogle.ps1](../scripts/repeatable-live-test/Test-NetProGoogle.ps1). It supports `Blocked`, `Allowed`, and `Browser` modes and creates a disposable Edge profile for the browser check.

## Start and verify the blocked test

On the gateway, resolve the address immediately before starting the test:

```bash
GOOGLE_IP=$(getent ahostsv4 www.google.com | awk '$2 == "STREAM" {print $1; exit}')
echo "$GOOGLE_IP"
sudo netpro-google-test-start "$GOOGLE_IP"
```

The helper records the previous reverse-path-filter and Tinyproxy state, adds a tagged `/etc/hosts` entry, starts Tinyproxy if necessary, sets `rp_filter=0`, and starts the mirror. It refuses malformed addresses or a duplicate active test.

On `policy-server-vm`, select TLS mode before creating the policy:

```bash
sudo systemctl stop netpro-policy
sudo netpro-policy-mode tls
sudo systemctl start netpro-policy
```

On `backend-vm`, create a disposable blocked-list row. Replace `GOOGLE_IP` with the address printed by the gateway and save the returned policy ID:

```bash
curl -k -sS -X POST https://127.0.0.1:3000/ps/blocked-list \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"Google live browser test",
    "domain":"www.google.com",
    "ip_add":"GOOGLE_IP",
    "category":"Other"
  }'
```

Confirm the row reaches Policy SQLite while Policy is running:

```bash
sudo sqlite3 /home/ubuntu/NetPro-Policy-Server/policy.db \
  "SELECT id, domain, ip_address FROM policies WHERE domain='www.google.com';"
```

From Windows, run ten proxied curl attempts and the isolated browser:

```powershell
.\scripts\repeatable-live-test\Test-NetProGoogle.ps1 -Mode Blocked -Attempts 10
.\scripts\repeatable-live-test\Test-NetProGoogle.ps1 -Mode Browser
```

Verified result: all 10/10 curl attempts were blocked with curl exit code `35`, and the fresh isolated Edge profile could not load Google. The exact error text can vary; the nonzero result and Policy/NPB evidence are the acceptance checks.

## Delete the policy and prove no-restart rollback

On `backend-vm`, delete the temporary row using the saved ID:

```bash
curl -k -sS -X DELETE \
  https://127.0.0.1:3000/ps/blocked-list/POLICY_ID
```

Confirm the row is absent from Policy SQLite. Without restarting Policy, run three allowed checks from Windows. The harness requires both curl exit code `0` and an HTTP `2xx` or `3xx` response:

```powershell
.\scripts\repeatable-live-test\Test-NetProGoogle.ps1 -Mode Allowed -Attempts 3
```

Verified result: Google returned HTTP 200 after deletion without a Policy restart. This demonstrates update/delete cache invalidation on the live Policy path.

Finally, stop the gateway test and restore the default HTTP mode:

```bash
sudo netpro-google-test-stop
```

```bash
sudo systemctl stop netpro-policy
sudo netpro-policy-mode http
sudo systemctl start netpro-policy
```

The stop helper removes only its tagged hosts entry and mirror state, restores the saved `rp_filter` and Tinyproxy state, and removes its runtime state file. If a run is interrupted, execute the stop helper before starting another test.

## Evidence and troubleshooting

- Record the resolved IP, policy ID, Policy mode/status, NPB classification, Policy RST counters, and the 10/10 curl exit codes.
- Resolve Google again for each new run; DNS answers can change and the Policy cache is IP-sensitive.
- If curl unexpectedly succeeds, first confirm the active Policy row contains the current resolved IP and that Policy is in TLS mode. A stale/mismatched IP or a segmented ClientHello can miss without implying that the cache fix failed.
- If the Edge check appears to use the normal browser session, verify that the harness created a new `--user-data-dir`; do not remove the user's normal profile.
- Keep generated profiles, logs, captures, certificates, policy IDs, and gateway runtime state out of this documentation repository.
