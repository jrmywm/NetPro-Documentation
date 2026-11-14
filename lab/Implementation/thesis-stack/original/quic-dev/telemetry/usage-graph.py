import os
import pandas as pd
import matplotlib.pyplot as plt
import re
from matplotlib.ticker import MaxNLocator
from datetime import timedelta

# Configuration
input_dir = "."  # Current directory
fixed_csvs_dir = "fixed_csvs"  # System stats directory
output_dir = "combined_system_plots"
testing_threshold_ratio = 0.5  # Testing active when packets > 50% of throughput
os.makedirs(output_dir, exist_ok=True)

def extract_port_id(filename):
    """Extract ID from port filename (e.g., '10-1' from 'packet_stats_port0_10-1.csv')"""
    match = re.search(r'_(\d+-\d+)\.csv$', filename) or re.search(r'_(\d+)\.csv$', filename)
    return match.group(1) if match else None

def extract_system_id(filename):
    """Extract ID from system filename (e.g., '10-1' from 'system_10-1_fixed.csv')"""
    match = re.search(r'_(\d+-\d+)_fixed\.csv$', filename) or re.search(r'_(\d+)_fixed\.csv$', filename)
    return match.group(1) if match else None

def parse_throughput(fid):
    """Parse throughput from ID (e.g., '10-1' → 100 pkt/s)"""
    return int(fid.split("-")[0]) * 10

def find_crossing_times(df, core_col, threshold=50):
    """Find timestamps where core crosses threshold (both rising and falling) after 1 second from start"""
    df = df.copy()
    df['above_threshold'] = df[core_col] > threshold
    df['crossing'] = df['above_threshold'].ne(df['above_threshold'].shift())

    # Get the earliest timestamp in the data
    min_time = df['Timestamp'].min()
    # Calculate 1 second after the earliest timestamp
    cutoff_time = min_time + timedelta(seconds=1)

    rising_times = []
    falling_times = []

    for i, row in df.iterrows():
        if row['crossing'] and row['Timestamp'] >= cutoff_time:
            if row['above_threshold']:
                rising_times.append(row['Timestamp'])  # Crossing up to >50%
            else:
                falling_times.append(row['Timestamp'])  # Crossing down to <=50%

    return rising_times, falling_times

