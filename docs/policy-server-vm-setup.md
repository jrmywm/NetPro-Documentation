# NetPro Policy Server VM Setup

This guide records the Policy Server VM configuration that was verified against the `Network-Laboratory-UI/NetPro-Policy-Server` repository. The runtime/source correction described below is the local commit `d658fa2 Fix two-port policy telemetry mapping`; it is part of the verified lab state, but must not be pushed to a Network-Laboratory repository as part of a rebuild.

## Verified result

The Policy Server successfully:

- built against DPDK 22.11.2;
- detected four logical CPU cores;
- initialized exactly two VMware VMXNET3 adapters through DPDK (selected input plus RST/output);
- entered its live statistics loop; and
- created the SQLite `policies` table while running;
- consumed a correctly formatted policy from Kafka at `192.168.0.90:9092`; and
- reproduced its hugepage and DPDK bindings automatically after a reboot;
- enforced matching HTTP and TLS policies; and
- generated two TCP-reset directions per blocked request and returned them to TRex with no reported interface errors.

## Repository baseline and known inconsistencies

The repository is the primary baseline, but its files disagree in several places:

- `README.md` lists DPDK 20.11.2, while `doc/DPDK installation guide.md` downloads DPDK 22.11.2. This verified setup uses 22.11.2 because it is the version used by the detailed installation procedure.
- The architecture documentation describes separate HTTP, TLS, and TCP-reset data ports, but the runtime accepts exactly two DPDK ports. Its error message incorrectly says that three are required. HTTP mode uses `0b:00.0` as input and `1b:00.0` as RST/output; TLS mode uses `13:00.0` as input and the same `1b:00.0` RST/output.
- `startup.sh` hard-codes PCI addresses `00:13.0` and `00:14.0`; they do not match this VM.
- `run.sh` selects CPU cores `0-4`, but this lab VM has four cores (`0-3`).
- The SQLite path is hard-coded under `/home/ubuntu`, although this VM uses the account `netpro`.
- The Kafka broker is hard-coded as `192.168.0.90:9092` in `policyServer.c`.

For those reasons, this guide uses VM-local configuration plus the verified local telemetry fix. Do not commit machine-local configuration, logs, generated stats, binaries, or `*.before-*` backups.

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

The preparation script is deliberately the boot-safe default: it allocates `1024` 2-MB hugepages (2 GB) and binds `0b:00.0` plus `1b:00.0`. It must not bind the management adapter. The TLS input `13:00.0` is returned to `vmxnet3` when TLS mode is selected.

## Run the Policy Server under systemd

Create `/etc/default/netpro-policy` with the default/reboot-safe mode:

```bash
echo 'NETPRO_POLICY_MODE=http' | sudo tee /etc/default/netpro-policy
```

The verified application unit is:

```ini
[Unit]
Description=NetPro Policy Server
Requires=netpro-dpdk-prepare.service
After=netpro-dpdk-prepare.service network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/netpro/NetPro-Policy-Server
EnvironmentFile=-/etc/default/netpro-policy
ExecStart=/home/netpro/NetPro-Policy-Server/build/policyServer -l 0-3 -n 2
Restart=on-failure
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

Save it as `/etc/systemd/system/netpro-policy.service`, then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now netpro-policy
systemctl is-enabled netpro-dpdk-prepare netpro-policy
systemctl is-active netpro-dpdk-prepare netpro-policy
sudo journalctl -u netpro-policy -n 40 --no-pager
```

The service's `WorkingDirectory`, optional environment file, DPDK command, restart policy, and SIGINT shutdown are significant. The Policy process must be stopped before changing DPDK bindings; systemd will restart it after a failure, so stop the unit rather than only killing a child process.

## Switch safely between HTTP and TLS modes

The Policy Server accepts exactly two DPDK ports. Create this VM-local helper so the selected input can be switched without editing the repository. The `status` branch intentionally runs before the process-running guard so status can be queried while the service is active:

```bash
sudo nano /usr/local/sbin/netpro-policy-mode
```

