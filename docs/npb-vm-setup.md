# NetPro NPB VM Setup

> Status: installation, three-port DPDK startup, HTTP/TLS classification, forwarding, enforcement-path delivery, automatic startup, and reboot persistence verified.

The `NetPro-Network-Packet-Broker` repository is the baseline. It receives traffic on one DPDK port, filters for HTTP GET and TLS Client Hello traffic using Hyperscan, and sends the two traffic classes through separate DPDK output ports.

## Repository requirements and inconsistencies

The repository README specifies:

- Ubuntu 20.04;
- DPDK 20.11.2;
- Hyperscan 5.4.2; and
- four NICs: one management, one RX, and two TX.

The detailed DPDK guide downloads DPDK 22.11.2, conflicting with the README. The Policy Server has already been verified with 22.11.2, so this guide plans to test the NPB with 22.11.2 first.

`startup.sh` hard-codes PCI addresses `00:13.0`, `00:14.0`, and `00:15.0`. Do not run it unchanged; discover and record the actual PCI addresses first.

`run.sh` launches:

```bash
./build/packetBroker -l 0-2 -n 4
```

The current source requires at least three DPDK ports and at least three logical cores. Its “number of ports must be even” error text is incorrect.

## Verified result

The NPB successfully:

- built on Ubuntu 20.04 against DPDK 22.11.2 and Hyperscan 5.4.2;
- initialized three VMXNET3 data adapters using `uio_pci_generic`;
- received TRex HTTP traffic on DPDK port 0;
- classified the traffic as HTTP GET; and
- forwarded it through DPDK port 1 with zero reported packet drops or errors;
- classified the repository TLS Client Hello capture; and
- forwarded TLS traffic through DPDK port 2 to the Policy Server.

## VMware hardware

| Setting | Value |
| --- | --- |
| VM name | `NPB-VM` |
| Hostname | `npb-vm` |
| Username | `netpro` |
| Guest OS | Ubuntu 20.04 |
| CPU | 4 virtual cores |
| Memory | 6 GB |
| Disk | 30 GB |

## Adapter order and LAN segments

| VMware adapter | Linux/DPDK role | Connection | Virtual device |
| --- | --- | --- | --- |
| Network Adapter | Management and SSH | NAT | E1000 |
| Network Adapter 2 | DPDK port 0 / input | `NetPro-RX` | VMXNET3 |
| Network Adapter 3 | DPDK port 1 / HTTP output | `NetPro-HTTP` | VMXNET3 |
| Network Adapter 4 | DPDK port 2 / TLS output | `NetPro-TLS` | VMXNET3 |

All adapters must have **Connect at power on** enabled. `NetPro-HTTP` and `NetPro-TLS` are shared with the Policy Server. The Packet Generator will share `NetPro-RX` with NPB adapter 2.

With the VM powered off and VMware closed, the `.vmx` file should contain:

```text
ethernet1.virtualDev = "vmxnet3"
ethernet2.virtualDev = "vmxnet3"
ethernet3.virtualDev = "vmxnet3"
```

Keep `ethernet0`, the NAT management adapter, on E1000.

## Verified interface and PCI mapping

```text
Management: ens33  -> 0000:02:01.0 -> e1000
DPDK port 0 / RX:  ens192 -> 0000:0b:00.0 -> vmxnet3
DPDK port 1 / HTTP: ens224 -> 0000:13:00.0 -> vmxnet3
DPDK port 2 / TLS: ens256 -> 0000:1b:00.0 -> vmxnet3
```

PCI addresses are VM-specific and may change if adapters are removed or re-added. Always confirm them before binding:

```bash
lspci -nnk | grep -A3 -i ethernet
ip -br addr
sudo dpdk-devbind.py -s
```

The management adapter must remain under the kernel driver and must never be bound to DPDK.

## Install build dependencies

```bash
sudo apt update
sudo apt install -y \
  build-essential git wget xz-utils \
  meson ninja-build pkg-config python3-pyelftools \
  libnuma-dev libelf-dev \
  cmake ragel libboost-all-dev \
  libcurl4-openssl-dev libjansson-dev \
  tmux ethtool pciutils
```

If `apt` says `/var/lib/dpkg/lock-frontend` is held by `unattended-upgr`, allow the automatic update to finish. Do not delete the lock file.

