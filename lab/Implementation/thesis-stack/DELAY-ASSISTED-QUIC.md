# Delay-assisted QUIC experimental mode

This mode adds an artificial delay to genuine server UDP443 responses on gateway ens37, limited to server192.168.80.28/client192.168.80.29. Policy Server-injected Closes arriving through the dedicated return interface are marked39001 and exempted. The full Clientâ†’Virtual TAPâ†’NPBâ†’Policy Serverâ†’dedicated gateway return path is used. No gateway helper generates Closes in this experiment.

Run from Windows PowerShell (lab password supplied through NETPRO_LAB_PASSWORD):

```powershell
$env:NETPRO_QUIC_RESPONSE_DELAY_MS='15'
$env:NETPRO_QUIC_TRIALS='20'
python 'C:\Users\jim\Documents\NetPro\Implementation\thesis-stack\run-delay-assisted-validation.py'
```

Delay accepts1â€“50ms. The runner temporarily starts the recovered QUIC candidate and NPB candidate, installs only its owned test rule, records client/gateway captures and curl elapsed times, removes the rule, then restores service binaries and gateway qdisc. Rollback timer protects the temporary return/delay configuration. It currently restores the preflight-tested fq_codel parameters; it must stop if a different qdisc is present. This is a bounded validation runner, not an always-on deployment service. Lab target only; no general Internet-domain enforcement claim.

Initial results:5ms delay blocked1/5, allowed5/5 before rule and5/5 after deletion.10ms delay blocked5/5, allowed5/5 before rule and5/5 after deletion. At10ms median curl total was8.504ms on baseline and31.654ms on delayed candidate,32.657ms after policy removal. These are whole HTTP3 transfers, not one-way delay or isolated processing overhead. Artificial delay can affect multiple server flights. Candidate changes and scheduling also confound before/after timing.

The twenty-request-per-phase repeat is recorded separately when complete. All outcomes must be retained, including failures. Success means requests fail to complete within the five-second observation window; not a guarantee for indefinitely retrying clients, browsers, or a loaded system. This is an explicit extension to the passive-injection design and not unchanged thesis replication.

## Larger repeat

Full-path10ms repeat:19/20 requests stopped within5seconds;1/20 escaped. Allow-before20/20 and allow-after-delete20/20. Baseline3/3. Evidence:evidence/live-thesis-profile-20261107T024955Z. Mode remains an explicitly experimental bounded runner; normal HTTP/TLS services and gateway qdisc restored. No claim of reliable permanent enforcement.

Measured medians(ms):{"allow-original": {"trials": 3, "passed": 3, "median_total_ms": 9.213000000000001}, "allow-candidate": {"trials": 20, "passed": 20, "median_total_ms": 30.6325}, "deny-rule": {"trials": 20, "passed": 19, "median_total_ms": 5000.3745}, "allow-after-delete": {"trials": 20, "passed": 20, "median_total_ms": 31.881}}

Follow-up: at 10 ms, the only captured client Handshake in the deny phase (UDP port 43577) was sent 13.31 ms after its first observed client packet; injected Close reached the client at 14.86 ms. At 15 and 20 ms, each run passed 10/10 allow, 10/10 deny within five seconds, and 10/10 allow after rule removal. Allowed median: 41.98 ms at 15 ms; 51.62 ms at 20 ms. Evidence: live-thesis-profile-20261107T043700Z and live-thesis-profile-20261107T043902Z respectively. Both runs restored original NPB and Policy Server builds. Recommend 15 ms for further testing; concurrent and browser traffic not verified.

Default selected by user:15ms for the bounded experimental validation runner. This does not permanently enable QUIC or delay on the live system; each run restores the working HTTP/TLS baseline.

## Combined build and concurrent checks

At 15 ms, HTTP/3-only curl with up to five simultaneous requests passed 20/20 allowed, 20/20 denied within five seconds, and 20/20 allowed after policy removal. Evidence is live-thesis-profile-20261107T074419Z. The initial harness attempt hit a Windows file lock because parallel workers shared an evidence file. The runner now collects remote output in each worker and records results serially.

With NETPRO_COMBINED_REGRESSION=1, the runner first exercises CSV-driven TLS while both candidate binaries are active, then exercises delayed QUIC using the same binaries. The first combined run activated the CSV rule but a TLS request escaped on trial 16. The client capture shows server data at 3.402 ms and a reset at 7.039 ms after ClientHello. The reset sequence matches the start of the earlier server payload. Evidence is csv-packets-20261107T074628Z.

The repeat passed 80/80 CSV-driven TLS probes including segmented ClientHello and all 30 QUIC probes across allow, deny and removal with up to five simultaneous requests. The cache reported 80 lookups, valid filter, zero errors and zero shadow mismatches. Zabbix recorded 40 matching TLS domain events and 1,025 matching QUIC domain events during the combined run window. Evidence is csv-packets-20261107T074744Z and live-thesis-profile-20261107T074723Z.

The runs restored both original binaries. The TLS escape remains an acceptance failure for a persistent rollout. Browser and TCP fallback checks remain open. The lab client had no browser installed and concurrent curl forced HTTP/3.

## Persistent lab deployment

The final deployment is active and enabled in systemd on the Policy Server, NPB, and gateway. It passed 18 allow, deny, and allow probes before installation and 18 more after restarting the persistent services. Each pass exercised HTTP/3 only, TCP/TLS only, and curl with HTTP/3 and TCP fallback enabled. The exact test rule was removed and policy replay readiness and baseline IDs were checked. The actual client browser and VM reboot remain untested.

The NPB now recognizes ClientHello record versions 03 01 through 03 03. The captured Caddy TCP ClientHello used 03 03. The gateway applies 15 ms to genuine UDP and TCP responses from port 443 for the test server and client pair only. Injected QUIC Closes and TCP resets bypass the delay. The gateway returns TCP resets in both directions. Rafie reported a valid filter with zero lookup errors or shadow mismatches. Zabbix recorded 2,983 matching domain events since deployment testing began.

Deployment evidence: evidence/persistent-prototype-20261107T080925Z/deployment.json. Earlier runs retain the TCP classification failure, missing broker install directory, early policy replay check, and stale test-rule deletion flag. The final run corrected these and validated rule removal after restart.

To roll back the deployment, stop and disable netpro-quic-lab.service on the gateway. On the NPB, run `sudo bash /home/netpro/incoming/thesis-rollout.RozK5s/rollback.sh`. On the Policy Server, run `sudo bash /home/netpro/incoming/thesis-rollout.0sKTGx/rollback.sh`. The scripts check the deployed override and original binary identity. Gateway rollback restores fq_codel. The existing standalone TCP/8443 test return helper shares ens38 and requires the gateway lab service to be stopped before that helper can be used.
