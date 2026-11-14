"""Transit router enforcement with an isolated Caddy origin on the gateway VM.
An explicit controller reconciles one verified applied policy to IP-based drops.
No autonomous domain-to-flow enforcement or production deployment is claimed.
"""
import os,sys,json,datetime,shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'Testing/snmp-quic-integration'),str(ROOT/'Testing/thesis-replication')]
import active_baseline as ab
ab.TEST_DOMAIN='blocked-router.test';ab.TEST_IP='198.18.0.3'
O=Path(__file__).parent/'evidence'/('latency-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));O.mkdir(parents=True)
w=ab.ActiveBaseline(os.environ['NETPRO_LAB_PASSWORD'],O,Path.home()/'.ssh/known_hosts');q=shlex.quote
GW='192.168.31.37';CL='192.168.31.39';stage=None;armed=False;client_owned=False;results=[];counts={}
tag='npr-'+w.run_id;timer='netpro-router-'+w.run_id.lower();ns='nprtest'
rules=[f'-p {proto} -s 192.168.80.29 -d 198.18.0.3 --dport 443 -m comment --comment {q(tag)} -j DROP' for proto in ['udp','tcp']]
allows=[f'-p {proto} -s 192.168.80.29 -d 198.18.0.2 --dport 443 -m comment --comment {q(tag+"-allow")} -j ACCEPT' for proto in ['udp','tcp']]+[f'-s 198.18.0.2 -d 192.168.80.29 -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment {q(tag+"-return")} -j ACCEPT']
def cmd(label,shell,host=GW):return w.command(host,label,shell,sudo=True,timeout=30)[1]
def reconcile(block):
 rows=w.sqlite('SELECT id, domain, ip_address FROM policies WHERE id = ?',(w.policy_id,))
 if block:assert len(rows)==1 and rows[0]['domain']==ab.TEST_DOMAIN and rows[0]['ip_address']==ab.TEST_IP
 else:assert len(rows)==1 and rows[0]['domain']==ab.TEST_DOMAIN and rows[0]['ip_address']==ab.TEST_IP
 for rule in rules:cmd('reconcile-'+str(block),'iptables -w 5 '+('-I FORWARD 1 ' if block else '-D FORWARD ')+rule)
def benchmark(label,count=50):
 code="""import subprocess,json
rows=[]
for mode,option in [('h3','--http3-only'),('tls','--http1.1')]:
 for trial in range(COUNT):
  command=['/home/netpro/netpro-thesis/http3/prefix/bin/curl',option,'--noproxy','*','--interface','192.168.80.29','--resolve','mysite.local:443:198.18.0.2','-k','--max-time','2','-sS','-o','/dev/null','-w','%{http_code} %{http_version} %{time_total} %{time_connect} %{time_appconnect} %{time_starttransfer}', 'https://mysite.local/']
  r=subprocess.run(command,capture_output=True,text=True)
  fields=r.stdout.split()
  rows.append(dict(mode=mode,trial=trial,rc=r.returncode,values=fields))
print(json.dumps(rows))
""".replace('COUNT',str(count))
 _,out,_=w.command(CL,'bench-'+label,'python3 -c '+q(code),timeout=90)
 rows=json.loads(out)
 for row in rows:
  row['block']=label
  assert row['rc']==0 and len(row['values'])==6 and row['values'][0]=='200' and row['values'][1]==('3' if row['mode']=='h3' else '1.1'),row
 if not label.startswith('warmup'):results.extend(rows)
 print(label,'PASS',len(rows),'successful fresh connections',flush=True)
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
https://mysite.local {{
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
 cmd('arm',f'systemd-run --quiet --collect --unit={timer} --on-active=300s /bin/bash {stage}/rollback.sh');armed=True
 cmd('client-arm',f"systemd-run --quiet --collect --unit={timer} --on-active=300s /bin/bash -c "+q('ip route del 198.18.0.2/32 via 192.168.80.28 dev ens37 2>/dev/null || true'),CL);client_owned=True
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
 benchmark('warmup-baseline',10)
 w.create_policy();reconcile(True);benchmark('warmup-enforced',10);reconcile(False)
 # Same topology, alternating ABBA order to reduce time drift. The unrelated
 # applied deny rule does not match this origin or SNI; target IP is .3.
 for i,condition in enumerate(['baseline','enforced','enforced','baseline','baseline','enforced','enforced','baseline']):
  if condition=='enforced':reconcile(True)
  try:benchmark(str(i)+'-'+condition)
  finally:
   if condition=='enforced':reconcile(False)
 w.delete_policy_exactly();w.baseline()

finally:
 cleanup_errors=[]
 try:
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
  (O/'results.json').write_text(json.dumps(dict(probes=results,origin_requests=counts,cleanup_errors=cleanup_errors),indent=2),encoding='utf8');w.save()
  for c in w.clients.values():c.close()
  print('EVIDENCE',O,flush=True)
 if cleanup_errors:raise RuntimeError(str(cleanup_errors))
assert len(results)==800,'Incomplete benchmark'
print('PASS 800/800; cleanup complete',flush=True)
