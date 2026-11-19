# Wartung und Administration

Alle Pfade in diesem Dokument sind relativ zum Projektstamm. Die Python-Verwaltung funktioniert unter Windows, Linux und macOS (Python 3.10+ sowie Docker CLI). Codebeispiele verwenden `python3` für Linux/macOS; unter Windows PowerShell `py -3` statt `python3` eingeben. `scripts/*.ps1` sind optionale Windows-PowerShell-Wrapper.

| Dokument | Inhalt |
| --- | --- |
| [Installation](installation-guide.md) | Erstinstallation unter Windows, Linux und macOS |
| [Architektur](architecture.md) | Container, Netzwerke, Daten und Sicherheit |
| **Wartung** (dieses Dokument) | Betrieb, Backup, Restore, Updates und Fehleranalyse |

## Schnellreferenz

| Aufgabe | Befehl |
| --- | --- |
| Status | `docker compose ps` |
| Healthchecks | `python3 updater/n8nctl.py health` |
| Starten / Stoppen | `docker compose up -d` / `docker compose stop` |
| Logs | `docker compose logs --tail 100 -f n8n` |
| Backup | `python3 updater/n8nctl.py backup` |
| Backup prüfen | `python3 updater/n8nctl.py verify backups/<backup-ordner>` |
| Restore | `python3 updater/n8nctl.py restore backups/<backup-ordner>` |
| Version prüfen | `python3 updater/n8nctl.py check` |
| Update prüfen | `python3 updater/n8nctl.py preflight <version>` |
| Update ausführen | `python3 updater/n8nctl.py update <version>` |

Windows PowerShell kann dieselben Python-Befehle mit `py -3 updater\n8nctl.py ...` aufrufen. Für häufig genutzte Windows-Aktionen gibt es zusätzlich `scripts/health.ps1`, `backup.ps1`, `restore.ps1`, `check-version.ps1` und `update-n8n.ps1`.

## Containerbetrieb

```sh
docker compose up -d
docker compose ps
docker compose logs --tail 100 n8n
docker compose logs --tail 100 postgres
docker compose stop
docker compose start
docker compose down
```

`docker compose down` lässt benannte Volumes bestehen. **Nicht `docker compose down -v` verwenden**, wenn die Instanzdaten erhalten bleiben sollen.

## Manuelles Backup und Verifikation

Ein Backup stoppen n8n für einen konsistenten Datenstand:

```sh
python3 updater/n8nctl.py backup
```

Die Ausgabe nennt den erzeugten Ordner unter `backups/`. Verifizieren Sie ein bestimmtes Backup mit:

```sh
python3 updater/n8nctl.py verify backups/<backup-ordner>
```

Optional: `python3 updater/n8nctl.py backup --online` erstellt das Backup ohne n8n anzuhalten; verwenden Sie das nur, wenn gleichzeitige Workflow-Ausführungen tolerierbar sind. Für regelmäßige Backups kann der Befehl über die native Aufgabenplanung des Betriebssystems gestartet werden (Windows Task Scheduler, Linux `cron`/systemd timer, macOS `launchd`). Achten Sie darauf, das Arbeitsverzeichnis auf den Projektstamm zu setzen.

Backups enthalten `.env`, Datenbankinhalte und den Encryption Key. Beschränken Sie Dateizugriff und verschlüsseln Sie externe Kopien.

## Wiederherstellen

Vor dem Restore wird bei laufendem PostgreSQL automatisch ein Sicherheits-Backup erstellt. Der Restore erfordert eine Bestätigung:

```sh
python3 updater/n8nctl.py restore backups/<backup-ordner>
```

Bei fehlender `.env` oder einem abweichenden Encryption Key übernehmen Sie die zum Backup gehörende Konfiguration ausdrücklich:

```sh
python3 updater/n8nctl.py restore backups/<backup-ordner> --restore-env
```

`--yes` überspringt die Bestätigung. Nutzen Sie diese Option nur, wenn das zu überschreibende Ziel und der Backup-Pfad geprüft wurden.

