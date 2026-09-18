# NetPro End-to-End HTTP and TLS Validation

> Result: HTTP and TLS policy enforcement verified on 15 September 2026 from TRex through the NPB and Policy Server, including TCP-reset delivery back to TRex.

This procedure uses the verified local Policy telemetry fix `d658fa2` plus VM-local services. The Policy runtime accepts exactly two DPDK ports: the selected input and the RST/output port. HTTP and TLS are therefore validated as separate selectable modes by changing which input adapter is bound to DPDK. The second DPDK port remains the RST output in both modes.

## Verified topology

```text
Packet-Generator-VM
  TRex port 0 (0000:03:00.0)
        | NetPro-RX
        v
NPB-VM
  port 0 RX   (0000:0b:00.0)
  port 1 HTTP (0000:13:00.0) -> NetPro-HTTP
  port 2 TLS  (0000:1b:00.0) -> NetPro-TLS

Policy-Server-VM
  HTTP input  (0000:0b:00.0) -> NetPro-HTTP
  TLS input   (0000:13:00.0) -> NetPro-TLS
  RST output  (0000:1b:00.0) -> NetPro-RX
```

The same PCI address can appear in different VMs because PCI addresses are local to each VM.

## Policy Server modes

Only change bindings while the Policy Server is stopped. The systemd service must be stopped, not just a child process, because it restarts on failure.

If the verified local helper from the Policy Server setup guide is installed, use:

```bash
sudo netpro-policy-mode http
sudo netpro-policy-mode tls
sudo netpro-policy-mode status
```

The detailed commands below are the manual equivalent and remain useful for recovery.

### HTTP mode

```bash
sudo dpdk-devbind.py -b vmxnet3 0000:13:00.0
sudo ip link set ens224 down
sudo ip link set ens192 down
sudo dpdk-devbind.py -b uio_pci_generic 0000:0b:00.0
sudo dpdk-devbind.py -b uio_pci_generic 0000:1b:00.0
sudo dpdk-devbind.py -s
```

Expected DPDK devices: `0000:0b:00.0` followed by `0000:1b:00.0`.

### TLS mode

```bash
sudo dpdk-devbind.py -b vmxnet3 0000:0b:00.0
sudo ip link set ens192 down
sudo ip link set ens224 down
sudo dpdk-devbind.py -b uio_pci_generic 0000:13:00.0
sudo dpdk-devbind.py -b uio_pci_generic 0000:1b:00.0
sudo dpdk-devbind.py -s
```

Expected DPDK devices: `0000:13:00.0` followed by `0000:1b:00.0`.

In both modes, DPDK enumerates the selected classifier input as application port 0 and the RST adapter as application port 1.

## Startup order

1. Start ZooKeeper and Kafka and confirm ports 2181 and 9092.
2. Start the Backend/PostgreSQL and Frontend if dashboard/database telemetry is in scope.
3. Start the Policy Server in the desired HTTP or TLS mode; boot-safe HTTP is the default.
4. Start the NPB with all three data adapters bound to DPDK.
5. Start TRex with `/usr/local/sbin/netpro-trex-start` and confirm its RPC listeners on 4500/4501.
6. Run the matching repository traffic-generator script.

### Kafka checks

```bash
systemctl is-active netpro-zookeeper
systemctl is-active netpro-kafka
sudo ss -ltnp | grep -E ':(2181|9092)'
```

### Policy Server

```bash
sudo systemctl is-active netpro-dpdk-prepare
sudo systemctl is-active netpro-policy
sudo netpro-policy-mode status
sudo dpdk-hugepages.py -s
sudo dpdk-devbind.py -s
```

### NPB

```bash
sudo dpdk-hugepages.py -s
sudo dpdk-devbind.py -s
cd ~/NetPro-Network-Packet-Broker
sudo ./build/packetBroker -l 0-3 -n 2
```

### TRex server

```bash
sudo /usr/local/sbin/netpro-trex-start
```

The helper runs TRex in the foreground with `/etc/trex_cfg.yaml`; keep that terminal open. A generator RPC error when ports 4500/4501 are not listening means TRex is not running yet, not that the HTTPS PCAP is malformed.

## HTTP enforcement test

The repository HTTP profile sends traffic to `48.0.0.1` with the HTTP host `facebook.co.id`. With the Policy Server running, publish this policy to `dpdk-blocked-list`:

```json
{"type":"create","createdBlockedList":{"domain":"facebook.co.id","ip_add":"48.0.0.1","id":"netpro-http-facebook-001"}}
```

Verify the policy:

```bash
sudo sqlite3 /home/ubuntu/NetPro-Policy-Server/policy.db \
"SELECT id, domain, ip_address FROM policies WHERE id='netpro-http-facebook-001';"
```

Run the generator in a second Packet Generator terminal:

```bash
source ~/.profile
cd /opt/trex/v3.04/automation/trex_control_plane/interactive/trex/npb_test/npb
python3 npb_testing_http.py \
  --sizes 256 \
  --pps_values 1000 2000 1000
```

Verified evidence included approximately 1,000 HTTP matches per active interval, 1,000 blocked requests, 1,000 client RSTs, 1,000 server RSTs, and 2,000 Policy Server transmissions. TRex port 0 transmitted 8,019 packets and received 8,019 return packets with zero interface errors. TRex port 1 remained unused, as required by the repository script.

## TLS enforcement test

The repository's `npb_testing_https.py` always loads `pcap/https_583B_single.pcap`. Inspection of that capture established:

