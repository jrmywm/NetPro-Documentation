"""Browser acceptance against the active persistent NetPro lab deployment."""
import datetime
import json
import os
from pathlib import Path
import shlex
import sys

BASE = Path(__file__).resolve().parent
sys.path[:0]=[str(BASE.parents[1]/'Testing/snmp-quic-integration'),str(BASE.parents[1]/'Testing/thesis-replication')]
from candidate_rollout import CandidateRollout
from remote import connect_verified
import active_baseline as ab

ab.TEST_DOMAIN = 'mysite.local'
ab.TEST_IP = '192.168.80.28'
OUT = BASE / 'evidence' / ('browser-persistent-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
OUT.mkdir(parents=True)
w = ab.ActiveBaseline(os.environ['NETPRO_LAB_PASSWORD'], OUT, Path.home()/'.ssh/known_hosts')
CL, GW = '192.168.31.39', '192.168.31.37'
results = []
rollouts = []
build = os.getenv("NETPRO_BROWSER_BUILD")

def command(host, label, shell):
    return w.command(host, label, shell, timeout=25)[1].strip()

def capture_navigation(options, profile, label):
    """Use Chromium's page target to capture a failed navigation too."""
    import base64
    import time
    import websocket
    client=w.clients[CL]
    browser='timeout 25 snap run chromium '+shlex.join(options+['--remote-debugging-port=0','about:blank'])
    _,stdout,stderr=client.exec_command(browser,timeout=28)
    ws=None
    try:
        deadline=time.monotonic()+10
        with client.open_sftp() as ftp:
            while True:
                try:
                    with ftp.open(profile+'/DevToolsActivePort') as f:
                        port,path=f.read().decode().splitlines()[:2]
                    break
                except (FileNotFoundError,ValueError):
                    if time.monotonic()>=deadline:
                        raise RuntimeError('Chromium debugging endpoint did not start')
                    time.sleep(.25)
        channel=client.get_transport().open_channel('direct-tcpip',('127.0.0.1',int(port)),('127.0.0.1',0))
        ws=websocket.create_connection('ws://127.0.0.1:'+port+path,socket=channel,timeout=12,suppress_origin=True)
        counter=0
        def call(method,params=None,session=None):
            nonlocal counter
            counter+=1
            request={'id':counter,'method':method,'params':params or {}}
            if session:request['sessionId']=session
            ws.send(json.dumps(request))
            while True:
                event=json.loads(ws.recv())
                if event.get('id')==counter:
                    if 'error' in event:raise RuntimeError(str(event['error']))
                    return event.get('result',{})
        target=call('Target.createTarget',{'url':'about:blank'})['targetId']
        session=call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId']
        navigation=call('Page.navigate',{'url':'https://mysite.local/'},session)
        time.sleep(.7)
        body=call('Runtime.evaluate',{'expression':'document.documentElement.outerHTML','returnByValue':True},session)['result'].get('value','')
        png=call('Page.captureScreenshot',{'format':'png'},session)['data']
        (OUT/(label+'.png')).write_bytes(base64.b64decode(png))
        (OUT/(label+'.navigation.json')).write_text(json.dumps(navigation,indent=2),encoding='utf-8')
        try:call('Browser.close')
        except websocket.WebSocketConnectionClosedException:pass
        return body,stderr.read().decode(errors='replace'),stdout.channel.recv_exit_status()
    finally:
        if ws:ws.close()

def probe(phase, mode):
    label = phase+'-'+mode
    remote_log = remote_dir+'/'+label+'.json'
    options = [
        '--headless','--disable-background-networking','--no-proxy-server',
        '--host-resolver-rules=MAP mysite.local 192.168.80.28',
        '--ignore-certificate-errors-spki-list='+pin,
        '--user-data-dir='+remote_dir+'/'+mode,
        '--log-net-log='+remote_log,
    ]
    if mode=='h3':options.append('--origin-to-force-quic-on=mysite.local:443')
    if mode=='tcp':options.append('--disable-quic')
    screenshot=os.getenv('NETPRO_BROWSER_SCREENSHOTS')=='1' and mode=='h3'
    if screenshot:
        # A unique profile prevents stale debugger ports and cached responses.
        profile=remote_dir+'/'+label
        options=[x for x in options if not x.startswith('--user-data-dir=')]
        options.extend(['--user-data-dir='+profile,'--window-size=1000,640'])
        body,error,rc=capture_navigation(options,profile,label)
    else:
        browser='timeout 18 snap run chromium '+shlex.join(options+['--dump-dom','https://mysite.local/'])
        _,stdout,stderr=w.clients[CL].exec_command(browser,timeout=23)
        body=stdout.read().decode(errors='replace')
        error=stderr.read().decode(errors='replace')
        rc=stdout.channel.recv_exit_status()
    (OUT/(label+'.html')).write_text(body,encoding='utf-8')
    (OUT/(label+'.stderr.txt')).write_text(error,encoding='utf-8')
    with w.clients[CL].open_sftp() as ftp:ftp.get(remote_log,str(OUT/(label+'.json')))
    log=json.loads((OUT/(label+'.json')).read_text(encoding='utf-8'))
    names={value:key for key,value in log['constants']['logEventTypes'].items()}
    events=[(names.get(e['type']),e['source']['id'],e.get('params',{})) for e in log['events']]
    quic={id for name,id,p in events if name=='QUIC_SESSION' and p.get('host')=='mysite.local'}
    tcp={id for name,id,p in events if name=='TCP_CONNECT' and p.get('remote_address')=='192.168.80.28:443'}
    resets=sum(name=='SSL_CONNECT' and id in tcp and p.get('net_error')==-101 for name,id,p in events)
    closes=sum(name=='QUIC_SESSION_CLOSED' and id in quic and p.get('from_peer') is True for name,id,p in events)
    completed=sum(name=='QUIC_SESSION_CRYPTO_HANDSHAKE_COMPLETE' and id in quic for name,id,p in events)
    loaded='NetPro thesis Caddy HTTP/3 endpoint' in body
    if phase=='deny':
        passed=not loaded and (closes>0 if mode=='h3' else resets>0)
    else:
        passed=loaded and rc==0 and (completed>0 if mode=='h3' else bool(tcp or quic))
    row=dict(phase=phase,mode=mode,passed=passed,loaded=loaded,exit=rc,quic_sessions=len(quic),
             tcp_connections=len(tcp),tls_resets=resets,peer_closes=closes,quic_handshakes=completed)
    results.append(row)
    print(json.dumps(row),flush=True)

def curl_probe(phase, mode):
    option='--http3-only' if mode=='h3' else '--http1.1'
    shell=("/home/netpro/netpro-thesis/http3/prefix/bin/curl "+option+
           " --noproxy '*' --interface 192.168.80.29 --resolve mysite.local:443:192.168.80.28"+
           " -k --max-time 5 -sS -o /dev/null -w 'HTTP %{http_code} VERSION %{http_version}\\n'"+
           " https://mysite.local/; rc=$?; echo CURL_EXIT=$rc")
    output=command(CL,phase+'-curl-'+mode,shell)
    rc=int(output.split('CURL_EXIT=')[-1].strip())
    passed=(rc!=0 and 'HTTP 000' in output) if phase=='deny' else (rc==0 and 'HTTP 200' in output)
    row=dict(phase=phase,mode='curl-'+mode,passed=passed,output=output)
    results.append(row)
    print(json.dumps(row),flush=True)

def run_phase(phase):
    for mode in ('h3','tcp','normal'):probe(phase,mode)
    for mode in ('h3','tcp'):curl_probe(phase,mode)

try:
    w.connect_all()
    w.baseline()
    if build:
        folder=Path(build)
        ps=json.loads((folder/'build-result.json').read_text())
        npb=json.loads((folder/'npb-build-result.json').read_text())
        assert ps['rc']==0
        host='192.168.31.33'
        w.clients[host],_=connect_verified(host,'netpro',os.environ['NETPRO_LAB_PASSWORD'],Path.home()/'.ssh/known_hosts')
        specs=[
            ('192.168.31.31','policy-server-vm','netpro-policy',ps['remote']+'/policyServer-browser',ps['stdout'].splitlines()[-1].split()[0],
             'cdc47721b017357569ebfc04f9e69b3f2f15f58bf60b3347aed7a9ae74b63e6f',
             {'NETPRO_REPLAY_READINESS':'1','NETPRO_REPLICATION_STATS_PATH':ps['remote']+'/replication-stats.json'}),
            (host,'npb-vm','netpro-npb',npb['remote']+'/packetBroker-browser',npb['sha256'],
             '034e97f0818ffa77f80a8cbf61714b911949fe30937a437871af5a2c6707e1bb',{}),
        ]
        for ip,hostname,unit,binary,sha,original,env in specs:
            rollout=CandidateRollout(w.clients[ip],hostname,unit,binary,sha,original,OUT,env)
            rollouts.append(rollout)
            rollout.start()
    command(GW,'browser-gateway-active' ,'systemctl is-active netpro-quic-lab.service')
    pin=command(GW,'lab-leaf-pin',"""set -o pipefail
openssl s_client -connect 192.168.80.28:443 -servername mysite.local </dev/null 2>/dev/null | openssl x509 -pubkey -noout | openssl pkey -pubin -outform DER | openssl dgst -sha256 -binary | openssl base64 -A
""")
    assert len(pin)==44
    remote_dir=command(CL,'browser-profile-dir','mkdir -p ~/snap/chromium/common && mktemp -d ~/snap/chromium/common/netpro-browser.XXXXXX')
    run_phase('before')
    if not all(x['passed'] for x in results):raise RuntimeError('Browser baseline incomplete')
    w.create_policy()
    try:
        run_phase('deny')
    finally:
        w.delete_policy_exactly()
    run_phase('after')
    w.baseline()
finally:
    try:
        if w.policy_id:w.delete_policy_exactly()
    finally:
        for rollout in reversed(rollouts):
            rollout.stop()
        (OUT/'browser-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        for c in w.clients.values():c.close()
        print('EVIDENCE',OUT,flush=True)
if not all(x['passed'] for x in results):raise SystemExit('Browser acceptance incomplete or failed')
