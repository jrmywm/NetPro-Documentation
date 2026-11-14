"""Live HTTP->virtual TAP->NPB->PS->SNMP receiver thesis workload.
Temporary candidate rollout only; preserve existing DB/API policies and restore
the original service. HTTP fixtures are segments, not established sessions.
"""
from pathlib import Path
import sys,json,datetime,shlex,time,hashlib,struct
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import run_remote_command
from active_baseline import ActiveBaseline,POLICY_HOST,BACKEND_HOST,CLIENT_HOST,GATEWAY_HOST
from candidate_rollout import CandidateRollout
OUT=BASE/'evidence'/('snmp-live-http-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
workflow=ActiveBaseline('netpro',OUT,Path('C:/Users/jim/.ssh/known_hosts'))
rollout=None;receiver_unit=None;capture_unit=None;receiver_root=None;gateway_root=None;client_root=None;sampler_unit=None;sampler_root=None;failed=False;results=[]
def cmd(host,label,command,sudo=False,timeout=30):return workflow.command(host,label,command,sudo=sudo,timeout=timeout)[1].strip()
def read_json(host,path):return json.loads(cmd(host,'read_'+Path(path).name,'cat '+shlex.quote(path),sudo=True))
def receive_state():return read_json(BACKEND_HOST,receiver_root+'/receiver-state.json')
def wait_domain_count(count):
 deadline=time.monotonic()+8
 while time.monotonic()<deadline:
  state=receive_state()
  if state['domain_events']>=count:return state
  time.sleep(.4)
 return receive_state()
try:
 workflow.connect_all();workflow.baseline()
 build=sorted((BASE/'evidence').glob('policy-thesis-build-*'))[-1]
 execution=json.loads((build/'execution.json').read_text());assert execution['exit']==0
 candidate_root=json.loads((build/'sources.json').read_text())['remote']
 candidate_sha=execution['stdout'].split()[0]
 private=json.loads((sorted((BASE/'evidence').glob('snmp-sender-bench-*'))[-1]/'sources.json').read_text())['remote_directory']+'/private'
 receiver_root=cmd(BACKEND_HOST,'receiver_private_directory','mkdir -p /home/netpro/incoming; mktemp -d /home/netpro/incoming/thesis-snmp-receiver.XXXXXX')
 archive=cmd(POLICY_HOST,'receiver_archive_path','mktemp /home/netpro/incoming/snmp-runtime.XXXXXX.tar.gz')
 staged=cmd(POLICY_HOST,'stage_receiver_runtime','mktemp -d /home/netpro/incoming/snmp-receiver-portable.XXXXXX')
 portable='cd '+shlex.quote(staged)+' && set -eu\n'+r'''
mkdir private
cp -a PRIVATE/. private/
for package in libperl5.30 libssl1.1; do
 v=$(dpkg-query -W -f='${Version}' "$package")
 apt-get download "$package=$v" >"download-$package.log" 2>&1
 deb=$(find . -maxdepth 1 -name "${package}_*.deb" -print)
 test -n "$deb"
 test "$(sha256sum "$deb" | cut -d' ' -f1)" = "$(apt-cache show "$package=$v" | awk '$1=="SHA256:" {print $2;exit}')"
 dpkg-deb -x "$deb" private
done
tar -czf ARCHIVE -C private .
'''.replace('PRIVATE',shlex.quote(private)).replace('ARCHIVE',shlex.quote(archive))
 cmd(POLICY_HOST,'archive_validated_runtime',portable,timeout=60)
 local_archive=OUT/'receiver-runtime.tar.gz'
 with workflow.clients[POLICY_HOST].open_sftp() as s:s.get(archive,str(local_archive))
 with workflow.clients[BACKEND_HOST].open_sftp() as s:
  s.put(str(local_archive),receiver_root+'/runtime.tar.gz');s.put(str(BASE/'live_snmp_receiver.py'),receiver_root+'/live_snmp_receiver.py')
 sha=hashlib.sha256(local_archive.read_bytes()).hexdigest()
 cmd(BACKEND_HOST,'extract_receiver_private_runtime','cd '+shlex.quote(receiver_root)+" && test \"$(sha256sum runtime.tar.gz | cut -d' ' -f1)\" = "+sha+' && mkdir private && tar -xzf runtime.tar.gz -C private')
 receiver_unit='netpro-'+Path(receiver_root).name
 cmd(BACKEND_HOST,'start_owned_receiver','systemd-run --quiet --collect --unit='+receiver_unit+' --uid=netpro --property=RuntimeMaxSec=1500 /usr/bin/python3 -u '+shlex.quote(receiver_root+'/live_snmp_receiver.py'),sudo=True)
 cmd(BACKEND_HOST,'receiver_readiness',"for i in $(seq 1 10); do if ss -H -lun 'sport = :11623' | awk '$4==\"192.168.31.35:11623\" {found=1} END {exit !found}'; then exit 0; fi; sleep .5; done; exit 1",sudo=True)
 rollout=CandidateRollout(workflow.clients[POLICY_HOST],'policy-server-vm','netpro-policy',candidate_root+'/policyServer-thesis-candidate',candidate_sha,'5892e752bb08395b2b3b1170fc9e45af21ac9251b7dfc9860a7b28dde0865614',OUT,{'NETPRO_SNMP_ENABLE':'1','NETPRO_SNMP_MANAGER_IPV4':'192.168.31.35','NETPRO_SNMP_MANAGER_PORT':'11623','NETPRO_SNMP_COMMUNITY':'public','NETPRO_REPLICATION_STATS_PATH':candidate_root+'/replication-stats.json'})
 rollout.start();workflow.create_policy()
 sampler_root=cmd(POLICY_HOST,'resource_sampler_directory','mktemp -d /home/netpro/incoming/thesis-resource-samples.XXXXXX')
 with workflow.clients[POLICY_HOST].open_sftp() as s:s.put(str(BASE/'live_resource_sampler.py'),sampler_root+'/live_resource_sampler.py')
 sampler_unit='netpro-'+Path(sampler_root).name
 cmd(POLICY_HOST,'start_resource_sampler','pid=$(systemctl show netpro-policy -p MainPID --value); systemd-run --quiet --collect --unit='+sampler_unit+' --uid=netpro --property=RuntimeMaxSec=600 /usr/bin/python3 '+shlex.quote(sampler_root+'/live_resource_sampler.py')+' "$pid" '+shlex.quote(sampler_root+'/samples.jsonl'),sudo=True)
 client_root=cmd(CLIENT_HOST,'sender_directory','mktemp -d /home/netpro/incoming/thesis-http-sender.XXXXXX')
 with workflow.clients[CLIENT_HOST].open_sftp() as s:s.put(str(BASE/'raw_thesis_sender.py'),client_root+'/raw_thesis_sender.py')
 # Observe only the dedicated PS return wire; do not reinject these fixtures.
 gateway_root=cmd(GATEWAY_HOST,'capture_directory','mktemp -d /home/netpro/incoming/thesis-reset-capture.XXXXXX')
 cmd(GATEWAY_HOST,'guard_idle_return_interface',"test \"$(cat /sys/class/net/ens38/address)\" = 00:0c:29:34:73:d6; ip -br link show ens38; test \"$(cat /sys/class/net/ens38/operstate)\" = down; test -z \"$(tc filter show dev ens38 ingress)\"",sudo=True)
 cmd(GATEWAY_HOST,'enable_owned_capture_interface','ip link set dev ens38 up promisc on',sudo=True)
 capture_unit='netpro-'+Path(gateway_root).name
 cmd(GATEWAY_HOST,'start_reset_wire_capture','systemd-run --quiet --collect --unit='+capture_unit+' --property=RuntimeMaxSec=600 /usr/bin/tcpdump -np -i ens38 -s 96 -w '+shlex.quote(gateway_root+'/resets.pcap')+" 'tcp and src host 192.168.80.28 and dst host 192.168.80.29 and src port 8080 and tcp[tcpflags] & tcp-rst != 0'",sudo=True)
 start=time.monotonic()
 def send_batch(count,trial):
  before=receive_state();stats_before=read_json(POLICY_HOST,candidate_root+'/replication-stats.json')
  output=cmd(CLIENT_HOST,'http_workload_'+str(trial),'cd '+shlex.quote(client_root)+' && python3 -u raw_thesis_sender.py http --count '+str(count)+' --pps 100',sudo=True,timeout=130)
  row=json.loads(output);state=wait_domain_count(before['domain_events']+row['sent_packets']);stats=read_json(POLICY_HOST,candidate_root+'/replication-stats.json')
  row.update(trial=trial,traps_received=state['domain_events']-before['domain_events'],duplicates_delta=state['duplicates']-before['duplicates'],snmp_overflow_delta=stats['snmp_overflow']-stats_before['snmp_overflow'],scope='live HTTP packet fixtures through virtual TAP/NPB/DPDK PS; receiver on Backend VM; not established HTTP sessions')
  row['passed']=row['sent_packets']==count and row['traps_received']==count and not row['duplicates_delta'] and not row['snmp_overflow_delta']
  results.append(row);(OUT/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(row),flush=True)
  if not row['passed']:raise RuntimeError('HTTP-driven SNMP delivery did not meet exact input count')
 send_batch(10,0)
 for trial in range(1,6):send_batch(1000,trial)
 send_batch(10000,6)
 # A genuine 120-second summary, not a shortened demo interval.
 deadline=start+140
 state=receive_state()
 while not state['summary_events'] and time.monotonic()<deadline:
  time.sleep(1);state=receive_state()
 (OUT/'summary.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
 if not state['summary_events']:raise RuntimeError('120-second summary not received')
 print('SUMMARY:',json.dumps(state),flush=True)
except Exception as e:
 failed=True;(OUT/'failure.txt').write_text(str(e),encoding='utf-8');print('STOP:',str(e),flush=True)
finally:
 errors=[]
 if workflow.policy_id:
  try:workflow.delete_policy_exactly()
  except Exception as e:errors.append('policy cleanup: '+str(e))
 if rollout:
  try:rollout.stop()
  except Exception as e:errors.append('candidate rollback: '+str(e))
 if sampler_unit:
  try:
   cmd(POLICY_HOST,'stop_resource_sampler','systemctl stop '+sampler_unit+' || test "$(systemctl show '+sampler_unit+' -p LoadState --value)" = not-found',sudo=True)
   with workflow.clients[POLICY_HOST].open_sftp() as s:s.get(sampler_root+'/samples.jsonl',str(OUT/'resource-samples.jsonl'))
  except Exception as e:errors.append('sampler cleanup: '+str(e))
 if capture_unit:
  try:
   cmd(GATEWAY_HOST,'stop_owned_capture','systemctl stop '+capture_unit,sudo=True)
   cmd(GATEWAY_HOST,'capture_journal','journalctl -u '+capture_unit+' --no-pager -n 12',sudo=True)
   cmd(GATEWAY_HOST,'restore_capture_interface','ip link set dev ens38 promisc off down',sudo=True)
   with workflow.clients[GATEWAY_HOST].open_sftp() as s:s.get(gateway_root+'/resets.pcap',str(OUT/'resets.pcap'))
  except Exception as e:errors.append('capture cleanup: '+str(e))
 if receiver_unit:
  try:
   cmd(BACKEND_HOST,'stop_owned_receiver','systemctl stop '+receiver_unit+' || test "$(systemctl show '+receiver_unit+' -p LoadState --value)" = not-found',sudo=True)
   with workflow.clients[BACKEND_HOST].open_sftp() as s:
    for name in ('receiver.log','events.jsonl','receiver-state.json','cleanup.json'):
     try:s.get(receiver_root+'/'+name,str(OUT/name))
     except OSError:pass
  except Exception as e:errors.append('receiver cleanup: '+str(e))
 (OUT/'run-cleanup.json').write_text(json.dumps({'errors':errors,'failed':failed,'policy_restored':workflow.policy_deleted},indent=2),encoding='utf-8')
 for c in workflow.clients.values():c.close()
 print('EVIDENCE:',OUT,flush=True)
 if errors:print('CLEANUP NEEDS REVIEW:',errors,flush=True)
raise SystemExit(1 if failed or errors else 0)
