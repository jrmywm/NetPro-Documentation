#!/usr/bin/env bash
# Send one fresh pinned Google HTTPS phase over the isolated lab route.
set -Eeuo pipefail
[[ $# == 2 ]] || { echo "Usage: $0 PINNED_IPV4 PHASE" >&2; exit 2; }
ip=$1; phase=$2
python3 -c 'import ipaddress,sys; a=ipaddress.ip_address(sys.argv[1]); sys.exit(0 if a.version == 4 else 1)' "$ip" || { echo 'Pinned address must be IPv4' >&2; exit 2; }
[[ "$phase" =~ ^[A-Za-z0-9._-]+$ ]] || { echo 'Invalid phase label' >&2; exit 2; }
[[ $(hostname -s) == netpro-test-client && $(< /sys/class/net/ens37/address) == 00:0c:29:91:39:14 ]] || { echo 'Client hostname/MAC guard failed' >&2; exit 1; }
sudo -S -p '' -v
start_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
route=$(ip -4 route show exact "$ip/32")
created=0
if [[ -z "$route" ]]; then
  sudo -n ip route add "$ip/32" via 192.168.80.28 dev ens37
  created=1
elif ! grep -Fq "$ip via 192.168.80.28 dev ens37" <<<"$route"; then
  echo "Conflicting exact route exists: $route" >&2; exit 1
fi
cleanup_route() { if (( created )); then sudo -n ip route del "$ip/32" via 192.168.80.28 dev ens37 || echo "Could not remove created route: $ip/32" >&2; fi; }
trap cleanup_route EXIT
printf 'phase=%s route=%s\n' "$phase" "$(ip -4 route show exact "$ip/32")"
printf 'start_utc=%s\n' "$start_utc"
set +e
curl -4 --http1.1 --noproxy '*' --interface 192.168.80.29 \
  --resolve "www.google.com:443:$ip" --connect-timeout 6 --max-time 20 \
  --silent --show-error --output /dev/null \
  --write-out 'http_code=%{http_code} remote_ip=%{remote_ip} total_seconds=%{time_total}\n' \
  "https://www.google.com/?netpro_phase=$phase"
rc=$?
set -e
printf 'end_utc=%s phase=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$phase"
printf 'curl_exit=%s\n' "$rc"
exit "$rc"
