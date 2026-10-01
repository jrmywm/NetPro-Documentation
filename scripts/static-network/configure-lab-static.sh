#!/usr/bin/env bash
# Add lab NAT reachability while preserving the existing service address.
set -Eeuo pipefail
[[ $# == 1 ]] || { echo "Usage: $0 policy|npb|generator|backend|frontend|kafka" >&2; exit 2; }
case "$1" in
 policy) role=policy; host=policy-server-vm; mac=00:0c:29:7a:35:1a; nat=192.168.31.31; service=192.168.0.91; base=00-installer-config.yaml; expected_files=(00-installer-config.yaml 99-netpro-control.yaml); add_service=0 ;;
 npb) role=npb; host=npb-vm; mac=00:0c:29:ba:d7:50; nat=192.168.31.33; service=192.168.0.92; base=00-installer-config.yaml; expected_files=(00-installer-config.yaml); add_service=1 ;;
 generator) role=generator; host=packet-generator-vm; mac=00:0c:29:c5:4f:de; nat=192.168.31.34; service=192.168.0.93; base=00-installer-config.yaml; expected_files=(00-installer-config.yaml); add_service=1 ;;
 backend) role=backend; host=backend-vm; mac=00:0c:29:92:1c:d1; nat=192.168.31.35; service=192.168.0.94; base=50-cloud-init.yaml; expected_files=(50-cloud-init.yaml 99-netpro-control.yaml); add_service=0 ;;
 frontend) role=frontend; host=frontend-vm; mac=00:0c:29:de:81:07; nat=192.168.31.36; service=192.168.0.95; base=50-cloud-init.yaml; expected_files=(50-cloud-init.yaml 99-netpro-lab.yaml); add_service=0 ;;
 kafka) role=kafka; host=kafka-broker-vm; mac=00:0c:29:4b:e8:38; nat=192.168.31.32; service=192.168.0.90; base=50-cloud-init.yaml; expected_files=(50-cloud-init.yaml 99-netpro-control.yaml); add_service=0 ;;
 *) echo "Unsupported role: $1" >&2; exit 2 ;;
esac

exec 9>/tmp/netpro-lab-static.lock
flock -n 9 || { echo 'Concurrent lab network change refused' >&2; exit 1; }
[[ $(hostname -s) == "$host" ]] || { echo "Wrong hostname; expected $host" >&2; exit 1; }
[[ -r /sys/class/net/ens33/address && $(< /sys/class/net/ens33/address) == "$mac" ]] || { echo 'ens33 MAC mismatch' >&2; exit 1; }
systemctl is-active --quiet systemd-networkd || { echo 'systemd-networkd inactive' >&2; exit 1; }
mapfile -t actual_files < <(find /etc/netplan -maxdepth 1 -type f \( -name '*.yaml' -o -name '*.yml' \) -printf '%f\n' | sort)
mapfile -t expected_files < <(printf '%s\n' "${expected_files[@]}" | sort)
[[ "${actual_files[*]}" == "${expected_files[*]}" ]] || { echo "Unexpected netplan files: ${actual_files[*]:-none}" >&2; exit 1; }
netplan=$(command -v netplan) || { echo 'netplan executable not on PATH' >&2; exit 1; }
sudo -S -p '' -v
validate_ens33() {
  sudo -n "$netplan" get ethernets.ens33 | python3 -c '
import sys, yaml
cfg = yaml.safe_load(sys.stdin) or {}
expected4, expected6 = sys.argv[1:3]
expected = sorted(sys.argv[3:])
actual = sorted(cfg.get("addresses") or [])
if actual != expected or str(cfg.get("dhcp4", "")).lower() != expected4 or (expected6 != "any" and str(cfg.get("dhcp6", "")).lower() != expected6):
    print("ens33 mismatch: addresses={} dhcp4={} dhcp6={}".format(actual, cfg.get("dhcp4"), cfg.get("dhcp6")), file=sys.stderr)
    raise SystemExit(1)
' "$1" "$2" "${@:3}"
}
validate_ens33 true any "$service/24" || { echo "Expected only $service/24 with DHCP enabled before change" >&2; exit 1; }

backup=$(sudo -n mktemp -d /var/tmp/netpro-lab-static.XXXXXX)
sudo -n cp -a "/etc/netplan/$base" "$backup/$base.original"
if sudo -n test -e /etc/cloud/cloud.cfg.d/99-netpro-disable-network-config.cfg; then
  sudo -n cp -a /etc/cloud/cloud.cfg.d/99-netpro-disable-network-config.cfg "$backup/cloud-init-network.original"
  cloud_existed=1
else cloud_existed=0; fi
rollback="$backup/rollback.sh"
sudo -n tee "$rollback" >/dev/null <<EOF
#!/usr/bin/env bash
set -e
cp -a '$backup/$base.original' '/etc/netplan/$base'
if [[ $cloud_existed == 1 ]]; then cp -a '$backup/cloud-init-network.original' /etc/cloud/cloud.cfg.d/99-netpro-disable-network-config.cfg; else rm -f /etc/cloud/cloud.cfg.d/99-netpro-disable-network-config.cfg; fi
'$netplan' apply
EOF
sudo -n chmod 0700 "$rollback"
rollback_unit="netpro-lab-static-rollback-$(date +%s)-$$"
sudo -n systemd-run --quiet --unit="$rollback_unit" --on-active=180s /bin/bash "$rollback"
printf 'Backup: %s\nScheduled rollback: %s.timer (180 seconds)\n' "$backup" "$rollback_unit"

edited=0
on_error() {
  rc=$?; trap - ERR
  if (( edited )); then
    if sudo -n /bin/bash "$rollback"; then
      sudo -n systemctl stop "$rollback_unit.timer" >/dev/null 2>&1 || echo "Config restored; timer may still run: $rollback_unit.timer" >&2
    else
      echo "Immediate rollback failed; scheduled rollback remains: $rollback_unit.timer" >&2
    fi
  fi
  exit "$rc"
}
trap on_error ERR
edited=1
if (( add_service )); then addresses="$nat/24, $service/24"; else addresses="$nat/24"; fi
sudo -n tee "/etc/netplan/$base" >/dev/null <<EOF
network:
  version: 2
  renderer: networkd
  ethernets:
    ens33:
      dhcp4: false
      dhcp6: false
      addresses: [$addresses]
      routes:
        - to: 0.0.0.0/0
          via: 192.168.31.2
      nameservers:
        addresses: [192.168.31.2]
EOF
sudo -n install -d -o root -g root -m 0755 /etc/cloud/cloud.cfg.d
sudo -n tee /etc/cloud/cloud.cfg.d/99-netpro-disable-network-config.cfg >/dev/null <<'EOF'
network: {config: disabled}
EOF
sudo -n "$netplan" generate
validate_ens33 false false "$nat/24" "$service/24" || { echo 'Generated config address/DHCP validation failed' >&2; false; }
apply_unit="netpro-lab-static-apply-$(date +%s)-$$"
sudo -n systemd-run --quiet --unit="$apply_unit" --on-active=2s "$netplan" apply
trap - ERR
printf 'Validated; apply scheduled in 2 seconds. Host=%s ens33=%s/24 service=%s/24 via/DNS=192.168.31.2 apply=%s.service\n' "$host" "$nat" "$service" "$apply_unit"
