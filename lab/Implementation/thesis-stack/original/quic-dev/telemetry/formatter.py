import csv
import os

# List file yang ingin diperbaiki
files_to_process = [

    'system_100-1.csv',
    'system_100-2.csv',
    'system_100-3.csv',
    'system_150-1.csv',
    'system_150-2.csv',
    'system_150-3.csv'
]

# Buat folder output jika belum ada
output_folder = 'fixed_csvs'
os.makedirs(output_folder, exist_ok=True)

def fix_csv(input_file, output_file):
    with open(input_file, 'r', newline='') as infile, open(output_file, 'w', newline='') as outfile:
        reader = csv.reader(infile)
        writer = csv.writer(outfile)
        
        for i, row in enumerate(reader):
            if i == 0:
                writer.writerow(row)  # Tulis header
            else:
                fixed_row = [row[0]]  # Timestamp tetap

                # Gabungkan tiap dua kolom CPU usage
                for j in range(1, 17, 2):
                    fixed_value = row[j].strip() + "." + row[j + 1].strip()
                    fixed_row.append(fixed_value)

                # Memory used (MiB): kolom ke-17
                fixed_row.append(row[17].strip())

                # Memory used (%): kolom ke-18 dan 19 digabung
                fixed_row.append(row[18].strip() + "." + row[19].strip())

                writer.writerow(fixed_row)

# Jalankan untuk semua file
for file in files_to_process:
    output_path = os.path.join(output_folder, file.replace(".csv", "_fixed.csv"))
    print(f"Memproses {file} → {output_path}")
    fix_csv(file, output_path)

print("✅ Semua file selesai diperbaiki dan disimpan di folder 'fixed_csvs'.")
