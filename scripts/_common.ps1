# Gemeinsame Hilfsfunktionen fuer die Wrapper-Skripte (Windows PowerShell 5.1+).
$ErrorActionPreference = 'Stop'
$script:ProjectRoot = Split-Path -Parent $PSScriptRoot
$script:N8nCtl = Join-Path $script:ProjectRoot 'updater\n8nctl.py'

function Get-Python {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $cmd) { throw 'Python 3.10+ wurde nicht gefunden (https://www.python.org/downloads/windows/).' }
    return $cmd.Source
}

# Ruft n8nctl.py auf; Ausgabe geht direkt an die Konsole, Exit-Code in $LASTEXITCODE.
function Invoke-N8nCtl {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $python = Get-Python
    & $python $script:N8nCtl $Arguments
}
