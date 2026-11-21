#Requires -Version 5.1
<#
.SYNOPSIS
    Launches Cloud Save Sync, finding Python reliably
    (py launcher -> known install -> PATH), even if the Microsoft Store stub shadows python.

    .\run.ps1                 -> GUI
    .\run.ps1 --cli sync      -> command line
    .\run.ps1 --cli scan --auto
#>
$Root = $PSScriptRoot
$args2 = @()
if ($args.Count -gt 0) { $args2 = $args }

$python = $null
foreach ($cand in @(
    (Get-Command py -ErrorAction SilentlyContinue).Source,
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    (Get-Command python -ErrorAction SilentlyContinue).Source,
    (Get-Command python3 -ErrorAction SilentlyContinue).Source
)) {
    if ($cand -and (Test-Path $cand) -and -not ($cand -match 'WindowsApps')) {
        # make sure it is a real python (the Store stub answers "Python not found")
        $v = & $cand --version 2>&1 | Select-Object -First 1
        if ($v -match '^Python \d') { $python = $cand; break }
    }
}
if (-not $python) {
    Write-Error "Python 3.10+ not found. Install it from https://www.python.org/downloads/ (or winget install Python.Python.3.12), then retry."
    exit 1
}
Write-Host "Python: $python ($(& $python --version 2>&1 | Select-Object -First 1))"
& $python (Join-Path $Root 'savesync.py') @args2
