#!/usr/bin/env bash
# Manage only the temporary OpenSSL listener used for the server-directed RST proof.
set -Eeuo pipefail
[[ $# == 1 && ( "$1" == start || "$1" == status || "$1" == stop ) ]] || { echo "Usage: $0 start|status|stop" >&2; exit 2; }
[[ $EUID == 0 ]] || { echo 'Run as root (sudo bash server.sh ...)' >&2; exit 1; }
[[ $(hostname -s) == backend-vm && $(< /sys/class/net/ens33/address) == 00:0c:29:92:1c:d1 ]] || { echo 'Backend hostname/MAC guard failed' >&2; exit 1; }
ip -4 -o addr show dev ens33 | grep -Fq '192.168.31.35/24' || { echo 'Backend ens33 address guard failed' >&2; exit 1; }
unit=netpro-server-rst-proof-listener
state=/run/netpro-server-rst-proof.state
case "$1" in
 start)
  [[ ! -e "$state" ]] || { echo "State already exists: $state" >&2; exit 1; }
  [[ $(systemctl show -p LoadState --value "$unit.service") == not-found ]] || { echo "Refusing pre-existing unit $unit.service" >&2; exit 1; }
  if ss -H -ltn | awk '$4 ~ /:8443$/ {found=1} END {exit !found}'; then echo 'TCP port 8443 already has a listener' >&2; exit 1; fi
  dir=$(mktemp -d /tmp/netpro-server-rst-proof.XXXXXX)
  rollback() { rc=$?; trap - ERR; systemctl stop "$unit.service" >/dev/null 2>&1 || true; rm -f "$state"; echo "Listener start failed; evidence directory retained: $dir" >&2; exit "$rc"; }
  trap rollback ERR
  openssl req -x509 -newkey rsa:2048 -nodes -days 1 -keyout "$dir/server.key" -out "$dir/server.crt" -subj '/CN=netpro-server-proof.test' >/dev/null 2>&1
  chmod 0600 "$dir/server.key"
  printf '%s\n' "$dir" >"$state"
  systemd-run --quiet --unit="$unit" --collect --property=RuntimeMaxSec=600s \
    /usr/bin/openssl s_server -accept 192.168.31.35:8443 -cert "$dir/server.crt" \
    -key "$dir/server.key" -www -state -tls1_2
  for _ in $(seq 1 5); do systemctl is-active --quiet "$unit.service" && break; sleep 1; done
  systemctl is-active --quiet "$unit.service" || { echo 'OpenSSL listener did not become active' >&2; false; }
  trap - ERR
  printf 'Listener active: %s on 192.168.31.35:8443\nCertificate/evidence directory: %s\n' "$unit.service" "$dir"
  ;;
 status)
  if [[ -f "$state" ]]; then printf 'state_dir=%s\n' "$(< "$state")"; else echo 'state=absent'; fi
  systemctl is-active "$unit.service" || true
  ss -H -ltn | awk '$4 ~ /:8443$/ {print "listener=" $4}'
  ;;
 stop)
  [[ -f "$state" ]] || { echo 'No owned listener state; refusing broad process cleanup' >&2; exit 1; }
  dir=$(< "$state")
  if [[ $(systemctl show -p LoadState --value "$unit.service") != not-found ]]; then
    systemctl stop "$unit.service"
  else
    echo "Unit $unit.service was already auto-collected; clearing its owned state"
  fi
  rm -f "$state"
  printf 'Stopped only %s.service; retained evidence directory: %s\n' "$unit" "$dir"
  ;;
esac
