import pathlib,os,paramiko,datetime,json,shlex
root=pathlib.Path(__file__).resolve().parents[2];tag=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')
out=root/'evidence'/('luthfi-original-'+tag);out.mkdir(parents=True)
original=pathlib.Path(r'C:\Users\jim\Documents\Codex\2026-09-11\referenced-chatgpt-conversation-this-is-an-2\work\thesis-review-2021\sources\recovered-code-20261029\Skripsi-main\Skripsi-main')
c=paramiko.SSHClient();c.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'));c.connect('192.168.31.35',username='netpro',password=os.environ['NETPRO_LAB_PASSWORD'],timeout=10)
def run(cmd):
 _,a,b=c.exec_command(cmd,timeout=240);s=a.read().decode();e=b.read().decode();rc=a.channel.recv_exit_status()
 if rc:raise RuntimeError(s[-1000:]+e[-1000:])
 return s
work='/home/netpro/incoming/luthfi-original-'+tag
try:
 run('mkdir -p '+work+'/app/{services,models,config}')
 with c.open_sftp() as s:
  for n in ['app/services/job.service.js','app/services/queue.service.js','app/config/db.config.js','app/models/blacklist.model.js','app/models/uploadJob.model.js','app/models/failedUpload.model.js']:
   s.put(str(original/n),work+'/'+n)
  s.put(str(root/'luthfi/tests/recovered-queue-baseline.js'),work+'/baseline.js')
 # Pinned versions match the recovered package ranges; isolated dependencies.
 (out/'install.log').write_text(run('cd '+work+' && npm install --no-audit --no-fund --ignore-scripts better-queue@3.8.12 fast-csv@5.0.2 sequelize@6.37.7 pg@8.15.5'))
 cmd='cd '+work+' && BASELINE_DATABASE=netpro_original_baseline_'+tag+' BASELINE_PG_PASSWORD=postgres node baseline.js '+work
 (out/'run.log').write_text(run(cmd))
 with c.open_sftp() as s:s.get(work+'/RESULTS.json',str(out/'RESULTS.json'))
 print('Original baseline completed; evidence:',out,flush=True)
finally:c.close()
