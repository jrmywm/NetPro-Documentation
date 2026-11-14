"""Temporary gateway enforcement experiment. Dedicated lab origin only.
The controller translates an exactly verified applied Policy Server rule into
an IP/UDP/port drop. It does not claim per-domain flow classification.
"""
import os,sys,json,datetime,shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Testing/snmp-quic-integration'),str(ROOT/'Testing/thesis-replication')]
import active_baseline as ab
ab.TEST_DOMAIN='mysite.local';ab.TEST_IP='192.168.80.28'
O=Path(__file__).parent/'evidence'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');O.mkdir(parents=True)
w=ab.ActiveBaseline(os.environ['NETPRO_LAB_PASSWORD'],O,Path.home()/'.ssh/known_hosts')
GW='192.168.31.37';CL='192.168.31.39';q=shlex.quote
comment='netpro-router-'+w.run_id
rule='-p udp -s 192.168.80.29 -d 192.168.80.28 --dport 443 -m comment --comment '+q(comment)+' -j DROP'
timer='netpro-router-'+w.run_id.lower();stage=None;armed=False;results=[]
def cmd(label,shell):return w.command(GW,label,shell,sudo=True,timeout=25)[1]
def reconcile(block):
 rows=w.sqlite('SELECT id, domain, ip_address FROM policies WHERE id = ?',(w.policy_id,))
 if block:
  assert len(rows)==1 and rows[0]['domain']==ab.TEST_DOMAIN and rows[0]['ip_address']==ab.TEST_IP
  cmd('router-install', 'iptables -w 5 -I INPUT 1 '+rule)
  cmd('router-rule-confirm','iptables -w 5 -C INPUT '+rule)
 else:
  assert not rows
  cmd('router-remove','iptables -w 5 -D INPUT '+rule)
def probes(phase):
 for mode in ['h3','tls']:
  for i in range(1,6):
   opt='--http3-only' if mode=='h3' else '--http1.1'
   shell="/home/netpro/netpro-thesis/http3/prefix/bin/curl "+opt+" --noproxy '*' --interface 192.168.80.29 --resolve mysite.local:443:192.168.80.28 -k --max-time 2 -sS -o /dev/null -w 'HTTP %{http_code} VERSION %{http_version}\\n' https://mysite.local/; rc=$?; echo CURL_EXIT=$rc"
   _,out,_=w.command(CL,f'{phase}-{mode}-{i}',shell,timeout=10)
   rc=int(out.split('CURL_EXIT=')[-1].strip())
   expected_block=phase=='deny'
   passed=(rc in ((28,) if mode=='h3' else (28,35,56)) and 'HTTP 000' in out) if expected_block else (rc==0 and 'HTTP 200' in out)
   results.append(dict(phase=phase,mode=mode,trial=i,passed=passed,output=out));print(phase,mode,i,'PASS' if passed else 'FAIL',flush=True)
try:
 w.connect_all();w.baseline()
 cmd('preflight',"set -eu; test \"$(hostname -s)\" = netpro-test-gateway; tc qdisc show dev ens37 | grep -q 'netem 3901: parent 3900:3.*delay 15ms'; ! tc filter show dev ens38 ingress | grep -q 'pref 38999 '; ! iptables -S INPUT | grep -Fq "+q(comment))
 stage=cmd('stage','mktemp -d /home/netpro/incoming/router-enforcement.XXXXXX').strip()
 rollback=f'''#!/bin/bash
set -eu
test "$(hostname -s)" = netpro-test-gateway
if iptables -w 5 -C INPUT {rule} 2>/dev/null; then iptables -w 5 -D INPUT {rule}; fi
if test -e {stage}/filter-owned; then tc filter del dev ens38 ingress protocol ip pref 38999; rm -- {stage}/filter-owned; fi
if test -e {stage}/delay-owned; then tc qdisc change dev ens37 parent 3900:3 handle 3901: netem limit 1000 delay 15ms; rm -- {stage}/delay-owned; fi
'''
 cmd('stage-permission','chown netpro:netpro '+q(stage))
 with w.clients[GW].open_sftp() as f:
  with f.file(stage+'/rollback.sh','w') as out:out.write(rollback)
 cmd('arm-rollback',f'systemd-run --quiet --collect --unit={timer} --on-active=300s /bin/bash {stage}/rollback.sh');armed=True
 cmd('isolate-mechanism',f'''set -eu
touch {stage}/delay-owned
tc qdisc change dev ens37 parent 3900:3 handle 3901: netem limit 1000 delay 0ms
touch {stage}/filter-owned
tc filter add dev ens38 ingress protocol ip pref 38999 flower ip_proto udp src_ip 192.168.80.28 dst_ip 192.168.80.29 src_port 443 action drop
tc qdisc show dev ens37
''')
 probes('before')
 if not all(r['passed'] for r in results):raise RuntimeError('Allow baseline failed')
 w.create_policy();reconcile(True)
 probes('deny')
 counters=cmd('drop-counters',"iptables -w 5 -L INPUT -nvx | grep -F "+q(comment))
 (O/'drop-counters.txt').write_text(counters,encoding='utf8')
 assert int(counters.split()[0])>0,'No actual router drops'
 w.delete_policy_exactly();reconcile(False)
 probes('after');w.baseline()
finally:
 try:
  if armed:
   cmd('restore-lab','/bin/bash '+q(stage+'/rollback.sh'))
   cmd('disarm','systemctl stop '+q(timer+'.timer'))
  if w.policy_id:w.delete_policy_exactly()
 finally:
  (O/'results.json').write_text(json.dumps(results,indent=2),encoding='utf8');w.save()
  for c in w.clients.values():c.close()
  print('EVIDENCE',O,flush=True)
assert len(results)==30 and all(r['passed'] for r in results),'Acceptance failed'
print('PASS 30/30; delay restored; temporary firewall and injection-suppression rules removed',flush=True)