```bash
#!/usr/bin/env bash
set -euo pipefail

HTTP_PCI="0000:0b:00.0"
TLS_PCI="0000:13:00.0"
RST_PCI="0000:1b:00.0"

if [[ $# -ne 1 ]]; then
    echo "Usage: sudo netpro-policy-mode {http|tls|status}"
    exit 1
fi

if [[ "$1" == "status" ]]; then
    configured="http"
    if [[ -r /etc/default/netpro-policy ]]; then
        # shellcheck disable=SC1091
        source /etc/default/netpro-policy
        configured="${NETPRO_POLICY_MODE:-http}"
    fi
    echo "configured mode: $configured"
    /usr/local/bin/dpdk-devbind.py -s
    exit 0
fi

if pgrep -f '/build/policyServer' >/dev/null; then
    echo "ERROR: Stop the Policy Server before changing DPDK bindings."
    exit 1
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
        printf 'NETPRO_POLICY_MODE=http\n' | /usr/sbin/tee /etc/default/netpro-policy >/dev/null
        echo "HTTP mode ready: port 0 = HTTP, port 1 = RST"
        ;;
    tls)
        /usr/local/bin/dpdk-devbind.py -b vmxnet3 "$HTTP_PCI"
        /usr/sbin/ip link set ens192 down 2>/dev/null || true
        /usr/sbin/ip link set ens224 down 2>/dev/null || true
        /usr/sbin/ip link set ens256 down 2>/dev/null || true
        /usr/local/bin/dpdk-devbind.py -b uio_pci_generic "$TLS_PCI" "$RST_PCI"
        printf 'NETPRO_POLICY_MODE=tls\n' | /usr/sbin/tee /etc/default/netpro-policy >/dev/null
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
sudo systemctl stop netpro-policy
sudo netpro-policy-mode http
sudo netpro-policy-mode status
sudo systemctl start netpro-policy
```

For TLS, use the same sequence with `tls`:

```bash
sudo systemctl stop netpro-policy
sudo netpro-policy-mode tls
sudo systemctl start netpro-policy
```

The helper refuses to change bindings while the Policy Server is running, writes `NETPRO_POLICY_MODE=http|tls` to `/etc/default/netpro-policy`, and reports the configured mode and current bindings with `status`. It was verified in both directions: HTTP mode binds `0000:0b:00.0` plus `0000:1b:00.0` and returns `0000:13:00.0` to `vmxnet3`; TLS mode binds `0000:13:00.0` plus `0000:1b:00.0` and returns `0000:0b:00.0` to `vmxnet3`. Notices that a device is already using the requested driver are harmless.

HTTP is the boot-time binding layout because `netpro-dpdk-prepare.service` binds `0b:00.0` and `1b:00.0`. Before rebooting from TLS mode, stop the Policy service and run `sudo netpro-policy-mode http`; this restores both the HTTP bindings and `NETPRO_POLICY_MODE=http`. If the VM is rebooted while `/etc/default/netpro-policy` still says `tls`, the preparation service restores HTTP NIC bindings but the process can label port 0 as TLS. Repair that mismatch by stopping `netpro-policy`, running `sudo netpro-policy-mode http`, and starting the service again. Select TLS again only when beginning a TLS test.

## Start the Policy Server

The enabled `netpro-policy.service` runs from the repository root so relative configuration paths resolve correctly. A manual foreground run is useful for first-install diagnosis only:

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

## Two-port telemetry fix (local Policy commit)

The live runtime has two DPDK ports, not three. Before the local fix, `policyServer.c` assumed port 0 was HTTP input, port 1 was TLS input, and port 2 was RST/output in both CSV output and `populate_json_stats()`. That produced misleading telemetry and was the source of the “three ports” confusion. `aggregator.c` is legacy code and is not the live sender.

The verified local commit is:

```text
d658fa2 Fix two-port policy telemetry mapping
```

Both live telemetry functions now read `NETPRO_POLICY_MODE`. The selected input is reported only in the corresponding HTTP or TLS fields, DPDK port 1 is always reported as RST/output, and inactive protocol fields are zero. The live POST goes directly from `policyServer` to `/ps/ps-packet`; do not chase `aggregator.c` when diagnosing missing rows.

