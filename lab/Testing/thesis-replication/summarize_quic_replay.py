"""Supplemental fixed-Initial packet capacity, not live HTTP3 outcome replication."""
from pathlib import Path
import json,statistics,csv,struct,hashlib
BASE=Path(__file__).resolve().parent
OUT=sorted(p for p in (BASE/'evidence').glob('quic-replay-dataplane-*') if (p/'results.json').exists())[-1]
rows=json.loads((OUT/'results.json').read_text());aggregates=[]
for r in rows:
 raw=(OUT/('p'+str(r['configured_pps'])+'-t'+str(r['trial'])+'.pcap')).read_bytes();endian='<' if raw[:4]==b'\xd4\xc3\xb2\xa1' else '>';offset=24;count=0
 while offset+16<=len(raw):
  _,_,n,_=struct.unpack_from(endian+'IIII',raw,offset);offset+=16;f=raw[offset:offset+n];offset+=n
  if len(f)<42 or f[12:14]!=b'\x08\x00' or f[23]!=17:continue
  u=14+(f[14]&15)*4
  if len(f)<u+8:continue
  source,destination,length,_=struct.unpack_from('!HHHH',f,u);payload=f[u+8:u+length]
  if source==18443 and length==74 and len(payload)==66 and payload[0]&0xc0==0xc0 and payload[1:5]==b'\0\0\0\1':count+=1
 r['wire_candidate_close_shapes']=count
for pps in [100,200,500,1000,1500]:
 rr=[r for r in rows if r['configured_pps']==pps]
 if not rr:continue
 aggregates.append({'target_pps':pps,'trials':len(rr),'achieved_pps_mean':statistics.mean(r['achieved_pps'] for r in rr),'positive_initials_total':sum(r['metrics']['quic_positive'] for r in rr),'close_sent_total':sum(r['metrics']['close_sent'] for r in rr),'close_sent_percentage_mean':statistics.mean(r['close_sent_per_positive']*100 for r in rr),'close_sent_percentage_sample_sd':statistics.stdev(r['close_sent_per_positive']*100 for r in rr) if len(rr)>1 else None})
lines=['# Supplemental paced QUIC Initial replay','',
 'This is a fixed authenticated 1,200-byte QUIC-v1 Initial replay through TAP -> NPB -> PS, not fresh HTTP/3 connections. Source ports vary, but the QUIC CID/payload is reused. No client-confirmed denial fraction is assigned to replay packets. It supplements the fresh-client generator limit; do not replace the thesis-style client workload with this table.',
 '', '| Target PPS | Trial | Actually sent | Actual PPS | Positive Initials | Close sent | Positive/input % | Close/positive % |',
 '|---|---:|---:|---:|---:|---:|---:|---:|']
for r in rows:lines.append(f"| {r['configured_pps']} | {r['trial']} | {r['sent_packets']} | {r['achieved_pps']:.2f} | {r['metrics']['quic_positive']} | {r['metrics']['close_sent']} | {r['metrics']['quic_positive']/r['sent_packets']*100:.2f} | {r['close_sent_per_positive']*100:.2f} |")
lines+=['','Thirty seconds per trial, three trials at each level. Missing positives count as input-path loss, not hidden successes. Close/positive counts PS TX accepted, not guaranteed client receipt. Per-trial dedicated-wire captures are retained.','', 'Cleanup: '+(OUT/'cleanup.json').read_text() if (OUT/'cleanup.json').exists() else 'Run still underway.']
lines+=['',f"Dedicated-wire captured candidate Close shapes: {sum(r['wire_candidate_close_shapes'] for r in rows):,}. Every trial's wire count equals PS accepted TX: {all(r['wire_candidate_close_shapes']==r['metrics']['close_sent'] for r in rows)}. Shape counting is not independent cryptographic authentication of every replay reply."]
(OUT/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');(OUT/'analysis.json').write_text(json.dumps({'trials':rows,'aggregates':aggregates},indent=2),encoding='utf-8')
hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='SHA256SUMS.json'}
(OUT/'SHA256SUMS.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
print('REPORT:',OUT/'RESULTS.md');print(json.dumps(aggregates,indent=2))
