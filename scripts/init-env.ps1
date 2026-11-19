<#
.SYNOPSIS  Erzeugt .env aus .env.example und generiert alle Geheimnisse (nur bei Neuinstallation).
.DESCRIPTION
  Bricht ab, wenn .env bereits existiert - ein neuer N8N_ENCRYPTION_KEY wuerde
  vorhandene Credentials unlesbar machen.
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'
if (Test-Path $envFile) { throw '.env existiert bereits. Abbruch, um den Encryption Key nicht zu ueberschreiben.' }

function New-Secret([int]$Bytes = 32) {
    $buf = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buf); $rng.Dispose()
    return ([Convert]::ToBase64String($buf)).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$content = Get-Content (Join-Path $root '.env.example') -Raw
foreach ($key in 'POSTGRES_PASSWORD', 'N8N_ENCRYPTION_KEY', 'UPDATER_TOKEN') {
    $content = $content -replace "(?m)^$key=.*$", "$key=$(New-Secret)"
}
[System.IO.File]::WriteAllText($envFile, $content.Replace("`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
# Zugriff auf den aktuellen Benutzer beschraenken
icacls $envFile /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
Write-Output ".env erstellt: $envFile"
Write-Output 'WICHTIG: .env (insb. N8N_ENCRYPTION_KEY) zusaetzlich sicher aufbewahren, z.B. im Passwort-Manager.'
