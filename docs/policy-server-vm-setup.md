# NetPro Policy Server VM Setup

This guide records the Policy Server VM configuration that was verified against the `Network-Laboratory-UI/NetPro-Policy-Server` repository. It intentionally keeps all changes local to the VM and does not modify the component repository.

## Verified result

The Policy Server successfully:

- built against DPDK 22.11.2;
- detected four logical CPU cores;
- initialized two VMware VMXNET3 adapters through DPDK;
- entered its live statistics loop; and
- created the SQLite `policies` table while running;
- consumed a correctly formatted policy from Kafka at `192.168.0.90:9092`; and
- reproduced its hugepage and DPDK bindings automatically after a reboot.
- enforced matching HTTP and TLS policies; and
- generated two TCP-reset directions per blocked request and returned them to TRex with no reported interface errors.

## Repository baseline and known inconsistencies

The repository is the primary baseline, but its files disagree in several places:

- `README.md` lists DPDK 20.11.2, while `doc/DPDK installation guide.md` downloads DPDK 22.11.2. This verified setup uses 22.11.2 because it is the version used by the detailed installation procedure.
- The architecture documentation describes separate HTTP, TLS, and TCP-reset data ports, but the current source requires exactly two DPDK ports. Its error message incorrectly says that three are required.
- `startup.sh` hard-codes PCI addresses `00:13.0` and `00:14.0`; they do not match this VM.
- `run.sh` selects CPU cores `0-4`, but this lab VM has four cores (`0-3`).
- The SQLite path is hard-coded under `/home/ubuntu`, although this VM uses the account `netpro`.
- The Kafka broker is hard-coded as `192.168.0.90:9092` in `policyServer.c`.

For those reasons, this guide runs the repository's commands manually with values verified on this VM. No repository files need to be edited.

## VMware hardware

| Setting | Value |
| --- | --- |
| Guest OS | Ubuntu 20.04 |
| CPU | 4 virtual cores |
| Memory | 6 GB |
| Disk | 30 GB |
| Network Adapter | NAT; management and SSH |
| Network Adapter 2 | LAN segment `NetPro-HTTP`; VMXNET3 |
| Network Adapter 3 | LAN segment `NetPro-TLS`; VMXNET3 |
| Network Adapter 4 | LAN segment `NetPro-RX`; VMXNET3; RST output |

All adapters should have **Connect at power on** enabled.

With the VM fully powered off and VMware Workstation closed, the VM's `.vmx` file contains:

```text
ethernet1.virtualDev = "vmxnet3"
ethernet2.virtualDev = "vmxnet3"
ethernet3.virtualDev = "vmxnet3"
```

`ethernet0` is the NAT/management adapter and remains E1000.

## Verified interface mapping

```text
Management: ens33  -> 0000:02:01.0 -> e1000
Data port 1: ens192 -> 0000:0b:00.0 -> vmxnet3
Data port 2: ens224 -> 0000:13:00.0 -> vmxnet3
RST output:  ens256 -> 0000:1b:00.0 -> vmxnet3
```

The management adapter must never be bound to DPDK.

Verify the mapping before binding:

```bash
ip -br addr
sudo ethtool -i ens192
sudo ethtool -i ens224
sudo ethtool -i ens256
```

## SSH and build dependencies

Install SSH if needed:

```bash
sudo apt update
sudo apt install -y openssh-server
sudo systemctl enable --now ssh
sudo ufw allow OpenSSH
```

Install the Policy Server and DPDK build requirements:

```bash
sudo apt update
sudo apt install -y \
  build-essential git wget xz-utils \
  meson ninja-build pkg-config \
  python3-pyelftools \
  libnuma-dev libelf-dev \
  sqlite3 libsqlite3-dev \
  librdkafka-dev \
  libcurl4-openssl-dev \
  libjansson-dev \
  tmux ethtool pciutils
```

## Install DPDK 22.11.2

```bash
cd ~
wget https://fast.dpdk.org/rel/dpdk-22.11.2.tar.xz
tar -xf dpdk-22.11.2.tar.xz
cd dpdk-stable-22.11.2

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

Expected version and tool locations on this VM:

```text
22.11.2
/usr/local/bin/dpdk-devbind.py
/usr/local/bin/dpdk-hugepages.py
```

## Clone and build the Policy Server

```bash
cd ~
git clone https://github.com/Network-Laboratory-UI/NetPro-Policy-Server
cd ~/NetPro-Policy-Server
make
```

The build should create:

```text
build/policyServer-shared
build/policyServer -> policyServer-shared
logs/
stats/
```

If `make` reports clock skew, correct the VM clock and rebuild without changing file contents:

```bash
sudo timedatectl set-ntp true
sudo systemctl restart systemd-timesyncd
sleep 3
touch Makefile policyServer.c
make
git status --short
```

The final Git command should produce no output.

## Create the hard-coded database location

The code expects `/home/ubuntu/NetPro-Policy-Server/policy.db`. The VM account is `netpro`, so create the expected local directory:

```bash
sudo mkdir -p /home/ubuntu/NetPro-Policy-Server
```

This directory is outside the Git checkout and does not modify the repository.

## Add the local Kafka-facing address

The source hard-codes Kafka at `192.168.0.90:9092`. Keep DHCP on `ens33` for NAT and SSH, then add a persistent secondary address for the NetPro control network:

```bash
sudo nano /etc/netplan/99-netpro-control.yaml
```

```yaml
network:
  version: 2
  ethernets:
    ens33:
      addresses:
        - 192.168.0.91/24
