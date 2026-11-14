"""Run existing guarded TLS deny/allow baseline; preserve policies and cleanup."""
from pathlib import Path
import sys
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'snmp-quic-integration'))
from active_baseline import ActiveBaseline
if __name__=='__main__':
 workflow=ActiveBaseline('netpro',BASE/'evidence',Path('C:/Users/jim/.ssh/known_hosts'),split_clienthello=True)
 raise SystemExit(workflow.execute())