Keep this commit local to the lab unless a separate source review explicitly authorizes an upstream change. Never commit generated stats, logs, binaries, `/etc/default/netpro-policy`, or `*.before-*` backups.

### Reproduce the source edit from a fresh upstream clone

The hash `d658fa2` is available only in the verified VM's local history; a fresh upstream clone must not be told to fetch or cherry-pick an unavailable hash. The following exact edit reproduces the fix. It assumes the clone still has the pre-fix hard-coded mappings. If either precondition fails, stop and inspect the source rather than applying the edit blindly.

From the Policy repository root:

```bash
cd ~/NetPro-Policy-Server
test "$(git rev-parse --is-inside-work-tree)" = true
test -f policyServer.c
grep -Fq 'port_statistics[2].rstClient' policyServer.c
grep -Fq 'json_object_set(jsonObject, "rx_i_tls_count", json_integer(port_statistics[1].rx_count));' policyServer.c
cp -a policyServer.c "policyServer.c.before-d658fa2"
```

Run this exact source-edit script. It replaces only `print_stats_csv()` and `populate_json_stats()` and refuses to proceed if the expected pre-fix anchors are absent:

The preferred transfer path is a patch exported from the known-good VM. On that VM, where the local commit exists, export only the source-file diff:

```bash
cd ~/NetPro-Policy-Server
git show --format= --binary d658fa2 -- policyServer.c > ~/netpro-policy-two-port-telemetry.patch
sha256sum ~/netpro-policy-two-port-telemetry.patch
```

Transfer that patch file to the fresh-clone VM through the approved private channel. Do not publish it or assume the upstream repository contains `d658fa2`. On the fresh clone, check that the artifact was actually transferred and contains both function edits before applying it:

```bash
cd ~/NetPro-Policy-Server
test -s ~/netpro-policy-two-port-telemetry.patch
grep -Fq 'print_stats_csv' ~/netpro-policy-two-port-telemetry.patch
grep -Fq 'populate_json_stats' ~/netpro-policy-two-port-telemetry.patch
grep -Fq 'NETPRO_POLICY_MODE' ~/netpro-policy-two-port-telemetry.patch
test -f policyServer.c
grep -Fq 'port_statistics[2].rstClient' policyServer.c
cp -a policyServer.c "policyServer.c.before-d658fa2"
git apply --check ~/netpro-policy-two-port-telemetry.patch
git apply ~/netpro-policy-two-port-telemetry.patch
git diff -- policyServer.c
```

If the patch is unavailable, the exact self-contained edit script below is the fallback; it has the same pre-fix anchors and replacement mapping.

