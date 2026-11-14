from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'snmp-quic-integration'))
from active_baseline import ActiveBaseline,GATEWAY_HOST
w=ActiveBaseline('netpro',Path(__file__).parent/'diagnostics',Path('C:/Users/jim/.ssh/known_hosts'))
try:
    w.connect_all();w.baseline()
    try:w.start_gateway_server()
    except Exception as e:print(e)
    r,o,e=w.command(GATEWAY_HOST,'listener-diagnostic','ss -H -ltn; systemctl status netpro-tap-live-http.service netpro-tap-live-tls.service --no-pager -n 4; journalctl -u netpro-tap-live-http.service --since "3 minutes ago" --no-pager -n 10; true',sudo=True,timeout=15)
    print(o+e)
finally:w.cleanup();w.save()
