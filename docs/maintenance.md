# Wartung und Administration: n8n-local

Alle Befehle für **Windows PowerShell**, ausgeführt in `C:\Weiterbildung\docker\n8n-local`. Wenn die Ausführungsrichtlinie Skripte blockiert, die Wrapper mit `powershell -ExecutionPolicy Bypass -File .\scripts\<name>.ps1` aufrufen.

| Dokument | Inhalt |
| --- | --- |
| [Installationsanleitung](installation-guide.md) | Neuinstallation Schritt für Schritt |
| [Architektur](architecture.md) | Aufbau, Netzwerke, Volumes, Updater, Sicherheitskonzept |
| **Wartung und Administration** (dieses Dokument) | Betrieb, Backup, Restore, Updates, Fehleranalyse |

## Schnellreferenz

| Aufgabe | Befehl |
| --- | --- |
| Status | `docker compose ps` |
| Gesamtzustand prüfen | `.\scripts\health.ps1` |
| Starten / Stoppen | `docker compose up -d` / `docker compose stop` |
| Logs n8n | `docker logs n8n --tail 100 -f` |
| Backup | `.\scripts\backup.ps1` |
| Restore | `.\scripts\restore.ps1 -BackupDirectory .\backups\<ordner>` |
| Neue Version? | `.\scripts\check-version.ps1` |
| Manuelles Update | `.\scripts\update-n8n.ps1 -Version x.y.z` |
| Update-Protokoll | `Get-Content .\logs\updates.jsonl -Tail 3` |
| Prüfprotokoll Workflow | `Get-Content .\logs\version-checks.jsonl -Tail 5` |
| Updater-Log | `Get-Content .\logs\updater.log -Tail 50` |

## Starten und Stoppen der Container

```powershell
docker compose up -d              # alles starten (postgres → volume-init → n8n)
docker compose stop               # anhalten, Container bleiben erhalten
docker compose stop n8n           # nur n8n anhalten (z. B. vor manuellen DB-Arbeiten)
docker compose start              # angehaltene Container wieder starten
docker compose down               # Container und Netzwerke entfernen; Volumes bleiben!
```

> **Warnung:** Niemals `docker compose down -v` ausführen. `-v` löscht alle Volumes und damit die gesamte Datenbank.

Wegen `restart: unless-stopped` starten die Container nach einem Neustart von Docker Desktop oder Windows automatisch, sofern sie nicht vorher manuell gestoppt wurden.

## Neustarten der Infrastruktur

```powershell
docker compose restart n8n        # nur n8n (z. B. nach Aktivieren eines Workflows per CLI)
docker compose restart            # beide Container
docker compose up -d --force-recreate n8n   # n8n neu erstellen, z. B. nach Änderung der docker-compose.yml
```

Host-Updater neu starten:

```powershell
Stop-ScheduledTask  -TaskName 'n8n-local Host-Updater'
Start-ScheduledTask -TaskName 'n8n-local Host-Updater'
Invoke-RestMethod http://127.0.0.1:5680/health
```

## Anzeigen der Logs

```powershell
docker logs n8n --tail 100                 # letzte 100 Zeilen
docker logs n8n -f                         # live (Strg+C beendet)
docker logs postgres --since 1h
docker compose logs --tail 50              # alle Services
Get-Content .\logs\updater.log -Tail 50 -Wait   # Host-Updater live
```

Die Container-Logs werden automatisch rotiert (`json-file`, 10 MB × 5 Dateien pro Container).

| Datei | Inhalt |
| --- | --- |
| `logs\updater.log` | Textprotokoll aller Aktionen des Host-Updaters (inkl. abgelehnter Anfragen) |
| `logs\updates.jsonl` | ein JSON-Datensatz pro Update-Vorgang |
| `logs\version-checks.jsonl` | ein JSON-Datensatz pro Workflow-Lauf (Entscheidung, Versionen) |
| `logs\update-<id>.out` | Ausgabe des separaten Update-Prozesses |

