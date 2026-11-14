#!/usr/bin/env python3
"""Small fail-closed NFQUEUE gate for the scoped NetPro HTTP/3 lab flow."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import stat
import struct
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

MAGIC = b"NPV1"
VERSION, VERDICT_TYPE = 1, 1
ALLOW, DENY, UNSUPPORTED = 1, 2, 3
RECORD_LEN, SIGNED_LEN = 134, 102
PS_IP, GATE_IP, LISTEN_PORT = "192.168.31.31", "192.168.31.38", 19191
CLIENT_IP, ORIGIN_IP, ORIGIN_PORT = "192.168.80.29", "192.168.80.28", 443
DEFAULT_QUEUE, MAX_PENDING, MAX_CACHE = 4242, 256, 1024
MAX_VERDICT_TTL_MS, CLOCK_SKEW_MS, CACHE_TTL, FLOW_TTL = 2000, 100, 2.0, 30.0
DECISION_TIMEOUT = 0.5
REPLAY_WINDOW = 4096


@dataclass(frozen=True)
class PacketKey:
    src: str
    dst: str
    sport: int
    dport: int
    payload_len: int
    payload_hash: bytes


@dataclass(frozen=True)
class Verdict:
    decision: int
    sequence: int
    generation: int


def packet_key(raw: bytes) -> tuple[PacketKey, bytes] | None:
    """Return IPv4 UDP tuple and UDP payload; reject fragments and malformed data."""
    offset = _ipv4_offset(raw)
    if offset is None:
        return None
    raw = raw[offset:]
    if len(raw) < 20 or raw[0] >> 4 != 4:
        return None
    ihl = (raw[0] & 15) * 4
    total = struct.unpack_from("!H", raw, 2)[0]
    frag = struct.unpack_from("!H", raw, 6)[0]
    if ihl < 20 or total > len(raw) or total < ihl + 8 or raw[9] != 17 or frag & 0x3fff:
        return None
    sport, dport, udp_len = struct.unpack_from("!HHH", raw, ihl)
    if udp_len < 8 or ihl + udp_len > total:
        return None
    payload = raw[ihl + 8:ihl + udp_len]
    src = socket.inet_ntoa(raw[12:16])
    dst = socket.inet_ntoa(raw[16:20])
    key = PacketKey(src, dst, sport, dport, len(payload), hashlib.sha256(payload).digest())
    return key, payload


def parse_verdict(record: bytes, source_ip: str, key: bytes, session: bytes,
                  now_ms: int | None = None) -> Verdict:
    """Authenticate and validate the fixed 134-byte NPV1 verdict."""
    if len(record) != RECORD_LEN or record[:4] != MAGIC:
        raise ValueError("bad_record")
    if record[4] != VERSION or record[5] != VERDICT_TYPE or record[7] != 0:
        raise ValueError("unsupported_record")
    expected = hmac.new(key, record[:SIGNED_LEN], hashlib.sha256).digest()
    if not hmac.compare_digest(expected, record[SIGNED_LEN:]):
        raise ValueError("bad_hmac")
    decision = record[6]
    if decision not in (ALLOW, DENY, UNSUPPORTED):
        raise ValueError("bad_decision")
    if record[8:24] != session:
        raise ValueError("wrong_session")
    seq, generation, issued, expires = struct.unpack_from("!QQQQ", record, 24)
    if seq == 0 or generation != 0:
        raise ValueError("bad_sequence_or_generation")
    if expires <= issued or expires - issued > MAX_VERDICT_TTL_MS:
        raise ValueError("bad_verdict_lifetime")
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if issued > now_ms + CLOCK_SKEW_MS or expires < now_ms - CLOCK_SKEW_MS:
        raise ValueError("expired_verdict")
    if source_ip != PS_IP:
        raise ValueError("untrusted_sender")
    src = socket.inet_ntoa(record[56:60])
    dst = socket.inet_ntoa(record[60:64])
    sport, dport, payload_len = struct.unpack_from("!HHH", record, 64)
    digest = record[70:102]
    pkt_key = PacketKey(src, dst, sport, dport, payload_len, digest)
    if (pkt_key.src, pkt_key.dst, pkt_key.dport) != (CLIENT_IP, ORIGIN_IP, ORIGIN_PORT):
        raise ValueError("out_of_scope")
    return Verdict(decision, seq, generation)


class VerdictBroker:
    """Bounded join between asynchronous authenticated verdicts and queued packets."""
    def __init__(self, capacity: int = MAX_PENDING, cache_ttl: float = CACHE_TTL):
        self.capacity, self.cache_ttl = capacity, cache_ttl
        self.lock = threading.Lock()
        self.pending: dict[PacketKey, threading.Event] = {}
        self.results: dict[PacketKey, Verdict] = {}
        self.early: OrderedDict[PacketKey, tuple[float, Verdict]] = OrderedDict()
        self.sequences: OrderedDict[int, None] = OrderedDict()
        self.max_sequence = 0

    def submit(self, packet: PacketKey, verdict: Verdict) -> str:
        with self.lock:
            self._purge()
            if (verdict.sequence in self.sequences or
                    verdict.sequence <= self.max_sequence - REPLAY_WINDOW):
                return "replay"
            self.sequences[verdict.sequence] = None
            self.max_sequence = max(self.max_sequence, verdict.sequence)
            floor = self.max_sequence - REPLAY_WINDOW
            for old_sequence in list(self.sequences):
                if old_sequence <= floor:
                    self.sequences.pop(old_sequence, None)
            event = self.pending.get(packet)
            if event is None:
                if len(self.early) >= self.capacity:
                    self.early.popitem(last=False)
                self.early[packet] = (time.monotonic() + self.cache_ttl, verdict)
                return "cached"
            self.results[packet] = verdict
            event.set()
            return "matched"

    def wait(self, packet: PacketKey, timeout: float) -> tuple[Verdict | None, str]:
        with self.lock:
            self._purge()
            found = self.early.pop(packet, None)
            if found:
                return found[1], "early"
            if len(self.pending) >= self.capacity:
                return None, "capacity"
            event = threading.Event()
            self.pending[packet] = event
        ready = event.wait(max(0.0, timeout))
        with self.lock:
            self.pending.pop(packet, None)
            verdict = self.results.pop(packet, None)
        return verdict, "matched" if ready and verdict else "timeout"

    def _purge(self) -> None:
        now = time.monotonic()
        for key, (deadline, _) in list(self.early.items()):
            if deadline <= now:
                self.early.pop(key, None)


class Gate:
    def __init__(self, secret: bytes, session: bytes, queue_no: int):
        self.secret, self.session, self.queue_no = secret, session, queue_no
        self.broker = VerdictBroker()
        self.allowed: OrderedDict[tuple[str, str, int, int], tuple[bytes, float]] = OrderedDict()
        self.stats = {"allow": 0, "deny": 0, "unsupported": 0, "timeout": 0,
                      "non_quic": 0, "replay": 0, "bad_verdict": 0}
        self.stop = threading.Event()
        self.listener_ready = threading.Event()
        self.listener_error: Exception | None = None
        self.wait_buckets = {"lt10": 0, "lt50": 0, "lt100": 0,
                             "lt250": 0, "lt500": 0, "timeout": 0}

    def verdict_listener(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((GATE_IP, LISTEN_PORT))
            sock.settimeout(0.5)
            self.listener_ready.set()
        except Exception as exc:
            self.listener_error = exc
            self.listener_ready.set()
            sock.close()
            return
        while not self.stop.is_set():
            try:
                data, addr = sock.recvfrom(512)
            except socket.timeout:
                continue
            try:
                pkt = _wire_key(data)
                v = parse_verdict(data, addr[0], self.secret, self.session)
                status = self.broker.submit(pkt, v)
                if status == "replay":
                    self.stats["replay"] += 1
            except (ValueError, OSError, struct.error):
                self.stats["bad_verdict"] += 1
        sock.close()

    def start_listener(self) -> threading.Thread:
        thread = threading.Thread(target=self.verdict_listener, daemon=True)
        thread.start()
        if not self.listener_ready.wait(2.0) or self.listener_error is not None:
            self.stop.set()
            raise RuntimeError("Verdict listener failed to bind; queue was not activated")
        return thread

    def handle(self, packet) -> None:
        raw = packet.get_payload()
        if _scoped_fragment(raw):
            self.stats["unsupported"] += 1
            self._log("drop", "scoped_ipv4_fragment_unsupported", None)
            packet.drop()
            return
        parsed = packet_key(raw)
        if not parsed:
            packet.accept()
            return
        key, payload = parsed
        if (key.src, key.dst, key.dport) != (CLIENT_IP, ORIGIN_IP, ORIGIN_PORT):
            packet.accept()
            return
        kind, client_scid = _quic_details(payload)
        flow = (key.src, key.dst, key.sport, key.dport)
        now = time.monotonic()
        for existing, (_, expiry) in list(self.allowed.items()):
            if expiry <= now:
                self.allowed.pop(existing, None)
        if kind == "non_quic":
            self.stats["non_quic"] += 1
            packet.accept()
            return
        if kind == "initial":
            current = self.allowed.get(flow)
            if current is not None and current[0] == client_scid:
                self.allowed[flow] = (client_scid, now + FLOW_TTL)
                self.allowed.move_to_end(flow)
                self._log("allow", "same_connection_initial", key)
                packet.accept()
                return
            self.allowed.pop(flow, None)
            self._log("waiting", "awaiting_policy_verdict", key, event="queued_initial")
            v, reason = self.broker.wait(key, DECISION_TIMEOUT)
            if v is None:
                self.stats["timeout"] += 1
                self.wait_buckets["timeout"] += 1
                self._log("timeout", reason, key, waited_ms=round((time.monotonic() - now) * 1000, 2))
                packet.drop()
            elif v.decision == ALLOW:
                self.stats["allow"] += 1
                self._remember_allowed(flow, client_scid, now + FLOW_TTL)
                elapsed_ms = (time.monotonic() - now) * 1000
                self._record_wait(elapsed_ms)
                self._log("allow", reason, key, waited_ms=round(elapsed_ms, 2))
                packet.accept()
            else:
                self.allowed.pop(flow, None)
                self.stats["deny" if v.decision == DENY else "unsupported"] += 1
                elapsed_ms = (time.monotonic() - now) * 1000
                self._record_wait(elapsed_ms)
                self._log("drop", "policy_deny" if v.decision == DENY else "policy_unsupported",
                          key, waited_ms=round(elapsed_ms, 2))
                packet.drop()
            return
        if kind == "unsupported":
            self.allowed.pop(flow, None)
            self.stats["unsupported"] += 1
            self._log("drop", "unsupported_quic_version_or_header", key)
            packet.drop()
            return
        if flow in self.allowed:
            client_scid, _ = self.allowed[flow]
            self.allowed[flow] = (client_scid, now + FLOW_TTL)
            self.allowed.move_to_end(flow)
            packet.accept()
            return
        self.stats["unsupported"] += 1
        self._log("drop", "unknown_non_initial", key)
        packet.drop()

    def _record_wait(self, elapsed_ms: float) -> None:
        bucket = ("lt10" if elapsed_ms < 10 else "lt50" if elapsed_ms < 50 else
                  "lt100" if elapsed_ms < 100 else "lt250" if elapsed_ms < 250 else
                  "lt500" if elapsed_ms < 500 else "timeout")
        self.wait_buckets[bucket] += 1

    def _log(self, action: str, reason: str, key: PacketKey | None,
             waited_ms: float | None = None, event: str = "verdict") -> None:
        fields = {"event": event, "action": action, "reason": reason,
                  "monotonic": time.monotonic()}
        if key is not None:
            fields.update(src=key.src, dst=key.dst, sport=key.sport, dport=key.dport,
                          payload_len=key.payload_len,
                          payload_sha256=key.payload_hash.hex())
        if waited_ms is not None:
            fields["waited_ms"] = waited_ms
        print(json.dumps(fields), flush=True)

    def _remember_allowed(self, flow: tuple[str, str, int, int],
                          client_scid: bytes, expires: float) -> None:
        self.allowed.pop(flow, None)
        if len(self.allowed) >= MAX_CACHE:
            self.allowed.popitem(last=False)
        self.allowed[flow] = (client_scid, expires)

    def run(self) -> None:
        try:
            from netfilterqueue import NetfilterQueue
        except ImportError as exc:
            raise SystemExit("Missing Python dependency: NetfilterQueue") from exc
        try:
            self.start_listener()
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        q = NetfilterQueue()
        q.bind(self.queue_no, self.handle, max_len=MAX_PENDING)
        print(json.dumps({"event": "gate_ready", "queue": self.queue_no,
                          "listen_ip": GATE_IP, "listen_port": LISTEN_PORT}), flush=True)
        try:
            q.run()
        finally:
            self.stop.set()
            q.unbind()
            print(json.dumps({"event": "gate_summary", "stats": self.stats,
                              "wait_buckets": self.wait_buckets}), flush=True)


def _wire_key(record: bytes) -> PacketKey:
    if len(record) != RECORD_LEN:
        raise ValueError("bad_record")
    return PacketKey(socket.inet_ntoa(record[56:60]), socket.inet_ntoa(record[60:64]),
                     *struct.unpack_from("!HHH", record, 64), record[70:102])


def _quic_kind(payload: bytes) -> str:
    return _quic_details(payload)[0]


def _quic_details(payload: bytes) -> tuple[str, bytes | None]:
    if not payload:
        return "non_quic", None
    if not payload[0] & 0x80:
        # A QUIC short-header packet contains a packet number and AEAD tag;
        # tiny UDP datagrams with the fixed bit set are not treated as QUIC.
        return ("short", None) if payload[0] & 0x40 and len(payload) >= 18 else ("non_quic", None)
    if not payload[0] & 0x40:
        return "unsupported", None
    if len(payload) < 6:
        return "unsupported", None
    version = struct.unpack_from("!I", payload, 1)[0]
    if version != 1:
        return "unsupported", None
    kind = (payload[0] >> 4) & 3
    dcid_len = payload[5]
    if dcid_len > 20 or 6 + dcid_len >= len(payload):
        return "unsupported", None
    scid_len_pos = 6 + dcid_len
    scid_len = payload[scid_len_pos]
    if scid_len > 20 or scid_len_pos + 1 + scid_len >= len(payload):
        return "unsupported", None
    if kind == 0 and scid_len == 0:
        return "unsupported", None
    client_scid = payload[scid_len_pos + 1:scid_len_pos + 1 + scid_len]
    # QUIC v1 long-header type 0 is Initial. Retry/Handshake/0-RTT are
    # only forwarded after an ALLOW for the same directional 5-tuple.
    pos = scid_len_pos + 1 + scid_len
    if kind == 0:
        token_len, pos = _read_varint(payload, pos)
        if token_len is None or pos + token_len >= len(payload):
            return "unsupported", None
        pos += token_len
    if kind in (0, 1, 2):
        packet_len, pos = _read_varint(payload, pos)
        if packet_len is None or packet_len < 1 or pos + packet_len > len(payload):
            return "unsupported", None
        return ("initial", client_scid) if kind == 0 else ("long", None)
    return ("long", None) if len(payload) >= pos + 16 else ("unsupported", None)


def _read_varint(data: bytes, pos: int) -> tuple[int | None, int]:
    if pos >= len(data):
        return None, pos
    size = 1 << (data[pos] >> 6)
    if pos + size > len(data):
        return None, pos
    value = data[pos] & 0x3f
    for byte in data[pos + 1:pos + size]:
        value = (value << 8) | byte
    return value, pos + size


def _scoped_fragment(raw: bytes) -> bool:
    offset = _ipv4_offset(raw)
    if offset is None:
        return False
    raw = raw[offset:]
    if len(raw) < 20 or raw[0] >> 4 != 4 or raw[9] != 17:
        return False
    if (socket.inet_ntoa(raw[12:16]), socket.inet_ntoa(raw[16:20])) != (CLIENT_IP, ORIGIN_IP):
        return False
    return bool(struct.unpack_from("!H", raw, 6)[0] & 0x3fff)


def _ipv4_offset(raw: bytes) -> int | None:
    if raw and raw[0] >> 4 == 4:
        return 0
    if len(raw) < 14:
        return None
    ethertype = struct.unpack_from("!H", raw, 12)[0]
    offset = 14
    while ethertype in (0x8100, 0x88a8, 0x9100):
        if len(raw) < offset + 4:
            return None
        ethertype = struct.unpack_from("!H", raw, offset + 2)[0]
        offset += 4
    return offset if ethertype == 0x0800 else None


def main() -> None:
    try:
        key_path = os.environ["NETPRO_VERDICT_HMAC_KEY_FILE"]
        session = bytes.fromhex(os.environ["NETPRO_VERDICT_SESSION_ID"])
    except (KeyError, ValueError) as exc:
        raise SystemExit("Set NETPRO_VERDICT_HMAC_KEY_FILE and NETPRO_VERDICT_SESSION_ID") from exc
    mode = stat.S_IMODE(os.stat(key_path).st_mode)
    if os.name == "posix" and mode & 0o077:
        raise SystemExit("HMAC key file must be readable only by its owner (mode 0600)")
    with open(key_path, "rb") as key_file:
        secret = bytes.fromhex(key_file.read().decode("ascii").strip())
    if len(secret) != 32 or len(session) != 16:
        raise SystemExit("HMAC key/session must decode to 32/16 bytes")
    Gate(secret, session, int(os.environ.get("NETPRO_NFQUEUE", DEFAULT_QUEUE))).run()


if __name__ == "__main__":
    main()
