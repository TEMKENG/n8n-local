<#
.SYNOPSIS  Manuelles, abgesichertes n8n-Update (Vorabpruefung, Backup, Pull, Healthchecks, Rollback).
.EXAMPLE   .\scripts\update-n8n.ps1 -Version 2.47.7
.EXAMPLE   .\scripts\update-n8n.ps1 -Version 2.47.7 -PreflightOnly
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version,
    [switch]$PreflightOnly,
    [switch]$AllowMajor,
    [switch]$Force
)
. (Join-Path $PSScriptRoot '_common.ps1')
if ($PreflightOnly) {
    $argsList = @('preflight', $Version)
} else {
    $argsList = @('update', $Version)
    if ($Force) { $argsList += '--yes' }
}
if ($AllowMajor) { $argsList += '--allow-major' }
Invoke-N8nCtl -Arguments $argsList
exit $LASTEXITCODE
