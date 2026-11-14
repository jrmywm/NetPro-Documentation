"""New lab Zabbix host/items; not an exported configuration from the thesis author."""
from pathlib import Path
import urllib.request, json, secrets, pwd, os
URL = 'http://192.168.31.35:8081/api_jsonrpc.php'
token = None
def api(method, params):
    obj = dict(jsonrpc='2.0', method=method, params=params, id=1)
    if token is not None: obj['auth'] = token
    req = urllib.request.Request(URL, json.dumps(obj).encode(), {'Content-Type': 'application/json-rpc'})
    data = json.load(urllib.request.urlopen(req, timeout=30))
    if 'error' in data: raise RuntimeError(json.dumps(data['error']))
    return data['result']
secretfile = Path('/home/netpro/netpro-thesis/zabbix-admin.json')
secretfile.parent.mkdir(parents=True, exist_ok=True)
print('API_VERSION', api('apiinfo.version', {}))
if secretfile.exists():
    admin_password = json.loads(secretfile.read_text())['password']
else:
    token = api('user.login', {'username': 'Admin', 'password': 'zabbix'})
    admin_password = secrets.token_urlsafe(24)
    api('user.update', {'userid': '1', 'passwd': admin_password})
    secretfile.write_text(json.dumps({'url': 'http://192.168.31.35:8081', 'username': 'Admin', 'password': admin_password}, indent=2), encoding='utf-8')
    secretfile.chmod(0o600)
    u = pwd.getpwnam('netpro'); os.chown(secretfile, u.pw_uid, u.pw_gid)
token = None
token = api('user.login', {'username': 'Admin', 'password': admin_password})
# Disable packaged localhost agent host: no agent is installed in this SNMP lab.
default = api('host.get', {'filter': {'host': ['Zabbix server']}, 'output': ['hostid']})
for h in default: api('host.update', {'hostid': h['hostid'], 'status': 1})
groups = api('hostgroup.get', {'filter': {'name': ['NetPro Thesis Monitoring']}, 'output': ['groupid']})
group = groups[0]['groupid'] if groups else api('hostgroup.create', {'name': 'NetPro Thesis Monitoring'})['groupids'][0]
hosts = api('host.get', {'filter': {'host': ['NetPro Policy Server']}, 'output': ['hostid']})
hostid = hosts[0]['hostid'] if hosts else api('host.create', {'host': 'NetPro Policy Server', 'groups': [{'groupid': group}], 'interfaces': [{'type': 2, 'main': 1, 'useip': 1, 'ip': '192.168.31.31', 'dns': '', 'port': '161', 'details': {'version': 2, 'bulk': 1, 'community': 'public'}}]})['hostids'][0]
interface = api('hostinterface.get', {'hostids': [hostid], 'output': ['interfaceid']})[0]['interfaceid']
specs = [
 ('SNMP agent uptime', 'netpro.snmp.uptime', '1.3.6.1.2.1.1.3.0', 'uptime', 3),
 ('CPU user percentage (UCD-SNMP)', 'netpro.cpu.user', '1.3.6.1.4.1.2021.11.9.0', '%', 3),
 ('CPU system percentage (UCD-SNMP)', 'netpro.cpu.system', '1.3.6.1.4.1.2021.11.10.0', '%', 3),
 ('CPU idle percentage (UCD-SNMP)', 'netpro.cpu.idle', '1.3.6.1.4.1.2021.11.11.0', '%', 3),
 ('Memory total', 'netpro.memory.total', '1.3.6.1.4.1.2021.4.5.0', 'B', 3),
 ('Memory available', 'netpro.memory.available', '1.3.6.1.4.1.2021.4.6.0', 'B', 3),
]
items = {}
for name, key, oid, units, value_type in specs:
    params = dict(name=name, key_=key, hostid=hostid, interfaceid=interface, type=20, snmp_oid=oid, value_type=value_type, units=units, delay='15s', history='7d', trends='30d')
    if 'memory' in key: params['preprocessing'] = [{'type': 1, 'params': '1024', 'error_handler': 0, 'error_handler_params': ''}]
    if 'uptime' in key: params['preprocessing'] = [{'type': 1, 'params': '0.01', 'error_handler': 0, 'error_handler_params': ''}]; params['value_type'] = 0
    found = api('item.get', {'hostids': [hostid], 'filter': {'key_': key}, 'output': ['itemid']})
    items[key] = found[0]['itemid'] if found else api('item.create', params)['itemids'][0]
found = api('item.get', {'hostids': [hostid], 'filter': {'key_': 'snmptrap.fallback'}, 'output': ['itemid']})
items['traps'] = found[0]['itemid'] if found else api('item.create', dict(name='Policy Server SNMP traps', key_='snmptrap.fallback', hostid=hostid, interfaceid=interface, type=17, value_type=2, delay='0', history='7d'))['itemids'][0]
for name, keys in [('Policy Server CPU via SNMP', ['netpro.cpu.user','netpro.cpu.system','netpro.cpu.idle']), ('Policy Server memory via SNMP', ['netpro.memory.total','netpro.memory.available'])]:
    if not api('graph.get', {'hostids': [hostid], 'filter': {'name': name}, 'output': ['graphid']}):
        api('graph.create', {'name': name, 'width': 900, 'height': 250, 'gitems': [{'itemid': items[k], 'color': ['FF5959','3366CC','44AA66'][i], 'sortorder': i} for i,k in enumerate(keys)]})
state = Path('/var/lib/netpro-thesis/zabbix-monitoring.json')
state.write_text(json.dumps({'hostid': hostid, 'items': items, 'configuration_origin': 'new lab setup; original author export absent'}, indent=2), encoding='utf-8')
print('ZABBIX_HOST', hostid, 'POLL_ITEMS', len(specs), 'TRAP_ITEM', items['traps'])
print('Admin credentials saved privately on backend-vm:', secretfile)
