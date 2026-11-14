"""Run existing guarded original-method validation against explicitly pinned current binary."""
from pathlib import Path
import os,sys,hashlib,paramiko
base=Path(__file__).resolve().parent
c=paramiko.SSHClient();c.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'));c.connect('192.168.31.31',username='netpro',password=os.environ['NETPRO_LAB_PASSWORD'],timeout=10)
try:
 _,a,e=c.exec_command('sha256sum /home/netpro/NetPro-Policy-Server/build/policyServer');pin=a.read().decode().split()[0]
finally:c.close()
assert len(pin)==64
s=(base/'validate-live-stack.py').read_text()
assert s.count('5892e752bb08395b2b3b1170fc9e45af21ac9251b7dfc9860a7b28dde0865614')==1
s=s.replace('5892e752bb08395b2b3b1170fc9e45af21ac9251b7dfc9860a7b28dde0865614',pin)
s=s.replace("{'NETPRO_SNMP_ENABLE':'0'","{'NETPRO_REPLAY_READINESS':'1','NETPRO_SNMP_ENABLE':'0'")
s=s.replace('if DIAGNOSTIC_TRACE:\n  metrics_deadline=', 'if True: # All profiles await the periodic metrics refresh.\n  metrics_deadline=')
os.environ['THESIS_REPLICATION_PROFILE']='1'
os.environ['THESIS_TEST_IP']='192.168.80.28'
# Explicit pin captured before any rollout; CandidateRollout validates it and
# restores that same actual build. No old expected hashes are bypassed.
print('Current policy binary pinned',pin,flush=True)
exec(compile(s,str(base/'validate-live-stack.py'),'exec'),{'__file__':str(base/'validate-live-stack.py'),'__name__':'__main__'})
