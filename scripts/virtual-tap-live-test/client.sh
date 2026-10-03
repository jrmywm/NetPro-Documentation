#!/usr/bin/env bash
# Four pinned client requests; no route, interface, or offload changes.
set -u
[[ $# == 1 && ( $1 == on-before || $1 == monitor-off || $1 == on-after ) ]] || { echo "Usage: $0 on-before|monitor-off|on-after" >&2; exit 2; }
[[ $(hostname -s) == netpro-test-client && $(< /sys/class/net/ens37/address) == 00:0c:29:91:39:14 ]] || { echo 'Client hostname/MAC guard failed' >&2; exit 1; }
ip -4 -o addr show dev ens37 | grep -Fq '192.168.80.29/24' || { echo 'Client ens37 address guard failed' >&2; exit 1; }
phase=$1; start=$(date -u '+%Y-%m-%dT%H:%M:%SZ'); failed=0
request() {
  scheme=$1; url=$2; shift 2
  result=$(curl --interface 192.168.80.29 --noproxy '*' --silent --show-error --output /dev/null --connect-timeout 5 --max-time 15 "$@" --write-out 'http=%{http_code} remote=%{remote_ip} seconds=%{time_total}' "$url" 2>&1); rc=$?
  printf 'phase=%s attempt=%s time=%s protocol=%s %s curl_exit=%s\n' "$phase" "$attempt" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$scheme" "$result" "$rc"
  [[ $rc -eq 0 && $result == *'http=200 '* ]] || failed=1
}
for attempt in 1 2; do
  request HTTP 'http://192.168.80.28:8080/' --http1.1
  request TLS 'https://netpro-tap.test:8443/' --http1.1 --tlsv1.2 --tls-max 1.2 --resolve netpro-tap.test:8443:192.168.80.28 --insecure
done
end=$(date -u '+%Y-%m-%dT%H:%M:%SZ'); printf 'phase=%s start=%s end=%s\n' "$phase" "$start" "$end"
exit "$failed"
