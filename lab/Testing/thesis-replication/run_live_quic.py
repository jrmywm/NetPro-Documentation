"""Guarded live QUIC-v1 HTTP/3 replication. Temporary overrides, exact CRUD,
owned narrow return filter, bounded workloads and automatic rollback timers.
Configured PPS is a fresh-connection target, NOT a guaranteed packet rate.
"""
from pathlib import Path
import sys,json,time,shlex,datetime,traceback
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
import active_baseline as ab
from remote import connect_verified
from candidate_rollout import CandidateRollout
ab.TEST_DOMAIN='netpro-quic.test';ab.TEST_IP='192.0.2.124'
PS=ab.POLICY_HOST;GW=ab.GATEWAY_HOST;CL=ab.CLIENT_HOST;NPB='192.168.31.33'
TIMING_ONLY='--functional-only' in sys.argv
PACKET_REPLAY='--packet-replay' in sys.argv
OUT=BASE/'evidence'/(('quic-replay-dataplane-' if PACKET_REPLAY else 'quic-timing-http3-' if TIMING_ONLY else 'quic-live-http3-')+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
w=ab.ActiveBaseline('netpro',OUT,Path('C:/Users/jim/.ssh/known_hosts'))
rollouts=[];server=None;return_root=None;capture=None;client_capture=None;sampler=None;gwroot=None;clroot=None;psroot=None;failed=False;results=[];functional=[]
q=shlex.quote
def cmd(host,label,command,sudo=False,timeout=30,allow=False):
 return w.command(host,label,command,sudo=sudo,timeout=timeout,allow_failure=allow)[1].strip()
def put(host,local,remote):
 with w.clients[host].open_sftp() as s:s.put(str(local),remote)
def get(host,remote,local):
 with w.clients[host].open_sftp() as s:s.get(remote,str(local))
def stop(host,unit):
 cmd(host,'stop_'+unit,'systemctl stop '+unit+' || test "$(systemctl show '+unit+' -p LoadState --value)" = not-found',sudo=True)
def stats():
 # Stats are published once per second; wait for final post-workload publication.
 time.sleep(1.3)
 return json.loads(cmd(PS,'quic_stats','cat '+q(psroot+'/replication-stats.json'),sudo=True))
def client_trials(mode,count=5):
 for trial in range(1,count+1):
  rc,out,err=w.command(CL,'http3_'+mode+'_'+str(trial),'cd '+q(clroot)+' && '+q(clpython)+' http3_endpoint.py client --initial '+q('initial-'+mode+'-'+str(trial)+'.bin'),timeout=12,allow_failure=True)
  row=json.loads(out);row.update(mode=mode,trial=trial,exit=rc)
  row['class']='http_200' if row['http_status']=='200' and row['response_complete'] else 'policy_close' if (row['terminated'] or {}).get('reason')=='BLOCKED_BY_POLICY_SERVER' else 'other_failure'
  functional.append(row);(OUT/'functional.json').write_text(json.dumps(functional,indent=2),encoding='utf-8');print(mode,trial,row['class'],row['elapsed_s'],flush=True)
  if mode.startswith('allow') and row['class']!='http_200':raise RuntimeError('HTTP3 allow baseline failed')
def capture_start(label,interface='ens38',snap=160):
 unit='netpro-quic-cap-'+Path(gwroot).name+'.'+label;path=gwroot+'/'+label+'.pcap'
 packet_filter="udp and src host 192.168.80.28 and dst host 192.168.80.29 and src port 18443" if interface=='ens38' else "udp and host 192.168.80.28 and host 192.168.80.29 and port 18443"
 cmd(GW,'start_capture_'+label,'systemd-run --quiet --collect --unit='+unit+' --property=RuntimeMaxSec=120 /usr/bin/tcpdump -np -U -i '+interface+' -s '+str(snap)+' -w '+q(path)+' '+q(packet_filter),sudo=True)
 cmd(GW,'capture_ready_'+label,'for i in $(seq 1 15); do test -s '+q(path)+' && exit 0; sleep .2; done; exit 1',sudo=True)
 return unit,path,label
def capture_stop(c):
 stop(GW,c[0]);cmd(GW,'capture_journal_'+c[2],'journalctl -u '+c[0]+' --no-pager -n 10',sudo=True);get(GW,c[1],OUT/(c[2]+'.pcap'))
def client_capture_stop(c):
 stop(CL,c[0]);cmd(CL,'client_capture_journal','journalctl -u '+c[0]+' --no-pager -n 10',sudo=True);get(CL,c[1],OUT/'client-functional-deny.pcap')
try:
 w.connect_all();w.baseline()
 w.clients[NPB],npb_identity=connect_verified(NPB,'netpro','netpro',w.known_hosts)
 (OUT/'npb-identity.json').write_text(json.dumps(npb_identity,indent=2),encoding='utf-8')
 dirs=json.loads((BASE/'evidence/quic-endpoint-20261012T161202Z/directories.json').read_text())
 gwpython=dirs['gateway']+'/venv/bin/python';clpython=dirs['client']+'/venv/bin/python'
 for host,python in [(GW,gwpython),(CL,clpython)]:cmd(host,'verify_private_aioquic',q(python)+' -c '+q('import aioquic; assert aioquic.__version__=="1.3.0"; print(aioquic.__version__)'))
 gwroot=cmd(GW,'http3_server_directory','mktemp -d /home/netpro/incoming/thesis-http3-server.XXXXXX')
 clroot=cmd(CL,'http3_client_directory','mktemp -d /home/netpro/incoming/thesis-http3-client.XXXXXX')
 put(GW,BASE/'http3_endpoint.py',gwroot+'/http3_endpoint.py')
 for name in ['http3_endpoint.py','http3_load.py','raw_thesis_sender.py']:put(CL,BASE/name,clroot+'/'+name)
 cmd(GW,'guard_endpoint_port',"test -z \"$(ss -H -lun 'sport = :18443')\"; test -z \"$(ss -H -ltn 'sport = :18443')\"",sudo=True)
 cmd(GW,'make_private_certificate','cd '+q(gwroot)+' && openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 2 -subj /CN=netpro-quic.test >/dev/null 2>&1 && chmod 600 key.pem')
 server='netpro-'+Path(gwroot).name
 cmd(GW,'start_http3_endpoint','systemd-run --quiet --collect --unit='+server+' --uid=netpro --property=WorkingDirectory='+gwroot+' --property=RuntimeMaxSec=1200 '+q(gwpython)+' http3_endpoint.py server --duration 1200',sudo=True)
 cmd(GW,'endpoint_readiness',"for i in $(seq 1 20); do ss -H -lun 'sport = :18443' | grep -q '192.168.80.28:18443' && exit 0; sleep .3; done; exit 1",sudo=True)
 client_trials('allow-original')
 psroot=json.loads((BASE/'evidence/policy-thesis-build-20261012T232612Z/sources.json').read_text())['remote']
 nr=json.loads((BASE/'evidence/npb-quic-candidate-20261012T162141Z/sources.json').read_text())['remote']
 for host,hostname,unit,binary,sha,original,env in [
  (PS,'policy-server-vm','netpro-policy',psroot+'/policyServer-thesis-candidate','d74c18645a077a9435f84c9a05cdb0c407c0415ce3cb65550db1113ff4d410a4','5892e752bb08395b2b3b1170fc9e45af21ac9251b7dfc9860a7b28dde0865614',{'NETPRO_SNMP_ENABLE':'0','NETPRO_REPLICATION_STATS_PATH':psroot+'/replication-stats.json'}),
  (NPB,'npb-vm','netpro-npb',nr+'/packetBroker-quic-candidate','3cde672b35005895a3121ce50ad892b98a5b1a935c0e60bfcd1ee2f7883fe760','607a680272458c2dad46e7caf16751990632415c940401f4fbfac68e88196430',{})]:
  r=CandidateRollout(w.clients[host],hostname,unit,binary,sha,original,OUT,env);rollouts.append(r);r.start()
 cmd(GW,'guard_idle_udp_return',"test \"$(cat /sys/class/net/ens38/address)\" = 00:0c:29:34:73:d6; test \"$(cat /sys/class/net/ens38/operstate)\" = down; test -z \"$(tc filter show dev ens38 ingress)\"; test -z \"$(tc filter show dev ens38 egress)\"",sudo=True)
 return_root=cmd(GW,'return_directory','mktemp -d /home/netpro/incoming/thesis-udp-return.XXXXXX')
 had_clsact=bool(cmd(GW,'original_return_qdisc','tc qdisc show dev ens38',sudo=True).find('clsact')>=0)
 timer='netpro-'+Path(return_root).name
 restore='''#!/bin/bash
set -euo pipefail
test "$(hostname -s)" = netpro-test-gateway
test "$(cat /sys/class/net/ens38/address)" = 00:0c:29:34:73:d6
tc filter del dev ens38 ingress protocol ip pref 39001 2>/dev/null || true
'''
 if not had_clsact:restore+='if test -z "$(tc filter show dev ens38 ingress)" && test -z "$(tc filter show dev ens38 egress)"; then tc qdisc del dev ens38 clsact 2>/dev/null || true; fi\n'
 restore+='ip link set dev ens38 promisc off down\n'
 with w.clients[GW].open_sftp() as s:
  with s.file(return_root+'/restore.sh','w') as f:f.write(restore)
 cmd(GW,'arm_return_rollback','systemd-run --quiet --collect --unit='+timer+' --on-active=1200s /bin/bash '+q(return_root+'/restore.sh'),sudo=True)
 if not had_clsact:cmd(GW,'add_owned_clsact','tc qdisc add dev ens38 clsact',sudo=True)
 cmd(GW,'enable_narrow_udp_return','ip link set dev ens38 up promisc on\ntc filter add dev ens38 ingress protocol ip pref 39001 flower src_mac 00:0c:29:34:73:cc dst_mac 00:0c:29:91:39:14 ip_proto udp src_ip 192.168.80.28 dst_ip 192.168.80.29 src_port 18443 action mirred egress redirect dev ens37',sudo=True)
 cmd(GW,'record_udp_return_filter','tc -s filter show dev ens38 ingress',sudo=True)
 before=stats();client_trials('allow-candidate');after=stats()
 get(CL,clroot+'/initial-allow-candidate-1.bin',OUT/'validated-client-initial.bin')
 (OUT/'allow-candidate-metrics.json').write_text(json.dumps({'before':before,'after':after},indent=2),encoding='utf-8')
 if after['quic_positive']<=before['quic_positive']:raise RuntimeError('No valid QUIC Initial reached candidate PS; do not label end-to-end test')
 w.create_policy();capture=capture_start('functional-deny','any',0)
 cu='netpro-quic-client-cap-'+Path(clroot).name;cp=clroot+'/client-functional-deny.pcap';client_capture=(cu,cp)
 cmd(CL,'start_client_timing_capture','systemd-run --quiet --collect --unit='+cu+' --property=RuntimeMaxSec=40 /usr/bin/tcpdump -np -U -i ens37 -s 0 -w '+q(cp)+" 'udp and host 192.168.80.28 and host 192.168.80.29 and port 18443'",sudo=True)
 cmd(CL,'client_timing_capture_readiness','for i in $(seq 1 15); do journalctl -u '+cu+" --no-pager -n 8 | grep -q 'listening on ens37' && exit 0; sleep .2; done; exit 1",sudo=True)
 client_trials('deny',10);client_capture_stop(client_capture);client_capture=None;capture_stop(capture);capture=None
 sr=cmd(PS,'resource_sampler_directory','mktemp -d /home/netpro/incoming/thesis-quic-resource.XXXXXX');put(PS,BASE/'live_resource_sampler.py',sr+'/sampler.py');sampler=('netpro-'+Path(sr).name,sr)
 cmd(PS,'start_quic_resources','pid=$(systemctl show netpro-policy -p MainPID --value); systemd-run --quiet --collect --unit='+sampler[0]+' --uid=netpro --property=RuntimeMaxSec=900 /usr/bin/python3 '+q(sr+'/sampler.py')+' "$pid" '+q(sr+'/samples.jsonl'),sudo=True)
 for pps in ([] if TIMING_ONLY else [100,200,500,1000,1500]):
  for trial in range(1,4):
   label='p'+str(pps)+'-t'+str(trial);before=stats();capture=capture_start(label)
   if PACKET_REPLAY:
    output=cmd(CL,'replay_'+label,'cd '+q(clroot)+' && /usr/bin/python3 -u raw_thesis_sender.py quic --fixture initial-allow-candidate-1.bin --pps '+str(pps)+' --seconds 30',sudo=True,timeout=45)
    row=json.loads(output);row.update(scheduling_elapsed_s=row['elapsed_s'],started_requests=0,achieved_request_starts_per_s=0,policy_close=0,http_200=0,timeout=0,other=0,skipped_inflight_limit=0)
    (OUT/(label+'.json')).write_text(json.dumps(row,indent=2),encoding='utf-8')
   else:
    output=cmd(CL,'load_'+label,'cd '+q(clroot)+' && '+q(clpython)+' -u http3_load.py --pps '+str(pps)+' --seconds 30 --output '+q(label+'.json'),timeout=100)
    row=json.loads(output);get(CL,clroot+'/'+label+'.json',OUT/(label+'.json'))
   after=stats();capture_stop(capture);capture=None
   delta={k:after[k]-before[k] for k in ['udp_seen','quic_positive','quic_blocked','close_crafted','close_sent','close_errors']}
   row.update(trial=trial,metrics=delta,close_sent_per_positive=delta['close_sent']/delta['quic_positive'] if delta['quic_positive'] else None,client_confirmed_close_fraction=row['policy_close']/row['started_requests'] if row['started_requests'] else None)
   results.append(row);(OUT/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(row),flush=True)
 w.delete_policy_exactly();client_trials('allow-restored')
 cmd(GW,'final_udp_return_stats','tc -s filter show dev ens38 ingress',sudo=True)
except Exception as e:
 failed=True;(OUT/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8');print('STOP:',e,flush=True)
finally:
 errors=[]
 def clean(label,fn):
  try:fn()
  except Exception as e:errors.append(label+': '+str(e))
 if capture:clean('capture',lambda:capture_stop(capture))
 if client_capture:clean('client timing capture',lambda:client_capture_stop(client_capture))
 if sampler:
  clean('sampler stop',lambda:stop(PS,sampler[0]));clean('resource download',lambda:get(PS,sampler[1]+'/samples.jsonl',OUT/'resource-samples.jsonl'))
 if w.policy_id and not w.policy_deleted:clean('exact policy delete',w.delete_policy_exactly)
 if return_root:
  clean('return restore',lambda:cmd(GW,'restore_owned_udp_return','/bin/bash '+q(return_root+'/restore.sh'),sudo=True))
  clean('return timer stop',lambda:stop(GW,timer+'.timer'))
 for r in reversed(rollouts):clean('original '+r.unit,r.stop)
 if server:clean('http3 server stop',lambda:stop(GW,server))
 if w.clients:
  clean('final policy baseline',w.baseline)
 (OUT/'cleanup.json').write_text(json.dumps({'failed':failed,'errors':errors,'temporary_rule_deleted':w.policy_deleted},indent=2),encoding='utf-8')
 for c in w.clients.values():c.close()
 print('EVIDENCE:',OUT,'cleanup errors:',errors,flush=True)
raise SystemExit(1 if failed or errors else 0)
