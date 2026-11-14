param([switch]$IncludePacketGenerator)
$ErrorActionPreference = 'Stop'
$vmrun = 'C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe'
$root = 'D:\VMWare Virtual Machines'
$running = & $vmrun list
if ($LASTEXITCODE -ne 0) { throw 'Cannot read running VMs' }
foreach ($legacy in @('Kafka-Broker-VM', 'Frontend-VM')) {
    $legacyPath = Join-Path $root "$legacy\$legacy.vmx"
    if ($running -contains $legacyPath) { throw "Stop legacy $legacy before using the consolidated setup. Kafka's old IP is owned by Management." }
}
$names = @('Backend-VM','Policy-Server-VM','NPB-VM','NetPro-Virtual-TAP','NetPro-Test-Gateway','Client-VM')
if ($IncludePacketGenerator) {
    $generatorPath = Join-Path $root 'Packet-Generator-VM\Packet-Generator-VM.vmx'
    if (-not ($running -contains $generatorPath)) {
        $os = Get-CimInstance Win32_OperatingSystem
        if (($os.FreePhysicalMemory / 1MB) -lt 7) { throw 'Packet Generator still has 6.06 GiB assigned. Less than 7 GiB host memory is available; leave it off or review its separate RAM needs first.' }
    }
    $names += 'Packet-Generator-VM'
}
foreach ($name in $names) {
    $path = Join-Path $root "$name\$name.vmx"
    if (-not (Test-Path -LiteralPath $path)) { throw "VM configuration missing: $path" }
    if ($running -contains $path) { Write-Output "$name already running"; continue }
    & $vmrun start $path nogui
    if ($LASTEXITCODE -ne 0) { throw "Failed to start $name; previously started VMs were left running" }
    Write-Output "$name started"
}
Write-Output 'Dashboard: https://192.168.31.35:3005'
Write-Output 'VM start success does not confirm application health; allow startup and verify services.'