## Install DPDK 22.11.2

```bash
cd ~
wget https://fast.dpdk.org/rel/dpdk-22.11.2.tar.xz
tar -xf dpdk-22.11.2.tar.xz
cd ~/dpdk-stable-22.11.2
meson setup build
ninja -C build
sudo ninja -C build install
sudo ldconfig
```

Verify:

```bash
pkg-config --modversion libdpdk
which dpdk-devbind.py
which dpdk-hugepages.py
```

## Install Hyperscan 5.4.2

Follow the repository's Hyperscan guide and build release 5.4.2. The verified installation reports:

```bash
pkg-config --modversion libhs
```

```text
5.4.2
```

If `ldconfig -p | grep libhs` prints nothing while `pkg-config` succeeds, continue with the repository build: its Makefile can use the installed static Hyperscan library through `pkg-config`.

## Clone and build the NPB

```bash
cd ~
git clone https://github.com/Network-Laboratory-UI/NetPro-Network-Packet-Broker.git
cd ~/NetPro-Network-Packet-Broker
make
```

Do not commit generated binaries, `stats/`, or `logs/`.

## Add the stable control address

Keep DHCP on the NAT adapter and add `192.168.0.92/24` as a persistent secondary address on `ens33`, using a separate local netplan file as on the other VMs. After applying it, verify:

```bash
ip -br addr show ens33
ping -c 2 192.168.0.90
ping -c 2 192.168.0.91
```

## Prepare hugepages and bind the data adapters

Stop the NPB before changing bindings:

```bash
sudo modprobe uio
sudo modprobe uio_pci_generic
sudo dpdk-hugepages.py -p 2M --setup 2G

sudo ip link set ens192 down
sudo ip link set ens224 down
sudo ip link set ens256 down

sudo dpdk-devbind.py -b uio_pci_generic \
  0000:0b:00.0 \
  0000:13:00.0 \
  0000:1b:00.0
```

Verify that all three data adapters appear under `Network devices using DPDK-compatible driver`:

```bash
sudo dpdk-hugepages.py -s
sudo dpdk-devbind.py -s
```

Expected hugepages: 1,024 pages of 2 MB, totalling 2 GB.

## Start the NPB

The repository's `run.sh` uses three cores and four memory channels. This VM was successfully tested using all four assigned logical cores and two memory channels:

```bash
cd ~/NetPro-Network-Packet-Broker
sudo ./build/packetBroker -l 0-3 -n 2
```

Using these VM-specific EAL arguments does not change the repository. Successful startup displays statistics for ports 0, 1, and 2.

## Automatic DPDK preparation and application startup

The verified VM uses `/usr/local/sbin/netpro-npb-dpdk-prepare.sh` to restore the volatile DPDK runtime state after boot. The script:

- refuses to continue while `packetBroker` or `dpdk-testpmd` is running;
- loads `uio` and `uio_pci_generic`;
- removes stale `rtemap_*` files;
- allocates 1,024 2 MB hugepages;
- brings `ens192`, `ens224`, and `ens256` down when present; and
- binds `0000:0b:00.0`, `0000:13:00.0`, and `0000:1b:00.0` to `uio_pci_generic`.

It is invoked by the enabled oneshot service `netpro-npb-dpdk-prepare.service`. The enabled `netpro-npb.service` requires that preparation service and runs:

```text
/home/netpro/NetPro-Network-Packet-Broker/build/packetBroker -l 0-3 -n 2
```

Verify both services and the runtime state:

```bash
systemctl is-enabled netpro-npb-dpdk-prepare netpro-npb
systemctl is-active netpro-npb-dpdk-prepare netpro-npb
sudo dpdk-hugepages.py -s
sudo dpdk-devbind.py -s
sudo journalctl -u netpro-npb -n 30 --no-pager
```

After reboot, the stable `192.168.0.92/24` address returned, both services reported enabled and active, 1,024 2 MB hugepages were available, all three VMXNET3 data adapters used `uio_pci_generic`, and the NPB journal displayed statistics for ports 0, 1, and 2. This verifies complete reboot persistence.

