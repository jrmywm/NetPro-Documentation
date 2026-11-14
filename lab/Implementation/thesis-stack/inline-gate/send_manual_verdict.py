#!/usr/bin/env python3
"""Send a synthetic signed verdict for a queue-mechanism test only."""
import argparse
import hashlib
import hmac
import json
import os
import socket
import stat
import struct
import time

PS_IP, GATE_IP, GATE_PORT = "192.168.31.31", "192.168.31.38", 19191
CLIENT_IP, ORIGIN_IP, ORIGIN_PORT = "192.168.80.29", "192.168.80.28", 443
DECISIONS = {"allow": 1, "deny": 2, "unsupported": 3}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decision", choices=DECISIONS)
    parser.add_argument("--sport", type=int, required=True)
    parser.add_argument("--payload-len", type=int, required=True)
    parser.add_argument("--payload-sha256", required=True)
    parser.add_argument("--sequence", type=int, required=True)
    parser.add_argument("--key-file", default=os.environ.get("NETPRO_VERDICT_HMAC_KEY_FILE"))
    parser.add_argument("--session", default=os.environ.get("NETPRO_VERDICT_SESSION_ID"))
    parser.add_argument("--gate-ip", default=GATE_IP)
    args = parser.parse_args()
    if not args.key_file or not args.session:
        parser.error("set --key-file/--session or NETPRO_VERDICT_HMAC_KEY_FILE/NETPRO_VERDICT_SESSION_ID")
    if not 1 <= args.sport <= 65535 or not 1 <= args.payload_len <= 65507:
        parser.error("invalid UDP source port or payload length")
    try:
        digest, session = bytes.fromhex(args.payload_sha256), bytes.fromhex(args.session)
        mode = stat.S_IMODE(os.stat(args.key_file).st_mode)
        if mode & 0o077:
            parser.error("key file must be mode 0600")
        with open(args.key_file, "rb") as key_file:
            secret = bytes.fromhex(key_file.read().decode("ascii").strip())
    except (OSError, ValueError, UnicodeError) as exc:
        parser.error(f"invalid key/session/hash: {exc}")
    if len(secret) != 32 or len(session) != 16 or len(digest) != 32:
        parser.error("key/session/hash lengths must be 32/16/32 bytes")
    if args.sequence <= 0:
        parser.error("sequence must be positive")

    now_ms = int(time.time() * 1000)
    prefix = (b"NPV1" + bytes((1, 1, DECISIONS[args.decision], 0)) + session +
              struct.pack("!QQQQ", args.sequence, 0, now_ms, now_ms + 1500) +
              socket.inet_aton(CLIENT_IP) + socket.inet_aton(ORIGIN_IP) +
              struct.pack("!HHH", args.sport, ORIGIN_PORT, args.payload_len) + digest)
    record = prefix + hmac.new(secret, prefix, hashlib.sha256).digest()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((PS_IP, 0))
    sock.sendto(record, (args.gate_ip, GATE_PORT))
    sock.close()
    print(json.dumps({"event": "manual_mechanism_verdict_sent", "decision": args.decision,
                      "sequence": args.sequence, "sport": args.sport,
                      "payload_len": args.payload_len, "payload_sha256": digest.hex(),
                      "warning": "synthetic queue mechanism result; not a Policy Server policy decision"}))


if __name__ == "__main__":
    main()
