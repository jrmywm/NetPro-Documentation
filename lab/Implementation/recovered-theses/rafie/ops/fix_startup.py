import os,paramiko,pathlib,json,time,hashlib,datetime
ROOT=pathlib.Path(__file__).resolve().parents[2]
tag=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=ROOT/'evidence'/('startup-retry-'+tag);out.mkdir(parents=True)
password=os.environ['NETPRO_LAB_PASSWORD']
def connect(ip):
 c=paramiko.SSHClient();c.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'));c.connect('192.168.31.'+ip,username='netpro',password=password,timeout=10);return c
ps=connect('31');mg=connect('35')
def run(c,cmd,sudo=False):
 if sudo:cmd='sudo -S -p "" bash -c '+__import__('shlex').quote(cmd)
 i,o,e=c.exec_command(cmd,timeout=180)
 if sudo:i.write(password+'\n');i.flush()
 a=o.read().decode(errors='replace');b=e.read().decode(errors='replace');rc=o.channel.recv_exit_status()
 if rc:raise RuntimeError(f'command failed {rc}: {a[-1000:]} {b[-1000:]}')
 return a
def status():return json.loads(run(ps,'cat /run/netpro-policy-cache.json'))
def rows():return run(ps,"sqlite3 /home/ubuntu/NetPro-Policy-Server/policy.db 'SELECT id,domain,ip_address FROM policies ORDER BY id;'",True)
work='/home/netpro/incoming/startup-retry-'+tag
live='/home/netpro/NetPro-Policy-Server'
baseline=rows();oldlink=run(ps,'readlink '+live+'/build/policyServer').strip()
backend_was_active=run(mg,'systemctl is-active netpro-backend').strip()=='active'
deployed=False;kafka_stopped=False
try:
 run(ps,'mkdir -p '+work+'/build; cp '+live+'/rafie_lookup.* '+live+'/Makefile '+work+'/')
 with ps.open_sftp() as s:s.put(str(ROOT/'rafie/policy-candidate/policyServer.c'),work+'/policyServer.c')
 build=run(ps,'cd '+work+' && make build/policyServer-shared');(out/'build.log').write_text(build)
 oldhash=run(ps,'sha256sum '+live+'/policyServer.c').split()[0]
 assert oldhash=='c770eb18afcfdb07a2650ab09c17f09d95ae74c02937dc2ae00b743f46db6ff8','Live source changed'
 run(ps,'cp '+live+'/policyServer.c '+work+'/policyServer.before.c; cp '+live+'/build/'+oldlink+' '+work+'/previous-binary')
 run(ps,'systemctl stop netpro-policy',True)
 run(ps,'cp '+work+'/policyServer.c '+live+'/policyServer.c; cp '+work+'/build/policyServer-shared '+live+'/build/policyServer-startup-'+tag+'; ln -sfn policyServer-startup-'+tag+' '+live+'/build/policyServer',True)
 deployed=True
 run(ps,'systemctl start netpro-policy',True)
 for _ in range(120):
  st=status()
  if st['policySyncReady']:break
  time.sleep(1)
 else:raise RuntimeError('Normal startup not ready')
 assert rows()==baseline,'Baseline changed'
 normal=st
 run(mg,'systemctl stop netpro-kafka',True);kafka_stopped=True
 run(ps,'systemctl restart netpro-policy',True)
 time.sleep(5);unavailable=status()
 assert not unavailable['policySyncReady'] and unavailable['initialHighwater']==-1,unavailable
 run(mg,'systemctl start netpro-kafka',True);kafka_stopped=False
 if backend_was_active:run(mg,'systemctl start netpro-backend',True)
 for _ in range(120):
  st=status()
  if st['policySyncReady']:break
  time.sleep(1)
 else:raise RuntimeError('Did not recover after Kafka restart')
 assert rows()==baseline,'Baseline changed after recovery'
 result={'passed':True,'normal':normal,'brokerUnavailable':unavailable,'recoveredWithoutPolicyRestart':st,'baselinePreserved':True,'oldBinary':oldlink,'work':work}
 (out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
except Exception:
 if kafka_stopped:run(mg,'systemctl start netpro-kafka',True)
 if backend_was_active:run(mg,'systemctl start netpro-backend',True)
 if deployed:
  run(ps,'systemctl stop netpro-policy; cp '+work+'/policyServer.before.c '+live+'/policyServer.c; ln -sfn '+oldlink+' '+live+'/build/policyServer; systemctl start netpro-policy',True)
 raise
finally:ps.close();mg.close()
