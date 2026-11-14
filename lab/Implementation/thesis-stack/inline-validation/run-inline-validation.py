#!/usr/bin/env python3
"""Guarded preflight and parent-reviewed inline QUIC validation workflow."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import secrets
import shlex
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

STACK = Path(__file__).resolve().parents[1]
IMPLEMENTATION = STACK.parent
TESTING = IMPLEMENTATION.parent / "Testing"
sys.path.insert(0, str(TESTING / "snmp-quic-integration"))
sys.path.insert(0, str(TESTING / "thesis-replication"))

import active_baseline as ab  # noqa: E402
from remote import HOSTS, connect_verified, run_remote_command  # noqa: E402
from candidate_rollout import CandidateRollout  # noqa: E402

POLICY = "192.168.31.31"
NPB = "192.168.31.33"
BACKEND = "192.168.31.35"
GATE = "192.168.31.38"
CLIENT = "192.168.31.39"
GATEWAY = "192.168.31.37"
EXPECTED_ORIGINALS = {
    "policy": "5892e752bb08395b2b3b1170fc9e45af21ac9251b7dfc9860a7b28dde0865614",
    "npb": "607a680272458c2dad46e7caf16751990632415c940401f4fbfac68e88196430",
}
NPB_CANDIDATE_SHA = "3cde672b35005895a3121ce50ad892b98a5b1a935c0e60bfcd1ee2f7883fe760"
ORIGIN = "192.168.80.28"
CLIENT_ADDR = "192.168.80.29"
TEST_URL = "https://mysite.local/"
KNOWN_HOSTS = Path.home() / ".ssh" / "known_hosts"


class CheckFailure(RuntimeError):
    pass


class QueuePhaseComplete(Exception):
    """Internal signal to finish after synthetic queue-mechanism evidence."""


def remote(client, command: str, *, sudo: bool = False, timeout: int = 12) -> str:
    rc, out, err = run_remote_command(client, command,
                                      sudo_password=PASSWORD if sudo else None,
                                      timeout=timeout)
    if rc:
        raise CheckFailure(f"read-only probe failed (exit {rc}): {err[-300:]}")
    return out.strip()


def check(label: str, result: str, required: str | None = None) -> dict:
    passed = required is None or required in result
    return {"check": label, "passed": passed, "result": result[-4000:]}


def run_preflight(evidence: Path) -> int:
    clients = {}
    checks: list[dict] = []
    document = {
        "workflow": "inline-quic-preflight",
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "live_test_executed": False,
        "mutations_performed": False,
        "secrets_recorded": False,
        "checks": checks,
    }
    try:
        for ip in (POLICY, NPB, BACKEND, GATE, GATEWAY, CLIENT):
            client, hostname = connect_verified(ip, "netpro", PASSWORD, KNOWN_HOSTS)
            clients[ip] = client
            checks.append(check("trusted SSH identity " + ip, hostname, HOSTS[ip]))

        # Exact API and SQLite ID sets are read-only. ActiveBaseline's baseline
        # routine refuses any unexpected drift and preserves SQLite-only rows.
        baseline = ab.ActiveBaseline(PASSWORD, evidence, KNOWN_HOSTS)
        baseline.clients = clients
        baseline.baseline()
        checks.append(check("Backend API and Policy SQLite baseline",
                            "exact known ID sets verified; SQLite-only rows preserved",
                            "exact known ID sets verified"))

        proc = remote(clients[POLICY],
                      "set -eu; systemctl is-active netpro-policy; "
                      "p=$(systemctl show netpro-policy -p MainPID --value); "
                      "sha256sum /proc/$p/exe", sudo=True)
        checks.append(check("Policy Server original executable hash", proc,
                            EXPECTED_ORIGINALS["policy"]))
        proc = remote(clients[NPB],
                      "set -eu; systemctl is-active netpro-npb; "
                      "p=$(systemctl show netpro-npb -p MainPID --value); "
                      "sha256sum /proc/$p/exe", sudo=True)
        checks.append(check("NPB original executable hash", proc,
                            EXPECTED_ORIGINALS["npb"]))

        tap = remote(clients[GATE],
                     "set -eu; ip -d link show br-tap; bridge link show; "
                     "ip -brief address show; "
                     "tc -s filter show dev ens34 ingress; "
                     "echo MIRROR_ENS34; tc -s filter show dev ens34 ingress; "
                     "echo MIRROR_ENS35; tc -s filter show dev ens35 ingress; "
                     "nft --version; nft list tables", sudo=True)
        for item in ("br-tap", "ens34", "ens35", "ens36"):
            checks.append(check("TAP interface present: " + item, tap, item))
        mirror34 = tap.split("MIRROR_ENS34", 1)[-1].split("MIRROR_ENS35", 1)[0]
        mirror35 = tap.split("MIRROR_ENS35", 1)[-1]
        checks.append(check("TAP ens34 ingress mirror hook", mirror34,
                            "mirred" if "mirred" in mirror34.lower() else "<missing>"))
        checks.append(check("TAP ens35 ingress mirror hook", mirror35,
                            "mirred" if "mirred" in mirror35.lower() else "<missing>"))
        checks.append(check("TAP bridge/mirror and nft inventory", tap))

        gate_deps = remote(clients[GATE],
                           "set -eu; /opt/netpro/inline-gate-venv/bin/python -c 'import netfilterqueue'; "
                           "command -v nft; command -v tcpdump; "
                           "test \"$(systemctl show -p LoadState --value "
                           "netpro-quic-gate-rollback.timer)\" = not-found; "
                           "if nft list table bridge netpro_quic_gate >/dev/null 2>&1; "
                           "then echo OWNED_TABLE_PRESENT; exit 1; "
                           "else echo OWNED_TABLE_ABSENT; fi; "
                           "if ss -H -lun 'sport = :19191' | grep -q .; "
                           "then echo VERDICT_PORT_IN_USE; exit 1; "
                           "else echo VERDICT_PORT_FREE; fi", sudo=True)
        checks.append(check("Gate dependencies and unowned runtime state", gate_deps))

        client_probe = remote(clients[CLIENT],
                              "set -eu; test -x /home/netpro/netpro-thesis/http3/prefix/bin/curl; "
                              "/home/netpro/netpro-thesis/http3/prefix/bin/curl -V")
        checks.append(check("Client HTTP/3-only curl binary", client_probe,
                            "HTTP3"))

        caddy = remote(clients[GATEWAY],
                       "set -eu; systemctl is-active caddy; "
                       "ss -H -lunp | grep -E '(:443[[:space:]]|:443$)'; "
                       "grep -F 'https://mysite.local' /etc/caddy/Caddyfile")
        checks.append(check("Caddy HTTP/3 endpoint and existing mysite.local vhost",
                            caddy, "https://mysite.local"))

        # Save only verification results. Password/key/session material is never
        # serialized, and command outputs are bounded by the shared SSH helper.
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "preflight.json").write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8")
        for row in checks:
            print(("PASS" if row["passed"] else "STOP"), row["check"], flush=True)
        print("PREFLIGHT_EVIDENCE", evidence / "preflight.json", flush=True)
        return 0 if all(x["passed"] for x in checks) else 2
    except Exception as exc:
        document["fatal"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "preflight.json").write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print("STOP: preflight failed; no live configuration was changed:",
              str(exc)[:300], flush=True)
        print("PREFLIGHT_EVIDENCE", evidence / "preflight.json", flush=True)
        return 2
    finally:
        for client in clients.values():
            client.close()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def command(workflow, host: str, label: str, text: str, *, sudo: bool = False,
            timeout: int = 30) -> str:
    rc, out, err = workflow.command(host, label, text, sudo=sudo, timeout=timeout)
    if rc:
        raise CheckFailure(f"{label} failed on {host}: {err[-400:]}")
    return out.strip()


def upload_private(sftp, path: str, content: bytes) -> None:
    """Create a new owner-only key file; never overwrite a prior run's key."""
    with sftp.open(path, "wx") as stream:
        stream.write(content)
    sftp.chmod(path, 0o600)


