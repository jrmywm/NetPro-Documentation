"""Build (do not install or launch) the isolated inline-policy candidate."""
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
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = BASE / "evidence" / f"build-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    names = (
        "packet-processor.c", "policyServer.c", "quicFunctions.c",
        "quicFunctions.h", "snmp_reporter.c", "snmp_reporter.h",
        "thesis_dataplane.c", "thesis_dataplane.h", "thesis_monitoring.c",
        "thesis_monitoring.h", "inline_verdict.c", "inline_verdict.h",
        "test_policy_lookup.c")
    sources = [BASE / name for name in names]
    result: dict[str, object] = {
        "created_utc": stamp,
        "host": "192.168.31.31",
        "build_only": True,
        "source_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sources
        },
    }
    c = None
    remote_root = ""
    try:
        c, _ = connect_verified(
            "192.168.31.31", "netpro", "netpro",
            Path("C:/Users/jim/.ssh/known_hosts"))
        rc, stdout, stderr = run_remote_command(
            c, "mktemp -d /home/netpro/incoming/npv1-policy-build.XXXXXX")
        remote_root = stdout.strip()
        if rc or not remote_root.startswith(
                "/home/netpro/incoming/npv1-policy-build."):
            raise RuntimeError("could not create isolated candidate build directory")
        with c.open_sftp() as sftp:
            for source in sources:
                sftp.put(str(source), f"{remote_root}/{source.name}")
        command = f"""set -eu
cd '{remote_root}'
FIXED='{fixed_root}'
FLAGS="-O1 -g -pthread -I$FIXED/headers/usr/include -I$FIXED/headers/usr/include/x86_64-linux-gnu -L$FIXED/link"
gcc $FLAGS -Dmain=archived_main -c packet-processor.c -o processor.o > build.log 2>&1
gcc $FLAGS -DALLOW_EXPERIMENTAL_API $(pkg-config --cflags libdpdk libcurl jansson sqlite3 rdkafka) \\
  policyServer.c snmp_reporter.c thesis_monitoring.c thesis_dataplane.c \\
  inline_verdict.c quicFunctions.c processor.o -o policyServer-inline \\
  $(pkg-config --libs libdpdk libcurl jansson sqlite3 rdkafka) -lcrypto -pthread >> build.log 2>&1
gcc $FLAGS -DALLOW_EXPERIMENTAL_API $(pkg-config --cflags libdpdk libcurl jansson sqlite3 rdkafka) \\
  test_policy_lookup.c snmp_reporter.c thesis_monitoring.c thesis_dataplane.c \\
  inline_verdict.c quicFunctions.c processor.o -o test-policy-lookup \\
  $(pkg-config --libs libdpdk libcurl jansson sqlite3 rdkafka) -lcrypto -pthread >> build.log 2>&1
./test-policy-lookup > policy-lookup.log 2>&1
sha256sum policyServer-inline > binary.sha256
"""
        rc, stdout, stderr = run_remote_command(c, command, timeout=180)
        result.update({"remote_root": remote_root, "exit_code": rc,
                       "stdout": stdout, "stderr": stderr})
        with c.open_sftp() as sftp:
            for name in ("build.log", "binary.sha256", "policy-lookup.log"):
                try:
                    sftp.get(f"{remote_root}/{name}", str(output / name))
                except OSError:
                    pass
        (output / "result.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"exit_code": rc,
                          "binary_sha256": ((output / "binary.sha256").read_text(
                              encoding="utf-8").split()[0]
                              if (output / "binary.sha256").exists() else None),
                          "remote_binary": f"{remote_root}/policyServer-inline",
                          "evidence_dir": str(output)}, indent=2))
        if rc:
            raise RuntimeError("candidate build failed; logs retained")
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
