"""Install thesis tool dependencies without modifying NetPro services or sources."""
from pathlib import Path
import sys, json, datetime, concurrent.futures
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parents[1] / 'Testing/snmp-quic-integration'))
from remote import connect_verified, run_remote_command
OUT = BASE / 'evidence' / ('dependencies-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
OUT.mkdir(parents=True)
PACKAGES = {
 '192.168.31.31': 'snmp snmpd',
 '192.168.31.35': 'snmp snmptrapd',
 '192.168.31.37': 'caddy',
 '192.168.31.39': 'build-essential pkg-config autoconf automake libtool git ca-certificates libgnutls28-dev libnghttp2-dev libidn2-dev zlib1g-dev',
}
def install(ip):
 c = None
 try:
  c, host = connect_verified(ip, 'netpro', 'netpro', Path('C:/Users/jim/.ssh/known_hosts'))
  command = 'sudo -S -p "" env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ' + PACKAGES[ip]
  rc, out, err = run_remote_command(c, command, sudo_password=__import__('os').environ['NETPRO_LAB_PASSWORD'], timeout=600)
  result = dict(ip=ip, host=host, packages=PACKAGES[ip], exit=rc, stdout=out, stderr=err)
 except Exception as exc:
  result = dict(ip=ip, error=str(exc))
 finally:
  if c: c.close()
 (OUT / (ip + '.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
 print(ip, 'PASS' if result.get('exit') == 0 else 'FAIL', result.get('error', ''), flush=True)
 return result
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 results = list(pool.map(install, PACKAGES))
print('EVIDENCE:', OUT, flush=True)
sys.exit(0 if all(r.get('exit') == 0 for r in results) else 1)
