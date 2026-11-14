"""Same-host PCAP Initial/Close/server-Handshake timing, not client drain time."""
from pathlib import Path
import json,struct,statistics,sys
BASE=Path(__file__).resolve().parent
runs=[p for p in (BASE/'evidence').glob('quic-*') if (p/'functional-deny.pcap').exists()]
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else sorted(runs)[-1]
CLIENT_SCOPE=(OUT/'client-functional-deny.pcap').exists()
raw=(OUT/('client-functional-deny.pcap' if CLIENT_SCOPE else 'functional-deny.pcap')).read_bytes()
magic=raw[:4];endian='<' if magic in [b'\xd4\xc3\xb2\xa1',b'\x4d\x3c\xb2\xa1'] else '>';nano=magic in [b'\x4d\x3c\xb2\xa1',b'\xa1\xb2\x3c\x4d'];link=struct.unpack_from(endian+'I',raw,20)[0]
def variable(buf,o):
 n=1<<(buf[o]>>6)
 if o+n>len(buf):raise ValueError('truncated variable integer')
 return int.from_bytes(buf[o:o+n],'big')&((1<<(n*8-2))-1),o+n
def packet_types(buf):
 result=[];o=0
 try:
  while o+7<=len(buf) and buf[o]&0x80:
   start=o;kind=(buf[o]>>4)&3;version=int.from_bytes(buf[o+1:o+5],'big')
   if version!=1:break
   o+=5;dl=buf[o];o+=1+dl;sl=buf[o];o+=1+sl
   if kind==0:
    token,o=variable(buf,o);o+=token
   if kind==3:break
   length,o=variable(buf,o);end=o+length
   if end>len(buf):break
   result.append(kind);o=end
 except (ValueError,IndexError):pass
 return result
flows={};offset=24;packets=0
while offset+16<=len(raw):
 sec,sub,n,_=struct.unpack_from(endian+'IIII',raw,offset);offset+=16;frame=raw[offset:offset+n];offset+=n;packets+=1
 if link==1:
  ip_offset=14;proto=frame[12:14]
 elif link==113:
  ip_offset=16;proto=frame[14:16]
 elif link==276:
  ip_offset=20;proto=frame[:2]
 else:raise ValueError('Unsupported capture link '+str(link))
 if proto!=b'\x08\x00' or len(frame)<ip_offset+28:continue
 ip=frame[ip_offset:];ihl=(ip[0]&15)*4
 if ip[9]!=17:continue
 src='.'.join(str(x) for x in ip[12:16]);dst='.'.join(str(x) for x in ip[16:20]);u=ip[ihl:]
 if len(u)<8:continue
 sport,dport,length,_=struct.unpack_from('!HHHH',u);data=u[8:length]
 now=sec+sub/(1e9 if nano else 1e6)
 if src=='192.168.80.29' and dport==18443 and 0 in packet_types(data):
  row=flows.setdefault(sport,{});row['client_initial']=min(now,row.get('client_initial',now))
 elif src=='192.168.80.28' and sport==18443:
  row=flows.setdefault(dport,{})
  if len(data)==66 and 0 in packet_types(data):row['candidate_close']=min(now,row.get('candidate_close',now))
  elif 2 in packet_types(data):row['server_handshake']=min(now,row.get('server_handshake',now))
  row['first_server_or_policy_reply']=min(now,row.get('first_server_or_policy_reply',now))
functional={r['local'][1]:r for r in json.loads((OUT/'functional.json').read_text()) if r['mode']=='deny'}
rows=[]
for port,f in sorted(flows.items()):
 if port not in functional:continue
 r={'client_port':port,'client_outcome':functional[port]['class'],'client_handshake':functional[port]['handshake']}
 for key in ['candidate_close','server_handshake']:
  r[key+'_ms_from_initial']=(f[key]-f['client_initial'])*1000 if key in f and 'client_initial' in f else None
 r['close_before_server_handshake']=f.get('candidate_close',float('inf'))<f.get('server_handshake',float('inf')) if 'candidate_close' in f and 'server_handshake' in f else None
 rows.append(r)
summary={'pcap_linktype':link,'captured_packets':packets,'functional_flows':len(functional),'matched_flow_timings':len(rows),'scope':('client single-interface same-clock capture; outbound Initial vs received Close/server Handshake; includes network and virtual TAP/return-path delay, not PS processing latency' if CLIENT_SCOPE else 'gateway same-clock cross-interface capture; main-path client Initial ingress vs dedicated-wire policy Close ingress vs original server coalesced Handshake; not PS processing latency'),'rows':rows}
negative=sum(r['candidate_close_ms_from_initial'] is not None and r['candidate_close_ms_from_initial']<0 for r in rows)
summary['negative_initial_to_close_intervals']=negative
summary['latency_interpretation']=('Client-observed packet response timing, includes both network paths. Not isolated PS processing latency. Negative intervals or missing flow pairs invalidate full timing comparison.' if CLIENT_SCOPE else 'Not a PS processing-latency estimate: mirrored input can reach PS before the original reaches gateway; cross-interface capture ordering can also differ. Preserve signed gateway-relative intervals. Use a single-interface client capture for client-observed response timing.')
for key in ['candidate_close_ms_from_initial','server_handshake_ms_from_initial']:
 values=[r[key] for r in rows if r[key] is not None]
 summary[key]={'n':len(values),'mean':statistics.mean(values),'min':min(values),'max':max(values)} if values else None
(OUT/'packet-timing.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
