# Host-Verwaltung (`n8nctl.py`)

Das Python-Werkzeug verwaltet Docker Compose, Healthchecks, Backups, Restore und n8n-Updates. Es benötigt Python 3.10+, Docker CLI/Compose und eine erzeugte `.env` im Projektstamm. Es verwendet keine zusätzlichen Python-Pakete.

Alle Befehle aus dem Projektstamm ausführen:

```sh
python3 updater/n8nctl.py --help
python3 updater/n8nctl.py health
python3 updater/n8nctl.py backup
python3 updater/n8nctl.py restore backups/<backup-ordner>
python3 updater/n8nctl.py check
python3 updater/n8nctl.py update <version>
```

Unter Windows PowerShell `python3` durch `py -3` ersetzen. Die optionale HTTP-API `python3 updater/n8nctl.py serve` lauscht standardmäßig nur auf `127.0.0.1:5680` und verlangt für administrative Endpunkte einen Bearer-Token aus `.env`. Unter Windows kann `scripts/install-updater-task.ps1` den Prozess in der Aufgabenplanung starten. Auf macOS kann er in einem geöffneten Terminal laufen. Unter nativem Linux kann der Docker-Container den Loopback-gebundenen Hostprozess standardmäßig nicht erreichen; öffnen Sie den Dienst nicht ohne gezielte Netzwerk- und Firewall-Konfiguration für alle Interfaces.

Der optionale n8n-Workflow ruft diese API über `host.docker.internal` auf. Aktivieren Sie ihn erst, wenn die Host-Verbindung tatsächlich funktioniert. Details: [Architektur](../docs/architecture.md#host-updater) und [Installation](../docs/installation-guide.md#7-host-updater-und-automatisierten-workflow-optional).
