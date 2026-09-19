[CmdletBinding()]
param(
    [ValidateSet("Blocked", "Allowed", "Browser")]
    [string]$Mode = "Blocked",

    [ValidateRange(1, 50)]
    [int]$Attempts = 10,

    [string]$Proxy = "http://192.168.80.128:8888"
)

$ErrorActionPreference = "Stop"

if ($Mode -eq "Browser") {
    $profile = Join-Path $env:TEMP ("netpro-browser-test-" + [guid]::NewGuid().ToString("N"))
    $url = "https://www.google.com/?netprobrowser=$(Get-Random)"

    Start-Process msedge.exe -ArgumentList @(
        "--user-data-dir=`"$profile`""
        "--proxy-server=$Proxy"
        "--disable-quic"
        "--no-first-run"
        "--new-window"
        $url
    )

    Write-Host "Started isolated Edge profile: $profile"
    Write-Host "Blocked mode: Google must remain unavailable."
    exit 0
}

$failures = 0
for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
    $url = "https://www.google.com/?netpro=$attempt-$(Get-Random)"

    $httpCode = & curl.exe `
        -sS `
        -o NUL `
        --write-out "%{http_code}" `
        --proxy $Proxy `
        --connect-timeout 5 `
        --max-time 10 `
        $url

    $exitCode = $LASTEXITCODE
    $httpCode = ([string]$httpCode).Trim()
    $isExpected = if ($Mode -eq "Blocked") {
        $exitCode -ne 0
    }
    else {
        $exitCode -eq 0 -and $httpCode -match '^[23][0-9]{2}$'
    }

    if ($isExpected) {
        Write-Host "PASS attempt $attempt (curl exit $exitCode, HTTP $httpCode)"
    }
    else {
        Write-Host "FAIL attempt $attempt (curl exit $exitCode, HTTP $httpCode)"
        $failures++
    }
}

if ($failures -gt 0) {
    throw "$failures of $Attempts attempts did not match expected $Mode behavior."
}

Write-Host "All $Attempts $Mode checks passed."
