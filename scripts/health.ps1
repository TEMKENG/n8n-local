<#
.SYNOPSIS  Fuehrt alle Healthchecks aus (Container, Version, Datenbank, Readiness, Web-UI). Exit 0 = gesund.
#>
. (Join-Path $PSScriptRoot '_common.ps1')
Invoke-N8nCtl -Arguments @('health')
exit $LASTEXITCODE
