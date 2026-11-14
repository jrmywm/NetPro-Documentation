"""Build the untouched archived QUIC crafter in a private directory and test it."""
from pathlib import Path
import sys,json,hashlib,datetime,shlex
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
WORK=Path('C:/Users/jim/Documents/Codex/2026-09-11/referenced-chatgpt-conversation-this-is-an-2/work')
SOURCE=WORK/'thesis-review-2021/repository-audit/sources/NetPro-Policy-Server/quic-dev/quic-processor'
fixed='--fixed' in sys.argv
OUT=BASE/'evidence'/(('quic-fixed-gate-' if fixed else 'quic-gate-')+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
c=None
try:
 c,_=connect_verified('192.168.31.31','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
 rc,root,err=run_remote_command(c,'mktemp -d /home/netpro/incoming/quic-close-gate.XXXXXX')
 if rc:raise RuntimeError(err)
 root=root.strip();files=[SOURCE/x for x in ('quicFunctions.c','quicFunctions.h')]+[(BASE/'quic-fixed-candidate/packet-processor.c') if fixed else SOURCE/'packet-processor.c',BASE/'quic_close_gate.c',WORK/'snmp-quic-integration/libssl-dev_1.1.1f-1ubuntu2.24_amd64.deb']
 with c.open_sftp() as s:
  for p in files:s.put(str(p),root+'/'+p.name)
 manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
 (OUT/'sources.json').write_text(json.dumps({'directory':root,'sha256':manifest},indent=2),encoding='utf-8')
 cmd=r'''set -eu
cd ROOT
deb=libssl-dev_1.1.1f-1ubuntu2.24_amd64.deb
v=1.1.1f-1ubuntu2.24
test "$(dpkg-query -W -f='${Version}' libssl1.1)" = "$v"
meta="$(apt-cache show "libssl-dev=$v")"
test "$(sha256sum "$deb" | cut -d' ' -f1)" = "$(printf '%s\n' "$meta" | awk '$1=="SHA256:" {print $2;exit}')"
test "$(dpkg-deb -f "$deb" Architecture)" = amd64
dpkg-deb -x "$deb" headers
mkdir link
ln -s /usr/lib/x86_64-linux-gnu/libcrypto.so.1.1 link/libcrypto.so
flags='-Iheaders/usr/include -Iheaders/usr/include/x86_64-linux-gnu -I.'
for mode in normal sanitized; do
 extra=''
 if test "$mode" = sanitized; then extra='-fsanitize=address,undefined -fno-omit-frame-pointer'; fi
 gcc -g -O1 $extra $flags -Dmain=archived_main -c packet-processor.c -o "$mode-packet.o" > "$mode-build.log" 2>&1
 gcc -g -O1 $extra $flags quicFunctions.c quic_close_gate.c "$mode-packet.o" -Llink -lcrypto -pthread -o "$mode-test" >> "$mode-build.log" 2>&1
 set +e
 ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 timeout 10s "./$mode-test" > "$mode-test.log" 2>&1
 code=$?
 set -e
 printf '%s_exit=%s\n' "$mode" "$code"
done
sha256sum *-test
systemctl is-active netpro-policy
'''.replace('ROOT',shlex.quote(root))
 (OUT/'commands.sh').write_text(cmd,encoding='utf-8')
 rc,out,err=run_remote_command(c,cmd,timeout=60)
 (OUT/'execution.json').write_text(json.dumps({'exit':rc,'stdout':out,'stderr':err},indent=2),encoding='utf-8')
 with c.open_sftp() as s:
  for name in ('normal-build.log','sanitized-build.log','normal-test.log','sanitized-test.log'):
   try:s.get(root+'/'+name,str(OUT/name))
   except OSError:pass
 print('Gate execution:',rc,out,err[:500])
 for p in OUT.glob('*-test.log'):
  print(p.name,p.read_text(encoding='utf-8')[:1600].encode('ascii','replace').decode())
 print('EVIDENCE:',OUT)
finally:
 if c:c.close()
