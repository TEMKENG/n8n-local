<#
.SYNOPSIS  Stoppt und entfernt die geplante Aufgabe des Host-Updaters.
#>
$taskName = 'n8n-local Host-Updater'
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
Write-Output "Aufgabe '$taskName' entfernt."
