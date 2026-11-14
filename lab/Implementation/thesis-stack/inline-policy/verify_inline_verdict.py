#!/usr/bin/env python3
"""One-shot loopback check of the C NPV1 publisher and Python verification."""
import hashlib
import hmac
import importlib.util
import os
import secrets
import socket
import struct
import sys
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WIRE_LEN = 134
SIGNED_LEN = 102

spec = importlib.util.spec_from_file_location("gate", Path(__file__).with_name("gate.py"))
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify_inline_verdict.py TEST_BINARY CURL_INITIAL")
    binary = str(Path(sys.argv[1]).resolve())
    fixture = Path(sys.argv[2]).read_bytes()
    raw_ip = bytearray(20 + 8 + len(fixture))
    raw_ip[0] = 0x45
    struct.pack_into("!H", raw_ip, 2, len(raw_ip))
    raw_ip[8] = 64
    raw_ip[9] = 17
    raw_ip[12:16] = socket.inet_aton("192.168.80.29")
    raw_ip[16:20] = socket.inet_aton("192.168.80.28")
    struct.pack_into("!HHH", raw_ip, 20, 49153, 443, 8 + len(fixture))
    raw_ip[28:] = fixture
    packet_key, parsed_payload = gate.packet_key(bytes(raw_ip))
    check(parsed_payload == fixture, "gate parser did not extract fixture payload")
    key = secrets.token_bytes(32)
    session = secrets.token_bytes(16)
    with tempfile.TemporaryDirectory(prefix="npv1-loopback-") as temp_name:
        temp = Path(temp_name)
        key_path = temp / "key.hex"
        key_path.write_text(key.hex(), encoding="ascii")
        key_path.chmod(0o600)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 19191))
        sock.settimeout(4)
        env = os.environ.copy()
        for name in ("NETPRO_VERDICT_HMAC_KEY", "NETPRO_VERDICT_HMAC_KEY_FILE",
                     "NETPRO_VERDICT_SESSION_ID", "NETPRO_VERDICT_BIND_IPV4",
                     "NETPRO_VERDICT_PEER_IPV4"):
            env.pop(name, None)
        env.update({
            "NETPRO_VERDICT_HMAC_KEY_FILE": str(key_path),
            "NETPRO_VERDICT_SESSION_ID": session.hex(),
            "NETPRO_VERDICT_BIND_IPV4": "127.0.0.1",
            "NETPRO_VERDICT_PEER_IPV4": "127.0.0.1",
        })
        run = subprocess.run([binary, str(Path(sys.argv[2]).resolve())],
                             env=env, capture_output=True, text=True, timeout=10)
        check(run.returncode == 0, "publisher run failed: " + run.stderr[-1000:])
        decisions = []
        for expected_seq in (1, 2, 3):
            msg, peer = sock.recvfrom(512)
            check(peer[0] == "127.0.0.1", "unexpected loopback sender")
            check(len(msg) == WIRE_LEN, "wrong wire length")
            check(msg[:4] == b"NPV1" and msg[4:6] == b"\x01\x01",
                  "wrong magic/version/type")
            check(msg[7] == 0 and msg[8:24] == session, "reserved/session mismatch")
            seq = int.from_bytes(msg[24:32], "big")
            check(seq == expected_seq, "publication sequence mismatch")
            check(msg[32:40] == b"\x00" * 8, "generation must remain reserved zero")
            issued = int.from_bytes(msg[40:48], "big")
            expires = int.from_bytes(msg[48:56], "big")
            now_ms = int(time.time() * 1000)
            check(expires - issued == 2000, "wrong verdict expiry interval")
            check(issued - 10000 <= now_ms <= expires + 10000,
                  "invalid wall-clock timestamps")
            check(msg[56:64] == socket.inet_aton("192.168.80.29") +
                  socket.inet_aton("192.168.80.28"), "tuple IP mismatch")
            check(msg[64:68] == (49153).to_bytes(2, "big") +
                  (443).to_bytes(2, "big"), "tuple ports mismatch")
            check(int.from_bytes(msg[68:70], "big") == len(fixture),
                  "UDP payload length mismatch")
            check(msg[70:102] == hashlib.sha256(fixture).digest(),
                  "UDP payload hash mismatch")
            check(hmac.compare_digest(msg[102:], hmac.new(
                key, msg[:SIGNED_LEN], hashlib.sha256).digest()), "HMAC mismatch")
            parsed = gate.parse_verdict(msg, gate.PS_IP, key, session, now_ms)
            check(parsed.decision == expected_seq and parsed.sequence == expected_seq and
                  parsed.generation == 0, "gate parser result mismatch")
            check(gate._wire_key(msg) == packet_key, "gate packet key mismatch")
            try:
                gate.parse_verdict(msg, "127.0.0.1", key, session, now_ms)
                raise RuntimeError("gate accepted an untrusted sender")
            except ValueError as exc:
                check(str(exc) == "untrusted_sender", "unexpected source validation error")
            decisions.append(msg[6])
        check(decisions == [1, 2, 3], "decision values mismatch")
        sock.close()

        # Missing configuration and an over-permissive key file must stay disabled.
        disabled_env = env.copy()
        disabled_env.pop("NETPRO_VERDICT_HMAC_KEY_FILE", None)
        disabled_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        disabled_sock.bind(("127.0.0.1", 19191))
        disabled_sock.settimeout(0.2)
        disabled = subprocess.run([binary, str(Path(sys.argv[2]).resolve())],
                                  env=disabled_env, capture_output=True, text=True,
                                  timeout=10)
        check(disabled.returncode == 3 and "PUBLISHER_DISABLED publish=-1 sent=0 disabled=1" in
              disabled.stdout, "missing key did not disable publisher")
        try:
            disabled_sock.recvfrom(512)
            raise RuntimeError("disabled publisher unexpectedly sent a verdict")
        except socket.timeout:
            pass
        disabled_sock.close()
        permissive_key = temp / "bad-mode.hex"
        permissive_key.write_text(key.hex(), encoding="ascii")
        permissive_key.chmod(0o644)
        bad_env = env.copy()
        bad_env["NETPRO_VERDICT_HMAC_KEY_FILE"] = str(permissive_key)
        bad_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        bad_sock.bind(("127.0.0.1", 19191))
        bad_sock.settimeout(0.2)
        bad = subprocess.run([binary, str(Path(sys.argv[2]).resolve())],
                             env=bad_env, capture_output=True, text=True, timeout=10)
        check(bad.returncode == 3 and "PUBLISHER_DISABLED publish=-1 sent=0 disabled=1" in bad.stdout,
              "permissive key file did not disable publisher")
        try:
            bad_sock.recvfrom(512)
            raise RuntimeError("permissive-key publisher unexpectedly sent a verdict")
        except socket.timeout:
            pass
        bad_sock.close()
    print("NPV1_LOOPBACK=PASS messages=3 gate_parser=PASS decisions=ALLOW,DENY,UNSUPPORTED HMAC=PASS tuple/hash=PASS source_rejection=PASS missing-key=DISABLED key-mode=DISABLED")


if __name__ == "__main__":
    main()
