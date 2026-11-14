from pathlib import Path
import sys,json,shlex
BASE=Path(__file__).resolve().parent;sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
run=sorted((BASE/'evidence').glob('snmp-live-http-*'))[-1]
doc=json.loads(next(run.glob('active-baseline-*.json')).read_text())
root=next(e['stdout'].strip() for e in doc['events'] if e.get('label')=='receiver_private_directory')
c,_=connect_verified('192.168.31.35','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
try:
 unit='netpro-'+Path(root).name
 cmd='journalctl -u '+unit+' --no-pager -n 12; ss -H -lun \'sport = :11623\'; cat '+shlex.quote(root+'/receiver.log')+'; cat '+shlex.quote(root+'/cleanup.json')+'; LD_LIBRARY_PATH='+shlex.quote(root+'/private/usr/lib/x86_64-linux-gnu:'+root+'/private/lib/x86_64-linux-gnu')+' ldd '+shlex.quote(root+'/private/usr/sbin/snmptrapd')+" | grep -E 'not found|perl|gdbm|db-'"
 rc,out,err=run_remote_command(c,cmd,sudo_password=__import__('os').environ['NETPRO_LAB_PASSWORD'])
 (run/'receiver-diagnosis.json').write_text(json.dumps({'command':cmd,'exit':rc,'stdout':out,'stderr':err},indent=2),encoding='utf-8');print(out,err)
finally:c.close()
