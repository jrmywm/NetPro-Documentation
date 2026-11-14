"""Run as root on backend-vm. New isolated DB; never change the NetPro test DB."""
from pathlib import Path
import subprocess, secrets, os, pwd, json, urllib.request, time, hashlib
def run(*args):
    return subprocess.check_output(args, text=True).strip()
def pg(sql):
    return run('sudo', '-u', 'postgres', 'psql', '-v', 'ON_ERROR_STOP=1', '-At', '-c', sql)
base = Path('/var/lib/netpro-thesis'); base.mkdir(mode=0o700, exist_ok=True)
marker = base / 'zabbix-configured.json'
if marker.exists(): raise SystemExit('Already configured; refusing to overwrite credentials/configuration')
if pg("SELECT 1 FROM pg_roles WHERE rolname='zabbix'") or pg("SELECT 1 FROM pg_database WHERE datname='zabbix_thesis'"):
    raise SystemExit('Existing Zabbix role/database found; manual review required')
password = secrets.token_hex(24)
pg(f"CREATE ROLE zabbix LOGIN PASSWORD '{password}'")
pg("CREATE DATABASE zabbix_thesis OWNER zabbix ENCODING 'UTF8' TEMPLATE template0")
schema = subprocess.Popen(['gzip', '-dc', '/usr/share/zabbix-sql-scripts/postgresql/server.sql.gz'], stdout=subprocess.PIPE)
subprocess.run(['sudo', '-u', 'zabbix', 'psql', '-v', 'ON_ERROR_STOP=1', 'zabbix_thesis'], stdin=schema.stdout, stdout=subprocess.DEVNULL, check=True)
schema.stdout.close()
if schema.wait() != 0: raise RuntimeError('Schema decompression failed')
def backup_write(path, contents, mode=0o644):
    p = Path(path)
    if p.exists():
        backup = p.with_name(p.name + '.pre-netpro-thesis')
        if backup.exists(): raise RuntimeError(f'Backup exists: {backup}')
        backup.write_bytes(p.read_bytes())
    p.write_text(contents, encoding='utf-8'); p.chmod(mode)
backup_write('/etc/zabbix/zabbix_server.conf', f'''LogFile=/var/log/zabbix/zabbix_server.log
PidFile=/run/zabbix/zabbix_server.pid
SocketDir=/run/zabbix
DBHost=
DBName=zabbix_thesis
DBUser=zabbix
DBPassword={password}
StartPollers=2
StartTrappers=2
StartSNMPTrapper=1
SNMPTrapperFile=/var/lib/zabbix/snmptraps/snmptraps.log
CacheSize=16M
HistoryCacheSize=8M
Timeout=5
ListenIP=127.0.0.1
''', 0o640)
os.chown('/etc/zabbix/zabbix_server.conf', 0, pwd.getpwnam('zabbix').pw_gid)
nginx = Path('/etc/zabbix/nginx.conf').read_text()
nginx = nginx.replace('#        listen          8080;', '        listen          192.168.31.35:8081;')
if '192.168.31.35:8081' not in nginx: raise RuntimeError('Unexpected packaged nginx listen template')
backup_write('/etc/zabbix/nginx.conf', nginx)
php = Path('/etc/zabbix/php-fpm.conf').read_text().replace('pm.max_children = 50', 'pm.max_children = 4').replace('pm.start_servers = 5', 'pm.start_servers = 1').replace('pm.min_spare_servers = 5', 'pm.min_spare_servers = 1').replace('pm.max_spare_servers = 35', 'pm.max_spare_servers = 2')
backup_write('/etc/zabbix/php-fpm.conf', php + '\nphp_value[date.timezone] = Asia/Taipei\n')
backup_write('/etc/zabbix/web/zabbix.conf.php', f'''<?php
$DB['TYPE'] = 'POSTGRESQL';
$DB['SERVER'] = '127.0.0.1';
$DB['PORT'] = '5432';
$DB['DATABASE'] = 'zabbix_thesis';
$DB['USER'] = 'zabbix';
$DB['PASSWORD'] = '{password}';
$DB['SCHEMA'] = '';
$ZBX_SERVER = '127.0.0.1';
$ZBX_SERVER_PORT = '10051';
$ZBX_SERVER_NAME = 'NetPro Thesis Monitoring';
$IMAGE_FORMAT_DEFAULT = IMAGE_FORMAT_PNG;
''', 0o640)
os.chown('/etc/zabbix/web/zabbix.conf.php', 0, pwd.getpwnam('www-data').pw_gid)
traps = Path('/var/lib/zabbix/snmptraps'); traps.mkdir(parents=True, exist_ok=True)
os.chown(traps, pwd.getpwnam('Debian-snmp').pw_uid, pwd.getpwnam('zabbix').pw_gid); traps.chmod(0o750)
traplog = traps / 'snmptraps.log'; traplog.touch(); traplog.chmod(0o640)
os.chown(traplog, pwd.getpwnam('Debian-snmp').pw_uid, pwd.getpwnam('zabbix').pw_gid)
url = 'https://raw.githubusercontent.com/zabbix/zabbix-docker/6.0/templates/scripts/snmptraps/zabbix_trap_handler.sh'
handler = urllib.request.urlopen(url, timeout=30).read()
script = Path('/usr/local/sbin/netpro-zabbix-trap-handler'); script.write_bytes(handler); script.chmod(0o755)
backup_write('/etc/snmp/snmptrapd.conf', 'authCommunity log,execute public 192.168.31.31\ntraphandle default /usr/local/sbin/netpro-zabbix-trap-handler\n')
backup_write('/etc/systemd/system/netpro-snmptrapd.service', '''[Unit]
Description=NetPro thesis Net-SNMP trap receiver for Zabbix
After=network-online.target
[Service]
User=Debian-snmp
Group=zabbix
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
UMask=0027
ExecStart=/usr/sbin/snmptrapd -f -On -n -Lo udp:192.168.31.35:162
Restart=on-failure
[Install]
WantedBy=multi-user.target
''')
subprocess.run(['systemctl', 'disable', '--now', 'snmptrapd.socket', 'snmptrapd.service'], check=False)
run('systemctl', 'daemon-reload')
run('nginx', '-t')
run('systemctl', 'enable', '--now', 'netpro-snmptrapd', 'zabbix-server')
run('systemctl', 'restart', 'php8.3-fpm', 'nginx')
time.sleep(3)
print(run('systemctl', 'is-active', 'zabbix-server', 'netpro-snmptrapd', 'netpro-backend', 'postgresql'))
marker.write_text(json.dumps({'db': 'zabbix_thesis', 'handler_url': url, 'handler_sha256': hashlib.sha256(handler).hexdigest(), 'web': 'http://192.168.31.35:8081'}, indent=2), encoding='utf-8')
print('ZABBIX_CONFIGURED=PASS; original Zabbix export not recovered; configuration is new lab setup')
