#!/usr/bin/env bash
# Temporary isolated-segment RST return path. Review before root execution.
set -Eeuo pipefail
[[ $# == 1 && $1 =~ ^(start|status|stop)$ ]] || { echo "Usage: $0 start|status|stop" >&2; exit 2; }
cmd=$1
host=netpro-test-gateway
state=/run/netpro-dedicated-rst-return
timer_file=/run/netpro-dedicated-rst-return.timer
timer_unit=netpro-dedicated-rst-return-stop
script=$(realpath -- "$0")
[[ $EUID == 0 ]] || { echo 'Run this helper as root.' >&2; exit 1; }
[[ $(hostname -s) == "$host" ]] || { echo "Wrong host; expected $host" >&2; exit 1; }

need_state() {
  [[ -f $state && $(< "$state") == dedicated-rst-return-v1 ]] || {
    echo 'No matching owned RST-return state; refusing.' >&2; exit 1;
  }
}

cleanup() {
  local failed=0
  need_state || return 1
  ip link set dev ens38 down || failed=1
  ip link set dev ens38 promisc off || failed=1
  tc filter del dev ens38 ingress protocol ip pref 201 handle 201 flower 2>/dev/null || true
  tc filter del dev ens38 ingress protocol ip pref 202 handle 202 flower 2>/dev/null || true
  tc filter del dev ens38 ingress protocol all pref 203 handle 203 matchall 2>/dev/null || true
  if tc qdisc show dev ens38 | grep -qw clsact; then
    if [[ -z $(tc filter show dev ens38 ingress) && -z $(tc filter show dev ens38 egress) ]]; then
      tc qdisc del dev ens38 clsact || failed=1
    else
      echo 'Foreign filters remain; preserving clsact and state for manual review.' >&2
      failed=1
    fi
  fi
  if [[ -f $timer_file && $(< "$timer_file") == "$timer_unit" ]]; then
    systemctl stop "$timer_unit.timer" 2>/dev/null || true
    rm -f "$timer_file"
  fi
  if (( failed )); then
    echo "Cleanup incomplete; retained $state for review/retry." >&2
    return 1
  fi
  rm -f "$state"
  echo 'Stopped: owned RST filters removed; ens38 restored DOWN/non-promiscuous.'
}

case "$cmd" in
start)
  [[ ! -e $state && ! -e $timer_file ]] || { echo 'Owned state/timer already exists; refusing.' >&2; exit 1; }
  [[ $(< /sys/class/net/ens37/address) == 00:0c:29:34:73:cc && $(< /sys/class/net/ens38/address) == 00:0c:29:34:73:d6 ]] || { echo 'Gateway ens37/ens38 MAC guard failed.' >&2; exit 1; }
  ip -4 -o addr show dev ens37 | grep -Fq '192.168.80.28/24' || { echo 'ens37 address guard failed.' >&2; exit 1; }
  ip -4 -o addr show dev ens38 | grep -q 'inet ' && { echo 'ens38 must have no IPv4 address.' >&2; exit 1; }
  ip -o link show dev ens38 | grep -q 'state DOWN' && ! ip -o link show dev ens38 | grep -q PROMISC || { echo 'ens38 must start DOWN and non-promiscuous.' >&2; exit 1; }
  [[ $(< /proc/sys/net/ipv4/ip_forward) == 0 ]] || { echo 'ip_forward must remain 0.' >&2; exit 1; }
  ! tc qdisc show dev ens38 | grep -qw clsact || { echo 'ens38 already has clsact; refusing.' >&2; exit 1; }
  for dir in ingress egress; do
    [[ -z $(tc filter show dev ens38 "$dir") ]] || { echo "ens38 $dir filters already exist; refusing." >&2; exit 1; }
  done
  [[ ! -e "/run/systemd/transient/$timer_unit.timer" && ! -e "/run/systemd/transient/$timer_unit.service" ]] || { echo 'Timer unit name is already allocated; refusing.' >&2; exit 1; }
  systemctl is-active --quiet "$timer_unit.timer" && { echo 'Timer is already active; refusing.' >&2; exit 1; } || true

  umask 077
  printf '%s\n' dedicated-rst-return-v1 > "$state"
  rollback_start() { local rc=$?; trap - ERR; cleanup || echo 'PARTIAL START: inspect Gateway and retry stop manually.' >&2; exit "$rc"; }
  trap rollback_start ERR
  printf '%s\n' "$timer_unit" > "$timer_file"
  systemd-run --quiet --unit="$timer_unit" --on-active=60s /bin/bash "$script" stop
  tc qdisc add dev ens38 clsact
  # Gateway-originated reset to the client: preserve the cloned L2/L3/L4 tuple.
  # tc police takes exceed/conform order: drop excess packets, pass conforming ones.
  tc filter add dev ens38 ingress protocol ip pref 201 handle 201 flower \
    src_mac 00:0c:29:34:73:cc dst_mac 00:0c:29:91:39:14 \
    src_ip 192.168.80.28/32 dst_ip 192.168.80.29/32 \
    ip_proto tcp src_port 8443 tcp_flags 0x04/0x04 \
    action police rate 16kbit burst 2kb conform-exceed drop/pipe \
    action mirred egress redirect dev ens37
  # Client-originated reset to the local TLS listener: deliver only matching RSTs to ens37 ingress.
  tc filter add dev ens38 ingress protocol ip pref 202 handle 202 flower \
    src_mac 00:0c:29:91:39:14 dst_mac 00:0c:29:34:73:cc \
    src_ip 192.168.80.29/32 dst_ip 192.168.80.28/32 \
    ip_proto tcp dst_port 8443 tcp_flags 0x04/0x04 \
    action police rate 16kbit burst 2kb conform-exceed drop/pipe \
    action skbedit ptype host pipe action mirred ingress redirect dev ens37
  tc filter add dev ens38 ingress protocol all pref 203 handle 203 matchall action drop
  ip link set dev ens38 up
  ip link set dev ens38 promisc on
  trap - ERR
  echo 'Started isolated RST return path; only the two guarded TCP/8443 RST tuples pass. Auto-stop in 60 seconds.'
  ;;
status)
  ip -br link | grep -E '^(ens37|ens38)[[:space:]]'
  printf 'ip_forward=%s state=%s timer=%s\n' \
    "$(< /proc/sys/net/ipv4/ip_forward)" \
    "$( [[ -f $state ]] && echo active || echo absent )" \
    "$(systemctl is-active "$timer_unit.timer" 2>/dev/null || true)"
  tc -s filter show dev ens38 ingress 2>/dev/null || true
  ;;
stop)
  cleanup
  ;;
esac
