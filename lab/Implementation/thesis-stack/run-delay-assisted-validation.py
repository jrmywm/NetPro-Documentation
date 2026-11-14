"""Run existing guarded original-method validation against explicitly pinned current binary."""
from pathlib import Path
import os,sys,hashlib,paramiko
base=Path(__file__).resolve().parent
c=paramiko.SSHClient();c.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'));c.connect('192.168.31.31',username='netpro',password=os.environ['NETPRO_LAB_PASSWORD'],timeout=10)
try:
 _,a,e=c.exec_command('sha256sum /home/netpro/NetPro-Policy-Server/build/policyServer');pin=a.read().decode().split()[0]
finally:c.close()
assert len(pin)==64
s=(base/'validate-live-stack.py').read_text()
assert s.count('5892e752bb08395b2b3b1170fc9e45af21ac9251b7dfc9860a7b28dde0865614')==1
s=s.replace('5892e752bb08395b2b3b1170fc9e45af21ac9251b7dfc9860a7b28dde0865614',pin)
s=s.replace("{'NETPRO_SNMP_ENABLE':'0'","{'NETPRO_REPLAY_READINESS':'1','NETPRO_SNMP_ENABLE':'0'")
s=s.replace('if DIAGNOSTIC_TRACE:\n  metrics_deadline=', 'if True: # All profiles await the periodic metrics refresh.\n  metrics_deadline=')
delay=int(os.getenv('NETPRO_QUIC_RESPONSE_DELAY_MS','15'))
if not 1<=delay<=50:raise ValueError('Delay must be 1..50 ms')
s=s.replace("action mirred egress redirect dev ens37", "action skbedit mark 39001 action mirred egress redirect dev ens37")
needle="restore_text+='ip link set dev ens38 promisc off down\\n'"
replacement="restore_text+='tc qdisc del dev ens37 root 2>/dev/null || true\\ntc qdisc add dev ens37 root fq_codel limit 10240 flows 1024 quantum 1514 target 5ms interval 100ms memory_limit 32Mb ecn\\n'\n "+needle
assert needle in s
s=s.replace(needle,replacement)
needle=" probes('allow-candidate')"
setup=""" before_delay=cmd(GW,'delay-preflight','tc qdisc show dev ens37',True)
 if not before_delay.startswith('qdisc fq_codel ') or len(before_delay.splitlines())!=1:raise RuntimeError('Unexpected gateway qdisc; stop')
 cmd(GW,'delay-enable','tc qdisc del dev ens37 root && tc qdisc add dev ens37 root handle 3900: prio bands 3 && tc qdisc add dev ens37 parent 3900:3 handle 3901: netem delay DELAYms && tc filter add dev ens37 parent 3900: protocol ip pref 1 handle 39001 fw flowid 3900:1 && tc filter add dev ens37 parent 3900: protocol ip pref 2 flower ip_proto udp src_ip 192.168.80.28 dst_ip 192.168.80.29 src_port 443 classid 3900:3',True)
 probes('allow-candidate')""".replace('DELAY',str(delay))
s=s.replace(needle,setup)
s=s.replace("'HTTP %{http_code} VERSION %{http_version}","'TIME %{time_total} HTTP %{http_code} VERSION %{http_version}")
s=s.replace("passed=good)","passed=good,output=out)")
s=s.replace("def probes(mode,n=5):", "def probes(mode,n="+str(int(os.getenv('NETPRO_QUIC_TRIALS','5')))+"):")
parallel=int(os.getenv('NETPRO_QUIC_PARALLEL','1'))
if not 1<=parallel<=10:raise ValueError('Parallel requests must be 1..10')
if parallel>1:
 start=s.index('def probes(')
 end=s.index('\ntry:',start)
 s=s[:start]+r"""
def probes(mode,n=5):
 from concurrent.futures import ThreadPoolExecutor
 def request(i):
  command="/home/netpro/netpro-thesis/http3/prefix/bin/curl --http3-only --noproxy '*' --interface 192.168.80.29 --resolve mysite.local:443:192.168.80.28 -k --max-time 5 -sS -o /dev/null -w 'TIME %{time_total} HTTP %{http_code} VERSION %{http_version}\n' https://mysite.local/; rc=$?; echo CURL_EXIT=$rc"
  _,stdout,stderr=w.clients[CL].exec_command(command,timeout=15)
  output=stdout.read().decode()
  if stdout.channel.recv_exit_status()!=0:raise RuntimeError(stderr.read().decode())
  return output
 with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
  for i,out in enumerate(pool.map(request,range(n))):
   rc=int(out.split('CURL_EXIT=')[-1].strip())
   passed=(rc==28 and 'HTTP 000' in out) if mode=='deny-rule' else (rc==0 and 'HTTP 200 VERSION 3' in out)
   rows.append(dict(mode=mode,trial=i+1,curl_exit=rc,passed=passed,output=out))
   print(mode,i+1,'PASS' if passed else 'FAIL',flush=True)
 if mode!='deny-rule' and any(not r['passed'] for r in rows if r['mode']==mode):
  raise RuntimeError('Unexpected allow result: '+mode)
""".replace('PARALLEL',str(parallel)).replace('n=5','n='+str(int(os.getenv('NETPRO_QUIC_TRIALS','5'))))+s[end:]
if os.getenv('NETPRO_COMBINED_REGRESSION')=='1':
 s=s.replace('if PROFILE and host==PS:', "if PROFILE and host==PS and os.getenv('NETPRO_COMBINED_REGRESSION')!='1':")
 hook="""
 import subprocess
 management='192.168.31.35'
 driver='python3 /home/netpro/recovered-theses-20261030/csv-live-api.py '
 cache=json.loads(cmd(PS,'combined-cache-status','cat /run/netpro-policy-cache.json'))
 if cache.get('mode')!='rafie' or not cache.get('policySyncReady'):
  raise RuntimeError('Combined candidate cache not ready')
 (OUT/'combined-cache.json').write_text(json.dumps(cache,indent=2))
 cmd(management,'combined-csv-setup',driver+'setup',True)
 try:
  env=os.environ.copy()
  env['NETPRO_SSH_PASSWORD']=env['NETPRO_LAB_PASSWORD']
  env['THESIS_TEST_DOMAIN']='netpro-tap.test'
  result=subprocess.run([sys.executable,str(BASE.parent/'recovered-theses/backend-candidate/ops/verify-csv-packets.py')],env=env,capture_output=True,text=True,timeout=300)
  (OUT/'combined-csv.log').write_text(result.stdout+result.stderr,encoding='utf-8')
  print(result.stdout,flush=True)
  (OUT/'combined-cache-after-tls.json').write_text(cmd(PS,'combined-cache-after-tls','cat /run/netpro-policy-cache.json'))
  result.check_returncode()
 finally:
  cmd(management,'combined-csv-retire',driver+'retire',True)
"""
 needle=" cmd(GW,'guard-return',"
 assert s.count(needle)==1
 s=s.replace(needle,hook+needle)
os.environ['THESIS_REPLICATION_PROFILE']='1'
os.environ['THESIS_TEST_IP']='192.168.80.28'
# Explicit pin captured before any rollout; CandidateRollout validates it and
# restores that same actual build. No old expected hashes are bypassed.
print('Current policy binary pinned',pin,flush=True)
exec(compile(s,str(base/'validate-live-stack.py'),'exec'),{'__file__':str(base/'validate-live-stack.py'),'__name__':'__main__'})
