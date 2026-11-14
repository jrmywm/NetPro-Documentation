"""Stage original thesis modules alongside existing lab adapters. No deployment."""
from pathlib import Path
import shutil,json,hashlib
BASE=Path(__file__).resolve().parent
OLD=BASE.parents[1]/'Testing/thesis-replication'
DEST=BASE/'candidate-policy'
if DEST.exists():raise RuntimeError('Candidate exists; refusing overwrite')
shutil.copytree(OLD/'candidate-policy',DEST)
for name in ['quicFunctions.c','quicFunctions.h']:
    shutil.copy2(BASE/'original/quic-dev/quic-processor'/name,DEST/name)
# Original processor plus previously independently tested close-crafter memory fix.
shutil.copy2(OLD/'quic-fixed-candidate/packet-processor.c',DEST/'packet-processor.c')
print('STAGED',DEST)