def stage_gate(workflow, run_id: str) -> tuple[str, str]:
    """Stage only reviewed gate files into a new remote incoming directory."""
    remote_root = f"/home/netpro/incoming/inline-gate-{run_id}"
    source = STACK / "inline-gate"
    files = (source / "gate.py", source / "stage-tap-rule.sh",
             source / "rollback-tap-rule.sh")
    require(all(p.is_file() and not p.is_symlink() for p in files),
            "gate source bundle missing or contains a symlink")
    sftp = workflow.clients[GATE].open_sftp()
    try:
        sftp.mkdir(remote_root, 0o700)
        for local in files:
            remote_path = remote_root + "/" + local.name
            with local.open("rb") as src, sftp.open(remote_path, "wx") as dst:
                dst.write(src.read())
            sftp.chmod(remote_path, 0o700 if local.suffix == ".sh" else 0o600)
    finally:
        sftp.close()
    return remote_root, remote_root + "/gate.py"


def start_gate(workflow, unit: str, script: str, key_path: str,
               session_hex: str) -> None:
    q = shlex.quote
    timer = unit + "-rollback"
    command(workflow, GATE, "gate_name_guard",
            "set -eu; test \"$(systemctl show -p LoadState --value " + q(unit + ".service") +
            ")\" = not-found; test \"$(systemctl show -p LoadState --value " + q(timer + ".timer") +
            ")\" = not-found; ! ss -H -lun 'sport = :19191' | grep -q .", sudo=True)
    command(workflow, GATE, "gate_rollback_timer_arm",
            "systemd-run --quiet --collect --unit=" + q(timer) +
            " --on-active=20m /bin/systemctl stop " + q(unit + ".service"),
            sudo=True, timeout=12)
    start = ("systemd-run --quiet --unit=" + q(unit) +
             " --property=Type=simple --property=Restart=no" +
             " --setenv=NETPRO_VERDICT_HMAC_KEY_FILE=" + q(key_path) +
             " --setenv=NETPRO_VERDICT_SESSION_ID=" + q(session_hex) +
             " --setenv=NETPRO_NFQUEUE=4242 "
             "/opt/netpro/inline-gate-venv/bin/python " + q(script))
    command(workflow, GATE, "gate_start", start, sudo=True, timeout=15)
    ready = ("set -eu; for i in $(seq 1 20); do "
             "systemctl is-active --quiet " + q(unit + ".service") +
             " && ss -H -lun 'sport = :19191' | grep -q . && { echo GATE_LISTENER_READY; exit 0; }; "
             "sleep 0.25; done; journalctl -u " + q(unit + ".service") +
             " -n 30 --no-pager; exit 1")
    command(workflow, GATE, "gate_readiness", ready, sudo=True, timeout=12)
    logs = command(workflow, GATE, "gate_nfqueue_ready_event",
                   "journalctl -u " + q(unit + ".service") +
                   " -o cat --no-pager", sudo=True, timeout=10)
    require('"event": "gate_ready"' in logs,
            "gate listener is not confirmed bound to NFQUEUE; refusing to install queue hook")


def stage_queue(workflow, remote_root: str) -> None:
    q = shlex.quote
    command(workflow, GATE, "queue_table_absent",
            "set -eu; ! nft list table bridge netpro_quic_gate >/dev/null 2>&1; "
            "test \"$(systemctl show -p LoadState --value "
            "netpro-quic-gate-rollback.timer)\" = not-found", sudo=True)
    command(workflow, GATE, "queue_stage",
            "/bin/bash " + q(remote_root + "/stage-tap-rule.sh"),
            sudo=True, timeout=15)
    command(workflow, GATE, "queue_stage_verify",
            "set -eu; nft list table bridge netpro_quic_gate; "
            "systemctl is-active --quiet netpro-quic-gate-rollback.timer",
            sudo=True)


def start_capture(workflow, host: str, interface: str, run_id: str,
                  filters: str) -> dict:
    unit = f"netpro-inline-cap-{run_id}-{host.split('.')[-1]}-{interface}"
    path = f"/home/netpro/incoming/{unit}.pcap"
    q = shlex.quote
    command(workflow, host, "capture_path_absent",
            "test ! -e " + q(path), sudo=True)
    tcpdump_path = command(workflow, host, "capture_binary", "command -v tcpdump", sudo=True)
    require(tcpdump_path.startswith("/usr/") and "\n" not in tcpdump_path,
            "unexpected tcpdump executable path")
    start = ("systemd-run --quiet --unit=" + q(unit) +
             " /usr/bin/timeout --signal=INT 180 " + q(tcpdump_path) + " -U -ni " + q(interface) +
             " -s0 -w " + q(path) + " " + q(filters))
    command(workflow, host, "capture_start", start, sudo=True, timeout=12)
    command(workflow, host, "capture_process_ready",
            "systemctl is-active --quiet " + q(unit + ".service"), sudo=True)
    return {"host": host, "interface": interface, "unit": unit, "path": path}


