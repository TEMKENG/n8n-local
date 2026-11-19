<#
.SYNOPSIS  Erstellt ein konsistentes, verifiziertes Backup (Datenbank, n8n-Volumes, .env, Compose-Datei).
.EXAMPLE   .\scripts\backup.ps1
.EXAMPLE   .\scripts\backup.ps1 -Online   # n8n waehrend des Backups nicht stoppen
#>
[CmdletBinding()]
param([string]$Reason = 'manual', [switch]$Online)
. (Join-Path $PSScriptRoot '_common.ps1')
$argsList = @('backup', '--reason', $Reason)
if ($Online) { $argsList += '--online' }
Invoke-N8nCtl -Arguments $argsList
exit $LASTEXITCODE
