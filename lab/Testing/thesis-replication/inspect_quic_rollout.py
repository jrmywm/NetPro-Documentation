from pathlib import Path
import sys,json
BASE=Path(__file__).resolve().parent;sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
c,a=connect_verified('192.168.31.33','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
try:
 command='''hostname -s
systemctl is-active netpro-npb
pid=$(systemctl show netpro-npb -p MainPID --value)
sha256sum /proc/$pid/exe
readlink /proc/$pid/exe
sha256sum /home/netpro/NetPro-Network-Packet-Broker/build/packetBroker
systemctl show netpro-npb -p MainPID -p ActiveState -p SubState
find /run/systemd/system/netpro-npb.service.d -maxdepth 1 -type f -print 2>/dev/null || true
'''
 rc,o,e=run_remote_command(c,command,sudo_password=__import__('os').environ['NETPRO_LAB_PASSWORD']);print(a,rc,o,e)
 run=sorted((BASE/'evidence').glob('quic-live-http3-*'))[-1]
 (run/'npb-diagnosis.json').write_text(json.dumps({'identity':a,'exit':rc,'stdout':o,'stderr':e},indent=2),encoding='utf-8')
finally:c.close()
