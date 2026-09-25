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
