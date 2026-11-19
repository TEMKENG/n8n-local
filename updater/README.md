# Host-Updater (`n8nctl.py`)

Einziger Baustein, der Docker steuert. n8n spricht ihn über `http://host.docker.internal:5680` mit Bearer-Token an und hat selbst keinen Docker-Socket-Zugriff.

- Nur Python-Standardbibliothek, lauscht nur auf `127.0.0.1:5680`.
- Start über die Windows-Aufgabe „n8n-local Host-Updater“ (`scripts/install-updater-task.ps1`).
- Endpunkte: `GET /health`, `GET /status`, `GET /check`, `POST /update` (`{"version":"x.y.z","dryRun":true}`), `POST /check-log`.
- Updates laufen als separater Prozess: Sperre, Vorabprüfung, verifiziertes Backup, Pull, Versionswechsel, Healthchecks und bei Fehlern ein vollständiger Rollback (DB + Volumes + Version).
- Protokolle: `logs/updates.jsonl`, `logs/version-checks.jsonl`, `logs/updater.log`.

CLI-Hilfe: `python updater\n8nctl.py --help`. Details: [docs/architecture.md](../docs/architecture.md#host-updater-architektur).