def main():
    print("Starting processing...")

    # Get all relevant files
    port_files = [f for f in os.listdir(input_dir) if f.endswith('.csv') and ('port0' in f)]
    
    try:
        system_files = [f for f in os.listdir(fixed_csvs_dir) if f.endswith('.csv') and 'fixed' in f]
    except FileNotFoundError:
        print(f"Error: Directory '{fixed_csvs_dir}' not found")
        return

    # Organize files by ID
    port_data = {extract_port_id(f): f for f in port_files if extract_port_id(f)}
    system_data = {extract_system_id(f): os.path.join(fixed_csvs_dir, f) for f in system_files if extract_system_id(f)}

    # Find common test cases
    common_ids = sorted(set(port_data) & set(system_data))
    
    if not common_ids:
        print("No matching test cases found between port and system files")
        return

    print(f"Found {len(common_ids)} test cases to process")

    for fid in common_ids:
        print(f"\nProcessing test case {fid}")
        throughput = parse_throughput(fid)

        try:
            # Load QUIC data to determine testing periods
            df_quic = pd.read_csv(port_data[fid])
            df_quic['Timestamp'] = pd.to_datetime(df_quic['Timestamp'], errors='coerce')
            df_quic.dropna(subset=['Timestamp'], inplace=True)

            # Load system stats
            df_sys = pd.read_csv(system_data[fid])
            df_sys['Timestamp'] = pd.to_datetime(df_sys['timestamp'], errors='coerce')
            df_sys.dropna(subset=['Timestamp'], inplace=True)

        except Exception as e:
            print(f"Error loading files: {e}")
            continue

        # Get CPU columns
        cpu_cols = [col for col in df_sys.columns if 'core' in col and '%' in col]
        n_cores = len(cpu_cols)

        # Find Core 1 column (assuming it's named like 'core1_usage%')
        core1_col = next((col for col in cpu_cols if 'core1' in col.lower()), None)

        # Find threshold crossing times for Core 1 (only after 1 second from start)
        rising_times, falling_times = [], []
        if core1_col:
            rising_times, falling_times = find_crossing_times(df_sys, core1_col, threshold=50)
            print(f"  Found {len(rising_times)} rising and {len(falling_times)} falling crossings after 1 second")

        # Create figure with 3x3 subplot grid
        fig, axes = plt.subplots(nrows=3, ncols=3, figsize=(24, 18))

        # Extract the last digit from fid for "Percobaan ke X"
        trial_number = fid.split("-")[-1] if "-" in fid else fid[-1]

        # Set the title with both throughput and trial number
        fig.suptitle(f"Grafik Penggunaan Resource Sistem\nThroughput: {throughput} pkt/s - Percobaan ke {trial_number}",
                     y=0.95, fontsize=20)

        # Highlight testing periods
        testing_periods = df_quic['QUIC_RST_Count'] > (throughput * testing_threshold_ratio)
        testing_spans = []
        if testing_periods.any():
            in_test = False
            start_time = None
            for time, is_testing in zip(df_quic['Timestamp'], testing_periods):
                if is_testing and not in_test:
                    start_time = time
                    in_test = True
                elif not is_testing and in_test:
                    testing_spans.append((start_time, time))
                    in_test = False
            if in_test:  # Handle ongoing testing at end
                testing_spans.append((start_time, df_quic['Timestamp'].iloc[-1]))

        # Determine policy server active period (between first rise and first fall)
        policy_active_span = []
        if rising_times and falling_times:
            # Use the first rising time and first falling time after it
            first_rise = rising_times[0]
            # Find the first fall that comes after the first rise
            first_fall = next((fall for fall in falling_times if fall > first_rise), None)
            if first_fall:
                policy_active_span = [(first_rise, first_fall)]
                print(f"  Policy Server active between {first_rise} and {first_fall}")

        # Memory usage data
        mem_mib_col = next((col for col in df_sys.columns if 'memory_used(MiB)' in col), None)

        # Calculate memory range for this test case (only if memory column exists)
        if mem_mib_col:
            mem_min = df_sys[mem_mib_col].min()
            mem_max = df_sys[mem_mib_col].max()
            # Add some padding (5% below min, 5% above max)
            mem_range = mem_max - mem_min
            mem_y_min = mem_min - (mem_range * 0.05)
            mem_y_max = mem_max + (mem_range * 0.05)
            print(f"  Memory range: {mem_min:.1f} - {mem_max:.1f} MiB")

        # Collect legend elements for the global legend
        global_legend_elements = []
        global_legend_labels = []

        for i, col in enumerate(cpu_cols):
            ax = axes[i // 3, i % 3]

            # Plot CPU usage
            ax.plot(df_sys['Timestamp'], df_sys[col], label=f'Penggunaan CPU Core {col.split("_")[0][4:]}')
            ax.set_ylabel('Penggunaan CPU (%)')
            max_cpu = df_sys[col].max()

            # Add dotted horizontal line at 100% (only add to global legend once)
            line_100 = ax.axhline(y=100, color='black', linestyle=':', linewidth=2, alpha=0.5)
            if i == 0:  # Only add to legend once
                global_legend_elements.append(line_100)
                global_legend_labels.append('100% CPU')

            ax.set_ylim(0, 105)  # Set y-axis limit to 5% above max value
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))

            # Highlight testing periods (green) - only add to global legend once
            for j, (start, end) in enumerate(testing_spans):
                span_testing = ax.axvspan(start, end, color='limegreen', alpha=0.15)
                if i == 0 and j == 0:  # Only add to legend once
                    global_legend_elements.append(span_testing)
                    global_legend_labels.append('Pengujian Aktif')

            # Highlight policy server active period (blue) - only add to global legend once
            for j, (start, end) in enumerate(policy_active_span):
                span_policy = ax.axvspan(start, end, color='yellow', alpha=0.1)
                if i == 0 and j == 0:  # Only add to legend once
                    global_legend_elements.append(span_policy)
                    global_legend_labels.append('Policy Server Aktif')

            # Plot memory usage on secondary axis if available
            if mem_mib_col:
                ax2 = ax.twinx()
                mem_line = ax2.plot(df_sys['Timestamp'], df_sys[mem_mib_col], color='crimson', linestyle='--')[0]
                if i == 0:  # Only add to legend once
                    global_legend_elements.append(mem_line)
                    global_legend_labels.append('Penggunaan Memori')
                
                ax2.set_ylabel('Penggunaan Memori (MiB)', color='crimson')
                ax2.tick_params(axis='y', labelcolor='crimson')
                # Set y-axis based on actual min/max values with padding
                ax2.set_ylim(mem_y_min, mem_y_max)

            # Add individual legend for CPU core usage only
            ax.legend(loc='upper left')
            ax.grid(True, alpha=0.3)
            ax.set_title(f'Core {col.split("_")[0][4:]}')

        # Hide unused subplots
        for i in range(n_cores, 9):
            ax = axes[i // 3, i % 3]
            ax.axis('off')

        # Add global legend at bottom right of the figure (excluding CPU core usage)
        fig.legend(global_legend_elements, global_legend_labels, 
                  loc='lower right', bbox_to_anchor=(0.95, 0.15), 
                  fontsize=30, frameon=True, fancybox=True, shadow=True)

        # Formatting
        fig.tight_layout(rect=[0, 0.1, 1, 0.9])  # Adjust layout to fit suptitle and legend
        plt.xticks(rotation=45)

        # Save plot
        out_file = os.path.join(output_dir, f"system_resources_{fid}.png")
        plt.savefig(out_file, bbox_inches='tight', dpi=300)
        plt.close()

        print(f"  Saved plot to {out_file}")

if __name__ == "__main__":
    main()