def stop_captures(workflow, captures: list[dict], evidence: Path) -> None:
    for cap in captures:
        unit = cap["unit"]
        try:
            command(workflow, cap["host"], "capture_stop",
                    "systemctl kill --signal=SIGINT " + shlex.quote(unit + ".service"),
                    sudo=True, timeout=15)
            time.sleep(0.4)
            rc, out, _ = workflow.command(
                cap["host"], "capture_hash", "sha256sum " + shlex.quote(cap["path"]),
                sudo=True, timeout=10)
            require(rc == 0 and re.fullmatch(r"[0-9a-f]{64}", out.split()[0]),
                    "capture hash missing")
            target = evidence / f"{cap['host'].replace('.', '-')}-{cap['interface']}-{Path(cap['path']).name}"
            with workflow.clients[cap["host"]].open_sftp() as sftp, target.open("xb") as dst:
                with sftp.open(cap["path"], "rb") as src:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        dst.write(chunk)
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            require(digest == out.split()[0], "downloaded pcap hash mismatch")
            cap["local_path"] = str(target.resolve())
            cap["sha256"] = digest
        except Exception as exc:
            cap["capture_error"] = type(exc).__name__


def curl_trial(workflow, evidence: Path, mode: str, trial: int) -> dict:
    curl = ("/home/netpro/netpro-thesis/http3/prefix/bin/curl --http3-only "
            "--noproxy '*' --interface 192.168.80.29 "
            "--resolve mysite.local:443:192.168.80.28 -k "
            "--connect-timeout 3 --max-time 6 "
            "-o /dev/null -w 'HTTP %{http_code} VERSION %{http_version} "
            "TOTAL %{time_total}\\n' https://mysite.local/; rc=$?; "
            "echo CURL_EXIT=$rc")
    out = command(workflow, CLIENT, f"{mode}_{trial}",
                  "set +e; date -u +CLIENT_START=%s.%N; " + curl +
                  "; date -u +CLIENT_END=%s.%N", timeout=12)
    match = re.search(r"HTTP (\d{3}) VERSION ([^ ]+) TOTAL ([0-9.]+).*CURL_EXIT=(\d+)",
                      out, re.S)
    if not match:
        raise CheckFailure(f"curl trial output was not parseable in {mode}")
    start_match = re.search(r"CLIENT_START=([^\r\n]+)", out)
    end_match = re.search(r"CLIENT_END=([^\r\n]+)", out)
    row = {"phase": mode, "trial": trial,
           "client_start_local": start_match.group(1) if start_match else None,
           "client_end_local": end_match.group(1) if end_match else None,
           "http_code": int(match.group(1)),
           "http_version": match.group(2), "time_total_seconds": float(match.group(3)),
           "curl_exit": int(match.group(4)), "client_output": out[-1000:]}
    (evidence / "curl-results.jsonl").open("a", encoding="utf-8").write(
        json.dumps(row, separators=(",", ":")) + "\n")
    return row


