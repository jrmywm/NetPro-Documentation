param([ValidateSet('memory-stage','memory-final-stage')][string]$StageName='memory-stage')
$ErrorActionPreference = 'Stop'
$vmrun = 'C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe'
$running = & $vmrun list
if ($LASTEXITCODE -ne 0) { throw 'Cannot determine running VMs' }
$stage = Join-Path $PSScriptRoot $StageName
$manifest = Get-Content -LiteralPath (Join-Path $stage 'manifest.json') -Raw | ConvertFrom-Json
foreach ($entry in $manifest) {
    if ($running -contains $entry.source) { throw "VM must be off: $($entry.name)" }
    if ((Get-FileHash -LiteralPath $entry.source -Algorithm SHA256).Hash -ne $entry.sha256) { throw "Configuration changed: $($entry.name)" }
    $candidate = Join-Path $stage "$($entry.name).vmx"
    $before = Get-Content -LiteralPath (Join-Path $stage "$($entry.name).original.vmx")
    $after = Get-Content -LiteralPath $candidate
    $changes = @(Compare-Object $before $after)
    if ($changes.Count -ne 2 -or @($changes | Where-Object { $_.InputObject -notmatch '^memsize = "\d+"$' }).Count -ne 0) { throw "Unexpected changes: $($entry.name)" }
}
foreach ($entry in $manifest) {
    Copy-Item -LiteralPath (Join-Path $stage "$($entry.name).vmx") -Destination $entry.source
    Write-Output "$($entry.name): backed-up RAM-only configuration applied"
}
