<#
.SYNOPSIS  Windows-Wrapper fuer die plattformuebergreifende .env-Initialisierung.
#>
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
$python = Get-Python
$initializer = Join-Path $PSScriptRoot 'init-env.py'
& $python $initializer
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$envFile = Join-Path (Split-Path -Parent $PSScriptRoot) '.env'
icacls $envFile /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Die Dateirechte von .env konnten nicht eingeschraenkt werden.' }
