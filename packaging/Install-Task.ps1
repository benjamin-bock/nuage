#Requires -Version 5.1
<#
.SYNOPSIS
    Tache planifiee Windows "CloudSaveSync" : sync toutes les 15 min + a l'ouverture
    de session. Utilise l'exe packagé s'il existe, sinon le script Python.
#>
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot | Split-Path -Parent
$Exe  = Join-Path $Root 'dist\CloudSaveSync\CloudSaveSync.exe'
$Py   = Join-Path $Root 'savesync.py'

if (Test-Path $Exe) {
    $action = New-ScheduledTaskAction -Execute $Exe -Argument '--cli sync'
}
else {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
    if (-not $python) { throw "Python introuvable dans le PATH" }
    $action = New-ScheduledTaskAction -Execute $python -Argument "`"$Py`" --cli sync"
}

$triggerRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)
$triggerLogon  = New-ScheduledTaskTrigger -AtLogOn

Register-ScheduledTask -TaskName 'CloudSaveSync' -Action $action -Trigger @($triggerRepeat, $triggerLogon) `
    -Description 'Sync des sauvegardes de jeux vers le cloud' -Force | Out-Null

Write-Host "Tache 'CloudSaveSync' creee : sync toutes les 15 min + a l'ouverture de session."
Write-Host "Suppression : Unregister-ScheduledTask -TaskName 'CloudSaveSync' -Confirm:$false"
