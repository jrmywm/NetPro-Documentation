"""Attach bounded, read-only CPU/RSS sampling to the verified candidate PID."""
from pathlib import Path
import sys,json,shlex
BASE=Path(__file__).resolve().parent;sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from remote import connect_verified,run_remote_command
OUT=sorted((BASE/'evidence').glob('snmp-live-http-*'))[-1]
c,_=connect_verified('192.168.31.31','netpro','netpro',Path('C:/Users/jim/.ssh/known_hosts'))
try:
 rc,root,err=run_remote_command(c,'mktemp -d /home/netpro/incoming/thesis-resource-samples.XXXXXX');root=root.strip()
 if rc:raise RuntimeError(err)
 with c.open_sftp() as s:s.put(str(BASE/'live_resource_sampler.py'),root+'/live_resource_sampler.py')
 unit='netpro-'+Path(root).name
 cmd="pid=$(systemctl show netpro-policy -p MainPID --value); test \"$(sha256sum /proc/$pid/exe | cut -d' ' -f1)\" = d74c18645a077a9435f84c9a05cdb0c407c0415ce3cb65550db1113ff4d410a4; systemd-run --quiet --collect --unit="+unit+' --uid=netpro --property=RuntimeMaxSec=90 /usr/bin/python3 '+shlex.quote(root+'/live_resource_sampler.py')+' "$pid" '+shlex.quote(root+'/samples.jsonl')
 rc,out,err=run_remote_command(c,'set -e; '+cmd,sudo_password=__import__('os').environ['NETPRO_LAB_PASSWORD'])
 (OUT/'resource-sampling.json').write_text(json.dumps({'root':root,'unit':unit,'command':cmd,'exit':rc,'stdout':out,'stderr':err,'scope':'attached during extended 10000-packet run; not all earlier trials'},indent=2),encoding='utf-8')
 print('Sampler started:',rc,unit,err)
finally:c.close()
