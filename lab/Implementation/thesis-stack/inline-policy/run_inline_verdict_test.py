"""Build and run the NPV1 loopback check on the Policy Server VM."""
from __future__ import annotations

import datetime
import hashlib
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
STACK = BASE.parent
TESTING = STACK.parents[1] / "Testing"
sys.path.insert(0, str(TESTING / "snmp-quic-integration"))
from remote import connect_verified, run_remote_command  # noqa: E402


def latest(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"no {pattern} in {directory}")
    return matches[-1]


def main() -> None:
    fixed_evidence = latest(TESTING / "thesis-replication" / "evidence",
                           "quic-fixed-gate-*")
    fixed_root = json.loads((fixed_evidence / "sources.json").read_text(
        encoding="utf-8"))["directory"]
    parser_evidence = latest(BASE.parent / "evidence", "original-parser-*")
    fixture = parser_evidence / "curl-initial.bin"
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = BASE / "evidence" / f"loopback-{stamp}"
    output.mkdir(parents=True, exist_ok=False)

    sources = [BASE / name for name in (
        "inline_verdict.c", "inline_verdict.h", "test_inline_verdict.c",
        "verify_inline_verdict.py")]
    sources.append(BASE.parent / "inline-gate" / "gate.py")
    sources.append(fixture)
    c = None
    remote_root = ""
    result: dict[str, object] = {
        "created_utc": stamp,
        "host": "192.168.31.31",
        "test": "isolated NPV1 loopback publisher/verifier",
        "source_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sources
        },
    }
    try:
        c, _ = connect_verified(
            "192.168.31.31", "netpro", "netpro",
            Path("C:/Users/jim/.ssh/known_hosts"))
        rc, out, err = run_remote_command(
            c, "mktemp -d /home/netpro/incoming/npv1-loopback.XXXXXX")
        remote_root = out.strip()
        if rc or not remote_root.startswith("/home/netpro/incoming/npv1-loopback."):
            raise RuntimeError("could not create isolated temporary build directory")
        with c.open_sftp() as sftp:
            for path in sources:
                sftp.put(str(path), f"{remote_root}/{path.name}")
        command = f"""set -eu
cd '{remote_root}'
FIXED='{fixed_root}'
gcc -O1 -g -pthread \\
  -I"$FIXED/headers/usr/include" \\
  -I"$FIXED/headers/usr/include/x86_64-linux-gnu" \\
  -L"$FIXED/link" \\
  $(pkg-config --cflags libdpdk) \\
  test_inline_verdict.c inline_verdict.c -o test_inline_verdict \\
  $(pkg-config --libs libdpdk) -lcrypto -pthread > build.log 2>&1
python3 verify_inline_verdict.py ./test_inline_verdict curl-initial.bin > test.log 2>&1
sha256sum test_inline_verdict > binary.sha256
cat test.log
"""
        rc, stdout, stderr = run_remote_command(c, command, timeout=180)
        result.update({"remote_root": remote_root, "exit_code": rc,
                       "stdout": stdout, "stderr": stderr})
        with c.open_sftp() as sftp:
            for name in ("build.log", "test.log", "binary.sha256"):
                try:
                    sftp.get(f"{remote_root}/{name}", str(output / name))
                except OSError:
                    pass
        (output / "result.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"exit_code": rc, "stdout": stdout.strip(),
                          "evidence_dir": str(output),
                          "remote_root": remote_root}, indent=2))
        if rc:
            raise RuntimeError("loopback build or verification failed; logs retained")
    except Exception as exc:
        result["error"] = str(exc)
        result["remote_root"] = remote_root
        (output / "result.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8")
        raise
    finally:
        if c:
            c.close()


if __name__ == "__main__":
    main()
