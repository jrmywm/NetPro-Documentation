#!/usr/bin/env bash
# Temporary HTTP/TLS endpoints for the isolated TAP independence check.
set -Eeuo pipefail
[[ $# == 1 && ( $1 == start || $1 == stop ) ]] || { echo "Usage: $0 start|stop" >&2; exit 2; }
[[ $EUID == 0 ]] || { echo 'Run as root' >&2; exit 1; }
[[ $(hostname -s) == netpro-test-gateway && $(< /sys/class/net/ens37/address) == 00:0c:29:34:73:cc ]] || { echo 'Gateway hostname/MAC guard failed' >&2; exit 1; }
ip -4 -o addr show dev ens37 | grep -Fq '192.168.80.28/24' || { echo 'Gateway ens37 address guard failed' >&2; exit 1; }
state=/run/netpro-tap-live-test
http=netpro-tap-live-http; tls=netpro-tap-live-tls
unit_present() { [[ $(systemctl show -p LoadState --value "$1.service") != not-found ]]; }
case "$1" in
 start)
  [[ ! -e "$state" ]] || { echo "Refusing existing state $state" >&2; exit 1; }
  ! unit_present "$http" && ! unit_present "$tls" || { echo 'Refusing pre-existing test unit' >&2; exit 1; }
  if ss -H -ltn | awk '$4 ~ /:(8080|8443)$/ {found=1} END {exit !found}'; then echo 'TCP port 8080 or 8443 is already listening' >&2; exit 1; fi
  dir=$(mktemp -d /tmp/netpro-tap-live.XXXXXX); chmod 0700 "$dir"; mkdir -m 0700 "$dir/web"
  rollback() { rc=$?; trap - ERR; systemctl stop "$http.service" "$tls.service" >/dev/null 2>&1 || true; rm -f "$state"; echo "Start failed; retained evidence: $dir" >&2; exit "$rc"; }
  trap rollback ERR
  install -o root -g root -m 0644 "$(dirname "$0")/index.html" "$dir/web/index.html"
  openssl req -x509 -newkey rsa:2048 -nodes -days 1 -keyout "$dir/server.key" -out "$dir/server.crt" -subj '/CN=netpro-tap.test' >/dev/null 2>&1
  chmod 0600 "$dir/server.key" "$dir/server.crt"
  printf '%s\n' "$dir" >"$state"; chmod 0600 "$state"
  systemd-run --quiet --unit="$http" --collect --property=RuntimeMaxSec=600s /usr/bin/python3 -m http.server 8080 --bind 192.168.80.28 --directory "$dir/web"
  systemd-run --quiet --unit="$tls" --collect --property=RuntimeMaxSec=600s /usr/bin/openssl s_server -accept 192.168.80.28:8443 -cert "$dir/server.crt" -key "$dir/server.key" -www -tls1_2
  for _ in $(seq 1 5); do systemctl is-active --quiet "$http.service" && systemctl is-active --quiet "$tls.service" && break; sleep 1; done
  systemctl is-active --quiet "$http.service"; systemctl is-active --quiet "$tls.service"
  trap - ERR
  printf 'HTTP and TLS test listeners active on 192.168.80.28:8080/8443\nEvidence directory: %s\n' "$dir"
  ;;
 stop)
  [[ -f "$state" ]] || { echo 'No owned test state; refusing broad process cleanup' >&2; exit 1; }
  dir=$(< "$state")
  for u in "$http" "$tls"; do if unit_present "$u"; then systemctl stop "$u.service"; else echo "$u.service already auto-collected"; fi; done
  rm -f "$state"
  printf 'Stopped only named test units; retained evidence directory: %s\n' "$dir"
  ;;
esac
