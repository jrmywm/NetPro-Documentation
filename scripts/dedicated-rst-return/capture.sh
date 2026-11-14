#!/usr/bin/env bash
# Bounded passive capture on the isolated RST link; never injects or forwards packets.
set -Eeuo pipefail
[[ $# == 0 ]] || { echo "Usage: $0" >&2; exit 2; }
[[ $EUID == 0 ]] || { echo 'Run this helper as root.' >&2; exit 1; }
[[ $(hostname -s) == netpro-test-gateway ]] || { echo 'Wrong host; expected netpro-test-gateway.' >&2; exit 1; }
[[ $(< /sys/class/net/ens38/address) == 00:0c:29:34:73:d6 ]] || { echo 'Gateway ens38 MAC guard failed.' >&2; exit 1; }
ip -o link show dev ens38 | grep -q 'state DOWN' && ! ip -o link show dev ens38 | grep -q PROMISC || { echo 'ens38 must start DOWN and non-promiscuous.' >&2; exit 1; }
! tc qdisc show dev ens38 | grep -qw clsact || { echo 'ens38 already has clsact; refusing.' >&2; exit 1; }
! ip link show dev np-rst-cap >/dev/null 2>&1 || { echo 'np-rst-cap already exists; refusing.' >&2; exit 1; }
for dir in ingress egress; do
  [[ -z $(tc filter show dev ens38 "$dir") ]] || { echo "ens38 $dir filters already exist; refusing." >&2; exit 1; }
done

umask 077
capture_dir=$(mktemp -d /tmp/netpro-rst-capture.XXXXXX)
chmod 700 "$capture_dir"
pcap=$capture_dir/return.pcap
qdisc_added=0
dummy_added=0
cleanup() {
  local failed=0
  local preserve_dummy=0
  ip link set dev ens38 down || failed=1
  if (( qdisc_added )); then
    tc filter del dev ens38 ingress protocol all pref 10 handle 100 matchall 2>/dev/null || true
    if [[ -z $(tc filter show dev ens38 ingress) && -z $(tc filter show dev ens38 egress) ]]; then
      tc qdisc del dev ens38 clsact || failed=1
    else
      echo 'Foreign filters remain; preserving clsact for review.' >&2
      failed=1
      preserve_dummy=1
    fi
  fi
  ip link set dev ens38 promisc off || failed=1
  if (( dummy_added )); then
    if (( preserve_dummy )); then
      echo 'Preserving np-rst-cap because a remaining filter may reference it.' >&2
    else
      ip link set dev np-rst-cap down || failed=1
      ip link delete dev np-rst-cap || failed=1
    fi
  fi
  echo "Capture retained at $capture_dir"
  (( failed == 0 )) || echo 'Cleanup needs Gateway review.' >&2
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

ip link add dev np-rst-cap type dummy
dummy_added=1
ip link set dev np-rst-cap up
tc qdisc add dev ens38 clsact
qdisc_added=1
tc filter add dev ens38 ingress protocol all pref 10 handle 100 matchall \
  action mirred egress mirror dev np-rst-cap action drop
ip link set dev ens38 up
ip link set dev ens38 promisc on
echo "Capture directory: $capture_dir"
echo 'Starting passive capture: TCP/8443, maximum 12 seconds or 100 packets.'
timeout 12s tcpdump -Z root -ni np-rst-cap -e -s0 -c 100 -w "$pcap" 'tcp port 8443' &
capture_pid=$!
capture_rc=0
wait "$capture_pid" || capture_rc=$?
[[ $capture_rc == 0 || $capture_rc == 124 ]] || { echo "tcpdump/timeout failed with status $capture_rc" >&2; exit "$capture_rc"; }
if [[ -s $pcap ]]; then
  echo 'Captured frames (bounded to 100):'
  tcpdump -nn -e -S -r "$pcap"
else
  echo 'No capture file was produced.'
fi
