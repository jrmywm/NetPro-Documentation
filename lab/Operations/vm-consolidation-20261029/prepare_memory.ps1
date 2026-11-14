param([ValidateSet('memory-stage','memory-final-stage')][string]$StageName='memory-stage',[switch]$ProcessorsOnly)
$ErrorActionPreference = 'Stop'
$vmrun = 'C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe'
$vmRoot = 'D:\VMWare Virtual Machines'
$running = & $vmrun list
if ($LASTEXITCODE -ne 0) { throw 'Cannot determine running VMs' }
$stage = Join-Path $PSScriptRoot $StageName
New-Item -ItemType Directory -Path $stage -Force | Out-Null
$targets = @('NPB-VM', 'Policy-Server-VM', 'NetPro-Test-Gateway', 'Client-VM', 'NetPro-Virtual-TAP')
if ($ProcessorsOnly) { $targets = @('NPB-VM','Policy-Server-VM') }
$manifest = @()
foreach ($name in $targets) {
    $source = Join-Path $vmRoot "$name\$name.vmx"
    if ($running -contains $source) { throw "VM must be off: $name" }
    $original = Join-Path $stage "$name.original.vmx"
    $candidate = Join-Path $stage "$name.vmx"
    if ((Test-Path -LiteralPath $original) -or (Test-Path -LiteralPath $candidate)) { throw "Stage already exists: $name" }
    Copy-Item -LiteralPath $source -Destination $original
    Copy-Item -LiteralPath $source -Destination $candidate
    $manifest += [pscustomobject]@{name=$name;source=$source;sha256=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash}
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stage 'manifest.json') -Encoding UTF8
$manifest | Select-Object name,sha256 | Format-Table -AutoSize