```bash
python3 - <<'PY'
from pathlib import Path

path = Path("policyServer.c")
source = path.read_text()
anchors = (
    "PS_ID, port_statistics[2].rstClient",
    'json_object_set(jsonObject, "rx_i_tls_count", json_integer(port_statistics[1].rx_count));',
)
missing = [anchor for anchor in anchors if anchor not in source]
if missing:
    raise SystemExit("Refusing edit; missing pre-fix anchor(s): " + ", ".join(missing))

csv_start = source.index("static void print_stats_csv(FILE *f, char *timestamp)\n{")
csv_end = source.index("\n}\n\n/**\n * This function reads the configuration", csv_start) + 2
json_start = source.index("static void\npopulate_json_stats(json_t *jsonArray, char *timestamp)\n{")
json_end = source.index("\n}\n/**\n * This function retrieves statistics", json_start) + 2

csv = r'''static void print_stats_csv(FILE *f, char *timestamp)
{
	// Write data to the CSV file
	const char *mode = getenv("NETPRO_POLICY_MODE");
	const int tls_mode = mode != NULL && strcmp(mode, "tls") == 0;
	const int input_port = 0;
	const int output_port = 1;

	fprintf(f, "%s,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%s,%ld,%ld,%ld\n",
			PS_ID,
			port_statistics[output_port].rstClient,
			port_statistics[output_port].rstServer,
			tls_mode ? 0 : port_statistics[input_port].rx_count,
			tls_mode ? 0 : port_statistics[input_port].tx_count,
			tls_mode ? 0 : port_statistics[input_port].rx_size,
			tls_mode ? 0 : port_statistics[input_port].tx_size,
			tls_mode ? 0 : port_statistics[input_port].dropped,
			tls_mode ? 0 : port_statistics[input_port].err_rx,
			tls_mode ? 0 : port_statistics[input_port].err_tx,
			tls_mode ? 0 : port_statistics[input_port].mbuf_err,
			tls_mode ? port_statistics[input_port].rx_count : 0,
			tls_mode ? port_statistics[input_port].tx_count : 0,
			tls_mode ? port_statistics[input_port].rx_size : 0,
			tls_mode ? port_statistics[input_port].tx_size : 0,
			tls_mode ? port_statistics[input_port].dropped : 0,
			tls_mode ? port_statistics[input_port].err_rx : 0,
			tls_mode ? port_statistics[input_port].err_tx : 0,
			tls_mode ? port_statistics[input_port].mbuf_err : 0,
			port_statistics[output_port].rx_count,
			port_statistics[output_port].tx_count,
			port_statistics[output_port].rx_size,
			port_statistics[output_port].tx_size,
			port_statistics[output_port].dropped,
			port_statistics[output_port].err_rx,
			port_statistics[output_port].err_tx,
			port_statistics[output_port].mbuf_err,
			timestamp,
			tls_mode ? 0 : port_statistics[input_port].throughput,
			tls_mode ? port_statistics[input_port].throughput : 0,
			port_statistics[output_port].throughput);
}'''

json = r'''static void
populate_json_stats(json_t *jsonArray, char *timestamp)
{
	// Create object for the statistics
	json_t *jsonObject = json_object();
	const char *mode = getenv("NETPRO_POLICY_MODE");
	const int tls_mode = mode != NULL && strcmp(mode, "tls") == 0;
	const int input_port = 0;
	const int output_port = 1;

	// Populate the JSON object
	json_object_set(jsonObject, "ps_id", json_string(PS_ID));

	json_object_set(jsonObject, "rx_i_http_count", json_integer(tls_mode ? 0 : port_statistics[input_port].rx_count));
	json_object_set(jsonObject, "tx_i_http_count", json_integer(tls_mode ? 0 : port_statistics[input_port].tx_count));
	json_object_set(jsonObject, "rx_i_http_size", json_integer(tls_mode ? 0 : port_statistics[input_port].rx_size));
	json_object_set(jsonObject, "tx_i_http_size", json_integer(tls_mode ? 0 : port_statistics[input_port].tx_size));
	json_object_set(jsonObject, "rx_i_http_drop", json_integer(tls_mode ? 0 : port_statistics[input_port].dropped));
	json_object_set(jsonObject, "rx_i_http_error", json_integer(tls_mode ? 0 : port_statistics[input_port].err_rx));
	json_object_set(jsonObject, "tx_i_http_error", json_integer(tls_mode ? 0 : port_statistics[input_port].err_tx));
	json_object_set(jsonObject, "rx_i_http_mbuf", json_integer(tls_mode ? 0 : port_statistics[input_port].mbuf_err));

	json_object_set(jsonObject, "rx_i_tls_count", json_integer(tls_mode ? port_statistics[input_port].rx_count : 0));
	json_object_set(jsonObject, "tx_i_tls_count", json_integer(tls_mode ? port_statistics[input_port].tx_count : 0));
	json_object_set(jsonObject, "rx_i_tls_size", json_integer(tls_mode ? port_statistics[input_port].rx_size : 0));
	json_object_set(jsonObject, "tx_i_tls_size", json_integer(tls_mode ? port_statistics[input_port].tx_size : 0));
	json_object_set(jsonObject, "rx_i_tls_drop", json_integer(tls_mode ? port_statistics[input_port].dropped : 0));
	json_object_set(jsonObject, "rx_i_tls_error", json_integer(tls_mode ? port_statistics[input_port].err_rx : 0));
	json_object_set(jsonObject, "tx_i_tls_error", json_integer(tls_mode ? port_statistics[input_port].err_tx : 0));
	json_object_set(jsonObject, "rx_i_tls_mbuf", json_integer(tls_mode ? port_statistics[input_port].mbuf_err : 0));

	json_object_set(jsonObject, "rstClient", json_integer(port_statistics[output_port].rstClient));
	json_object_set(jsonObject, "rstServer", json_integer(port_statistics[output_port].rstServer));
	json_object_set(jsonObject, "rx_o_count", json_integer(port_statistics[output_port].rx_count));
	json_object_set(jsonObject, "tx_o_count", json_integer(port_statistics[output_port].tx_count));
	json_object_set(jsonObject, "rx_o_size", json_integer(port_statistics[output_port].rx_size));
	json_object_set(jsonObject, "tx_o_size", json_integer(port_statistics[output_port].tx_size));
	json_object_set(jsonObject, "rx_o_drop", json_integer(port_statistics[output_port].dropped));
	json_object_set(jsonObject, "rx_o_error", json_integer(port_statistics[output_port].err_rx));
	json_object_set(jsonObject, "tx_o_error", json_integer(port_statistics[output_port].err_tx));
	json_object_set(jsonObject, "rx_o_mbuf", json_integer(port_statistics[output_port].mbuf_err));

	json_object_set(jsonObject, "time", json_string(timestamp));
	json_object_set(jsonObject, "rx_i_http_throughput", json_integer(tls_mode ? 0 : port_statistics[input_port].throughput));
	json_object_set(jsonObject, "rx_i_tls_throughput", json_integer(tls_mode ? port_statistics[input_port].throughput : 0));
	json_object_set(jsonObject, "tx_o_throughput", json_integer(port_statistics[output_port].throughput));

	// Append the JSON object to the JSON array
	json_array_append(jsonArray, jsonObject);
}'''

source = source[:csv_start] + csv + source[csv_end:]
json_start = source.index("static void\npopulate_json_stats(json_t *jsonArray, char *timestamp)\n{")
json_end = source.index("\n}\n/**\n * This function retrieves statistics", json_start) + 2
source = source[:json_start] + json + source[json_end:]
path.write_text(source)
PY
```

