#!/bin/bash

# Create directory if it doesn't exist
mkdir -p telemetry

# CSV file path
CSV_FILE="telemetry/system_150-3.csv"

# Write CSV header if file doesn't exist or is empty
if [ ! -f "$CSV_FILE" ] || [ ! -s "$CSV_FILE" ]; then
    # Get number of CPU cores to create core columns
    cores=$(grep -c ^processor /proc/cpuinfo)
    header="timestamp"
    for ((i=0; i<cores; i++)); do
        header+=",core${i}_usage(%)"
    done
    header+=",memory_used(MiB),memory_used(%)"
    echo "$header" > "$CSV_FILE"
fi

# Function to get CPU usage per core
get_cpu_usage() {
    # Get CPU usage per core as comma-separated string without trailing comma
mpstat -P ALL 1 1 | awk '/Average:/ && $2 ~ /[0-9]/ {printf "%.2f,", 100 - $NF}' | sed 's/,$//'
}


# Function to get memory usage
get_memory_usage() {
    # Get memory usage in MiB and percentage
    read mem_total mem_used <<< $(free -m | awk '/Mem:/ {print $2, $3}')
    mem_percent=$(awk "BEGIN {printf \"%.2f\", ($mem_used/$mem_total)*100}")
    echo "$mem_used,$mem_percent"
}

# Main monitoring function
monitor_resources() {
    while true; do
        # Get current timestamp in specified format
        timestamp=$(date +"%Y-%m-%d %H:%M:%S")
        
        # Get CPU and memory data
        cpu_data=$(get_cpu_usage)
        mem_data=$(get_memory_usage)
        
        # Write to CSV file
        echo "$timestamp,$cpu_data,$mem_data" >> "$CSV_FILE"
        
        # Wait for 1 second before next measurement
        sleep 1
    done
}

# Start monitoring
monitor_resources