#Requires -Version 5.1
<#
.SYNOPSIS
    Lance Cloud Save Sync en trouvant Python de maniere fiable
    (py launcher -> install connu -> PATH), meme si le stub Microsoft Store masque python.

    .
un.ps1                 -> GUI
    .
un.ps1 --cli sync      -> ligne de commande
    .
un.ps1 --cli scan --auto
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
        # verifie que c'est un vrai python (le stub Store repond "Python est introuvable")
        $v = & $cand --version 2>&1 | Select-Object -First 1
        if ($v -match '^Python \d') { $python = $cand; break }
    }
}
if (-not $python) {
    Write-Error "Python 3.10+ introuvable. Installe-le depuis https://www.python.org/downloads/ (ou winget install Python.Python.3.12) puis relance."
    exit 1
}
Write-Host "Python : $python ($(& $python --version 2>&1 | Select-Object -First 1))"
& $python (Join-Path $Root 'savesync.py') @args2
