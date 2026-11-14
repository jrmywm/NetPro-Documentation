"""Private Net-SNMP receiver and numeric-OID evidence, no system SNMP install."""
from pathlib import Path
import os,subprocess,time,threading,json,re,signal
ROOT=Path(__file__).resolve().parent;private=ROOT/'private';stop=threading.Event()
for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
for name in ('home','persist'): (ROOT/name).mkdir(exist_ok=True)
env=dict(os.environ,LD_LIBRARY_PATH=str(private/'usr/lib/x86_64-linux-gnu')+':'+str(private/'lib/x86_64-linux-gnu'),HOME=str(ROOT/'home'),SNMP_PERSISTENT_DIR=str(ROOT/'persist'),MIBS='')
(ROOT/'receiver.conf').write_text('authCommunity log public\n',encoding='utf-8')
if subprocess.check_output(['ss','-H','-lun','sport = :11623']).strip():raise RuntimeError('Receiver port occupied')
receiver=subprocess.Popen([str(private/'usr/sbin/snmptrapd'),'-f','-C','-c',str(ROOT/'receiver.conf'),'-Lo','-t','-On','-F','%v\n','udp:192.168.31.35:11623'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
events=[];started=time.monotonic()
def reader():
 with (ROOT/'receiver.log').open('w',encoding='utf-8') as log,(ROOT/'events.jsonl').open('w',encoding='utf-8') as records:
  for line in receiver.stdout:
   now=time.monotonic();log.write(f'{now:.9f} '+line);log.flush()
   def counter(arc):
    m=re.search(r'1\.3\.6\.1\.4\.1\.53864\.1\.0\.'+str(arc)+r'\s*=\s*Counter64:\s*(\d+)',line)
    return int(m[1]) if m else None
   kind=counter(12)
   if kind is None:continue
   uptime=re.search(r'Timeticks:\s*\((\d+)\)',line)
   row={'kind':kind,'sequence':counter(11),'reset_attempts':counter(2),'reset_kernel_accepted':counter(3),'agent_uptime_cs':int(uptime[1]) if uptime else None,'receiver_monotonic':now,'receiver_elapsed_s':now-started,'domain_present':'netpro-tap.test' in line}
   events.append(row);records.write(json.dumps(row)+'\n');records.flush()
thread=threading.Thread(target=reader,daemon=True);thread.start()
try:
 while not stop.wait(.5):
  if receiver.poll() is not None:raise RuntimeError('receiver exited '+str(receiver.returncode))
  if time.monotonic()-started>1500:break
  summary={'domain_events':sum(e['kind']==1 and e['domain_present'] for e in events),'other_domain_events':sum(e['kind']==1 and not e['domain_present'] for e in events),'summary_events':[e for e in events if e['kind']==2],'duplicates':len([e['sequence'] for e in events if e['kind']==1])-len({e['sequence'] for e in events if e['kind']==1})}
  tmp=ROOT/'receiver-state.json.tmp';tmp.write_text(json.dumps(summary),encoding='utf-8');tmp.replace(ROOT/'receiver-state.json')
finally:
 receiver.terminate()
 try:receiver.wait(timeout=5)
 except subprocess.TimeoutExpired:receiver.kill();receiver.wait()
 thread.join(timeout=3)
 (ROOT/'cleanup.json').write_text(json.dumps({'receiver_exit':receiver.returncode,'port_released':not bool(subprocess.check_output(['ss','-H','-lun','sport = :11623']).strip()),'events':len(events)}),encoding='utf-8')
