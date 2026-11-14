#!/bin/bash

# Number of runs to average
runs=500
total_time=0

# Run the command multiple times and accumulate the total time
for ((i=1; i<=runs; i++)); do
    # Use 'time' to run the command and capture the output
    result=$( { time timeout 2m ./packet-processor; } 2>&1 )

    # Extract the real time from the output
    real_time=$(echo "$result" | grep real | awk '{print $2}')

    # Parse minutes, seconds, and milliseconds
    minutes=$(echo "$real_time" | cut -d'm' -f1)
    seconds=$(echo "$real_time" | cut -d'm' -f2 | cut -d's' -f1)
    milliseconds=$(echo "$real_time" | cut -d'.' -f2 | cut -d's' -f1)

    # Convert to milliseconds (1 minute = 60 seconds, 1 second = 1000 milliseconds)
    # Use bc for floating-point arithmetic
    total_milliseconds=$(echo "$minutes * 60 * 1000 + $seconds * 1000 + $milliseconds" | bc)

    # Add to total time
    total_time=$(echo "$total_time + $total_milliseconds" | bc)

    echo "Run $i: Duration = $total_milliseconds milliseconds"
done

# Calculate average time in milliseconds
average_time=$(echo "scale=2; $total_time / $runs" | bc)

echo "Average time over $runs runs: $average_time milliseconds"