"""Bounded lab controller: applied PS policy -> scoped gateway IP drops.
Separate verified SSH connections; last rules retained on errors until cleanup
or the experiment rollback timer. This is not a production controller.
"""
import threading,time,json,shlex,re,os
from pathlib import Path
from remote import connect_verified,run_remote_command
class RouterController:
 def __init__(self,password,comment,output):
  self.password=password;self.comment=comment;self.output=Path(output);self.stop_event=threading.Event();self.state=None;self.error=None;self.events=[]
 def start(self):
  self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
 def run(self):
  clients=[]
  try:
   ps,_=connect_verified('192.168.31.31','netpro',self.password,Path.home()/'.ssh/known_hosts');clients.append(ps)
   gw,_=connect_verified('192.168.31.37','netpro',self.password,Path.home()/'.ssh/known_hosts');clients.append(gw)
   sql="SELECT id, domain, ip_address FROM policies WHERE domain='mysite.local' AND ip_address='198.18.0.2'"
   code="import sqlite3,json; c=sqlite3.connect('file:/home/ubuntu/NetPro-Policy-Server/policy.db?mode=ro',uri=True,timeout=1); c.row_factory=sqlite3.Row; print(json.dumps([dict(r) for r in c.execute("+repr(sql)+")]))"
   command="python3 -c "+shlex.quote(code)
   while not self.stop_event.is_set():
    rc,out,err=run_remote_command(ps,command,sudo_password=self.password,timeout=5)
    if rc:raise RuntimeError('Policy read failed: '+err)
    rows=json.loads(out or '[]');assert len(rows)<=1
    if rows:assert re.fullmatch('[A-Fa-f0-9-]{36}',rows[0]['id'])
    block=bool(rows)
    if self.stop_event.is_set():break
    script='set -eu\n'
    for proto in ['udp','tcp']:
     rule=f'-p {proto} -s 192.168.80.29 -d 198.18.0.2 --dport 443 -m comment --comment '+shlex.quote(self.comment)+' -j DROP'
     if block:script+='iptables -w 2 -C FORWARD '+rule+' 2>/dev/null || iptables -w 2 -I FORWARD 1 '+rule+'\n'
     else:script+='if iptables -w 2 -C FORWARD '+rule+' 2>/dev/null; then iptables -w 2 -D FORWARD '+rule+'; fi\n'
    rc,out,err=run_remote_command(gw,'bash -c '+shlex.quote(script),sudo_password=self.password,timeout=8)
    if rc:raise RuntimeError('Firewall update failed: '+err)
    if block!=self.state:self.events.append(dict(time_utc=time.time(),blocked=block,policy_ids=[r['id'] for r in rows]))
    self.state=block
    self.stop_event.wait(.25)
  except Exception as e:self.error=repr(e)
  finally:
   for c in clients:c.close()
   self.output.write_text(json.dumps(dict(events=self.events,error=self.error),indent=2),encoding='utf8')
 def wait(self,state):
  end=time.monotonic()+20
  while time.monotonic()<end:
   if self.error:raise RuntimeError(self.error)
   if self.state is state:return
   time.sleep(.05)
  raise RuntimeError('Controller did not reach expected state')
 def stop(self):
  self.stop_event.set();self.thread.join(timeout=20)
  if self.thread.is_alive():raise RuntimeError('Controller did not stop')