## Updates und Host-Updater

Prüfen Sie zuerst den stabilen Release-Stand sowie die Vorabprüfung:

```sh
python3 updater/n8nctl.py check
python3 updater/n8nctl.py preflight <version>
```

Ein manuelles Update erstellt automatisch ein Backup, zieht das Image, wartet auf Healthchecks und führt bei Fehlern einen vollständigen Restore durch:

```sh
python3 updater/n8nctl.py update <version>
```

Major-Updates erfordern `--allow-major`; lesen Sie vorher die n8n-Release-Hinweise und erstellen Sie ein zusätzliches Backup. Ein expliziter Restore ist weiterhin verfügbar, falls nötig.

Der optionale Host-Updater wird unter Windows über die geplante Aufgabe installiert:

```powershell
.\scripts\install-updater-task.ps1
.\scripts\uninstall-updater-task.ps1
```

Manueller Start, beispielsweise unter macOS:

```sh
python3 updater/n8nctl.py serve
```

Für Linux mit nativem Docker Engine ist die integrierte Loopback-API aus n8n heraus standardmäßig nicht erreichbar. Öffnen Sie den Dienst nicht global. Einzelne Befehle (`backup`, `restore`, `update`, `health`) funktionieren unabhängig davon direkt auf dem Host. Siehe [Installationshinweise](installation-guide.md#7-host-updater-und-automatisierten-workflow-optional).

## Protokolle und Diagnose

```sh
docker compose ps
docker compose logs --tail 100 n8n
docker compose logs --tail 100 postgres
python3 updater/n8nctl.py health
python3 updater/n8nctl.py status
```

Host-Updater-Protokolle liegen unter `logs/`: `updater.log`, `updates.jsonl`, `version-checks.jsonl` und `update-<id>.out`. Diese Laufzeitdateien werden nicht in Git versioniert.

| Symptom | Prüfung / Maßnahme |
| --- | --- |
| Docker zeigt nur den Client | Docker Desktop bzw. den Docker-Dienst starten und `docker version` erneut prüfen |
| n8n ist unhealthy | `docker compose logs n8n` sowie den Healthcheck von PostgreSQL prüfen |
| Port 5678 belegt | `N8N_PORT` in `.env` ändern und mit `docker compose up -d` neu erstellen |
| PostgreSQL-Authentifizierung schlägt fehl | ursprüngliches `POSTGRES_PASSWORD` aus der korrespondierenden `.env`/dem Backup wiederherstellen; Änderungen der Image-Umgebungsvariablen ändern kein bestehendes Datenbankpasswort |
| Credentials lassen sich nicht entschlüsseln | passenden `N8N_ENCRYPTION_KEY` aus `.env` oder einem Backup wiederherstellen |
| Updater-Workflow erreicht den Host nicht | `python3 updater/n8nctl.py serve`, Token, Host-Firewall und OS-spezifische Hinweise prüfen; unter nativem Linux ist Loopback aus dem Container nicht erreichbar |

## PostgreSQL-Wartung

PostgreSQL-Minor-Upgrades derselben Major-Version: erst Backup erstellen, `POSTGRES_VERSION` in `.env` ändern, dann:

```sh
docker compose pull postgres
docker compose up -d postgres
python3 updater/n8nctl.py health
```

Ein PostgreSQL-Major-Upgrade benötigt eine geplante Migration und einen getesteten Dump/Restore. Ändern Sie nicht lediglich das Image-Tag bei einem bestehenden Datenverzeichnis. Erstellen und prüfen Sie ein Backup und folgen Sie der offiziellen PostgreSQL-/Image-Dokumentation, bevor Sie die Instanz migrieren.

## Dokumentation generieren und prüfen

Im Projektstamm:

```sh
python3 docs/tools/build_docs.py
python3 docs/tools/build_docs.py --check
```

Der Generator aktualisiert HTML und SVG aus Markdown und prüft Seitenlinks, Anker und Diagrammzuordnungen.
