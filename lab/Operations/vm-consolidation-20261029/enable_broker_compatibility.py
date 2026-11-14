"""Retain the compiled-in PS bootstrap address without changing PS binaries."""
from pathlib import Path
import datetime,json,os,subprocess,sys
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified,run_remote_command,redact
vmrun=r'C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe'
old=r'D:\VMWare Virtual Machines\Kafka-Broker-VM\Kafka-Broker-VM.vmx'
z=subprocess.run([vmrun,'list'],capture_output=True,text=True,timeout=20)
if z.returncode or old.lower() in z.stdout.lower():raise SystemExit('Old Kafka VM must be off before moving its compatibility IP')
base=Path(__file__).resolve().parent;stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=base/'evidence'/('broker-compatibility-'+stamp);out.mkdir(parents=True)
unit='''[Unit]
Description=NetPro legacy Kafka bootstrap IP for preserved Policy binary
Wants=network-online.target
After=network-online.target
Before=netpro-kafka.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/ip address replace 192.168.0.90/32 dev ens33
ExecStop=/usr/sbin/ip address del 192.168.0.90/32 dev ens33

[Install]
WantedBy=multi-user.target
'''
(out/'netpro-kafka-compatibility-ip.service').write_text(unit,encoding='utf-8')
cred=os.environ.get('NETPRO_LAB_PASSWORD','netpro');c=None
try:
 c,_=connect_verified('192.168.31.35','netpro',cred,Path(r'C:\Users\jim\.ssh\known_hosts'))
 with c.open_sftp() as s:s.put(str(out/'netpro-kafka-compatibility-ip.service'),'/home/netpro/netpro-kafka-compatibility-ip.service')
 cmd='''set -eu
test ! -e /etc/systemd/system/netpro-kafka-compatibility-ip.service
install -m 0644 /home/netpro/netpro-kafka-compatibility-ip.service /etc/systemd/system/netpro-kafka-compatibility-ip.service
systemctl daemon-reload
systemctl enable --now netpro-kafka-compatibility-ip
ip -4 -br addr show ens33
JAVA_HOME=/opt/netpro-runtime/java-17-openjdk-amd64 /home/netpro/kafka_2.13-3.6.1/bin/kafka-topics.sh --bootstrap-server 192.168.0.90:9092 --describe --topic dpdk-blocked-list
'''
 rc,o,e=run_remote_command(c,cmd,sudo_password=cred,timeout=60)
 (out/'result.json').write_text(json.dumps({'exit':rc,'stdout':redact(o),'stderr':redact(e)},indent=2),encoding='utf-8')
 print('EXIT',rc,'EVIDENCE',out);print(redact(o));print(redact(e));sys.exit(rc)
finally:
 if c:c.close()
