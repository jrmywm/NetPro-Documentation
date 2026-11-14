"""Read-only guest inventory for the management consolidation."""
from pathlib import Path
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified, run_remote_command, redact

p = argparse.ArgumentParser()
p.add_argument('host')
a = p.parse_args()
credential = os.environ.get('NETPRO_LAB_PASSWORD', 'netpro')
out = Path(__file__).resolve().parent / 'evidence' / (
    datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + a.host
)
out.mkdir(parents=True, exist_ok=False)
command = r'''hostname
free -m
df -h /
ip -4 -br addr
systemctl list-units --type=service --all --no-pager --plain | grep -Ei 'netpro|kafka|zookeeper|postgres|zabbix|snmp|nginx|apache|node' || true
ss -H -ltnu
ps -eo comm,rss --sort=-rss | head -n 12
find /etc/systemd/system -maxdepth 2 -type f \( -iname '*netpro*' -o -iname '*kafka*' -o -iname '*zookeeper*' \) -print
find /home/netpro -maxdepth 2 -type d \( -iname '*frontend*' -o -iname '*backend*' -o -iname '*kafka*' \) -print
command -v node || true
command -v npm || true
command -v java || true
'''
c = None
try:
    c, hostname = connect_verified(a.host, 'netpro', credential, Path(r'C:\Users\jim\.ssh\known_hosts'))
    rc, stdout, stderr = run_remote_command(c, command, timeout=40)
    result = {'host': a.host, 'hostname': hostname, 'exit': rc,
              'stdout': redact(stdout), 'stderr': redact(stderr)}
    (out / 'inventory.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('EVIDENCE', out)
    print(result['stdout'])
    print(result['stderr'])
except Exception as exc:
    (out / 'error.json').write_text(json.dumps({'error': redact(str(exc))}), encoding='utf-8')
    print(type(exc).__name__, redact(str(exc)))
    sys.exit(1)
finally:
    if c:
        c.close()
