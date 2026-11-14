from scapy.all import PcapReader, UDP
import csv
from datetime import datetime

QUIC_LONG_HEADER_TYPES = {
    0: "Initial",
    1: "0-RTT",
    2: "Handshake",
    3: "Retry"
}

def is_quic_long_header(payload):
    if len(payload) < 6:
        return False
    first_byte = payload[0]
    return (first_byte & 0b11000000) == 0b11000000  # Bit 7-6 = 11

def get_quic_type(payload):
    if len(payload) < 1:
        return None
    first_byte = payload[0]
    packet_type = (first_byte & 0b00110000) >> 4
    return QUIC_LONG_HEADER_TYPES.get(packet_type, f"Unknown ({packet_type})")

def extract_dcid_scid(payload):
    try:
        if len(payload) < 7:
            return None, None, None
        version = payload[1:5]
        dcid_len = payload[5]
        if 6 + dcid_len >= len(payload):
            return None, None, None
        dcid = payload[6:6 + dcid_len]
        scid_len_index = 6 + dcid_len
        if scid_len_index >= len(payload):
            return None, None, None
        scid_len = payload[scid_len_index]
        scid_start = scid_len_index + 1
        scid_end = scid_start + scid_len
        if scid_end > len(payload):
            return None, None, None
        scid = payload[scid_start:scid_end]
        return dcid.hex(), scid.hex(), version.hex()
    except:
        return None, None, None

# File pcapng
pcap_file = "quic-capture-time.pcapng"
csv_file = "quic_packets.csv"

with PcapReader(pcap_file) as pcap, open(csv_file, mode='w', newline='') as file:
    writer = csv.writer(file)
    # Menambahkan kolom timestamp ke header CSV
    writer.writerow(["Packet #", "Timestamp", "Type", "Version", "DCID", "SCID"])
    
    count = 0
    for i, pkt in enumerate(pcap, 1):
        if UDP in pkt:
            try:
                payload = bytes(pkt[UDP].payload)
                if is_quic_long_header(payload):
                    quic_type = get_quic_type(payload)
                    dcid, scid, version = extract_dcid_scid(payload)
                    if dcid and scid:
                        count += 1
                        # Mendapatkan timestamp dengan presisi milidetik
                        timestamp = pkt.time  # Timestamp dalam detik dengan presisi floating-point
                        # Format timestamp hingga milidetik (6 digit desimal)
                        formatted_timestamp = f"{timestamp:.6f}"
                        writer.writerow([count, formatted_timestamp, quic_type, version, dcid, scid])
                        print(f"[#{count}] Pkt#{i} | Timestamp: {formatted_timestamp} | Type: {quic_type} | Version: {version} | DCID: {dcid} | SCID: {scid}")
            except Exception as e:
                print(f"Error parsing packet #{i}: {e}")

print(f"Data has been saved to {csv_file}")