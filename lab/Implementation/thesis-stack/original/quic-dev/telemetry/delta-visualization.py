import pandas as pd
import matplotlib.pyplot as plt

# Load CSV hasil sebelumnya
initial_to_initial_df = pd.read_csv("initial_to_initial_deltas.csv")
initial_to_handshake_df = pd.read_csv("handshake_deltas.csv")

# Tambahkan kolom label
initial_to_initial_df["Type"] = "Initial→CC"
initial_to_handshake_df["Type"] = "Initial→Handshake"

# Gabungkan kedua DataFrame
combined_df = pd.concat([initial_to_initial_df, initial_to_handshake_df], ignore_index=True)

# Pastikan kolom packet number bertipe integer
combined_df["Initial Packet #"] = combined_df["Initial Packet #"].astype(int)

# Urutkan berdasarkan Initial Packet #
combined_df = combined_df.sort_values(by="Initial Packet #")

# Kelompokkan per 100 paket initial
combined_df["Group"] = combined_df["Initial Packet #"] // 100

# Hitung rata-rata Time Delta tiap grup dan tiap tipe
grouped_avg = combined_df.groupby(["Group", "Type"])["Time Delta (ms)"].mean().reset_index()

# Pivot untuk visualisasi
pivot_df = grouped_avg.pivot(index="Group", columns="Type", values="Time Delta (ms)")

# Plot dan simpan sebagai gambar
plt.figure(figsize=(12, 6))
plt.plot(pivot_df.index * 100, pivot_df["Initial→CC"], marker='o', label="Initial→CC")
plt.plot(pivot_df.index * 100, pivot_df["Initial→Handshake"], marker='s', label="Initial→Handshake")
plt.title("Rata-rata Time Delta setiap 100 Paket Initial")
plt.xlabel("Nomor Paket Initial Awal")
plt.ylabel("Rata-rata Time Delta (ms)")
plt.legend()
plt.grid(True)
plt.tight_layout()

# Simpan sebagai file gambar
plt.savefig("quic_time_delta_avg.png")
