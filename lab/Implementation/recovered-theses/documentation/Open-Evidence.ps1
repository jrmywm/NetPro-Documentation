param([ValidateSet('live','luthfi','rafie','packets','benchmark')][string]$Page='live')
$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = "NetPro Evidence - $Page"
try {
    $raw = $Host.UI.RawUI
    $width = [Math]::Min(116, $raw.MaxPhysicalWindowSize.Width)
    $height = [Math]::Min(42, $raw.MaxPhysicalWindowSize.Height)
    $raw.BufferSize = New-Object System.Management.Automation.Host.Size ($width, 1000)
    $raw.WindowSize = New-Object System.Management.Automation.Host.Size ($width, $height)
    [Console]::CursorVisible = $false
} catch { }
Clear-Host
$console = Join-Path $PSScriptRoot 'evidence_console.py'
python -X utf8 -u $console $Page
if ($LASTEXITCODE -ne 0) { Write-Host 'Evidence command failed. Do not use this as passing evidence.' -ForegroundColor Red }
Write-Host ''
Write-Host 'Actual console output. Press any key to close this evidence window.' -ForegroundColor DarkGray
try { [Console]::CursorVisible = $false; $null = [Console]::ReadKey($true) } catch { }
