import sys,json,shlex,re,hashlib
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'snmp-quic-integration'))
from active_baseline import ActiveBaseline,CLIENT_HOST,WorkflowError
from remote import upload_file
HERE=Path(__file__).parent
OUT=HERE/'evidence'/('rst-stress-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
class BurstTest(ActiveBaseline):
    def __init__(self,concurrency):
        super().__init__('netpro',OUT,Path('C:/Users/jim/.ssh/known_hosts'))
        self.concurrency=concurrency;self.worker=None
    def run_probe(self,mode):
        if self.worker is None:
            self.worker=f'/home/netpro/incoming/rst-load-{self.run_id}.py'
            with self.clients[CLIENT_HOST].open_sftp() as s:upload_file(s,HERE/'rst_load_client.py',self.worker)
        remote=f'/home/netpro/incoming/rst-load-{mode}-{self.run_id}.pcap'
        command=f'''set -eu
test ! -e {shlex.quote(remote)}
capdir=$(mktemp -d /tmp/netpro-rst-load.XXXXXXXX)
pcap="$capdir/client.pcap"
timeout -s INT 35 tcpdump -U -Z root -ni ens37 -s0 -c 5000 -w "$pcap" 'tcp port 8443 and host 192.168.80.28' >/dev/null 2>"$capdir/capture.log" &
pid=$!
trap 'kill -INT "$pid" 2>/dev/null || true' EXIT
sleep 1
kill -0 "$pid"
python3 {shlex.quote(self.worker)} {mode} {self.concurrency} >"$capdir/trials.json" || true
sleep 2
kill -INT "$pid" 2>/dev/null || true
wait "$pid" || true
trap - EXIT
install -o netpro -g netpro -m 0644 "$pcap" {shlex.quote(remote)}
cat "$capdir/trials.json"
cat "$capdir/capture.log"
echo Retained_remote_evidence="$capdir"
'''
        _,stdout,_=self.command(CLIENT_HOST,f'{mode}_burst_c{self.concurrency}',command,sudo=True,timeout=35)
        rows=json.loads(next(line for line in stdout.splitlines() if line.startswith('{')))
        dropped=re.search(r'(\d+) packets dropped by kernel',stdout)
        local=OUT/f'c{self.concurrency}-{mode}.pcap';self.download_capture(remote,local)
        # Analyze Ethernet IPv4/TCP directly: verify reset destination ports for all failed trials.
        import struct
        data=local.read_bytes();endian={'d4c3b2a1':'<','a1b2c3d4':'>'}.get(data[:4].hex());assert endian
        assert struct.unpack_from(endian+'I',data,20)[0]==1
        offset=24;ports=set();rst_count=0
        while offset+16<=len(data):
            length=struct.unpack_from(endian+'I',data,offset+8)[0];offset+=16;frame=data[offset:offset+length];offset+=length
            if len(frame)<54 or frame[12:14]!=b'\x08\x00':continue
            ip=frame[14:];ihl=(ip[0]&15)*4
            if ip[9]!=6 or ip[12:16]!=bytes([192,168,80,28]) or ip[16:20]!=bytes([192,168,80,29]):continue
            tcp=ip[ihl:]
            if len(tcp)>=20 and tcp[13]&4:ports.add(struct.unpack_from('!H',tcp,2)[0]);rst_count+=1
        wanted={r['local_port'] for r in rows['rows']}
        rows.update({'capture_kernel_drops':int(dropped.group(1)) if dropped else None,'client_rst_packets':rst_count,'client_rst_ports':sorted(ports),'all_trials_have_client_rst':wanted<=ports,'pcap_sha256':hashlib.sha256(data).hexdigest()})
        passed=rows['attempted']==32 and rows['expected']==32 and rows['capture_kernel_drops']==0 and (wanted<=ports if mode=='deny' else rst_count==0)
        rows['passed']=passed
        (OUT/f'c{self.concurrency}-{mode}.json').write_text(json.dumps(rows,indent=2))
        self.document['outcomes'][mode]=rows;self.save()
        print(f'c={self.concurrency} {mode}: expected={rows["expected"]}/{rows["attempted"]}, RST={rst_count}, p95={rows["p95_ms"]:.2f}ms, passed={passed}',flush=True)
        return passed

if __name__=='__main__':
    results=[]
    for concurrency in (4,8,16):
        w=BurstTest(concurrency);rc=w.execute();results.append({'concurrency':concurrency,'exit':rc,'evidence':str(w.evidence_path)})
        if rc:break
    (OUT/'summary.json').write_text(json.dumps(results,indent=2))
    lines=['# RST concurrent deny–allow test','',f'UTC run: {OUT.name}',
        '## Method','Client → Virtual TAP → Gateway; mirror → NPB → Policy Server; dedicated NetPro-RST return path. One temporary SNI-only policy uses netpro-tap.test with unrelated dummy IP 192.0.2.123. Baseline API/SQLite IDs are verified and preserved by the existing guarded workflow.',
        '32 fresh TLS 1.2 connections per deny/allow phase, burst concurrency 4/8/16, one-second pauses between bursts. Existing reset policing remains 16 kbit/s with 2 KB burst. This is a bounded concurrency test, not unlimited reset throughput. Gateway endpoint uses the existing OpenSSL test server.',
        '', '| Concurrent clients | Phase | Expected/attempted | Client RST packets | p95 ms | Capture kernel drops | Result |','|---:|---|---:|---:|---:|---:|---|']
    for f in sorted(OUT.glob('c*-*.json')):
        x=json.loads(f.read_text());lines.append(f'| {x["concurrency"]} | {x["mode"]} | {x["expected"]}/{x["attempted"]} | {x["client_rst_packets"]} | {x["p95_ms"]:.2f} | {x["capture_kernel_drops"]} | {"PASS" if x["passed"] else "FAIL"} |')
    lines+=['','## Timing risk correction','“RST kalah cepat dari paket asli di perangkat edge” is an unverified architecture risk, not an observed fact in this lab. An out-of-band mirrored design can race the original connection, but this test measures outcome and capture evidence, not classification-to-injection latency T_total versus RTT. Burst injection of 3–5 RSTs and eBPF/XDP are investigation options, not validated fixes; neither was enabled here.',
        '', '## Acceptance and limits','Deny requires curl exit 35/56 with HTTP 000 and elapsed <2.5 seconds, plus a client-directed TCP RST captured for every trial local port. Timeouts and successful HTTP responses are failures. Allow requires HTTP 200 for every trial and no client-directed RST in its capture. Capture kernel drops must be zero. This does not measure loss at DPDK interfaces, establish physical fail-open, or guarantee blocking of established sessions, TLS variants, or QUIC.',
        'Cleanup and baseline re-verification are recorded in active-baseline JSON files. The test removes only its own temporary policy and owned return/listener state. It does not restart production services.',
        '', '## Repeat and screenshot','Run from the Windows workspace: `python -u work/tap-stress/run_rst_stress.py`. Capture the actual terminal stage summaries and evidence path; retain PCAP, JSON and hashes.']
    (OUT/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('EVIDENCE:',OUT.resolve(),flush=True)