The invariant is deliberate: `NETPRO_POLICY_MODE` selects the protocol labels only; DPDK always enumerates the selected input as application port 0 and the RST/output adapter as port 1. HTTP mode reports port 0 only in `rx_i_http_*`, TLS mode reports it only in `rx_i_tls_*`, inactive protocol fields are zero, and all `rst*`/`rx_o_*`/`tx_o_*` fields come from port 1.

Rebuild and restart the local service:

```bash
make
sudo systemctl daemon-reload
sudo systemctl restart netpro-policy
systemctl is-active netpro-policy
```

Validate both mappings before staging anything:

```bash
grep '^NETPRO_POLICY_MODE=' /etc/default/netpro-policy
sudo netpro-policy-mode status
sudo journalctl -u netpro-policy -n 40 --no-pager
```

Run the HTTP and TLS checks in [End-to-end HTTP and TLS validation](end-to-end-http-validation.md), including the PostgreSQL `MAX(packet_id)` baseline and 70-second wait. Confirm HTTP has nonzero `rx_i_http_count`/HTTP throughput and zero TLS fields, then switch with `sudo systemctl stop netpro-policy`, `sudo netpro-policy-mode tls`, and `sudo systemctl start netpro-policy`; confirm the inverse TLS mapping and port-1 RST/output values. One- or two-packet differences are sampling-boundary effects.

If the build or validation fails, stop the service and restore the backup before investigating further:

```bash
sudo systemctl stop netpro-policy
cp -a policyServer.c.before-d658fa2 policyServer.c
make
```

Only after the diff and both mode checks pass may the source fix be recorded locally. Stage exactly the source file, inspect the staged diff, and do not push upstream:

```bash
git add policyServer.c
git diff --cached -- policyServer.c
git commit -m "Fix two-port policy telemetry mapping"
# Never run git push for this local lab fix.
```

The verified VM called this local commit `d658fa2`; a fresh clone will have a different commit ID unless its parent history is identical. The reproducible artifact is the checked precondition plus the exact edit above, not an unavailable hash.

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

## Runtime Backend configuration and certificate trust

The dashboard-generated Policy Server ID is `6f7e663a-dfae-4b31-9e4e-93bc64d3e0a1`. A VM-local runtime copy of `config/config.cfg` uses:

