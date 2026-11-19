# Installationsanleitung: n8n lokal mit Docker und PostgreSQL

Diese Anleitung richtet eine neue lokale Instanz in einem **frei gewählten Installationsverzeichnis** ein. Docker Compose startet n8n und PostgreSQL mit persistenten, benannten Volumes. Die Compose-Befehle sind unter Windows, Linux und macOS gleich; administrative `.ps1`-Wrapper sind nur für Windows.

| Dokument | Inhalt |
| --- | --- |
| **Installation** (dieses Dokument) | Voraussetzungen und Einrichtung |
| [Architektur](architecture.md) | Container, Netzwerke, Volumes und Updater |
| [Wartung](maintenance.md) | Betrieb, Backup, Restore, Updates und Fehleranalyse |

## 1. Voraussetzungen

- Docker Engine mit Docker Compose v2 oder Docker Desktop mit Compose v2.
- Git für das Klonen des Repositorys (oder ein heruntergeladenes Projektarchiv).
- Python 3.10+ für `.env`-Initialisierung und die Verwaltungswerkzeuge.
- Empfohlen: mindestens 8 GB RAM und 10 GB freier Speicher.
- Host-Ports 5678 (Weboberfläche) und optional 5680 (Host-Updater) müssen frei sein.
- Internetverbindung zum Abruf der Container-Images und für n8n-Workflows.

### Windows

1. Windows 10/11 x64 mit aktivierter Hardware-Virtualisierung verwenden.
2. WSL 2 installieren oder aktualisieren (PowerShell als Administrator):

   ```powershell
   wsl --install --no-distribution
   wsl --update
   ```

3. Docker Desktop installieren: <https://docs.docker.com/desktop/setup/install/windows-install/>. WSL 2-Backend aktivieren, Docker Desktop starten und auf „Engine running“ warten.
4. Git für Windows und Python 3 installieren. Bei der Python-Installation `py -3` verfügbar machen.

### Linux

Docker Engine und das Compose-Plugin gemäß der offiziellen Anleitung für die eigene Distribution installieren: <https://docs.docker.com/engine/install/>. Das Compose-Plugin ist hier beschrieben: <https://docs.docker.com/compose/install/linux/>.

```sh
sudo systemctl enable --now docker
docker version
docker compose version
```

Für die Host-Verwaltungswerkzeuge muss Ihr Benutzer auf den Docker-Socket zugreifen können. Auf Distributionen, die die Gruppe `docker` verwenden, richten Sie den Zugriff so ein:

```sh
sudo usermod -aG docker "$USER"
```

Danach vollständig abmelden und erneut anmelden. Die Gruppe `docker` gewährt effektiv Root-Rechte; nehmen Sie nur vertrauenswürdige Benutzer auf. Wenn Sie die Gruppe nicht verwenden möchten, müssen auch die Verwaltungswerkzeuge mit einem passenden Docker-Socket-Zugriff laufen.

### macOS

Docker Desktop für Apple Silicon oder Intel installieren: <https://docs.docker.com/desktop/setup/install/mac-install/>. Docker Desktop starten und warten, bis die Engine betriebsbereit ist. Git ist über Xcode Command Line Tools oder separat verfügbar; Python 3 kann von <https://www.python.org/downloads/macos/> installiert werden.

## 2. Docker und Compose prüfen

In PowerShell, Terminal oder einer Shell:

```sh
docker version
docker compose version
docker run --rm hello-world
```

`docker version` muss Client und Server anzeigen. Wenn nur der Client erscheint, Docker Desktop bzw. den Docker-Dienst starten. Die Compose-Datei erwartet Linux-Container.

## 3. Projekt in einem eigenen Verzeichnis beziehen

Wählen Sie ein Verzeichnis, in dem Ihr Benutzer Schreibrechte hat und in dem Docker-Daten bzw. Backups ausreichend Platz haben. Die folgenden Verzeichnisse sind Beispiele, keine Voraussetzungen.

**Windows PowerShell:**

```powershell
$InstallDir = Join-Path $HOME 'n8n-local'
git clone https://github.com/TEMKENG/n8n-local.git $InstallDir
Set-Location $InstallDir
```

**Linux / macOS (Bash, Zsh):**

```sh
INSTALL_DIR="$HOME/n8n-local"
git clone https://github.com/TEMKENG/n8n-local.git "$INSTALL_DIR"
cd "$INSTALL_DIR"
```

Wenn Sie ein anderes Installationsverzeichnis wählen, muss dessen übergeordnetes Verzeichnis bereits vorhanden sein. Wenn Sie das Projekt bereits ausgecheckt haben, wechseln Sie stattdessen in dessen Stammverzeichnis. Alle weiteren relativen Pfade beziehen sich auf dieses Verzeichnis.

## 4. Geheimnisse erzeugen und `.env` konfigurieren

Im Projektstamm (Linux/macOS):

```sh
python3 scripts/init-env.py
```

Unter Windows PowerShell:

```powershell
py -3 scripts\init-env.py
```

Das Skript erzeugt `.env` aus `.env.example`, generiert ein eigenes Datenbankpasswort, einen persistenten `N8N_ENCRYPTION_KEY` und ein Updater-Token und bricht ab, falls `.env` bereits existiert. Unter Linux/macOS erhält die Datei Benutzer-Lese-/Schreibrechte. Windows übernimmt die ACL des Installationsverzeichnisses; speichern Sie das Projekt dort nur in einem benutzergeschützten Verzeichnis.

