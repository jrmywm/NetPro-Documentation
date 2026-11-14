"""Run an explicitly selected command, retain its full output, and show a compact tail."""
import argparse, datetime, json, sys
from pathlib import Path
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parents[1] / 'Testing/snmp-quic-integration'))
from remote import connect_verified, run_remote_command
p = argparse.ArgumentParser()
p.add_argument('ip'); p.add_argument('label'); p.add_argument('--command', required=True)
p.add_argument('--sudo', action='store_true'); p.add_argument('--timeout', type=int, default=60)
p.add_argument('--upload', type=Path); p.add_argument('--destination')
a = p.parse_args()
out = BASE / 'evidence' / (a.label + '-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
out.mkdir(parents=True)
c, host = connect_verified(a.ip, 'netpro', 'netpro', Path('C:/Users/jim/.ssh/known_hosts'))
try:
 if a.upload:
  if not a.destination: raise ValueError('upload requires destination')
  with c.open_sftp() as s: s.put(str(a.upload), a.destination)
 rc, stdout, stderr = run_remote_command(c, a.command, sudo_password=__import__('os').environ['NETPRO_LAB_PASSWORD'] if a.sudo else None, timeout=a.timeout)
 (out / 'result.json').write_text(json.dumps(dict(host=host, exit=rc, stdout=stdout, stderr=stderr), indent=2), encoding='utf-8')
 print('HOST', host, 'EXIT', rc, 'EVIDENCE', out)
 print(stdout[-1800:]); print(stderr[-1000:])
finally: c.close()
sys.exit(rc)