```text
HOSTNAME= https://192.168.0.94:3000
```

Back up the repository default outside the repository before installing the generated configuration. Do not commit the generated ID or VM-specific URL.

Install the Backend public certificate so libcurl can validate its self-signed lab certificate:

```bash
sudo cp ~/netpro-backend.crt \
  /usr/local/share/ca-certificates/netpro-backend.crt
sudo update-ca-certificates
curl -i https://192.168.0.94:3000/ps/blocked-list
```

Never copy the Backend private key to this VM. Once the runtime configuration and trust were installed, Policy heartbeats appeared in PostgreSQL every five seconds and the dashboard could mark the device Active.

## Troubleshooting

### `Cannot get hugepage information`

The boot preparation service has not run or failed. Check it with:

```bash
systemctl status netpro-dpdk-prepare --no-pager
sudo dpdk-hugepages.py -s
```

### `Error: number of ports must be 3`

This repository message is misleading in two ways: the runtime accepts exactly two DPDK ports, and it can also appear when the selected NICs have returned to the kernel `vmxnet3` driver after reboot. Check the preparation service and `sudo dpdk-devbind.py -s`. The expected pair is `0b:00.0` + `1b:00.0` in HTTP mode or `13:00.0` + `1b:00.0` in TLS mode.

### Hugepage setup reports pages still in use

After confirming that no Policy Server process is running, stale `rtemap_*` runtime files can be removed:

```bash
pgrep -af policyServer || echo "Policy Server is not running"
sudo rm -f -- /dev/hugepages/rtemap_*
sudo systemctl restart netpro-dpdk-prepare
```

Never remove those mappings while a DPDK process is running.

## Verified HTTP and TLS enforcement and telemetry

In HTTP mode, DPDK port 0 is PCI `0000:0b:00.0` and DPDK port 1 is the RST output at `0000:1b:00.0`. The verified `facebook.co.id` policy produced approximately 1,000 blocked requests, 1,000 client RSTs, and 1,000 server RSTs per active interval. The corresponding telemetry showed `rx_i_http_count` about 1,000, `rx_i_tls_count` 0, RST client/server about 1,000 each, output RX/TX about 1,000/2,000, output drop about 1,000, nonzero HTTP/output throughput, and TLS throughput 0.

In TLS mode, stop the Policy Server, return `0000:0b:00.0` to `vmxnet3`, and bind `0000:13:00.0` plus `0000:1b:00.0` to `uio_pci_generic`. The verified `www.ui.ac.id` policy produced the same match, drop, and two-direction RST behavior. Telemetry showed HTTP input/throughput 0, TLS input about 1,000, RST client/server about 1,000 each, output RX/TX about 1,000/2,000, TLS throughput about `587000`, and output throughput about `108000`. TRex received 16,032 frames in response to 8,016 TLS transmissions.

Small one- or two-packet differences are sampling-boundary effects, not a failed mapping. Compare active intervals and the direction fields together.

Return to HTTP mode before the reboot, then verify the machine-local service state after startup:

```bash
systemctl is-active netpro-dpdk-prepare netpro-policy
sudo netpro-policy-mode status
sudo dpdk-hugepages.py -s
sudo dpdk-devbind.py -s
curl -i https://192.168.0.94:3000/ps/pss
```

The verified reboot restored HTTP mode, `NETPRO_POLICY_MODE=http`, 2 GB of hugepages, `0b:00.0`/`1b:00.0` bindings, and an active dashboard heartbeat.

Do not restart `netpro-dpdk-prepare` during a TLS test: it intentionally restores the HTTP bindings. If a mode switch fails, stop `netpro-policy`, run `sudo netpro-policy-mode status`, restore the desired mode, and start the service again. To roll back the local telemetry change, stop the service and restore the separately saved pre-change `policyServer.c`/binary; do not delete the active build or backups blindly.

See [End-to-end HTTP and TLS validation](end-to-end-http-validation.md).

## Remaining integration work

- Validate mixed HTTP, HTTPS, and UDP workloads after deciding how to schedule the selectable input modes.
- Review whether the local telemetry fix should be maintained upstream; the lab rebuild itself must keep it local.
