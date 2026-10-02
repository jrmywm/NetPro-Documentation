#!/usr/bin/env bash
# Temporary, narrowly scoped gateway path for proving server-directed RST delivery.
set -Eeuo pipefail
[[ $# == 1 && $1 =~ ^(start|status|stop)$ ]] || { echo "Usage: $0 start|status|stop" >&2; exit 2; }
cmd=$1
host=netpro-test-gateway
client=192.168.80.29
server=192.168.31.35
comment=netpro-server-rst-proof
state=/run/netpro-server-rst-proof
timer_file=/run/netpro-server-rst-proof.timer
timer_unit=netpro-server-rst-proof-stop
script=$(realpath -- "$0")
[[ $EUID == 0 ]] || { echo 'Run this helper as root.' >&2; exit 1; }
[[ $(hostname -s) == "$host" ]] || { echo "Wrong host; expected $host" >&2; exit 1; }

need_state() { [[ -f $state ]] || { echo 'RST proof path is not started' >&2; exit 1; }; }

remove_qdisc_if_empty() {
  local dev=$1
  if tc qdisc show dev "$dev" | grep -qw clsact; then
    if [[ -z $(tc filter show dev "$dev" ingress) && -z $(tc filter show dev "$dev" egress) ]]; then
      tc qdisc del dev "$dev" clsact 2>/dev/null || return 1
    fi
  else
    return 0
  fi
  [[ -z $(tc filter show dev "$dev" ingress) && -z $(tc filter show dev "$dev" egress) ]] || echo "$dev clsact retained because unrelated filters are present" >&2
}

cleanup() {
  local failed=0
  [[ -f $state ]] || return 0
  # State is created by this root-only helper and contains only numeric values.
  source "$state"
  ip link set dev ens38 down || failed=1
  ip link set dev ens38 promisc off || failed=1
  tc filter del dev ens37 ingress protocol ip pref 5 handle 50 flower 2>/dev/null || true
  tc filter del dev ens37 ingress protocol ip pref 10 handle 100 flower 2>/dev/null || true
  tc filter del dev ens38 ingress protocol ip pref 10 handle 110 flower 2>/dev/null || true
  tc filter del dev ens38 ingress protocol all pref 20 handle 120 matchall 2>/dev/null || true
  iptables -D FORWARD -i ens37 -o ens33 -s "$client/32" -d "$server/32" -p tcp --dport 8443 -m comment --comment "$comment" -j ACCEPT 2>/dev/null || true
  iptables -D FORWARD -i ens38 -o ens33 -s "$client/32" -d "$server/32" -p tcp --dport 8443 -m comment --comment "$comment" -j ACCEPT 2>/dev/null || true
  iptables -D FORWARD -i ens33 -o ens37 -s "$server/32" -d "$client/32" -p tcp --sport 8443 -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment "$comment" -j ACCEPT 2>/dev/null || true
  iptables -t nat -D POSTROUTING -s "$client/32" -d "$server/32" -p tcp --dport 8443 -o ens33 -m comment --comment "$comment" -j MASQUERADE 2>/dev/null || true
  sysctl -q -w "net.ipv4.conf.ens38.rp_filter=$rp_filter_ens38" || failed=1
  sysctl -q -w "net.ipv4.conf.all.rp_filter=$rp_filter_all" || failed=1
  sysctl -q -w "net.ipv4.ip_forward=$ip_forward" || failed=1
  if (( ens38_up )); then ip link set dev ens38 up || failed=1; fi
  if (( ens38_promisc )); then ip link set dev ens38 promisc on || failed=1; fi
  remove_qdisc_if_empty ens37 || failed=1
  remove_qdisc_if_empty ens38 || failed=1
  if [[ -f $timer_file && $(< "$timer_file") == "$timer_unit" ]]; then
    systemctl stop "$timer_unit.timer" 2>/dev/null || true
    rm -f "$timer_file"
  fi
  if (( failed )); then
    echo "Cleanup incomplete; retained state at $state for retry" >&2
    return 1
  fi
  rm -f "$state"
  echo 'RST proof path stopped; owned rules removed and sysctl/link state restored.'
}

case "$cmd" in
start)
  [[ ! -e $state && ! -e $timer_file && ! -e /run/netpro-passive-demo.forward && ! -e /run/netpro-test-gateway.ip-forward ]] || { echo 'Gateway helper state already exists; refusing' >&2; exit 1; }
  ! systemctl is-active --quiet netpro-test-gateway || { echo 'Existing gateway service is active; refusing' >&2; exit 1; }
  [[ $(< /sys/class/net/ens33/address) == 00:0c:29:34:73:c2 && $(< /sys/class/net/ens37/address) == 00:0c:29:34:73:cc && $(< /sys/class/net/ens38/address) == 00:0c:29:34:73:d6 ]] || { echo 'Gateway NIC MAC guard failed' >&2; exit 1; }
  ip -4 -o addr show dev ens33 | grep -Fq '192.168.31.37/24' || { echo 'ens33 address mismatch' >&2; exit 1; }
  ip -4 -o addr show dev ens37 | grep -Fq '192.168.80.28/24' || { echo 'ens37 address mismatch' >&2; exit 1; }
  ip route get "$server" | grep -Fq 'dev ens33' || { echo 'Server route must use ens33' >&2; exit 1; }
  [[ $(< /proc/sys/net/ipv4/ip_forward) == 0 ]] || { echo 'ip_forward must initially be 0' >&2; exit 1; }
  ip -o link show dev ens38 | grep -q 'state DOWN' && ! ip -o link show dev ens38 | grep -q PROMISC || { echo 'ens38 must initially be down and non-promiscuous' >&2; exit 1; }
  rp_filter_all=$(< /proc/sys/net/ipv4/conf/all/rp_filter)
  rp_filter_ens33=$(< /proc/sys/net/ipv4/conf/ens33/rp_filter)
  rp_filter_ens37=$(< /proc/sys/net/ipv4/conf/ens37/rp_filter)
  rp_filter_ens38=$(< /proc/sys/net/ipv4/conf/ens38/rp_filter)
  [[ $rp_filter_all != 1 ]] || { echo 'rp_filter all=1 is strict; ask the gateway owner before proceeding' >&2; exit 1; }
  [[ $rp_filter_ens33 == 2 && $rp_filter_ens37 == 2 ]] || { echo 'ens33 and ens37 rp_filter must both be loose (2) before lowering the all setting' >&2; exit 1; }
  link_info=$(ip -o link show dev ens38)
  ens38_up=0; [[ $link_info == *'state UP'* ]] && ens38_up=1
  ens38_promisc=0; [[ $link_info == *PROMISC* ]] && ens38_promisc=1
  for dev in ens37 ens38; do
    ! tc qdisc show dev "$dev" | grep -qw clsact || { echo "$dev already has clsact" >&2; exit 1; }
    for dir in ingress egress; do [[ -z $(tc filter show dev "$dev" "$dir") ]] || { echo "$dev $dir filters already exist" >&2; exit 1; }; done
  done
  ! iptables-save | grep -q "$comment" || { echo 'Owned iptables rules already exist' >&2; exit 1; }
  [[ ! -e "/run/systemd/transient/$timer_unit.timer" && ! -e "/run/systemd/transient/$timer_unit.service" ]] || { echo 'Owned timer name is already allocated; refusing' >&2; exit 1; }
  systemctl is-active --quiet "$timer_unit.timer" && { echo 'Owned timer name is already active; refusing' >&2; exit 1; } || true

  ip_forward=$(< /proc/sys/net/ipv4/ip_forward)
  umask 077
  printf 'ip_forward=%s\nrp_filter_all=%s\nrp_filter_ens38=%s\nens38_up=%s\nens38_promisc=%s\n' "$ip_forward" "$rp_filter_all" "$rp_filter_ens38" "$ens38_up" "$ens38_promisc" > "$state"
  rollback_start() { rc=$?; trap - ERR; cleanup || echo 'PARTIAL START CLEANUP FAILED; run gateway.sh stop' >&2; exit "$rc"; }
  trap rollback_start ERR
  printf '%s\n' "$timer_unit" > "$timer_file"
  systemd-run --quiet --unit="$timer_unit" --on-active=10m /bin/bash "$script" stop
  tc qdisc add dev ens37 clsact
  tc filter add dev ens37 ingress protocol ip pref 5 handle 50 flower src_ip "$client/32" dst_ip "$server/32" ip_proto tcp dst_port 8443 tcp_flags 0x04/0x04 action drop
  tc filter add dev ens37 ingress protocol ip pref 10 handle 100 flower src_ip "$client/32" dst_ip "$server/32" ip_proto tcp dst_port 8443 action mirred egress mirror dev ens38
  tc qdisc add dev ens38 clsact
  tc filter add dev ens38 ingress protocol ip pref 10 handle 110 flower src_ip "$client/32" dst_ip "$server/32" ip_proto tcp dst_port 8443 tcp_flags 0x04/0x04 action skbedit ptype host pass
  tc filter add dev ens38 ingress protocol all pref 20 handle 120 matchall action drop
  iptables -t nat -A POSTROUTING -s "$client/32" -d "$server/32" -p tcp --dport 8443 -o ens33 -m comment --comment "$comment" -j MASQUERADE
  iptables -I FORWARD 1 -i ens37 -o ens33 -s "$client/32" -d "$server/32" -p tcp --dport 8443 -m comment --comment "$comment" -j ACCEPT
  iptables -I FORWARD 1 -i ens38 -o ens33 -s "$client/32" -d "$server/32" -p tcp --dport 8443 -m comment --comment "$comment" -j ACCEPT
  iptables -I FORWARD 1 -i ens33 -o ens37 -s "$server/32" -d "$client/32" -p tcp --sport 8443 -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment "$comment" -j ACCEPT
  sysctl -q -w net.ipv4.ip_forward=1
  sysctl -q -w net.ipv4.conf.all.rp_filter=0
  sysctl -q -w net.ipv4.conf.ens38.rp_filter=0
  ip link set dev ens38 up
  ip link set dev ens38 promisc on
  trap - ERR
  echo 'Started scoped server-RST proof path. ens37 drops client RSTs and mirrors only client→server TCP/8443 to ens38; ens38 admits only matching server-directed RSTs. Auto-stop in 10 minutes.'
  ;;
status)
  ip -br link | grep -E '^(ens33|ens37|ens38)[[:space:]]'
  printf 'ip_forward=%s rp_filter(all/ens38)=%s/%s state=%s\n' "$(< /proc/sys/net/ipv4/ip_forward)" "$(< /proc/sys/net/ipv4/conf/all/rp_filter)" "$(< /proc/sys/net/ipv4/conf/ens38/rp_filter)" "$( [[ -f $state ]] && echo active || echo absent )"
  tc -s filter show dev ens37 ingress
  tc -s filter show dev ens38 ingress
  iptables-save | grep "$comment" || true
  ;;
stop) need_state; cleanup ;;
esac
