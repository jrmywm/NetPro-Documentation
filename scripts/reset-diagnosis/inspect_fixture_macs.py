#!/usr/bin/env python3
"""Read-only summary of the two TRex PCAP fixtures and generated packet defaults."""

# Import TRex first so its bundled Scapy is used in the interactive environment.
from trex.stl.api import STLPktBuilder, STLStream, STLTXSingleBurst
from scapy.all import Ether, IP, TCP, UDP, rdpcap


PCAPS = (
    "/opt/trex/v3.04/automation/trex_control_plane/interactive/trex/npb_test/npb/pcap/https_583B_single.pcap",
    "/opt/trex/v3.04/automation/trex_control_plane/interactive/trex/npb_test/npb/pcap/udp_1518B_no_crc.pcap",
)
TREX_PORT0_MACS = ("00:0c:29:c5:4f:e8", "00:0c:29:ba:d7:5a")


def describe(packet):
    ether = packet.getlayer(Ether)
    ip = packet.getlayer(IP)
    tcp = packet.getlayer(TCP)
    udp = packet.getlayer(UDP)
    payload_len = len(bytes(tcp.payload)) if tcp else len(bytes(udp.payload)) if udp else 0
    fields = [
        f"Ether={ether.src}>{ether.dst}" if ether else "Ether=missing",
        f"IP={ip.src}>{ip.dst}" if ip else "IP=missing",
    ]
    if tcp:
        fields.append(f"TCP={tcp.sport}>{tcp.dport} flags={tcp.flags}")
    elif udp:
        fields.append(f"UDP={udp.sport}>{udp.dport}")
    else:
        fields.append("L4=missing")
    fields.append(f"payload={payload_len}B")
    return " ".join(fields)


def describe_trex_defaults(label, packet):
    builder = STLPktBuilder(pkt=packet)
    stream = STLStream(
        packet=builder,
        mode=STLTXSingleBurst(total_pkts=1, pps=1),
    )
    print(
        f"  TRex {label}: stream.flags={stream.fields['flags']} "
        f"default_src_mac={builder.is_default_src_mac()} "
        f"default_dst_mac={builder.is_default_dst_mac()}"
    )


print(f"Configured TRex port 0 MACs: src={TREX_PORT0_MACS[0]} dst={TREX_PORT0_MACS[1]}")
generated = Ether() / IP(src="16.0.0.1", dst="48.0.0.1") / TCP(dport=80)
print("Scapy-generated HTTP header defaults: " + describe(generated))
describe_trex_defaults("generated HTTP", generated)

for path in PCAPS:
    packets = rdpcap(path)
    print(f"{path} ({len(packets)} packets)")
    if packets:
        packet = packets[0]
        print(f"  #1: {describe(packet)}")
        describe_trex_defaults("fixture packet 1", packet)
