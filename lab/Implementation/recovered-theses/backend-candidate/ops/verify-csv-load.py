"""Actual authenticated 1,001-policy CSV activation/publication/application/removal check."""
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import time
spec=importlib.util.spec_from_file_location('live_helpers',Path(__file__).with_name('verify-live-e2e.py'))
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def main():
    mg,_=h.connect_verified('192.168.31.35','netpro',h.password,h.KNOWN)
    ps,_=h.connect_verified('192.168.31.31','netpro',h.password,h.KNOWN)
    api='python3 /home/netpro/recovered-theses-20261030/csv-live-api.py '
    baseline=h.policies(ps); results=[];fixture=None;activated=False
    try:
        fixture=json.loads(h.command(mg,api+'upload load'))
        assert fixture['valid']==1001 and fixture['duplicate']==1 and fixture['invalid']==0
        prefix=fixture['prefix'];assert re.fullmatch(r'csv-load-[0-9a-f-]+-',prefix)
        activated=True;publication=json.loads(h.command(mg,api+'activate load'))
        assert publication['stored']==1001 and publication['published']==1001
        expected=json.loads(h.command(mg,api+'snapshot load'))
        code="import sqlite3,json,hashlib; c=sqlite3.connect('file:/home/ubuntu/NetPro-Policy-Server/policy.db?mode=ro',uri=True); rows=c.execute('SELECT id,domain,ip_address FROM policies WHERE domain LIKE ? ORDER BY id',("+repr(prefix+'%')+",)).fetchall(); text='\\n'.join('|'.join(str(v or '') for v in r) for r in rows); print(json.dumps({'count':len(rows),'digest':hashlib.md5(text.encode()).hexdigest()}))"
        for _ in range(120):
            actual=json.loads(h.command(ps,'python3 -c '+shlex.quote(code)))
            if actual==expected:break
            time.sleep(1)
        else:raise RuntimeError('PS application count/digest did not match all 1001 authoritative policies')
        results.append({'name':'1001 CSV policies (explicit IP + domain only) published/applied with exact UUID/domain/IP digest','passed':True,'expected':expected})
        print('PASS 1,001 unique CSV policies applied exactly on active Policy Server')
    except Exception as e:results.append({'name':str(e),'passed':False});raise
    finally:
        try:
            if activated:
                h.command(mg,api+'remove load')
                for _ in range(120):
                    report=json.loads(h.command(ps,'python3 -c '+shlex.quote(code)))
                    if report['count']==0:break
                    time.sleep(1)
                else:raise RuntimeError('Load fixture removal did not reach PS')
                assert h.policies(ps)==baseline
                results.append({'name':'all 1001 fixture policies removed and exact PS baseline restored','passed':True})
                print('PASS 1,001-rule cleanup and exact PS baseline restoration')
        finally:
            mg.close();ps.close()
            (h.BASE/'evidence/csv-live-load.json').write_text(json.dumps({'date':datetime.datetime.now(datetime.timezone.utc).isoformat(),'fixture':fixture,'results':results,'packetBlockingTested':False},indent=2),encoding='utf-8')
if __name__=='__main__':main()
