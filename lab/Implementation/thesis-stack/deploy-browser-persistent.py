"""Guarded promotion of the previously tested browser QUIC candidates.

Usage: install, accept MANIFEST, or rollback MANIFEST.
Both old persistent drop-ins remain intact. A boot-enabled rollback timer
restores the prior build unless acceptance explicitly disarms it.
"""
import datetime
import json
import os
from pathlib import Path
import shlex
import sys

BASE = Path(__file__).resolve().parent
sys.path[:0] = [str(BASE.parents[1] / 'Testing/thesis-replication'), str(BASE.parents[1] / 'Testing/snmp-quic-integration')]
from remote import connect_verified, run_remote_command

SPECS = [
    ('192.168.31.31', 'policy-server-vm', 'netpro-policy',
     '/home/netpro/incoming/chromium-reassembly.aMTJMc/policyServer-browser',
     '132c7650d01400a6726a359c06994963b8636893930d417e394cc86028016f1d',
     'cdc47721b017357569ebfc04f9e69b3f2f15f58bf60b3347aed7a9ae74b63e6f'),
    ('192.168.31.33', 'npb-vm', 'netpro-npb',
     '/home/netpro/incoming/chromium-reassembly-npb.udREex/packetBroker-browser',
     '977736f0989f396a9401c8fe3e487271bf1f978dc778c10b1d88e590b9bae46f',
     '034e97f0818ffa77f80a8cbf61714b911949fe30937a437871af5a2c6707e1bb'),
]
PASSWORD = os.environ['NETPRO_LAB_PASSWORD']
q = shlex.quote
action = sys.argv[1]
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
OUT = BASE / 'evidence' / ('browser-deployment-' + stamp)
OUT.mkdir(parents=True)
clients = {}


def command(host, script, timeout=90):
    if host not in clients:
        clients[host], _ = connect_verified(host, 'netpro', PASSWORD, Path.home()/'.ssh/known_hosts')
    rc, out, err = run_remote_command(clients[host], 'bash -c '+q(script),
                                      sudo_password=PASSWORD, timeout=timeout)
    with (OUT/'operations.jsonl').open('a', encoding='utf8') as f:
        f.write(json.dumps(dict(host=host, script=script, rc=rc, stdout=out, stderr=err))+'\n')
    if rc:
        raise RuntimeError(host+': '+out[-400:]+err[-700:])
    return out.strip()


