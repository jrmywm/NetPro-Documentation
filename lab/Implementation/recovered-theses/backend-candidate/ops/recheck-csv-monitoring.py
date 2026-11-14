"""Repeat live CSV propagation without overwriting historical acceptance evidence."""
from pathlib import Path
import datetime
p=Path(__file__).with_name('verify-csv-load.py')
tag=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
s=p.read_text().replace('evidence/csv-live-load.json','evidence/csv-live-load-'+tag+'.json')
exec(compile(s,str(p),'exec'),{'__file__':str(p),'__name__':'__main__'})
