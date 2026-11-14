import sys,os,json,time,shlex,hashlib,concurrent.futures
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command

HERE=Path(__file__).parent
RUN='tap-stress-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
OUT=HERE/'evidence'/RUN;OUT.mkdir(parents=True)
PASSWORD=os.environ.get('NETPRO_LAB_PASSWORD','netpro')
KNOWN=Path('C:/Users/jim/.ssh/known_hosts')
IPS={'tap':'192.168.31.38','gateway':'192.168.31.37','client':'192.168.31.39','npb':'192.168.31.33','policy':'192.168.31.31'}
clients={};remote={};units=[];stages=[]
def write_evidence(path,text):
    path.write_text(text,encoding='utf-8')
def execute(role,cmd,sudo=False,timeout=15):
    rc,out,err=run_remote_command(clients[role],cmd,PASSWORD if sudo else None,timeout)
    if rc:raise RuntimeError(f'{role} command failed {rc}: {out} {err}')
    return out
def snapshot(role,label):
    cmd="date -u; uptime; free -m; ip -br addr; ip -s link; systemctl is-active netpro-virtual-tap-mirror netpro-npb netpro-policy; readlink /home/netpro/NetPro-Network-Packet-Broker/build/packetBroker; readlink /home/netpro/NetPro-Policy-Server/build/policyServer; true"
    out=execute(role,cmd);write_evidence(OUT/f'{label}-{role}.txt',out)
    if role=='tap':write_evidence(OUT/f'{label}-tap-tc.txt',execute(role,'tc -s filter show dev ens34 ingress; tc -s filter show dev ens35 ingress; bridge link',True))
try:
    for role,ip in IPS.items():
        clients[role],_=connect_verified(ip,'netpro',PASSWORD,KNOWN)
        snapshot(role,'before')
    assert 'active'==execute('tap','systemctl is-active netpro-virtual-tap-mirror').strip()
    execute('npb','systemctl is-active --quiet netpro-npb');execute('policy','systemctl is-active --quiet netpro-policy')
    route=execute('client','ip route get 192.168.80.28')
    assert 'dev ens37' in route and 'src 192.168.80.29' in route
    for role in ('tap','gateway','client'):
        base=execute(role,'mktemp -d /home/netpro/incoming/tap-stress.XXXXXXXX').strip()
        assert base.startswith('/home/netpro/incoming/tap-stress.')
        remote[role]=base
        with clients[role].open_sftp() as s:s.put(str(HERE/'lab_worker.py'),base+'/lab_worker.py')
    base=remote['gateway']
    # Match the server's reuse-address behavior: TIME_WAIT is not a live listener.
    # This still refuses an existing listener and never kills another process.
    try:
        execute('gateway',"python3 -c 'import socket; sockets=[]; [(sockets.append(s:=socket.socket()),s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1),s.bind((\"192.168.80.28\",p))) for p in (18080,18443)]'")
    except RuntimeError:
        write_evidence(OUT/'port-conflict.txt',execute('gateway','ss -ltnp; ss -tan state time-wait',True))
        raise RuntimeError('Temporary test port 18080 or 18443 unavailable; see port-conflict.txt. No existing process was stopped.')
    execute('gateway',f'openssl req -x509 -newkey rsa:2048 -nodes -days 1 -keyout {base}/key.pem -out {base}/cert.pem -subj /CN=netpro-stress.test >/dev/null 2>&1; chmod 600 {base}/key.pem')
    for role,mode in [('gateway','serve'),('tap','monitor'),('gateway','monitor'),('client','monitor')]:
        unit=RUN+'-'+role+'-'+mode
        execute(role,f'systemd-run --quiet --unit={unit} --collect --property=RuntimeMaxSec=360 --property=User=netpro /usr/bin/python3 {remote[role]}/lab_worker.py {mode} --folder {remote[role]}',True)
        units.append((role,unit))
    ready=False
    for _ in range(15):
        time.sleep(1)
        rc,out,err=run_remote_command(clients['gateway'],'curl --noproxy "*" --max-time 2 -fsS http://192.168.80.28:18080/ >/dev/null')
        if rc==0:ready=True;break
    write_evidence(OUT/'listener-readiness.txt',execute('gateway',f'systemctl status {RUN}-gateway-serve.service --no-pager; ss -ltn; true'))
    if not ready:raise RuntimeError('Gateway temporary listener not ready; no load generated')
    for protocol in ('http','https'):
        for concurrency in (1,4,8,16):
            began=time.time()
            result=json.loads(execute('client',f'python3 {remote["client"]}/lab_worker.py load --folder {remote["client"]} --protocol {protocol} --workers {concurrency} --duration 10',timeout=25))
            result['start_utc_epoch']=began;result['end_utc_epoch']=time.time();stages.append(result)
            # Preserve stage rows immediately; recovery reuses the one-client filename remotely.
            with clients['client'].open_sftp() as s:
                s.get(remote['client']+'/'+result['stage']+'.jsonl',str(OUT/('stage-'+result['stage']+'.jsonl')))
            print(json.dumps(result),flush=True)
            if result['failure']:raise RuntimeError('Request failure: higher load stages cancelled')
            # Host protection: stop escalation below 128 MiB available or service failure.
            mem=execute('tap',"awk '/MemAvailable:/ {print $2}' /proc/meminfo").strip()
            if int(mem)<131072:raise RuntimeError('Low TAP available memory: stopped escalation')
            execute('tap','systemctl is-active --quiet netpro-virtual-tap-mirror')
    for role in IPS:snapshot(role,'after')
    execute('npb','systemctl is-active --quiet netpro-npb');execute('policy','systemctl is-active --quiet netpro-policy')
    status='completed'
