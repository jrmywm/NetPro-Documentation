import csv

# Nama file input dan output
input_file = "quic_packets.csv"
output_file = "handshake_deltas.csv"

# Tempat penyimpanan hasil
handshake_deltas = []

# Baca isi file
with open(input_file, newline='') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

    i = 0
    while i < len(rows):
        current_row = rows[i]

        # Langkah 1: Deteksi paket Initial
        if current_row["Type"] == "Initial":
            scid = current_row["SCID"]
            timestamp_initial = float(current_row["Timestamp"])

            # Langkah 2: Cari paket Handshake ke depan
            j = i + 1
            while j < len(rows):
                next_row = rows[j]
                if next_row["Type"] == "Handshake":
                    if next_row["DCID"] == scid:
                        timestamp_handshake = float(next_row["Timestamp"])
                        delta_ms = (timestamp_handshake - timestamp_initial) * 1000  # dalam milidetik
                        handshake_deltas.append({
                            "Initial Packet #": current_row["Packet #"],
                            "Handshake Packet #": next_row["Packet #"],
                            "Time Delta (ms)": round(delta_ms, 3)
                        })
                        break  # Stop saat ketemu pertama yang cocok
                j += 1

        i += 1

# Tulis ke CSV
with open(output_file, mode='w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["Initial Packet #", "Handshake Packet #", "Time Delta (ms)"])
    writer.writeheader()
    writer.writerows(handshake_deltas)