Die zentralen Einstellungen in `.env`:

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `N8N_VERSION` | `2.47.7` | fest gepinnte n8n-Version |
| `POSTGRES_VERSION` | `17.12` | fest gepinnte PostgreSQL-Version |
| `POSTGRES_DB`, `POSTGRES_USER` | `n8n` | Datenbank und Benutzer |
| `POSTGRES_PASSWORD` | zufällig erzeugt | Datenbankpasswort |
| `N8N_ENCRYPTION_KEY` | zufällig erzeugt | Schlüssel für gespeicherte n8n-Credentials |
| `N8N_PORT` | `5678` | lokaler Browser-Port |
| `TZ`, `GENERIC_TIMEZONE` | `Europe/Berlin` | Container- und Workflow-Zeitzone |
| `UPDATER_TOKEN` | zufällig erzeugt | Authentifizierung des optionalen Host-Updaters |

Sie können `N8N_PORT` ändern, wenn Port 5678 belegt ist. Ändern Sie den Encryption Key nach dem ersten Start nicht: Ohne den ursprünglichen Schlüssel können gespeicherte Credentials nicht entschlüsselt werden. `.env` niemals committen oder unverschlüsselt weitergeben.

## 5. Konfiguration prüfen und Container starten

Alle folgenden Befehle sind im Projektstamm auszuführen:

```sh
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
```

Beim ersten Start lädt Docker die Images und n8n führt Datenbankmigrationen aus. Warten Sie, bis sowohl `postgres` als auch `n8n` den Status `healthy` haben:

```sh
docker compose ps
docker compose logs --tail 50 n8n
```

Der Readiness-Endpunkt prüft n8n und die Datenbank:

```sh
curl --fail http://localhost:5678/healthz/readiness
```

In PowerShell können Sie stattdessen verwenden:

```powershell
(Invoke-WebRequest http://localhost:5678/healthz/readiness).StatusCode
```

Der erfolgreiche HTTP-Status ist `200`. Falls Sie `N8N_PORT` geändert haben, verwenden Sie den eingestellten Port.

## 6. n8n initial einrichten

1. Öffnen Sie `http://localhost:5678`.
2. Erstellen Sie im n8n-Einrichtungsdialog Ihr persönliches Owner-Konto.
3. Melden Sie sich an und prüfen Sie, ob der Editor funktioniert.

Der Host-Port ist an `127.0.0.1` gebunden. Die Weboberfläche ist deshalb standardmäßig nur auf dem lokalen Computer erreichbar. Für externen Zugriff wäre eine gesondert abgesicherte HTTPS-/Reverse-Proxy-Konfiguration erforderlich.

## 7. Host-Updater und automatisierten Workflow (optional)

Die Infrastruktur und manuelle Updates funktionieren ohne einen laufenden Host-Updater. Die PowerShell-Installation als geplante Aufgabe ist ausschließlich für Windows vorgesehen:

```powershell
.\scripts\install-updater-task.ps1
```

Der Task startet den Python-Updater bei der Anmeldung. Für Windows ohne Task Scheduler sowie macOS kann der Updater in einem eigenen Terminal gestartet werden:

```sh
python3 updater/n8nctl.py serve
```

Das Terminal muss geöffnet bleiben. Docker Desktop stellt `host.docker.internal` unter Windows/macOS bereit; die Verbindung des Updater-Prozesses zur Containerumgebung kann je nach Host-Firewall und Docker-Desktop-Version abweichen und wurde hier nicht auf allen Versionen getestet.

**Linux-Hinweis:** Der Updater bindet standardmäßig ausschließlich an Loopback (`127.0.0.1`), was aus einem Container auf nativem Docker Engine nicht direkt erreichbar ist. Veröffentlichen Sie ihn nicht ungeschützt auf allen Netzwerkschnittstellen. Lassen Sie den Update-Workflow deaktiviert, sofern Sie nicht bewusst eine auf den Docker-Host beschränkte Netzwerk-/Firewall-Lösung eingerichtet haben. Manuelle Verwaltungsbefehle funktionieren weiterhin.

Wenn der Updater erreichbar ist, können Sie in n8n ein Header-Auth-Credential mit `Authorization: Bearer <UPDATER_TOKEN>` aus `.env` anlegen und `workflows/weekly-n8n-update.json` importieren. Prüfen Sie vor dem Aktivieren die Hinweise in [Architektur](architecture.md#host-updater) und [Wartung](maintenance.md#updates-und-host-updater).

## 8. Nützliche Befehle

```sh
docker compose ps
docker compose logs -f n8n
docker compose stop
docker compose up -d
python3 updater/n8nctl.py health
python3 updater/n8nctl.py backup
```

Mit `docker compose down` werden Container und Netzwerk entfernt, die Volumes bleiben erhalten. **Nicht** `docker compose down -v` verwenden, wenn Daten erhalten bleiben sollen.

## Installationsprüfung

| Prüfung | Erwartung |
| --- | --- |
| `docker version` | Client und Server vorhanden |
| `docker compose config --quiet` | keine Fehlermeldung |
| `docker compose ps` | `postgres` und `n8n` healthy |
| `curl http://localhost:5678/healthz/readiness` | HTTP 200 |
| n8n im Browser | Owner-Konto kann erstellt werden |
| `python3 updater/n8nctl.py health` (Windows: `py -3 updater\n8nctl.py health`) | alle Healthchecks erfolgreich |

Die Compose-Konfiguration und Python-Hilfsprogramme sind betriebssystemunabhängig. Getestet werden kann die reale Container- und Host-Updater-Integration nur auf den jeweils verfügbaren Docker-Hosts; die Linux-Host-Updater-Einschränkung ist oben ausdrücklich dokumentiert.
