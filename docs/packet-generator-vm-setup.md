# NetPro Packet Generator VM Setup

> Status: TRex v3.04, VMware/DPDK ports, repository HTTP/TLS scripts, enforcement, and RST return verified.

This guide records the Packet Generator VM built from the `Network-Laboratory-UI/NetPro-Packet-Generator` repository. The repository is kept unchanged. TRex configuration, Python path settings, and VMware details are local to the VM.

## Verified result

- Ubuntu 20.04, four logical cores, and approximately 6 GB RAM.
- Two VMXNET3 data adapters detected by TRex.
- TRex v3.04 starts successfully in interactive/stateless mode.
- The repository's `npb_testing_http.py` loads successfully.
- TRex transmitted the 256-byte HTTP test through `NetPro-RX`.
- The NPB received, classified, and forwarded the traffic to the Policy Server.
- TRex transmitted the repository's 583-byte TLS capture and received both Policy Server RST directions.

## VMware hardware and topology

| Setting | Value |
| --- | --- |
| VM name | `Packet-Generator-VM` |
| Hostname | `packet-generator-vm` |
| Username | `netpro` |
| Guest OS | Ubuntu 20.04 |
| CPU | 4 virtual cores |
| Memory | 6 GB |
| Disk | 20 GB |
| Network Adapter | NAT; management and SSH; E1000 |
| Network Adapter 2 | `NetPro-RX`; VMXNET3; TRex port 0 |
| Network Adapter 3 | `NetPro-PG-AUX`; VMXNET3; TRex port 1 |

The verified PCI mapping is:

```text
Management: ens33  -> 0000:02:01.0 -> e1000
TRex port 0: ens160 -> 0000:03:00.0 -> vmxnet3
TRex port 1: ens192 -> 0000:0b:00.0 -> vmxnet3
```

All adapters must have **Connect at power on** enabled. `NetPro-RX` must match the NPB's input LAN segment. The auxiliary segment prevents the second TRex port from being attached accidentally to the HTTP or TLS output networks.

## Management address

The verified management interface has DHCP for VMware NAT plus `192.168.0.93/24` as its stable NetPro control address. Verify connectivity before continuing:

```bash
ip -br addr show ens33
ping -c 2 192.168.0.90
ping -c 2 192.168.0.91
ping -c 2 192.168.0.92
```

## Install basic tools

```bash
sudo apt update
sudo apt install -y git wget ca-certificates python3
sudo update-ca-certificates
```

If `apt` reports a package-manager lock held by `unattended-upgr`, wait for the automatic update to finish. Do not delete the lock file.

## Install TRex v3.04

```bash
sudo mkdir -p /opt/trex
sudo chown netpro:netpro /opt/trex
cd /opt/trex
wget -O v3.04.tar.gz https://trex-tgn.cisco.com/trex/release/v3.04.tar.gz
tar -xzf v3.04.tar.gz
cd /opt/trex/v3.04
```

If certificate verification fails, first check the VM date and refresh `ca-certificates`. `wget --no-check-certificate` bypasses server identity verification and should be a last-resort lab workaround only. If it is used, verify that extraction produces the expected TRex files before running anything:

```bash
ls -lh /opt/trex/v3.04/t-rex-64 \
  /opt/trex/v3.04/dpdk_setup_ports.py
```

## Configure TRex ports

Inspect the available adapters:

```bash
cd /opt/trex/v3.04
sudo ./dpdk_setup_ports.py -s
```

The NPB input adapter's verified MAC address is `00:0c:29:ba:d7:5a`. Configure both required TRex ports with an explicit destination MAC:

```bash
sudo ./dpdk_setup_ports.py \
  -c 03:00.0 0b:00.0 \
  --dest-macs 00:0c:29:ba:d7:5a 00:0c:29:ba:d7:5a \
  -o /etc/trex_cfg.yaml

sudo cat /etc/trex_cfg.yaml
```

