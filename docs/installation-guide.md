# Installationsanleitung: n8n lokal mit Docker und PostgreSQL

Diese Anleitung beschreibt jeden Schritt, um die Umgebung `n8n-local` auf einem Windows-Rechner von Grund auf neu einzurichten, ohne fremde Hilfe. Alle Befehle sind für **Windows PowerShell** geschrieben und werden im Projektverzeichnis `C:\Weiterbildung\docker\n8n-local` ausgeführt, sofern nicht anders angegeben.

| Dokument | Inhalt |
| --- | --- |
| **Installationsanleitung** (dieses Dokument) | Neuinstallation Schritt für Schritt |
| [Architektur](architecture.md) | Aufbau, Netzwerke, Volumes, Updater, Sicherheitskonzept |
| [Wartung und Administration](maintenance.md) | Betrieb, Backup, Restore, Updates, Fehleranalyse |

## Referenzstand

Diese Werte wurden bei der Installation am 16.11.2026 tatsächlich verwendet und getestet:

| Komponente | Version / Wert |
| --- | --- |
| Betriebssystem | Windows 11 Home, Build 26300 (x64) |
| CPU / RAM | AMD Ryzen 7 7435HS (8 Kerne), 16 GB |
| Docker Desktop | 4.98.0 mit WSL-2-Backend |
| Docker Engine | 29.9.2 |
| Docker Compose | v5.6.1 (Plugin `docker compose`) |
| Git | 2.50.1 |
| Python (für Host-Updater) | 3.15.2 |
| n8n | 2.47.7 (Image `docker.n8n.io/n8nio/n8n:2.47.7`) |
| PostgreSQL | 17.12 (Image `postgres:17.12`) |
| n8n-Adresse | <http://localhost:5678> |
| Host-Updater | `http://127.0.0.1:5680` (nur lokal) |
| Zeitzone | `Europe/Berlin` |

## 1. Voraussetzungen und Systemanforderungen

| Anforderung | Minimum | Empfohlen |
| --- | --- | --- |
| Windows | Windows 10 22H2 / Windows 11 (Home, Pro, Enterprise) | Windows 11 |
| Virtualisierung | Im BIOS/UEFI aktiviert (AMD-V / Intel VT-x) | |
| WSL | WSL 2 | aktuelle Version (`wsl --update`) |
| RAM | 8 GB | 16 GB |
| Freier Speicher | 10 GB | 30 GB+ (Images, Volumes, Backups) |
| Freie Ports | 5678 (n8n), 5680 (Host-Updater) | |
| Python | 3.10+ (nur Standardbibliothek) | 3.12+ |

Prüfen Sie den Ausgangszustand:

```powershell
# Betriebssystem
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber
# Virtualisierung aktiv?
(Get-CimInstance Win32_ComputerSystem).HypervisorPresent
# Freier Speicher auf C:
Get-PSDrive C | Select-Object Used, Free
# Ports frei? (keine Ausgabe = frei)
netstat -ano | Select-String ':5678 |:5680 '
# Git und Python
git --version
python --version
```

> **Hinweis:** Python wird nur für den Host-Updater (`updater/n8nctl.py`) benötigt. Installation: <https://www.python.org/downloads/windows/>, dabei die Option „Add python.exe to PATH“ aktivieren.

## 2. Docker-Installation

1. WSL 2 installieren bzw. aktualisieren (PowerShell **als Administrator**):

   ```powershell
   wsl --install --no-distribution
   wsl --update
   ```

   Danach den Rechner neu starten, falls dazu aufgefordert.

2. Docker Desktop von <https://docs.docker.com/desktop/setup/install/windows-install/> herunterladen und installieren. Im Installer **„Use WSL 2 instead of Hyper-V“** aktiviert lassen (unter Windows Home die einzige Option).

3. Docker Desktop starten und unter **Settings → General** aktivieren:
   - **Start Docker Desktop when you sign in to your computer**: Pflicht, damit Container und der wöchentliche Workflow ohne manuelles Zutun laufen.
   - **Use the WSL 2 based engine**: aktiviert.

> **Warnung:** Administratorrechte werden nur für die Installation von WSL und Docker Desktop benötigt. Alle weiteren Schritte laufen als normaler Benutzer.

## 3. Docker-Compose-Prüfung

