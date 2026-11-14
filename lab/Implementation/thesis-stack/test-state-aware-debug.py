"""Controlled gateway-local state-aware Initial Close diagnostic; no traffic holding."""
from pathlib import Path
import os,paramiko,time,json,datetime
B=Path(__file__).resolve().parent
O=B/'evidence'/('state-aware-debug-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));O.mkdir()
def connect(ip):
 c=paramiko.SSHClient();c.load_host_keys(str(Path.home()/'.ssh/known_hosts'));c.connect(ip,username='netpro',password=os.environ['NETPRO_LAB_PASSWORD'],timeout=10);return c
g=connect('192.168.31.37');c=connect('192.168.31.39')
helper=r'''
import socket,struct,subprocess,json,sys,time
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from quic_analysis import expand
import hmac,hashlib
mode=sys.argv[1]
p=subprocess.Popen(['timeout','45','tcpdump','--immediate-mode','-U','-ni','ens37','-s0','-w','-','udp port 443 and host 192.168.80.29'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
s=socket.socket(socket.AF_INET,socket.SOCK_RAW,socket.IPPROTO_RAW)
def exact(n):
 b=b''
 while len(b)<n:
  a=p.stdout.read(n-len(b))
  if not a:raise EOFError
  b+=a
 return b
def ids(q):
 n=q[5];dc=q[6:6+n];o=6+n;n=q[o];return dc,q[o+1:o+1+n]
def checksum(b):
 if len(b)%2:b+=b'\0'
 n=sum(struct.unpack('!%dH'%(len(b)//2),b));n=(n>>16)+(n&65535);n+=(n>>16);return (~n)&65535
flows={};sent=set();globalhdr=exact(24);endian='<' if globalhdr[:4]==bytes.fromhex('d4c3b2a1') else '>'
print('READY',flush=True)
try:
 while True:
  sec,usec,n,_=struct.unpack(endian+'IIII',exact(16));b=exact(n)
  if len(b)<42 or b[12:14]!=b'\x08\x00':continue
  off=14+(b[14]&15)*4;sp,dp,ul,_=struct.unpack('!HHHH',b[off:off+8]);q=b[off+8:off+ul]
  if len(q)<7 or q[0]&240!=192:continue
  dc,sc=ids(q)
  if sp!=443:
   flows[sp]=(dc,sc);continue
  if dp not in flows or dp in sent:continue
  orig,client=flows[dp]
  if dc!=client:continue
  sent.add(dp)
  # Initial secrets remain derived from client's ORIGINAL DCID.
  initial=hmac.new(bytes.fromhex('38762cf7f55934b34d179ae6a4c80cadccbb7f0a'),orig,hashlib.sha256).digest()
  secret=expand(initial,b'server in',32);key=expand(secret,b'quic key',16);iv=expand(secret,b'quic iv',12);hp=expand(secret,b'quic hp',16)
  pn=1 if mode=='corrected' else 0;server=sc if mode=='corrected' else bytes.fromhex('fd8b4bf2')
  reason=b'NETPRO_CONTROLLED_DIAGNOSTIC';plain=b'\x1c\x02\x06'+bytes([len(reason)])+reason
  length=1+len(plain)+16
  head=b'\xc0\x00\x00\x00\x01'+bytes([len(client)])+client+bytes([len(server)])+server+b'\0'+bytes([length])
  aad=head+bytes([pn]);nonce=bytes(a^b for a,b in zip(iv,pn.to_bytes(12,'big')));enc=AESGCM(key).encrypt(nonce,plain,aad);raw=bytearray(aad+enc)
  mask=Cipher(algorithms.AES(hp),modes.ECB()).encryptor().update(raw[len(head)+4:len(head)+20]);raw[0]^=mask[0]&15;raw[len(head)]^=mask[1]
  udp=struct.pack('!HHHH',443,dp,8+len(raw),0)+raw
  ip=bytearray(struct.pack('!BBHHHBBH4s4s',69,0,20+len(udp),0,0,64,17,0,b[26:30],b[30:34]));ip[10:12]=struct.pack('!H',checksum(bytes(ip)))
  s.sendto(bytes(ip)+udp,(socket.inet_ntoa(b[30:34]),0));print(json.dumps({'port':dp,'mode':mode,'real_scid':sc.hex(),'injected_scid':server.hex(),'pn':pn}),flush=True)
except EOFError:pass
finally:p.terminate();s.close()
'''
try:
 remote='/home/netpro/incoming/state-aware-close-'+O.name
 _,a,_=g.exec_command('mkdir -p '+remote);a.channel.recv_exit_status()
 with g.open_sftp() as f:
  with f.file(remote+'/helper.py','w') as z:z.write(helper)
  f.put(str(B/'analyze-close-capture.py'),remote+'/quic_analysis.py')
 rows=[]
 capture='/home/netpro/incoming/'+O.name+'.pcap'
 si,so,se=c.exec_command('sudo -S -p "" sh -c '+__import__('shlex').quote('tcpdump -U -ni ens37 -s0 -w '+capture+' "udp port 443 and host 192.168.80.28" >/dev/null 2>&1 & echo $!'))
 si.write(os.environ['NETPRO_LAB_PASSWORD']+'\n');si.flush();capture_pid=int(so.read().decode().strip());time.sleep(1)
 for mode in ['original','corrected']:
  si,so,se=g.exec_command('sudo -S -p "" timeout 40 python3 -u '+remote+'/helper.py '+mode);si.write(os.environ['NETPRO_LAB_PASSWORD']+'\n');si.flush()
  assert so.readline().strip()=='READY'
  for i in range(5):
   command="/home/netpro/netpro-thesis/http3/src/curl/src/curl --http3-only --noproxy '*' --interface 192.168.80.29 --resolve mysite.local:443:192.168.80.28 -k --connect-timeout 3 --max-time 5 -sS -o /dev/null -w 'HTTP %{http_code} VERSION %{http_version}\\n' https://mysite.local/; echo RC=$?"
   _,a,e=c.exec_command(command,timeout=10);out=a.read().decode();err=e.read().decode();rows.append({'mode':mode,'trial':i+1,'stdout':out,'stderr':err});print(mode,i+1,out.strip(),flush=True)
  # timeout bounds helper lifetime; wait then collect its actual output.
  log=so.read().decode();errors=se.read().decode();(O/(mode+'-helper.log')).write_text(log+errors,encoding='utf-8')
 si,so,se=c.exec_command('sudo -S -p "" kill -INT '+str(capture_pid));si.write(os.environ['NETPRO_LAB_PASSWORD']+'\n');si.flush();so.channel.recv_exit_status();time.sleep(1)
 si,so,se=c.exec_command('sudo -S -p "" chmod 644 '+capture);si.write(os.environ['NETPRO_LAB_PASSWORD']+'\n');si.flush();so.channel.recv_exit_status()
 with c.open_sftp() as f:f.get(capture,str(O/'client.pcap'))
 (O/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8');print('EVIDENCE',O)
finally:g.close();c.close()
