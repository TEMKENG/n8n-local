<#
.SYNOPSIS  Vergleicht die installierte n8n-Version mit der neuesten stabilen Version auf GitHub.
#>
. (Join-Path $PSScriptRoot '_common.ps1')
Invoke-N8nCtl -Arguments @('check')
exit $LASTEXITCODE
