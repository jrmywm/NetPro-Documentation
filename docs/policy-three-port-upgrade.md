# Policy Server three-port build and validation

This is the current runbook for the Policy Server build that processes HTTP and TLS inputs at the same time. The VM's local source commit is `e75c9f2` (`Process HTTP and TLS concurrently on three policy ports`). The earlier selectable two-port setup remains documented in [the historical Policy Server guide](policy-server-vm-setup.md).

## Verified layout and scope

| Role | PCI address | Linux interface before DPDK binding |
| --- | --- | --- |
| HTTP input | `0000:0b:00.0` | `ens192` |
| TLS input | `0000:13:00.0` | `ens224` |
| RST output | `0000:1b:00.0` | `ens256` |
| Management | `0000:02:01.0` | `ens33` |

The service started with all three data adapters bound to `uio_pci_generic`; DPDK probed the three devices. Sequential HTTP and TLS checks passed without changing bindings, and a mixed workload passed. After a Policy VM reboot, both Policy services were active, the three DPDK bindings and 2 GB of hugepages returned, and another mixed workload passed. `ens33` remained kernel-managed for SSH and control-network access.

The reproducible source snapshot is [policyServer.c](../assets/policy-three-port/policyServer.c). An incremental patch is also available at [policyServer-three-port.patch](../assets/policy-three-port/policyServer-three-port.patch); it applies only to the source baseline identified by commit `6784d46` and SHA-256 `72eaf6eb8dfc1ec62201970e9172b8db32dceeff0f8858b44d89bec1bba65382`. Verify the source before applying; do not apply this patch to a different revision or assume it is a patch against the later deployed commit `e75c9f2`. The documented VM already runs `e75c9f2`; the rebuild procedure below is for a VM at the exact baseline, not a second upgrade of that VM.

To reproduce the candidate source in a clean clone, check out the exact baseline, verify the unmodified file hash, then validate and apply the asset:

```bash
git checkout --detach 6784d46
test "$(git rev-parse --short=7 HEAD)" = 6784d46
test "$(sha256sum policyServer.c | awk '{print $1}')" = 72eaf6eb8dfc1ec62201970e9172b8db32dceeff0f8858b44d89bec1bba65382
git apply --check /path/to/policyServer-three-port.patch
git apply /path/to/policyServer-three-port.patch
```

Use a disposable clean clone for these commands. The hash check is for the source before applying the patch.

The candidate's `print_stats()` console panel still iterates over two logical ports. Its journal panel can therefore show only ports 0 and 1; use the CSV/JSON telemetry and Backend `ps_packet` rows to verify the three logical roles.

## Candidate helper contents

The boot preparation helper allocates 2 GB of 2 MB hugepages and binds the three data adapters. It deliberately leaves management `ens33` alone:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Management ens33 stays on the kernel driver. These three data adapters
# are the simultaneous HTTP input, TLS input, and TCP RST output.
/usr/sbin/modprobe uio
/usr/sbin/modprobe uio_pci_generic
/usr/local/bin/dpdk-hugepages.py -p 2M --setup 2G

for interface in ens192 ens224 ens256; do
    if /usr/sbin/ip link show "$interface" >/dev/null 2>&1; then
        /usr/sbin/ip link set "$interface" down
    fi
done

/usr/local/bin/dpdk-devbind.py -b uio_pci_generic \
    0000:0b:00.0 \
    0000:13:00.0 \
    0000:1b:00.0
```

The mode helper supports `all` and `status`. `all` refuses to rebind adapters while the service or Policy process is running; `status` reports PCI bindings and can be run while Policy is active:

```bash
#!/usr/bin/env bash
set -euo pipefail

HTTP_PCI="0000:0b:00.0"
TLS_PCI="0000:13:00.0"
RST_PCI="0000:1b:00.0"

