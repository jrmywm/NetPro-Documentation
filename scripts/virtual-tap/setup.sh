#!/usr/bin/env bash
# Install, confirm (only after SSH verification), or roll back the isolated TAP VM.
set -Eeuo pipefail
[[ $# == 1 && $1 =~ ^(install|confirm|rollback|status)$ ]] || { echo "Usage: $0 install|confirm|rollback|status" >&2; exit 2; }
action=$1
HOST=netpro-virtual-tap
MACHINE_ID=64ff1c0225bc42f588b6afaf62654e66
STATE_DIR=/var/lib/netpro-virtual-tap
STATE=$STATE_DIR/state
NETPLAN=/etc/netplan/50-cloud-init.yaml
CLOUD_CFG=/etc/cloud/cloud.cfg.d/99-netpro-virtual-tap-disable-network.cfg
LIBEXEC=/usr/local/libexec/netpro-virtual-tap
UNIT=/etc/systemd/system/netpro-virtual-tap-mirror.service
ROLLBACK_UNIT=netpro-virtual-tap-rollback
APPLY_UNIT=netpro-virtual-tap-apply
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
[[ $EUID == 0 ]] || { echo 'Run as root' >&2; exit 1; }
[[ $(hostname -s) == "$HOST" && $(< /etc/machine-id) == "$MACHINE_ID" ]] || { echo 'VM identity guard failed' >&2; exit 1; }

rollback() {
  [[ -f $STATE ]] || { echo 'No install state to roll back' >&2; return 1; }
  source "$STATE"
  systemctl stop "$ROLLBACK_UNIT.timer" 2>/dev/null || true
  systemctl disable --now netpro-virtual-tap-mirror.service 2>/dev/null || true
  cp -p "$backup_dir/50-cloud-init.yaml" "$NETPLAN"
  rm -f "$CLOUD_CFG"
  netplan generate
  systemd-run --quiet --unit=netpro-virtual-tap-rollback-apply --collect --no-block /usr/sbin/netplan apply
  rm -f "$UNIT"
  rm -f "$LIBEXEC/mirror.sh" "$LIBEXEC/setup.sh"
  rmdir "$LIBEXEC" 2>/dev/null || true
  systemctl daemon-reload
  rm -f "$STATE" "$STATE_DIR/timer"
  rmdir "$STATE_DIR"
  echo "Rollback queued; original Netplan restored. Backup retained at $backup_dir"
}

case "$action" in
install)
  [[ ! -e $STATE_DIR && ! -e $LIBEXEC && ! -e $UNIT && ! -e $CLOUD_CFG ]] || { echo 'Owned install paths already exist; refusing' >&2; exit 1; }
  [[ -f $NETPLAN ]] || { echo 'Expected original 50-cloud-init.yaml is missing' >&2; exit 1; }
  [[ -f "$SCRIPT_DIR/netplan.yaml" && -f "$SCRIPT_DIR/mirror.sh" && -f "$SCRIPT_DIR/netpro-virtual-tap-mirror.service" && -f "$SCRIPT_DIR/cloud-init-network-disabled.cfg" ]] || { echo 'Setup assets are incomplete' >&2; exit 1; }
  [[ ! -e /run/systemd/transient/$ROLLBACK_UNIT.timer && ! -e /run/systemd/transient/$APPLY_UNIT.service ]] || { echo 'A transient install/rollback unit already exists' >&2; exit 1; }
  [[ $(< /sys/class/net/ens33/address) == 00:0c:29:da:93:08 && $(< /sys/class/net/ens34/address) == 00:0c:29:da:93:12 && $(< /sys/class/net/ens35/address) == 00:0c:29:da:93:1c && $(< /sys/class/net/ens36/address) == 00:0c:29:da:93:26 ]] || { echo 'VM adapter MAC guard failed' >&2; exit 1; }
  arping -D -I ens33 -c 3 -w 4 192.168.31.38 || { echo 'Static address DAD failed; refusing' >&2; exit 1; }
  for file in "$SCRIPT_DIR/setup.sh" "$SCRIPT_DIR/mirror.sh"; do bash -n "$file"; done
  backup_dir=$(mktemp -d /var/tmp/netpro-virtual-tap.XXXXXX)
  chmod 700 "$backup_dir"
  cp -p "$NETPLAN" "$backup_dir/50-cloud-init.yaml"
  mkdir -p "$backup_dir/candidate/etc/netplan"
  install -m 0600 "$SCRIPT_DIR/netplan.yaml" "$backup_dir/candidate/etc/netplan/50-cloud-init.yaml"
  netplan generate --root-dir "$backup_dir/candidate"
  install -d -m 0700 "$STATE_DIR"
  printf 'backup_dir=%q\n' "$backup_dir" > "$STATE"
  chmod 600 "$STATE"
  failed_install() { rc=$?; trap - ERR; rollback || echo 'Automatic rollback failed; retained state and backup' >&2; exit "$rc"; }
  trap failed_install ERR
  install -d -m 0755 "$LIBEXEC"
  install -m 0755 "$SCRIPT_DIR/mirror.sh" "$LIBEXEC/mirror.sh"
  install -m 0755 "$SCRIPT_DIR/setup.sh" "$LIBEXEC/setup.sh"
  install -m 0644 "$SCRIPT_DIR/netpro-virtual-tap-mirror.service" "$UNIT"
  install -m 0600 "$SCRIPT_DIR/cloud-init-network-disabled.cfg" "$CLOUD_CFG"
  install -m 0600 "$SCRIPT_DIR/netplan.yaml" "$NETPLAN"
  printf '%s\n' "$ROLLBACK_UNIT" > "$STATE_DIR/timer"
  systemd-run --quiet --unit="$ROLLBACK_UNIT" --on-active=3m /bin/bash "$LIBEXEC/setup.sh" rollback
  systemctl daemon-reload
  systemctl enable netpro-virtual-tap-mirror.service
  netplan generate
  systemd-run --quiet --unit="$APPLY_UNIT" --collect --no-block /bin/bash -c '/usr/sbin/netplan apply && /usr/bin/systemctl start netpro-virtual-tap-mirror.service'
  trap - ERR
  echo 'Install queued via systemd. Verify a new SSH session on 192.168.31.38, then run: NETPRO_STATIC_SSH_VERIFIED=1 /usr/local/libexec/netpro-virtual-tap/setup.sh confirm. Otherwise rollback starts automatically in 3 minutes.'
  echo "Backup: $backup_dir"
  ;;
confirm)
  [[ -f $STATE ]] || { echo 'No install state to confirm' >&2; exit 1; }
  [[ ${NETPRO_STATIC_SSH_VERIFIED:-} == 1 ]] || { echo 'First verify a new SSH session on 192.168.31.38, then set NETPRO_STATIC_SSH_VERIFIED=1 for this command.' >&2; exit 1; }
  ip -4 -o addr show dev ens33 | grep -Fq '192.168.31.38/24' || { echo 'ens33 does not have the expected static address; rollback remains armed' >&2; exit 1; }
  [[ $(systemctl is-active netpro-virtual-tap-mirror.service 2>/dev/null || true) == active ]] || { echo 'Mirror service is not active; rollback remains armed' >&2; exit 1; }
  systemctl stop "$ROLLBACK_UNIT.timer"
  rm -f "$STATE_DIR/timer"
  echo 'Rollback timer canceled; backup retained. Static SSH verification acknowledged.'
  ;;
rollback) rollback ;;
status)
  printf 'state=%s mirror_service=%s rollback_timer=%s\n' "$( [[ -f $STATE ]] && echo installed || echo absent )" "$(systemctl is-active netpro-virtual-tap-mirror.service 2>/dev/null || true)" "$(systemctl is-active "$ROLLBACK_UNIT.timer" 2>/dev/null || true)"
  ip -br address show dev ens33
  ip -br link show dev br-tap
  for dev in ens34 ens35 ens36; do ip -br link show dev "$dev"; done
  ;;
esac
