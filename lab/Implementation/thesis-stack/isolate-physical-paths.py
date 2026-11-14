"""Compare direct observation and direct injection independently, with rollback."""
from pathlib import Path
import datetime,hashlib,json,os,shutil,socket,subprocess,time

BASE=Path(__file__).resolve().parent
VMX=Path(r'D:\VMWare Virtual Machines\Policy-Server-VM\Policy-Server-VM.vmx')
VMRUN=Path(r'C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe')
DIRECT='52 67 af 19 3d ec 75 41-39 f8 64 c7 3c 4b ff 98'
TLS='52 75 f7 66 d0 54 5c 1c-e8 36 cc 0b df ed 36 90'
RST='52 fd db 17 0b 60 c3 3d-c4 c0 9e a8 f6 5e fc f6'
PROFILE=BASE/'evidence'/('isolated-paths-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
PROFILE.mkdir(parents=True)

def run(args,timeout=60):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise RuntimeError(f'{args[0]} exited {p.returncode}: {p.stderr[-400:]}')
    return p.stdout.strip()

def vmx_read():
    return VMX.read_text(encoding='utf-8',errors='strict')

def put_segment(text,adapter,expected,value):
    import re
    key=f'ethernet{adapter}.pvnID = "'
    pat=re.compile(r'(?m)^'+re.escape(key)+r'([^"\r\n]+)"$')
    match=list(pat.finditer(text))
    if len(match)!=1 or match[0].group(1)!=expected:
        raise RuntimeError(f'Adapter {adapter} does not have its expected segment; stop.')
    return text[:match[0].start(1)]+value+text[match[0].end(1):]

def set_segments(target,expected):
    old=vmx_read()
    new=put_segment(old,2,expected[0],target[0])
    new=put_segment(new,3,expected[1],target[1])
    tmp=VMX.with_suffix('.vmx.netpro-tmp')
    tmp.write_text(new,encoding='utf-8',newline='')
    os.replace(tmp,VMX)
    if vmx_read()!=new:raise RuntimeError('VMX verification failed')
    return hashlib.sha256(new.encode()).hexdigest()

def protect_stop():
    p=subprocess.run(['python',str(BASE/'prepare-policy-shutdown.py')],capture_output=True,text=True,timeout=70)
    if p.returncode:raise RuntimeError('Policy DB backup/stop guard failed: '+p.stderr[-500:])
    run([str(VMRUN),'stop',str(VMX),'soft'],timeout=55)
    if str(VMX).lower() in run([str(VMRUN),'list'],timeout=20).lower():
        raise RuntimeError('Policy Server VM did not stop; leave VMX unchanged.')

def start_wait():
    run([str(VMRUN),'start',str(VMX),'nogui'],timeout=55)
    # VMware boots this DPDK VM slowly after an adapter change; allow the guest
    # networking and sshd to settle instead of treating a slow SSH as failure.
    end=time.monotonic()+180
    while time.monotonic()<end:
        try:
            s=socket.create_connection(('192.168.31.31',22),2);s.close();return
        except OSError:time.sleep(2)
    raise RuntimeError('SSH did not return after Policy Server start')

original=vmx_read()
if 'ethernet2.pvnID = "'+TLS+'"' not in original or 'ethernet3.pvnID = "'+RST+'"' not in original:
    raise SystemExit('Expected full topology is not active; stop.')
shutil.copy2(VMX,PROFILE/'Policy-Server-VM.full-before.vmx')
results=[]
try:
    for name,segments,expected,envkey in [
        ('direct-observe-gateway-return',(DIRECT,RST),(TLS,RST),'THESIS_DIRECT_OBSERVE'),
        ('npb-observe-direct-injection',(TLS,DIRECT),(DIRECT,RST),'THESIS_DIRECT_INJECT'),
    ]:
        evidence=PROFILE/name;evidence.mkdir()
        protect_stop()
        vmx_hash=set_segments(segments,expected)
        (evidence/'adapter-change.json').write_text(json.dumps(
            {'adapter2_segment':segments[0],'adapter3_segment':segments[1],
             'vmx_sha256':vmx_hash},indent=2),encoding='utf-8')
        start_wait()
        env=os.environ.copy();env['THESIS_REPLICATION_PROFILE']='1';env[envkey]='1'
        p=subprocess.run(['python','-u',str(BASE/'validate-live-stack.py')],
                         env=env,capture_output=True,text=True,timeout=350)
        (evidence/'workflow.json').write_text(json.dumps(
            {'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr[-3000:]},
            indent=2),encoding='utf-8')
        results.append({'mode':name,'exit':p.returncode,'tail':p.stdout[-1200:]})
        print(name,'EXIT',p.returncode,p.stdout[-1000:],flush=True)
finally:
    # Never make restoration depend on SSH. If the guest is still running,
    # request a graceful VMware stop directly, then restore the full topology.
    running=str(VMX).lower() in run([str(VMRUN),'list'],timeout=20).lower()
    if running:
        run([str(VMRUN),'stop',str(VMX),'soft'],timeout=90)
        if str(VMX).lower() in run([str(VMRUN),'list'],timeout=20).lower():
            raise RuntimeError('Policy Server VM did not stop; refusing to edit its active VMX.')
    current=vmx_read()
    import re
    for adapter,value in [(2,TLS),(3,RST)]:
        pat=re.compile(r'(?m)^(ethernet'+str(adapter)+r'\.pvnID = ")[^"\r\n]+("$)')
        current,n=pat.subn(lambda m:m.group(1)+value+m.group(2),current)
        if n!=1:raise RuntimeError(f'Cannot safely restore adapter {adapter}; manual recovery needed.')
    if current!=vmx_read():
        tmp=VMX.with_suffix('.vmx.netpro-restore-tmp')
        tmp.write_text(current,encoding='utf-8',newline='');os.replace(tmp,VMX)
    start_wait()
    shutil.copy2(VMX,PROFILE/'Policy-Server-VM.full-restored.vmx')
    (PROFILE/'matrix-summary.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print('RESTORED_FULL_TOPOLOGY',PROFILE,flush=True)
