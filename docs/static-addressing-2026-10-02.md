# Static addressing audit and migration — 2 October 2026

## Confirmed baseline

- The six core NetPro VMs (Policy, Kafka, NPB, Packet Generator, Backend, Frontend) have unique machine IDs. Their existing static control addresses `192.168.0.90`–`192.168.0.95` are preserved.
- Gateway and Client addresses are static: Gateway NAT address `192.168.31.37/24` and Client NAT address `192.168.31.39/24` are on `ens33`; Gateway lab-link address `192.168.80.28/24` and Client lab-link address `192.168.80.29/24` are on `ens37`. Both use `192.168.31.2` as default gateway and DNS on `ens33` only. Internet ping/DNS checks passed on both and Gateway-to-Client ping succeeded. These settings have not been reboot-tested.
- The Gateway and Client pair still report duplicate Linux machine-id `cf5c76ab092042a6b98fa7ee449eb8e7` despite different MAC addresses. This is separate from the six core VM identity check above.
- VMnet8/VMnet1 DHCP pools remain unchanged at `.128`–`.254`.

## Applied NAT-side static addresses

| VM | Applied address |
| --- | --- |
| Policy Server | `192.168.31.31/24` |
| Kafka Broker | `192.168.31.32/24` |
| NPB | `192.168.31.33/24` |
| Packet Generator | `192.168.31.34/24` |
| Backend | `192.168.31.35/24` |
| Frontend | `192.168.31.36/24` |

All six addresses were applied as planned. Internet ping and DNS checks passed on all six VMs. `netpro-policy`, `netpro-npb`, `netpro-kafka`, `netpro-backend`, `postgresql`, and `netpro-frontend` are active. Packet Generator TRex remains stopped, matching its baseline state. Static routes were confirmed and no rollback timers remain. The service VMs' existing `192.168.0.90`–`192.168.0.95` control addresses remain intact.

Frontend `.env.local` now uses Backend API `https://192.168.31.35:3000`; its backup is `/home/netpro/NetPro-Frontend/.env.local.backup.20261001173350`. Only Frontend was restarted for this change. Windows-host HTTP 200 checks passed for dashboard `https://192.168.31.36:3005` and API endpoint `https://192.168.31.35:3000/npb/npbs`; the served Frontend JavaScript bundle contains the new Backend URL. Backend's preserved control endpoint `https://192.168.0.94:3000` remains available. Backend-to-control-address pings to `.90`, `.91`, `.92`, `.93`, and `.95` passed. No VM reboot was performed.

Backups for the six service-VM migrations are under `/var/tmp/netpro-lab-static.*`: Policy `kDHxt7`, Kafka `cPt47T`, NPB `EKzgVI`, Packet Generator `PdvfcS`, Backend `sOhmAn`, and Frontend `q7SxfH`. The Gateway backup is `/var/tmp/netpro-static.3u3z9r`; the original Client backup is `/var/tmp/netpro-static.9GqRLs` (a second duplicate Client backup is `lRsxfk`). The `.31`–`.37` and `.39` addresses are outside the unchanged `.128`–`.254` DHCP pools. Old proxy and test references may still need updating before use. See the [engineering checkpoint](engineering-checkpoint-2026-10-01.md) for earlier Gateway/Client connectivity evidence.

The checked-in, environment-specific helpers and role arguments are listed in [`scripts/static-network/README.md`](../scripts/static-network/README.md). `configure-lab-static.sh` verifies the expected old service address with DHCP enabled, so it refuses a rerun after migration. The Frontend helper likewise requires the prior `.135` API URL. Reboot persistence has not yet been verified.
