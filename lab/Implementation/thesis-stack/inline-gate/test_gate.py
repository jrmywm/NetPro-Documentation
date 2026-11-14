import hashlib
import hmac
import socket
import struct
import time
import unittest
from unittest import mock

import gate


def udp_packet(payload: bytes, src="192.168.80.29", dst="192.168.80.28",
               sport=54000, dport=443, fragment=0) -> bytes:
    udp_len = 8 + len(payload)
    udp = struct.pack("!HHHH", sport, dport, udp_len, 0) + payload
    total = 20 + len(udp)
    return (struct.pack("!BBHHHBBH4s4s", 0x45, 0, total, 1, fragment, 64, 17, 0,
                        socket.inet_aton(src), socket.inet_aton(dst)) + udp)


def quic_initial(client_scid=b"client-a", dcid=b"server-a") -> bytes:
    return (b"\xc0\x00\x00\x00\x01" + bytes((len(dcid),)) + dcid +
            bytes((len(client_scid),)) + client_scid + b"\x00\x01\x00")


def wire_record(secret: bytes, session: bytes, key: gate.PacketKey,
                decision=gate.ALLOW, seq=1, now_ms=None) -> bytes:
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    unsigned = (b"NPV1" + bytes((1, 1, decision, 0)) + session +
                struct.pack("!QQQQ", seq, 0, now_ms - 10, now_ms + 1000) +
                socket.inet_aton(key.src) + socket.inet_aton(key.dst) +
                struct.pack("!HHH", key.sport, key.dport, key.payload_len) + key.payload_hash)
    assert len(unsigned) == gate.SIGNED_LEN
    return unsigned + hmac.new(secret, unsigned, hashlib.sha256).digest()


