"""Read-only scheduling/resource evidence following a late RST."""
from pathlib import Path
import sys,json,datetime
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
OUT=BASE/'evidence'/('scheduling-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
for ip,unit in [('192.168.31.31','netpro-policy'),('192.168.31.33','netpro-npb'),('192.168.31.34','netpro-packet-generator'),('192.168.31.38','netpro-virtual-tap-mirror')]:
 c,_=connect_verified(ip,'netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'),trusted_host_alias='192.168.31.134' if ip.endswith('.34') else None)
 try:
  cmd=f"uptime; free -m; cat /proc/pressure/cpu /proc/pressure/memory; pid=$(systemctl show {unit} -p MainPID --value); if test \"${{pid:-0}}\" -gt 0; then ps -T -p \"$pid\" -o pid,tid,psr,pcpu,stat,comm; fi; ps -eo pid,pcpu,pmem,comm --sort=-pcpu | head -n 8; journalctl -u {unit} --since '5 minutes ago' --no-pager | grep -Ei 'error|fatal|failed|drop' | tail -n 4"
  rc,out,err=run_remote_command(c,cmd,sudo_password=__import__('os').environ['NETPRO_LAB_PASSWORD'],timeout=15)
  (OUT/(unit+'.json')).write_text(json.dumps({'command':cmd,'exit':rc,'stdout':out,'stderr':err},indent=2),encoding='utf-8');print(unit,out,err[:150])
 finally:c.close()
print('EVIDENCE:',OUT)
