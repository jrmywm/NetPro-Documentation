"""Bounded local lab endpoint/load/resource collector; no external targets."""
import argparse, concurrent.futures, hashlib, http.server, json, os, ssl
import subprocess, threading, time
from pathlib import Path
BODY=b'NetPro bounded virtual TAP stress test\n'*112
HASH=hashlib.sha256(BODY).hexdigest()

class Endpoint(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Length',str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)
    def log_message(self,*args):pass

class TestServer(http.server.ThreadingHTTPServer):
    request_queue_size=128
    daemon_threads=True

def serve(folder):
    servers=[]
    for port in (18080,18443):
        s=TestServer(('192.168.80.28',port),Endpoint)
        s.daemon_threads=True
        if port==18443:
            ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version=ctx.maximum_version=ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(str(folder/'cert.pem'),str(folder/'key.pem'))
            # Defer each TLS handshake to its request thread, not the accept loop.
            s.socket=ctx.wrap_socket(s.socket,server_side=True,do_handshake_on_connect=False)
        threading.Thread(target=s.serve_forever,daemon=True).start(); servers.append(s)
    time.sleep(990)
    for s in servers:s.shutdown()

def percentile(values,p):
    if not values:return None
    values=sorted(values); return values[round((len(values)-1)*p)]

def load(protocol,workers,duration,folder):
    assert workers in (1,4,8,16,32) and 1<=duration<=30
    port=18080 if protocol=='http' else 18443
    cmd=['curl','--interface','192.168.80.29','--noproxy','*','--http1.1','--resolve',f'netpro-stress.test:{port}:192.168.80.28','--connect-timeout','2','--max-time','4','-ksS','-w','\n%{http_code}',f'{protocol}://netpro-stress.test:{port}/']
    if protocol=='https':cmd[1:1]=['--tlsv1.2','--tls-max','1.2']
    deadline=time.monotonic()+duration
    def worker(number):
        rows=[]
        while time.monotonic()<deadline:
            start=time.monotonic()
            try:
                r=subprocess.run(cmd,capture_output=True,timeout=5)
                body,_,status=r.stdout.rpartition(b'\n')
                ok=r.returncode==0 and status==b'200' and hashlib.sha256(body).hexdigest()==HASH
                rows.append({'worker':number,'utc':time.time(),'elapsed_s':time.monotonic()-start,'curl_exit':r.returncode,'http':status.decode(errors='replace'),'body_ok':ok,'error':r.stderr.decode(errors='replace')[:200]})
                if not ok:break
            except subprocess.TimeoutExpired:
                rows.append({'worker':number,'utc':time.time(),'elapsed_s':time.monotonic()-start,'curl_exit':124,'http':'000','body_ok':False,'error':'bounded subprocess timeout'});break
        return rows
    start=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        rows=[row for batch in pool.map(worker,range(workers)) for row in batch]
    elapsed=time.monotonic()-start
    tag=f'{protocol}-c{workers}'
    (folder/(tag+'.jsonl')).write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
    latency=[r['elapsed_s']*1000 for r in rows if r['body_ok']]
    print(json.dumps({'stage':tag,'protocol':protocol,'concurrency':workers,'requested_seconds':duration,'elapsed_s':elapsed,'requests':len(rows),'success':len(latency),'failure':len(rows)-len(latency),'completed_rps':len(rows)/elapsed,'p50_ms':percentile(latency,.5),'p95_ms':percentile(latency,.95),'p99_ms':percentile(latency,.99),'max_ms':max(latency) if latency else None}),flush=True)

def monitor(folder):
    rows=[]; previous=None
    for sample in range(990):
        cpu=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
        total=sum(cpu); idle=cpu[3]+cpu[4]; pct=None
        if previous and total>previous[0]:pct=100*(1-(idle-previous[1])/(total-previous[0]))
        previous=(total,idle)
        mem={x.split(':')[0]:int(x.split()[1]) for x in Path('/proc/meminfo').read_text().splitlines() if x.split(':')[0] in ('MemTotal','MemAvailable','SwapTotal','SwapFree')}
        interfaces={}
        for nic in ('ens33','ens34','ens35','ens36','ens37','ens38','br-tap'):
            p=Path('/sys/class/net')/nic/'statistics'
            if p.exists():interfaces[nic]={n:int((p/n).read_text()) for n in ('rx_packets','tx_packets','rx_bytes','tx_bytes','rx_dropped','tx_dropped','rx_errors','tx_errors')}
        vmstat={l.split()[0]:int(l.split()[1]) for l in Path('/proc/vmstat').read_text().splitlines() if l.split()[0] in ('oom_kill','pswpin','pswpout')}
        row={'utc':time.time(),'cpu_busy_pct':pct,'memory_kib':mem,'interfaces':interfaces,'vmstat':vmstat}
        if os.uname().nodename=='backend-vm' and sample%5==0:
            try:
                r=subprocess.run(['curl','-ksS','--max-time','3','-o','/dev/null','-w','%{http_code}','https://127.0.0.1:3005/api/ps/pss'],capture_output=True,text=True,timeout=4)
                row['management_api']={'exit':r.returncode,'http':r.stdout.strip()}
            except subprocess.TimeoutExpired:row['management_api']={'exit':124,'http':'000'}
        with (folder/'resource.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        time.sleep(1)

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['serve','load','monitor']); p.add_argument('--folder',required=True);p.add_argument('--protocol',choices=['http','https']);p.add_argument('--workers',type=int,default=1);p.add_argument('--duration',type=int,default=10);a=p.parse_args();folder=Path(a.folder)
    if a.mode=='serve':serve(folder)
    elif a.mode=='monitor':monitor(folder)
    else:load(a.protocol,a.workers,a.duration,folder)
