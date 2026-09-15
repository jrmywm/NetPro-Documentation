# NetPro End-to-End HTTP Validation

> Result: verified on 15 September 2026 from TRex through the NPB to the Policy Server.

This procedure validates packet delivery and HTTP classification without changing any component repository. It does not yet claim that blocked-policy matching or TCP-reset enforcement works.

## Validated path

```text
Packet-Generator-VM
  TRex port 0 (0000:03:00.0)
        │ NetPro-RX
        ▼
NPB-VM
  port 0 RX (0000:0b:00.0)
  HTTP GET classification
  port 1 TX (0000:13:00.0)
        │ NetPro-HTTP
        ▼
Policy-Server-VM
  port 0 HTTP RX (0000:0b:00.0)
```

The same PCI address can appear in different VMs; each address is local to that VM.

## Startup order

### 1. Kafka Broker

```bash
systemctl is-active netpro-zookeeper
systemctl is-active netpro-kafka
sudo ss -ltnp | grep -E ':(2181|9092)'
```

Both services should report `active`. Kafka is not required to physically forward these test packets, but the current Policy Server initializes its Kafka consumer, so keeping it available avoids unrelated startup errors.

### 2. Policy Server

```bash
systemctl is-active netpro-dpdk-prepare
sudo dpdk-hugepages.py -s
sudo dpdk-devbind.py -s

cd ~/NetPro-Policy-Server
sudo ./build/policyServer -l 0-3 -n 2
```

Expected DPDK devices: `0000:0b:00.0` and `0000:13:00.0`.

### 3. NPB

```bash
sudo dpdk-hugepages.py -s
sudo dpdk-devbind.py -s

cd ~/NetPro-Network-Packet-Broker
sudo ./build/packetBroker -l 0-3 -n 2
```

Expected DPDK devices: `0000:0b:00.0`, `0000:13:00.0`, and `0000:1b:00.0`.

### 4. TRex server

```bash
cd /opt/trex/v3.04
sudo ./t-rex-64 -i
```

### 5. Repository HTTP test

In a second Packet Generator terminal:

```bash
source ~/.profile
cd /opt/trex/v3.04/automation/trex_control_plane/interactive/trex/npb_test/npb
python3 npb_testing_http.py \
  --sizes 256 \
  --pps_values 1000 2000 1000
```

## Observed evidence

### TRex

- Traffic transmitted on port 0.
- Port 1 remained idle for the HTTP-only test.
- One run reported 8,012 output packets and 2,051,072 output bytes.

### NPB

- Port 0 received the generated traffic.
- `HTTP GET match` increased with the receive count.
- Port 1 transmitted the classified HTTP packets.
- Port 2 remained idle.
- Drops, RX errors, TX errors, and mbuf errors remained zero.

### Policy Server

Successive reporting intervals showed:

```text
Packets received count: 984, then 997, then 999
Packets received size:  251904, 255232, 255744
Packets dropped:        0
Packet errors rx:       0
Packet errors tx:       0
```

Policy Server port 1 remained zero, which is correct for an HTTP-only test.

## What this proves

- VMware `NetPro-RX` and `NetPro-HTTP` LAN segment assignments are correct.
- The relevant VMXNET3 adapters and DPDK bindings work.
- TRex can transmit the repository's HTTP profile.
- The NPB can receive, classify, and forward HTTP GET traffic.
- The Policy Server can receive that forwarded traffic on its HTTP port.

## What this does not yet prove

- That the generated host/domain matches a row in the Policy Server SQLite database.
- That the Policy Server drops a blocked flow.
- That TCP reset packets are generated and reach the intended endpoints.
- That TLS Client Hello classification works through `NetPro-TLS`.
- That the full mixed workload or high-rate benchmark is stable.

## Screenshot checklist

Capture these as evidence without exposing passwords or secrets:

1. VMware LAN segment mapping for the Packet Generator, NPB, and Policy Server.
2. `dpdk-devbind.py -s` on the NPB and Policy Server.
3. TRex port statistics showing output packets on port 0.
4. NPB statistics showing port 0 RX, HTTP GET matches, and port 1 TX.
5. Policy Server statistics showing approximately 1,000 packets received on port 0 with zero errors.