if [[ $# -ne 1 ]]; then
    echo "Usage: sudo netpro-policy-mode {all|status}"
    exit 1
fi

if [[ "$1" == "status" ]]; then
    echo "Policy port layout: HTTP + TLS inputs, dedicated RST output"
    /usr/local/bin/dpdk-devbind.py -s
    exit 0
fi

if [[ "$1" != "all" ]]; then
    echo "This build uses all three data ports. Usage: sudo netpro-policy-mode {all|status}"
    exit 1
fi

if /usr/bin/systemctl is-active --quiet netpro-policy ||
   /usr/bin/pgrep -f '/build/policyServer' >/dev/null; then
    echo "ERROR: Stop netpro-policy before changing DPDK bindings."
    exit 1
fi

/usr/sbin/modprobe uio
/usr/sbin/modprobe uio_pci_generic

for interface in ens192 ens224 ens256; do
    if /usr/sbin/ip link show "$interface" >/dev/null 2>&1; then
        /usr/sbin/ip link set "$interface" down
    fi
done

/usr/local/bin/dpdk-devbind.py -b uio_pci_generic \
    "$HTTP_PCI" "$TLS_PCI" "$RST_PCI"

echo "Three-port Policy layout ready."
/usr/local/bin/dpdk-devbind.py -s
```

These helpers are installed under `/usr/local/sbin` on the VM and are included as versioned assets alongside the source. `netpro-policy.service` requires the preparation service and reads `/etc/default/netpro-policy`; the current source no longer uses `NETPRO_POLICY_MODE` to select ports, so a legacy `NETPRO_POLICY_MODE=http` value there does not change the three-port layout. No systemd unit edit is required solely for that legacy value. The post-reboot checks below verified the active services and restored bindings. Keep runtime copies, `/etc/default/netpro-policy`, and backups out of machine-independent instructions.

## Fresh VM using the source snapshot

Follow the [historical VM guide](policy-server-vm-setup.md) for Ubuntu, DPDK, VMware network, and systemd prerequisites. Use the source snapshot and helpers in this documentation repository for the current three-port application. A fresh VM does not need the local `6784d46` commit; the hash gate in the next section applies only to an incremental upgrade.

From the documentation repository root on Windows, transfer the checked-in source snapshot and helper assets to the Policy VM (confirm its SSH host key through the VM console on first use):

```powershell
scp .\assets\policy-three-port\policyServer.c netpro@192.168.31.131:/tmp/policyServer-three-port.c
scp .\assets\policy-three-port\netpro-dpdk-prepare.sh netpro@192.168.31.131:/tmp/netpro-dpdk-prepare-3port.sh
scp .\assets\policy-three-port\netpro-policy-mode netpro@192.168.31.131:/tmp/netpro-policy-mode-3port
```

On the Policy VM, compile the snapshot under a separate binary name first, then install it and the helpers:

```bash
cd ~/NetPro-Policy-Server
sudo bash -n /tmp/netpro-dpdk-prepare-3port.sh
sudo bash -n /tmp/netpro-policy-mode-3port
make APP=policyServer-three-port SRCS-pb=/tmp/policyServer-three-port.c shared
sudo systemctl stop netpro-policy
cp /tmp/policyServer-three-port.c policyServer.c
make
sudo install -m 755 /tmp/netpro-dpdk-prepare-3port.sh /usr/local/sbin/netpro-dpdk-prepare.sh
sudo install -m 755 /tmp/netpro-policy-mode-3port /usr/local/sbin/netpro-policy-mode
sudo netpro-policy-mode all
sudo systemctl start netpro-policy
systemctl is-active netpro-policy
sudo netpro-policy-mode status
```

Keep the management adapter `ens33` on its kernel driver. The copied source is a lab snapshot; review the VM-specific `config/config.cfg`, Kafka address, and SQLite path using the setup guide before expecting control-plane integration.

## In-place upgrade from the exact baseline

These steps preserve the installed source, binary, and both helpers for rollback. The documented VM already runs `e75c9f2`; do not apply the baseline patch to it. Transfer the same three assets using the PowerShell commands above. Confirm the target VM's baseline hash and revision before proceeding; if either differs, stop and inspect the source history.

On the Policy VM, confirm the original source baseline before using the checked-in source snapshot:

```bash
cd ~/NetPro-Policy-Server
git rev-parse --short HEAD
sha256sum policyServer.c
```

Expected SHA-256 for the baseline file is:

```text
72eaf6eb8dfc1ec62201970e9172b8db32dceeff0f8858b44d89bec1bba65382  policyServer.c
```

The baseline commit must be `6784d46`. If either the source hash or revision does not match, stop; this rebuild procedure is scoped to that baseline. Compile the candidate to a separate executable before stopping the service:

```bash
make APP=policyServer-three-port \
  SRCS-pb=/tmp/policyServer-three-port.c shared
ls -l build/policyServer-three-port-shared
```

Continue only if compilation succeeds. Then preserve the current source and service binary and both helpers for rollback. Existing backup names must not be overwritten:

```bash
cd ~/NetPro-Policy-Server
test ! -e policyServer.c.before-three-port
test ! -e build/policyServer-shared.before-three-port
sudo test ! -e /usr/local/sbin/netpro-dpdk-prepare.sh.before-three-port
sudo test ! -e /usr/local/sbin/netpro-policy-mode.before-three-port

cp -p policyServer.c policyServer.c.before-three-port
cp -p build/policyServer-shared build/policyServer-shared.before-three-port
sudo cp -p /usr/local/sbin/netpro-dpdk-prepare.sh /usr/local/sbin/netpro-dpdk-prepare.sh.before-three-port
sudo cp -p /usr/local/sbin/netpro-policy-mode /usr/local/sbin/netpro-policy-mode.before-three-port

sudo bash -n /tmp/netpro-dpdk-prepare-3port.sh
sudo bash -n /tmp/netpro-policy-mode-3port
sudo systemctl stop netpro-policy
cp /tmp/policyServer-three-port.c policyServer.c
make
```

Only after the build succeeds, install both helpers, bind all three ports, and start Policy:

```bash
sudo install -m 755 /tmp/netpro-dpdk-prepare-3port.sh /usr/local/sbin/netpro-dpdk-prepare.sh
sudo install -m 755 /tmp/netpro-policy-mode-3port /usr/local/sbin/netpro-policy-mode
sudo netpro-policy-mode all
sudo systemctl start netpro-policy
systemctl is-active netpro-policy
sudo netpro-policy-mode status
sudo journalctl -u netpro-policy -n 80 --no-pager
```

Confirm `netpro-policy` is active, all three data PCI devices use `uio_pci_generic`, management remains available, and the journal shows three successful PCI probes without a port-count error. Role mapping messages may be in the application log rather than the journal. The console stats panel may show only ports 0 and 1 due to the noted display limitation. Do not run the old `netpro-policy-mode http` or `tls` commands with this build.

## Validate sequential and mixed traffic

Start TRex on the Packet Generator VM in one terminal with `sudo /usr/local/sbin/netpro-trex-start` and keep it running. Before the test, record fresh NPB and Policy `MAX(packet_id)` values on the Backend VM:

```bash
PGPASSWORD=postgres psql -h 127.0.0.1 -U postgres -d test -tAc "
SELECT COALESCE((SELECT MAX(packet_id) FROM npb_packet),0) || ' ' ||
       COALESCE((SELECT MAX(packet_id) FROM ps_packet),0);"
```

In another Packet Generator terminal, run HTTP and HTTPS in sequence without changing Policy bindings, followed by the mixed test:

```bash
source ~/.profile
cd /opt/trex/v3.04/automation/trex_control_plane/interactive/trex/npb_test/npb
python3 npb_testing_http.py --sizes 256 --pps_values 1000 2000 1000
python3 npb_testing_https.py --sizes 583 --pps_values 1000 2000 1000
python3 npb_testing_http_https_udp.py --sizes 256 --pps_values 1000 2000 1000
```

For the recorded run at `2026-09-25 01:50:01` through `01:50:08 UTC`, NPB packet rows `101230`–`101237` reported about 250 HTTP and 250 TLS packets per full second. Matching Policy rows `100186`–`100193` reported about 250 packets in each input field and about 500 client-directed plus 500 server-directed resets per full second. Policy output counts were near 1,000 packets per second. These are observed counts from this test interval, not a capacity or performance guarantee.

After the mixed job finishes, allow about 70 seconds for telemetry to arrive. The following Backend PostgreSQL queries show the recorded run; replace `101229` and `100185` with the NPB and Policy IDs captured immediately before a new run:

```bash
PGPASSWORD=postgres psql -h 127.0.0.1 -U postgres -d test -c "
SELECT packet_id, time, http_count, https_count, no_match,
       rx_i_count, tx_o_http_count, tx_o_tls_count
FROM npb_packet
WHERE packet_id > 101229
  AND (http_count > 0 OR https_count > 0)
ORDER BY packet_id DESC
LIMIT 15;

SELECT packet_id, time, \"rstClient\", \"rstServer\",
       rx_i_http_count, rx_i_tls_count,
       rx_o_count, tx_o_count,
       rx_i_http_throughput, rx_i_tls_throughput
FROM ps_packet
WHERE packet_id > 100185
  AND (rx_i_http_count > 0 OR rx_i_tls_count > 0)
ORDER BY packet_id DESC
LIMIT 15;"
```

The sample interval showed both `rx_i_http_count` and `rx_i_tls_count` nonzero in the same Policy rows, with `rstClient` and `rstServer` each close to twice either single input count. This is evidence that both protocols were processed concurrently during that mixed run.

## Post-reboot acceptance

After rebooting the Policy VM on 25 September 2026, `netpro-dpdk-prepare` and `netpro-policy` both reported `active`. `dpdk-hugepages.py -s` showed 1,024 mounted 2 MB pages (2 GB). `netpro-policy-mode status` showed all three data PCI devices on `uio_pci_generic`, while management `ens33` stayed on `e1000` with `192.168.0.91/24` and `192.168.31.131/24`.

A new mixed run after that reboot produced Policy rows `101852`–`101860` at `02:19:14`–`02:19:22 UTC`, all after baseline packet ID `101778`. Each full second recorded 250 HTTP and 250 TLS inputs in the same row, 500 client and 500 server RSTs, and 1,000 output packets. These observations verify Policy startup, bindings, and concurrent traffic processing after a VM reboot. They do not constitute a powered-off cold-start test of the entire six-VM lab.

To repeat the check, reboot the Policy VM, confirm both services and the three bindings, record a new `ps_packet` baseline, run `npb_testing_http_https_udp.py` once, and query rows newer than that baseline with both `rx_i_http_count` and `rx_i_tls_count` above zero.

## Rollback

If the build, startup, or validation fails, restore the saved source, binary, and both VM helpers before restarting the previous service:

```bash
cd ~/NetPro-Policy-Server
sudo systemctl stop netpro-policy
cp -p policyServer.c.before-three-port policyServer.c
cp -p build/policyServer-shared.before-three-port build/policyServer-shared
sudo cp -p /usr/local/sbin/netpro-dpdk-prepare.sh.before-three-port /usr/local/sbin/netpro-dpdk-prepare.sh
sudo cp -p /usr/local/sbin/netpro-policy-mode.before-three-port /usr/local/sbin/netpro-policy-mode
sudo netpro-policy-mode http
sudo systemctl start netpro-policy
systemctl is-active netpro-policy
```

The restored two-port helper's `http` command returns the TLS adapter to `vmxnet3` and prepares the former HTTP-plus-RST layout.
