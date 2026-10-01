#!/usr/bin/env python3
"""Compare TRex return counters for original and packet-normalized MACs."""

# Load the TRex API before Scapy so packet classes match the running client library.
from trex.stl.api import (
    STLClient,
    STLPktBuilder,
    STLStream,
    STLTXSingleBurst,
    STLVmFlowVar,
    STLVmWrFlowVar,
    STLVmFixChecksumHw,
    CTRexVmInsFixHwCs,
)
from scapy.all import Ether, IP, TCP, Raw, Padding, rdpcap
import json
import os
import time


SERVER = "127.0.0.1"
TX_PORT = 0
RX_PORT = 1
PORTS = [TX_PORT, RX_PORT]
TLS_PCAP = "/opt/trex/v3.04/automation/trex_control_plane/interactive/trex/npb_test/npb/pcap/https_583B_single.pcap"
HTTP_PAYLOAD = b"GET / HTTP/1.1\r\nHost: facebook.co.id\r\nConnection: close\r\n\r\n"
CASE_MODES = ("original", "normalized")


def make_http_packet():
    packet = (
        Ether()
        / IP(src="16.0.0.1", dst="48.0.0.1")
        / TCP(sport=22001, dport=80, flags="PA")
        / Raw(load=HTTP_PAYLOAD)
    )
    padding = max(0, 252 - len(bytes(packet)))
    if padding:
        packet = packet / Padding(load=b"\x00" * padding)
    return packet


def make_streams(mode, tls_packet):
    packets = [make_http_packet(), tls_packet]
    case_offset = 1000 if mode == "normalized" else 0
    first_sports = (22001 + case_offset, 23001 + case_offset)
    streams = []
    for packet, first_sport in zip(packets, first_sports):
        if not packet.haslayer(TCP):
            raise RuntimeError("Both diagnostic packets must contain TCP")
        vm = [
            STLVmFlowVar(
                name="source_port",
                min_value=first_sport,
                max_value=first_sport + 99,
                size=2,
                step=1,
                op="inc",
            ),
            STLVmWrFlowVar(fv_name="source_port", pkt_offset="TCP.sport"),
            STLVmFixChecksumHw(
                l3_offset="IP",
                l4_offset="TCP",
                l4_type=CTRexVmInsFixHwCs.L4_TYPE_TCP,
            ),
        ]
        builder = STLPktBuilder(pkt=packet, vm=vm)
        kwargs = {}
        if mode == "normalized":
            kwargs = {
                "mac_src_override_by_pkt": False,
                "mac_dst_override_mode": 0,
            }
        stream = STLStream(
            packet=builder,
            mode=STLTXSingleBurst(total_pkts=100, pps=100),
            **kwargs,
        )
        streams.append(stream)
        print(
            f"{mode} stream flags={stream.fields['flags']} "
            f"src_override={stream.fields.get('mac_src_override_by_pkt', 'default')} "
            f"dst_override={stream.fields.get('mac_dst_override_mode', 'default')} "
            f"packet_mac={packet[Ether].src}>{packet[Ether].dst} "
            f"default_src_mac={builder.is_default_src_mac()} "
            f"default_dst_mac={builder.is_default_dst_mac()} "
            f"sport_range={first_sport}-{first_sport + 99}"
        )
    return streams


def relevant_stats(port_stats):
    return {
        key: value
        for key, value in port_stats.items()
        if any(token in key.lower() for token in ("pkt", "packet", "byte", "err", "drop"))
    }


def run_case(client, mode, tls_packet):
    client.remove_all_streams(ports=[TX_PORT])
    streams = make_streams(mode, tls_packet)
    client.add_streams(streams, ports=[TX_PORT])
    client.clear_stats(ports=PORTS)
    capture_id = None
    capture_path = f"/tmp/netpro-mac-return-{mode}-{os.getpid()}-{time.time_ns()}.pcap"
    try:
        capture_result = client.start_capture(
            rx_ports=PORTS,
            limit=1000,
            bpf_filter="tcp[tcpflags] & tcp-rst != 0",
        )
        capture_id = capture_result["id"]
        print(f"{mode} RST capture started: {capture_id}")
    except Exception as error:
        print(f"{mode} RST capture unavailable: {type(error).__name__}: {error}")
    try:
        client.start(ports=[TX_PORT], force=True)
        client.wait_on_traffic(ports=[TX_PORT], timeout=15)
        time.sleep(1)
    finally:
        if capture_id is not None:
            try:
                client.stop_capture(capture_id, output=capture_path)
                print(f"{mode} RST capture saved: {capture_path}")
            except Exception as error:
                print(f"{mode} RST capture stop failed: {type(error).__name__}: {error}")
    stats = client.get_stats()
    per_port = {
        str(port): relevant_stats(stats.get(port, {}))
        for port in PORTS
    }
    totals = {}
    for values in per_port.values():
        for key, value in values.items():
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0) + value
    print(json.dumps({"case": mode, "totals": totals, "ports": per_port}, sort_keys=True))


def main():
    tls_packets = rdpcap(TLS_PCAP)
    if not tls_packets:
        raise RuntimeError(f"No packets found in {TLS_PCAP}")
    tls_packet = tls_packets[0]
    client = STLClient(server=SERVER)
    acquired = False
    try:
        client.connect()
        client.acquire(ports=PORTS)
        acquired = True
        client.reset(ports=PORTS)
        for mode in CASE_MODES:
            run_case(client, mode, tls_packet)
    finally:
        if acquired:
            try:
                client.stop(ports=[TX_PORT])
            except Exception:
                pass
            try:
                client.remove_all_streams(ports=[TX_PORT])
            except Exception:
                pass
            client.release(ports=PORTS)
        client.disconnect()


if __name__ == "__main__":
    main()
