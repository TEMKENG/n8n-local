# n8n-local

Lokale n8n-Installation mit PostgreSQL in Docker Compose. Die Container-Konfiguration ist betriebssystemunabhängig; Windows, Linux und macOS können dieselben Compose-Dateien und persistenten Docker-Volumes verwenden.

Enthalten sind ein abgesichertes Compose-Setup, plattformübergreifende Python-Werkzeuge für Healthchecks, Backups, Restore und Updates sowie ein optionaler wöchentlicher n8n-Update-Workflow. Die PowerShell-Skripte in `scripts/` sind Komfort-Wrapper für Windows; die eigentliche Verwaltung erfolgt über `updater/n8nctl.py`.

## Schnellstart

1. Docker installieren und starten (siehe [Installationsanleitung](docs/installation-guide.md)).
2. Repository in ein selbst gewähltes Verzeichnis klonen.
3. Im Projektverzeichnis `python3 scripts/init-env.py` ausführen (Windows: `py -3 scripts\init-env.py`).
4. `docker compose config --quiet` und anschließend `docker compose up -d` ausführen.
5. <http://localhost:5678> öffnen und das n8n-Owner-Konto erstellen.

## Dokumentation

| Dokument | Markdown | HTML |
| --- | --- | --- |
| Installation unter Windows, Linux und macOS | [Installation](docs/installation-guide.md) | [HTML](docs/installation-guide.html) |
| Architektur, Netzwerke, Volumes und Sicherheit | [Architektur](docs/architecture.md) | [HTML](docs/architecture.html) |
| Betrieb, Backup, Restore und Updates | [Wartung](docs/maintenance.md) | [HTML](docs/maintenance.html) |

Markdown ist die Quelle der HTML-Dokumentation. Nach Änderungen im Repository-Stamm ausführen:

```sh
python3 docs/tools/build_docs.py
python3 docs/tools/build_docs.py --check
```

Unter Windows PowerShell jeweils `py -3` statt `python3` verwenden.

## Verwaltung

Die folgenden Python-Befehle funktionieren auf allen drei Betriebssystemen (Python 3.10+ und Docker CLI erforderlich):

```sh
python3 updater/n8nctl.py health
python3 updater/n8nctl.py backup
python3 updater/n8nctl.py check
python3 updater/n8nctl.py update <version>
```

PowerShell-Nutzer ersetzen in diesen Befehlen `python3` durch `py -3`. Backups enthalten Geheimnisse und Datenbankinhalte. `.env`, `backups/` und Laufzeitlogs sind von Git ausgeschlossen; Backups außerhalb des Rechners nur verschlüsselt speichern. Details und betriebssystemspezifische Hinweise stehen in den verlinkten Dokumenten.