- TLS SNI: `www.ui.ac.id`
- destination IP: `152.118.24.175`
- destination TCP port: 443
- captured frame size: 583 bytes

With the Policy Server running in TLS mode, publish this policy:

```json
{"type":"create","createdBlockedList":{"domain":"www.ui.ac.id","ip_add":"152.118.24.175","id":"netpro-tls-ui-001"}}
```

Verify the policy:

```bash
sudo sqlite3 /home/ubuntu/NetPro-Policy-Server/policy.db \
"SELECT id, domain, ip_address FROM policies WHERE id='netpro-tls-ui-001';"
```

Run the repository test:

```bash
source ~/.profile
cd /opt/trex/v3.04/automation/trex_control_plane/interactive/trex/npb_test/npb
python3 npb_testing_https.py \
  --sizes 583 \
  --pps_values 1000 2000 1000
```

The script uses Python `range(start, stop, step)`, so these arguments run one 1,000-pps job for approximately eight seconds. The `--sizes` value is stored as result metadata; the packet bytes still come from the fixed 583-byte capture.

## Telemetry and PostgreSQL verification

Backend direct sender field names match the database schema: `rstClient`, `rstServer`, `rx_i_http_*`, `rx_i_tls_*`, `rx_o_*`, and `tx_o_*`. Before a traffic run, record a packet-row baseline because telemetry is sent once per minute:

```bash
baseline=$(PGPASSWORD=postgres psql -h 127.0.0.1 -U postgres -d test -Atc \
  'SELECT COALESCE(MAX(packet_id),0) FROM ps_packet;')
echo "baseline packet_id=${baseline}"
```

Wait at least 70 seconds after the generator run (telemetry is sent once per minute), then query only rows newer than that baseline (use the actual table/column names shown by `\dt`/`\d ps_packet` if a checkout differs):

```bash
sleep 70
```

```bash
PGPASSWORD=postgres psql -h 127.0.0.1 -U postgres -d test \
  -c "SELECT packet_id, \"rstClient\", \"rstServer\", rx_i_http_count, rx_i_tls_count, rx_o_count, tx_o_count FROM ps_packet WHERE packet_id > ${baseline} ORDER BY packet_id;"
```

HTTP evidence should show `rx_i_http_count` about 1,000, `rx_i_tls_count` 0, RST client/server about 1,000 each, output RX/TX about 1,000/2,000, output drop about 1,000, HTTP/output throughput nonzero, and TLS throughput 0. TLS evidence is symmetric: HTTP zero, TLS input about 1,000, RST about 1,000 each, output RX/TX about 1,000/2,000, TLS throughput about `587000`, and output throughput about `108000`. One- or two-packet differences are sampling-boundary effects.

## Verified TLS evidence

- NPB: up to 1,000 `TLS CLIENT HELLO match` packets per active reporting interval, forwarded through TLS output port 2.
- Policy Server: 1,000 received and blocked TLS packets, approximately 1,000 client RSTs plus 1,000 server RSTs, and 2,000 transmitted packets per active interval.
- TRex port 0: 8,016 transmitted packets and 16,032 received packets.
- NPB, Policy Server, and TRex: zero reported RX/TX interface errors.

The 2:1 receive/transmit ratio at TRex is expected in this lab topology: the Policy Server emits two RST frames for each blocked request and its RST adapter shares `NetPro-RX`; TRex port 0 is in promiscuous mode and observes both.

Counters returning to zero after the run represent idle one-second intervals, not failure. Use the nonzero active intervals and final cumulative TRex counters as evidence.

The post-reboot repeat on 17 September 2026 produced the same behavior: NPB matched and forwarded 1,004 TLS Client Hello packets through port 2, Policy produced stable 1,000-request intervals with 2,000 RST transmissions, and TRex finished with 8,017 transmitted packets and 16,034 received frames. All three components again reported zero interface errors.

## Full blocked-list CRUD propagation

Create, update, and delete were each verified through Backend → PostgreSQL → Kafka → Policy SQLite. For each operation, query PostgreSQL and the live Policy database while the Policy service is running, then confirm the corresponding Kafka event. The Backend update response displayed an odd `updatedAt:{val:"CURRENT_TIMESTAMP"}` object even though PostgreSQL stored the correct timestamp; treat that as a response-format issue, not a persistence failure.

## What is proven

- TRex can transmit the repository's HTTP and TLS profiles.
- The NPB receives, classifies, and forwards HTTP GET and TLS Client Hello traffic through the correct LAN segments.
- Kafka policies reach the Policy Server's SQLite database for create/update/delete operations.
- The Policy Server matches both repository profiles, blocks them, and emits both TCP RST directions.
- RST frames return to TRex through `NetPro-RX`.

## Current source limitation

The Policy process uses the selected DPDK application port 0 for input and application port 1 for RST transmission. It does not consume both HTTP and TLS inputs simultaneously; switch modes between runs. The local telemetry fix maps the selected input to the correct HTTP/TLS fields and does not change this selectable-mode limitation.

## Screenshot checklist

1. VMware LAN-segment mappings for Packet Generator, NPB, and Policy Server.
2. NPB `dpdk-devbind.py -s` showing three data adapters.
3. Policy Server bindings in HTTP mode and TLS mode.
4. Kafka/SQLite rows for the HTTP and TLS policies.
5. NPB HTTP and TLS classification counters.
6. Policy Server receive, drop, and client/server RST counters.
7. TRex cumulative `opackets`, `ipackets`, `ierrors`, and `oerrors`.
