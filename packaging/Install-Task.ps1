#Requires -Version 5.1
<#
.SYNOPSIS
    Windows scheduled task "CloudSaveSync": runs a sync every 15 min + at logon.
    Uses the packaged exe if present, otherwise the Python script.
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
    if (-not $python) { throw "Python not found in PATH" }
    $action = New-ScheduledTaskAction -Execute $python -Argument "`"$Py`" --cli sync"
}

$triggerRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)
$triggerLogon  = New-ScheduledTaskTrigger -AtLogOn

Register-ScheduledTask -TaskName 'CloudSaveSync' -Action $action -Trigger @($triggerRepeat, $triggerLogon) `
    -Description 'Sync game saves to the cloud' -Force | Out-Null

Write-Host "Scheduled task 'CloudSaveSync' created: sync every 15 min + at logon."
Write-Host "Remove it with: Unregister-ScheduledTask -TaskName 'CloudSaveSync' -Confirm:$false"
