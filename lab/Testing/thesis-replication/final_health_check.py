"""Read-only post-experiment original binary, policy and owned-port checks."""
from pathlib import Path
import sys,json,datetime
BASE=Path(__file__).resolve().parent;sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from active_baseline import ActiveBaseline
from remote import connect_verified
OUT=BASE/'evidence'/('postflight-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
w=ActiveBaseline('netpro',OUT,Path('C:/Users/jim/.ssh/known_hosts'));failed=False
try:
 w.connect_all();w.baseline();w.clients['192.168.31.33'],_=connect_verified('192.168.31.33','netpro','netpro',w.known_hosts)
 for host,unit,sha in [('192.168.31.31','netpro-policy','5892e752bb08395b2b3b1170fc9e45af21ac9251b7dfc9860a7b28dde0865614'),('192.168.31.33','netpro-npb','607a680272458c2dad46e7caf16751990632415c940401f4fbfac68e88196430')]:
  command='set -eu\nsystemctl is-active --quiet '+unit+'\npid=$(systemctl show '+unit+' -p MainPID --value)\ntest "$(sha256sum /proc/$pid/exe | cut -d\' \' -f1)" = '+sha+'\nreadlink /proc/$pid/exe'
  _,out,_=w.command(host,'original_'+unit,command,sudo=True);print(unit,'ACTIVE; exact original hash verified;',out.strip())
 w.command('192.168.31.37','gateway_restored',"test \"$(cat /sys/class/net/ens38/operstate)\" = down; test -z \"$(tc filter show dev ens38 ingress)\"; test -z \"$(ss -H -lun 'sport = :18443')\"",sudo=True)
 w.command('192.168.31.31','private_agent_port_released',"test -z \"$(ss -H -lun 'sport = :11625')\"")
 w.command('192.168.31.35','private_receiver_port_released',"test -z \"$(ss -H -lun 'sport = :11623')\"")
 print('PASS: four baseline SQLite policies and one Backend policy preserved; owned endpoint/agent/receiver ports released; return interface restored.')
except Exception as e:failed=True;print('FAIL:',e)
finally:
 for c in w.clients.values():c.close()
 (OUT/'result.json').write_text(json.dumps({'passed':not failed},indent=2),encoding='utf-8')
 print('POSTFLIGHT:',OUT)
raise SystemExit(1 if failed else 0)
