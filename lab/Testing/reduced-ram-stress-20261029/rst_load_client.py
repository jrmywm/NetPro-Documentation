import sys,subprocess,concurrent.futures,json,time,statistics
mode=sys.argv[1]; concurrency=int(sys.argv[2]); assert mode in ('deny','allow') and concurrency in (4,8,16)
command=['curl','--interface','192.168.80.29','--noproxy','*','--silent','--show-error','--output','/dev/null','--connect-timeout','2','--max-time','3','--resolve','netpro-tap.test:8443:192.168.80.28','--http1.1','--tlsv1.2','--tls-max','1.2','--insecure','--header','Connection: close','--write-out','%{http_code}|%{time_total}|%{local_port}','https://netpro-tap.test:8443/']
def request(n):
    r=subprocess.run(command,capture_output=True,timeout=5)
    fields=r.stdout.decode().split('|');fields+=['']*(3-len(fields))
    elapsed=float(fields[1] or 0)
    ok=(r.returncode==0 and fields[0]=='200') if mode=='allow' else (r.returncode in (35,56) and fields[0]=='000' and elapsed<2.5)
    return {'trial':n,'curl_rc':r.returncode,'http':fields[0],'elapsed_s':elapsed,'local_port':int(fields[2] or 0),'expected':ok,'error':r.stderr.decode()[:200]}
rows=[]
for start in range(0,32,concurrency):
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:rows+=list(pool.map(request,range(start+1,min(start+concurrency,32)+1)))
    if any(not x['expected'] for x in rows):break
    time.sleep(1) # Preserve existing 16 kbit/s reset safety policing between bounded bursts.
lat=sorted(x['elapsed_s']*1000 for x in rows)
print(json.dumps({'mode':mode,'concurrency':concurrency,'attempted':len(rows),'expected':sum(x['expected'] for x in rows),'p50_ms':lat[round((len(lat)-1)*.5)],'p95_ms':lat[round((len(lat)-1)*.95)],'rows':rows}),flush=True)
sys.exit(0 if len(rows)==32 and all(x['expected'] for x in rows) else 1)
