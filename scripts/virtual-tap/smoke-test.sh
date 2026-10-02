#!/usr/bin/env bash
# Isolated bridge/TC mirror smoke test. This script never touches production links.
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo 'Run as root' >&2; exit 1; }
for tool in ip tc ping tcpdump timeout; do command -v "$tool" >/dev/null || { echo "Missing required tool: $tool" >&2; exit 1; }; done

tag="nt$$_$RANDOM"
tag=${tag:0:11}
brns="${tag}b"; a="${tag}a"; b="${tag}c"; mon="${tag}m"
ab="${tag}ab"; ba="${tag}ba"; cb="${tag}cb"; bc="${tag}bc"; mb="${tag}mb"; bm="${tag}bm"
capture_dir=$(mktemp -d /tmp/netpro-tap-smoke.XXXXXX)
chmod 0700 "$capture_dir"
pcap="$capture_dir/capture.pcap"
created_ns=(); created_links=(); cap_pid=''
cleanup() {
  set +e
  if [[ -n "$cap_pid" ]]; then kill "$cap_pid" >/dev/null 2>&1; wait "$cap_pid" >/dev/null 2>&1; fi
  for ns in "${created_ns[@]}"; do ip netns del "$ns" >/dev/null 2>&1; done
  for dev in "${created_links[@]}"; do ip link show dev "$dev" >/dev/null 2>&1 && ip link del dev "$dev" >/dev/null 2>&1; done
  rm -f "$pcap"
  rmdir "$capture_dir" >/dev/null 2>&1 || true
}
trap cleanup EXIT

for ns in "$brns" "$a" "$b" "$mon"; do
  if ip netns list | awk '{print $1}' | grep -Fxq "$ns"; then echo "Namespace collision: $ns" >&2; exit 1; fi
  ip netns add "$ns"
  created_ns+=("$ns")
done
ip -n "$brns" link add br0 type bridge
ip -n "$brns" link set br0 up

ip link add "$ab" type veth peer name "$ba"; created_links+=("$ab" "$ba")
ip link set "$ab" netns "$a"; ip link set "$ba" netns "$brns"
ip link add "$cb" type veth peer name "$bc"; created_links+=("$cb" "$bc")
ip link set "$cb" netns "$b"; ip link set "$bc" netns "$brns"
ip link add "$mb" type veth peer name "$bm"; created_links+=("$mb" "$bm")
ip link set "$mb" netns "$mon"; ip link set "$bm" netns "$brns"

ip -n "$brns" link set "$ba" master br0
ip -n "$brns" link set "$bc" master br0
for pair in "$a:$ab" "$b:$cb" "$mon:$mb" "$brns:$ba" "$brns:$bc" "$brns:$bm"; do
  ns=${pair%%:*}; dev=${pair#*:}; ip -n "$ns" link set "$dev" up
done
ip -n "$brns" link set lo up
ip -n "$a" link set lo up; ip -n "$b" link set lo up; ip -n "$mon" link set lo up
ip -n "$a" addr add 198.18.77.1/24 dev "$ab"
ip -n "$b" addr add 198.18.77.2/24 dev "$cb"
ip -n "$a" neigh flush dev "$ab" >/dev/null 2>&1 || true
ip -n "$b" neigh flush dev "$cb" >/dev/null 2>&1 || true

ip netns exec "$brns" tc qdisc add dev "$ba" clsact
ip netns exec "$brns" tc qdisc add dev "$bc" clsact
ip netns exec "$brns" tc filter add dev "$ba" ingress protocol all pref 10 matchall action mirred egress mirror dev "$bm"
ip netns exec "$brns" tc filter add dev "$bc" ingress protocol all pref 10 matchall action mirred egress mirror dev "$bm"

capture_start() {
  : >"$pcap"
  ip netns exec "$mon" tcpdump -Z root -n -U -i "$mb" -w "$pcap" 'icmp' >/dev/null 2>&1 & cap_pid=$!
  sleep 1
}
capture_stop() {
  kill "$cap_pid" >/dev/null 2>&1 || true
  wait "$cap_pid" >/dev/null 2>&1 || true
  cap_pid=''
}
icmp_count() { tcpdump -n -r "$pcap" 'icmp' 2>/dev/null | wc -l; }

capture_start
ip netns exec "$a" ping -n -c 2 -W 2 198.18.77.2 >/dev/null
sleep 0.5
capture_stop
count=$(icmp_count)
[[ $count -gt 0 ]] || { echo 'FAIL: ping passed but monitor captured no mirrored ICMP' >&2; exit 1; }
echo "PASS: endpoint ping and TC mirror capture ($count ICMP packets)"

ip netns exec "$brns" tc filter del dev "$ba" ingress
ip netns exec "$brns" tc filter del dev "$bc" ingress
capture_start
ip netns exec "$a" ping -n -c 2 -W 2 198.18.77.2 >/dev/null
sleep 0.5
capture_stop
count=$(icmp_count)
[[ $count -eq 0 ]] || { echo "FAIL: monitor captured $count ICMP packets with mirrors removed" >&2; exit 1; }
echo 'PASS: endpoint ping remains functional with mirror filters removed; monitor saw no ICMP'

ip netns exec "$brns" tc filter add dev "$ba" ingress protocol all pref 10 matchall action mirred egress mirror dev "$bm"
ip netns exec "$brns" tc filter add dev "$bc" ingress protocol all pref 10 matchall action mirred egress mirror dev "$bm"
ip netns exec "$a" ping -n -c 2 -W 2 198.18.77.2 >/dev/null
echo 'PASS: endpoint ping remains functional after mirror filters were re-added'
