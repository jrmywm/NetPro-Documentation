npm install --save express multer fast-csv json2csv sequelize pg dotenv nodemon
# Skripsi

# Sistem Manajemen Blacklist Domain

Sistem ini dirancang untuk mengelola dan memproses daftar domain yang masuk ke dalam blacklist. Sistem mendukung upload file CSV dalam jumlah besar, validasi data, dan penanganan error dengan baik.

## Fitur Utama

- Upload file CSV dengan jumlah data besar
- Validasi data otomatis
- Penanganan error dan failed records
- Export data ke CSV
- API untuk manajemen blacklist
- Statistik upload dan processing
- Retry mechanism untuk failed records

## Persyaratan Sistem

- Node.js (versi 14.x atau lebih baru)
- PostgreSQL (versi 12.x atau lebih baru)
- NPM (versi 6.x atau lebih baru)

## Struktur Folder

```
├── app/                    # Folder utama aplikasi
│   ├── config/            # Konfigurasi aplikasi
│   │   ├── db.config.js   # Konfigurasi database
│   │   └── multer.config.js # Konfigurasi file upload
│   ├── controllers/       # Controller untuk menangani request
│   │   ├── job.controller.js
│   │   └── failedUpload.controller.js
│   ├── models/           # Model database
│   │   ├── uploadJob.model.js
│   │   ├── failedUpload.model.js
│   │   └── blacklist.model.js
│   ├── routes/           # Definisi routes
│   │   ├── job.routes.js
│   │   └── failedUpload.routes.js
│   ├── services/         # Business logic
│   │   ├── job.service.js
│   │   └── failedUpload.service.js
│   ├── utils/            # Utility functions
│   │   ├── Response.utilities.js
│   │   └── logger.js
│   └── migrations/       # Database migrations
├── uploads/              # Folder untuk menyimpan file yang diupload
├── logs/                 # Folder untuk menyimpan log files
├── .env                  # File konfigurasi environment
├── .gitignore           # File untuk mengabaikan file/folder dari git
├── package.json         # Dependencies dan scripts
├── index.js             # Entry point aplikasi
└── README.md            # Dokumentasi project
```

## Instalasi

1. Clone repository:
```bash
git clone [URL_REPOSITORY]
cd [NAMA_FOLDER]
```

2. Install dependencies:
```bash
npm install
```

3. Install dependencies tambahan yang dibutuhkan:
```bash
npm install --save express multer fast-csv json2csv sequelize pg dotenv nodemon
```

## Konfigurasi

1. Buat file `.env` di root project dengan format berikut:
```env
# Database Configuration
DB_HOST=
DB_PORT=
DB_NAME=
DB_USER=
DB_PASSWORD=

# Server Configuration
PORT=
CORS_ORIGIN=

# File Upload Configuration
MAX_SINGLE_FILE_SIZE=
MAX_TOTAL_UPLOAD_SIZE=
ALLOWED_FILE_EXTENSIONS=
```

2. Pastikan folder upload sudah dibuat:
```bash
mkdir uploads
```

## Struktur Database

### Tabel upload_jobs
- id (Primary Key)
- filename (String)
- status (String)
- total_records (Integer)
- processed_records (Integer)
- unique_domains (Integer)
- duplicate_domains (Integer)
- failed_records (Integer)
- processing_time (Float)
- error_message (Text)
- retry_count (Integer)
- last_retry_at (Timestamp)
- createdAt (Timestamp)
- updatedAt (Timestamp)

### Tabel failed_uploads
- id (Primary Key)
- job_id (Foreign Key)
- row_number (Integer)
- name (String)
- domain (String)
- reason (String)
- category (String)
- hit_count (Integer)
- error_message (Text)
- original_data (JSONB)
- createdAt (Timestamp)
- updatedAt (Timestamp)

### Tabel blacklists
- id (Primary Key)
- domain (String)
- name (String)
- reason (String)
- category (String)
- hit_count (Integer)
- createdAt (Timestamp)
- updatedAt (Timestamp)

## Menjalankan Aplikasi

1. Development mode:
```bash
npm run dev
```

2. Production mode:
```bash
npm start
```

## API Endpoints

### Upload Jobs
- `GET /api/jobs` - Mendapatkan daftar semua jobs
- `GET /api/jobs/:id` - Mendapatkan detail job
- `POST /api/jobs/upload` - Upload file CSV baru
- `GET /api/jobs/:id/download` - Download hasil processing

### Failed Records
- `GET /api/jobs/:jobId/failed-records` - Mendapatkan daftar failed records
- `GET /api/jobs/:jobId/failed-records/download` - Download failed records
- `POST /api/jobs/:jobId/failed-records/process-all` - Proses semua failed records
- `PUT /api/jobs/:jobId/failed-records/:recordId` - Update failed record

## Format File CSV

File CSV yang diupload harus memiliki format berikut:
```csv
name,domain,reason,category,hit_count
```

Contoh:
```csv
name,domain,reason,category,hit_count
Example Domain,example.com,Malicious content,spam,100
```

## Penanganan Error

Sistem menangani beberapa jenis error:
1. Validasi data (domain kosong, format tidak sesuai)
2. Duplikasi domain
3. Error database
4. Error file processing

## Monitoring dan Logging

- Log file tersedia di folder `logs/`
- Statistik processing tersedia di database
- Error tracking melalui error_message di tabel jobs

## Keamanan

- Validasi input untuk mencegah SQL injection
- Pembatasan ukuran file
- Validasi tipe file
- Sanitasi data

## Troubleshooting

1. Error koneksi database:
   - Periksa konfigurasi database di .env
   - Pastikan PostgreSQL berjalan
   - Periksa firewall settings

2. Error upload file:
   - Periksa permission folder uploads
   - Pastikan ukuran file tidak melebihi batas
   - Validasi format file

3. Error processing:
   - Periksa log file
   - Validasi format data
   - Periksa koneksi database

## Kontribusi

1. Fork repository
2. Buat branch fitur baru
3. Commit perubahan
4. Push ke branch
5. Buat Pull Request

## Lisensi

[Masukkan informasi lisensi di sini]