class GateTests(unittest.TestCase):
    def setUp(self):
        self.secret = b"k" * 32
        self.session = b"s" * 16
        self.raw = udp_packet(b"\xc0\x00\x00\x01\x08\x00\x00")
        self.key, self.payload = gate.packet_key(self.raw)

    def test_ipv4_udp_tuple_and_payload_hash(self):
        parsed = gate.packet_key(self.raw)
        self.assertEqual(parsed[0], self.key)
        self.assertEqual(self.key.payload_hash, hashlib.sha256(self.payload).digest())
        ethernet = b"\0" * 12 + b"\x08\x00" + self.raw
        vlan = b"\0" * 12 + b"\x81\x00\x00\x01\x08\x00" + self.raw
        self.assertEqual(gate.packet_key(ethernet)[0], self.key)
        self.assertEqual(gate.packet_key(vlan)[0], self.key)

    def test_malformed_and_fragmented_packets_rejected(self):
        self.assertIsNone(gate.packet_key(b"short"))
        self.assertIsNone(gate.packet_key(udp_packet(b"abc", fragment=0x2000)))

    def test_signed_record_and_scope(self):
        record = wire_record(self.secret, self.session, self.key)
        self.assertEqual(len(record), 134)
        verdict = gate.parse_verdict(record, gate.PS_IP, self.secret, self.session)
        self.assertEqual((verdict.decision, verdict.sequence), (gate.ALLOW, 1))
        with self.assertRaisesRegex(ValueError, "bad_hmac"):
            gate.parse_verdict(record[:-1] + bytes((record[-1] ^ 1,)), gate.PS_IP,
                               self.secret, self.session)
        with self.assertRaisesRegex(ValueError, "untrusted_sender"):
            gate.parse_verdict(record, "192.168.31.32", self.secret, self.session)

    def test_wrong_session_expiry_and_bad_enum_rejected(self):
        record = wire_record(self.secret, self.session, self.key)
        with self.assertRaisesRegex(ValueError, "wrong_session"):
            gate.parse_verdict(record, gate.PS_IP, self.secret, b"x" * 16)
        expired = bytearray(record)
        struct.pack_into("!Q", expired, 40, int(time.time() * 1000) - 1100)
        struct.pack_into("!Q", expired, 48, int(time.time() * 1000) - 1000)
        expired[102:] = hmac.new(self.secret, expired[:102], hashlib.sha256).digest()
        with self.assertRaisesRegex(ValueError, "expired_verdict"):
            gate.parse_verdict(bytes(expired), gate.PS_IP, self.secret, self.session)
        invalid = bytearray(record)
        invalid[6] = 4
        invalid[102:] = hmac.new(self.secret, invalid[:102], hashlib.sha256).digest()
        with self.assertRaisesRegex(ValueError, "bad_decision"):
            gate.parse_verdict(bytes(invalid), gate.PS_IP, self.secret, self.session)

    def test_broker_handles_early_delivery_and_replay(self):
        broker = gate.VerdictBroker(capacity=2)
        verdict = gate.Verdict(gate.DENY, 7, 0)
        self.assertEqual(broker.submit(self.key, verdict), "cached")
        self.assertEqual(broker.submit(self.key, verdict), "replay")
        self.assertEqual(broker.wait(self.key, 0)[0], verdict)

    def test_broker_times_out_and_bounds_cache(self):
        broker = gate.VerdictBroker(capacity=1, cache_ttl=0.01)
        self.assertEqual(broker.wait(self.key, 0)[1], "timeout")
        self.assertEqual(broker.submit(self.key, gate.Verdict(gate.ALLOW, 1, 0)), "cached")
        key2 = gate.packet_key(udp_packet(b"different"))[0]
        broker.submit(key2, gate.Verdict(gate.ALLOW, 2, 0))
        self.assertEqual(len(broker.early), 1)

    def test_quic_classification_is_explicit(self):
        self.assertEqual(gate._quic_kind(b"not-quic"), "non_quic")
        self.assertEqual(gate._quic_kind(b"\x01" + b"not-quic"), "non_quic")
        self.assertEqual(gate._quic_kind(b"\xc0\x00"), "unsupported")
        initial = quic_initial()
        self.assertEqual(gate._quic_kind(initial), "initial")
        self.assertEqual(gate._quic_kind(initial[:6]), "unsupported")
        self.assertEqual(gate._quic_kind(quic_initial(client_scid=b"")), "unsupported")
        self.assertEqual(gate._quic_kind(b"\x40" + b"x" * 20), "short")
        self.assertEqual(gate._quic_kind(b"\xd0\x00\x00\x00\x01\x00\x00\x01\x00"), "long")
        self.assertEqual(gate._quic_kind(b"\xc0\x00\x00\x00\x02\x00"), "unsupported")

    def test_deny_clears_previously_allowed_flow_and_unknown_short_header_drops(self):
        class FakePacket:
            def __init__(self, payload):
                self.payload, self.action = payload, None
            def get_payload(self): return self.payload
            def accept(self): self.action = "accept"
            def drop(self): self.action = "drop"

        gate_instance = gate.Gate(self.secret, self.session, 4242)
        flow = (self.key.src, self.key.dst, self.key.sport, self.key.dport)
        gate_instance.allowed[flow] = (b"old-client", time.monotonic() + 30)
        initial_bytes = quic_initial(client_scid=b"new-client")
        broker_key, _ = gate.packet_key(udp_packet(initial_bytes))
        gate_instance.broker.submit(broker_key, gate.Verdict(gate.DENY, 1, 0))
        initial = FakePacket(udp_packet(initial_bytes))
        gate_instance.handle(initial)
        self.assertEqual(initial.action, "drop")
        self.assertNotIn(flow, gate_instance.allowed)
        unknown_short = FakePacket(udp_packet(b"\x40" + b"q" * 20))
        gate_instance.handle(unknown_short)
        self.assertEqual(unknown_short.action, "drop")

    def test_initial_timeout_clears_old_flow_and_fails_closed(self):
        class FakePacket:
            def __init__(self, payload): self.payload, self.action = payload, None
            def get_payload(self): return self.payload
            def accept(self): self.action = "accept"
            def drop(self): self.action = "drop"

        gate_instance = gate.Gate(self.secret, self.session, 4242)
        flow = ("192.168.80.29", "192.168.80.28", 54000, 443)
        gate_instance.allowed[flow] = (b"old-client", time.monotonic() + 30)
        initial = FakePacket(udp_packet(quic_initial(client_scid=b"new-client")))
        with mock.patch.object(gate, "DECISION_TIMEOUT", 0):
            gate_instance.handle(initial)
        self.assertEqual(initial.action, "drop")
        self.assertNotIn(flow, gate_instance.allowed)

    def test_allowed_short_header_passes_and_flow_cache_is_bounded(self):
        class FakePacket:
            def __init__(self, payload):
                self.payload, self.action = payload, None
            def get_payload(self): return self.payload
            def accept(self): self.action = "accept"
            def drop(self): self.action = "drop"

        gate_instance = gate.Gate(self.secret, self.session, 4242)
        flow = (self.key.src, self.key.dst, self.key.sport, self.key.dport)
        old_expiry = time.monotonic() + 1
        gate_instance.allowed[flow] = (b"client-a", old_expiry)
        short = FakePacket(udp_packet(b"\x40" + b"q" * 20))
        gate_instance.handle(short)
        self.assertEqual(short.action, "accept")
        self.assertGreater(gate_instance.allowed[flow][1], old_expiry)
        with mock.patch.object(gate, "MAX_CACHE", 3):
            for port in range(10_000, 10_005):
                gate_instance._remember_allowed(("192.168.80.29", "192.168.80.28",
                                                 port, 443), b"client", time.monotonic() + 10)
        self.assertEqual(len(gate_instance.allowed), 3)

    def test_same_client_scid_initial_continues_connection(self):
        class FakePacket:
            def __init__(self, payload): self.payload, self.action = payload, None
            def get_payload(self): return self.payload
            def accept(self): self.action = "accept"
            def drop(self): self.action = "drop"

        gate_instance = gate.Gate(self.secret, self.session, 4242)
        flow = ("192.168.80.29", "192.168.80.28", 54000, 443)
        old_expiry = time.monotonic() + 1
        gate_instance.allowed[flow] = (b"client-a", old_expiry)
        packet = FakePacket(udp_packet(quic_initial(client_scid=b"client-a")))
        gate_instance.handle(packet)
        self.assertEqual(packet.action, "accept")
        self.assertEqual(gate_instance.allowed[flow][0], b"client-a")
        self.assertGreater(gate_instance.allowed[flow][1], old_expiry)

    def test_expired_connection_state_drops_later_packet(self):
        class FakePacket:
            def __init__(self, payload): self.payload, self.action = payload, None
            def get_payload(self): return self.payload
            def accept(self): self.action = "accept"
            def drop(self): self.action = "drop"

        gate_instance = gate.Gate(self.secret, self.session, 4242)
        flow = ("192.168.80.29", "192.168.80.28", 54000, 443)
        gate_instance.allowed[flow] = (b"client-a", time.monotonic() - 1)
        packet = FakePacket(udp_packet(b"\x40" + b"q" * 20))
        gate_instance.handle(packet)
        self.assertEqual(packet.action, "drop")
        self.assertNotIn(flow, gate_instance.allowed)

    def test_new_client_scid_does_not_inherit_old_tuple_allow(self):
        class FakePacket:
            def __init__(self, payload): self.payload, self.action = payload, None
            def get_payload(self): return self.payload
            def accept(self): self.action = "accept"
            def drop(self): self.action = "drop"

        gate_instance = gate.Gate(self.secret, self.session, 4242)
        flow = ("192.168.80.29", "192.168.80.28", 54000, 443)
        gate_instance.allowed[flow] = (b"client-a", time.monotonic() + 30)
        packet = FakePacket(udp_packet(quic_initial(client_scid=b"client-b")))
        with mock.patch.object(gate, "DECISION_TIMEOUT", 0):
            gate_instance.handle(packet)
        self.assertEqual(packet.action, "drop")
        self.assertNotIn(flow, gate_instance.allowed)

    def test_verdict_listener_bind_failure_prevents_startup(self):
        gate_instance = gate.Gate(self.secret, self.session, 4242)

        class FailedSocket:
            def bind(self, _): raise OSError("in use")
            def close(self): pass

        with mock.patch.object(gate.socket, "socket", return_value=FailedSocket()):
            with self.assertRaisesRegex(RuntimeError, "queue was not activated"):
                gate_instance.start_listener()

    def test_fragmented_scoped_udp_is_rejected(self):
        self.assertTrue(gate._scoped_fragment(udp_packet(b"x", fragment=0x2000)))
        ethernet = b"\0" * 12 + b"\x08\x00" + udp_packet(b"x", fragment=0x2000)
        self.assertTrue(gate._scoped_fragment(ethernet))
        self.assertFalse(gate._scoped_fragment(udp_packet(b"x", src="192.168.80.30",
                                                           fragment=0x2000)))

    def test_replay_window_keeps_reordering_but_rejects_old_sequence(self):
        broker = gate.VerdictBroker(capacity=1)
        self.assertEqual(broker.submit(self.key, gate.Verdict(gate.ALLOW, 5000, 0)), "cached")
        self.assertEqual(broker.submit(self.key, gate.Verdict(gate.DENY, 4500, 0)), "cached")
        self.assertEqual(broker.submit(self.key, gate.Verdict(gate.ALLOW, 5000 -
                                                               gate.REPLAY_WINDOW, 0)), "replay")


if __name__ == "__main__":
    unittest.main()
