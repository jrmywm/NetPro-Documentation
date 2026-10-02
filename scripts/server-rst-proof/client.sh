#!/usr/bin/env bash
# Send one pinned TLS 1.2 request over the client lab route and report its result.
set -Eeuo pipefail
[[ $# == 1 && "$1" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "Usage: $0 PHASE_LABEL" >&2; exit 2; }
phase=$1
[[ $(hostname -s) == netpro-test-client && $(< /sys/class/net/ens37/address) == 00:0c:29:91:39:14 ]] || { echo 'Client hostname/MAC guard failed' >&2; exit 1; }
ip -4 -o addr show dev ens37 | grep -Fq '192.168.80.29/24' || { echo 'Client ens37 address guard failed' >&2; exit 1; }
sudo -S -p '' -v
target=192.168.31.35
route=$(ip -4 route show exact "$target/32")
[[ -z "$route" ]] || { echo "Refusing pre-existing host route: $route" >&2; exit 1; }
sudo -n ip route add "$target/32" via 192.168.80.28 dev ens37 src 192.168.80.29
route_created=1
cleanup_route() { if (( route_created )); then sudo -n ip route del "$target/32" via 192.168.80.28 dev ens37 || echo "Could not remove created route $target/32" >&2; fi; }
trap cleanup_route EXIT
start_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
printf 'phase=%s start_utc=%s route=%s\n' "$phase" "$start_utc" "$(ip -4 route show exact "$target/32")"
set +e
curl -4 --interface 192.168.80.29 --noproxy '*' --http1.1 --tlsv1.2 --tls-max 1.2 \
  --resolve "netpro-server-proof.test:8443:$target" -k -sS -o /dev/null \
  --connect-timeout 5 --max-time 15 \
  --write-out 'http_status=%{http_code} remote_ip=%{remote_ip} total_seconds=%{time_total}\n' \
  "https://netpro-server-proof.test:8443/?phase=$phase"
curl_status=$?
set -e
printf 'phase=%s end_utc=%s curl_exit=%s\n' "$phase" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$curl_status"
exit "$curl_status"
