"""Private HTTP/3-v1 endpoint/client with no TCP fallback or session reuse."""
import asyncio,argparse,json,ssl,socket,time
from pathlib import Path
from aioquic.asyncio import serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from aioquic.quic.events import HandshakeCompleted,ConnectionTerminated
from aioquic.quic.packet import QuicProtocolVersion
from aioquic.h3.connection import H3Connection,H3_ALPN
from aioquic.h3.events import HeadersReceived,DataReceived

class HTTP3Server(QuicConnectionProtocol):
 def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.http=H3Connection(self._quic)
 def quic_event_received(self,event):
  for e in self.http.handle_event(event):
   if isinstance(e,HeadersReceived):
    self.http.send_headers(e.stream_id,[(b':status',b'200'),(b'content-type',b'text/plain')])
    self.http.send_data(e.stream_id,b'NetPro HTTP/3 replication\n',end_stream=True);self.transmit()

async def server(a):
 config=QuicConfiguration(is_client=False,alpn_protocols=H3_ALPN,supported_versions=[QuicProtocolVersion.VERSION_1]);config.load_cert_chain('cert.pem','key.pem')
 s=await serve('192.168.80.28',18443,configuration=config,create_protocol=HTTP3Server)
 try:await asyncio.sleep(a.duration)
 finally:s.close()

def client(a):
 peer=('192.168.80.28',18443);config=QuicConfiguration(is_client=True,alpn_protocols=H3_ALPN,supported_versions=[QuicProtocolVersion.VERSION_1],server_name='netpro-quic.test',verify_mode=ssl.CERT_NONE)
 q=QuicConnection(configuration=config);h=H3Connection(q);start=time.monotonic();q.connect(peer,start)
 handshake=False;status=None;ended=False;terminated=None;body=b'';sent=received=0;first=None
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
  sock.bind(('192.168.80.29',0));sock.settimeout(.01);local=sock.getsockname()
  while time.monotonic()-start<5:
   now=time.monotonic()
   for data,addr in q.datagrams_to_send(now):
    if sent==0:Path(a.initial).write_bytes(data);first=len(data)
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
     handshake=True;h.send_headers(0,[(b':method',b'GET'),(b':scheme',b'https'),(b':authority',b'netpro-quic.test'),(b':path',b'/')],end_stream=True)
    if isinstance(event,ConnectionTerminated):terminated={'error_code':event.error_code,'reason':event.reason_phrase,'frame_type':event.frame_type}
    for e in h.handle_event(event):
     if isinstance(e,HeadersReceived):status=dict(e.headers).get(b':status',b'').decode();ended|=e.stream_ended
     if isinstance(e,DataReceived):body+=e.data;ended|=e.stream_ended
   if ended or terminated:break
 result={'protocol':'HTTP/3 over QUIC v1','tcp_fallback':False,'handshake':handshake,'http_status':status,'response_complete':ended,'body':body.decode(errors='replace'),'terminated':terminated,'elapsed_s':time.monotonic()-start,'local':local,'peer':peer,'sent_datagrams':sent,'received_datagrams':received,'initial_bytes':first}
 print(json.dumps(result),flush=True);return 0 if status=='200' and ended else 1

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['server','client']);p.add_argument('--duration',type=int,default=900);p.add_argument('--initial',default='initial.bin');a=p.parse_args()
 if not 1<=a.duration<=1200:raise SystemExit(2)
 if a.mode=='server':asyncio.run(server(a))
 else:raise SystemExit(client(a))