```

Apply and test:

```bash
sudo chmod 600 /etc/netplan/99-netpro-control.yaml
sudo netplan apply
ip -br addr show ens33
ping -c 2 192.168.0.90
```

## Prepare DPDK automatically after boot

Do not use the repository's unmodified `startup.sh` on this VM: its PCI addresses do not match this VM. Create a local-only preparation script instead:

```bash
sudo nano /usr/local/sbin/netpro-dpdk-prepare.sh
```

```bash
#!/bin/bash
set -euo pipefail

/usr/sbin/modprobe uio
/usr/sbin/modprobe uio_pci_generic

/usr/local/bin/dpdk-hugepages.py -p 2M --setup 2G

for interface in ens192 ens224 ens256; do
    if /usr/sbin/ip link show "$interface" >/dev/null 2>&1; then
        /usr/sbin/ip link set "$interface" down
    fi
done

/usr/local/bin/dpdk-devbind.py \
    -b uio_pci_generic \
    0000:0b:00.0 \
    0000:1b:00.0
```

```bash
sudo chmod 755 /usr/local/sbin/netpro-dpdk-prepare.sh
sudo nano /etc/systemd/system/netpro-dpdk-prepare.service
```

```ini
[Unit]
Description=Prepare hugepages and DPDK adapters for NetPro Policy Server
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/netpro-dpdk-prepare.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

Enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now netpro-dpdk-prepare
```

Verify after a reboot:

```bash
systemctl is-active netpro-dpdk-prepare
sudo dpdk-hugepages.py -s
sudo dpdk-devbind.py -s
ping -c 2 192.168.0.90
```

Expected state:

- the service reports `active` (`active (exited)` in the detailed status);
- 1,024 pages of 2 MB each are mounted, totalling 2 GB;
- `0000:0b:00.0` and `0000:1b:00.0` use `uio_pci_generic` for the default HTTP mode; and
- `ens33` remains active for SSH.

## Switch safely between HTTP and TLS modes

The current Policy Server reads only DPDK application port 0 and uses application port 1 for RST output. Create this VM-local helper so the inspected input can be switched without editing the repository:

```bash
sudo nano /usr/local/sbin/netpro-policy-mode
```

```bash
#!/usr/bin/env bash
set -euo pipefail

HTTP_PCI="0000:0b:00.0"
TLS_PCI="0000:13:00.0"
RST_PCI="0000:1b:00.0"

if pgrep -f '/build/policyServer' >/dev/null; then
    echo "ERROR: Stop the Policy Server before changing DPDK bindings."
    exit 1
fi

if [[ $# -ne 1 ]]; then
    echo "Usage: sudo netpro-policy-mode {http|tls|status}"
    exit 1
fi

if [[ "$1" == "status" ]]; then
    /usr/local/bin/dpdk-devbind.py -s
    exit 0
fi

/usr/sbin/modprobe uio
/usr/sbin/modprobe uio_pci_generic

case "$1" in
    http)
        /usr/local/bin/dpdk-devbind.py -b vmxnet3 "$TLS_PCI"
        /usr/sbin/ip link set ens224 down 2>/dev/null || true
        /usr/sbin/ip link set ens192 down 2>/dev/null || true
        /usr/sbin/ip link set ens256 down 2>/dev/null || true
        /usr/local/bin/dpdk-devbind.py -b uio_pci_generic "$HTTP_PCI" "$RST_PCI"
        echo "HTTP mode ready: port 0 = HTTP, port 1 = RST"
        ;;
    tls)
        /usr/local/bin/dpdk-devbind.py -b vmxnet3 "$HTTP_PCI"
        /usr/sbin/ip link set ens192 down 2>/dev/null || true
        /usr/sbin/ip link set ens224 down 2>/dev/null || true
        /usr/sbin/ip link set ens256 down 2>/dev/null || true
        /usr/local/bin/dpdk-devbind.py -b uio_pci_generic "$TLS_PCI" "$RST_PCI"
        echo "TLS mode ready: port 0 = TLS, port 1 = RST"
        ;;
    *)
        echo "Usage: sudo netpro-policy-mode {http|tls|status}"
        exit 1
        ;;
