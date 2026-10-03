# Professor video demonstration guide — dashboard-first, 6–10 minutes

## Demonstration goal

Show current HTTP/TLS telemetry, how a viewer can inspect its time window and chart layout, and the bounded result of the passive mirror-branch test. This is a virtual-lab demonstration of telemetry and monitor-branch independence—not active blocking, a physical TAP, TAP-VM power-off tolerance, or a fail-open guarantee. Do not create or edit a Policy rule during the recording.

### Deployment precheck — required before filming

The repo includes the reviewed helpers but does not record their VM-side deployment directories. Before filming, from PowerShell at the workspace root, stage the Gateway and Client helper files into the documented demo directory. Authentication uses the configured SSH key or interactive login; do not put passwords in commands, shell history, or the recording.

```powershell
$helperDir = ".\NetPro-Documentation-current\scripts\virtual-tap-live-test"
ssh netpro@192.168.31.37 'mkdir -p ~/netpro-demo/virtual-tap-live-test'
ssh netpro@192.168.31.39 'mkdir -p ~/netpro-demo/virtual-tap-live-test'
scp "$helperDir\server.sh" "$helperDir\index.html" 'netpro@192.168.31.37:~/netpro-demo/virtual-tap-live-test/'
scp "$helperDir\client.sh" 'netpro@192.168.31.39:~/netpro-demo/virtual-tap-live-test/'
ssh netpro@192.168.31.37 'ls -l ~/netpro-demo/virtual-tap-live-test/server.sh ~/netpro-demo/virtual-tap-live-test/index.html'
ssh netpro@192.168.31.39 'ls -l ~/netpro-demo/virtual-tap-live-test/client.sh'
```

This is a pre-recording helper deployment, not part of the live demonstration. After transfer, confirm the files exist on the intended hosts and review them there. The Gateway helper requires root and sets a 10-minute runtime limit on its temporary HTTP/TLS listeners. The checked-in Client/Gateway helpers do not toggle `ens36`. The prior run used a separate root-controlled, host-guarded monitor toggle with automatic restoration, which is not included in this helper bundle. Locate and review that runner and verify its automatic restore before including the monitor-off phase. If unavailable, skip that phase—do not manually lower the monitor NIC or improvise a timer.

Also confirm the existing virtual TAP wiring, active mirror service, monitoring NIC restored/up, and the read-only dashboard pair IDs below. Stop if services are not in their recorded healthy state, a temporary listener/state already exists, or a conflicting test gateway helper is active.

| VM | Management IP | Demo role/address |
| --- | --- | --- |
| Policy Server | `192.168.31.31` | dashboard telemetry source |
| Kafka Broker | `192.168.31.32` | policy/telemetry service |
| NPB | `192.168.31.33` | packet classification and dashboard samples |
| Packet Generator | `192.168.31.34` | TRex stays stopped for this demo |
| Backend | `192.168.31.35` | API/database |
| Frontend | `192.168.31.36` | `https://192.168.31.36:3005` |
| Gateway | `192.168.31.37` | local demo server; lab link `192.168.80.28` |
| Virtual TAP | `192.168.31.38` | bridge/monitor; never power off during demo |
| Client | `192.168.31.39` | lab link `192.168.80.29` |

