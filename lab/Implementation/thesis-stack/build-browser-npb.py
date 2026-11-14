import json,os,re,sys
from pathlib import Path
import paramiko
b=Path(r'C:\Users\jim\Documents\NetPro\Implementation\thesis-stack')
c=paramiko.SSHClient()
c.load_host_keys(str(Path.home()/'.ssh/known_hosts'))
c.connect('192.168.31.33',username='netpro',password=os.environ['NETPRO_LAB_PASSWORD'],timeout=10)
try:
 _,o,e=c.exec_command('mktemp -d /home/netpro/incoming/chromium-reassembly-npb.XXXXXX')
 d=o.read().decode().strip()
 assert o.channel.recv_exit_status()==0
 old='/home/netpro/incoming/combined-npb-tls.LvFaUQ'
 with c.open_sftp() as f:
  for name in ['packetBroker.c','quic_classifier.h','tls_record_tracker.h']:
   data=f.open(old+'/'+name).read()
   if name=='quic_classifier.h':
    before=b'if(sl>20||!sl||o+sl>end)'
    assert data.count(before)==1
    data=data.replace(before,b'if(sl>20||o+sl>end)')
    (b/'candidate-npb'/'quic_classifier_browser.h').write_bytes(data)
   with f.open(d+'/'+name,'wb') as o:o.write(data)
 _,o,e=c.exec_command('cd '+d+' && gcc -O2 -DALLOW_EXPERIMENTAL_API -pthread $(pkg-config --cflags libdpdk libcurl jansson) packetBroker.c -o packetBroker-browser $(pkg-config --libs libdpdk libcurl jansson) -lhs -lstdc++ -lm >build.log 2>&1 && sha256sum packetBroker-browser',timeout=30)
 output=o.read().decode()
 assert o.channel.recv_exit_status()==0,e.read().decode()
 ps_dir=b/'evidence/chromium-reassembly-build-20261107T095606Z'
 (ps_dir/'npb-build-result.json').write_text(json.dumps({'remote':d,'sha256':output.split()[0]},indent=2))
 print(d,output)
finally:c.close()
