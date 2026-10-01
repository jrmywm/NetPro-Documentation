#!/usr/bin/env python3
"""Offline regression harness for the production TLS flow parser and tracker."""

import argparse
import hashlib
import pathlib
import struct
import subprocess
import tempfile

SOURCE_SHA256 = "bf51e1c98b1d2c3a323270fa87e0bebc1759f6d5b5032c316c6c2e302438d819"
TRACKER_SHA256 = "e52d75d29585f3e2339fdfa4df4291254ec7dcc164ecb743898eaaba579d7112"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_record(path):
    raw = path.read_bytes()
    magic = raw[:4]
    endian = {b"\xd4\xc3\xb2\xa1": "<", b"\xa1\xb2\xc3\xd4": ">",
              b"\x4d\x3c\xb2\xa1": "<", b"\xa1\xb2\x3c\x4d": ">"}.get(magic)
    if not endian or len(raw) < 24 or struct.unpack_from(endian + "I", raw, 20)[0] != 1:
        raise ValueError("expected a complete classic Ethernet PCAP")
    offset, flows = 24, {}
    while offset + 16 <= len(raw):
        _, _, caplen, _ = struct.unpack_from(endian + "IIII", raw, offset)
        offset += 16
        frame = raw[offset:offset + caplen]
        if len(frame) != caplen:
            raise ValueError("truncated PCAP packet")
        offset += caplen
        if len(frame) < 54 or frame[12:14] != b"\x08\x00":
            continue
        ip = frame[14:]
        ihl = (ip[0] & 15) * 4
        if ip[0] >> 4 != 4 or ip[9] != 6 or len(ip) < ihl + 20:
            continue
        iplen = struct.unpack_from(">H", ip, 2)[0]
        tcp = ip[ihl:iplen]
        thl = (tcp[12] >> 4) * 4
        if len(tcp) < thl or thl < 20:
            continue
        sport, dport, seq = struct.unpack_from(">HHI", tcp)
        payload = tcp[thl:]
        if payload:
            flows.setdefault((ip[12:20], sport, dport), []).append((seq, payload))
    candidates = []
    for (_addresses, _sport, dport), packets in flows.items():
        if dport != 8443:
            continue
        for base, first in packets:
            if len(first) < 6 or first[:2] != b"\x16\x03" or first[5] != 1:
                continue
            total = struct.unpack_from(">H", first, 3)[0] + 5
            if total < 9 or total > 4096:
                continue
            data, cursor = bytearray(total), 0
            spans = []
            for seq, payload in packets:
                rel = (seq - base) & 0xffffffff
                if rel < total:
                    spans.append((rel, payload[:total - rel]))
            for rel, payload in sorted(spans):
                if rel > cursor:
                    break
                end = rel + len(payload)
                if end > cursor:
                    data[cursor:end] = payload[cursor - rel:]
                    cursor = end
            if cursor == total:
                candidates.append(bytes(data))
    if not candidates:
        raise ValueError("no complete ClientHello record on destination TCP port 8443")
    return max(candidates, key=len)


def c_bytes(data):
    return ",".join(f"0x{x:02x}" for x in data)


def extract(source, begin, end):
    return source[source.index(begin):source.index(end, source.index(begin))]