```powershell
docker version            # Client UND Server müssen antworten
docker compose version    # erwartet: Docker Compose version v2.x oder neuer
docker info --format '{{.OSType}} {{.ServerVersion}}'   # erwartet: linux ...
docker run --rm hello-world
```

Antwortet nur der Client, läuft die Docker-Engine nicht: Docker Desktop starten und warten, bis das Wal-Symbol „Engine running“ meldet.

Vor der Installation auf Konflikte prüfen:

```powershell
docker ps -a --format '{{.Names}}' | Select-String '^(n8n|postgres)$'   # keine Ausgabe = kein Konflikt
docker volume ls --format '{{.Name}}' | Select-String 'n8n-local'
```

## 4. Erstellung der Projektstruktur

Das Projekt ist eigenständig und liegt außerhalb anderer Repositories:

```powershell
New-Item -ItemType Directory -Force C:\Weiterbildung\docker\n8n-local
Set-Location C:\Weiterbildung\docker\n8n-local
# Bei Wiederherstellung aus Git:
# git clone <repository-url> C:\Weiterbildung\docker\n8n-local
```

Zielstruktur:

```text
n8n-local/
├── docker-compose.yml          # Services, Netzwerke, Volumes
├── .env                        # Geheimnisse (NICHT in Git)
├── .env.example                # Vorlage ohne Geheimnisse
├── .gitignore
├── README.md
├── scripts/                    # PowerShell-Wrapper für Administration
│   ├── init-env.ps1            # .env mit Geheimnissen erzeugen
│   ├── backup.ps1 / restore.ps1
│   ├── check-version.ps1 / update-n8n.ps1 / health.ps1
│   └── install-updater-task.ps1 / uninstall-updater-task.ps1
├── updater/
│   ├── n8nctl.py               # Host-Updater: Backup, Restore, Update, Rollback, HTTP-API
│   └── state/                  # Update-Sperre (Laufzeit, nicht in Git)
├── workflows/
│   └── weekly-n8n-update.json  # Workflow-Export ohne Geheimnisse
├── backups/                    # Backups (nicht in Git)
├── logs/                       # Update- und Prüfprotokolle (nicht in Git)
└── docs/                       # Diese Dokumentation (Markdown + HTML)
```

## 5. Erstellung und Konfiguration der `.env`

Alle sensiblen und veränderlichen Werte stehen ausschließlich in `.env`. Die Vorlage `.env.example` enthält alle Schlüssel:

| Variable | Bedeutung | Wert |
| --- | --- | --- |
| `N8N_VERSION` | Gepinnte n8n-Version (wird vom Updater gepflegt) | `2.47.7` |
| `POSTGRES_VERSION` | Gepinnte PostgreSQL-Version | `17.12` |
| `POSTGRES_DB` | Datenbankname | `n8n` |
| `POSTGRES_USER` | Datenbankbenutzer | `n8n` |
| `POSTGRES_PASSWORD` | Datenbankpasswort | generiert, 256 Bit |
| `N8N_ENCRYPTION_KEY` | Schlüssel für gespeicherte Credentials | generiert, 256 Bit |
| `N8N_PORT` | Host-Port der Weboberfläche (nur 127.0.0.1) | `5678` |
| `TZ`, `GENERIC_TIMEZONE` | Zeitzone für Container und Schedule-Trigger | `Europe/Berlin` |
| `UPDATER_TOKEN` | Bearer-Token zwischen n8n und Host-Updater | generiert, 256 Bit |
| `UPDATER_HOST`, `UPDATER_PORT` | Bindung des Host-Updaters | `127.0.0.1`, `5680` |
| `BACKUP_RETENTION_DAYS` | Backups älter als X Tage löschen … | `30` |
| `BACKUP_KEEP_MIN` | … aber immer mindestens N neueste behalten | `5` |
| `MIN_FREE_GB` | Mindestreserve an freiem Speicher für Backup/Update | `5` |
| `N8N_OWNER_EMAIL`, `N8N_OWNER_PASSWORD` | Optional: initiales Owner-Konto (siehe Schritt 13) | |

