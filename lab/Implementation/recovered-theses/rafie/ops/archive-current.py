"""Retain reproducible active sources and compact final health, excluding credentials."""
import pathlib,paramiko,os,json,hashlib,datetime,shlex
root=pathlib.Path(__file__).resolve().parents[2];dest=root/'combined-policy';dest.mkdir(exist_ok=True)
c=paramiko.SSHClient();c.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'));c.connect('192.168.31.31',username='netpro',password=os.environ['NETPRO_LAB_PASSWORD'],timeout=10)
try:
 with c.open_sftp() as s:
  for n in ['policyServer.c','rafie_lookup.c','rafie_lookup.h','thesis_monitoring.c','thesis_monitoring.h','Makefile']:s.get('/home/netpro/NetPro-Policy-Server/'+n,str(dest/n))
 _,a,e=c.exec_command('readlink /home/netpro/NetPro-Policy-Server/build/policyServer; sha256sum /home/netpro/NetPro-Policy-Server/build/policyServer; cat /run/netpro-policy-cache.json')
 report={'collectedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'active':a.read().decode(),'sourceHashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.suffix in ['.c','.h'] or p.name=='Makefile'}}
 (dest/'DEPLOYED.json').write_text(json.dumps(report,indent=2));print(report['active'])
finally:c.close()
