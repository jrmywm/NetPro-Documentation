"""Preserve configured/achieved load, dataplane counts and client outcomes separately."""
from pathlib import Path
import json,statistics,struct,csv,hashlib
BASE=Path(__file__).resolve().parent
runs=[p for p in (BASE/'evidence').glob('quic-live-http3-*') if (p/'results.json').exists()]
OUT=sorted(runs)[-1]
rows=json.loads((OUT/'results.json').read_text());functional=json.loads((OUT/'functional.json').read_text())
def wire_count(path):
 raw=path.read_bytes();magic=raw[:4];endian='<' if magic in [b'\xd4\xc3\xb2\xa1',b'\x4d\x3c\xb2\xa1'] else '>';offset=24;count=packets=0
 assert struct.unpack_from(endian+'I',raw,20)[0]==1,'Expected Ethernet capture'
 while offset+16<=len(raw):
  _,_,n,_=struct.unpack_from(endian+'IIII',raw,offset);offset+=16;f=raw[offset:offset+n];offset+=n;packets+=1
  if len(f)<42 or f[12:14]!=b'\x08\x00' or f[23]!=17:continue
  u=14+(f[14]&15)*4
  if len(f)<u+8:continue
  source,destination,length,_=struct.unpack_from('!HHHH',f,u);payload=f[u+8:u+length]
  # Candidate generator is independently authenticated in the retained crypto gate.
  # This capture shape count alone is not independent per-packet authentication.
  if source==18443 and length==74 and len(payload)==66 and payload[0]&0xc0==0xc0 and payload[1:5]==b'\0\0\0\1':count+=1
 return {'candidate_close_shape_packets':count,'total_captured_packets':packets}
for r in rows:
 label='p'+str(r['configured_pps'])+'-t'+str(r['trial'])
 r['wire']=wire_count(OUT/(label+'.pcap'))
 r['positive_initials_per_s']=r['metrics']['quic_positive']/r['scheduling_elapsed_s']
means=[]
thesis={100:98.1,200:91.3,500:91.9,1000:89.3,1500:87.8}
for pps in [100,200,500,1000,1500]:
 rr=[r for r in rows if r['configured_pps']==pps]
 if not rr:continue
 def mean(key):return statistics.mean(r[key] for r in rr)
 values=[r['close_sent_per_positive']*100 for r in rr if r['close_sent_per_positive'] is not None]
 means.append({'configured_pps':pps,'trials':len(rr),'achieved_request_starts_per_s_mean':mean('achieved_request_starts_per_s'),'positive_initials_per_s_mean':mean('positive_initials_per_s'),'close_sent_percentage_mean':statistics.mean(values) if values else None,'close_sent_percentage_sample_sd':statistics.stdev(values) if len(values)>1 else None,'client_confirmed_close_percentage_mean':mean('client_confirmed_close_fraction')*100,'thesis_close_sent_percentage_mean':thesis[pps]})
samples=[json.loads(l) for l in (OUT/'resource-samples.jsonl').read_text().splitlines()] if (OUT/'resource-samples.jsonl').exists() else []
resources={}
for key in ['process_cpu_percent_one_core','process_cpu_percent_guest_capacity','guest_cpu_percent','rss_kib']:
 vals=[s[key] for s in samples if s.get(key) is not None]
 if vals:resources[key]={'mean':statistics.mean(vals),'max':max(vals)}
summary={'trials':rows,'aggregates':means,'functional':functional,'resource_summary':resources,'resource_sample_count':len(samples),'cleanup':json.loads((OUT/'cleanup.json').read_text()) if (OUT/'cleanup.json').exists() else None}
(OUT/'analysis.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
columns=['configured_pps','trial','started_requests','achieved_request_starts_per_s','positive_initials_per_s','policy_close','http_200','timeout','other','close_sent_per_positive','client_confirmed_close_fraction','skipped_inflight_limit']
with (OUT/'trials.csv').open('w',encoding='utf-8',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
lines=['# Live HTTP/3 QUIC-v1 replication — 13 October 2026 (Asia/Taipei)','',
 'Actual path: fresh HTTP/3 client -> software virtual TAP -> gateway HTTP/3 server; mirrored copy -> temporary NPB QUIC candidate -> Policy Server authenticated SNI parsing -> dedicated return wire -> narrow UDP redirect -> client. No TCP fallback.',
 '', '| Target starts/s | Trial | Starts | Actual starts/s | Positive Initials | Close sent | Wire Close shapes | Client confirms | HTTP 200 escapes | Timeout |',
 '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
for r in rows:lines.append(f"| {r['configured_pps']} | {r['trial']} | {r['started_requests']} | {r['achieved_request_starts_per_s']:.2f} | {r['metrics']['quic_positive']} | {r['metrics']['close_sent']} | {r['wire']['candidate_close_shape_packets']} | {r['policy_close']} | {r['http_200']} | {r['timeout']} |")
lines+=['','## Comparison and scope','',
 'Thesis setup used Caddy/custom HTTP3 curl, Proxmox and an 8-vCPU PS. This experiment uses private aioquic 1.3.0 HTTP/3 endpoints and VMware with a four-vCPU PS, a safety-fixed Close generator, bounded parser, and an adapted NPB classifier. It is an adapted reproduction, not identical software/hardware or a claim of matching numeric results.',
 '', 'Each configured level has three 30-second trials. Target is fresh connection starts per second, not a guarantee of achieved packet PPS. Retransmissions can increase positive Initial counts; sender CPU and the 512-in-flight cap can reduce achieved input. Compare using actual positive input and retain skipped starts.',
 '', 'Close sent / positive Initial is the thesis-style dataplane ratio. DPDK accepted TX is not proof of delivery. Wire counts identify the tested 66-byte Initial shape, not independent authentication of every packet. Client-confirmed Close / started requests is a separate operational measure. HTTP 200 with the rule present is a blocking escape, not a pass.',
 '', 'Functional client elapsed times include QUIC closing/draining timers and must not be presented as Initial-to-Close packet latency. Packet timing still requires a capture with both input and return traffic on the same clock.',
 '', 'Results retain all outcomes and cleanup status. Production sources/symlinks are not replaced; original binary hashes and policy IDs are verified during rollback.']
lines+=['','| Target | Trials | Actual starts/s mean | Positive/s mean | Our Close sent % mean ± sample SD | Thesis reported mean % | Client confirmed % mean |','|---|---:|---:|---:|---:|---:|---:|']
for a in means:lines.append(f"| {a['configured_pps']} | {a['trials']} | {a['achieved_request_starts_per_s_mean']:.2f} | {a['positive_initials_per_s_mean']:.2f} | {a['close_sent_percentage_mean']:.2f} ± {a['close_sent_percentage_sample_sd'] or 0:.2f} | {a['thesis_close_sent_percentage_mean']:.1f} | {a['client_confirmed_close_percentage_mean']:.2f} |")
lines+=['','Resource summary (one-second samples; process CPU normalized separately to one core and guest capacity):','',json.dumps(resources,indent=2),'','Cleanup: '+json.dumps(summary['cleanup'])]
(OUT/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='SHA256SUMS.json'}
(OUT/'SHA256SUMS.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
print('REPORT:',OUT/'RESULTS.md');print('Aggregates:',json.dumps(means));print('Cleanup:',summary['cleanup'])
