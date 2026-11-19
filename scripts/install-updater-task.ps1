<#
.SYNOPSIS  Registriert den Host-Updater als geplante Aufgabe (Start bei Anmeldung, ohne Adminrechte) und startet ihn.
.DESCRIPTION
  Aufgabe: "n8n-local Host-Updater". Laeuft im Benutzerkontext (wie Docker Desktop),
  lauscht nur auf 127.0.0.1:UPDATER_PORT und wird bei Absturz automatisch neu gestartet.
#>
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
$taskName = 'n8n-local Host-Updater'
$python = Get-Python
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { $pythonw = $python }

$action    = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$script:N8nCtl`" serve" -WorkingDirectory $script:ProjectRoot
$trigger   = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
               -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
               -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description 'Abgesicherter Host-Updater fuer n8n-local (nur 127.0.0.1)' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 3
$port = (Select-String -Path (Join-Path $script:ProjectRoot '.env') -Pattern '^UPDATER_PORT=(\d+)').Matches[0].Groups[1].Value
try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 5
    Write-Output "Host-Updater laeuft: $($r | ConvertTo-Json -Compress)"
} catch {
    Write-Warning "Host-Updater antwortet nicht. Siehe logs\updater.log"
    exit 1
}
