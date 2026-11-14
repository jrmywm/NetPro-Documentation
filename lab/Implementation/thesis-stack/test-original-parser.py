"""Isolated test of recovered getDomain against actual curl/Caddy traffic."""
from pathlib import Path
import sys,json,datetime,struct,shlex,hashlib
BASE=Path(__file__).resolve().parent
TEST=BASE.parents[1]/'Testing'
sys.path.insert(0,str(TEST/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
OUT=BASE/'evidence'/('original-parser-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));OUT.mkdir(parents=True)
client=None; ps=None
def command(c, label, cmd, sudo=False, timeout=60):
    rc,o,e=run_remote_command(c,cmd,sudo_password=__import__('os').environ['NETPRO_LAB_PASSWORD'] if sudo else None,timeout=timeout)
    (OUT/(label+'.json')).write_text(json.dumps(dict(exit=rc,stdout=o,stderr=e),indent=2),encoding='utf-8')
    print(label,'EXIT',rc,o[-1400:],e[-700:],flush=True)
    if rc:raise RuntimeError(label+' failed')
    return o
try:
    client,_=connect_verified('192.168.31.39','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
    remote='/tmp/netpro-original-parser-'+OUT.name+'.pcap'
    command(client,'curl-capture',f'''sudo -S -p "" timeout 8 tcpdump -ni ens37 -s0 -w {shlex.quote(remote)} 'udp and dst host 192.168.80.28 and dst port 443' &
p=$!
sleep 1
/home/netpro/netpro-thesis/http3/prefix/bin/curl --http3-only --noproxy '*' --interface 192.168.80.29 --resolve mysite.local:443:192.168.80.28 -k --max-time 5 -sS -o /dev/null -w 'HTTP %{{http_code}} VERSION %{{http_version}}\n' https://mysite.local/
wait "$p" || true
''',True,20)
    with client.open_sftp() as s:s.get(remote,str(OUT/'curl-caddy.pcap'))
    raw=(OUT/'curl-caddy.pcap').read_bytes(); endian='<' if raw[:4]==b'\xd4\xc3\xb2\xa1' else '>';pos=24;payload=None
    while pos+16<=len(raw):
        _,_,n,_=struct.unpack_from(endian+'IIII',raw,pos);pos+=16;packet=raw[pos:pos+n];pos+=n
        if len(packet)<42 or packet[12:14]!=b'\x08\x00':continue
        ihl=(packet[14]&15)*4;udp=14+ihl
        if packet[23]!=17:continue
        length=int.from_bytes(packet[udp+4:udp+6],'big');q=packet[udp+8:udp+length]
        if q and (q[0]&0xf0)==0xc0 and q[1:5]==b'\x00\x00\x00\x01':payload=q;break
    if not payload:raise RuntimeError('No captured QUIC v1 Initial')
    (OUT/'curl-initial.bin').write_bytes(payload)
    print('ACTUAL_CURL_INITIAL_BYTES',len(payload),flush=True)
    ps,_=connect_verified('192.168.31.31','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
    root=command(ps,'stage','mktemp -d /home/netpro/incoming/original-quic-gate.XXXXXX').strip()
    source=BASE/'original/quic-dev/quic-processor'
    files=[source/'packet-processor.c',source/'quicFunctions.c',source/'quicFunctions.h',BASE/'original-parser-gate.c',OUT/'curl-initial.bin']
    with ps.open_sftp() as s:
        for p in files:s.put(str(p),root+'/'+p.name)
    fixed=json.loads((sorted((TEST/'thesis-replication/evidence').glob('quic-fixed-gate-*'))[-1]/'sources.json').read_text())['directory']
    flags=f'-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -pthread -I{fixed}/headers/usr/include -I{fixed}/headers/usr/include/x86_64-linux-gnu -L{fixed}/link'
    command(ps,'build',f'cd {root} && gcc {flags} -Dmain=archived_main -c packet-processor.c -o processor.o && gcc {flags} original-parser-gate.c quicFunctions.c processor.o -lcrypto -o original-parser-gate',timeout=90)
    command(ps,'original-parser',f'cd {root} && ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 ./original-parser-gate curl-initial.bin mysite.local')
finally:
    if client:client.close()
    if ps:ps.close()
    print('EVIDENCE',OUT,flush=True)
