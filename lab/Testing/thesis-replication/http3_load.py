"""30-second scheduled, fresh HTTP/3 connection workload; no TCP fallback."""
import argparse,asyncio,json,ssl,time,resource
from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.packet import QuicProtocolVersion
from aioquic.quic.events import HandshakeCompleted,ConnectionTerminated
from aioquic.h3.connection import H3Connection,H3_ALPN
from aioquic.h3.events import HeadersReceived,DataReceived

class Client(QuicConnectionProtocol):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs);self.http=H3Connection(self._quic);self.result=asyncio.get_running_loop().create_future();self.status=None;self.handshake=False
 def request(self):
  self.http.send_headers(0,[(b':method',b'GET'),(b':scheme',b'https'),(b':authority',b'netpro-quic.test'),(b':path',b'/')],end_stream=True);self.transmit()
 def quic_event_received(self,event):
  if isinstance(event,HandshakeCompleted):self.handshake=True
  if isinstance(event,ConnectionTerminated) and not self.result.done():
   self.result.set_result({'class':'policy_close' if event.reason_phrase=='BLOCKED_BY_POLICY_SERVER' else 'other_termination','reason':event.reason_phrase,'handshake':self.handshake})
  for e in self.http.handle_event(event):
   if isinstance(e,HeadersReceived):self.status=dict(e.headers).get(b':status',b'').decode()
   if isinstance(e,(HeadersReceived,DataReceived)) and e.stream_ended and not self.result.done():self.result.set_result({'class':'http_200' if self.status=='200' else 'other_http','http_status':self.status,'handshake':self.handshake})

async def run(a):
 start=time.monotonic();before=resource.getrusage(resource.RUSAGE_SELF);pending=set();outcomes=[];scheduled=started=skipped=0;request_times=[]
 async def one():
  began=time.monotonic();config=QuicConfiguration(is_client=True,alpn_protocols=H3_ALPN,supported_versions=[QuicProtocolVersion.VERSION_1],server_name='netpro-quic.test',verify_mode=ssl.CERT_NONE)
  try:
   async with connect('192.168.80.28',18443,configuration=config,create_protocol=Client,wait_connected=False) as c:
    c.request();r=await asyncio.wait_for(asyncio.shield(c.result),5)
  except asyncio.TimeoutError:r={'class':'timeout'}
  except Exception as e:r={'class':'error','error':type(e).__name__+': '+str(e)}
  r['elapsed_s']=time.monotonic()-began;outcomes.append(r)
 while time.monotonic()-start<a.seconds:
  target=start+scheduled/a.pps;await asyncio.sleep(max(0,target-time.monotonic()))
  if time.monotonic()-start>=a.seconds:break
  scheduled+=1
  if len(pending)>=512:skipped+=1;continue
  started+=1;request_times.append(time.monotonic()-start);task=asyncio.create_task(one());pending.add(task);task.add_done_callback(pending.discard)
 send_end=time.monotonic()
 if pending:await asyncio.gather(*list(pending))
 after=resource.getrusage(resource.RUSAGE_SELF)
 summary={'scope':'fresh HTTP/3 QUIC-v1 connections against local endpoint; no TCP fallback; max 512 in flight','configured_pps':a.pps,'requested_seconds':a.seconds,'scheduling_elapsed_s':send_end-start,'total_elapsed_s':time.monotonic()-start,'scheduled':scheduled,'started_requests':started,'skipped_inflight_limit':skipped,'achieved_request_starts_per_s':started/(send_end-start),'policy_close':sum(r['class']=='policy_close' for r in outcomes),'http_200':sum(r['class']=='http_200' for r in outcomes),'timeout':sum(r['class']=='timeout' for r in outcomes),'other':sum(r['class'] not in ('policy_close','http_200','timeout') for r in outcomes),'completed_outcomes':len(outcomes),'sender_cpu_s':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime}
 if a.output:
  from pathlib import Path
  Path(a.output).write_text(json.dumps({'summary':summary,'request_start_times_s':request_times,'outcomes':outcomes}),encoding='utf-8')
 print(json.dumps(summary),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--pps',type=int,required=True);p.add_argument('--seconds',type=int,default=30);p.add_argument('--output');a=p.parse_args()
 if not 1<=a.pps<=1500 or not 1<=a.seconds<=30:raise SystemExit('outside approved bound')
 asyncio.run(run(a))