def make_harness(source, record):
    flow_type = extract(source, "typedef struct\n{\n\tbool used;\n\tuint32_t src_addr", "} tls_flow_t;") + "} tls_flow_t;"
    parser = extract(source, "static uint16_t tls_u16", "static inline char *extractDomainfromHTTP")
    return f'''#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
#define MAX_DOMAIN_LEN 256
#define TLS_FLOW_SLOTS 128
#define TLS_FLOW_MAX_BYTES 4096
#define TLS_FLOW_TIMEOUT_SEC 15
#define RTE_ETHER_TYPE_IPV4 0x0800
#define IPPROTO_TCP 6
#define RTE_TCP_SYN_FLAG 0x02
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
#define rte_cpu_to_be_16(x) __builtin_bswap16((uint16_t)(x))
#define rte_be_to_cpu_16(x) __builtin_bswap16((uint16_t)(x))
#define rte_be_to_cpu_32(x) __builtin_bswap32((uint32_t)(x))
#else
#define rte_cpu_to_be_16(x) ((uint16_t)(x))
#define rte_be_to_cpu_16(x) ((uint16_t)(x))
#define rte_be_to_cpu_32(x) ((uint32_t)(x))
#endif
typedef int rte_spinlock_t;
#define RTE_SPINLOCK_INITIALIZER 0
static void rte_spinlock_lock(rte_spinlock_t *p) {{ (void)p; }}
static void rte_spinlock_unlock(rte_spinlock_t *p) {{ (void)p; }}
struct rte_ether_hdr {{ uint8_t dst[6], src[6]; uint16_t ether_type; }} __attribute__((packed));
struct rte_ipv4_hdr {{ uint8_t version_ihl, type_of_service; uint16_t total_length, packet_id, fragment_offset; uint8_t time_to_live, next_proto_id; uint16_t hdr_checksum; uint32_t src_addr, dst_addr; }} __attribute__((packed));
struct rte_tcp_hdr {{ uint16_t src_port, dst_port; uint32_t sent_seq, recv_ack; uint8_t data_off, tcp_flags; uint16_t rx_win, cksum, tcp_urp; }} __attribute__((packed));
struct rte_mbuf {{ uint8_t *buf; size_t pkt_len; }};
static const void *rte_pktmbuf_read(const struct rte_mbuf *m, uint32_t off, uint32_t len, void *dst) {{
  if ((size_t)off + len > m->pkt_len) return NULL;
  memcpy(dst, m->buf + off, len); return dst;
}}
{flow_type}
static tls_flow_t tls_flows[TLS_FLOW_SLOTS];
static rte_spinlock_t tls_flow_lock = RTE_SPINLOCK_INITIALIZER;
{parser}
static uint8_t record[] = {{{c_bytes(record)}}};
static uint8_t frame[14 + 20 + 20 + sizeof(record)];
static struct rte_mbuf packet;
static void packet_segment(size_t offset, size_t length, uint32_t seq) {{
  memset(frame, 0, sizeof(frame));
  struct rte_ether_hdr *eth = (void *)frame;
  eth->ether_type = rte_cpu_to_be_16(RTE_ETHER_TYPE_IPV4);
  struct rte_ipv4_hdr *ip = (void *)(frame + 14);
  ip->version_ihl = 0x45; ip->total_length = rte_cpu_to_be_16((uint16_t)(40 + length));
  ip->next_proto_id = IPPROTO_TCP; ip->src_addr = 0x01020304; ip->dst_addr = 0x05060708;
  struct rte_tcp_hdr *tcp = (void *)(frame + 34);
  tcp->src_port = rte_cpu_to_be_16(47000); tcp->dst_port = rte_cpu_to_be_16(8443);
  tcp->sent_seq = __builtin_bswap32(seq); tcp->data_off = 5 << 4;
  memcpy(frame + 54, record + offset, length); packet.buf = frame; packet.pkt_len = 54 + length;
}}
static void deliver(size_t offset, size_t length, uint32_t seq, const char *wanted, bool complete) {{
  packet_segment(offset, length, seq); bool done = false;
  char *host = extractDomainfromHTTPS(&packet, &done);
  assert(done == complete);
  if (wanted) {{ assert(host && strcmp(host, wanted) == 0); free(host); }} else {{ assert(host == NULL); }}
}}
static void clear_flows(void) {{ memset(tls_flows, 0, sizeof(tls_flows)); }}
int main(void) {{
  const size_t n = sizeof(record); const uint32_t base = 1000;
  assert(n > 9 && record[0] == 0x16 && record[5] == 1);
  size_t first = n / 3, second = n / 3, last = n - first - second;
  bool done = false; char *expected = tls_clienthello_sni(record, n, &done); assert(done && expected);
  clear_flows(); deliver(0, first, base, NULL, false); deliver(first, second, base + (uint32_t)first, NULL, false); deliver(first + second, last, base + (uint32_t)(first + second), expected, true);
  puts("PASS in-order segments: production parser returns captured SNI");
  clear_flows(); deliver(0, first, base, NULL, false); deliver(0, first, base, NULL, false); deliver(first, second, base + (uint32_t)first, NULL, false); deliver(first + second, last, base + (uint32_t)(first + second), expected, true);
  puts("PASS duplicate retransmission: duplicate bytes do not prevent exact match");
  clear_flows(); deliver(0, first, base, NULL, false); deliver(first - 2, second, base + (uint32_t)(first - 2), NULL, false); deliver(first + second - 2, last + 2, base + (uint32_t)(first + second - 2), expected, true);
  puts("PASS identical overlap: matching overlap is accepted");
  clear_flows(); deliver(0, first, base, NULL, false); record[first - 1] ^= 0x01; deliver(first - 2, second, base + (uint32_t)(first - 2), NULL, false); record[first - 1] ^= 0x01;
  deliver(first + second - 2, last + 2, base + (uint32_t)(first + second - 2), NULL, false);
  puts("PASS inconsistent overlap: flow discarded; no false SNI match");
  clear_flows(); deliver(0, first, base, NULL, false); deliver(first + second, last, base + (uint32_t)(first + second), NULL, false); deliver(first, second, base + (uint32_t)first, NULL, false);
  puts("PASS out-of-order gap: production policy rejects/discards the flow; no arbitrary reassembly claim");
  clear_flows(); uint32_t wrap = 0xfffffff0u; deliver(0, first, wrap, NULL, false); deliver(first, second, wrap + (uint32_t)first, NULL, false); deliver(first + second, last, wrap + (uint32_t)(first + second), expected, true);
  puts("PASS TCP sequence wrap: in-order record crossing wrap matches captured SNI");
  free(expected); return 0;
}}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=pathlib.Path, required=True, help="production policyServer.c")
    ap.add_argument("--tracker", type=pathlib.Path, required=True, help="production tls_record_tracker.h")
    ap.add_argument("--fixture", type=pathlib.Path, required=True, help="classic Ethernet PCAP containing the ClientHello flow")
    ap.add_argument("--gcc", default="gcc", help="C compiler executable (default: gcc)")
    args = ap.parse_args()
    for path, expected, label in ((args.source, SOURCE_SHA256, "production parser"), (args.tracker, TRACKER_SHA256, "tracker")):
        actual = digest(path)
        if actual != expected:
            raise SystemExit(f"FAIL {label} source SHA256 mismatch: {actual} (expected {expected})")
    record = fixture_record(args.fixture)
    tracker_path = args.tracker.resolve().as_posix()
    with tempfile.TemporaryDirectory(prefix="tls-regression-") as td:
        tmp = pathlib.Path(td)
        parser_c, parser_exe = tmp / "parser.c", tmp / "parser.exe"
        parser_c.write_text(make_harness(args.source.read_text(encoding="utf-8"), record), encoding="utf-8")
        subprocess.run([args.gcc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(parser_c), "-o", str(parser_exe)], check=True)
        subprocess.run([str(parser_exe)], check=True)
        tracker_c, tracker_exe = tmp / "tracker.c", tmp / "tracker.exe"
        tracker_source = pathlib.Path(__file__).with_name("tracker_regression.c").read_text(encoding="utf-8")
        tracker_c.write_text(tracker_source.replace('"tls_record_tracker.h"', f'"{tracker_path}"'), encoding="utf-8")
        subprocess.run([args.gcc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(tracker_c), "-o", str(tracker_exe)], check=True)
        subprocess.run([str(tracker_exe)], check=True)
    print(f"PASS fixture record: {len(record)} bytes; parser source SHA256 verified; tracker source SHA256 verified")
    print("SCOPE: offline algorithm coverage only; no live service or end-to-end network behavior tested")


if __name__ == "__main__":
    main()