esac

/usr/local/bin/dpdk-devbind.py -s
```

```bash
sudo chmod 755 /usr/local/sbin/netpro-policy-mode
```

Usage:

```bash
sudo netpro-policy-mode http
sudo netpro-policy-mode tls
sudo netpro-policy-mode status
```

The helper refuses to change bindings while the Policy Server is running. It was verified in both directions: HTTP mode binds `0000:0b:00.0` plus `0000:1b:00.0`; TLS mode binds `0000:13:00.0` plus `0000:1b:00.0`. Notices that a device is already using the requested driver are harmless.

The selection is not persistent across reboot. The existing `netpro-dpdk-prepare` service intentionally restores HTTP mode at boot.

## Start the Policy Server

Run from the repository root so relative configuration paths resolve correctly:

```bash
cd ~/NetPro-Policy-Server
sudo ./build/policyServer -l 0-3 -n 2
```

This uses the same DPDK memory-channel value as `run.sh`, but selects the four cores actually assigned to this VM.

Expected startup indicators include:

```text
EAL: Detected CPU lcores: 4
EAL: Probe PCI driver: net_vmxnet3 ... 0000:0b:00.0
EAL: Probe PCI driver: net_vmxnet3 ... 0000:1b:00.0
```

The live statistics counters remain zero until another NetPro component sends traffic.

`PACKET BORKER` in the statistics display is a typo in the repository; it does not mean that the wrong executable is running.

## Verify SQLite while the server is running

Open a second SSH session while the Policy Server is still running:

```bash
sudo sqlite3 /home/ubuntu/NetPro-Policy-Server/policy.db ".tables"
```

Expected output:

```text
policies
```

Stop the Policy Server with `Ctrl+C`. The repository deliberately calls `delete_database()` during a clean shutdown, so `policy.db` is removed. Running `sqlite3` against that path after shutdown creates a new empty database and therefore shows no tables.

## Verify Kafka integration

With the Policy Server running, publish this one-line test message from the Kafka VM:

```json
{"type":"create","createdBlockedList":{"domain":"example.com","ip_add":"93.184.216.34","id":"netpro-test-001"}}
```

Then query the Policy VM from a second SSH session:

```bash
sudo sqlite3 /home/ubuntu/NetPro-Policy-Server/policy.db \
"SELECT id, domain, ip_address FROM policies WHERE id='netpro-test-001';"
```

Verified output:

```text
netpro-test-001|example.com|93.184.216.34
```

The consumer always starts at the beginning of partition 0. Non-JSON test text produces a logged JSON parsing error but does not crash the process. Keep the production topic free of arbitrary plaintext messages.

## Troubleshooting

### `Cannot get hugepage information`

The boot preparation service has not run or failed. Check it with:

```bash
systemctl status netpro-dpdk-prepare --no-pager
sudo dpdk-hugepages.py -s
```

### `Error: number of ports must be 3`

This repository message is misleading. It appeared when the two data NICs had returned to the kernel `vmxnet3` driver after reboot, so DPDK saw no ports. Check `sudo dpdk-devbind.py -s`.

### Hugepage setup reports pages still in use

After confirming that no Policy Server process is running, stale `rtemap_*` runtime files can be removed:

```bash
pgrep -af policyServer || echo "Policy Server is not running"
sudo rm -f -- /dev/hugepages/rtemap_*
sudo systemctl restart netpro-dpdk-prepare
```

Never remove those mappings while a DPDK process is running.

## Verified HTTP and TLS enforcement

In HTTP mode, DPDK port 0 is PCI `0000:0b:00.0` and DPDK port 1 is the RST output at `0000:1b:00.0`. The verified `facebook.co.id` policy produced approximately 1,000 blocked requests, 1,000 client RSTs, and 1,000 server RSTs per active interval.

In TLS mode, stop the Policy Server, return `0000:0b:00.0` to `vmxnet3`, and bind `0000:13:00.0` plus `0000:1b:00.0` to `uio_pci_generic`. The verified `www.ui.ac.id` policy produced the same match, drop, and two-direction RST behavior. TRex received 16,032 frames in response to 8,016 TLS transmissions.

The current source polls only application port 0, so HTTP and TLS inputs cannot run simultaneously without a source change. Do not restart the HTTP-mode preparation service during a manual TLS-mode test because it will restore the HTTP bindings.

See [End-to-end HTTP and TLS validation](end-to-end-http-validation.md).

## Remaining integration work

- Design and review a Policy Server source change for simultaneous HTTP and TLS inputs.
- Validate mixed HTTP, HTTPS, and UDP workloads.
- Replace the mode-specific local preparation behavior with an explicit, documented mode selector if repeated switching is required.