Felder in `updates.jsonl`: `startedAt`, `finishedAt`, `durationSeconds`, `versionBefore`, `targetVersion`, `versionAfter`, `backup`, `backupStatus`, `health` (alle Checks), `status` (`success` / `aborted` / `rolled-back` / `rollback-failed`), `rollback`, `error`, `steps`, `requestedBy`.

Übersicht als Tabelle:

```powershell
Get-Content .\logs\updates.jsonl | ConvertFrom-Json |
  Select-Object startedAt, versionBefore, targetVersion, versionAfter, status, backupStatus, durationSeconds |
  Format-Table -AutoSize
```

## Prüfen der PostgreSQL-Verbindung

```powershell
docker exec postgres pg_isready -U n8n -d n8n -h 127.0.0.1
docker exec postgres psql -U n8n -d n8n -c "select version();"
docker exec postgres psql -U n8n -d n8n -c "select count(*) as workflows from workflow_entity;"
docker exec -it postgres psql -U n8n -d n8n          # interaktive Konsole (\q beendet)
# Verbindung aus Sicht von n8n:
Invoke-WebRequest http://localhost:5678/healthz/readiness -UseBasicParsing | Select-Object StatusCode
```

## Manuelles Backup

```powershell
.\scripts\backup.ps1                  # Standard: n8n wird für ca. 10–30 s gestoppt (konsistent)
.\scripts\backup.ps1 -Reason vor-umbau
.\scripts\backup.ps1 -Online          # ohne Stopp (nur wenn keine Workflows laufen)
```

Ablauf: Speicherplatz prüfen → n8n stoppen → `pg_dump` + `pg_dumpall --globals-only` → Volumes archivieren → `.env` und `docker-compose.yml` kopieren → `manifest.json` mit SHA-256 schreiben → verifizieren → n8n starten → Aufbewahrung anwenden. Erfolgsmeldung: `"verified": true`.

Ein vorhandenes Backup prüfen:

```powershell
python .\updater\n8nctl.py verify .\backups\20261116-092806-manual
```

Aufbewahrung (in `.env`): Backups älter als `BACKUP_RETENTION_DAYS=30` Tage werden beim nächsten Backup gelöscht, die `BACKUP_KEEP_MIN=5` neuesten bleiben immer erhalten. Manuell anstoßen: `python .\updater\n8nctl.py prune`.

> **Warnung:** Backups enthalten den Encryption Key. Kopien außerhalb des Rechners nur verschlüsselt ablegen, z. B. `7z a -t7z -mhe=on -p backup.7z .\backups\<ordner>`.

### Automatische Backups (optional)

Ein tägliches Backup lässt sich per Aufgabenplanung einrichten:

```powershell
$a = New-ScheduledTaskAction -Execute 'powershell.exe' `
     -Argument '-NoProfile -ExecutionPolicy Bypass -File C:\Weiterbildung\docker\n8n-local\scripts\backup.ps1 -Reason daily'