## 6. Generierung der Passwörter und Encryption Keys

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\init-env.ps1
```

Das Skript kopiert `.env.example` nach `.env`, ersetzt alle `GENERATE_ME`-Werte durch kryptografisch zufällige 256-Bit-Werte (Base64url, ohne Sonderzeichen, die Compose stören) und beschränkt die Dateirechte auf den aktuellen Benutzer. Existiert `.env` bereits, bricht es ab.

Manuelle Alternative für einzelne Werte:

```powershell
$b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
[Convert]::ToBase64String($b).TrimEnd('=').Replace('+','-').Replace('/','_')
```

> **Warnung:** Der `N8N_ENCRYPTION_KEY` darf nach dem ersten Start **nie** geändert werden und darf nicht verloren gehen. Ohne ihn lassen sich gespeicherte Credentials nicht mehr entschlüsseln. Bewahren Sie die `.env` zusätzlich an einem sicheren Ort auf, z. B. in einem Passwort-Manager. Jedes Backup enthält eine Kopie (`env.backup`).

## 7. Konfiguration von PostgreSQL

PostgreSQL wird vollständig über Umgebungsvariablen des offiziellen Images konfiguriert (Ausschnitt aus `docker-compose.yml`):

```yaml
postgres:
  image: postgres:${POSTGRES_VERSION}     # 17.12, gepinnt
  container_name: postgres
  restart: unless-stopped
  environment:
    POSTGRES_DB: ${POSTGRES_DB}
    POSTGRES_USER: ${POSTGRES_USER}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    PGDATA: /var/lib/postgresql/data
  volumes:
    - postgres_data:/var/lib/postgresql/data
  networks: [backend]                     # internes Netz, kein Host-Port
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U \"$${POSTGRES_USER}\" -d \"$${POSTGRES_DB}\" -h 127.0.0.1"]
```

- Beim **ersten** Start mit leerem Volume legt das Image Datenbank und Benutzer an. Spätere Änderungen von `POSTGRES_PASSWORD` in `.env` wirken nicht mehr auf die bestehende Datenbank.
- Es gibt **kein** `ports:` – PostgreSQL ist vom Host und aus dem LAN nicht erreichbar.
- PostgreSQL 17 nutzt `PGDATA=/var/lib/postgresql/data`. Ab PostgreSQL 18 ändert das offizielle Image den Pfad. Ein Major-Upgrade ist in der [Wartungsdokumentation](maintenance.md#manuelles-aktualisieren-von-postgresql) beschrieben.

## 8. Konfiguration von n8n

Die wichtigsten n8n-Variablen (vollständig in `docker-compose.yml`):

| Variable | Wert | Zweck |
| --- | --- | --- |
| `DB_TYPE` | `postgresdb` | PostgreSQL statt SQLite |
| `DB_POSTGRESDB_HOST` | `postgres` | Service-Name im internen Netz |
| `DB_POSTGRESDB_PORT` | `5432` | |
| `DB_POSTGRESDB_DATABASE` / `_USER` / `_PASSWORD` | aus `.env` | |
| `N8N_ENCRYPTION_KEY` | aus `.env` | fest, persistent |
| `N8N_HOST` / `N8N_PROTOCOL` / `N8N_PORT` | `localhost` / `http` / `5678` | |
| `N8N_EDITOR_BASE_URL`, `N8N_WEBHOOK_URL` | `http://localhost:5678/` | |
| `N8N_SECURE_COOKIE` | `false` | nötig für HTTP auf localhost |
| `N8N_DEFAULT_BINARY_DATA_MODE` | `filesystem` | Binärdaten im eigenen Volume |
| `N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS` | `true` | |
| `N8N_DIAGNOSTICS_ENABLED` | `false` | keine Telemetrie |
| `N8N_UNVERIFIED_PACKAGES_ENABLED` | `false` | keine ungeprüften Community-Pakete |
| `EXECUTIONS_DATA_PRUNE` / `_MAX_AGE` | `true` / `336` | Ausführungsdaten nach 14 Tagen löschen |
| `GENERIC_TIMEZONE`, `TZ` | `Europe/Berlin` | Zeitzone für Schedule-Trigger |

## 9. Erklärung der Docker-Compose-Datei

