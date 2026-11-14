$ErrorActionPreference = 'Stop'
$vmrunPath = 'C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe'
$vmRoot = 'D:\VMWare Virtual Machines'
$running = @(& $vmrunPath list)
if ($LASTEXITCODE -ne 0) { throw 'Cannot read VMware running VM list' }
$vmNames = @('Policy-Server-VM','NPB-VM','Kafka-Broker-VM','Backend-VM','Frontend-VM','NetPro-Test-Gateway','Client-VM','NetPro-Virtual-TAP','Packet-Generator-VM')
$results = foreach ($name in $vmNames) {
    $target = Join-Path (Join-Path $vmRoot $name) ($name + '.vmx')
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Missing exact VM target: $target" }
    if ($running -contains $target) {
        Write-Host "$name : already running"
        [pscustomobject]@{name=$name;exit=0;result='already running'}
        continue
    }
    Write-Host "Starting $name"
    $reply = (& $vmrunPath start $target nogui 2>&1 | Out-String).Trim()
    $code = $LASTEXITCODE
    Write-Host "$name : exit=$code $reply"
    [pscustomobject]@{name=$name;exit=$code;result=$reply}
}
$outDir = Join-Path $PSScriptRoot 'evidence'
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outDir "vm-start-$stamp.json") -Encoding UTF8
Write-Host 'Final running VM list:'
& $vmrunPath list