$t = New-ScheduledTaskTrigger -Daily -At 02:30
Register-ScheduledTask -TaskName 'n8n-local Backup' -Action $a -Trigger $t
```

Vor jedem automatischen Update erstellt der Host-Updater zusätzlich immer ein Backup `…-pre-update`.

## Manuelle Wiederherstellung

```powershell
Get-ChildItem .\backups -Directory | Sort-Object Name     # Backup auswählen
.\scripts\restore.ps1 -BackupDirectory .\backups\20261116-092806-manual
# Rückfrage mit "ja" bestätigen; -Force überspringt die Rückfrage
```

Ablauf: Hashes und Dump prüfen → Encryption Key vergleichen → Sicherheits-Backup `pre-restore` → `N8N_VERSION`/`POSTGRES_VERSION` aus dem Backup setzen → n8n stoppen → Volumes ersetzen → Datenbank neu anlegen und `pg_restore` → n8n starten → Healthchecks.

| Situation | Parameter |
| --- | --- |
| Normaler Restore auf demselben Rechner | keiner |
| `.env` fehlt oder Encryption Key unterscheidet sich | `-RestoreEnv` (übernimmt `env.backup`) |

## Manuelles Aktualisieren von n8n

Empfohlen über den Host-Updater: Vorabprüfung, Backup, Healthchecks und Rollback sind eingebaut.

```powershell
.\scripts\check-version.ps1                              # installiert vs. neueste stabile Version
.\scripts\update-n8n.ps1 -Version 2.47.8 -PreflightOnly  # nur prüfen
.\scripts\update-n8n.ps1 -Version 2.47.8                 # Update mit Rückfrage
.\scripts\update-n8n.ps1 -Version 3.0.1 -AllowMajor      # Major-Update (vorher Release Notes lesen!)
```

Bei Major-Updates zuerst die Release Notes und den Migrationsleitfaden von n8n lesen: <https://docs.n8n.io/release-notes/>.

Komplett manuell, ohne Updater:

```powershell
.\scripts\backup.ps1 -Reason vor-update
docker pull docker.n8n.io/n8nio/n8n:2.47.8
(Get-Content .env) -replace '^N8N_VERSION=.*', 'N8N_VERSION=2.47.8' | Set-Content .env -Encoding ascii
docker compose up -d --no-deps n8n
.\scripts\health.ps1
# Bei Fehler: .\scripts\restore.ps1 -BackupDirectory .\backups\<vor-update-ordner> -Force
```

## Manuelles Aktualisieren von PostgreSQL

**Minor-Update** (z. B. 17.12 → 17.13, gleiche Datenformate):

```powershell
.\scripts\backup.ps1 -Reason vor-pg-update
(Get-Content .env) -replace '^POSTGRES_VERSION=.*', 'POSTGRES_VERSION=17.13' | Set-Content .env -Encoding ascii
docker compose pull postgres
docker compose up -d postgres
.\scripts\health.ps1
```

**Major-Update** (z. B. 17 → 18): Das Datenverzeichnis ist nicht kompatibel. Vorgehen per Dump und Restore:

1. `.\scripts\backup.ps1 -Reason vor-pg-major` ausführen und den Backup-Ordner notieren.
2. `docker compose down` ausführen und das alte Volume umbenennen bzw. sichern. Es bleibt als Fallback erhalten:
   `docker volume create n8n-local_postgres_data_pg17` und die Daten per `docker run --rm -v n8n-local_postgres_data:/from -v n8n-local_postgres_data_pg17:/to alpine:3.22 sh -c "cp -a /from/. /to/"` kopieren.
3. `docker volume rm n8n-local_postgres_data` ausführen.
4. `POSTGRES_VERSION` in `.env` anpassen. **Ab PostgreSQL 18** in `docker-compose.yml` `PGDATA` entfernen und das Volume auf `/var/lib/postgresql` mounten (geänderte Konvention des offiziellen Images).
5. `docker compose up -d postgres`, danach `.\scripts\restore.ps1 -BackupDirectory .\backups\<ordner> -Force`.
6. `.\scripts\health.ps1` ausführen und die Daten prüfen.

## Kontrolle des automatisierten Update-Workflows

| Prüfung | Befehl / Ort |
| --- | --- |
| Workflow aktiv? | `docker exec postgres psql -U n8n -d n8n -tAc "select name, active from workflow_entity where id='weeklyN8nUpdater'"` → `t` |
| Letzte Ausführungen | UI: **Overview → Executions** bzw. Workflow → **Executions** |
| Letzte Entscheidungen | `Get-Content .\logs\version-checks.jsonl -Tail 5` |
| Letzte Updates | `Get-Content .\logs\updates.jsonl -Tail 1 \| ConvertFrom-Json` |
| Updater läuft? | `Invoke-RestMethod http://127.0.0.1:5680/health` |
| Updater-Status mit Auth | siehe unten |
| Manuell ausführen | `docker exec -e N8N_RUNNERS_BROKER_PORT=5690 n8n n8n execute --id=weeklyN8nUpdater --rawOutput` |

