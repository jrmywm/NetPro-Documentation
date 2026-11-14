import pandas as pd
import matplotlib.pyplot as plt
import os

# Settings
output_dir = "output"
os.makedirs(output_dir, exist_ok=True)
threshold = 10  # adjust as needed

# Load CSV files
# Load the CSVs
csv1 = pd.read_csv("packet_stats_port0_10-1.csv")
csv2 = pd.read_csv("packet_stats_port1_10-1.csv")

# Remove duplicated columns from CSV1
csv1 = csv1.loc[:, ~csv1.columns.duplicated()]

# Suffix to distinguish columns
csv1 = csv1.add_suffix('_dev1')
csv2 = csv2.add_suffix('_dev2')

# Rename Timestamp back
csv1 = csv1.rename(columns={'Timestamp_dev1': 'Timestamp'})
csv2 = csv2.rename(columns={'Timestamp_dev2': 'Timestamp'})

# Merge both CSVs
merged = pd.merge(csv1, csv2, on='Timestamp', how='outer')
merged['Timestamp'] = pd.to_datetime(merged['Timestamp'])
merged = merged.sort_values('Timestamp')

# Filter: Show only rows where either device has QUIC_RST_Count > threshold
filtered = merged[
    (merged['QUIC_RST_Count_dev1'] > threshold) |
    (merged['QUIC_RST_Count_dev2'] > threshold)
]

# Plot
plt.figure(figsize=(12, 6))
plt.plot(filtered['Timestamp'], filtered['QUIC_RST_Count_dev1'], label='Device 1 (Port 0)', marker='o')
plt.plot(filtered['Timestamp'], filtered['QUIC_RST_Count_dev2'], label='Device 2 (Port 1)', marker='x')
plt.xlabel('Timestamp')
plt.ylabel('QUIC_RST_Count')
plt.title(f'QUIC_RST_Count Over Time (Only When > {threshold})')
plt.legend()
plt.grid(True)
plt.xticks(rotation=45)
plt.tight_layout()

# Save plot
plot_path = os.path.join(output_dir, "quic_rst_filtered.png")
plt.savefig(plot_path)
print(f"Filtered plot saved to {plot_path}")