def load_candidate_manifest() -> tuple[str, str, str]:
    """Select the newest PS build whose recorded source matches local source."""
    source = STACK / "inline-policy" / "policyServer.c"
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    builds = sorted((STACK / "inline-policy" / "evidence").glob("build-*/result.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    for path in builds:
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            source_hashes = row.get("source_sha256", {})
            if row.get("exit_code") != 0 or source_hashes.get("policyServer.c") != source_sha:
                continue
            if any(not (STACK / "inline-policy" / name).is_file() or
                   hashlib.sha256((STACK / "inline-policy" / name).read_bytes()).hexdigest() != digest
                   for name, digest in source_hashes.items()):
                continue
            remote_root = row.get("remote_root")
            binary_sha_path = path.parent / "binary.sha256"
            sha_text = binary_sha_path.read_text(encoding="ascii")
            sha = sha_text.split()[0]
            if not re.fullmatch(r"[0-9a-f]{64}", sha):
                continue
            return str(remote_root), sha, str(path)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    raise CheckFailure("no successful inline-policy build matches current policyServer.c")


def launch_async_curl(workflow):
    """Start one bounded HTTP/3-only curl without blocking the verdict sender."""
    command_text = (
        "date -u +CLIENT_START=%s.%N; "
        "/home/netpro/netpro-thesis/http3/prefix/bin/curl --http3-only "
        "--noproxy '*' --interface 192.168.80.29 "
        "--resolve mysite.local:443:192.168.80.28 -k "
        "--connect-timeout 3 --max-time 6 "
        "-o /dev/null -w 'HTTP %{http_code} VERSION %{http_version} "
        "TOTAL %{time_total}\\n' https://mysite.local/; rc=$?; "
        "echo CURL_EXIT=$rc; date -u +CLIENT_END=%s.%N"
    )
    _, stdout, stderr = workflow.clients[CLIENT].exec_command(command_text, timeout=10)
    return stdout, stderr


def collect_async(stdout, timeout: float = 8.0) -> str:
    deadline = time.monotonic() + timeout
    chunks = []
    while time.monotonic() < deadline:
        if stdout.channel.recv_ready():
            chunks.append(stdout.channel.recv(4096).decode("utf-8", "replace"))
        if stdout.channel.exit_status_ready() and not stdout.channel.recv_ready():
            break
        time.sleep(0.02)
    if not stdout.channel.exit_status_ready():
        stdout.channel.close()
        raise CheckFailure("asynchronous HTTP/3 request exceeded its bounded timeout")
    while stdout.channel.recv_ready():
        chunks.append(stdout.channel.recv(4096).decode("utf-8", "replace"))
    return "".join(chunks)


def manual_mechanism_trial(workflow, evidence: Path, gate_unit: str, key_path: str,
                           session_hex: str, sequence: int, decision: str,
                           helper_paths: list[str]) -> dict:
    """Answer the exact Initial observed by the gate with a synthetic NPV1 record."""
    cursor = caddy_cursor(workflow)
    previous = gate_events(workflow, gate_unit)
    known = {(e.get("sport"), e.get("payload_sha256"), e.get("payload_len"))
             for e in previous if e.get("event") == "queued_initial"}
    stdout, _ = launch_async_curl(workflow)
    deadline = time.monotonic() + 0.32
    queued = None
    while time.monotonic() < deadline:
        log = command(workflow, GATE, "manual_gate_wait_event",
                      "journalctl -u " + shlex.quote(gate_unit + ".service") +
                      " -n 40 -o cat --no-pager", sudo=True, timeout=3)
        for line in log.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") != "queued_initial":
                continue
            key = (event.get("sport"), event.get("payload_sha256"), event.get("payload_len"))
            if key not in known and event.get("src") == CLIENT_ADDR and event.get("dst") == ORIGIN:
                queued = event
                break
        if queued:
            break
        time.sleep(0.015)
    require(queued is not None,
            "gate did not log queued Initial before 500ms manual-verdict deadline")
    helper = STACK / "inline-gate" / "send_manual_verdict.py"
    remote_helper = f"/home/netpro/incoming/send-manual-verdict-{sequence}-{uuid4().hex[:8]}.py"
    helper_paths.append(remote_helper)
    with workflow.clients[POLICY].open_sftp() as sftp:
        with helper.open("rb") as src, sftp.open(remote_helper, "wx") as dst:
            dst.write(src.read())
        sftp.chmod(remote_helper, 0o700)
    send = ("/usr/bin/python3 " + shlex.quote(remote_helper) + " " + decision +
            " --sport " + str(int(queued["sport"])) +
            " --payload-len " + str(int(queued["payload_len"])) +
            " --payload-sha256 " + shlex.quote(queued["payload_sha256"]) +
            " --sequence " + str(sequence) + " --key-file " + shlex.quote(key_path) +
            " --session " + shlex.quote(session_hex))
    send_output = command(workflow, POLICY, "synthetic_manual_verdict", send, timeout=4)
    response = collect_async(stdout)
    observed = gate_events(workflow, gate_unit, evidence, "manual-" + decision)
    exact_events = [event for event in observed
                    if event.get("event") == "verdict"
                    and event.get("sport") == queued["sport"]
                    and event.get("payload_sha256") == queued["payload_sha256"]
                    and event.get("payload_len") == queued["payload_len"]]
    require(any(event.get("action") == ("allow" if decision == "allow" else "drop")
                and (decision == "allow" or event.get("reason") == "policy_deny")
                for event in exact_events),
            "manual verdict was not accepted for the exact queued Initial; timeout is not a verdict")
    require("manual_mechanism_verdict_sent" in send_output,
            "synthetic verdict sender did not confirm a send")
    match = re.search(r"HTTP (\d{3}) VERSION ([^ ]+) TOTAL ([0-9.]+).*CURL_EXIT=(\d+)",
                      response, re.S)
    require(match is not None, "manual queue trial curl output was not parseable")
    row = {"decision": decision, "synthetic_queue_mechanism_only": True,
           "sport": queued["sport"], "payload_len": queued["payload_len"],
           "payload_sha256": queued["payload_sha256"], "http_code": int(match.group(1)),
           "http_version": match.group(2), "time_total_seconds": float(match.group(3)),
           "curl_exit": int(match.group(4)), "client_output": response[-1000:],
           "sender_path": remote_helper}
    if decision == "allow":
        require(row["curl_exit"] == 0 and row["http_code"] == 200 and row["http_version"] == "3",
                "manual ALLOW did not release the queued HTTP/3 request")
    else:
        require(row["curl_exit"] != 0 and row["http_code"] == 0,
                "manual DENY did not prevent HTTP/3 completion")
    row["caddy_access_records"] = len(caddy_access_since(workflow, cursor))
    if decision == "deny":
        require(row["caddy_access_records"] == 0,
                "manual DENY request appeared in Caddy access log")
    with (evidence / "manual-mechanism.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, separators=(",", ":")) + "\n")
    return row


def gate_events(workflow, unit: str, evidence: Path | None = None,
                label: str = "snapshot") -> list[dict]:
    text = ("sudo -S -p '' -- sh -c " + shlex.quote(
        "journalctl -u " + shlex.quote(unit + ".service") +
        " -n 5000 -o cat --no-pager"))
    stdin, stdout, stderr = workflow.clients[GATE].exec_command(text, timeout=15)
    stdin.write(PASSWORD + "\n")
    stdin.flush()
    stdin.close()
    output = stdout.read().decode("utf-8", "replace")
    error = stderr.read().decode("utf-8", "replace")
    if stdout.channel.recv_exit_status() != 0:
        raise CheckFailure("could not read bounded gate journal: " + error[-300:])
    if evidence is not None:
        with (evidence / f"gate-{unit}-{label}.jsonl").open("x", encoding="utf-8") as stream:
            stream.write(output)
    events = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
            if isinstance(item, dict) and item.get("event") in ("verdict", "queued_initial"):
                events.append(item)
        except json.JSONDecodeError:
            continue
    return events


def summarize(values: list[float]) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {"samples": 0, "median": None, "p95": None}
    return {"samples": len(ordered), "median": ordered[(len(ordered) - 1) // 2],
            "p95": ordered[min(len(ordered) - 1, int((len(ordered) - 1) * 0.95))]}


def verdict_counts(events: list[dict]) -> dict[str, int]:
    return {
        "policy_deny": sum(1 for ev in events if ev.get("reason") == "policy_deny"),
        "policy_unsupported": sum(1 for ev in events if ev.get("reason") == "policy_unsupported"),
        "timeout": sum(1 for ev in events if ev.get("event") == "verdict" and ev.get("action") == "timeout"),
        "allow": sum(1 for ev in events if ev.get("event") == "verdict" and ev.get("action") == "allow"),
    }


def run_benchmark_sweep(workflow, evidence: Path, phase: str, helper_path: str,
                        gate_unit: str | None = None) -> dict:
    """Run bounded latency samples; this is not a load/stress benchmark."""
    python_path = command(workflow, CLIENT, "benchmark_python", "command -v python3")
    require(python_path.startswith("/usr/") and "\n" not in python_path,
            "unexpected client python3 path")
    summaries = []
    for concurrency in (1, 4, 8, 16):
        before = verdict_counts(gate_events(workflow, gate_unit, evidence,
                                             f"bench-{phase}-c{concurrency}-before")) if gate_unit else None
        cursor = caddy_cursor(workflow)
        invocation = (shlex.quote(python_path) + " " + shlex.quote(helper_path) +
                      " --requests 20 --concurrency " + str(concurrency) + " --expect allow")
        raw = command(workflow, CLIENT, f"bench_{phase}_c{concurrency}", invocation,
                      timeout=90)
        try:
            report = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CheckFailure(f"benchmark {phase}/c{concurrency} returned invalid JSON") from exc
        require(report.get("attempted") == 20 and report.get("requests") == 20 and
                report.get("concurrency") == concurrency and report.get("expectation_met") is True and
                report.get("expectation_failures") == 0,
                f"benchmark {phase}/c{concurrency} did not meet its HTTP/3 allow expectation")
        rows = report.get("results")
        require(isinstance(rows, list) and len(rows) == 20 and all(
            row.get("curl_code") == 0 and row.get("http_status") == "200" and
            str(row.get("http_version", "")).startswith("3") and
            row.get("runner_timeout") is False for row in rows),
            f"benchmark {phase}/c{concurrency} has a non-HTTP/3-200 request")
        access = caddy_access_since(workflow, cursor)
        require(len(access) >= 20,
                f"benchmark {phase}/c{concurrency} has fewer than 20 Caddy access records")
        report["caddy_access_records"] = len(access)
        if gate_unit:
            after_events = gate_events(workflow, gate_unit, evidence,
                                       f"bench-{phase}-c{concurrency}-after")
            after = verdict_counts(after_events)
            delta = {key: after[key] - before[key] for key in after}
            require(delta["allow"] >= 20 and delta["policy_deny"] == 0 and
                    delta["policy_unsupported"] == 0 and delta["timeout"] == 0,
                    f"benchmark {phase}/c{concurrency} gate counts do not show 20 clean allow verdicts")
            all_allow_events = [ev for ev in after_events
                                if ev.get("event") == "verdict" and ev.get("action") == "allow"]
            new_allow = all_allow_events[before["allow"]:]
            report["gate_verdict_delta"] = delta
            report["gate_wait_ms"] = summarize([float(ev["waited_ms"]) for ev in new_allow
                                                 if isinstance(ev.get("waited_ms"), (int, float))])
        full_path = evidence / f"benchmark-{phase}-c{concurrency}.json"
        full_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        summary = {key: value for key, value in report.items() if key != "results"}
        summary["classification"] = "bounded latency sample; not stress/load evidence"
        summary["detailed_results_file"] = str(full_path.resolve())
        summaries.append(summary)
    return {"name": f"benchmark_{phase}",
            "classification": "bounded latency sample; not stress/load evidence",
            "requests_per_concurrency": 20,
            "concurrency_levels": [1, 4, 8, 16], "runs": summaries}


def caddy_cursor(workflow) -> str:
    output = command(workflow, GATEWAY, "caddy_cursor_before_phase",
                     "journalctl -u caddy.service -n 1 --show-cursor --no-pager", timeout=12)
    match = re.search(r"-- cursor: (\S+)", output)
    if not match:
        raise CheckFailure("Caddy journal cursor unavailable; cannot bound origin request count")
    return match.group(1)


def caddy_access_since(workflow, cursor: str) -> list[str]:
    output = command(workflow, GATEWAY, "caddy_access_after_phase",
                     "journalctl -u caddy.service --after-cursor=" + shlex.quote(cursor) +
                     " --no-pager -o cat", timeout=12)
    return [line for line in output.splitlines()
            if '"logger":"http.log.access"' in line and '"host":"mysite.local"' in line]


def add_exact_policy(workflow, domain: str, run_id: str, phase: str) -> str:
    ab.TEST_DOMAIN = domain
    ab.TEST_IP = ORIGIN
    workflow.test_name = f"inline-quic-{run_id}-{phase}"
    workflow.policy_id = None
    workflow.policy_deleted = False
    workflow.document["test_name"] = workflow.test_name
    return workflow.create_policy()


def verify_policy_baseline(workflow) -> None:
    api_ids, _ = workflow.policy_api_ids()
    sql_ids = {str(row["id"]) for row in workflow.sqlite("SELECT id FROM policies ORDER BY id;")}
    require(api_ids == set(workflow.document["baseline_api_policy_ids"]),
            "Backend API IDs did not return to exact pre-run baseline")
    require(sql_ids == set(workflow.document["baseline_sqlite_policy_ids"]),
            "Policy SQLite IDs did not return to exact pre-run baseline")


def ensure_domain_absent(workflow, domain: str) -> None:
    _, rows = workflow.policy_api_ids()
    require(not any(row.get("domain") == domain for row in rows),
            "domain already has a policy; refusing to test: " + domain)
    rows = workflow.sqlite("SELECT id, domain, ip_address FROM policies WHERE domain = ?",
                           (domain,))
    require(not rows, "domain already exists in Policy SQLite; refusing test")


def run_active(args) -> int:
    evidence = args.evidence
    evidence.mkdir(parents=True, exist_ok=False)
    clients: dict[str, object] = {}
    workflow = None
    rollouts: list[CandidateRollout] = []
    captures: list[dict] = []
    key_hex = secrets.token_hex(32)
    manual_session = secrets.token_hex(16)
    policy_session = secrets.token_hex(16)
    run_id = uuid4().hex[:12]
    key_paths = {POLICY: f"/home/netpro/incoming/inline-verdict-{run_id}.key",
                 GATE: f"/home/netpro/incoming/inline-verdict-{run_id}.key"}
    gate_unit = "netpro-inline-gate-" + run_id + "-manual"
    active_gate_unit = "netpro-inline-gate-" + run_id + "-policy"
    gate_root = None
    gate_started = False
    active_gate_root = None
    active_gate_started = False
    queue_staged = False
    benchmark_helper_path = None
    temporary_policy = False
    manual_helpers: list[str] = []
    stats_path = f"/home/netpro/incoming/inline-stats-{run_id}.json"
    result = {"workflow": "inline-quic-functional", "run_id": run_id,
              "trials_per_phase": args.trials, "candidate_hashes": {
                  "policy_original": EXPECTED_ORIGINALS["policy"],
                  "policy_inline_gate_only": None,
                  "npb_original": EXPECTED_ORIGINALS["npb"],
                  "npb_quic_candidate": NPB_CANDIDATE_SHA},
              "secret_values_recorded": False, "phases": [], "cleanup": [],
              "timing_note": "Curl time_total and client-local timestamps are recorded; no cross-host clock ordering is inferred."}
    try:
        for ip in (POLICY, NPB, BACKEND, GATE, GATEWAY, CLIENT):
            clients[ip], _ = connect_verified(ip, "netpro", PASSWORD, KNOWN_HOSTS)
        workflow = ab.ActiveBaseline(PASSWORD, evidence, KNOWN_HOSTS)
        workflow.clients = clients
        workflow.baseline()
        ensure_domain_absent(workflow, "mysite.local")
        ensure_domain_absent(workflow, "unrelated-domain.test")

        policy_root, candidate_sha, manifest_path = load_candidate_manifest()
        policy_binary = policy_root + "/policyServer-inline"
        result["candidate_hashes"]["policy_inline_gate_only"] = candidate_sha
        result["policy_build_manifest"] = manifest_path
        npb_root = "/home/netpro/incoming/npb-quic-candidate.jsL9uV"
        npb_binary = npb_root + "/packetBroker-quic-candidate"
        for host, path, expected in ((POLICY, policy_binary, candidate_sha),
                                     (NPB, npb_binary, NPB_CANDIDATE_SHA)):
            observed = command(workflow, host, "candidate_binary_hash",
                               "sha256sum " + shlex.quote(path))
            require(observed.split()[0] == expected,
                    "candidate binary hash mismatch; refusing rollout")

        # The first Policy Server candidate run has no verdict key configured.
        # This retains the recovered decision path while measuring candidate
        # latency with no queue and makes later manual verdicts unambiguous.
        disabled_env = {"NETPRO_SNMP_ENABLE": "0", "NETPRO_INLINE_CLOSE_ENABLE": "0"}
        for host, hostname, unit, binary, sha, env in (
            (NPB, "npb-vm", "netpro-npb", npb_binary, NPB_CANDIDATE_SHA, {}),
            (POLICY, "policy-server-vm", "netpro-policy", policy_binary,
             candidate_sha, disabled_env),
        ):
            rollout = CandidateRollout(workflow.clients[host], hostname, unit,
                                       binary, sha, EXPECTED_ORIGINALS[
                                           "policy" if host == POLICY else "npb"],
                                       evidence, env)
            rollouts.append(rollout)
            rollout.start()

        # Candidate/no-queue allow is the comparison condition. The gate starts
        # only after this phase, so no old verdict can remain pending/cached.
        pre_events_start = time.monotonic()
        baseline_rows = [curl_trial(workflow, evidence, "candidate_noqueue_allow", i + 1)
                         for i in range(args.trials)]
        require(all(r["curl_exit"] == 0 and r["http_code"] == 200 and
                    r["http_version"] == "3" for r in baseline_rows),
                "candidate/no-queue baseline did not produce only HTTP/3 200")
        result["phases"].append({"name": "candidate_noqueue_allow", "rows": baseline_rows,
                                  "controller_monotonic_seconds": pre_events_start})
        if args.benchmark:
            local_helper = STACK / "inline-gate" / "bench_http3.py"
            benchmark_helper_path = f"/home/netpro/incoming/inline-bench-{run_id}.py"
            with workflow.clients[CLIENT].open_sftp() as sftp:
                with local_helper.open("rb") as src, sftp.open(benchmark_helper_path, "wx") as dst:
                    dst.write(src.read())
                sftp.chmod(benchmark_helper_path, 0o700)
            result["phases"].append(run_benchmark_sweep(
                workflow, evidence, "candidate_noqueue_allow", benchmark_helper_path))

        # Readiness and captures precede the no-bypass nft queue hook.
        for host, path in key_paths.items():
            with workflow.clients[host].open_sftp() as sftp:
                upload_private(sftp, path, (key_hex + "\n").encode("ascii"))
        gate_root, gate_script = stage_gate(workflow, run_id + "-manual")
        gate_started = True
        start_gate(workflow, gate_unit, gate_script, key_paths[GATE], manual_session)
        filters = "udp port 443 and host " + CLIENT_ADDR + " and host " + ORIGIN
        for host, iface in ((GATE, "ens36"), (CLIENT, "ens37"), (GATEWAY, "ens37")):
            captures.append(start_capture(workflow, host, iface, run_id + "-manual", filters))
        time.sleep(0.5)
        queue_staged = True
        stage_queue(workflow, gate_root)

        manual_rows = [
            manual_mechanism_trial(workflow, evidence, gate_unit, key_paths[POLICY],
                                   manual_session, 1, "allow", manual_helpers),
            manual_mechanism_trial(workflow, evidence, gate_unit, key_paths[POLICY],
                                   manual_session, 2, "deny", manual_helpers),
        ]
        result["phases"].append({"name": "synthetic_queue_mechanism_only",
                                  "rows": [{k: v for k, v in row.items() if k != "sender_path"}
                                           for row in manual_rows],
                                  "claim": "matching manual NPV1 ALLOW releases one request; matching synthetic DENY drops one request; neither is a Policy Server decision"})
        if args.phase == "queue":
            result["passed"] = True
            raise QueuePhaseComplete()

        # Remove the mechanism-only hook before swapping Policy Server from
        # disabled publisher to the authenticated live publisher.
        if args.phase != "queue":
            command(workflow, GATE, "manual_queue_rollback",
                    "/bin/bash " + shlex.quote(gate_root + "/rollback-tap-rule.sh"),
                    sudo=True)
            queue_staged = False
            command(workflow, GATE, "manual_gate_stop",
                    "systemctl kill --signal=SIGINT " + shlex.quote(gate_unit + ".service"),
                    sudo=True, timeout=15)
            command(workflow, GATE, "manual_gate_timer_stop",
                    "systemctl stop " + shlex.quote(gate_unit + "-rollback.timer") +
                    " 2>/dev/null || true", sudo=True, timeout=10)
            gate_started = False
            stop_captures(workflow, captures, evidence)
            result["captures"] = result.get("captures", []) + captures
            captures = []

        if args.phase != "queue":
            policy_disabled_rollout = next(r for r in rollouts if r.unit == "netpro-policy" and r.started)
            policy_disabled_rollout.stop()
        policy_env = {
            "NETPRO_SNMP_ENABLE": "0",
            "NETPRO_INLINE_CLOSE_ENABLE": "0",
            "NETPRO_VERDICT_HMAC_KEY_FILE": key_paths[POLICY],
            "NETPRO_VERDICT_SESSION_ID": policy_session,
            "NETPRO_VERDICT_BIND_IPV4": POLICY,
            "NETPRO_VERDICT_PEER_IPV4": GATE,
            "NETPRO_REPLICATION_STATS_PATH": stats_path,
        }
        if args.phase != "queue":
          active_ps_rollout = CandidateRollout(
            workflow.clients[POLICY], "policy-server-vm", "netpro-policy",
            policy_binary, candidate_sha, EXPECTED_ORIGINALS["policy"], evidence, policy_env)
          rollouts.append(active_ps_rollout)
          active_ps_rollout.start()
        active_gate_root, active_gate_script = stage_gate(workflow, run_id + "-policy")
        active_gate_started = True
        start_gate(workflow, active_gate_unit, active_gate_script,
                   key_paths[GATE], policy_session)
        for host, iface in ((GATE, "ens36"), (CLIENT, "ens37"), (GATEWAY, "ens37")):
            captures.append(start_capture(workflow, host, iface, run_id + "-policy", filters))
        time.sleep(0.5)
        queue_staged = True
        stage_queue(workflow, active_gate_root)

        def run_phase(name: str, expect: str) -> None:
            before_events = gate_events(workflow, active_gate_unit, evidence, name + "-before")
            before_counts = {
                "policy_deny": sum(1 for ev in before_events if ev.get("reason") == "policy_deny"),
                "policy_unsupported": sum(1 for ev in before_events if ev.get("reason") == "policy_unsupported"),
                "timeout": sum(1 for ev in before_events if ev.get("event") == "verdict" and ev.get("action") == "timeout"),
                "allow": sum(1 for ev in before_events if ev.get("event") == "verdict" and ev.get("action") == "allow"),
            }
            cursor = caddy_cursor(workflow)
            rows = [curl_trial(workflow, evidence, name, i + 1)
                    for i in range(args.trials)]
            time.sleep(0.5)
            after_events = gate_events(workflow, active_gate_unit, evidence, name + "-after")
            after_counts = {
                "policy_deny": sum(1 for ev in after_events if ev.get("reason") == "policy_deny"),
                "policy_unsupported": sum(1 for ev in after_events if ev.get("reason") == "policy_unsupported"),
                "timeout": sum(1 for ev in after_events if ev.get("event") == "verdict" and ev.get("action") == "timeout"),
                "allow": sum(1 for ev in after_events if ev.get("event") == "verdict" and ev.get("action") == "allow"),
            }
            origin_access = caddy_access_since(workflow, cursor)
            if expect == "allow":
                valid = all(r["curl_exit"] == 0 and r["http_code"] == 200 and
                            r["http_version"] == "3" for r in rows)
                require(valid, f"{name}: not every request completed HTTP/3 200")
                require(after_counts["policy_deny"] == before_counts["policy_deny"],
                        f"{name}: gate recorded a policy deny during allow phase")
                require(after_counts["allow"] - before_counts["allow"] >= args.trials,
                        f"{name}: too few explicit ALLOW verdicts reached the gate")
                require(after_counts["timeout"] == before_counts["timeout"],
                        f"{name}: gate timed out during an expected allow phase")
                require(after_counts["policy_unsupported"] == before_counts["policy_unsupported"],
                        f"{name}: gate reported unsupported traffic during an allow phase")
                require(len(origin_access) >= args.trials,
                        f"{name}: fewer than expected Caddy requests completed")
            else:
                valid = all(r["curl_exit"] != 0 and r["http_code"] == 0
                            for r in rows)
                require(valid, f"{name}: a denied request completed or did not fail")
                require_deny_count = after_counts["policy_deny"] - before_counts["policy_deny"]
                require(require_deny_count >= args.trials,
                        f"{name}: expected policy_deny gate verdicts; observed {require_deny_count}")
                require(after_counts["timeout"] == before_counts["timeout"],
                        f"{name}: gate timeouts occurred; timeout is not a policy deny")
                require(after_counts["policy_unsupported"] == before_counts["policy_unsupported"],
                        f"{name}: unsupported decisions occurred; not a policy deny")
                require(len(origin_access) == 0,
                        f"{name}: Caddy recorded denied-domain requests")
            phase = {"name": name, "expected": expect, "rows": rows,
                     "gate_reason_counts_before": before_counts,
                     "gate_reason_counts_after": after_counts,
                     "caddy_access_records": len(origin_access),
                     "caddy_access_tail": origin_access[-args.trials:]}
            result["phases"].append(phase)
            workflow.event("inline_functional_phase", phase_name=name, expected=expect,
                           gate_counts=after_counts, caddy_access=len(origin_access))

        run_phase("candidate_queued_allow", "allow")
        if args.benchmark:
            result["phases"].append(run_benchmark_sweep(
                workflow, evidence, "candidate_queued_allow", benchmark_helper_path,
                active_gate_unit))

        add_exact_policy(workflow, "unrelated-domain.test", run_id, "same-ip-control")
        temporary_policy = True
        run_phase("unrelated-domain_same-ip_control", "allow")
        workflow.delete_policy_exactly()
        temporary_policy = False
        verify_policy_baseline(workflow)

        add_exact_policy(workflow, "mysite.local", run_id, "mysite-deny")
        temporary_policy = True
        run_phase("mysite.local_policy_deny", "deny")
        workflow.delete_policy_exactly()
        temporary_policy = False
        verify_policy_baseline(workflow)
        run_phase("allow_after_delete", "allow")
        result["passed"] = True
    except QueuePhaseComplete:
        pass
    except Exception as exc:
        result["passed"] = False
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)[:500]
        print("STOP:", type(exc).__name__, "(inspect bounded evidence; cleanup will run)",
              flush=True)
    finally:
        # Remove only this run's exact policy, unique queue table, gate unit,
        # captures, and candidate overrides; preserve any valid existing DB.
        if workflow is not None and queue_staged:
            try:
                roots = [root for root in (active_gate_root, gate_root) if root]
                require(bool(roots), "no staged gate rollback script available")
                try:
                    nft_snapshot = command(workflow, GATE, "queue_counters_before_rollback",
                                           "nft -a list table bridge netpro_quic_gate",
                                           sudo=True, timeout=10)
                    (evidence / "nft-queue-before-rollback.txt").write_text(
                        nft_snapshot + "\n", encoding="utf-8")
                except Exception as exc:
                    result["cleanup"].append("queue counter snapshot unavailable: " + str(exc)[:200])
                command(workflow, GATE, "queue_rollback",
                        "/bin/bash " + shlex.quote(roots[-1] + "/rollback-tap-rule.sh"), sudo=True)
                result["cleanup"].append("owned bridge nft table and rollback timer removed")
            except Exception as exc:
                result["cleanup"].append("queue rollback needs operator review: " + str(exc)[:250])
        if workflow is not None:
            for unit, started in ((active_gate_unit, active_gate_started), (gate_unit, gate_started)):
                if started:
                    try:
                        command(workflow, GATE, "gate_stop_" + unit.rsplit("-", 1)[-1],
                                "systemctl kill --signal=SIGINT " + shlex.quote(unit + ".service") +
                                " 2>/dev/null || systemctl stop " + shlex.quote(unit + ".service"),
                                sudo=True, timeout=15)
                        command(workflow, GATE, "gate_timer_stop_" + unit.rsplit("-", 1)[-1],
                                "systemctl stop " + shlex.quote(unit + "-rollback.timer") +
                                " 2>/dev/null || true", sudo=True, timeout=10)
                        result["cleanup"].append(unit + " stopped; summary journal retained")
                        journal = gate_events(workflow, unit, evidence, "final")
                        waits = [float(ev["waited_ms"]) for ev in journal
                                 if ev.get("event") == "verdict" and isinstance(ev.get("waited_ms"), (int, float))]
                        result.setdefault("gate_wait_ms", {})[unit] = summarize(waits)
                    except Exception as exc:
                        result["cleanup"].append("gate cleanup needs operator review: " + str(exc)[:250])
        if captures and workflow is not None:
            stop_captures(workflow, captures, evidence)
            result["captures"] = result.get("captures", []) + captures
        if workflow is not None and (temporary_policy or workflow.policy_id is not None):
            try:
                workflow.delete_policy_exactly()
                verify_policy_baseline(workflow)
                result["cleanup"].append("temporary policy removed; baseline IDs verified")
            except Exception as exc:
                result["cleanup"].append("policy cleanup needs operator review: " + str(exc)[:250])
        if workflow is not None:
            for rollout in reversed(rollouts):
                try:
                    rollout.stop()
                    result["cleanup"].append(rollout.unit + " original restored")
                except Exception as exc:
                    result["cleanup"].append(rollout.unit + " rollback needs operator review: " + str(exc)[:250])
            if stats_path:
                try:
                    stats_local = evidence / "policy-publisher-stats.json"
                    with workflow.clients[POLICY].open_sftp() as sftp, stats_local.open("xb") as dst:
                        with sftp.open(stats_path, "rb") as src:
                            dst.write(src.read(1024 * 1024))
                    command(workflow, POLICY, "stats_file_remove",
                            "rm -f -- " + shlex.quote(stats_path), sudo=True, timeout=10)
                except FileNotFoundError:
                    pass
                except Exception as exc:
                    result["cleanup"].append("publisher stats retrieval needs operator review: " + str(exc)[:250])
            for host, path in key_paths.items():
                try:
                    command(workflow, host, "remove_run_key_file",
                            "rm -f -- " + shlex.quote(path) + " && test ! -e " + shlex.quote(path),
                            sudo=True, timeout=10)
                except Exception:
                    result["cleanup"].append("run key removal needs operator review on " + host)
            for path in manual_helpers:
                try:
                    command(workflow, POLICY, "remove_manual_verdict_helper",
                            "rm -f -- " + shlex.quote(path) + " && test ! -e " + shlex.quote(path),
                            sudo=False, timeout=10)
                except Exception as exc:
                    result["cleanup"].append("manual helper removal needs operator review: " + str(exc)[:200])
            if benchmark_helper_path:
                try:
                    command(workflow, CLIENT, "remove_benchmark_helper",
                            "rm -f -- " + shlex.quote(benchmark_helper_path) +
                            " && test ! -e " + shlex.quote(benchmark_helper_path),
                            sudo=False, timeout=10)
                except Exception as exc:
                    result["cleanup"].append("benchmark helper removal needs operator review: " + str(exc)[:200])
        result["candidate_rollouts"] = [{"unit": r.unit, "candidate_started": r.started,
                                         "original_sha256": r.original_sha}
                                        for r in rollouts]
        result["secret_files_removed"] = not any("key removal needs operator review" in x for x in result["cleanup"])
        result["passed"] = bool(result.get("passed")) and not any("needs operator review" in x for x in result["cleanup"])
        result_path = evidence / "inline-summary.json"
        result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        if workflow is not None:
            workflow.save()
        for client in clients.values():
            client.close()
    return 0 if result.get("passed") else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("preflight", "queue", "functional", "plan"),
                        default="preflight")
    parser.add_argument("--evidence", type=Path,
                        default=STACK / "evidence" / "inline-validation")
    parser.add_argument("--trials", type=int, choices=(5, 20), default=5,
                        help="use 5 for the reviewed shakeout, then 20 for each accepted phase")
    parser.add_argument("--benchmark", action="store_true",
                        help="add bounded 20-request HTTP/3 latency samples at concurrency 1/4/8/16 before and after queueing")
    parser.add_argument("--execute-reviewed", action="store_true",
                        help="explicitly activate the guarded lab workflow after parent review")
    args = parser.parse_args()
    if args.phase == "plan":
        print("No action performed. Read README.md for staged queue and functional protocol.")
        return 0
    global PASSWORD
    PASSWORD = os.environ.get("NETPRO_LAB_PASSWORD") or getpass.getpass(
        "Lab SSH/sudo password (kept in memory only): ")
    if not PASSWORD:
        print("STOP: empty password; no connection attempted.")
        return 2
    if not KNOWN_HOSTS.is_file():
        print("STOP: trusted known_hosts file is missing; no connection attempted.")
        return 2
    if args.phase == "preflight":
        if args.execute_reviewed or args.benchmark:
            print("STOP: --execute-reviewed and --benchmark are valid only for queue or functional phases.")
            return 2
        return run_preflight(args.evidence)
    if args.benchmark and args.phase != "functional":
        print("STOP: --benchmark is only supported with --phase functional.")
        return 2
    if not args.execute_reviewed:
        print("STOP: queue and functional phases require --execute-reviewed after parent review.")
        return 3
    return run_active(args)


if __name__ == "__main__":
    raise SystemExit(main())
