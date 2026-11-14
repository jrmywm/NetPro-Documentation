"""Transit router enforcement with an isolated Caddy origin on the gateway VM.
An explicit controller reconciles one verified applied policy to IP-based drops.
No autonomous domain-to-flow enforcement or production deployment is claimed.
"""
import os,sys,json,datetime,shlex,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'Testing/snmp-quic-integration'),str(ROOT/'Testing/thesis-replication')]
import active_baseline as ab
from router_policy_controller import RouterController
ab.TEST_DOMAIN='mysite.local';ab.TEST_IP='198.18.0.2'
O=Path(__file__).parent/'evidence'/('automatic-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));O.mkdir(parents=True)
w=ab.ActiveBaseline(os.environ['NETPRO_LAB_PASSWORD'],O,Path.home()/'.ssh/known_hosts');q=shlex.quote
GW='192.168.31.37';CL='192.168.31.39';stage=None;armed=False;client_owned=False;results=[];counts={};controller=None;propagation=[]
tag='npr-'+w.run_id;timer='netpro-router-'+w.run_id.lower();ns='nprtest'
rules=[f'-p {proto} -s 192.168.80.29 -d 198.18.0.2 --dport 443 -m comment --comment {q(tag)} -j DROP' for proto in ['udp','tcp']]
allows=[f'-p {proto} -s 192.168.80.29 -d 198.18.0.2 --dport 443 -m comment --comment {q(tag+"-allow")} -j ACCEPT' for proto in ['udp','tcp']]+[f'-s 198.18.0.2 -d 192.168.80.29 -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment {q(tag+"-return")} -j ACCEPT']
def cmd(label,shell,host=GW):return w.command(host,label,shell,sudo=True,timeout=30)[1]
def probes(phase):
 for hostname in ['mysite.local','allowed-router.test']:
  for mode in ['h3','tls']:
   for trial in range(1,4):
    opt='--http3-only' if mode=='h3' else '--http1.1'
    shell="/home/netpro/netpro-thesis/http3/prefix/bin/curl "+opt+" --noproxy '*' --interface 192.168.80.29 --resolve "+hostname+":443:198.18.0.2 -k --max-time 2 -sS -o /dev/null -w 'HTTP %{http_code} VERSION %{http_version}\\n' https://"+hostname+"/; rc=$?; echo CURL_EXIT=$rc"
    _,out,_=w.command(CL,f'{phase}-{hostname}-{mode}-{trial}',shell,timeout=10);rc=int(out.split('CURL_EXIT=')[-1].strip())
    deny=phase.endswith('deny')
    passed=(rc==28 and 'HTTP 000' in out) if deny else (rc==0 and 'HTTP 200' in out and ('VERSION 3' in out if mode=='h3' else 'VERSION 1.1' in out))
    results.append(dict(phase=phase,hostname=hostname,mode=mode,trial=trial,passed=passed,collateral=deny and hostname=='allowed-router.test',output=out));print(phase,hostname,mode,trial,'EXPECTED' if passed else 'UNEXPECTED',flush=True)
 counts[phase]=int(cmd('origin-count-'+phase,'sleep 0.2; test ! -e '+stage+'/access.log && echo 0 || wc -l <'+stage+'/access.log').strip())
try:
 w.connect_all();w.baseline()
 cmd('preflight',"set -eu; test \"$(hostname -s)\" = netpro-test-gateway; test -x /usr/bin/caddy; ! ip netns list | grep -q '^nprtest '; test ! -e /sys/class/net/npr0; test -z \"$(ip route show 198.18.0.0/30)\"; ! tc filter show dev ens38 ingress | grep -q 'pref 38999 '")
 cmd('client-preflight','test -z "$(ip route show 198.18.0.2/32)"',CL)
 old_forward=cmd('forward-before','cat /proc/sys/net/ipv4/ip_forward').strip();assert old_forward in ('0','1')
 stage=cmd('stage','mktemp -d /home/netpro/incoming/router-transit.XXXXXX').strip();cmd('stage-permissions','chown netpro:netpro '+q(stage))
 rollback=f'''#!/bin/bash
set -eu
test "$(hostname -s)" = netpro-test-gateway
'''
 for rule in rules+allows:rollback+=f'if iptables -w 5 -C FORWARD {rule} 2>/dev/null; then iptables -w 5 -D FORWARD {rule}; fi\n'
 rollback+=f'''systemctl stop {timer}-origin.service 2>/dev/null || true
if test -e {stage}/filter-owned; then tc filter del dev ens38 ingress protocol ip pref 38999; rm -- {stage}/filter-owned; fi
if test -e {stage}/namespace-owned; then ip netns del {ns}; rm -- {stage}/namespace-owned; fi
if test -e /sys/class/net/npr0; then ip link del npr0 2>/dev/null || true; fi
if test -e {stage}/forward-owned; then sysctl -w net.ipv4.ip_forward={old_forward}; rm -- {stage}/forward-owned; fi
'''
 caddy=f'''{{
 admin off
 auto_https disable_redirects
}}
https://mysite.local, https://allowed-router.test {{
 bind 198.18.0.2
 tls internal
 respond "NetPro transit router origin"
 log {{
  output file {stage}/access.log
 }}
}}
'''
 with w.clients[GW].open_sftp() as f:
  for name,data in [('rollback.sh',rollback),('Caddyfile',caddy)]:
   with f.file(stage+'/'+name,'w') as out:out.write(data)
 cmd('arm',f'systemd-run --quiet --collect --unit={timer} --on-active=600s /bin/bash {stage}/rollback.sh');armed=True
 cmd('client-arm',f"systemd-run --quiet --collect --unit={timer} --on-active=600s /bin/bash -c "+q('ip route del 198.18.0.2/32 via 192.168.80.28 dev ens37 2>/dev/null || true'),CL);client_owned=True
 cmd('namespace-origin',f'''set -eu
touch {stage}/namespace-owned
ip netns add {ns}
ip link add npr0 type veth peer name nps0
ip link set nps0 netns {ns}
ip addr add 198.18.0.1/30 dev npr0
ip link set npr0 up
ip netns exec {ns} ip addr add 198.18.0.2/30 dev nps0
ip netns exec {ns} ip link set nps0 up
ip netns exec {ns} ip link set lo up
ip netns exec {ns} ip route add default via 198.18.0.1
touch {stage}/forward-owned
sysctl -w net.ipv4.ip_forward=1
touch {stage}/filter-owned
tc filter add dev ens38 ingress protocol ip pref 38999 flower ip_proto udp src_ip 198.18.0.2 dst_ip 192.168.80.29 src_port 443 action drop
systemd-run --quiet --collect --unit={timer}-origin /usr/sbin/ip netns exec {ns} /usr/bin/env XDG_DATA_HOME={stage}/data XDG_CONFIG_HOME={stage}/config /usr/bin/caddy run --config {stage}/Caddyfile --adapter caddyfile
sleep 2
systemctl is-active --quiet {timer}-origin.service
for attempt in $(seq 1 50); do ip netns exec {ns} ss -H -lun 'sport = :443' | grep -q . && break; sleep 0.2; done
ip netns exec {ns} ss -H -lun 'sport = :443' | grep -q .
''')
 for rule in allows:cmd('forward-allow','iptables -w 5 -I FORWARD 1 '+rule)
 cmd('client-route','ip route add 198.18.0.2/32 via 192.168.80.28 dev ens37 src 192.168.80.29',CL)
 controller=RouterController(os.environ['NETPRO_LAB_PASSWORD'],tag,O/'controller.json');controller.start();controller.wait(False)
 for cycle in range(1,4):
  label='cycle-'+str(cycle)
  probes(label+'-before')
  if not all(r['passed'] for r in results):raise RuntimeError('Allow baseline failed')
  w.policy_id=None;w.policy_deleted=False
  started=time.monotonic();w.create_policy();controller.wait(True)
  propagation.append(dict(cycle=cycle,action='create',seconds=time.monotonic()-started))
  probes(label+'-deny')
  assert counts[label+'-deny']==counts[label+'-before'],counts
  counter=cmd(label+'-drop-counters','iptables -w 5 -L FORWARD -nvx | grep -F '+q(tag)+' | grep DROP')
  assert len(counter.strip().splitlines())==2 and all(int(line.split()[0])>0 for line in counter.strip().splitlines())
  (O/(label+'-drop-counters.txt')).write_text(counter,encoding='utf8')
  started=time.monotonic();w.delete_policy_exactly();controller.wait(False)
  propagation.append(dict(cycle=cycle,action='delete',seconds=time.monotonic()-started))
  probes(label+'-after');w.baseline()
  assert counts[label+'-after']==counts[label+'-before']+12,counts
 w.baseline()

finally:
 cleanup_errors=[]
 try:
  if controller:
   try:controller.stop()
   except Exception as error:cleanup_errors.append(str(error))
  if armed:
   try:cmd('gateway-restore','/bin/bash '+q(stage+'/rollback.sh'));cmd('gateway-disarm','systemctl stop '+timer+'.timer')
   except Exception as error:cleanup_errors.append(str(error))
  if client_owned:
   try:cmd('client-restore','ip route del 198.18.0.2/32 via 192.168.80.28 dev ens37 2>/dev/null || true; systemctl stop '+timer+'.timer',CL)
   except Exception as error:cleanup_errors.append(str(error))
  if w.policy_id:
   try:w.delete_policy_exactly()
   except Exception as error:cleanup_errors.append(str(error))
 finally:
  (O/'results.json').write_text(json.dumps(dict(probes=results,origin_requests=counts,cleanup_errors=cleanup_errors,propagation=propagation),indent=2),encoding='utf8');w.save()
  for c in w.clients.values():c.close()
  print('EVIDENCE',O,flush=True)
 if cleanup_errors:raise RuntimeError(str(cleanup_errors))
assert len(results)==108 and all(r['passed'] for r in results),'Experiment incomplete or unexpected results'
print('108/108 observations match expectations; automatic updates work; shared-IP collateral blocking CONFIRMED; cleanup complete',flush=True)
