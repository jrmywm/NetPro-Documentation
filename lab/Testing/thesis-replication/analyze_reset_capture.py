"""Summarize TCP reset timing from saved Ethernet PCAP without third-party libs."""
import struct,json,sys,socket
from pathlib import Path
raw=Path(sys.argv[1]).read_bytes();endian='<' if raw[:4]==b'\xd4\xc3\xb2\xa1' else '>'
offset=24;rows=[]
while offset+16<=len(raw):
 sec,usec,n,orig=struct.unpack_from(endian+'IIII',raw,offset);offset+=16;p=raw[offset:offset+n];offset+=n
 if len(p)<54 or p[12:14]!=b'\x08\x00':continue
 ihl=(p[14]&15)*4;t=14+ihl
 if p[23]!=6 or len(p)<t+20:continue
 src=socket.inet_ntoa(p[26:30]);dst=socket.inet_ntoa(p[30:34]);sp,dp,seq,ack=struct.unpack_from('!HHII',p,t)
 thl=(p[t+12]>>4)*4;length=int.from_bytes(p[16:18],'big')-ihl-thl
 rows.append(dict(time=sec+usec/1e6,src=src,dst=dst,sport=sp,dport=dp,seq=seq,ack=ack,flags=p[t+13],length=length))
start=rows[0]['time']
for r in rows:r['relative_ms']=round((r['time']-start)*1000,3)
selected=[r for r in rows if r['flags']&4 or r['length'] or r['flags']&2]
print(json.dumps({'packets':len(rows),'events':selected},indent=2))
