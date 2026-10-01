#!/usr/bin/env bash
# Update only the frontend API URL, preserving a local backup for rollback.
set -Eeuo pipefail
[[ $# == 1 && $(basename -- "$1") == .env.local ]] || { echo "Usage: $0 /path/to/frontend/.env.local" >&2; exit 2; }
[[ $(hostname -s) == frontend-vm ]] || { echo 'This script must run on frontend-vm' >&2; exit 1; }
env_file=$(realpath -- "$1")
[[ -f "$env_file" ]] || { echo "Missing $env_file" >&2; exit 1; }
[[ $(grep -Ec '^REACT_APP_BASE_URL=.*192\.168\.31\.135' "$env_file") == 1 ]] || { echo 'Expected exactly one REACT_APP_BASE_URL using 192.168.31.135' >&2; exit 1; }
sudo -S -p '' -v
backup="${env_file}.backup.$(date +%Y%m%d%H%M%S)"
sudo -n cp -p -- "$env_file" "$backup"
sudo -n sed -i '/^REACT_APP_BASE_URL=/s/192\.168\.31\.135/192.168.31.35/' "$env_file"
sudo -n chown --reference="$backup" "$env_file"
sudo -n chmod --reference="$backup" "$env_file"
grep -Eq '^REACT_APP_BASE_URL=.*192\.168\.31\.35' "$env_file" || { echo 'Updated API URL verification failed' >&2; exit 1; }
if ! sudo -n systemctl restart netpro-frontend || ! sudo -n systemctl is-active --quiet netpro-frontend; then
  echo 'Frontend restart failed; restoring the saved env file and restarting old configuration' >&2
  sudo -n cp -p -- "$backup" "$env_file"
  sudo -n systemctl restart netpro-frontend || true
  exit 1
fi
printf 'Updated REACT_APP_BASE_URL to 192.168.31.35; netpro-frontend active. Backup: %s\n' "$backup"
