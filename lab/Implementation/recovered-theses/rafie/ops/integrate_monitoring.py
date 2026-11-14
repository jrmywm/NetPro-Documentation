"""Build and guarded rollout of recovered monitoring plus accepted lookup/retry."""
import os,pathlib,paramiko,datetime,json,time,hashlib,shlex,re
root=pathlib.Path(__file__).resolve().parents[2];stack=root.parent/'thesis-stack'
tag=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=root/'evidence'/('monitoring-merge-'+tag);out.mkdir(parents=True)
source=(root/'rafie/policy-candidate/policyServer.c').read_text()
source=source.replace('"192.168.0.90:9092"','"192.168.31.35:9092"')
source=source.replace('#include "rafie_lookup.h"','#include "rafie_lookup.h"\n#include "thesis_monitoring.h"')
assert '#include "thesis_monitoring.h"' in source
source=re.sub(r'(domain_check = domain_checker\(domain\);)(\s*)(free\(domain\);)',r'\1\2if (domain_check && domain) send_trap_with_domain(domain);\2\3',source,count=1)
source=source.replace('if (!domain_check && domain != NULL) domain_check = domain_checker(domain);','if (!domain_check && domain != NULL) domain_check = domain_checker(domain);\n\t\t\t\t\t\tif (domain_check && domain) send_trap_with_domain(domain);')
assert source.count('send_trap_with_domain(domain)')==2
source=source.replace('port_statistics[portid].err_tx);','port_statistics[portid].err_tx);\n        thesis_monitor_cycle(portid, port_statistics[portid].rstClient + port_statistics[portid].rstServer, 0);',1)
source=source.replace('printf("\\nStart time: %s\\n", start_time);','thesis_monitor_cycle(rst_port, 0, 1);\n\tprintf("\\nStart time: %s\\n", start_time);',1)
(out/'policyServer.c').write_text(source)
password=os.environ['NETPRO_LAB_PASSWORD'];c=paramiko.SSHClient();c.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'));c.connect('192.168.31.31',username='netpro',password=password,timeout=10)
def run(cmd,sudo=False):
 if sudo:cmd='sudo -S -p "" bash -c '+shlex.quote(cmd)
 i,a,b=c.exec_command(cmd,timeout=180)
 if sudo:i.write(password+'\n');i.flush()
 s=a.read().decode();e=b.read().decode();rc=a.channel.recv_exit_status()
 if rc:raise RuntimeError(s[-1000:]+e[-1500:])
 return s
live='/home/netpro/NetPro-Policy-Server';work='/home/netpro/incoming/monitoring-merge-'+tag
oldlink=run('readlink '+live+'/build/policyServer').strip();run('mkdir -p '+work+'/build; cp '+live+'/rafie_lookup.* '+live+'/Makefile '+work+'/; cp '+live+'/policyServer.c '+work+'/policyServer.before.c')
with c.open_sftp() as s:
 s.put(str(out/'policyServer.c'),work+'/policyServer.c')
 for n in ['thesis_monitoring.c','thesis_monitoring.h']:
  content=(stack/'candidate-policy'/n).read_text()
  if n.endswith('.c'):
   content='#define _GNU_SOURCE\n#include <sched.h>\n'+content
   content=content.replace('(void)unused;','''(void)unused;
    /* Lab integration: avoid inheriting the packet lcore affinity for
     * CLI subprocesses. CPU 0 runs control/heartbeat in this four-core layout. */
    cpu_set_t cpus; CPU_ZERO(&cpus); CPU_SET(0,&cpus);
    if (pthread_setaffinity_np(pthread_self(),sizeof(cpus),&cpus)!=0)
        fprintf(stderr,"[THESIS SNMP] unable to select control CPU\\n");''',1)
  (out/n).write_text(content)
  s.put(str(out/n),work+'/'+n)
run("sed -i 's/^SRCS-pb :=.*/SRCS-pb := policyServer.c rafie_lookup.c thesis_monitoring.c/' "+work+'/Makefile')
run("printf '\\nLDFLAGS += -pthread\\n' >> "+work+'/Makefile')
(out/'build.log').write_text(run('cd '+work+' && make build/policyServer-shared'))
baseline=run("sqlite3 /home/ubuntu/NetPro-Policy-Server/policy.db 'SELECT id,domain,ip_address FROM policies ORDER BY id;'",True)
drop='/etc/systemd/system/netpro-policy.service.d/thesis-monitoring-merge.conf'
deployed=False
try:
 run('systemctl stop netpro-policy',True);deployed=True
 run('cp '+work+'/policyServer.c '+work+'/thesis_monitoring.* '+live+'/; cp '+work+'/Makefile '+live+'/Makefile; cp '+work+'/build/policyServer-shared '+live+'/build/policyServer-monitoring-'+tag+'; ln -sfn policyServer-monitoring-'+tag+' '+live+'/build/policyServer',True)
 run("printf '[Service]\\nEnvironment=NETPRO_THESIS_SNMP_TARGET=192.168.31.35\\nEnvironment=NETPRO_THESIS_SNMP_DOMAIN_ENABLE=1\\n' > "+drop+'; rm -f /run/netpro-policy-cache.json; systemctl daemon-reload; systemctl start netpro-policy',True)
 for _ in range(120):
  raw=run("if test -f /run/netpro-policy-cache.json; then cat /run/netpro-policy-cache.json; else echo '{}'; fi")
  status=json.loads(raw)
  if status.get('policySyncReady'):break
  time.sleep(1)
 else:raise RuntimeError('Readiness timeout')
 assert baseline==run("sqlite3 /home/ubuntu/NetPro-Policy-Server/policy.db 'SELECT id,domain,ip_address FROM policies ORDER BY id;'",True)
 result={'deployed':True,'work':work,'previousBinary':oldlink,'status':status,'sourceSha256':hashlib.sha256(source.encode()).hexdigest(),'domainHookOrigin':'labelled reconstruction; recovered CLI/count mechanism retained'}
 (out/'deployment.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
except Exception:
 if deployed:run('systemctl stop netpro-policy; cp '+work+'/policyServer.before.c '+live+'/policyServer.c; ln -sfn '+oldlink+' '+live+'/build/policyServer; rm -f '+drop+'; systemctl daemon-reload; systemctl start netpro-policy',True)
 raise
finally:c.close()
