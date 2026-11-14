"""Temporary guarded full-path Caddy/curl validation; originals restored on exit."""
from pathlib import Path
import sys,json,datetime,shlex,time,re,os
BASE=Path(__file__).resolve().parent; TEST=BASE.parents[1]/'Testing'
sys.path.insert(0,str(TEST/'snmp-quic-integration'));sys.path.insert(0,str(TEST/'thesis-replication'))
import active_baseline as ab
from remote import connect_verified
from candidate_rollout import CandidateRollout
ab.TEST_DOMAIN=os.getenv('THESIS_TEST_DOMAIN','mysite.local');ab.TEST_IP=os.getenv('THESIS_TEST_IP','192.0.2.124')
PS='192.168.31.31';NPB='192.168.31.33';GW='192.168.31.37';CL='192.168.31.39'
PROFILE=os.getenv('THESIS_REPLICATION_PROFILE')=='1'
DIAGNOSTIC_TRACE=os.getenv('THESIS_DIAGNOSTIC_TRACE')=='1'
INLINE_DROP=os.getenv('THESIS_INLINE_DROP_DIAGNOSTIC')=='1'
DIRECT=os.getenv('THESIS_DIRECT_TOPOLOGY')=='1'
DIRECT_OBSERVE=DIRECT or os.getenv('THESIS_DIRECT_OBSERVE')=='1'
DIRECT_INJECT=DIRECT or os.getenv('THESIS_DIRECT_INJECT')=='1'
PROFILE_NAME=('inline-drop' if INLINE_DROP else 'direct-both' if DIRECT else 'direct-observe' if DIRECT_OBSERVE else 'direct-inject' if DIRECT_INJECT else 'full-path')
OUT=BASE/'evidence'/(('live-'+PROFILE_NAME+'-' if PROFILE_NAME!='full-path' else 'live-thesis-profile-' if PROFILE else 'live-original-stack-')+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
w=ab.ActiveBaseline('netpro',OUT,Path('C:/Users/jim/.ssh/known_hosts'));rollouts=[];restore=None;timer=None;npb=None;rows=[];error=None;captures=[];trace_remote=None;qlog_remote=None
q=shlex.quote
def cmd(h,label,s,sudo=False,timeout=60):return w.command(h,label,s,sudo=sudo,timeout=timeout)[1]
def probes(mode,n=5):
 if DIAGNOSTIC_TRACE:n=1
 for i in range(n):
  command="/home/netpro/netpro-thesis/http3/prefix/bin/curl --http3-only --noproxy '*' --interface 192.168.80.29 --resolve mysite.local:443:192.168.80.28 -k --connect-timeout 3 --max-time 5 -v -o /dev/null -w 'HTTP %{http_code} VERSION %{http_version}\\n' https://mysite.local/; rc=$?; echo CURL_EXIT=$rc"
  if DIAGNOSTIC_TRACE and mode=='deny-rule':
   global trace_remote,qlog_remote
   trace_remote='/home/netpro/incoming/netpro-quic-deny-'+OUT.name+'.trace'
   qlog_remote=cmd(CL,'qlog-stage','mktemp -d /home/netpro/incoming/quic-qlog.XXXXXX').strip()
   command='QLOGDIR='+q(qlog_remote)+' '+command
   command=command.replace(' -v -o ', ' --trace-time --trace-ids --trace-ascii '+q(trace_remote)+' -o ')
  if PROFILE and not DIAGNOSTIC_TRACE:command=command.replace('--http3-only','--http3').replace('--connect-timeout 3 ','')
  out=cmd(CL,f'{mode}-{i+1}',command,timeout=12)
  rc=int(out.split('CURL_EXIT=')[-1].strip());good=(rc==0 and 'HTTP 200 VERSION 3' in out) if mode.startswith('allow') else (rc!=0 and 'HTTP 000' in out)
  rows.append(dict(mode=mode,trial=i+1,curl_exit=rc,passed=good));print(mode,i+1,'CURL_EXIT',rc,'PASS' if good else 'FAIL',flush=True)
  if not good and not (PROFILE and mode=='deny-rule'):raise RuntimeError('Unexpected HTTP3 result: '+mode)
try:
 w.connect_all();w.baseline()
 npb,_=connect_verified(NPB,'netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'));w.clients[NPB]=npb
 probes('allow-original',3)
 build=sorted((BASE/'evidence').glob('original-candidate-build-*'))[-1]
 sources=json.loads((build/'sources.json').read_text());psroot=sources['remote']
 sha=re.search(r'([0-9a-f]{64})  policyServer-original-thesis',json.loads((build/'build.json').read_text())['stdout']).group(1)
 # Keep monitoring CLI original synchronous; custom async reporter is disabled.
 configs=[(PS,'policy-server-vm','netpro-policy',psroot+'/policyServer-original-thesis',sha,'5892e752bb08395b2b3b1170fc9e45af21ac9251b7dfc9860a7b28dde0865614',{'NETPRO_SNMP_ENABLE':'0','NETPRO_THESIS_SNMP_TARGET':'192.168.31.35','NETPRO_REPLICATION_STATS_PATH':psroot+'/replication-stats.json'}),(NPB,'npb-vm','netpro-npb','/home/netpro/incoming/npb-quic-candidate.jsL9uV/packetBroker-quic-candidate','3cde672b35005895a3121ce50ad892b98a5b1a935c0e60bfcd1ee2f7883fe760','607a680272458c2dad46e7caf16751990632415c940401f4fbfac68e88196430',{})]
 for host,hostname,unit,binary,sha,original,env in configs:
  if DIRECT_OBSERVE and host==NPB:continue
  if PROFILE and host==PS:
   env['NETPRO_THESIS_SNMP_DOMAIN_ENABLE']='0'
   env.pop('NETPRO_THESIS_SNMP_TARGET',None)
  r=CandidateRollout(w.clients[host],hostname,unit,binary,sha,original,OUT,env);rollouts.append(r);r.start()
 cmd(GW,'guard-return',"test \"$(cat /sys/class/net/ens38/address)\" = 00:0c:29:34:73:d6 && test \"$(cat /sys/class/net/ens38/operstate)\" = down && test -z \"$(tc filter show dev ens38 ingress)\"",True)
 root=cmd(GW,'stage-return','mktemp -d /home/netpro/incoming/original-stack-return.XXXXXX').strip()
 had_clsact='clsact' in cmd(GW,'qdisc-before','tc qdisc show dev ens38',True)
 restore=root+'/restore.sh';timer='netpro-'+Path(root).name
 restore_text='#!/bin/bash\nset -eu\ntest "$(cat /sys/class/net/ens38/address)" = 00:0c:29:34:73:d6\ntc filter del dev ens38 ingress protocol ip pref 39001 2>/dev/null || true\n'
 tcp_rule='-i ens37 -s 192.168.80.29 -d 192.168.80.28 -p tcp --dport 443 -m comment --comment '+timer+' -j DROP'
 udp_rule='-i ens37 -s 192.168.80.29 -d 192.168.80.28 -p udp --dport 443 -m comment --comment '+timer+'-udp -j DROP'
 if PROFILE:restore_text+='iptables -D INPUT '+tcp_rule+' 2>/dev/null || true\n'
 if INLINE_DROP:restore_text+='iptables -D INPUT '+udp_rule+' 2>/dev/null || true\n'
 if not had_clsact and not DIRECT:restore_text+='if test -z "$(tc filter show dev ens38 ingress)" && test -z "$(tc filter show dev ens38 egress)"; then tc qdisc del dev ens38 clsact; fi\n'
 restore_text+='ip link set dev ens38 promisc off down\n'
 with w.clients[GW].open_sftp() as s:
  with s.file(restore,'w') as f:f.write(restore_text)
 cmd(GW,'return-rollback-timer','systemd-run --quiet --collect --unit='+timer+' --on-active=900s /bin/bash '+q(restore),True)
 if not had_clsact and not DIRECT_INJECT:cmd(GW,'return-qdisc','tc qdisc add dev ens38 clsact',True)
 if not DIRECT_INJECT:cmd(GW,'return-setup','ip link set dev ens38 up promisc on\ntc filter add dev ens38 ingress protocol ip pref 39001 flower src_mac 00:0c:29:34:73:cc dst_mac 00:0c:29:91:39:14 ip_proto udp src_ip 192.168.80.28 dst_ip 192.168.80.29 src_port 443 action mirred egress redirect dev ens37',True)
 if PROFILE:cmd(GW,'thesis-no-tcp-fallback','iptables -I INPUT 1 '+tcp_rule,True)
 probes('allow-candidate')
 policy=w.create_policy()
 capture_targets=([(CL,'ens37')] if DIRECT_INJECT else [(CL,'ens37'),(GW,'ens38')])
 if INLINE_DROP:capture_targets.append((GW,'ens37'))
 for host,iface in capture_targets:
  caproot=cmd(host,'capture-stage','mktemp -d /home/netpro/incoming/quic-close-capture.XXXXXX').strip()
  path=caproot+'/capture.pcap';unit='netpro-'+Path(caproot).name
  cmd(host,'capture-start','systemd-run --quiet --collect --unit='+unit+' /usr/bin/timeout 90 /usr/bin/tcpdump -U -ni '+iface+' -s0 -w '+q(path)+" 'port 443'",True)
  captures.append((host,path,unit))
 time.sleep(1)
 if INLINE_DROP:cmd(GW,'inline-drop-add','iptables -I INPUT 1 '+udp_rule,True)
 probes('deny-rule')
 if INLINE_DROP:
  cmd(GW,'inline-drop-counters','iptables -nvL INPUT --line-numbers',True)
  cmd(GW,'inline-drop-remove','iptables -D INPUT '+udp_rule,True)
 if trace_remote:
  with w.clients[CL].open_sftp() as s:s.get(trace_remote,str(OUT/'client-curl-deny.trace'))
 if qlog_remote:
  listing=cmd(CL,'qlog-list','find '+q(qlog_remote)+' -maxdepth 1 -type f').splitlines()
  with w.clients[CL].open_sftp() as ftp:
   for remote_path in listing:ftp.get(remote_path,str(OUT/Path(remote_path).name))
 metrics=json.loads(cmd(PS,'deny-metrics','cat '+q(psroot+'/replication-stats.json')))
 if DIAGNOSTIC_TRACE:
  metrics_deadline=time.monotonic()+15
  while metrics.get('quic_close_tx_accepted',metrics.get('close_sent',0))<(1 if DIAGNOSTIC_TRACE else 5) and time.monotonic()<metrics_deadline:
   time.sleep(.5)
   metrics=json.loads(cmd(PS,'deny-metrics-poll','cat '+q(psroot+'/replication-stats.json')))
 if not INLINE_DROP and metrics.get('quic_close_tx_accepted',metrics.get('close_sent',0))<(1 if DIAGNOSTIC_TRACE else 5):raise RuntimeError('Insufficient Close TX counters; inspect metrics')
 cmd(GW,'deny-return-counters','tc -s filter show dev ens38 ingress',True)
 w.delete_policy_exactly();probes('allow-after-delete')
 if PROFILE:
  cmd(GW,'no-tcp-fallback-counters','iptables -nvL INPUT --line-numbers',True)
  if any(not r['passed'] for r in rows):error='Thesis-profile functional deny failed; retain measured results'
 # Verify genuine 120-second periodic summary from the running original CLI hook.
 if not PROFILE:print('Waiting for genuine 120-second summary; no shortened interval.',flush=True)
 deadline=time.monotonic()+130
 while not PROFILE and time.monotonic()<deadline:
  out=cmd('192.168.31.35','summary-check','sudo -S -p "" tail -n 120 /var/lib/zabbix/snmptraps/snmptraps.log',True)
  if 'packets after 2 minutes' in out:break
  time.sleep(5)
 else:
  if not PROFILE:raise RuntimeError('120-second original summary not received')
 if not PROFILE:print('ORIGINAL_SNMP_120_SECOND_SUMMARY=PASS',flush=True)