except Exception as e:
    status='stopped';print('STOP:',str(e),flush=True)
    write_evidence(OUT/'error.txt',str(e))
finally:
    # A low-load recovery check and final counters precede removal of owned listeners.
    if 'client' in remote and any(mode.endswith('-serve') for _,mode in units):
        for protocol in ('http','https'):
            try:
                recovery=json.loads(execute('client',f'python3 {remote["client"]}/lab_worker.py load --folder {remote["client"]} --protocol {protocol} --workers 1 --duration 3',timeout=10))
                with clients['client'].open_sftp() as s:s.get(remote['client']+'/'+protocol+'-c1.jsonl',str(OUT/('recovery-'+protocol+'.jsonl')))
                report_path=OUT/('recovery-'+protocol+'.json');write_evidence(report_path,json.dumps(recovery,indent=2))
            except Exception as e:write_evidence(OUT/('recovery-'+protocol+'-error.txt'),str(e))
    for role in clients:
        try:snapshot(role,'final')
        except Exception as e:write_evidence(OUT/f'final-error-{role}.txt',str(e))
    for role,unit in units:
        try:execute(role,f'systemctl stop {unit}.service',True)
        except Exception as e:write_evidence(OUT/f'cleanup-{role}.txt',str(e))
    for role,folder in remote.items():
        try:
            with clients[role].open_sftp() as s:
                for name in s.listdir(folder):
                    if name.endswith('.jsonl'):s.get(folder+'/'+name,str(OUT/(role+'-'+name)))
        except Exception as e:write_evidence(OUT/f'download-{role}.txt',str(e))
    report={'run':RUN,'status':status,'scope':'Bounded local virtual TAP HTTP/TLS request load; no policy changes, no mirror toggle; not throughput saturation or blocking benchmark','hosts':IPS,'remote_evidence':remote,'stages':stages,'utc_end':datetime.now(timezone.utc).isoformat(),'worker_sha256':hashlib.sha256((HERE/'lab_worker.py').read_bytes()).hexdigest()}
    write_evidence(OUT/'summary.json',json.dumps(report,indent=2))
    lines=['# Virtual TAP bounded load test',f'Run: {RUN}',f'Status: {status}',
        '', '## Method',
        'Local Client → Linux bridge Virtual TAP → Gateway. Mirroring stays enabled. NPB and Policy Server are checked active; no policy is changed and no blocking/RST test is performed.',
        'HTTP and fresh TLS 1.2 connections use temporary ports 18080/18443, 4,368-byte verified response bodies, concurrency 1/4/8/16, ten seconds per stage. Curl runs per request; latency includes its process overhead. Private self-signed certificate is accepted only by the test curl command.',
        '', '## Results', '| Protocol | Concurrent workers | Successful/attempted | Requests/s | p95 ms | p99 ms |', '|---|---:|---:|---:|---:|---:|']
    for x in stages:lines.append(f'| {x["protocol"]} | {x["concurrency"]} | {x["success"]}/{x["requests"]} | {x["completed_rps"]:.2f} | {x["p95_ms"] or 0:.2f} | {x["p99_ms"] or 0:.2f} |')
    lines+=['','## Resources and observed counters']
    for role in ('tap','gateway','client'):
        f=OUT/(role+'-resource.jsonl')
        if not f.exists():continue
        records=[json.loads(s) for s in f.read_text().splitlines()]
        if not records:continue
        cpu=[r['cpu_busy_pct'] for r in records if r['cpu_busy_pct'] is not None]
        lines.append(f'- {role}: {len(records)} one-second samples; mean CPU busy {sum(cpu)/len(cpu) if cpu else 0:.2f}%, peak {max(cpu) if cpu else 0:.2f}%; minimum MemAvailable {min(r["memory_kib"]["MemAvailable"] for r in records)/1024:.1f} MiB.')
        if role=='tap':
            for nic,final in records[-1]['interfaces'].items():
                initial=records[0]['interfaces'][nic]
                delta={k:final[k]-initial[k] for k in final}
                lines.append(f'- TAP {nic} counter deltas: '+', '.join(f'{k}={v}' for k,v in delta.items())+'.')
    lines+=['','## Recovery and cleanup']
    for protocol in ('http','https'):
        f=OUT/('recovery-'+protocol+'.json')
        if f.exists():
            x=json.loads(f.read_text());lines.append(f'- {protocol} recovery at one client: {x["success"]}/{x["requests"]} succeeded.')
    lines+=['- Only run-owned transient server/monitor units are stopped. Temporary evidence/certificate folders are retained on the VMs; no bridge, mirror, VM, policy, MTU, or offload configuration is altered.',
        '', '## Interpretation and limits',
        'This is a short, application-level load sweep on a shared VMware host, not a sustained soak, maximum packets/s or line-rate measurement. Endpoints, curl process creation, TLS handshakes, CPU scheduling and VM resources can limit results. Mirror TX counters confirm copies were emitted, not that every copy was processed by DPDK NPB/Policy Server. Zero interface drops is not proof of end-to-end zero packet loss. No physical fail-open or live QUIC/SNMP validation is claimed.',
        'Preserve the earlier run tap-stress-20261010T125018Z: TLS at 16 workers had five connect timeouts with the small default accept queue. The rerun uses queue 128 and per-thread TLS handshakes. This comparison changes the test endpoint only and does not establish the sole cause of those timeouts.',
        '', '## Reproduce', 'From the Windows workspace: `python -u work/tap-stress/run_stress.py`. It requires existing trusted SSH keys, the configured lab hosts, Paramiko, and the lab password via NETPRO_LAB_PASSWORD or the existing lab default. Each run creates a new evidence directory.',
        'For an actual terminal screenshot, run that command in PowerShell and capture the stage summaries and final evidence path. Stage-prefixed JSONL files preserve load-stage requests; recovery files preserve the separate low-load probes. Resource samples, before/final counters and summary.json are retained alongside this report.']
    write_evidence(OUT/'RESULTS.md','\n'.join(lines)+'\n')
    for c in clients.values():c.close()
    print('EVIDENCE:',OUT.resolve(),flush=True)
