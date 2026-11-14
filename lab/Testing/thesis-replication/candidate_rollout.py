"""Temporary systemd candidate override, exact binary guards, timer rollback.
Policy old-binary shutdown can unlink SQLite: retain online backup, restore
only if absent, and leave existing valid databases intact during rollback.
"""
import json,shlex,hashlib
from pathlib import Path
from remote import run_remote_command

class CandidateRollout:
 def __init__(self,client,host,unit,candidate,candidate_sha,original_sha,evidence,environment=None):
  self.client=client;self.host=host;self.unit=unit;self.candidate=candidate;self.candidate_sha=candidate_sha;self.original_sha=original_sha;self.evidence=Path(evidence);self.environment=environment or {};self.root=None;self.started=False
 def command(self,cmd,timeout=30):
  rc,out,err=run_remote_command(self.client,cmd,sudo_password=__import__('os').environ['NETPRO_LAB_PASSWORD'],timeout=timeout)
  with (self.evidence/(self.unit+'-rollout.jsonl')).open('a',encoding='utf-8') as f:f.write(json.dumps({'command':cmd,'exit':rc,'stdout':out,'stderr':err})+'\n')
  if rc:raise RuntimeError(self.unit+': '+out[-500:]+err[-700:])
  return out.strip()
 def start(self):
  self.root=self.command('mktemp -d /home/netpro/incoming/thesis-rollout.XXXXXX');q=shlex.quote
  self.command('chown netpro:netpro '+q(self.root))
  marker=Path(self.root).name;timer='netpro-'+marker;dropin='/run/systemd/system/'+self.unit+'.service.d/95-'+marker+'.conf'
  self.timer=timer;self.dropin=dropin
  db='/home/ubuntu/NetPro-Policy-Server/policy.db'
  policy=self.unit=='netpro-policy'
  stopcmd='systemctl stop '+self.unit
  restore=''
  if policy:
   restore=f'''if test ! -e {db}; then install -o netpro -g netpro -m 0644 {q(self.root)}/policy-before.db {db}; fi
test "$(sqlite3 -cmd '.timeout 10000' -readonly {db} 'PRAGMA integrity_check;')" = ok
'''
  rollback=f'''#!/bin/bash
set -euo pipefail
test "$(hostname -s)" = {q(self.host)}
root={q(self.root)}
test -d "$root"
if test -f {q(dropin)}; then
 test "$(sha256sum {q(dropin)} | cut -d' ' -f1)" = "$(cat "$root/dropin.sha256")"
 {stopcmd}
 {restore}
 rm -- {q(dropin)}
 systemctl daemon-reload
 systemctl start {self.unit}
fi
{restore}
systemctl start {self.unit}
systemctl is-active --quiet {self.unit}
pid=$(systemctl show {self.unit} -p MainPID --value)
test "$(sha256sum /proc/$pid/exe | cut -d' ' -f1)" = {q(self.original_sha)}
printf 'ORIGINAL_RESTORED %s\\n' {self.unit}
'''
  env=''.join('Environment='+key+'='+str(value)+'\n' for key,value in self.environment.items())
  config='[Service]\nExecStart=\nExecStart='+self.candidate+' -l 0-3 -n 2\n'+env
  with self.client.open_sftp() as s:
   for name,content in [('rollback.sh',rollback),('pilot.conf',config)]:
    with s.file(self.root+'/'+name,'w') as f:f.write(content)
  # Arm the rollback before stopping anything. The source/binary checks must
  # pass before this script writes the runtime override.
  backup=''
  if policy:
   backup=f'''test "$(sqlite3 -cmd '.timeout 10000' -readonly {db} 'PRAGMA integrity_check;')" = ok
sqlite3 -cmd '.timeout 10000' {db} ".backup '{self.root}/policy-before.db'"
test "$(sqlite3 -cmd '.timeout 10000' -readonly {q(self.root)}/policy-before.db 'PRAGMA integrity_check;')" = ok
sqlite3 -cmd '.timeout 10000' -readonly {db} 'SELECT id FROM policies ORDER BY id;' >{q(self.root)}/ids-before.txt
'''
  script=f'''set -euo pipefail
test "$(hostname -s)" = {q(self.host)}
test ! -e {q(dropin)}
test "$(systemctl show -p LoadState --value {timer}.timer)" = not-found
systemctl is-active --quiet {self.unit}
pid=$(systemctl show {self.unit} -p MainPID --value)
test "$(sha256sum /proc/$pid/exe | cut -d' ' -f1)" = {q(self.original_sha)}
test "$(sha256sum {q(self.candidate)} | cut -d' ' -f1)" = {q(self.candidate_sha)}
{backup}
sha256sum {q(self.root)}/pilot.conf | cut -d' ' -f1 >{q(self.root)}/dropin.sha256
systemd-run --quiet --collect --unit={timer} --on-active=1800s /bin/bash {q(self.root)}/rollback.sh
systemctl is-active --quiet {timer}.timer
trap '/bin/bash {self.root}/rollback.sh' ERR
systemctl stop {self.unit}
{restore}
install -d -m 0755 $(dirname {q(dropin)})
install -m 0644 {q(self.root)}/pilot.conf {q(dropin)}
systemctl daemon-reload
systemctl start {self.unit}
sleep 3
systemctl is-active --quiet {self.unit}
pid=$(systemctl show {self.unit} -p MainPID --value)
test "$(sha256sum /proc/$pid/exe | cut -d' ' -f1)" = {q(self.candidate_sha)}
'''
  if policy:
   if self.environment.get('NETPRO_REPLAY_READINESS')=='1':
    script+='''for attempt in $(seq 1 120); do
if python3 -c 'import json; d=json.load(open("/run/netpro-policy-cache.json")); raise SystemExit(not d.get("policySyncReady"))' 2>/dev/null; then break; fi
sleep 1
done
python3 -c 'import json; assert json.load(open("/run/netpro-policy-cache.json"))["policySyncReady"]'
'''
   script+=f"sqlite3 -cmd '.timeout 10000' -readonly {db} 'SELECT id FROM policies ORDER BY id;' >{q(self.root)}/ids-after.txt\ncmp {q(self.root)}/ids-before.txt {q(self.root)}/ids-after.txt\n"
  self.started=True
  self.command('/bin/bash -c '+q(script),timeout=180)
  print(self.unit,'candidate active; automatic rollback armed',flush=True)
 def stop(self):
  if not self.started:return
  self.command('/bin/bash '+shlex.quote(self.root+'/rollback.sh'),timeout=65)
  self.command('systemctl stop '+self.timer+'.timer',timeout=15)
  self.started=False
  print(self.unit,'original restored',flush=True)
