"""Read-only integration prerequisites; never changes lab services."""
from pathlib import Path
import sys, json, datetime
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command,TRUSTED_HOST_ALIASES
outdir=BASE/'evidence'/('live-path-inspection-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
outdir.mkdir(parents=True)
checks={
 '192.168.31.31': "systemctl cat netpro-policy; readlink /home/netpro/NetPro-Policy-Server/build/policyServer; pkg-config --modversion libdpdk libcurl jansson sqlite3 rdkafka; ip -br link; ls /sys/bus/pci/drivers/vfio-pci/ 2>/dev/null; ss -lunp",
 '192.168.31.33': "systemctl cat netpro-npb; readlink /home/netpro/NetPro-Network-Packet-Broker/build/packetBroker; sha256sum /home/netpro/NetPro-Network-Packet-Broker/packetBroker.c; ip -br link; ss -lunp",
 '192.168.31.37': "ip route; ip -br addr; command -v caddy || true; command -v openssl; openssl version; python3 -c 'import importlib.util; print(\"aioquic=\",bool(importlib.util.find_spec(\"aioquic\")))'; tc filter show dev ens38 ingress; ss -lntup",
 '192.168.31.39': "ip route; python3 -c 'import importlib.util; print(\"aioquic=\",bool(importlib.util.find_spec(\"aioquic\")))'; curl --version; ss -lntup",
 '192.168.31.34': "ip -br addr; ls -d /opt/trex* /home/netpro/trex* /home/netpro/TRex* 2>/dev/null; python3 -c 'import importlib.util; print(\"scapy=\",bool(importlib.util.find_spec(\"scapy\")))'",
 '192.168.31.32': "systemctl list-units --type=service --all --no-pager | grep -Ei 'kafka|zoo'; ss -lnt | grep -E '9092|2181'"
}
for ip,command in checks.items():
 c=None
 try:
  c,name=connect_verified(ip,'netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'),trusted_host_alias=TRUSTED_HOST_ALIASES.get(ip))
  rc,out,err=run_remote_command(c,command,sudo_password=__import__('os').environ['NETPRO_LAB_PASSWORD'],timeout=20)
  result={'host':name,'command':command,'exit':rc,'stdout':out,'stderr':err}
  (outdir/(name+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
  print(name,rc,out,err[:250])
 except Exception as e: print(ip,type(e).__name__,str(e))
 finally:
  if c:c.close()
print('EVIDENCE:',outdir)