def install(spec):
    host, hostname, unit, source, sha, old = spec
    root = '/var/lib/netpro-browser-deployment/'+stamp
    binary = '/usr/local/libexec/'+unit+'-browser-quic'
    dropin = '/etc/systemd/system/'+unit+'.service.d/96-browser-quic.conf'
    timer = unit+'-browser-quic-rollback'
    config = '[Service]\nExecStart=\nExecStart='+binary+' -l 0-3 -n 2\n'
    import hashlib
    config_sha = hashlib.sha256(config.encode()).hexdigest()
    db = '/home/ubuntu/NetPro-Policy-Server/policy.db'
    restore = ''
    backup = ''
    if unit == 'netpro-policy':
        restore = f'''if test ! -e {db}; then install -o netpro -g netpro -m 0644 {root}/policy-before.db {db}; fi
test "$(sqlite3 -cmd '.timeout 10000' -readonly {db} 'PRAGMA integrity_check;')" = ok
'''
        backup = f'''sqlite3 -cmd '.timeout 10000' {db} ".backup '{root}/policy-before.db'"
test "$(sqlite3 -readonly {root}/policy-before.db 'PRAGMA integrity_check;')" = ok
'''
    rollback = f'''#!/bin/bash
set -euo pipefail
test "$(hostname -s)" = {hostname}
if test -e {dropin}; then
 test "$(sha256sum {dropin} | cut -d' ' -f1)" = {config_sha}
 systemctl stop {unit}
 {restore}
 rm -- {dropin}
 systemctl daemon-reload
 systemctl start {unit}
fi
systemctl is-active --quiet {unit}
pid=$(systemctl show {unit} -p MainPID --value)
test "$(sha256sum /proc/$pid/exe | cut -d' ' -f1)" = {old}
systemctl disable --now {timer}.timer
echo ORIGINAL_RESTORED
'''
    service = '[Unit]\nDescription=Restore previous NetPro browser candidate baseline\n[Service]\nType=oneshot\nExecStart=/bin/bash '+root+'/rollback.sh\n'
    timer_conf = '[Unit]\nDescription=Automatic rollback until browser deployment is accepted\n[Timer]\nOnActiveSec=20min\nAccuracySec=1s\n[Install]\nWantedBy=timers.target\n'
    command(host, f'''set -euo pipefail
test "$(hostname -s)" = {hostname}
test ! -e {dropin}
test ! -e {binary}
test ! -e /etc/systemd/system/{timer}.timer
pid=$(systemctl show {unit} -p MainPID --value)
test "$(sha256sum /proc/$pid/exe | cut -d' ' -f1)" = {old}
test "$(sha256sum {source} | cut -d' ' -f1)" = {sha}
install -d -o netpro -g netpro -m 0750 {root}
{backup}
''')
    with clients[host].open_sftp() as ftp:
        for name, content in [('candidate.conf',config),('rollback.sh',rollback),('rollback.service',service),('rollback.timer',timer_conf)]:
            with ftp.file(root+'/'+name,'w') as f:
                f.write(content)
    row = dict(host=host,unit=unit,root=root,binary=binary,dropin=dropin,timer=timer,
               sha256=sha,previous_sha256=old,config_sha256=config_sha)
    records.append(row)
    save()
    command(host, f'''set -euo pipefail
install -m 0644 {root}/rollback.service /etc/systemd/system/{timer}.service
install -m 0644 {root}/rollback.timer /etc/systemd/system/{timer}.timer
systemctl daemon-reload
systemctl enable --now {timer}.timer
systemctl is-active --quiet {timer}.timer
trap '/bin/bash {root}/rollback.sh' ERR
install -m 0755 {source} {binary}
install -m 0644 {root}/candidate.conf {dropin}
systemctl daemon-reload
systemctl restart {unit}
systemctl is-active --quiet {unit}
pid=$(systemctl show {unit} -p MainPID --value)
test "$(sha256sum /proc/$pid/exe | cut -d' ' -f1)" = {sha}
systemctl is-enabled {unit}
''')
    print(unit+' persistent candidate active; boot-enabled rollback timer armed',flush=True)


records = []
manifest = OUT/'deployment.json'
state = 'installing'
def save():
    manifest.write_text(json.dumps(dict(state=state,created_utc=stamp,hosts=records),indent=2),encoding='utf8')

try:
    if action == 'install':
        try:
            for spec in SPECS:
                install(spec)
            state = 'pending-acceptance'
            save()
        except Exception:
            state = 'failed'
            save()
            for row in reversed(records):
                try: command(row['host'], '/bin/bash '+q(row['root']+'/rollback.sh'))
                except Exception as error: print('ROLLBACK NEEDS ATTENTION',str(error),flush=True)
            raise
    elif action in ('accept','rollback'):
        original_manifest = Path(sys.argv[2])
        document = json.loads(original_manifest.read_text())
        records = document['hosts']
        if action == 'accept':
            # Verify both candidates before disarming either rollback timer.
            for row in records:
                command(row['host'], f'''set -euo pipefail
systemctl is-active --quiet {row['unit']}
pid=$(systemctl show {row['unit']} -p MainPID --value)
test "$(sha256sum /proc/$pid/exe | cut -d' ' -f1)" = {row['sha256']}
test "$(sha256sum {row['dropin']} | cut -d' ' -f1)" = {row['config_sha256']}
''')
            for row in records:
                command(row['host'],'systemctl disable --now '+q(row['timer']+'.timer'))
        else:
            for row in reversed(records):
                command(row['host'],'/bin/bash '+q(row['root']+'/rollback.sh'))
        document['state'] = 'accepted' if action == 'accept' else 'rolled-back'
        original_manifest.write_text(json.dumps(document,indent=2),encoding='utf8')
    else:
        raise ValueError('Expected install, accept MANIFEST or rollback MANIFEST')
finally:
    for client in clients.values():client.close()
    print('EVIDENCE',OUT,flush=True)