The generated configuration should contain the two PCI addresses, their source MAC addresses, and the NPB destination MAC. The MAC address is VM-specific: if VMware regenerates the NPB NIC or the VM is copied instead of moved, discover the new NPB RX MAC and regenerate this file.

## Install the Packet Generator repository in TRex

For this TRex distribution, the actual interactive client path is:

```text
/opt/trex/v3.04/automation/trex_control_plane/interactive/trex
```

Clone the repository there:

```bash
cd /opt/trex/v3.04/automation/trex_control_plane/interactive/trex
git clone https://github.com/Network-Laboratory-UI/NetPro-Packet-Generator.git npb_test
cd npb_test/npb
```

TRex v3.04's packaged directory layout differs from the path expected by the repository's `stl_path.py`. The verified local compatibility links are:

```bash
ln -s ../stl /opt/trex/v3.04/automation/stl
ln -s ../external_libs /opt/trex/v3.04/automation/external_libs
```

Set the client import path:

```bash
export PYTHONPATH=/opt/trex/v3.04/automation/trex_control_plane/interactive:$PYTHONPATH
```

Add the same export to `~/.profile` if it must survive login, then load it with `source ~/.profile`.

Verify the repository script without sending traffic:

```bash
cd /opt/trex/v3.04/automation/trex_control_plane/interactive/trex/npb_test/npb
python3 npb_testing_http.py --help
```

## Start TRex and run the verified HTTP test

Terminal 1:

```bash
cd /opt/trex/v3.04
sudo ./t-rex-64 -i
```

Wait until TRex reports that its ports are ready. Terminal 2:

```bash
source ~/.profile
cd /opt/trex/v3.04/automation/trex_control_plane/interactive/trex/npb_test/npb
python3 npb_testing_http.py \
  --sizes 256 \
  --pps_values 1000 2000 1000
```

During the successful test, TRex port 0 transmitted packets while port 1 remained idle. An earlier run reported 8,012 transmitted packets and 2,051,072 bytes. The exact totals depend on test timing.

## Run the verified TLS test

Keep TRex running in terminal 1. In terminal 2:

```bash
source ~/.profile
cd /opt/trex/v3.04/automation/trex_control_plane/interactive/trex/npb_test/npb
python3 npb_testing_https.py \
  --sizes 583 \
  --pps_values 1000 2000 1000
```

The script transmits only from TRex port 0 and loads the fixed capture `pcap/https_583B_single.pcap`. That capture contains TLS SNI `www.ui.ac.id` for `152.118.24.175:443`. The verified run produced:

```text
port 0 opackets:  8016
port 0 ipackets: 16032
port 0 ierrors:      0
port 0 oerrors:      0
```

The two received frames per transmitted request are the client- and server-directed RST frames emitted by the Policy Server onto the shared `NetPro-RX` segment. Port 1 remains unused by both the repository HTTP and HTTPS scripts.

## Troubleshooting

### `Port 0 dest MAC is invalid`

TRex does not know where to send the frame. Regenerate `/etc/trex_cfg.yaml` with `--dest-macs` using the NPB's actual RX adapter MAC.

### `Could not determine STL profiles path`

Confirm the two compatibility links and `PYTHONPATH` shown above. Do not modify the repository just to fix the installed TRex directory layout.

### `ModuleNotFoundError: No module named 'scapy'` mentions local `http.py`

This can be a secondary error caused by Python importing the repository's `http.py` while handling the original path failure. Fix `stl_path.py` resolution first and retest with `--help`.

### TRex transmits but the NPB reports zero packets

Check, in order:

1. Packet Generator adapter 2 and NPB adapter 2 both use `NetPro-RX`.
2. Both adapters are connected in VMware.
3. `/etc/trex_cfg.yaml` uses the current NPB RX MAC.
4. NPB PCI `0000:0b:00.0` is bound to `uio_pci_generic`.
5. The NPB process was started before the test.

## Remaining validation

- Run the mixed HTTP/HTTPS/UDP cases in `runner.sh` after accounting for the Policy Server's single-input limitation.
- Decide which generated JSON, PCAPs, and screenshots should be retained outside Git as test evidence.
