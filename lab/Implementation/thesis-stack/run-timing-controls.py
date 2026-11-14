import paramiko,os,json
from pathlib import Path
b=Path(r'C:\Users\jim\Documents\NetPro\Implementation\thesis-stack');d=sorted((b/'evidence').glob('timing-sweep-*'))[-1]
def conn(s):
 c=paramiko.SSHClient();c.load_host_keys(str(Path.home()/'.ssh/known_hosts'));c.connect('192.168.31.'+s,username='netpro',password=os.environ['NETPRO_LAB_PASSWORD'],timeout=10);return c
g=conn('37');c=conn('39')
def root(cmd):
 i,o,e=g.exec_command('sudo -S -p "" sh -c '+__import__('shlex').quote(cmd));i.write(os.environ['NETPRO_LAB_PASSWORD']+'\n');i.flush();a=o.read().decode();err=e.read().decode();assert o.channel.recv_exit_status()==0,err;return a
restore='tc qdisc del dev ens37 root 2>/dev/null || true; tc qdisc add dev ens37 root fq_codel limit 10240p flows 1024 quantum 1514 target 5ms interval 100ms memory_limit 32Mb ecn'
rows=[]
try:
 assert root('tc qdisc show dev ens37').startswith('qdisc fq_codel ')
 root('systemd-run --quiet --collect --unit=netpro-timing-control-rollback --on-active=120s /bin/sh -c '+__import__('shlex').quote(restore))
 for delay in [0,2,5,10]:
  root('tc qdisc del dev ens37 root; tc qdisc add dev ens37 root handle 3900: prio bands 3; tc qdisc add dev ens37 parent 3900:3 handle 3901: netem delay '+str(delay)+'ms; tc filter add dev ens37 parent 3900: protocol ip pref 2 flower ip_proto udp src_ip 192.168.80.28 dst_ip 192.168.80.29 src_port 443 classid 3900:3')
  for n in range(3):
   _,o,e=c.exec_command("/home/netpro/netpro-thesis/http3/prefix/bin/curl --http3-only --noproxy '*' --interface 192.168.80.29 --resolve mysite.local:443:192.168.80.28 -k --max-time 5 -sS -o /dev/null -w 'HTTP %{http_code} VERSION %{http_version}' https://mysite.local/")
   text=o.read().decode();rc=o.channel.recv_exit_status();rows.append({'delay_ms':delay,'trial':n+1,'rc':rc,'result':text})
 print(json.dumps(rows));(d/'no-injection-controls.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
finally:
 root(restore);root('systemctl stop netpro-timing-control-rollback.timer');g.close();c.close()
