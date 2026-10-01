# Static network migration helpers

These scripts preserve the environment-specific host and MAC checks used for the 2 October 2026 migration. They are one-time migration helpers, not repeatable setup commands. Do not rerun after successful migration; inspect live VM configuration and backups before any recovery use. No VM reboot validation is recorded yet.

Run on the matching VM with the corresponding role argument:

| Script | Where to run | Role argument |
| --- | --- | --- |
| `configure-static.sh` | Gateway / Client | `gateway` / `client` |
| `configure-lab-static.sh` | Six core service VMs | `policy`, `kafka`, `npb`, `generator`, `backend`, `frontend` |
| `frontendenvmigration.sh` | Frontend VM | Absolute path to `.env.local` |

Both network scripts verify the expected hostname, MAC address, active `systemd-networkd`, and expected netplan file set before editing, and schedule a 180-second rollback. `configure-static.sh` does not check DHCP state. `configure-lab-static.sh` additionally verifies that `ens33` has the expected static service-control address while DHCPv4 is enabled; that guard prevents rerunning it after migration. The Frontend helper accepts only the prior Backend URL at `192.168.31.135`, backs up `.env.local`, changes it to `192.168.31.35`, and restarts `netpro-frontend` with rollback on failure. Its old-URL guard prevents rerunning it after migration.

The Gateway/Client helper configures the `ens33` NAT address and `ens37` lab-link address. The six-service helper changes `ens33` while preserving each VM's existing `192.168.0.90`–`.95` service-control address. Results and backup locations are in [the static addressing record](../../docs/static-addressing-2026-10-02.md).
