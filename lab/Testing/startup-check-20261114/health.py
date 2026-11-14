import concurrent.futures,json,time,datetime,os
from pathlib import Path
import paramiko
OUT=Path(__file__).resolve().parent
commands={
31:"hostname; uptime -p; systemctl is-active netpro-policy; cat /run/netpro-policy-cache.json; systemctl show netpro-policy -p ExecStart",
33:"hostname; uptime -p; systemctl is-active netpro-npb; systemctl show netpro-npb -p ExecStart",
35:"hostname; uptime -p; systemctl is-active netpro-backend postgresql netpro-kafka nginx zabbix-server netpro-snmptrapd; systemctl --failed --no-legend",
37:"hostname; uptime -p; systemctl is-active netpro-quic-lab; systemctl --failed --no-legend; tc qdisc show dev ens37; ip -4 -br addr; ss -lntu | grep -E ':443 |:8443 '",
38:"hostname; uptime -p; systemctl --failed --no-legend; ip -br link; bridge link; tc -s filter show dev ens34 ingress; tc -s filter show dev ens35 ingress",
39:"hostname; uptime -p; ip -4 -br addr; ip route; /home/netpro/netpro-thesis/http3/prefix/bin/curl --version | head -2"
}
def check(n):
 c=paramiko.SSHClient();c.load_host_keys(str(Path.home()/'.ssh/known_hosts'))
 try:
  c.connect('192.168.31.'+str(n),username='netpro',password=os.environ['NETPRO_LAB_PASSWORD'],timeout=8,banner_timeout=10,auth_timeout=10)
  i,o,e=c.exec_command(commands[n],timeout=45);out=o.read().decode();err=e.read().decode();rc=o.channel.recv_exit_status()
  return dict(ip=n,rc=rc,stdout=out,stderr=err)
 except Exception as e:return dict(ip=n,error=str(e))
 finally:c.close()
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(check,commands))
(OUT/'health.json').write_text(json.dumps(results,indent=2),encoding='utf8')
for r in results:print(json.dumps(r))