| Element | Konfiguration | Begründung |
| --- | --- | --- |
| `name: n8n-local` | fester Projektname | isoliert von anderen Compose-Projekten |
| Images | `postgres:17.12`, `docker.n8n.io/n8nio/n8n:2.47.7` | offizielle Images, gepinnt, kein `latest` |
| `restart` | `unless-stopped` | Neustart nach Docker-/Systemneustart |
| `depends_on` | `postgres: service_healthy`, `volume-init: service_completed_successfully` | n8n startet erst bei bereiter Datenbank |
| `volume-init` | einmaliger Alpine-Container | setzt Besitzer UID 1000 auf das Binary-Volume |
| Ports | nur `127.0.0.1:5678:5678` | n8n nur lokal erreichbar |
| Netzwerk `backend` | `internal: true` | n8n ↔ PostgreSQL, kein Internetzugang |
| Netzwerk `egress` | Standard-Bridge | nur n8n: GitHub-API, Host-Updater, Port |
| Healthcheck n8n | `GET /healthz/readiness` | prüft DB-Verbindung und Migrationen |
| Healthcheck PostgreSQL | `pg_isready` | |
| `security_opt` | `no-new-privileges:true` | keine Rechteausweitung |
| Ressourcen | n8n 2 GB / 2 CPU, PostgreSQL 1 GB / 2 CPU | schützt den Rechner |
| Logging | `json-file`, 10 MB × 5 | Logrotation |

Die Datei prüfen:

```powershell
docker compose config --quiet     # keine Ausgabe = gültig
```

## 10. Erstellung der persistenten Volumes

Die Volumes werden beim ersten `docker compose up` automatisch mit festen Namen angelegt:

| Volume | Mountpunkt | Inhalt |
| --- | --- | --- |
| `n8n-local_postgres_data` | `/var/lib/postgresql/data` (postgres) | gesamte n8n-Datenbank |
| `n8n-local_n8n_data` | `/home/node/.n8n` (n8n) | Instanz-Konfiguration, Event-Logs, Community-Nodes |
| `n8n-local_n8n_binary` | `/home/node/.n8n/binaryData` (n8n) | Binärdaten von Ausführungen |

Optional vorab anlegen und prüfen:

```powershell
docker volume create n8n-local_postgres_data
docker volume create n8n-local_n8n_data
docker volume create n8n-local_n8n_binary
docker volume ls --filter name=n8n-local
```

> **Hinweis:** Bei Docker Desktop liegen die Volumes in der WSL-2-VM (`docker-desktop`), physisch in der Datei `%LOCALAPPDATA%\Docker\wsl\disk\docker_data.vhdx`. Sie überstehen Container-Neustarts, Image-Updates und `docker compose down`. Nur `docker compose down -v` oder `docker volume rm` löscht sie.

## 11. Starten der Container

```powershell
docker compose pull                       # Images herunterladen
docker compose up -d postgres             # zuerst die Datenbank
docker inspect postgres --format '{{.State.Health.Status}}'   # wiederholen bis "healthy"
docker compose up -d                      # volume-init und n8n
```

Beim ersten Start führt n8n alle Datenbankmigrationen aus (ca. 30–60 s). Den Container währenddessen nicht stoppen.

## 12. Überprüfung der Installation

```powershell
docker compose ps                                       # beide "healthy"
docker logs n8n --tail 30                               # "Editor is now accessible via: http://localhost:5678"
docker exec n8n n8n --version                           # 2.47.7
docker exec postgres psql -U n8n -d n8n -tAc "select count(*) from migrations"   # > 0
Invoke-WebRequest http://localhost:5678/healthz/readiness -UseBasicParsing | Select-Object StatusCode   # 200
.\scripts\health.ps1                                    # alle Checks "ok": true
```

## 13. Erstmalige Einrichtung des n8n-Benutzerkontos

1. <http://localhost:5678> im Browser öffnen.
2. Das Formular „Set up owner account“ ausfüllen (E-Mail, Vor-/Nachname, Passwort mit mind. 8 Zeichen, einer Ziffer und einem Großbuchstaben).
3. Optional den Lizenzschlüssel der kostenlosen Community-Edition anfordern (Settings → Usage and plan).

> **Hinweis zur aktuellen Installation:** Das Owner-Konto wurde automatisiert angelegt (E-Mail `admin@n8n.local`, Passwort in `.env` unter `N8N_OWNER_PASSWORD`). Nach der ersten Anmeldung unter **Settings → Personal** E-Mail und Passwort ändern und die beiden Zeilen anschließend aus `.env` entfernen.

