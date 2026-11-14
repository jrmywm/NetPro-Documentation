# Actual terminal screenshots for the RST test

Open Windows PowerShell. These commands display saved evidence; they do not send traffic or change policies. Use Windows Snipping Tool (Win+Shift+S) to capture the visible terminal including the command and output. Identify these as saved test results, not a newly running test.

## Screenshot 1 — all deny and allow results

```powershell
Set-Location 'C:\Users\jim\Documents\NetPro\Testing\tap-stress'
$rstEvidence = Join-Path $PWD 'evidence\rst-stress-20261010T130008Z'
Get-ChildItem -LiteralPath $rstEvidence -Filter 'c*-*.json' |
  ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json } |
  Sort-Object concurrency, mode |
  Select-Object concurrency, mode, attempted, expected, client_rst_packets, capture_kernel_drops, passed |
  Format-Table -AutoSize
```

Expected: six rows (4, 8 and 16 clients × deny/allow), attempted=32, expected=32, passed=True, capture drops=0; deny RST=32, allow RST=0.

Suggested caption: Pengujian deny–allow TLS pada 4, 8, dan 16 client bersamaan: 96/96 koneksi ditolak dengan RST dan 96/96 koneksi kembali berhasil setelah policy dihapus.

## Screenshot 2 — denied trials and reset coverage

```powershell
$denyResult = Get-Content -LiteralPath (Join-Path $rstEvidence 'c16-deny.json') -Raw | ConvertFrom-Json
$denyResult | Select-Object mode, concurrency, attempted, expected, client_rst_packets, all_trials_have_client_rst, capture_kernel_drops, passed | Format-List
$denyResult.rows | Select-Object -First 8 trial, curl_rc, http, elapsed_s, local_port, expected | Format-Table -AutoSize
```

Expected: all_trials_have_client_rst=True, client_rst_packets=32; displayed trials have curl_rc 35 or 56, HTTP 000, expected=True. Connection timeouts do not count as successful blocks.

Suggested caption: Bukti penolakan TLS dengan reset arah client untuk setiap koneksi uji pada concurrency 16.

## Screenshot 3 — connections recover after rule deletion

```powershell
$allowResult = Get-Content -LiteralPath (Join-Path $rstEvidence 'c16-allow.json') -Raw | ConvertFrom-Json
$allowResult | Select-Object mode, concurrency, attempted, expected, client_rst_packets, capture_kernel_drops, passed | Format-List
$allowResult.rows | Select-Object -First 8 trial, curl_rc, http, elapsed_s, expected | Format-Table -AutoSize
```

Expected: 32/32 expected successes, RST=0; displayed trials curl_rc=0, HTTP=200.

Suggested caption: Setelah policy sementara dihapus, seluruh 32 koneksi pada concurrency 16 berhasil dengan HTTP 200 tanpa RST arah client pada capture.

## Optional — verify PCAP integrity

```powershell
$actualHash = (Get-FileHash -LiteralPath (Join-Path $rstEvidence 'c16-deny.pcap') -Algorithm SHA256).Hash.ToLower()
[pscustomobject]@{ File='c16-deny.pcap'; SHA256=$actualHash; MatchesRecorded=($actualHash -eq $denyResult.pcap_sha256) } | Format-List
```

This verifies the retained capture, not every aspect of packet processing.

## Fresh live rerun (changes temporary test state)

Only when the required VMs are on and no other demo owns the test listeners or return path:

```powershell
Set-Location 'C:\Users\jim\Documents\NetPro\Testing\tap-stress'
python -u .\run_rst_stress.py
```

This creates and deletes one temporary SNI policy per concurrency level and enables the guarded return path temporarily. It checks the exact expected API and SQLite baseline, stops on failure, and writes a NEW timestamped evidence directory. Capture the real terminal output. Do not reuse the archived evidence folder variable for the new run.

Boundaries: bounded bursts with existing reset policing, TLS 1.2 and new connections only. No maximum-throughput, physical fail-open, or live QUIC claim.
