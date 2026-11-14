"""Root-only disposable-account driver for the deployed user-facing CSV API (via nginx)."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

SESSION = Path('/home/netpro/recovered-theses-20261030/csv-test-session.json')
context = ssl.create_default_context(cafile='/home/ubuntu/cert/server.crt'); context.check_hostname = False
BASE = 'https://127.0.0.1:3005/api'
def save(data):
    fd = os.open(str(SESSION), os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as out: json.dump(data, out, indent=2)
def api(endpoint, method='GET', body=None, token=None, raw=None, content_type=None):
    headers = {'Content-Type': content_type or 'application/json'}
    if token: headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + endpoint, method=method, headers=headers,
        data=raw if raw is not None else None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, context=context, timeout=120) as r:
            data = r.read(); return r.status, json.loads(data) if 'json' in r.headers.get('Content-Type','') else data.decode()
    except urllib.error.HTTPError as e:
        text = e.read().decode();
        try: value = json.loads(text)
        except ValueError: value = {'message': text[:500]}
        return e.code, value
def checked(*args, **kwargs):
    status, value = api(*args, **kwargs)
    if status >= 300: raise RuntimeError('API %s: %s' % (status, value))
    return value
def user(data, which='A'): return data['users'][which]
def wait(data, label, desired):
    entry = data['jobs'][label]; token = user(data)['token']
    for _ in range(600):
        try:
            code, response = api('/ps/csv-imports/' + entry['id'], token=token)
            if code in [502,503,504]: time.sleep(.3); continue
            if code >= 300: raise RuntimeError('Job request failed: '+str(response))
            job = response['job']
        except (urllib.error.URLError, OSError): time.sleep(.3); continue
        if job['status'] == desired: entry['job'] = job; save(data); return job
        if job['status'] == 'failed' and desired != 'failed': raise RuntimeError('Job failed: ' + str(job['error_message']))
        time.sleep(.3)
    raise RuntimeError('Job timed out waiting for ' + desired)
def main():
    if os.geteuid() != 0: raise RuntimeError('Root needed for private test session')
    mode = sys.argv[1]
    if mode == 'setup':
        if SESSION.exists() and json.loads(SESSION.read_text()).get('active'):
            print(json.dumps({'active': True, 'reused': True})); return
        data = {'active': True, 'suffix': secrets.token_hex(5), 'users': {}, 'jobs': {}}
        save(data)
        for which in ['A','B']:
            email = 'netpro-csv-' + which.lower() + '-' + data['suffix'] + '@example.test'
            password = secrets.token_urlsafe(24)
            data['users'][which] = {'email': email, 'password': password}; save(data)
            checked('/user/register','POST',{'name': 'NetPro CSV test ' + which,'email': email,'password': password})
            login = checked('/user/login','POST',{'email': email,'password': password})['loginResult']
            data['users'][which].update({'id': login['userId'], 'token': login['token']}); save(data)
        print(json.dumps({'active': True, 'accounts': 2, 'credentialsPrinted': False})); return
    data = json.loads(SESSION.read_text()); token = user(data)['token']
    label = sys.argv[2] if len(sys.argv) > 2 else 'small'
    if mode == 'upload':
        if label in data['jobs']:
            old = checked('/ps/csv-imports/'+data['jobs'][label]['id'],token=token)['job']
            reusable = (label == 'restart' and old['status'] == 'ready') or (label == 'packet' and old['status'] == 'removed')
            if not reusable or old['publication']['stored']:
                raise RuntimeError('Fixture label already exists')
            data.setdefault('history',[]).append({'label':label,**data['jobs'][label]}); del data['jobs'][label]; save(data)
        suffix = data['suffix'] + '-' + secrets.token_hex(3)
        if label == 'packet':
            domains = ['netpro-tap.test']; content = 'domain,ip_add,name,category\nnetpro-tap.test,,NetPro CSV packet verification,Other\nnetpro-tap.test,,NetPro CSV packet verification,Other\n,,Missing,Other\n'
        elif label in ['large','restart']:
            domains = []; content = 'domain,category\n' + ''.join('csv-large-%s-%d.example,Other\n' % (suffix,i) for i in range(100000))
        elif label == 'load':
            domains = ['csv-load-%s-%d.example' % (suffix,i) for i in range(1001)]
            rows = ['%s,%s,Other\n' % (domain,'192.0.2.244' if i % 2 == 0 else '') for i,domain in enumerate(domains)]
            content = 'domain,ip_add,category\n' + ''.join(rows) + rows[0]
        else:
            domains = ['csv-api-' + suffix + '.example', 'csv-api-sni-' + suffix + '.example']
            content = 'domain,ip_add,category\n%s,192.0.2.245,Other\n%s,,Other\n%s,192.0.2.245,Other\n,,Other\nhttps://example.com,,Other\n' % (domains[0],domains[1],domains[0])
        boundary = 'netpro-' + secrets.token_hex(12)
        name = 'netpro-csv-' + label + '-' + suffix + '.csv'
        raw = ('--'+boundary+'\r\nContent-Disposition: form-data; name="files"; filename="'+name+'"\r\nContent-Type: text/csv\r\n\r\n'+content+'\r\n--'+boundary+'--\r\n').encode()
        result = checked('/ps/csv-imports','POST',token=token,raw=raw,content_type='multipart/form-data; boundary='+boundary)
        data['jobs'][label] = {'id': result['jobs'][0]['id'], 'domains': domains, 'prefix': 'csv-load-'+suffix+'-' if label=='load' else None}; save(data)
        job = wait(data,label,'ready'); print(json.dumps({'id':job['id'],'status':job['status'],'total':job['total_records'],
            'valid':job['valid_records'],'duplicate':job['duplicate_records'],'invalid':job['invalid_records'],'domains':domains if len(domains)<5 else [],'prefix':data['jobs'][label]['prefix']})); return
    entry = data['jobs'].get(label)
    if mode == 'owner-checks':
        job_id = data['jobs']['small']['id']
        assert api('/ps/csv-imports')[0] == 401
        assert api('/ps/csv-imports/'+job_id, token=user(data,'B')['token'])[0] == 404
        assert checked('/ps/csv-imports',token=user(data,'B')['token'])['jobs'] == []
        preview = checked('/ps/csv-imports/'+job_id+'/preview',token=token)
        assert len(preview['rows']) == 2 and len(preview['failures']) == 2
        assert 'Domain is required' in checked('/ps/csv-imports/'+job_id+'/failures.csv',token=token)
        assert api('/ps/csv-imports/'+job_id+'/activate','POST',{},token=token)[0] == 400
        assert api('/ps/csv-imports/'+job_id+'/activate','POST',{'confirmation':'ACTIVATE'},token=token)[0] == 409
        print(json.dumps({'passed':True,'checks':['401 missing token','404 different owner','owner-isolated history','preview','failed CSV','confirmation required','invalid-row review required']})); return
    if mode == 'activate':
        checked('/ps/csv-imports/'+entry['id']+'/activate','POST',{'confirmation':'ACTIVATE','acceptInvalid':True},token=token)
        job=wait(data,label,'completed')
        print(json.dumps({'id':job['id'],'source_key':job['source_key'],'stored':job['publication']['stored'],'published':job['publication']['published'],'applicationVerified':job['applicationVerified']})); return
    if mode == 'remove':
        job = checked('/ps/csv-imports/'+entry['id'],token=token)['job']
        if job['publication']['stored']:
            checked('/ps/csv-imports/'+entry['id']+'/remove','POST',{'confirmation':'REMOVE'},token=token)
            job=wait(data,label,'removed')
        print(json.dumps({'id':job['id'],'status':job['status']})); return
    if mode == 'job':
        print(json.dumps(checked('/ps/csv-imports/'+entry['id'],token=token))); return
    if mode == 'snapshot':
        if not re.fullmatch(r'[0-9a-f-]{36}', entry['id']): raise RuntimeError('Invalid fixture job ID')
        query = "SELECT json_build_object('count',count(*),'digest',md5(coalesce(string_agg(p.id::text||'|'||p.domain||'|'||coalesce(p.ip_add,''),E'\\n' ORDER BY p.id),''))) FROM ps_blocked_list p JOIN netpro_bulk_policy_keys k ON k.policy_id=p.id WHERE k.source_key=(SELECT source_key FROM netpro_csv_jobs WHERE id='%s')" % entry['id']
        r=subprocess.run(['runuser','-u','postgres','--','psql','-d','test','-Atc',query],capture_output=True,text=True,check=True)
        print(r.stdout.strip()); return
    if mode == 'session-info':
        print(json.dumps({'email':user(data)['email'],'userId':user(data)['id'],'jobs':{k:v['id'] for k,v in data['jobs'].items()}})); return
    if mode == 'retire':
        for key, item in data['jobs'].items():
            job=checked('/ps/csv-imports/'+item['id'],token=token)['job']
            if job['publication']['stored'] and job['status']!='removed': raise RuntimeError('Active job remains: '+key)
        for u in data['users'].values():
            checked('/user/delete','DELETE',token=u['token']); u.pop('token',None); u.pop('password',None)
        data['active']=False; save(data); print(json.dumps({'temporaryAccountsRemoved':2,'jobEvidenceRetained':True})); return
    raise RuntimeError('Unknown mode')
if __name__ == '__main__': main()