Dashboard URLs: [NPB](https://192.168.31.36:3005/dashboard/npb?id=79c57972-db3b-409e-b4e8-ab4ee526f666) and [Policy Server](https://192.168.31.36:3005/dashboard/ps?id=6f7e663a-dfae-4b31-9e4e-93bc64d3e0a1). These point to the verified paired device IDs.

Before the session, run read-only service checks on the respective hosts:

```bash
# Frontend VM (.36)
systemctl is-active netpro-frontend
# Backend VM (.35)
systemctl is-active netpro-backend postgresql
# NPB VM (.33)
systemctl is-active netpro-npb
# Policy VM (.31)
systemctl is-active netpro-policy
# Kafka VM (.32)
systemctl is-active netpro-kafka netpro-zookeeper
```

On the Gateway (`192.168.31.37`), run these read-only checks before starting the endpoints:

```bash
cat /proc/sys/net/ipv4/ip_forward
ip -br link show dev ens38
sudo ss -H -ltnp '( sport = :8080 or sport = :8443 )'
```

Expected: `ip_forward` is `0`, `ens38` is `DOWN`, and the listener query prints no matching line. The `server.sh` helper independently refuses an existing listener or test state. The read-only mirror-status command below verifies the TAP service separately. Stop if any state differs or if another listener/test helper is present.

Before recording, from the TAP VM, the read-only status helper is:

```bash
sudo /usr/local/libexec/netpro-virtual-tap/mirror.sh status
```

It should show `ens34` and `ens35` attached to `br-tap`, `ens36` up, mirror state active, and the ingress drop filter on `ens36`. The service remains the currently installed software mirror. Do not run setup, install, rollback, or stop actions as part of the video.

## Run of show (about 8 minutes)

| Time | Screen and action | Suggested narration / expected result |
| --- | --- | --- |
| 0:00–0:40 | Open the dashboard over HTTPS. State that this is a VM lab. | “This demo shows passive telemetry and a software mirror. It does not claim a hardware TAP or safe active blocking.” |
| 0:40–1:20 | Briefly show the topology/address table, then navigate to the paired NPB and Policy dashboards using the UI. | Identify Gateway `192.168.80.28`, Client `.29`, NPB `.33`, Policy `.31`, and the virtual TAP `.38`. Do not show credentials. |
| 1:20–2:40 | NPB dashboard: show current sample age and HTTP/HTTPS/RX charts. Select 15 minutes, pause, then Live. Change 2 columns to 1, hide a chart, expand/collapse one, then Reset. | Point out that counters are packets per telemetry sample, not rates. Live resumes sample updates; Reset restores all charts and default columns. |
| 2:40–3:40 | Policy dashboard: show the four reset/RX charts and the existing Blocked List table in read-only mode. Select a longer window if useful. | Explain that the table is not changed during this demo. Lifetime cards and selected-window charts are distinct. Reset charts may remain at zero because this safe demo creates no block match. |
| 3:40–4:20 | Capture the visible telemetry baseline (latest sample age/time and current chart values) before generating test requests. | If a baseline is already moving, note it rather than implying zero traffic. No database writes or policy updates. |
| 4:20–5:00 | On Gateway: `cd ~/netpro-demo/virtual-tap-live-test` then `sudo bash ./server.sh start`. | The identity-guarded helper checks host, NIC MAC/address, state, and listeners. Record its printed evidence directory. |
| 5:00–6:10 | On Client: `cd ~/netpro-demo/virtual-tap-live-test` then `bash ./client.sh on-before`. Return to the NPB/Policy dashboards and wait for fresh samples. | The helper sends two HTTP and two TLS requests to the lab Gateway per phase. Expected response: HTTP 200 for all four; NPB HTTP/TLS and RX charts should show activity after telemetry ingestion. Policy reset charts may stay zero because no Policy rule is changed or matched. |
| 6:10–7:10 | Optional only after the deployment precheck: the reviewed, timed monitor-toggle runner performs monitor-off and schedules automatic restore. Run `bash ./client.sh monitor-off` while the runner's brief off interval is active, then run `bash ./client.sh on-after` after it reports restoration. Keep the dashboard visible. | Expected for the previously verified bounded test: all requests succeeded on/off/on; no request-matched NPB row appeared during monitor-off, and matched samples returned after restore. If the timer runner is missing, skip this phase and state that only the existing historical result is shown. |
| 7:10–8:30 | Recheck Live status, sample ages and Blocked List; stop only the test listeners: `sudo bash ./server.sh stop` from the same verified Gateway helper directory. | Confirm the mirror service and `ens36` are restored/up. Show cleanup output and explain the test does not establish VM-power-off fail-open or active reset delivery. |

The local demo endpoints are `http://192.168.80.28:8080/` and `https://netpro-tap.test:8443/`; the Client helper pins the TLS name/address and uses the lab's temporary self-signed certificate. Do not use or film a production credential.

### Stop criteria

Stop the demonstration and do not continue to monitor-off if a host guard fails, the existing monitor restore timer cannot be verified, a pre-existing test state/listener is present, any request fails, the dashboard reports unexpected errors, the monitor does not restore, or counters show a reset burst. Stop the named listeners with the helper's guarded `stop` action. If the monitor does not restore, stop the demo and use the reviewed recovery procedure; do not manually alter it. Do not run `scripts/passive-demo/gateway.sh` at the same time as the local TAP test; do not start TRex, old tinyproxy/routed helpers, or any active RST injection.

If helper directories are not present on the VMs, this is a deployment-precheck failure. Do not copy helpers or change VM state during the recording; arrange and verify that deployment separately.

## Claims to avoid

- Do not describe monitor-NIC down as TAP-VM power-off tolerance or physical fail-open behavior.
- Do not present the failed shared-RX active-blocking test as successful; it had an escaped request and a probable reset feedback loop, without a usable PCAP.
- Successful custom-range form submission and mobile viewport layout have not been verified.
- The NPB and Policy dashboard UI checks are current; keep the video factual and avoid inferring loss-free capture from the charts.
