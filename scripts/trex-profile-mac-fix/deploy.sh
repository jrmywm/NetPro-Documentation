#!/usr/bin/env bash
set -euo pipefail

REMOTE_DIR=/opt/trex/v3.04/automation/trex_control_plane/interactive/trex/npb_test/npb
UPDATE_DIR=/tmp/netpro-mac-profile-update
FILES=(npb_testing_http.py npb_testing_https.py npb_testing_http_udp.py npb_testing_https_udp.py npb_testing_http_https_udp.py)
[[ -d "$REMOTE_DIR" && -d "$UPDATE_DIR" && -f "$UPDATE_DIR/MANIFEST.sha256" ]] || { echo "Missing profile/update directory or manifest" >&2; exit 1; }
if ps -eo comm= | grep -Eq '^(_?t-rex-64|trex)$'; then echo "TRex is running; refusing deploy" >&2; exit 1; fi

(cd "$REMOTE_DIR" && sha256sum -c <<'SUMS'
734a2f54328f3bbda41ab2a2c5128a127979845bdbac5512d328a5dceb9d50ca  npb_testing_http.py
6a617cd76c6fe6a16a80a1bbd6d6457193ebd76b9a12bfabbdbdfb9a2a3e517f  npb_testing_https.py
5d776c268eebe1b7fc33e76ce93cf8be2d656ff48676f3615cc79429dd9fa9f9  npb_testing_http_udp.py
102adfb44a623ae01292c52e8fa38d578ed839ba81ff66425b5ebeb4a79cbd43  npb_testing_https_udp.py
bd22a764f23927447b6a7bd0641bc67335c02f3b39d1b094d32fcb5d0ae0865c  npb_testing_http_https_udp.py
SUMS
)
(cd "$UPDATE_DIR" && sha256sum -c <<'SUMS'
ed35b05e47d40f8afa6fe3e31bac63963b05317776b8da8fba42b8b4d8ff055e  npb_testing_http.py
d69cdd7b1390f353959acb918f8c03f91a022a42f5f2eecbb57f973b1605f265  npb_testing_https.py
92f95839f73465495b0b499b59a8f5b3301d29a124a56365f024009b53a426b9  npb_testing_http_udp.py
e9206e0ab67d51c573d15109b817648274912a0ab71068e1648fa7aeadeafb41  npb_testing_https_udp.py
7b90ade576f7996678878b3812c15dee3b893ae5205d8649254a8ecc20db73b2  npb_testing_http_https_udp.py
SUMS
)
(cd "$UPDATE_DIR" && sha256sum -c MANIFEST.sha256)
python3 - "$UPDATE_DIR" "${FILES[@]}" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
for name in sys.argv[2:]:
    path = root / name
    compile(path.read_bytes(), str(path), "exec")
    print(f"Syntax OK: {name}")
PY

BACKUP_DIR=$(mktemp -d /tmp/netpro-mac-profile-backup.XXXXXX)
for file in "${FILES[@]}"; do cp -p "$REMOTE_DIR/$file" "$BACKUP_DIR/$file"; done
cp -p "$UPDATE_DIR/MANIFEST.sha256" "$BACKUP_DIR/MANIFEST.sha256"
(cd "$BACKUP_DIR" && sha256sum "${FILES[@]}") > "$BACKUP_DIR/ORIGINAL.sha256"
for file in "${FILES[@]}"; do cp -p "$UPDATE_DIR/$file" "$REMOTE_DIR/$file.tmp.$$"; done
for file in "${FILES[@]}"; do
  if ! mv -f "$REMOTE_DIR/$file.tmp.$$" "$REMOTE_DIR/$file"; then
    for restore in "${FILES[@]}"; do cp -p "$BACKUP_DIR/$restore" "$REMOTE_DIR/$restore"; done
    echo "Install failed; originals restored from $BACKUP_DIR" >&2; exit 1
  fi
done
echo "Backup: $BACKUP_DIR"
cat "$BACKUP_DIR/ORIGINAL.sha256"
for file in "${FILES[@]}"; do sha256sum "$REMOTE_DIR/$file"; done
