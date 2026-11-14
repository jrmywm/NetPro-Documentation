#!/usr/bin/env bash
set -euo pipefail

TABLE=netpro_quic_gate
UNIT=netpro-quic-gate-rollback
QUEUE=4242

if [[ $(id -u) -ne 0 ]]; then
  echo "Run as root on the TAP." >&2
  exit 1
fi
if nft list table bridge "$TABLE" >/dev/null 2>&1; then
  echo "Refusing to replace existing bridge table $TABLE." >&2
  exit 1
fi
if systemctl is-active --quiet "$UNIT.timer" || systemctl is-active --quiet "$UNIT.service"; then
  echo "Refusing because the owned rollback unit already exists." >&2
  exit 1
fi

cleanup_failed_stage() {
  nft delete table bridge "$TABLE" >/dev/null 2>&1 || true
  systemctl stop "$UNIT.timer" "$UNIT.service" >/dev/null 2>&1 || true
}
trap cleanup_failed_stage ERR

# Arm rollback before touching modules or creating the bridge hook. If SSH is
# lost during the following commands, this timer removes only our table.
systemd-run --quiet --collect --unit="$UNIT" --on-active=20m --timer-property=AccuracySec=1s \
  /bin/sh -c 'if /usr/sbin/nft list table bridge netpro_quic_gate >/dev/null 2>&1; then /usr/sbin/nft delete table bridge netpro_quic_gate; fi'
modprobe nfnetlink_queue
modprobe nft_queue
nft add table bridge "$TABLE"
nft add chain bridge "$TABLE" forward '{ type filter hook forward priority filter; policy accept; }'
# Non-initial IPv4 fragments have no visible UDP port. Drop only fragments
# between the selected lab endpoints so they cannot bypass the UDP/443 queue.
nft add rule bridge "$TABLE" forward ip saddr 192.168.80.29 ip daddr 192.168.80.28 ip protocol udp 'ip frag-off' '&' 0x3fff '!=' 0 counter drop
# Queue only client-to-origin UDP/443. The gate passes non-QUIC UDP payloads.
nft add rule bridge "$TABLE" forward ip saddr 192.168.80.29 ip daddr 192.168.80.28 udp dport 443 counter queue num "$QUEUE"
trap - ERR
echo "Staged $TABLE; automatic rollback scheduled in 20 minutes."
echo "Gate process must be ready before any test traffic is sent."
