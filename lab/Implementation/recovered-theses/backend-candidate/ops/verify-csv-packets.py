"""Full TAP/NPB/PS TLS path, with the test policy created ONLY through CSV import UI APIs."""
import datetime
import getpass
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from active_baseline import ActiveBaseline, BACKEND_HOST, TEST_DOMAIN

BASE=Path(__file__).resolve().parents[2]
OUT=BASE/'evidence'/('csv-packets-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
OUT.mkdir(parents=True)
def main():
    password=os.environ.get('NETPRO_SSH_PASSWORD') or getpass.getpass('NetPro lab SSH password: ')
    w=ActiveBaseline(password,OUT,Path(r'C:\Users\jim\.ssh\known_hosts'))
    w.document['workflow']='csv-import-tls-full-path'
    w.document['policy_creation_path']='authenticated CSV upload/review/activation; no legacy rule create API'
    original_id=w.run_id; result={'test_domain':TEST_DOMAIN,'results':[]}; job=None; removed=False
    def csv(mode, allow_failure=False):
        rc,out,err=w.command(BACKEND_HOST,'csv-'+mode,'python3 /home/netpro/recovered-theses-20261030/csv-live-api.py '+mode+' packet',sudo=True,timeout=60,allow_failure=allow_failure)
        if rc:
            if allow_failure:return None
            raise RuntimeError('CSV operation failed: '+mode)
        return json.loads(out)
    def probe(label, mode):
        w.run_id=original_id+'-'+label
        passed=w.run_probe(mode)
        detail=json.loads(json.dumps(w.document['outcomes'][mode]))
        result['results'].append({'name':label,'passed':passed,'scope':'20 actual client TLS requests with pcap','details':detail})
        print(('PASS ' if passed else 'FAIL ')+label,flush=True)
        if not passed:raise RuntimeError('Packet probe did not pass all trials: '+label)
    try:
        w.connect_all();w.baseline();w.start_gateway_server();w.start_return_helper()
        probe('allow-before-csv','allow')
        old=csv('job',True)
        if old and old['job']['status']=='ready':job=old['job']
        else:job=csv('upload')
        assert job.get('valid',job.get('valid_records'))==1
        assert job.get('duplicate',job.get('duplicate_records'))==1
        assert job.get('invalid',job.get('invalid_records'))==1
        result['upload']=job
        activation=csv('activate');result['activation']=activation
        for _ in range(40):
            rows=w.sqlite('SELECT id,domain,ip_address FROM policies WHERE domain=?',(TEST_DOMAIN,))
            if len(rows)==1 and rows[0]['ip_address']=='':break
            import time;time.sleep(1)
        else:raise RuntimeError('CSV domain-only policy not applied to PS')
        result['applied_policy']=rows[0]
        probe('deny-from-csv','deny')
        w.split_clienthello=True;w.document['split_clienthello_requested']=True
        try:
            w.configure_split_profile();probe('deny-split-clienthello-from-csv','deny_split')
        finally:
            w.restore_split_profile();w.split_clienthello=False
        csv('remove');w.wait_sqlite_row(rows[0]['id'],False);removed=True
        probe('allow-after-csv-removal','allow')
        w.baseline();result['baseline_restored']=True
    except Exception as e:
        result['results'].append({'name':str(e),'passed':False});raise
    finally:
        try:
            if job and not removed:csv('remove')
        finally:
            w.cleanup()
            result['cleanup']=w.document['cleanup']
            result['passed']=bool(result['results']) and all(row['passed'] for row in result['results']) and result.get('baseline_restored',False) and not any(x.get('status') in ['error','needs_review'] for x in result['cleanup'])
            (OUT/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print('Evidence:',OUT,flush=True)
    if not result['passed']:raise RuntimeError('CSV packet test or cleanup incomplete')
if __name__=='__main__':main()
