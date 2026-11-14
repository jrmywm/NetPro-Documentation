"""Bounded lab-only Ethernet HTTP/QUIC replay, not established client sessions."""
import socket,struct,time,json,argparse,resource
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('mode',choices=['http','quic']);p.add_argument('--count',type=int,default=1000);p.add_argument('--pps',type=int,default=100);p.add_argument('--seconds',type=int,default=0);p.add_argument('--fixture',default='initial.bin');a=p.parse_args()
if not (1<=a.pps<=1500 and 0<=a.seconds<=30 and 1<=a.count<=10000):raise SystemExit('outside approved bound')
mac=Path('/sys/class/net/ens37/address').read_text().strip()
if mac!='00:0c:29:91:39:14':raise SystemExit('unexpected client interface MAC')
src=socket.inet_aton('192.168.80.29');dst=socket.inet_aton('192.168.80.28')
eth=bytes.fromhex('000c293473cc000c299139140800')
def checksum(data):
 if len(data)%2:data+=b'\0'
 total=sum(struct.unpack('!'+str(len(data)//2)+'H',data))
 while total>>16:total=(total&65535)+(total>>16)
 return (~total)&65535
payload=b'GET /thesis-replication HTTP/1.1\r\nHost: netpro-tap.test\r\nConnection: close\r\n\r\n' if a.mode=='http' else Path(a.fixture).read_bytes()
if a.mode=='quic' and len(payload)!=1200:raise SystemExit('expected validated 1200-byte Initial')
protocol=6 if a.mode=='http' else 17
def frame(i):
 sport=40000+i%1000
 if protocol==6:
  transport=struct.pack('!HHIIBBHHH',sport,8080,100+i,1,0x50,0x18,65535,0,0)+payload
  c=checksum(src+dst+struct.pack('!BBH',0,6,len(transport))+transport)
  transport=transport[:16]+struct.pack('!H',c)+transport[18:]
 else:
  transport=struct.pack('!HHHH',sport,18443,8+len(payload),0)+payload
  c=checksum(src+dst+struct.pack('!BBH',0,17,len(transport))+transport) or 65535
  transport=transport[:6]+struct.pack('!H',c)+transport[8:]
 ip=struct.pack('!BBHHHBBH4s4s',0x45,0,20+len(transport),i%65536,0,64,protocol,0,src,dst)
 ip=ip[:10]+struct.pack('!H',checksum(ip))+ip[12:]
 return eth+ip+transport
start=time.monotonic();count=0;byte_count=0;before=resource.getrusage(resource.RUSAGE_SELF)
with socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(0x0800)) as s:
 s.bind(('ens37',0));s.settimeout(2)
 while (time.monotonic()-start<a.seconds) if a.seconds else (count<a.count):
  target=start+count/a.pps;delay=target-time.monotonic()
  if delay>0:time.sleep(delay)
  if a.seconds and time.monotonic()-start>=a.seconds:break
  data=frame(count);n=s.send(data)
  if n!=len(data):raise RuntimeError('partial raw send')
  count+=1;byte_count+=n
elapsed=time.monotonic()-start;after=resource.getrusage(resource.RUSAGE_SELF)
print(json.dumps({'scope':'lab-only replayed HTTP segments or authenticated QUIC Initial fixture, not live connections','mode':a.mode,'configured_pps':a.pps,'requested_seconds':a.seconds,'sent_packets':count,'sent_bytes':byte_count,'elapsed_s':elapsed,'achieved_pps':count/elapsed,'sender_cpu_s':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime}),flush=True)