```powershell
$token = (Select-String -Path .env -Pattern '^UPDATER_TOKEN=(.+)$').Matches[0].Groups[1].Value
Invoke-RestMethod http://127.0.0.1:5680/status -Headers @{ Authorization = "Bearer $token" } | ConvertTo-Json -Depth 5
# Dry-Run einer Zielversion, ohne Änderung:
Invoke-RestMethod http://127.0.0.1:5680/update -Method Post -ContentType 'application/json' `
  -Headers @{ Authorization = "Bearer $token" } -Body '{"version":"2.47.7","dryRun":true}'
```

**Zeitplan ändern:** In der UI den Knoten „Montag 03:00 (Europe/Berlin)“ öffnen und Wochentag/Uhrzeit anpassen. Den Knoten passend umbenennen, **Publish** klicken und den Export `workflows/weekly-n8n-update.json` aktualisieren (Workflow-Menü → Download). Die Zeitzone kommt aus den Workflow-Einstellungen (`Europe/Berlin`) und aus `GENERIC_TIMEZONE`.

**Rollback-Pfad testen**, ohne die Version zu wechseln:

```powershell
python .\updater\n8nctl.py update 2.47.7 --yes --simulate-failure
# erwartet: status "rolled-back", rollback.ok = true
```

**Workflow deaktivieren:** `docker exec n8n n8n unpublish:workflow --id=weeklyN8nUpdater` und danach `docker compose restart n8n`.

## Fehleranalyse

| Symptom | Ursache / Prüfung | Lösung |
| --- | --- | --- |
| `docker` antwortet nur mit Client | Docker Desktop läuft nicht | Docker Desktop starten |
| n8n bleibt `starting`/`unhealthy` | `docker logs n8n --tail 100` | DB-Fehler: `docker compose ps postgres` prüfen |
| `password authentication failed` | `POSTGRES_PASSWORD` in `.env` geändert | ursprüngliches Passwort wiederherstellen (aus `backups\*\env.backup`) |
| Credentials „could not be decrypted“ | falscher `N8N_ENCRYPTION_KEY` | Key aus dem Backup (`env.backup`) wiederherstellen |
| Port 5678 belegt | `netstat -ano \| Select-String ':5678 '` | Fremdprozess beenden oder `N8N_PORT` ändern |
| Workflow: „Installierte Version ermitteln“ schlägt fehl | Updater läuft nicht / Token falsch | `Start-ScheduledTask 'n8n-local Host-Updater'`; Credential prüfen |
| Workflow: `decision=blocked` | Vorabprüfung, siehe `reason` | z. B. Speicherplatz freigeben, Healthchecks reparieren |
| `updates.jsonl`: `aborted` | Backup oder Vorabprüfung fehlgeschlagen, **nichts geändert** | `error` lesen, Ursache beheben |
| `updates.jsonl`: `rolled-back` | neue Version nicht gesund, alter Stand wiederhergestellt | `health.checks` lesen, Release Notes prüfen, später erneut |
| `updates.jsonl`: `rollback-failed` | **kritisch** | `logs\updater.log` lesen, manuell `restore.ps1` mit dem `pre-update`-Backup |
| Update-Sperre hängt | `updater\state\update.lock` existiert ohne laufenden Prozess | wird nach 3 h automatisch entfernt; sonst Datei löschen |
| `Task Broker's port 5679 is already in use` bei `n8n execute` | n8n läuft bereits | `-e N8N_RUNNERS_BROKER_PORT=5690` angeben |

Diagnosepaket:

