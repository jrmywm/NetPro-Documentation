import csv
import random
import string
from datetime import datetime

# Configuration
NUM_ROWS = 2000000
OUTPUT_FILE = 'blacklist_data.csv'

# Categories for random selection
CATEGORIES = ['malware', 'phishing', 'spam', 'fraud', 'other']

# Function to generate random domain
def generate_unique_domain(index):
    # Generate a random string of 5-10 characters
    random_str = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 10)))
    # Add a number to ensure uniqueness
    return f"{random_str}{index+1}.com"

# Function to generate random name
def generate_name():
    first_names = ['John', 'Jane', 'Mike', 'Sarah', 'David', 'Lisa', 'Robert', 'Emma']
    last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller']
    return f"{random.choice(first_names)} {random.choice(last_names)}"

# Function to generate random reason
def generate_reason():
    reasons = [
        "Suspicious activity detected",
        "Known malware distribution",
        "Phishing attempt",
        "Spam source",
        "Fraudulent website",
        "Malicious content",
        "Suspicious behavior",
        "Reported by users"
    ]
    return random.choice(reasons)

# Generate data
data = []
for i in range(NUM_ROWS):
    row = {
        'name': generate_name(),
        'domain': generate_unique_domain(i),
        'reason': generate_reason(),
        'category': random.choice(CATEGORIES),
        'hit_count': random.randint(0, 1000)
    }
    data.append(row)

# Write to CSV
with open(OUTPUT_FILE, 'w', newline='') as csvfile:
    fieldnames = ['name', 'domain', 'reason', 'category', 'hit_count']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    
    writer.writeheader()
    for row in data:
        writer.writerow(row)

print(f"Generated {NUM_ROWS} rows of data in {OUTPUT_FILE}")
