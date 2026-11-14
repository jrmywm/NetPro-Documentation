$ErrorActionPreference = 'Stop'
$vmrun = 'C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe'
$running = & $vmrun list
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect running VMs' }
$inventory = foreach ($file in Get-ChildItem -LiteralPath 'D:\VMWare Virtual Machines' -Recurse -Filter '*.vmx' -File) {
    $text = Get-Content -LiteralPath $file.FullName -Raw
    $match = [regex]::Match($text, '(?m)^memsize = "(\d+)"')
    if (-not $match.Success) { throw "No memory size in $($file.FullName)" }
    [pscustomobject]@{Name=$file.BaseName;Path=$file.FullName;RAM_MiB=[int]$match.Groups[1].Value;Running=($running -contains $file.FullName)}
}
$os = Get-CimInstance Win32_OperatingSystem
$result = [pscustomobject]@{
    CollectedUTC=(Get-Date).ToUniversalTime().ToString('o')
    HostRAM_GiB=[math]::Round($os.TotalVisibleMemorySize/1MB,2)
    HostAvailableRAM_GiB=[math]::Round($os.FreePhysicalMemory/1MB,2)
    RunningCount=@($inventory | Where-Object Running).Count
    RunningAssignedRAM_GiB=(@($inventory | Where-Object Running | Measure-Object RAM_MiB -Sum).Sum/1024)
    VMs=@($inventory)
}
$out = Join-Path $PSScriptRoot ('evidence\host-final-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '.json')
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $out -Encoding UTF8
$inventory | Select-Object Name,RAM_MiB,Running | Format-Table -AutoSize
Write-Output "Running VM count: $($result.RunningCount); assigned RAM: $($result.RunningAssignedRAM_GiB) GiB; host available: $($result.HostAvailableRAM_GiB) GiB"
Write-Output "Evidence: $out"
