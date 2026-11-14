import os
import pandas as pd
import matplotlib.pyplot as plt
import re

# Configuration
input_dir = "."  # Current directory
output_dir = "output"
threshold = 50  # Show all > 0
os.makedirs(output_dir, exist_ok=True)

def extract_id(filename):
    match = re.search(r'_(\d+(?:-\d+)?)', filename)
    return match.group(1) if match else None

def parse_throughput_and_trial(fid):
    # Extracts throughput and trial from ID like "10-3" or "150"
    parts = fid.split("-")
    throughput = int(parts[0]) * 10  # Convert 10 to 100 pkt/s
    trial = int(parts[1]) if len(parts) > 1 else 1
    return throughput, trial

# Get all file names
files = [f for f in os.listdir(input_dir) if f.endswith('.csv')]
port0_files = {extract_id(f): f for f in files if "port0" in f}
port1_files = {extract_id(f): f for f in files if "port1" in f}

# Process matched files
for fid in sorted(set(port0_files) & set(port1_files)):
    f0 = port0_files[fid]
    f1 = port1_files[fid]

    print(f"Processing: {f0} vs {f1}")
    throughput, trial = parse_throughput_and_trial(fid)

    # Load CSVs
    df0 = pd.read_csv(os.path.join(input_dir, f0)).loc[:, ~pd.read_csv(os.path.join(input_dir, f0)).columns.duplicated()].add_suffix('_dev1')
    df1 = pd.read_csv(os.path.join(input_dir, f1)).loc[:, ~pd.read_csv(os.path.join(input_dir, f1)).columns.duplicated()].add_suffix('_dev2')
    df0 = df0.rename(columns={'Timestamp_dev1': 'Timestamp'})
    df1 = df1.rename(columns={'Timestamp_dev2': 'Timestamp'})

    # Merge by timestamp
    df = pd.merge(df0, df1, on='Timestamp', how='outer')
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df = df.dropna(subset=['Timestamp']).sort_values('Timestamp')

    # Filter when any QUIC_RST_Count > threshold
    df_filtered = df[
        (df['QUIC_RST_Count_dev1'] > threshold) |
        (df['QUIC_RST_Count_dev2'] > threshold)
    ]

    if df_filtered.empty:
        print(f"  Skipped {fid}: No data above threshold")
        continue

    # Plot
    plt.figure(figsize=(12, 6))
    plt.plot(df_filtered['Timestamp'], df_filtered['QUIC_RST_Count_dev1'], label='Paket QUIC Positif Masuk', marker='o')
    plt.plot(df_filtered['Timestamp'], df_filtered['QUIC_RST_Count_dev2'], label='Connection Close Terkirim', marker='x')
    plt.xlabel('Waktu')
    plt.ylabel('Jumlah Paket QUIC')
    plt.title("Jumlah paket QUIC positif yang masuk dan paket Connection Close terkirim terhadap waktu\n"
              f"Throughput: {throughput} pkt/s | Percobaan nomor {trial}")
    plt.xticks(rotation=45)
    plt.legend()
    plt.tight_layout()

    # Save
    out_file = os.path.join(output_dir, f"quic_rst_plot_{fid}.png")
    plt.savefig(out_file)
    plt.close()
    print(f"  Saved plot to {out_file}")
