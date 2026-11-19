<#
.SYNOPSIS  Stellt ein Backup wieder her (Datenbank + n8n-Volumes) und prueft danach die Healthchecks.
.DESCRIPTION
  Vor dem Ueberschreiben wird automatisch ein Sicherheits-Backup "pre-restore" erstellt.
  -RestoreEnv uebernimmt die .env (inkl. Encryption Key) aus dem Backup, z.B. nach Systemverlust.
.EXAMPLE   .\scripts\restore.ps1 -BackupDirectory .\backups\20261116-093000-manual
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BackupDirectory,
    [switch]$RestoreEnv,
    [switch]$Force
)
. (Join-Path $PSScriptRoot '_common.ps1')
$dir = (Resolve-Path $BackupDirectory).Path
$argsList = @('restore', $dir)
if ($RestoreEnv) { $argsList += '--restore-env' }
if ($Force) { $argsList += '--yes' }
Invoke-N8nCtl -Arguments $argsList
exit $LASTEXITCODE
