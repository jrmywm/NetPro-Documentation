$ErrorActionPreference = 'Stop'
$vmrun = 'C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe'
$root = 'D:\VMWare Virtual Machines'
$running = & $vmrun list
if ($LASTEXITCODE -ne 0) { throw 'Cannot read running VMs' }
# Management is stopped last; Policy uses its database-preservation guard.
foreach ($name in @('Client-VM','NetPro-Test-Gateway','NetPro-Virtual-TAP','NPB-VM','Policy-Server-VM','Backend-VM')) {
    $path = Join-Path $root "$name\$name.vmx"
    if (-not ($running -contains $path)) { Write-Output "$name already off"; continue }
    & $vmrun stop $path soft
    if ($LASTEXITCODE -ne 0) { throw "Graceful stop failed for $name; no force-reset or hard stop was attempted" }
    Write-Output "$name gracefully stopped"
}
