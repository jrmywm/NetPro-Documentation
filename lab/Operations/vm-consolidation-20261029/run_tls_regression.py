"""Reuse the existing guarded live TLS workflow after consolidation."""
from pathlib import Path
import argparse,json,os,sys
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
sys.path.insert(0,r'C:\Users\jim\Documents\NetPro\Testing\snmp-quic-integration')
from active_baseline import ActiveBaseline
p=argparse.ArgumentParser();p.add_argument('--split-clienthello',action='store_true');a=p.parse_args()
base=Path(__file__).resolve().parent
workflow=ActiveBaseline(os.environ.get('NETPRO_LAB_PASSWORD','netpro'),base/'evidence',Path(r'C:\Users\jim\.ssh\known_hosts'),split_clienthello=a.split_clienthello)
rc=workflow.execute()
print('REGRESSION_PASS',rc==0,'SPLIT_CLIENTHELLO',a.split_clienthello)
if workflow.document.get('failure'):print(json.dumps(workflow.document['failure']))
sys.exit(rc)
