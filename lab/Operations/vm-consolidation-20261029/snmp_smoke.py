"""Single labelled SNMP trap delivery check; not a policy-blocking test."""
from pathlib import Path
import datetime,json,os,sys,time
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified,run_remote_command,redact
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');marker='netpro-consolidation-smoke-'+stamp
out=Path(__file__).resolve().parent/'evidence'/('snmp-smoke-'+stamp);out.mkdir(parents=True)
cred=os.environ.get('NETPRO_LAB_PASSWORD','netpro');clients=[]
try:
 ps,_=connect_verified('192.168.31.31','netpro',cred,Path(r'C:\Users\jim\.ssh\known_hosts'));clients.append(ps)
 back,_=connect_verified('192.168.31.35','netpro',cred,Path(r'C:\Users\jim\.ssh\known_hosts'));clients.append(back)
 cmd=f"snmptrap -v2c -c public udp:192.168.31.35:162 '' .1.3.6.1.4.1.53864.1.0 .1.3.6.1.4.1.53864.1.1 s {marker}"
 rc,o,e=run_remote_command(ps,cmd,timeout=15)
 if rc:raise RuntimeError('Trap sender failed: '+redact(e))
 time.sleep(2)
 cmd=f'''journalctl -u netpro-snmptrapd -n 80 --no-pager -o cat
grep -F '{marker}' /var/log/snmptraps/snmptraps.log /var/log/snmptrap/snmptrap.log /var/log/zabbix/snmptraps.log /var/lib/zabbix/snmptraps/snmptraps.log 2>/dev/null || true
'''
 rc,o,e=run_remote_command(back,cmd,sudo_password=cred,timeout=20)
 result={'marker':marker,'sender_exit':0,'receiver_marker_found':marker in o,'receiver_output':redact(o),'stderr':redact(e)}
 (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print('SNMP_RECEIVED',result['receiver_marker_found'],'EVIDENCE',out)
 sys.exit(0 if result['receiver_marker_found'] else 1)
finally:
 for c in clients:c.close()
