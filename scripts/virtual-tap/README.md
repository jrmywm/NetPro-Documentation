# Virtual TAP helper bundle

These identity-guarded scripts and configuration files install and manage the `netpro-virtual-tap` Ubuntu VM's software mirror bridge. Review before use; run setup actions as root on that VM only. The install uses a three-minute automatic rollback, canceled only after confirming a fresh SSH connection at `192.168.31.38` and an active mirror service. The retained original Netplan backup is `/var/tmp/netpro-virtual-tap.GwWPvi`; manual rollback is `/usr/local/libexec/netpro-virtual-tap/setup.sh rollback`. The bridge mirrors ingress copies from `ens34`/`ens35` to monitor `ens36`; ingress arriving on `ens36` is dropped.

The bridge is not a physical TAP and is not fail-open: VM shutdown breaks the bridged datapath. Isolated namespace smoke results do not establish end-to-end client/NPB traffic; VMware wiring and that acceptance test remain pending. Captured output is in [`evidence/virtual-tap`](../../evidence/virtual-tap/).
