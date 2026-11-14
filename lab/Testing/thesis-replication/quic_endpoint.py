"""Private QUIC-v1 echo baseline, not HTTP/3 or enforcement."""
import argparse,asyncio,json,socket,ssl,time,base64,sys
from pathlib import Path
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from aioquic.quic.events import HandshakeCompleted,StreamDataReceived,ConnectionTerminated
from aioquic.asyncio import serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.packet import QuicProtocolVersion

class Echo(QuicConnectionProtocol):
 def quic_event_received(self,event):
  if isinstance(event,StreamDataReceived):
   self._quic.send_stream_data(event.stream_id,event.data,end_stream=event.end_stream)
   self.transmit()

async def server(args):
 config=QuicConfiguration(is_client=False,alpn_protocols=['netpro-replication'],supported_versions=[QuicProtocolVersion.VERSION_1])
 config.load_cert_chain('cert.pem','key.pem')
 instance=await serve('192.168.80.28',args.port,configuration=config,create_protocol=Echo)
 try: await asyncio.sleep(40)
 finally: instance.close()

def client(args):
 config=QuicConfiguration(is_client=True,alpn_protocols=['netpro-replication'],supported_versions=[QuicProtocolVersion.VERSION_1],server_name='netpro-quic.test',verify_mode=ssl.CERT_NONE)
 q=QuicConnection(configuration=config);peer=('192.168.80.28',args.port)
 start=time.monotonic();q.connect(peer,now=start)
 handshake=False;echo=False;terminated=None;sent=received=0
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
  sock.bind(('192.168.80.29',0));sock.settimeout(.02)
  local=sock.getsockname()
  while time.monotonic()-start<8:
   now=time.monotonic()
   for data,addr in q.datagrams_to_send(now):
    if sent==0: Path(args.initial).write_bytes(data)
    sock.sendto(data,addr);sent+=1
   try:
    data,addr=sock.recvfrom(65535)
    if addr!=peer:continue
    received+=1;q.receive_datagram(data,addr,time.monotonic())
   except socket.timeout:pass
   now=time.monotonic();timer=q.get_timer()
   if timer is not None and timer<=now:q.handle_timer(now)
   while (event:=q.next_event()) is not None:
    if isinstance(event,HandshakeCompleted):
     handshake=True;q.send_stream_data(0,b'netpro-replication',end_stream=True)
    if isinstance(event,StreamDataReceived) and event.data==b'netpro-replication':echo=True
    if isinstance(event,ConnectionTerminated):terminated={'error_code':event.error_code,'reason':event.reason_phrase}
   if echo or terminated:break
 result={'scope':'live QUIC v1 echo baseline; no enforcement; not HTTP/3','handshake':handshake,'echo':echo,'terminated':terminated,'sent_datagrams':sent,'received_datagrams':received,'elapsed_s':time.monotonic()-start,'local':local,'peer':peer,'initial_bytes':Path(args.initial).stat().st_size if sent else 0}
 print(json.dumps(result));return 0 if handshake and echo else 1

def close_gate(args):
 config=QuicConfiguration(is_client=True,alpn_protocols=['netpro-replication'],supported_versions=[QuicProtocolVersion.VERSION_1],server_name='netpro-quic.test',verify_mode=ssl.CERT_NONE)
 q=QuicConnection(configuration=config);peer=('192.168.80.28',args.port);now=time.monotonic();q.connect(peer,now)
 data=q.datagrams_to_send(now)[0][0]
 print(base64.b64encode(data).decode(),flush=True)
 close=base64.b64decode(sys.stdin.readline().strip(),validate=True)
 q.receive_datagram(close,peer,now+.01)
 # ConnectionTerminated is emitted after the closing/draining timer, not immediately.
 timer=q.get_timer()
 if timer is not None:q.handle_timer(timer+.001)
 events=[];terminated=None
 while (event:=q.next_event()) is not None:
  events.append(type(event).__name__)
  if isinstance(event,ConnectionTerminated):terminated={'error_code':event.error_code,'reason':event.reason_phrase,'frame_type':event.frame_type}
 print(json.dumps({'scope':'real aioquic client state machine; no network injection or DPDK','events':events,'connection_terminated':terminated,'initial_bytes':len(data),'close_bytes':len(close),'passed':terminated is not None}),flush=True)
 return 0 if terminated else 1

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['server','client','close-gate']);p.add_argument('--port',type=int,default=18443);p.add_argument('--initial',default='initial.bin');a=p.parse_args()
 if a.mode=='server':asyncio.run(server(a))
 else:raise SystemExit(close_gate(a) if a.mode=='close-gate' else client(a))
