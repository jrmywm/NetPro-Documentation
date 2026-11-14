"""Read-only source snapshot for separate candidate development."""
from pathlib import Path
import sys,json,hashlib
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified
out=BASE/'candidate-inputs';out.mkdir(exist_ok=True)
manifest={}
for ip,repo,names in [('192.168.31.33','NetPro-Network-Packet-Broker',['packetBroker.c','tls_record_tracker.h']),('192.168.31.31','NetPro-Policy-Server',['policyServer.c'])]:
 c,_=connect_verified(ip,'netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
 try:
  with c.open_sftp() as s:
   for name in names:
    dest=out/name
    if dest.exists():raise RuntimeError('Snapshot exists; refusing overwrite: '+str(dest))
    s.get('/home/netpro/'+repo+'/'+name,str(dest));manifest[name]=hashlib.sha256(dest.read_bytes()).hexdigest()
 finally:c.close()
(out/'sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest,indent=2))
