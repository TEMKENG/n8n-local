# n8n-local

Lokale, eigenständige n8n-Installation mit PostgreSQL unter Docker Desktop (Windows 11), mit wöchentlicher automatischer Versionsprüfung und abgesichertem Auto-Update.

| | |
| --- | --- |
| Weboberfläche | <http://localhost:5678> (nur lokal) |
| n8n | 2.47.7 (`docker.n8n.io/n8nio/n8n`, gepinnt) |
| PostgreSQL | 17.12 (`postgres`, gepinnt) |
| Update-Workflow | **Weekly n8n Version Checker & Auto Updater**, montags 03:00 `Europe/Berlin`, aktiv |
| Host-Updater | `updater/n8nctl.py`, Aufgabe „n8n-local Host-Updater“, `127.0.0.1:5680` |

## Dokumentation

| Markdown | HTML | Inhalt |
| --- | --- | --- |
| [docs/installation-guide.md](docs/installation-guide.md) | [HTML](docs/installation-guide.html) | Neuinstallation Schritt für Schritt |
| [docs/architecture.md](docs/architecture.md) | [HTML](docs/architecture.html) | Architektur, Updater, Backup/Rollback, Sicherheit |
| [docs/maintenance.md](docs/maintenance.md) | [HTML](docs/maintenance.html) | Betrieb, Backup, Restore, Updates, Fehleranalyse |

Die HTML-Dateien werden aus den Markdown-Dateien generiert. Nach Änderungen ausführen:

```powershell
python docs\tools\build_docs.py          # HTML neu erzeugen
python docs\tools\build_docs.py --check  # Konsistenz, Links und Diagramme prüfen
```

## Wichtigste Befehle

```powershell
docker compose ps                 # Status
.\scripts\health.ps1              # alle Healthchecks
.\scripts\backup.ps1              # verifiziertes Backup
.\scripts\restore.ps1 -BackupDirectory .\backups\<ordner>
.\scripts\check-version.ps1       # neue stabile Version?
.\scripts\update-n8n.ps1 -Version x.y.z
```

## Struktur

```text
docker-compose.yml   Services n8n, postgres, volume-init; Netze backend (internal) + egress
.env / .env.example  Konfiguration und Geheimnisse (.env nie committen)
scripts/             PowerShell-Wrapper (Backup, Restore, Update, Health, Updater-Aufgabe)
updater/n8nctl.py    Host-Updater: Backup, Restore, Update, Rollback, HTTP-API
workflows/           Export des Update-Workflows (ohne Geheimnisse)
backups/  logs/      Laufzeitdaten (nicht in Git)
docs/                Dokumentation (Markdown-Quelle, generiertes HTML, SVG-Diagramme)
```

## Sicherheit

- `.env` enthält Datenbankpasswort, `N8N_ENCRYPTION_KEY` und `UPDATER_TOKEN`. Sie ist in `.gitignore` eingetragen und muss zusätzlich sicher verwahrt werden. Ohne den Encryption Key sind gespeicherte Credentials verloren.
- Backups enthalten den Encryption Key und alle Daten. Außer Haus nur verschlüsselt ablegen.
- n8n und der Updater sind nur an `127.0.0.1` gebunden, PostgreSQL hat keinen Host-Port, und n8n hat keinen Zugriff auf den Docker-Socket.
