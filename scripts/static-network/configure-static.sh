#!/usr/bin/env bash
# Static ens33/ens37 config with an automatic 180-second rollback.
set -Eeuo pipefail
[[ $# == 1 && ( "$1" == gateway || "$1" == client ) ]] || { echo "Usage: $0 gateway|client" >&2; exit 2; }
role=$1
if [[ "$role" == gateway ]]; then
  host=netpro-test-gateway; mac33=00:0c:29:34:73:c2; mac37=00:0c:29:34:73:cc
  nat_ip=192.168.31.37; test_ip=192.168.80.28
else
  host=netpro-test-client; mac33=00:0c:29:91:39:0a; mac37=00:0c:29:91:39:14
  nat_ip=192.168.31.39; test_ip=192.168.80.29
fi
[[ $(hostname -s) == "$host" ]] || { echo "Wrong hostname; expected $host" >&2; exit 1; }
[[ $(< /sys/class/net/ens33/address) == "$mac33" ]] || { echo 'ens33 MAC mismatch' >&2; exit 1; }
[[ $(< /sys/class/net/ens37/address) == "$mac37" ]] || { echo 'ens37 MAC mismatch' >&2; exit 1; }
systemctl is-active --quiet systemd-networkd || { echo 'systemd-networkd is not active' >&2; exit 1; }
mapfile -t yml < <(find /etc/netplan -maxdepth 1 -type f \( -name '*.yaml' -o -name '*.yml' \) -printf '%f\n')
[[ ${#yml[@]} == 1 && ${yml[0]} == 50-cloud-init.yaml ]] || { echo "Unexpected /etc/netplan YAML files: ${yml[*]:-none}" >&2; exit 1; }
netplan=$(command -v netplan) || { echo 'netplan not on PATH' >&2; exit 1; }
sudo -S -p '' -v
backup=$(sudo -n mktemp -d /var/tmp/netpro-static.XXXXXX)
sudo -n cp -a /etc/netplan/50-cloud-init.yaml "$backup/50-cloud-init.yaml.original"
if sudo -n test -e /etc/cloud/cloud.cfg.d/99-netpro-disable-network-config.cfg; then
  sudo -n cp -a /etc/cloud/cloud.cfg.d/99-netpro-disable-network-config.cfg "$backup/cloud-init-network.original"
  cloud_existed=1
else cloud_existed=0; fi
rollback="$backup/rollback.sh"
sudo -n tee "$rollback" >/dev/null <<EOF
#!/usr/bin/env bash
set -e
cp -a '$backup/50-cloud-init.yaml.original' /etc/netplan/50-cloud-init.yaml
if [[ $cloud_existed == 1 ]]; then cp -a '$backup/cloud-init-network.original' /etc/cloud/cloud.cfg.d/99-netpro-disable-network-config.cfg; else rm -f /etc/cloud/cloud.cfg.d/99-netpro-disable-network-config.cfg; fi
'$netplan' apply
EOF
sudo -n chmod 0700 "$rollback"
rollback_unit="netpro-static-rollback-$(date +%s)-$$"
sudo -n systemd-run --quiet --unit="$rollback_unit" --on-active=180s /bin/bash "$rollback"
edited=0
on_error() {
  rc=$?; trap - ERR
  if (( edited )); then
    sudo -n systemctl stop "$rollback_unit.timer" >/dev/null 2>&1 || true
    if sudo -n /bin/bash "$rollback"; then echo 'Validation failed; original network config restored' >&2; else echo "ROLLBACK FAILED; scheduled timer: $rollback_unit.timer" >&2; fi
  fi
  exit "$rc"
}
trap on_error ERR
edited=1
sudo -n tee /etc/netplan/50-cloud-init.yaml >/dev/null <<EOF
network:
  version: 2
  renderer: networkd
  ethernets:
    ens33:
      dhcp4: false
      dhcp6: false
      addresses: [$nat_ip/24]
      routes:
        - to: 0.0.0.0/0
          via: 192.168.31.2
      nameservers:
        addresses: [192.168.31.2]
    ens37:
      dhcp4: false
      dhcp6: false
      addresses: [$test_ip/24]
EOF
sudo -n install -d -o root -g root -m 0755 /etc/cloud/cloud.cfg.d
sudo -n tee /etc/cloud/cloud.cfg.d/99-netpro-disable-network-config.cfg >/dev/null <<'EOF'
network: {config: disabled}
EOF
sudo -n "$netplan" generate
apply_unit="netpro-static-apply-$(date +%s)-$$"
sudo -n systemd-run --quiet --unit="$apply_unit" --on-active=2s "$netplan" apply
trap - ERR
printf 'Validated; apply in 2 seconds. Backup: %s\nRollback timer: %s.timer (180 seconds)\nApply unit: %s.service\nNAT ens33: %s/24 via 192.168.31.2, DNS 192.168.31.2\nTest ens37: %s/24\n' "$backup" "$rollback_unit" "$apply_unit" "$nat_ip" "$test_ip"
