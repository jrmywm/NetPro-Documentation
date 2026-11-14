"""Install the lab prototype only if guarded HTTP/3 and TLS probes pass."""
import datetime
import json
import os
from pathlib import Path
import shlex
from pathlib import PurePosixPath
import sys

BASE = Path(__file__).resolve().parent
TEST = BASE.parents[1] / 'Testing'
sys.path[:0] = [str(TEST / 'snmp-quic-integration'), str(TEST / 'thesis-replication')]
import active_baseline as ab
from candidate_rollout import CandidateRollout
from remote import connect_verified

ab.TEST_DOMAIN = 'mysite.local'
ab.TEST_IP = '192.168.80.28'
PS, NPB, GW, CL = ('192.168.31.' + str(n) for n in (31, 33, 37, 39))
OUT = BASE / 'evidence' / ('persistent-prototype-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
OUT.mkdir(parents=True)
password = os.environ['NETPRO_LAB_PASSWORD']
known_hosts = Path.home() / '.ssh/known_hosts'
w = ab.ActiveBaseline(password, OUT, known_hosts)
q = shlex.quote
gateway_unit = 'netpro-quic-lab.service'
gateway_timer = 'netpro-quic-lab-rollback'
gateway_script = '/usr/local/libexec/netpro-quic-lab'
gateway_config = '/etc/systemd/system/' + gateway_unit
restore_queue = 'tc qdisc replace dev ens37 root fq_codel limit 10240 flows 1024 quantum 1514 target 5ms interval 100ms memory_limit 32Mb ecn'
scope = 'src_ip 192.168.80.28 dst_ip 192.168.80.29 src_port 443'
setup = f"""#!/bin/bash
set -euo pipefail
test "$(hostname -s)" = netpro-test-gateway
case "${{1:-}}" in
stop)
 tc filter del dev ens38 ingress protocol ip pref 39001 2>/dev/null || true
 tc filter del dev ens38 ingress protocol ip pref 39002 2>/dev/null || true
 tc filter del dev ens38 ingress protocol ip pref 39003 2>/dev/null || true
 tc qdisc del dev ens38 clsact 2>/dev/null || true
 ip link set dev ens38 promisc off down
 if tc qdisc show dev ens37 | grep -q '^qdisc prio 3900: root'; then
  tc qdisc del dev ens37 root
  {restore_queue}
 fi
 ;;
start)
 test "$(cat /sys/class/net/ens38/address)" = 00:0c:29:34:73:d6
 test "$(cat /sys/class/net/ens38/operstate)" = down
 test "$(tc qdisc show dev ens37 | wc -l)" = 1
 tc qdisc show dev ens37 | grep -q '^qdisc fq_codel .* root'
 ! tc qdisc show dev ens38 | grep -q clsact
 trap '"$0" stop' ERR
 ip link set dev ens38 up promisc on
 tc qdisc add dev ens38 clsact
 tc filter add dev ens38 ingress protocol ip pref 39001 flower src_mac 00:0c:29:34:73:cc dst_mac 00:0c:29:91:39:14 ip_proto udp {scope} action skbedit mark 39001 action mirred egress redirect dev ens37
 tc filter add dev ens38 ingress protocol ip pref 39002 flower dst_mac 00:0c:29:91:39:14 ip_proto tcp {scope} tcp_flags 0x04/0x04 action skbedit mark 39001 action mirred egress redirect dev ens37
 tc filter add dev ens38 ingress protocol ip pref 39003 flower src_mac 00:0c:29:91:39:14 dst_mac 00:0c:29:34:73:cc ip_proto tcp src_ip 192.168.80.29 dst_ip 192.168.80.28 dst_port 443 tcp_flags 0x04/0x04 action skbedit ptype host pipe action mirred ingress redirect dev ens37
 tc qdisc replace dev ens37 root handle 3900: prio bands 3
 tc qdisc add dev ens37 parent 3900:3 handle 3901: netem delay 15ms
 tc filter add dev ens37 parent 3900: protocol ip pref 1 handle 39001 fw flowid 3900:1
 tc filter add dev ens37 parent 3900: protocol ip pref 2 flower ip_proto udp {scope} classid 3900:3
 tc filter add dev ens37 parent 3900: protocol ip pref 3 flower ip_proto tcp {scope} classid 3900:3
 ;;
*) exit 2 ;;
esac
"""
unit_text = f"""[Unit]
Description=NetPro delay assisted QUIC on the lab gateway
Wants=network-online.target
After=network-online.target sys-subsystem-net-devices-ens37.device sys-subsystem-net-devices-ens38.device
Requires=sys-subsystem-net-devices-ens37.device sys-subsystem-net-devices-ens38.device

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={gateway_script} start
ExecStop={gateway_script} stop

[Install]
WantedBy=multi-user.target
"""
rollouts, promoted, results = [], [], []
gateway_owned = False
accepted = False

def cmd(host, label, command, sudo=False):
    return w.command(host, label, command, sudo=sudo, timeout=70)[1].strip()

def stage_gateway():
    global gateway_owned
    cmd(GW, 'gateway-files-absent', f'test ! -e {gateway_script} && test ! -e {gateway_config}', True)
    stage = cmd(GW, 'gateway-stage', 'mktemp -d')
    with w.clients[GW].open_sftp() as ftp:
        for name, data in [('setup', setup), ('unit', unit_text)]:
            with ftp.file(stage + '/' + name, 'w') as f:
                f.write(data)
    gateway_owned = True
    cmd(GW, 'gateway-install', f'install -m 0755 {q(stage)}/setup {gateway_script} && install -m 0644 {q(stage)}/unit {gateway_config} && systemctl daemon-reload', True)
    cmd(GW, 'gateway-arm', f'systemd-run --quiet --collect --unit={gateway_timer} --on-active=600s /usr/bin/systemctl disable --now {gateway_unit}', True)
    cmd(GW, 'gateway-start', f'systemctl start {gateway_unit}', True)

def probe(phase, transport, deny, count=5):
    for trial in range(1, count + 1):
        option = {'h3':'--http3-only','tls':'--http1.1','fallback':'--http3'}[transport]
        curl = f"/home/netpro/netpro-thesis/http3/prefix/bin/curl {option} --noproxy '*' --interface 192.168.80.29 --resolve mysite.local:443:192.168.80.28 -k --max-time 5 -sS -o /dev/null -w 'HTTP %{{http_code}} VERSION %{{http_version}}\\n' https://mysite.local/; rc=$?; echo CURL_EXIT=$rc"
        out = cmd(CL, f'{phase}-{transport}-{trial}', curl)
        rc = int(out.split('CURL_EXIT=')[-1].strip())
        passed = (rc in ((28,) if transport == 'h3' else (28, 35, 56)) and 'HTTP 000' in out) if deny else (rc == 0 and any(x in out for x in ({'h3':['HTTP 200 VERSION 3'],'tls':['HTTP 200 VERSION 1.1'],'fallback':['HTTP 200 VERSION 3','HTTP 200 VERSION 2','HTTP 200 VERSION 1.1']}[transport])))
        results.append(dict(phase=phase, transport=transport, trial=trial, passed=passed, output=out))
        print(phase, transport, trial, 'PASS' if passed else 'FAIL', flush=True)
    return all(r['passed'] for r in results if r['phase'] == phase and r['transport'] == transport)

def validate(prefix="", count=5):
    for transport in ('h3', 'tls', 'fallback'):
        probe(prefix+'before', transport, False, count)
    w.policy_id = None
    w.policy_deleted = False
    w.create_policy()
    try:
        for transport in ('h3', 'tls', 'fallback'):
            probe(prefix+'deny', transport, True, count)
    finally:
        w.delete_policy_exactly()
    for transport in ('h3', 'tls', 'fallback'):
        probe(prefix+'after', transport, False, count)
    if not all(r['passed'] for r in results):
        cmd(GW,'failed-return-counters','tc -s filter show dev ens38 ingress',True)
        raise RuntimeError('Persistent acceptance failed, see transport probe results')

try:
    w.connect_all()
    w.baseline()
    w.clients[NPB], _ = connect_verified(NPB, 'netpro', password, known_hosts)
    psroot = '/home/netpro/incoming/combined-thesis-candidate.9dQF6H'
    configs = [
        (PS, 'policy-server-vm', 'netpro-policy', psroot + '/policyServer-original-thesis', 'cdc47721b017357569ebfc04f9e69b3f2f15f58bf60b3347aed7a9ae74b63e6f', 'd7d696fd5997f2a947f02348cb6fa145b9a5f19ea3ed214d0e6816a3e56ec8d5', {'NETPRO_REPLAY_READINESS':'1','NETPRO_THESIS_SNMP_TARGET':'192.168.31.35','NETPRO_THESIS_SNMP_DOMAIN_ENABLE':'1','NETPRO_REPLICATION_STATS_PATH':psroot+'/replication-stats.json'}),
        (NPB, 'npb-vm', 'netpro-npb', '/home/netpro/incoming/combined-npb-tls.LvFaUQ/packetBroker-combined', '034e97f0818ffa77f80a8cbf61714b911949fe30937a437871af5a2c6707e1bb', '607a680272458c2dad46e7caf16751990632415c940401f4fbfac68e88196430', {}),
    ]
    for host, hostname, name, binary, sha, original, env in configs:
        rollout = CandidateRollout(w.clients[host], hostname, name, binary, sha, original, OUT, env)
        rollouts.append(rollout)
        rollout.start()
    stage_gateway()
    validate(count=2)
    for rollout in rollouts:
        dropin = '/etc/systemd/system/' + rollout.unit + '.service.d/95-combined-prototype.conf'
        binary = '/usr/local/libexec/' + rollout.unit + '-combined-prototype'
        rollout.command(f'test ! -e {q(dropin)} && test ! -e {q(binary)}')
        promoted.append((rollout, dropin, binary))
        directory = str(PurePosixPath(dropin).parent)
        rollout.command(f'install -d -m 0755 {q(directory)} /usr/local/libexec && install -m 0755 {q(rollout.candidate)} {q(binary)}')
        staged = rollout.root + '/persistent.conf'
        rollout.command(f'sed "s|^ExecStart={rollout.candidate} |ExecStart={binary} |" {q(rollout.dropin)} >{q(staged)}')
        rollback_path = rollout.root + '/rollback.sh'
        with rollout.client.open_sftp() as ftp:
            with ftp.file(rollback_path) as f:
                rollback = f.read().decode()
            marker = f'if test -f {q(rollout.dropin)}; then'
            assert rollback.count(marker) == 1
            persistent_cleanup = f"""if test -f {q(dropin)}; then
 cmp {q(staged)} {q(dropin)}
 systemctl stop {rollout.unit}
 rm -- {q(dropin)}
 install -m 0644 {q(rollout.root)}/pilot.conf {q(rollout.dropin)}
 systemctl daemon-reload
fi
"""
            with ftp.file(rollback_path + '.new', 'w') as f:
                f.write(rollback.replace(marker, persistent_cleanup + marker))
            ftp.posix_rename(rollback_path + '.new', rollback_path)
        rollout.command(f'install -m 0644 {q(staged)} {q(dropin)} && systemctl daemon-reload')
    cmd(GW, 'gateway-enable', f'systemctl enable {gateway_unit} && systemctl is-enabled {gateway_unit}', True)
    for rollout, dropin, binary in promoted:
        clear_status = 'rm -f /run/netpro-policy-cache.json && ' if rollout.unit == 'netpro-policy' else ''
        rollout.command(f'systemctl stop {rollout.unit} && {clear_status}rm -- {q(rollout.dropin)} && systemctl daemon-reload && systemctl start {rollout.unit}', timeout=70)
        if rollout.unit == 'netpro-policy':
            ready = q('import json; assert json.load(open("/run/netpro-policy-cache.json"))["policySyncReady"]')
            rollout.command(f'for attempt in $(seq 1 120); do python3 -c {ready} 2>/dev/null && exit 0; sleep 1; done; exit 1', timeout=135)
        rollout.command(f'systemctl is-enabled {rollout.unit}')
        rollout.command(f'pid=$(systemctl show {rollout.unit} -p MainPID --value); test "$(sha256sum /proc/$pid/exe | cut -d" " -f1)" = {rollout.candidate_sha}')
    cmd(GW, 'gateway-restart', f'systemctl restart {gateway_unit}', True)
    w.baseline()
    validate('persisted-', count=2)
    for rollout in rollouts:
        rollout.command('systemctl stop '+rollout.timer+'.timer')
    cmd(GW, 'gateway-disarm', f'systemctl stop {gateway_timer}.timer', True)
    accepted = True
finally:
    try:
        if w.policy_id:
            w.delete_policy_exactly()
        if not accepted:
            if gateway_owned:
                cmd(GW, 'gateway-rollback', f'systemctl disable --now {gateway_unit} || true; systemctl stop {gateway_timer}.timer || true; rm -f {gateway_config} {gateway_script}; systemctl daemon-reload', True)
            for rollout, dropin, binary in reversed(promoted):
                rollout.command(f'rm -f {q(dropin)} {q(binary)} && systemctl daemon-reload')
                # Recreate the owned runtime override so its rollback restarts the service.
                rollout.command(f'install -m 0644 {q(rollout.root)}/pilot.conf {q(rollout.dropin)}')
            for rollout in reversed(rollouts):
                rollout.stop()
    finally:
        (OUT/'deployment.json').write_text(json.dumps({'persistent':accepted,'probes':results},indent=2),encoding='utf-8')
        for client in w.clients.values():
            client.close()
        print('EVIDENCE', OUT, flush=True)
