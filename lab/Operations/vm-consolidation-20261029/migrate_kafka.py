"""Data-preserving, staged migration of the single lab Kafka broker."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,sys,time
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from remote import connect_verified,run_remote_command,redact
p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','runtime','copy','activate']);a=p.parse_args()
base=Path(__file__).resolve().parent
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=base/'evidence'/('kafka-'+a.phase+'-'+stamp);out.mkdir(parents=True)
cred=os.environ.get('NETPRO_LAB_PASSWORD','netpro');known=Path(r'C:\Users\jim\.ssh\known_hosts');clients=[]
def connect(ip):
 c,_=connect_verified(ip,'netpro',cred,known);clients.append(c);return c
def run(c,label,cmd,sudo=True,timeout=90):
 rc,o,e=run_remote_command(c,cmd,sudo_password=cred if sudo else None,timeout=timeout)
 (out/(label+'.json')).write_text(json.dumps({'exit':rc,'stdout':redact(o),'stderr':redact(e)},indent=2),encoding='utf-8')
 print(label,'exit',rc,flush=True)
 if rc:raise RuntimeError(label+': '+redact(e[-1800:]))
 return o
try:
 back=connect('192.168.31.35')
 if a.phase=='prepare':
  run(back,'backup-and-java',f'''set -eu
umask 077
test "$(df -Pk / | awk 'NR==2 {{print $4}}')" -gt 1500000
mkdir -p /root/netpro-consolidation-{stamp}
sudo -u postgres pg_dump -Fc test > /root/netpro-consolidation-{stamp}/test.dump
sudo -u postgres pg_dumpall --globals-only > /root/netpro-consolidation-{stamp}/postgres-globals.sql
cp -a /etc/systemd/system/netpro-backend.service /root/netpro-consolidation-{stamp}/
cp -a /home/netpro/NetPro-Backend/src/config/kafkaConfig.js /root/netpro-consolidation-{stamp}/
if ! command -v java >/dev/null; then DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends openjdk-17-jre-headless; fi
java -version
df -h /
''',timeout=240)
 elif a.phase=='runtime':
  source=connect('192.168.31.32')
  run(source,'archive-runtime',f'''set -eu
umask 077
test -x /usr/lib/jvm/java-17-openjdk-amd64/bin/java
mkdir -p /home/netpro/consolidation-backups/{stamp}
chown netpro:netpro /home/netpro/consolidation-backups /home/netpro/consolidation-backups/{stamp}
tar -hczf /home/netpro/consolidation-backups/{stamp}/java-runtime.tar.gz -C /usr/lib/jvm java-17-openjdk-amd64
chown netpro:netpro /home/netpro/consolidation-backups/{stamp}/java-runtime.tar.gz
''',timeout=120)
  local=out/'java-runtime.tar.gz'
  with source.open_sftp() as s:s.get(f'/home/netpro/consolidation-backups/{stamp}/java-runtime.tar.gz',str(local))
  digest=hashlib.sha256(local.read_bytes()).hexdigest()
  run(back,'prepare-runtime-directory',f'install -d -o netpro -g netpro -m 0700 /home/netpro/consolidation-stage /home/netpro/consolidation-stage/{stamp}')
  remote=f'/home/netpro/consolidation-stage/{stamp}/java-runtime.tar.gz'
  with back.open_sftp() as s:s.put(str(local),remote)
  run(back,'install-runtime',f'''set -eu
test ! -e /opt/netpro-runtime/java-17-openjdk-amd64
printf '%s  %s\n' '{digest}' '{remote}' | sha256sum -c -
install -d -m 0755 /opt/netpro-runtime
tar -xzf {remote} -C /opt/netpro-runtime
/opt/netpro-runtime/java-17-openjdk-amd64/bin/java -version
''',timeout=120)
 elif a.phase=='copy':
  source=connect('192.168.31.32')
  run(back,'stop-backend','systemctl stop netpro-backend')
  # Stop both original services before copying their consistent state.
  run(source,'cold-backup',f'''set -eu
umask 077
mkdir -p /home/netpro/consolidation-backups/{stamp}
chown netpro:netpro /home/netpro/consolidation-backups /home/netpro/consolidation-backups/{stamp}
systemctl stop netpro-kafka
systemctl stop netpro-zookeeper
test "$(systemctl is-active netpro-kafka || true)" != active
test "$(systemctl is-active netpro-zookeeper || true)" != active
tar --sparse -czf /home/netpro/consolidation-backups/{stamp}/kafka-state.tar.gz -C / home/netpro/kafka_2.13-3.6.1 var/lib/netpro-kafka var/lib/netpro-zookeeper etc/systemd/system/netpro-kafka.service etc/systemd/system/netpro-zookeeper.service
chown netpro:netpro /home/netpro/consolidation-backups/{stamp}/kafka-state.tar.gz
sha256sum /home/netpro/consolidation-backups/{stamp}/kafka-state.tar.gz
''',timeout=180)
  local=out/'kafka-state.tar.gz'
  with source.open_sftp() as s:s.get(f'/home/netpro/consolidation-backups/{stamp}/kafka-state.tar.gz',str(local))
  digest=hashlib.sha256(local.read_bytes()).hexdigest()
  run(back,'prepare-import',f'''set -eu
test ! -e /home/netpro/kafka_2.13-3.6.1
test ! -e /var/lib/netpro-kafka
test ! -e /var/lib/netpro-zookeeper
mkdir -p /home/netpro/consolidation-stage/{stamp}
chown netpro:netpro /home/netpro/consolidation-stage /home/netpro/consolidation-stage/{stamp}
''')
  remote=f'/home/netpro/consolidation-stage/{stamp}/kafka-state.tar.gz'
  with back.open_sftp() as s:s.put(str(local),remote)
  run(back,'extract-import',f'''set -eu
printf '%s  %s\n' '{digest}' '{remote}' | sha256sum -c -
tar -xzf {remote} -C /
chown -R netpro:netpro /home/netpro/kafka_2.13-3.6.1 /var/lib/netpro-kafka /var/lib/netpro-zookeeper
cp -a /home/netpro/kafka_2.13-3.6.1/config/server.properties /home/netpro/consolidation-stage/{stamp}/server.properties.original
''',timeout=180)
  (out/'state.json').write_text(json.dumps({'stamp':stamp,'sha256':digest,'source_stopped':True},indent=2),encoding='utf-8')
 elif a.phase=='activate':
  source=connect('192.168.31.32')
  run(source,'ensure-source-stopped','test "$(systemctl is-active netpro-kafka || true)" != active; test "$(systemctl is-active netpro-zookeeper || true)" != active')
  # Backups and narrowly scoped substitutions; original services retain their names.
  run(back,'configure',f'''set -eu
umask 077
mkdir -p /root/netpro-consolidation-{stamp}
cp -a /home/netpro/NetPro-Backend/src/config/kafkaConfig.js /root/netpro-consolidation-{stamp}/
cp -a /etc/systemd/system/netpro-backend.service /root/netpro-consolidation-{stamp}/
cp -a /home/netpro/kafka_2.13-3.6.1/config/server.properties /root/netpro-consolidation-{stamp}/
''')
  # Use remote Python for exact configuration updates, sent as a reviewed script.
  cmd=r'''set -eu
python3 - <<'PY'
from pathlib import Path
p=Path('/home/netpro/kafka_2.13-3.6.1/config/server.properties')
s=p.read_text();old='advertised.listeners=PLAINTEXT://192.168.0.90:9092'
assert s.count(old)==1
p.write_text(s.replace(old,'advertised.listeners=PLAINTEXT://192.168.31.35:9092'))
p=Path('/home/netpro/NetPro-Backend/src/config/kafkaConfig.js');s=p.read_text()
assert s.count('192.168.0.90:9092')==1
p.write_text(s.replace('192.168.0.90:9092','127.0.0.1:9092'))
PY
install -d /etc/systemd/system/netpro-kafka.service.d /etc/systemd/system/netpro-zookeeper.service.d /etc/systemd/system/netpro-backend.service.d
'''
  run(back,'rewrite-endpoints',cmd)
  units={
   '/etc/systemd/system/netpro-kafka.service.d/consolidation.conf':'[Service]\nEnvironment="JAVA_HOME=/opt/netpro-runtime/java-17-openjdk-amd64"\nEnvironment="KAFKA_HEAP_OPTS=-Xms128m -Xmx512m"\nTimeoutStopSec=60\n',
   '/etc/systemd/system/netpro-zookeeper.service.d/consolidation.conf':'[Service]\nEnvironment="JAVA_HOME=/opt/netpro-runtime/java-17-openjdk-amd64"\nEnvironment="KAFKA_HEAP_OPTS=-Xms64m -Xmx128m"\nTimeoutStopSec=60\n',
   '/etc/systemd/system/netpro-backend.service.d/consolidation.conf':'[Unit]\nRequires=netpro-kafka.service\nAfter=netpro-kafka.service\n[Service]\nEnvironment="JAVA_HOME=/opt/netpro-runtime/java-17-openjdk-amd64"\nEnvironment="KAFKA_HEAP_OPTS=-Xms32m -Xmx128m"\nExecStartPre=/bin/sh -c "for i in $(seq 1 60); do /home/netpro/kafka_2.13-3.6.1/bin/kafka-broker-api-versions.sh --bootstrap-server 127.0.0.1:9092 >/dev/null 2>&1 && exit 0; sleep 1; done; exit 1"\nTimeoutStartSec=180\n'}
  # Stage bytes over SFTP rather than interpolating shell text.
  for dest,content in units.items():
   name=Path(dest).parent.name+'-'+Path(dest).name
   lp=out/name;lp.write_text(content,encoding='utf-8')
   rp='/home/netpro/'+name
   with back.open_sftp() as s:s.put(str(lp),rp)
   run(back,'install-'+name,f'install -m 0644 {rp} {dest}')
  run(back,'start-services','''set -eu
systemctl daemon-reload
systemctl enable netpro-zookeeper netpro-kafka
systemctl start netpro-zookeeper
systemctl start netpro-kafka
systemctl restart netpro-backend
systemctl is-active netpro-zookeeper netpro-kafka netpro-backend
JAVA_HOME=/opt/netpro-runtime/java-17-openjdk-amd64 /home/netpro/kafka_2.13-3.6.1/bin/kafka-topics.sh --bootstrap-server 127.0.0.1:9092 --describe --topic dpdk-blocked-list
curl -kfsS --max-time 10 https://127.0.0.1:3005/api/npb/npbs
curl -kfsS --max-time 10 https://127.0.0.1:3005/api/ps/blocked-list
free -m
''',timeout=220)
 print('COMPLETE',a.phase,'EVIDENCE',out,flush=True)
finally:
 for c in clients:c.close()