```powershell
.\scripts\health.ps1
docker compose ps
docker inspect n8n --format '{{json .State.Health}}' | ConvertFrom-Json | Select-Object -ExpandProperty Log | Select-Object -Last 3
Get-Content .\logs\updater.log -Tail 30
```

## Speicherplatzverwaltung

```powershell
docker system df                       # Images, Container, Volumes, Build-Cache
docker system df -v | Select-String 'n8n-local'
Get-ChildItem .\backups -Directory | ForEach-Object {
  [pscustomobject]@{ Name = $_.Name; MB = [math]::Round((Get-ChildItem $_.FullName -Recurse | Measure-Object Length -Sum).Sum / 1MB, 1) } }
python .\updater\n8nctl.py prune       # Aufbewahrungsregel anwenden
docker image prune                     # ungenutzte, unbenannte Images entfernen
docker image rm docker.n8n.io/n8nio/n8n:<alte-version>   # alte n8n-Images (nicht die aktuelle!)
```

- Ausführungsdaten werden durch `EXECUTIONS_DATA_PRUNE=true` nach 14 Tagen (`EXECUTIONS_DATA_MAX_AGE=336` h) gelöscht.
- Die WSL-Disk von Docker Desktop schrumpft nicht automatisch: Docker Desktop → **Settings → Resources → Disk image size** bzw. **Troubleshoot → Clean / Purge data** (Vorsicht: „Purge“ löscht Volumes).
- Backup und Update verweigern den Start, wenn weniger als 2 × Volumegröße + `MIN_FREE_GB` frei ist.

## Wiederherstellung nach einem Systemausfall

### Szenario A: Docker Desktop oder WSL defekt, Projektordner intakt

1. Docker Desktop neu installieren (siehe [Installationsanleitung](installation-guide.md#2-docker-installation)).
2. Sind die Volumes noch vorhanden (`docker volume ls`), genügt `docker compose up -d`.
3. Fehlen sie: `docker compose up -d postgres`, dann `.\scripts\restore.ps1 -BackupDirectory .\backups\<neuestes> -Force`.

### Szenario B: Neuer Rechner, nur eine Backup-Kopie vorhanden

1. Docker Desktop, Git und Python installieren.
2. Projekt aus Git klonen oder kopieren (ohne `.env`).
3. Den Backup-Ordner nach `backups\` kopieren und entschlüsseln.
4. `.env` aus dem Backup übernehmen: `Copy-Item .\backups\<ordner>\env.backup .env`.
5. `docker compose pull`, danach `docker compose up -d postgres`.
6. `.\scripts\restore.ps1 -BackupDirectory .\backups\<ordner> -RestoreEnv -Force`.
7. `.\scripts\install-updater-task.ps1`, danach `.\scripts\health.ps1`.
8. Anmeldung in der UI mit dem bisherigen Konto. Workflows, Credentials und der Update-Workflow sind wiederhergestellt.

### Szenario C: `.env` verloren, Volumes intakt

`env.backup` aus dem neuesten Backup nach `.env` kopieren. Ohne Backup lässt sich der `N8N_ENCRYPTION_KEY` nur aus `/home/node/.n8n/config` im Volume `n8n_data` lesen (`docker run --rm -v n8n-local_n8n_data:/d alpine:3.22 cat /d/config`), falls n8n ihn dort gespeichert hat. Gespeicherte Credentials sind ohne Key verloren.

## Regelmäßige Wartung

| Intervall | Aufgabe |
| --- | --- |
| wöchentlich (automatisch) | Versionsprüfung und ggf. Update (Montag 03:00) |
| wöchentlich | `logs\version-checks.jsonl` und `logs\updates.jsonl` kurz prüfen |
| monatlich | `.\scripts\backup.ps1` und eine verschlüsselte Kopie außer Haus |
| quartalsweise | Restore-Test auf Testbasis; Docker Desktop aktualisieren |
| bei Major-Release von n8n | Release Notes lesen, manuell mit `-AllowMajor` aktualisieren |
