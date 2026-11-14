"""Gracefully reboot six NetPro VMs and verify changed Linux boot IDs.

The Management VM returns before dependent VMs restart. No power reset is used.
"""
import concurrent.futures
import datetime
import json
import logging
logging.getLogger("paramiko.transport").setLevel(logging.CRITICAL)
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'Testing/snmp-quic-integration'))
from remote import connect_verified, run_remote_command

PASSWORD = os.environ['NETPRO_LAB_PASSWORD']
HOSTS = ['192.168.31.'+str(n) for n in (35,31,33,37,38,39)]
OUT = Path(__file__).parent/('reboot-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')

def reboot(host):
    client, _ = connect_verified(host,'netpro',PASSWORD,Path.home()/'.ssh/known_hosts',timeout=8)
    try:
        rc, old, err = run_remote_command(client,'cat /proc/sys/kernel/random/boot_id')
        if rc:raise RuntimeError(err)
        try:
            rc, out, err = run_remote_command(client,'systemctl reboot',sudo_password=PASSWORD,timeout=8)
            if rc:raise RuntimeError(out+err)
        except (EOFError, OSError):
            pass  # The reboot may close its SSH channel before returning status.
    finally:
        client.close()
    print(host+' graceful reboot requested',flush=True)
    deadline = time.monotonic()+240
    last = ''
    while time.monotonic()<deadline:
        time.sleep(4)
        client = None
        try:
            client, _ = connect_verified(host,'netpro',PASSWORD,Path.home()/'.ssh/known_hosts',timeout=5)
            rc, current, err = run_remote_command(client,'cat /proc/sys/kernel/random/boot_id',timeout=5)
            if rc==0 and current.strip()!=old.strip():
                print(host+' returned with a new boot ID',flush=True)
                return dict(host=host,before=old.strip(),after=current.strip(),passed=True)
        except Exception as error:
            last=str(error)
        finally:
            if client:client.close()
    raise RuntimeError(host+' did not return with a new boot ID: '+last)

if sys.argv[1:] != ['--execute']:
    raise SystemExit('Use --execute to reboot the six VMs')
results=[]
try:
    results.append(reboot(HOSTS[0]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for result in pool.map(reboot,HOSTS[1:]):results.append(result)
finally:
    OUT.write_text(json.dumps(results,indent=2),encoding='utf8')
    print('EVIDENCE',OUT,flush=True)
