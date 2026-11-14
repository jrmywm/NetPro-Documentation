import os
import pandas as pd
import re
import matplotlib.pyplot as plt
import numpy as np

# Configuration
input_dir = "."
output_file = "summary.txt"
plot_file = "success_rate_vs_throughput.png"

def extract_id(filename):
    match = re.search(r'_(\d+(?:-\d+)?)', filename)
    return match.group(1) if match else None

def parse_throughput_and_trial(fid):
    parts = fid.split("-")
    throughput = int(parts[0]) * 10
    trial = int(parts[1]) if len(parts) > 1 else 1
    return throughput, trial

# Collect and process files
files = [f for f in os.listdir(input_dir) if f.endswith('.csv')]
port0_files = {extract_id(f): f for f in files if "port0" in f}
port1_files = {extract_id(f): f for f in files if "port1" in f}

entries = []
for fid in sorted(set(port0_files) & set(port1_files)):
    df0 = pd.read_csv(os.path.join(input_dir, port0_files[fid]))
    df1 = pd.read_csv(os.path.join(input_dir, port1_files[fid]))
    
    throughput, trial = parse_throughput_and_trial(fid)
    packet_sum = df0['QUIC_RST_Count'].sum()
    rst_sum = df1['QUIC_RST_Count'].sum()
    success_rate = (rst_sum / packet_sum * 100) if packet_sum > 0 else 0
    
    entries.append({
        "throughput": throughput,
        "trial": trial,
        "success_rate": success_rate
    })

# Prepare data for summary and plot
throughput_groups = {}
for entry in entries:
    tp = entry["throughput"]
    if tp not in throughput_groups:
        throughput_groups[tp] = []
    throughput_groups[tp].append(entry["success_rate"])

throughputs = sorted(throughput_groups.keys())
avg_rates = [np.mean(throughput_groups[tp]) for tp in throughputs]
std_devs = [np.std(throughput_groups[tp]) for tp in throughputs]

# Generate enhanced summary file with std dev
with open(output_file, "w") as f:
    # Write header
    f.write("Throughput Analysis Summary\n")
    f.write("="*30 + "\n\n")
    
    # Write individual trials first
    f.write("Individual Trial Results:\n")
    f.write("-"*30 + "\n")
    for entry in sorted(entries, key=lambda x: (x["throughput"], x["trial"])):
        f.write(f"Throughput: {entry['throughput']} pkt/s | Trial: {entry['trial']}\n"
                f"Success rate: {entry['success_rate']:.1f}%\n"
                "-------------------------\n")
    
    # Write summary statistics
    f.write("\nSummary Statistics by Throughput:\n")
    f.write("-"*30 + "\n")
    for tp, avg, std in zip(throughputs, avg_rates, std_devs):
        f.write(f"Throughput: {tp} pkt/s\n"
                f"Average success rate: {avg:.1f}%\n"
                f"Standard deviation: {std:.1f}%\n"
                f"Trials: {len(throughput_groups[tp])}\n"
                "-------------------------\n")

# Create plot (unchanged from your version)
plt.figure(figsize=(10, 6))
plt.plot(throughputs, avg_rates, 'o-', label='Average Success Rate')

# Add data point labels
for tp, rate in zip(throughputs, avg_rates):
    plt.text(tp, rate + 2, f'{rate:.1f}%', 
             ha='center', va='bottom', fontsize=9)

# Customize axes
plt.xticks(throughputs)
plt.yticks(np.arange(0, 101, 10))
plt.xlim(min(throughputs) - 10, max(throughputs) + 10)
plt.ylim(0, 100)

# Formatting
plt.xlabel("Throughput (packets/second)", fontsize=12)
plt.ylabel("Success Rate (%)", fontsize=12)
plt.title("QUIC Connection Close Success Rate", fontsize=14)
plt.grid(True, linestyle='--', alpha=0.7)
plt.legend(loc='best')

# Save and close
plt.tight_layout()
plt.savefig(plot_file, dpi=300, bbox_inches='tight')
plt.close()