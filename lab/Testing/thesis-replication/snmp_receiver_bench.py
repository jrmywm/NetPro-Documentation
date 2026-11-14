"""Remote isolated sender/receiver benchmark, not HTTP/DPDK integration."""
from pathlib import Path
import subprocess,os,time,threading,json,re,resource,statistics
ROOT=Path(__file__).resolve().parent
private=ROOT/'private'
env=dict(os.environ,PATH=str(private/'usr/bin')+':'+os.environ['PATH'],LD_LIBRARY_PATH=str(private/'usr/lib/x86_64-linux-gnu')+':'+str(private/'lib/x86_64-linux-gnu'),MIBS='',HOME=str(ROOT/'home'),SNMP_PERSISTENT_DIR=str(ROOT/'persist'))
for d in ('home','persist'): (ROOT/d).mkdir(exist_ok=True)
if subprocess.check_output(['ss','-H','-lun','sport = :11621']).strip():raise RuntimeError('UDP11621 occupied; refusing')
conf=ROOT/'receiver.conf';conf.write_text('authCommunity log public\n',encoding='utf-8')
received=[]
receiver=subprocess.Popen([str(private/'usr/sbin/snmptrapd'),'-f','-C','-c',str(conf),'-Lo','-t','-On','-F','%v\n','udp:127.0.0.1:11621'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,text=True,bufsize=1)
def reader():
 with (ROOT/'receiver.log').open('w',encoding='utf-8') as log:
  for line in receiver.stdout:
   arrival=time.monotonic();log.write(f'{arrival:.9f} {line}');log.flush()
   m=re.search(r'replication-trial-(\d+) port 0 sent (\d+) packets',line)
   if m:received.append((int(m[1]),int(m[2]),arrival))
t=threading.Thread(target=reader,daemon=True);t.start();results=[]
try:
 time.sleep(0.5)
 if receiver.poll() is not None:raise RuntimeError('receiver exited during startup')
 for trial in range(1,6):
  before=resource.getrusage(resource.RUSAGE_CHILDREN)
  r=subprocess.run([str(ROOT/'sender'),'1000',str(trial)],env=env,capture_output=True,text=True,timeout=120)
  after=resource.getrusage(resource.RUSAGE_CHILDREN)
  (ROOT/f'sender-{trial}.log').write_text(r.stdout+r.stderr,encoding='utf-8')
  row=json.loads(r.stdout.strip().splitlines()[-1]);time.sleep(0.4)
  entries=[x for x in received if x[0]==trial];ids=[x[1] for x in entries]
  missing=sorted(set(range(1,1001))-set(ids));intervals=[b[2]-a[2] for a,b in zip(entries,entries[1:])]
  row.update(receiver_count=len(ids),unique_received=len(set(ids)),missing=missing,duplicates=len(ids)-len(set(ids)),send_command_exit=r.returncode,mean_arrival_interval_ms=statistics.mean(intervals)*1000 if intervals else None,sender_tree_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,scope='isolated branch-style sender/receiver; no HTTP or DPDK')
  row['passed']=r.returncode==0 and len(ids)==1000 and not missing and row['duplicates']==0
  results.append(row);(ROOT/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
  print(json.dumps(row),flush=True)
finally:
 receiver.terminate()
 try:receiver.wait(timeout=5)
 except subprocess.TimeoutExpired:receiver.kill();receiver.wait()
 t.join(timeout=3)
 (ROOT/'cleanup.json').write_text(json.dumps({'receiver_exit':receiver.returncode,'port_released':not bool(subprocess.check_output(['ss','-H','-lun','sport = :11621']).strip())}),encoding='utf-8')