except Exception as exc:error=str(exc);print('FAIL',error,flush=True)
finally:
 # Let the capture buffer drain before interrupting tcpdump.
 if captures:time.sleep(2)
 for host,path,unit in captures:
  try:
   w.command(host,'capture-stop','systemctl kill --signal=SIGINT '+unit+'.service',sudo=True,timeout=15,allow_failure=True)
   time.sleep(.5)
   with w.clients[host].open_sftp() as s:s.get(path,str(OUT/(host+'-close.pcap')))
  except Exception as exc:print('Capture retrieval:',str(exc),flush=True)
 if rollouts:
  try:
   cmd(GW,'final-return-counters','tc -s filter show dev ens38 ingress',True)
   cmd(PS,'final-candidate-metrics','cat '+q(psroot+'/replication-stats.json'))
  except Exception as exc:print('Final diagnostics:',str(exc),flush=True)
 try:
  if w.policy_id:w.delete_policy_exactly()
 except Exception as exc:error=(error or '')+' cleanup policy: '+str(exc)
 if restore:
  try:
   cmd(GW,'restore-return','bash '+q(restore),True)
   cmd(GW,'cancel-return-timer','systemctl stop '+timer+'.timer',True)
  except Exception as exc:error=(error or '')+' return cleanup: '+str(exc)
 if trace_remote:
  try:cmd(CL,'trace-cleanup','rm -f '+q(trace_remote))
  except Exception as exc:print('Trace cleanup:',str(exc),flush=True)
 for r in reversed(rollouts):
  try:r.stop()
  except Exception as exc:error=(error or '')+' rollout cleanup: '+str(exc)
 (OUT/'summary.json').write_text(json.dumps(dict(passed=not error,error=error,trials=rows),indent=2),encoding='utf-8')
 w.save()
 for c in w.clients.values():c.close()
 print('EVIDENCE',OUT,flush=True)
if error:raise SystemExit(error)
