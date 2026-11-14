import paramiko,os,pathlib,json,shlex,datetime
root=pathlib.Path(__file__).resolve().parents[2]
c=paramiko.SSHClient();c.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'));c.connect('192.168.31.35',username='netpro',password=os.environ['NETPRO_LAB_PASSWORD'],timeout=10)
sql="SELECT json_build_object('domainEvents',count(*) FILTER (WHERE value LIKE '%netpro-tap.test%'),'periodicSummaryEvents',count(*) FILTER (WHERE value LIKE '%after 2 minutes%')) FROM history_log WHERE clock >= 1794006000"
cmd='runuser -u postgres -- psql -d zabbix_thesis -Atc '+shlex.quote(sql)
try:
 i,a,e=c.exec_command('sudo -S -p "" bash -c '+shlex.quote(cmd));i.write(os.environ['NETPRO_LAB_PASSWORD']+'\n');i.flush();raw=a.read().decode();rc=a.channel.recv_exit_status()
 if rc:raise RuntimeError(e.read().decode())
 counts=json.loads(raw);assert counts['domainEvents']>0 and counts['periodicSummaryEvents']>0
 result={'checkedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':'Zabbix history_log on Management, actual policy test domain and recovered periodic summary since 2026-11-06 23:00 UTC','counts':counts}
 out=root/'evidence/monitoring-receipt-20261107.json';out.write_text(json.dumps(result,indent=2));print(json.dumps(result))
finally:c.close()
