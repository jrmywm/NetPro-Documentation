"""Repeat existing guarded system/module validations; retain evidence, no rollout."""
from pathlib import Path
import sys,json,re,hashlib,shlex
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'snmp-quic-integration'))
from active_baseline import ActiveBaseline,CLIENT_HOST,GATEWAY_HOST,POLICY_HOST
from remote import connect_verified,run_remote_command
BASE=Path(__file__).parent
OUT=BASE/'evidence'/('verification-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
KNOWN=Path('C:/Users/jim/.ssh/known_hosts')
findings={};errors=[]
def save(name,value):
    (OUT/name).write_text(value if isinstance(value,str) else json.dumps(value,indent=2),encoding='utf-8')

# Module checks never replace or restart the production Policy Server.
c=None
try:
    c,_=connect_verified(POLICY_HOST,'netpro','netpro',KNOWN)
    # Private dependency extraction, never a system package install. The harness
    # independently verifies the uploaded package against apt metadata.
    rc,depdir,err=run_remote_command(c,'mktemp -d /home/netpro/incoming/quic-verification-deps.XXXXXX')
    if rc:raise RuntimeError('private QUIC dependency directory failed')
    depdir=depdir.strip()
    pkg=Path('C:/Users/jim/Documents/Codex/2026-09-11/referenced-chatgpt-conversation-this-is-an-2/work/snmp-quic-integration/libssl-dev_1.1.1f-1ubuntu2.24_amd64.deb')
    with c.open_sftp() as s:
        s.put(str(pkg),depdir+'/'+pkg.name)
        with s.open('/home/netpro/incoming/linux-bundle-v5/test-v5-private-headers.sh') as f: harness=f.read().decode()
        harness=harness.replace('retained=/tmp/quic-openssl-uploaded-deb.EgdlXg','retained='+depdir)
        # Extraction follows all package identity/hash/size checks in the harness.
        harness=harness.replace('multiarch="$(dpkg-architecture -qDEB_HOST_MULTIARCH)"','dpkg-deb -x "$deb_file" "$retained/headers"\nmultiarch="$(dpkg-architecture -qDEB_HOST_MULTIARCH)"')
        with s.open(depdir+'/test.sh','w') as f:f.write(harness)
    save('quic-harness.sh',harness)
    save('quic-dependency.json',{'remote_directory':depdir,'package_sha256':hashlib.sha256(pkg.read_bytes()).hexdigest(),'system_install':False})
    for name,script in [('snmp','/home/netpro/incoming/isolated-snmp-receiver-20261010/run-private-validation.sh'),('quic',depdir+'/test.sh')]:
        rc,out,err=run_remote_command(c,'/bin/bash '+shlex.quote(script),timeout=90)
        save(name+'.txt',out+err)
        passed=rc==0 and ('PASS: Net-SNMP accepted' in out if name=='snmp' else 'REGULAR_TEST=PASS' in out and 'ASAN_UBSAN_TEST=PASS' in out and out.count('PASS ')==36)
        findings[name]={'passed':passed,'exit':rc,'scope':'isolated loopback reporter/receiver' if name=='snmp' else 'offline QUIC v1 parser regular and ASAN/UBSAN; not live enforcement'}
        if name=='snmp':
            match=re.search(r'Private run evidence: (/home/netpro/incoming/isolated-snmp-receiver-20261010/\.private-run\.[A-Za-z0-9]+)',out)
            if match:
                with c.open_sftp() as s:
                    for f in ('receiver.log','sender.log','version.txt','ldd.txt'):s.get(match.group(1)+'/'+f,str(OUT/('snmp-'+f)))
        if name=='quic':
            match=re.search(r'V5_EVIDENCE_RETAINED=(/tmp/quic-v5-validation\.[A-Za-z0-9]+)',out)
            if match:
                with c.open_sftp() as s:
                    for f in ('build.log','test.log','sanitizer-build.log','sanitizer-test.log'):s.get(match.group(1)+'/'+f,str(OUT/('quic-'+f)))
        print(name.upper(), 'PASS' if passed else 'FAIL',flush=True)
    rc,out,err=run_remote_command(c,'systemctl is-active netpro-policy; ss -lun; uptime')
    save('policy-module-postcheck.txt',out+err)
except Exception as e:errors.append('module checks: '+str(e));print(errors[-1],flush=True)
finally:
    if c:c.close()

# System check: monitor on/off/on, with existing emergency restoration timer.
w=ActiveBaseline('netpro',OUT,KNOWN);tap=None;owns_mirror=False
try:
    w.connect_all();w.baseline();w.start_gateway_server()
    tap,_=connect_verified('192.168.31.38','netpro','netpro',KNOWN)
    def tapcmd(label,cmd):
        rc,out,err=run_remote_command(tap,cmd,'netpro',timeout=15);save(label+'.txt',out+err)
        if rc:raise RuntimeError(label+' failed '+str(rc))
        return out
    on=json.loads((BASE/'operations-on-after-and-cleanup.json').read_text())
    off=json.loads((BASE/'operations-mirror-off-probe.json').read_text())
    stop=json.loads((BASE/'operations-mirror-off-stop.json').read_text())[0]['command']
    restore=json.loads((BASE/'operations-mirror-restore.json').read_text())[0]['command']
    for phase in ('on-before','off','on-after'):
        if phase=='off':
            tapcmd('timer-ownership-preflight','test "$(systemctl show -p LoadState --value netpro-mirror-restore.timer)" = not-found; test "$(systemctl show -p LoadState --value netpro-mirror-restore.service)" = not-found')
            owns_mirror=True;tapcmd('mirror-stop-with-recovery-timer',stop)
        elif phase=='on-after':tapcmd('mirror-restore',restore);owns_mirror=False
        checks=off if phase=='off' else on
        tapcmd(phase+'-before',checks[0]['command'])
        counter_before=tapcmd(phase+'-counter-before','cat /sys/class/net/ens36/statistics/tx_packets; cat /sys/class/net/ens36/statistics/tx_bytes')
        rc,out,err=w.command(CLIENT_HOST,phase+'-requests',checks[1]['command'],timeout=55)
        save(phase+'-requests.txt',out+err)
        counter_after=tapcmd(phase+'-counter-after','cat /sys/class/net/ens36/statistics/tx_packets; cat /sys/class/net/ens36/statistics/tx_bytes')
        tapcmd(phase+'-after',checks[2]['command'])
        a=list(map(int,counter_before.split()));b=list(map(int,counter_after.split()))
        tx=b[0]-a[0]
        passed=rc==0 and 'http_200=20/20 tls_200=20/20 attempted=40/40' in out and (tx==0 if phase=='off' else tx>0)
        findings[phase]={'passed':passed,'http_success':20 if passed else None,'tls_success':20 if passed else None,'monitor_tx_packet_delta':tx,'monitor_tx_byte_delta':b[1]-a[1]}
        print('TAP',phase,'PASS' if passed else 'FAIL','monitor TX delta',tx,flush=True)
        if not passed:raise RuntimeError(phase+' acceptance criteria failed')
except Exception as e:errors.append('TAP checks: '+str(e));print(errors[-1],flush=True)
finally:
    if owns_mirror and tap:
        try:tapcmd('emergency-mirror-restore',restore)
        except Exception as e:errors.append('mirror restoration: '+str(e))
    if tap:tap.close()
    w.cleanup()
    if any(x.get('status') in ('error','needs_review') for x in w.document['cleanup']):errors.append('TAP test cleanup needs review')

# Separate guarded TLS deny/allow, including proof of ClientHello segmentation.
if all(findings.get(k,{}).get('passed') for k in ('on-before','off','on-after')) and not errors:
    w=ActiveBaseline('netpro',OUT,KNOWN,split_clienthello=True)
    rc=w.execute();findings['tls-deny-allow-split']={'passed':rc==0,'scope':'20 deny + 20 allow, new TLS 1.2 connections, split ClientHello PCAP'}
    print('TLS split deny/allow','PASS' if rc==0 else 'FAIL',flush=True)
save('summary.json',{'findings':findings,'errors':errors,'created_local_date':'10 October 2026','timezone':'Asia/Taipei'})
lines=['# System and module validation','', '| Check | Result | Scope or observation |','|---|---|---|']
for k,v in findings.items():lines.append(f'| {k} | {"PASS" if v["passed"] else "FAIL"} | {v.get("scope",str(v))} |')
lines+=['','Mirror TX measures copies emitted, not downstream packet-loss rate. Monitor-off test leaves bridge forwarding and the TAP VM running; it does not prove physical fail-open. SNMP is isolated loopback delivery, QUIC is offline parsing; neither is live end-to-end integration. TLS blocking applies only to the tested new TLS 1.2 connections.','', 'Errors: '+('; '.join(errors) if errors else 'None'),'', 'Repeat from Windows PowerShell: `python -u C:/Users/jim/Documents/NetPro/Testing/verification/run_verification.py`. Capture actual terminal summaries. Evidence includes logs, PCAP, cleanup and hashes.']
save('RESULTS.md','\n'.join(lines)+'\n')
save('SHA256.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='SHA256.json'})
print('EVIDENCE:',OUT.resolve(),flush=True)
