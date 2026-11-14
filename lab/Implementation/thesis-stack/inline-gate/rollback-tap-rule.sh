#!/usr/bin/env bash
set -euo pipefail

TABLE=netpro_quic_gate
UNIT=netpro-quic-gate-rollback

if [[ $(id -u) -ne 0 ]]; then
  echo "Run as root on the TAP." >&2
  exit 1
fi
if nft list table bridge "$TABLE" >/dev/null 2>&1; then
  nft delete table bridge "$TABLE"
fi
systemctl stop "$UNIT.timer" "$UNIT.service" >/dev/null 2>&1 || true
echo "Removed only the owned bridge table and its rollback timer."