## 14. Zugriff auf die lokale Weboberfläche

- Adresse: **<http://localhost:5678>**, nur von diesem Rechner aus erreichbar.
- Aus dem LAN oder Internet ist n8n bewusst nicht erreichbar. Für externe Webhooks wäre ein abgesicherter Reverse-Proxy mit HTTPS nötig. Das ist nicht Teil dieser Installation.

## 15. Host-Updater und wöchentlichen Workflow einrichten

### 15.1 Host-Updater installieren

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-updater-task.ps1
# erwartet: Host-Updater laeuft: {"ok":true,"service":"n8n-local-updater"}
```

Das Skript registriert die geplante Aufgabe **„n8n-local Host-Updater“**. Sie startet bei der Anmeldung im Benutzerkontext (keine Adminrechte nötig), lauscht nur auf `127.0.0.1:5680` und wird bei einem Absturz minütlich neu gestartet.

### 15.2 Credential für den Updater anlegen

Der Workflow authentifiziert sich per Header `Authorization: Bearer <UPDATER_TOKEN>`. Variante A in der UI:

1. **Credentials → Add credential → „Header Auth“**.
2. Name: `n8n Host Updater Token`, Header-Name: `Authorization`, Value: `Bearer ` + Wert von `UPDATER_TOKEN` aus `.env`.

Variante B per CLI (so wurde es installiert; die temporäre Datei wird sofort gelöscht):

```powershell
$token = (Select-String -Path .env -Pattern '^UPDATER_TOKEN=(.+)$').Matches[0].Groups[1].Value
$cred = ConvertTo-Json -Depth 5 @(@{ id='hostUpdaterCred1'; name='n8n Host Updater Token'; type='httpHeaderAuth';
          data=@{ name='Authorization'; value="Bearer $token" } })
$tmp = New-TemporaryFile; [IO.File]::WriteAllText($tmp, $cred)
docker cp $tmp n8n:/tmp/cred.json; Remove-Item $tmp
docker exec n8n n8n import:credentials --input=/tmp/cred.json
docker exec -u root n8n rm -f /tmp/cred.json
```

n8n verschlüsselt das Credential beim Import mit dem `N8N_ENCRYPTION_KEY`.

### 15.3 Workflow importieren und aktivieren

```powershell
docker cp .\workflows\weekly-n8n-update.json n8n:/tmp/wf.json
docker exec n8n n8n import:workflow --input=/tmp/wf.json
docker exec -u root n8n rm -f /tmp/wf.json
docker exec n8n n8n publish:workflow --id=weeklyN8nUpdater
docker compose restart n8n
```

Alternativ in der UI: **Workflows → Import from file**, im HTTP-Knoten das Credential `n8n Host Updater Token` auswählen und oben rechts **Publish** klicken.

### 15.4 Funktionstest

```powershell
# Workflow einmal manuell ausführen (eigener Task-Broker-Port, da n8n läuft)
docker exec -e N8N_RUNNERS_BROKER_PORT=5690 n8n n8n execute --id=weeklyN8nUpdater --rawOutput
Get-Content .\logs\version-checks.jsonl -Tail 1
```

Erwartet: `"decision": "none"` (aktuell) oder `"decision": "update"` mit `"updateRequested": true`. Im zweiten Fall führt der Host-Updater das Update ca. 20 Sekunden später aus. Das Ergebnis steht danach in `logs\updates.jsonl`.

## Checkliste Neuinstallation

| # | Schritt | Prüfung |
| --- | --- | --- |
| 1 | Docker Desktop + WSL 2 | `docker version` zeigt Server |
| 2 | Projekt kopieren/klonen | Struktur wie oben |
| 3 | `.\scripts\init-env.ps1` | `.env` existiert, Schlüssel sicher verwahrt |
| 4 | `docker compose up -d` | `docker compose ps` → healthy |
| 5 | Owner-Konto anlegen | Login funktioniert |
| 6 | `.\scripts\install-updater-task.ps1` | `/health` antwortet |
| 7 | Credential + Workflow importieren, publizieren | Workflow aktiv |
| 8 | Funktionstest + `.\scripts\backup.ps1` | Backup „verified“ |
