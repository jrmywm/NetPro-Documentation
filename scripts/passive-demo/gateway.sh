#!/usr/bin/env bash
# Passive gateway mirror with an isolated Policy injection NIC. Run start, then up/down as needed.
set -Eeuo pipefail
[[ $# == 1 ]] || { echo "Usage: $0 start|up|down|status|stop" >&2; exit 2; }
cmd=$1; host=netpro-test-gateway; state=/run/netpro-passive-demo.forward; timer_file=/run/netpro-passive-demo.timer
drop_comment=netpro-passive-demo
root() { if (( EUID == 0 )); then "$@"; else sudo -n "$@"; fi; }
[[ $(hostname -s) == "$host" ]] || { echo "Wrong host; expected $host" >&2; exit 1; }
[[ $(< /sys/class/net/ens33/address) == 00:0c:29:34:73:c2 && $(< /sys/class/net/ens37/address) == 00:0c:29:34:73:cc && $(< /sys/class/net/ens38/address) == 00:0c:29:34:73:d6 ]] || { echo 'Gateway NIC MAC guard failed' >&2; exit 1; }
if (( EUID != 0 )); then sudo -S -p '' -v; fi
need_state() { [[ -f "$state" ]] || { echo 'Passive demo is not started' >&2; exit 1; }; }

cleanup() {
  local original
  [[ -f "$state" ]] || return 0
  original=$(< "$state")
  root tc filter del dev ens37 ingress protocol all pref 10 2>/dev/null || true
  root tc filter del dev ens38 ingress protocol all pref 10 2>/dev/null || true
  root tc qdisc del dev ens37 clsact 2>/dev/null || true
  root tc qdisc del dev ens38 clsact 2>/dev/null || true
  root iptables -D FORWARD -i ens37 -o ens33 -s 192.168.80.29/32 -m comment --comment "$drop_comment" -j ACCEPT 2>/dev/null || true
  root iptables -D FORWARD -i ens33 -o ens37 -d 192.168.80.29/32 -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment "$drop_comment" -j ACCEPT 2>/dev/null || true
  root iptables -t nat -D POSTROUTING -s 192.168.80.29/32 -o ens33 -m comment --comment "$drop_comment" -j MASQUERADE 2>/dev/null || true
  root sysctl -q -w "net.ipv4.ip_forward=$original"
  root ip link set dev ens38 down
  root ip link set dev ens38 promisc off
  if [[ -f "$timer_file" ]]; then root systemctl stop "$(< "$timer_file").timer" 2>/dev/null || true; fi
  root rm -f "$timer_file" "$state"
  echo 'Passive demo stopped; ens38 down/promisc off and forwarding restored.'
}

case "$cmd" in
 start)
  [[ ! -e "$state" && ! -e "$timer_file" && ! -e /run/netpro-test-gateway.ip-forward ]] || { echo 'Passive demo or gateway-helper state already exists' >&2; exit 1; }
  ! systemctl is-active --quiet netpro-test-gateway || { echo 'Existing gateway helper is active; refusing' >&2; exit 1; }
  ip -4 -o addr show dev ens33 | grep -Fq '192.168.31.37/24' || { echo 'ens33 address mismatch' >&2; exit 1; }
  ip -4 -o addr show dev ens37 | grep -Fq '192.168.80.28/24' || { echo 'ens37 address mismatch' >&2; exit 1; }
  [[ $(< /proc/sys/net/ipv4/ip_forward) == 0 ]] || { echo 'ip_forward must initially be 0' >&2; exit 1; }
  ip -o link show dev ens38 | grep -q 'state DOWN' && ! ip -o link show dev ens38 | grep -q PROMISC || { echo 'ens38 must initially be down and non-promiscuous' >&2; exit 1; }
  for dev in ens37 ens38; do
    ! tc qdisc show dev "$dev" | grep -qw clsact || { echo "$dev already has clsact" >&2; exit 1; }
    for dir in ingress egress; do [[ -z "$(tc filter show dev "$dev" "$dir")" ]] || { echo "$dev $dir filters already exist" >&2; exit 1; }; done
  done
  ! root iptables-save | grep -q "$drop_comment" || { echo 'Owned iptables rules already exist' >&2; exit 1; }
  original_forward=$(< /proc/sys/net/ipv4/ip_forward)
  printf '%s\n' "$original_forward" | root tee "$state" >/dev/null
  rollback_start() { rc=$?; trap - ERR; cleanup || echo 'PARTIAL START CLEANUP FAILED; run gateway.sh stop' >&2; exit "$rc"; }
  trap rollback_start ERR
  script=$(realpath -- "$0"); timer_unit=netpro-passive-demo-cleanup
  printf '%s\n' "$timer_unit" | root tee "$timer_file" >/dev/null
  root systemd-run --quiet --unit="$timer_unit" --on-active=10m /bin/bash "$script" stop
  root tc qdisc add dev ens38 clsact
  root tc filter add dev ens38 ingress protocol all pref 10 matchall action drop
  root ip link set dev ens38 up
  root ip link set dev ens38 promisc on
  root sysctl -q -w net.ipv4.ip_forward=1
  root iptables -A FORWARD -i ens37 -o ens33 -s 192.168.80.29/32 -m comment --comment "$drop_comment" -j ACCEPT
  root iptables -A FORWARD -i ens33 -o ens37 -d 192.168.80.29/32 -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment "$drop_comment" -j ACCEPT
  root iptables -t nat -A POSTROUTING -s 192.168.80.29/32 -o ens33 -m comment --comment "$drop_comment" -j MASQUERADE
  root tc qdisc add dev ens37 clsact
  root tc filter add dev ens37 ingress protocol all pref 10 matchall action mirred egress mirror dev ens38
  trap - ERR
  printf 'Passive demo started. Auto-cleanup: %s.timer in 10 minutes. Mirror ens37 ingress -> ens38 egress; ens38 ingress drops all.\n' "$timer_unit"
  ;;
 up) need_state; root ip link set dev ens38 up; root ip link set dev ens38 promisc on; echo 'ens38 up/promiscuous; ingress isolation remains installed.' ;;
 down) need_state; root ip link set dev ens38 down; root ip link set dev ens38 promisc off; echo 'ens38 down/non-promiscuous; no other path changed.' ;;
 status)
  ip -br link | grep -E '^(ens37|ens38)[[:space:]]'
  printf 'ip_forward=%s state=%s\n' "$(< /proc/sys/net/ipv4/ip_forward)" "$( [[ -f "$state" ]] && echo active || echo absent )"
  tc -s filter show dev ens37 ingress
  tc -s filter show dev ens38 ingress
  ;;
 stop) need_state; cleanup ;;
 *) echo "Unknown command: $cmd" >&2; exit 2 ;;
esac
