"""Produce evidence-backed live SNMP results, with explicit metric definitions."""
from pathlib import Path
import json,sys,struct,statistics
BASE=Path(__file__).resolve().parent;sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified
OUT=sorted((BASE/'evidence').glob('snmp-live-http-*'))[-1]
meta=OUT/'resource-sampling.json'
if meta.exists():
 m=json.loads(meta.read_text());c,_=connect_verified('192.168.31.31','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
 try:
  with c.open_sftp() as s:s.get(m['root']+'/samples.jsonl',str(OUT/'resource-samples.jsonl'))
 finally:c.close()
rows=json.loads((OUT/'results.json').read_text());events=[json.loads(l) for l in (OUT/'events.jsonl').read_text().splitlines()];domain=[e for e in events if e['kind']==1 and e['domain_present']]
samples=[json.loads(l) for l in (OUT/'resource-samples.jsonl').read_text().splitlines()] if (OUT/'resource-samples.jsonl').exists() else []
raw=(OUT/'resets.pcap').read_bytes();endian='<' if raw[:4]==b'\xd4\xc3\xb2\xa1' else '>';o=24;count=0
while o+16<=len(raw):
 sec,usec,n,orig=struct.unpack_from(endian+'IIII',raw,o);o+=16;p=raw[o:o+n];o+=n
 if len(p)>47 and p[12:14]==b'\x08\x00' and p[23]==6:
  t=14+(p[14]&15)*4
  if len(p)>t+13 and p[t+13]&4:count+=1
index=0
for row in rows:
 block=domain[index:index+row['sent_packets']];index+=row['sent_packets']
 intervals=[(b['receiver_monotonic']-a['receiver_monotonic'])*1000 for a,b in zip(block,block[1:])]
 row['mean_receive_interval_ms']=statistics.mean(intervals) if intervals else None
 row['trap_loss_percent']=(row['sent_packets']-row['traps_received'])/row['sent_packets']*100
summary={'http_packets_sent':sum(r['sent_packets'] for r in rows),'domain_traps_received':len(domain),'client_directed_rst_packets_captured_on_dedicated_return_wire':count,'summary_traps':[e for e in events if e['kind']==2],'domain_sequences_contiguous':sorted(e['sequence'] for e in domain)==list(range(1,len(domain)+1)),'resource_scope':'extended 10000-packet trial; sampler attached after it began' if meta.exists() else 'whole live HTTP experiment'}
if samples:
 for key in ('process_cpu_percent_one_core','process_cpu_percent_guest_capacity','guest_cpu_percent','rss_kib'):
  values=[s[key] for s in samples if s.get(key) is not None]
  summary[key]={'mean':statistics.mean(values),'max':max(values)} if values else None
 summary['resource_samples']=len(samples)
(OUT/'analysis.json').write_text(json.dumps({'trials':rows,'summary':summary},indent=2),encoding='utf-8')
lines=['# Live HTTP-driven SNMP replication — 13 October 2026 (Asia/Taipei)','',
 'Path: client HTTP packet fixtures → software virtual TAP → existing NPB → temporary DPDK Policy Server candidate → separate Net-SNMP receiver on Backend VM. No TCP sessions are established by the packet generator; captured resets prove generation/delivery on the return wire, not client denial.',
 '', '| Trial | HTTP packets | Domain traps | Loss (%) | Duplicates | Mean receive interval (ms) |','|---|---:|---:|---:|---:|---:|']
for r in rows:lines.append(f"| {r['trial']} | {r['sent_packets']} | {r['traps_received']} | {r['trap_loss_percent']:.3f} | {r['duplicates_delta']} | {r['mean_receive_interval_ms']:.4f} |")
lines+=['',f"Dedicated-wire client reset capture: {count:,} packets. Domain trap sequence continuity: {summary['domain_sequences_contiguous']}.",
 '', 'Reset capture is three packets below the 15,010-event input. Tcpdump reported zero kernel drops. Capture-readiness timing is a hypothesis, not a verified explanation; do not claim lossless reset delivery from this experiment.',
 '', 'Summary received at agent uptime '+', '.join(str(e['agent_uptime_cs']/100)+' s' for e in summary['summary_traps'])+'. Configured interval is 120 seconds; measured first dispatch includes startup/scheduler delay.',
 '', 'Receive interval is not one-way network latency. Runs were paced at 100 packets/s; this is not an unpaced burst or the thesis hardware. Candidate uses a bounded asynchronous BER sender, unlike the shell-per-trap implementation described in the thesis. This is an adapted functional/workload replication, not byte-identical source or identical numerical performance.',
 '', 'CPU is measured over one-second deltas. One-core CPU can exceed 100%; guest-capacity CPU divides by four vCPUs. Do not equate these directly to the thesis’s ambiguous 40-unit CPU scale. Sampling covers the extended run, not all five earlier trials.',
 '', 'Original Policy Server binary restored; temporary API rule removed. See run-cleanup.json, receiver cleanup.json and operation logs.',
 '', 'Zabbix polling/dashboard replication remains outstanding.']
(OUT/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(summary,indent=2));print('REPORT:',OUT/'RESULTS.md')
