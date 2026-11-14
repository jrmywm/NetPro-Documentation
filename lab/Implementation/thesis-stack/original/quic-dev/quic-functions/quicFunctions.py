from scapy.all import rdpcap, UDP

def is_quic_initial(payload):
    if len(payload) < 6:
        return False
    first_byte = payload[0]
    is_long_header = (first_byte & 0b11000000) == 0b11000000
    packet_type = (first_byte & 0b00110000) >> 4
    return is_long_header and packet_type == 0  # Initial packet

def extract_dcid_scid(payload):
    try:
        version = payload[1:5]
        dcid_len = payload[5]
        dcid = payload[6:6+dcid_len]
        scid_len_index = 6 + dcid_len
        scid_len = payload[scid_len_index]
        scid = payload[scid_len_index+1:scid_len_index+1+scid_len]
        return dcid.hex(), scid.hex()
    except:
        return None, None

# BACA FILE PCAPNG
packets = rdpcap("quic-capture-time.pcapng")  # ganti nama file sesuai

for pkt in packets:
    if UDP in pkt:
        payload = bytes(pkt[UDP].payload)
        if is_quic_initial(payload):
            dcid, scid = extract_dcid_scid(payload)
            if dcid and scid:
                print(f"DCID: {dcid}, SCID: {scid}")
