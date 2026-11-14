import pathlib,os,paramiko,datetime,json
root=pathlib.Path(__file__).resolve().parents[2];tag=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S');out=root/'evidence'/('luthfi-adapted-'+tag);out.mkdir(parents=True)
c=paramiko.SSHClient();c.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'));c.connect('192.168.31.35',username='netpro',password=os.environ['NETPRO_LAB_PASSWORD'],timeout=10)
def run(cmd):
 _,a,b=c.exec_command(cmd,timeout=240);s=a.read().decode();e=b.read().decode();rc=a.channel.recv_exit_status()
 if rc:raise RuntimeError(s[-1000:]+e[-1000:])
 return s
work='/home/netpro/incoming/luthfi-adapted-'+tag
try:
 run('cp -a /home/netpro/incoming/luthfi-original-20261106230840 '+work)
 with c.open_sftp() as s:
  for n in ['app/services/bounded-upload.service.js','app/services/csv-batches.js','app/models/blacklist.model.js','app/models/uploadJob.model.js','app/models/failedUpload.model.js']:
   s.put(str(root/'luthfi'/n),work+'/'+n)
  s.put(str(root/'luthfi/tests/recovered-queue-baseline.js'),work+'/baseline.js')
 (out/'run.log').write_text(run('cd '+work+' && BASELINE_ADAPTED=1 BASELINE_DATABASE=netpro_original_baseline_'+tag+' BASELINE_PG_PASSWORD=postgres node baseline.js '+work))
 with c.open_sftp() as s:s.get(work+'/RESULTS.json',str(out/'RESULTS.json'))
 print('Adapted core completed; evidence',out,flush=True)
finally:c.close()
