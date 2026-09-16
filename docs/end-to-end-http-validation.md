# NetPro End-to-End HTTP and TLS Validation

> Result: HTTP and TLS policy enforcement verified on 15 September 2026 from TRex through the NPB and Policy Server, including TCP-reset delivery back to TRex.

This procedure uses the component repositories unchanged. Because the current Policy Server source reads only DPDK port 0 and requires exactly two DPDK ports, HTTP and TLS are validated as separate modes by changing which Policy Server input adapter is bound to DPDK. The second DPDK port remains the RST output in both modes.

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

Only change bindings while the Policy Server is stopped.

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
2. Start the Policy Server in the desired HTTP or TLS mode.
3. Start the NPB with all three data adapters bound to DPDK.
4. Start the TRex server.
5. Run the matching repository traffic-generator script.

### Kafka checks

```bash
systemctl is-active netpro-zookeeper
systemctl is-active netpro-kafka
sudo ss -ltnp | grep -E ':(2181|9092)'
```

### Policy Server

```bash
sudo dpdk-hugepages.py -s
sudo dpdk-devbind.py -s
cd ~/NetPro-Policy-Server
sudo ./build/policyServer -l 0-3 -n 2
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
cd /opt/trex/v3.04
sudo ./t-rex-64 -i
```

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

## Verified TLS evidence

- NPB: up to 1,000 `TLS CLIENT HELLO match` packets per active reporting interval, forwarded through TLS output port 2.
- Policy Server: 1,000 received and blocked TLS packets, approximately 1,000 client RSTs plus 1,000 server RSTs, and 2,000 transmitted packets per active interval.
- TRex port 0: 8,016 transmitted packets and 16,032 received packets.
- NPB, Policy Server, and TRex: zero reported RX/TX interface errors.

The 2:1 receive/transmit ratio at TRex is expected in this lab topology: the Policy Server emits two RST frames for each blocked request and its RST adapter shares `NetPro-RX`; TRex port 0 is in promiscuous mode and observes both.

Counters returning to zero after the run represent idle one-second intervals, not failure. Use the nonzero active intervals and final cumulative TRex counters as evidence.

## What is proven

- TRex can transmit the repository's HTTP and TLS profiles.
- The NPB receives, classifies, and forwards HTTP GET and TLS Client Hello traffic through the correct LAN segments.
- Kafka policies reach the Policy Server's SQLite database.
- The Policy Server matches both repository profiles, blocks them, and emits both TCP RST directions.
- RST frames return to TRex through `NetPro-RX`.

## Current source limitation

The unmodified Policy Server does not process HTTP and TLS inputs simultaneously. It polls only DPDK application port 0 while application port 1 is used for RST transmission. Testing therefore requires switching its DPDK input between the HTTP and TLS adapters. Supporting both inputs concurrently requires a deliberate Policy Server source change and a separate review.

## Screenshot checklist

1. VMware LAN-segment mappings for Packet Generator, NPB, and Policy Server.
2. NPB `dpdk-devbind.py -s` showing three data adapters.
3. Policy Server bindings in HTTP mode and TLS mode.
4. Kafka/SQLite rows for the HTTP and TLS policies.
5. NPB HTTP and TLS classification counters.
6. Policy Server receive, drop, and client/server RST counters.
7. TRex cumulative `opackets`, `ipackets`, `ierrors`, and `oerrors`.
