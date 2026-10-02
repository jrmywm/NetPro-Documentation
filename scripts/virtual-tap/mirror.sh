#!/usr/bin/env bash
set -Eeuo pipefail
[[ $# == 1 && $1 =~ ^(start|stop|status)$ ]] || { echo "Usage: $0 start|stop|status" >&2; exit 2; }
cmd=$1
state=/run/netpro-virtual-tap-mirror.state
devs=(ens34 ens35 ens36)
[[ $EUID == 0 ]] || { echo 'Run as root' >&2; exit 1; }
[[ $(hostname -s) == netpro-virtual-tap && $(< /etc/machine-id) == 64ff1c0225bc42f588b6afaf62654e66 ]] || { echo 'Host identity guard failed' >&2; exit 1; }
[[ $(< /sys/class/net/ens34/address) == 00:0c:29:da:93:12 && $(< /sys/class/net/ens35/address) == 00:0c:29:da:93:1c && $(< /sys/class/net/ens36/address) == 00:0c:29:da:93:26 ]] || { echo 'Mirror NIC MAC guard failed' >&2; exit 1; }

owned_filter_present() { tc filter show dev "$1" ingress | grep -q 'handle 0x64'; }
remove_qdisc_if_empty() {
  local dev=$1
  tc qdisc show dev "$dev" | grep -qw clsact || return 0
  [[ -z $(tc filter show dev "$dev" ingress) && -z $(tc filter show dev "$dev" egress) ]] || { echo "$dev clsact retained with unrelated filters" >&2; return 0; }
  tc qdisc del dev "$dev" clsact
}
cleanup() {
  local failed=0 dev
  tc filter del dev ens34 ingress protocol all pref 100 handle 100 matchall 2>/dev/null || true
  tc filter del dev ens35 ingress protocol all pref 100 handle 100 matchall 2>/dev/null || true
  tc filter del dev ens36 ingress protocol all pref 100 handle 100 matchall 2>/dev/null || true
  for dev in "${devs[@]}"; do
    if owned_filter_present "$dev"; then echo "Owned filter remains on $dev" >&2; failed=1; fi
  done
  for dev in "${devs[@]}"; do remove_qdisc_if_empty "$dev" || failed=1; done
  if (( failed )); then echo "Cleanup incomplete; retained $state" >&2; return 1; fi
  rm -f "$state"
  echo 'Virtual TAP mirrors stopped; bridge and management networking were not changed.'
}

case "$cmd" in
start)
  if [[ -f $state ]]; then
    if owned_filter_present ens34 && owned_filter_present ens35 && owned_filter_present ens36; then echo 'Virtual TAP mirrors already active'; exit 0; fi
    echo 'Owned mirror state is incomplete; run stop before restarting' >&2; exit 1
  fi
  [[ -e /sys/class/net/br-tap ]] || { echo 'br-tap is missing; configure Netplan first' >&2; exit 1; }
  ip -o link show dev ens34 | grep -qw br-tap && ip -o link show dev ens35 | grep -qw br-tap || { echo 'ens34 and ens35 must both be bridge ports of br-tap' >&2; exit 1; }
  ! ip -o link show dev ens33 | grep -qw br-tap && ! ip -o link show dev ens36 | grep -qw br-tap || { echo 'Management ens33 and monitor ens36 must remain outside br-tap' >&2; exit 1; }
  [[ -z $(ip -o addr show dev ens36) ]] || { echo 'Monitor ens36 must have no IPv4 or IPv6 addresses' >&2; exit 1; }
  ip -o link show dev ens36 | grep -Eq '<[^>]*UP[,>]' || { echo 'Monitor ens36 must be administratively up' >&2; exit 1; }
  for dev in "${devs[@]}"; do
    ! tc qdisc show dev "$dev" | grep -qw clsact || { echo "$dev already has clsact; refusing" >&2; exit 1; }
    for dir in ingress egress; do [[ -z $(tc filter show dev "$dev" "$dir") ]] || { echo "$dev $dir filters already exist; refusing" >&2; exit 1; }; done
  done
  umask 077; printf 'owned_by=netpro-virtual-tap-mirror\n' > "$state"
  rollback_start() { rc=$?; trap - ERR; cleanup || echo 'Partial mirror start cleanup failed; run mirror.sh stop' >&2; exit "$rc"; }
  trap rollback_start ERR
  for dev in "${devs[@]}"; do tc qdisc add dev "$dev" clsact; done
  tc filter add dev ens34 ingress protocol all pref 100 handle 100 matchall action mirred egress mirror dev ens36
  tc filter add dev ens35 ingress protocol all pref 100 handle 100 matchall action mirred egress mirror dev ens36
  tc filter add dev ens36 ingress protocol all pref 100 handle 100 matchall action drop
  trap - ERR
  echo 'Virtual TAP mirror active: ens34/ens35 ingress mirrored to ens36; ens36 ingress dropped.'
  ;;
stop)
  [[ -f $state ]] || { echo 'Virtual TAP mirrors already stopped'; exit 0; }
  cleanup
  ;;
status)
  for dev in ens34 ens35 ens36 br-tap; do ip -br link show dev "$dev"; done
  printf 'mirror_state=%s\n' "$( [[ -f $state ]] && echo active || echo absent )"
  for dev in "${devs[@]}"; do tc -s filter show dev "$dev" ingress; done
  ;;
esac