A post-reboot HTTP enforcement retest also succeeded. The captured NPB journal showed a peak of 3,000 received packets on port 0 across the test sequence, 1,000 HTTP GET matches in an active reporting interval, 1,000 packets sent through HTTP output port 1, an idle TLS port 2, and zero RX/TX/mbuf errors. The Policy Server simultaneously received and blocked 1,000 requests and emitted 2,000 RST packets.

The post-reboot TLS enforcement retest succeeded as well. NPB recorded 1,004 TLS Client Hello matches and forwarded 1,004 packets through TLS output port 2 while HTTP port 1 remained idle. Policy repeatedly showed stable active intervals of 1,000 received and blocked packets, 1,000 client RSTs, 1,000 server RSTs, and 2,000 transmissions with zero interface errors. TRex transmitted 8,017 packets and received 16,034 RST frames, preserving the expected 2:1 ratio.

## Verified HTTP forwarding

With the Packet Generator transmitting a 256-byte HTTP profile at approximately 1,000 packets per reporting interval:

- port 0 received approximately 1,000 packets;
- `HTTP GET match` increased by approximately 1,000;
- port 1 transmitted approximately 1,000 packets;
- port 2 remained idle; and
- drops and RX/TX/mbuf errors remained zero.

An independent kernel/tcpdump test and DPDK `testpmd` test also verified traffic arrival on `0000:0b:00.0`. The `testpmd` receive counter reached 8,011 packets. Rebind the device to `uio_pci_generic` before restarting the NPB.

The application prints `PACKET BORKER`; this is a typo in the repository output, not a different program.

## Verified TLS forwarding

The repository HTTPS test uses `https_583B_single.pcap`, whose TLS SNI is `www.ui.ac.id` and destination is `152.118.24.175:443`. During the verified 1,000-pps test:

- port 0 received the generated frames;
- `TLS CLIENT HELLO match` reached approximately 1,000 per active interval;
- port 2 forwarded approximately 1,000 frames to `NetPro-TLS`;
- the Policy Server received and blocked the matching traffic; and
- RX/TX/mbuf error counters remained zero.

## Installation checklist

- [x] Ubuntu 20.04 and SSH
- [x] Four adapters with the three data adapters using VMXNET3
- [x] Stable control address `192.168.0.92/24`
- [x] DPDK 22.11.2
- [x] Hyperscan 5.4.2
- [x] Repository build
- [x] Three-port DPDK startup
- [x] HTTP classification and forwarding
- [x] Delivery from NPB HTTP output to Policy Server port 0
- [x] TLS classification and forwarding
- [x] Local boot-preparation and NPB application services
- [ ] Mixed-workload validation
- [x] Full reboot persistence after both services were installed

## Expected build dependencies

The Makefile discovers DPDK and Hyperscan through `pkg-config` and links curl and Jansson. Before building, verify:

```bash
pkg-config --modversion libdpdk
pkg-config --modversion libhs
```

The Makefile builds a static binary by default and creates `stats/` and `logs/`. Generated binaries, logs, and statistics stay local and must not be committed.

## Runtime Backend configuration and certificate trust

The dashboard-generated NPB ID is `79c57972-db3b-409e-b4e8-ab4ee526f666`. A VM-local runtime copy of `config/config.cfg` uses:

```text
HOSTNAME= https://192.168.0.94:3000
```

Back up the repository default outside the repository before installing this generated configuration. Do not commit the generated IDs or VM-specific URL.

Because the Backend uses a self-signed lab certificate, install its public certificate on the NPB VM:

```bash
sudo cp ~/netpro-backend.crt \
  /usr/local/share/ca-certificates/netpro-backend.crt
sudo update-ca-certificates
curl -i https://192.168.0.94:3000/npb/npbs
```

Never copy the Backend private key to this VM.

## Validation record

| Check | Status |
| --- | --- |
| VMware hardware | Verified |
| NIC ordering and VMXNET3 | Verified |
| Ubuntu and SSH | Verified |
| DPDK 22.11.2 | Verified |
| Hyperscan 5.4.2 | Verified |
| Repository build | Verified |
| Three-port DPDK startup | Verified |
| HTTP split | Verified |
| TLS split | Verified |
| DPDK preparation service | Verified |
| NPB application service | Verified |
| Full reboot persistence | Verified |
