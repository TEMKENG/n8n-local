#!/usr/bin/env python3
"""
n8nctl - Host-seitiges Verwaltungswerkzeug fuer die lokale n8n-Installation.

Unterbefehle:
  status            Zustand der Installation als JSON
  health            Alle Healthchecks ausfuehren (Exit 0 = gesund)
  check             Neueste stabile n8n-Version auf GitHub ermitteln
  backup            Konsistentes, verifiziertes Backup erstellen
  verify DIR        Backup pruefen (Hashes, Dump, Archive)
  restore DIR       Backup wiederherstellen (Datenbank + n8n-Volumes)
  update VERSION    Abgesichertes Update mit Backup, Healthchecks, Rollback
  prune             Aufbewahrungsregel auf backups/ anwenden
  serve             Authentifizierte HTTP-Schnittstelle fuer den n8n-Workflow

Sicherheitsprinzipien:
  * Fuehrt ausschliesslich fest definierte docker/docker-compose-Aufrufe aus,
    immer als Argumentliste (keine Shell, keine Benutzereingabe im Befehl).
  * Veraendert nur das Compose-Projekt "n8n-local" in PROJECT_ROOT.
  * PostgreSQL wird bei einem Update nie neu erstellt; nur bei einem Rollback
    wird die Datenbank aus dem zugehoerigen Backup wiederhergestellt.
  * Nur Python-Standardbibliothek.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
BACKUP_DIR = PROJECT_ROOT / "backups"
LOG_DIR = PROJECT_ROOT / "logs"
STATE_DIR = PROJECT_ROOT / "updater" / "state"
LOCK_FILE = STATE_DIR / "update.lock"
CURRENT_FILE = STATE_DIR / "current-update.json"
UPDATE_LOG = LOG_DIR / "updates.jsonl"
CHECK_LOG = LOG_DIR / "version-checks.jsonl"
TEXT_LOG = LOG_DIR / "updater.log"

PROJECT_NAME = "n8n-local"
N8N_CONTAINER = "n8n"
PG_CONTAINER = "postgres"
N8N_IMAGE_REPO = "docker.n8n.io/n8nio/n8n"
HELPER_IMAGE = "alpine:3.22"
VOLUMES = {
    "n8n-data.tar.gz": "n8n-local_n8n_data",
    "n8n-binary.tar.gz": "n8n-local_n8n_binary",
}
GITHUB_RELEASES = "https://api.github.com/repos/n8n-io/n8n/releases"
SEMVER_RE = re.compile(r"^(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,5})$")
STABLE_TAG_RE = re.compile(r"^n8n@(\d+\.\d+\.\d+)$")
LOCK_STALE_SECONDS = 3 * 3600
HEALTH_TIMEOUT_SECONDS = 600

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
class N8nCtlError(Exception):
    pass


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{now_iso()} [pid {os.getpid()}] {msg}"
    with TEXT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    try:
        print(line, file=sys.stderr, flush=True)
    except Exception:  # pythonw hat kein stderr
        pass


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        raise N8nCtlError(f"{ENV_FILE} fehlt")
    return parse_env(ENV_FILE.read_text(encoding="utf-8-sig"))


def parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip()
    return values


def set_env_value(key: str, value: str) -> None:
    """Ersetzt genau eine Zeile KEY=... atomar; alle anderen Zeilen bleiben."""
    text = ENV_FILE.read_text(encoding="utf-8-sig")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if not pattern.search(text):
        raise N8nCtlError(f"{key} nicht in .env gefunden")
    new_text = pattern.sub(f"{key}={value}", text, count=1)
    tmp = ENV_FILE.with_suffix(".tmp")
    tmp.write_text(new_text, encoding="utf-8", newline="\n")
    os.replace(tmp, ENV_FILE)


def semver(v: str) -> tuple[int, int, int]:
    m = SEMVER_RE.match(v or "")
    if not m:
        raise N8nCtlError(f"Ungueltige Version: {v!r}")
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


def run(args: list[str], *, check: bool = True, timeout: int = 600,
        stdin=None, stdout=None, capture: bool = True) -> subprocess.CompletedProcess:
    """Fuehrt docker-Befehle als Argumentliste aus (nie ueber eine Shell)."""
    if args[0] != "docker":
        raise N8nCtlError("Nur docker-Aufrufe sind erlaubt")
    kwargs = dict(cwd=PROJECT_ROOT, timeout=timeout, creationflags=NO_WINDOW, stdin=stdin)
    if stdout is not None:
        kwargs["stdout"] = stdout
        kwargs["stderr"] = subprocess.PIPE
    elif capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    proc = subprocess.run(args, **kwargs)
    if check and proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "replace").strip()
        raise N8nCtlError(f"Befehl fehlgeschlagen ({proc.returncode}): {' '.join(args[:4])} ... {err[-500:]}")
    return proc


def out(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout or b"").decode("utf-8", "replace").strip()


def compose(*args: str, check: bool = True, timeout: int = 900) -> subprocess.CompletedProcess:
    return run(["docker", "compose", "--project-directory", str(PROJECT_ROOT),
                "-f", str(COMPOSE_FILE), "-p", PROJECT_NAME, *args], check=check, timeout=timeout)


def http_get(url: str, timeout: int = 10, headers: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "n8n-local-updater", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if exc.fp else b""
    except Exception:
        return 0, b""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Zustand & Healthchecks
# --------------------------------------------------------------------------- #
def container_state(name: str) -> dict:
    proc = run(["docker", "inspect", name, "--format",
                "{{json .State}}|{{.Config.Image}}"], check=False, timeout=30)
    if proc.returncode != 0:
        return {"exists": False}
    state_json, image = out(proc).rsplit("|", 1)
    st = json.loads(state_json)
    return {
        "exists": True,
        "running": st.get("Running", False),
        "status": st.get("Status"),
        "health": (st.get("Health") or {}).get("Status"),
        "startedAt": st.get("StartedAt"),
        "image": image,
    }


def running_n8n_version() -> str | None:
    proc = run(["docker", "exec", N8N_CONTAINER, "n8n", "--version"], check=False, timeout=60)
    if proc.returncode != 0:
        return None
    for line in out(proc).splitlines():
        if SEMVER_RE.match(line.strip()):
            return line.strip()
    return None


def health_report(expected_version: str | None = None) -> dict:
    env = read_env()
    port = env.get("N8N_PORT", "5678")
    checks: dict[str, dict] = {}

    pg = container_state(PG_CONTAINER)
    checks["postgres_container"] = {"ok": bool(pg.get("running")) and pg.get("health") == "healthy",
                                    "detail": pg.get("health") or pg.get("status")}
    n8n = container_state(N8N_CONTAINER)
    checks["n8n_container"] = {"ok": bool(n8n.get("running")) and n8n.get("health") == "healthy",
                               "detail": n8n.get("health") or n8n.get("status")}

    version = running_n8n_version() if n8n.get("running") else None
    want = expected_version or env.get("N8N_VERSION")
    checks["n8n_version"] = {"ok": version == want, "detail": f"laufend={version} erwartet={want}"}

    proc = run(["docker", "exec", PG_CONTAINER, "psql", "-U", env.get("POSTGRES_USER", "n8n"),
                "-d", env.get("POSTGRES_DB", "n8n"), "-tAc",
                "select count(*) from migrations"], check=False, timeout=30)
    ok_db = proc.returncode == 0 and out(proc).isdigit() and int(out(proc)) > 0
    checks["database_schema"] = {"ok": ok_db, "detail": f"migrations={out(proc) if proc.returncode == 0 else 'n/a'}"}

    code, _ = http_get(f"http://127.0.0.1:{port}/healthz/readiness")
    checks["n8n_readiness"] = {"ok": code == 200, "detail": f"HTTP {code}"}
    code, body = http_get(f"http://127.0.0.1:{port}/")
    checks["web_ui"] = {"ok": code == 200 and b"<html" in body.lower(), "detail": f"HTTP {code}"}

    return {"ok": all(c["ok"] for c in checks.values()), "checkedAt": now_iso(), "checks": checks}


def wait_healthy(expected_version: str, timeout: int = HEALTH_TIMEOUT_SECONDS) -> dict:
    start = time.time()
    report: dict = {}
    while time.time() - start < timeout:
        report = health_report(expected_version)
        if report["ok"]:
            return report
        n8n = container_state(N8N_CONTAINER)
        # Dauerhaft ungesund/abgestuerzt (nach Anlaufzeit) -> nicht weiter warten.
        if time.time() - start > 180 and (n8n.get("health") == "unhealthy"
                                          or n8n.get("status") in ("exited", "dead")):
            return report
        time.sleep(10)
    return report


def status() -> dict:
    env = read_env()
    last = None
    if UPDATE_LOG.exists():
        lines = UPDATE_LOG.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            last = json.loads(lines[-1])
    current = None
    if CURRENT_FILE.exists():
        try:
            current = json.loads(CURRENT_FILE.read_text(encoding="utf-8"))
        except Exception:
            current = None
    n8n = container_state(N8N_CONTAINER)
    return {
        "configuredVersion": env.get("N8N_VERSION"),
        "runningVersion": running_n8n_version() if n8n.get("running") else None,
        "postgresVersion": env.get("POSTGRES_VERSION"),
        "n8nContainer": n8n,
        "postgresContainer": container_state(PG_CONTAINER),
        "updateInProgress": lock_active(),
        "currentUpdate": current if lock_active() else None,
        "lastUpdate": last,
        "time": now_iso(),
    }


# --------------------------------------------------------------------------- #
# Versionsermittlung
# --------------------------------------------------------------------------- #
def fetch_stable_releases() -> list[dict]:
    code, body = http_get(f"{GITHUB_RELEASES}?per_page=100", timeout=20,
                          headers={"Accept": "application/vnd.github+json"})
    if code != 200:
        raise N8nCtlError(f"GitHub-API antwortete mit HTTP {code}")
    result = []
    for rel in json.loads(body):
        m = STABLE_TAG_RE.match(rel.get("tag_name", ""))
        if m and not rel.get("prerelease") and not rel.get("draft"):
            result.append({"version": m.group(1), "url": rel.get("html_url"),
                           "publishedAt": rel.get("published_at"), "body": rel.get("body") or ""})
    result.sort(key=lambda r: semver(r["version"]), reverse=True)
    return result


def get_release(version: str) -> dict:
    code, body = http_get(f"{GITHUB_RELEASES}/tags/n8n%40{version}", timeout=20,
                          headers={"Accept": "application/vnd.github+json"})
    if code != 200:
        raise N8nCtlError(f"Release n8n@{version} nicht gefunden (HTTP {code})")
    rel = json.loads(body)
    if rel.get("draft") or rel.get("prerelease") or rel.get("tag_name") != f"n8n@{version}":
        raise N8nCtlError(f"n8n@{version} ist kein offizielles stabiles Release")
    return rel


def check_latest() -> dict:
    env = read_env()
    installed = env["N8N_VERSION"]
    releases = fetch_stable_releases()
    if not releases:
        raise N8nCtlError("Keine stabile Version gefunden")
    latest = releases[0]
    return {"installedVersion": installed, "latestVersion": latest["version"],
            "updateAvailable": semver(latest["version"]) > semver(installed),
            "releaseUrl": latest["url"], "publishedAt": latest["publishedAt"]}


# --------------------------------------------------------------------------- #
# Backup / Verify / Restore
# --------------------------------------------------------------------------- #
def volume_size(volume: str) -> int:
    proc = run(["docker", "run", "--rm", "-v", f"{volume}:/d:ro", HELPER_IMAGE,
                "du", "-sb", "/d"], timeout=300)
    return int(out(proc).split()[0])


def ensure_disk_space(min_extra_bytes: int = 0) -> dict:
    env = read_env()
    min_free = int(env.get("MIN_FREE_GB", "5")) * 1024 ** 3
    sizes = {v: volume_size(v) for v in ["n8n-local_postgres_data", *VOLUMES.values()]}
    needed = 2 * sum(sizes.values()) + min_free + min_extra_bytes
    free = shutil.disk_usage(PROJECT_ROOT).free
    info = {"freeBytes": free, "requiredBytes": needed, "volumeBytes": sizes}
    if free < needed:
        raise N8nCtlError(f"Zu wenig Speicherplatz: frei {free / 1e9:.1f} GB, benoetigt {needed / 1e9:.1f} GB")
    return info


def backup(reason: str = "manual", stop_n8n: bool = True) -> Path:
    env = read_env()
    disk = ensure_disk_space()
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_reason = re.sub(r"[^a-z0-9-]", "", reason.lower())[:30] or "manual"
    target = BACKUP_DIR / f"{stamp}-{safe_reason}"
    partial = target.with_name(target.name + ".partial")
    partial.mkdir()
    log(f"Backup startet: {target.name}")

    was_running = bool(container_state(N8N_CONTAINER).get("running"))
    if stop_n8n and was_running:
        # n8n anhalten, damit Datenbank und Dateien denselben Zeitpunkt abbilden.
        compose("stop", "-t", "60", "n8n")
    try:
        with (partial / "database.dump").open("wb") as fh:
            run(["docker", "exec", PG_CONTAINER, "pg_dump", "-U", env["POSTGRES_USER"],
                 "-d", env["POSTGRES_DB"], "-Fc", "-Z", "6"], stdout=fh, timeout=1800)
        with (partial / "globals.sql").open("wb") as fh:
            run(["docker", "exec", PG_CONTAINER, "pg_dumpall", "-U", env["POSTGRES_USER"],
                 "--globals-only"], stdout=fh, timeout=300)
        for archive, volume in VOLUMES.items():
            with (partial / archive).open("wb") as fh:
                run(["docker", "run", "--rm", "-v", f"{volume}:/data:ro", HELPER_IMAGE,
                     "tar", "-czf", "-", "-C", "/data", "."], stdout=fh, timeout=1800)
        shutil.copy2(ENV_FILE, partial / "env.backup")
        shutil.copy2(COMPOSE_FILE, partial / "docker-compose.yml")
        pg_image = container_state(PG_CONTAINER).get("image")
        manifest = {
            "createdAt": now_iso(),
            "reason": safe_reason,
            "n8nVersion": env["N8N_VERSION"],
            "n8nRunningVersion": None,
            "postgresVersion": env["POSTGRES_VERSION"],
            "postgresImage": pg_image,
            "n8nImage": f"{N8N_IMAGE_REPO}:{env['N8N_VERSION']}",
            "encryptionKeySha256": hashlib.sha256(env["N8N_ENCRYPTION_KEY"].encode()).hexdigest(),
            "n8nWasStopped": stop_n8n and was_running,
            "host": os.environ.get("COMPUTERNAME", ""),
            "disk": disk,
            "files": {},
        }
        for f in sorted(partial.iterdir()):
            manifest["files"][f.name] = {"bytes": f.stat().st_size, "sha256": sha256_file(f)}
        (partial / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        verify(partial)
        os.replace(partial, target)
    except Exception:
        log(f"Backup FEHLGESCHLAGEN: {partial.name}")
        shutil.rmtree(partial, ignore_errors=True)
        raise
    finally:
        if stop_n8n and was_running:
            compose("start", "n8n", check=False)
    log(f"Backup verifiziert: {target}")
    try:
        prune()
    except Exception as exc:  # Aufraeumen darf ein gueltiges Backup nicht ungueltig machen
        log(f"Aufraeumen der Backups fehlgeschlagen: {exc}")
    return target


def verify(directory: Path) -> dict:
    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        raise N8nCtlError(f"manifest.json fehlt in {directory}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"database.dump", "globals.sql", "env.backup", "docker-compose.yml", *VOLUMES.keys()}
    missing = required - set(manifest["files"])
    if missing:
        raise N8nCtlError(f"Backup unvollstaendig: {sorted(missing)}")
    for name, meta in manifest["files"].items():
        path = directory / name
        if not path.exists() or path.stat().st_size != meta["bytes"] or meta["bytes"] == 0 and name != "globals.sql":
            raise N8nCtlError(f"Datei fehlt/leer/abweichend: {name}")
        if sha256_file(path) != meta["sha256"]:
            raise N8nCtlError(f"SHA256 stimmt nicht: {name}")
    # Datenbank-Dump muss von pg_restore lesbar sein und n8n-Tabellen enthalten.
    with (directory / "database.dump").open("rb") as fh:
        proc = run(["docker", "exec", "-i", PG_CONTAINER, "pg_restore", "--list"], stdin=fh, timeout=600)
    toc = out(proc)
    for table in ("workflow_entity", "credentials_entity", "migrations"):
        if f"TABLE DATA public {table}" not in toc:
            raise N8nCtlError(f"Dump enthaelt keine Daten fuer Tabelle {table}")
    # Archive muessen vollstaendig lesbar sein.
    for archive in VOLUMES:
        with tarfile.open(directory / archive, "r:gz") as tf:
            tf.getmembers()
    env_backup = parse_env((directory / "env.backup").read_text(encoding="utf-8-sig"))
    if hashlib.sha256(env_backup.get("N8N_ENCRYPTION_KEY", "").encode()).hexdigest() != manifest["encryptionKeySha256"]:
        raise N8nCtlError("Encryption Key im Backup passt nicht zum Manifest")
    return manifest


def wait_postgres(timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if container_state(PG_CONTAINER).get("health") == "healthy":
            return
        time.sleep(3)
    raise N8nCtlError("PostgreSQL wurde nicht gesund")


def restore(directory: Path, *, restore_env: bool = False, safety_backup: bool = True,
            start: bool = True) -> dict:
    directory = Path(directory).resolve()
    manifest = verify(directory)
    env_backup = parse_env((directory / "env.backup").read_text(encoding="utf-8-sig"))

    if ENV_FILE.exists():
        env = read_env()
        same_key = hmac.compare_digest(env.get("N8N_ENCRYPTION_KEY", ""), env_backup["N8N_ENCRYPTION_KEY"])
        if not same_key and not restore_env:
            raise N8nCtlError("Encryption Key in .env unterscheidet sich vom Backup. "
                              "Mit --restore-env die .env aus dem Backup uebernehmen.")
    else:
        restore_env = True

    if safety_backup and container_state(PG_CONTAINER).get("running"):
        try:
            backup("pre-restore")
        except Exception as exc:
            raise N8nCtlError(f"Sicherheits-Backup vor Restore fehlgeschlagen: {exc}")

    log(f"Restore startet aus {directory.name}")
    if restore_env:
        shutil.copy2(directory / "env.backup", ENV_FILE)
    else:
        # Nur die Versionen auf den Stand des Backups setzen, Geheimnisse bleiben.
        set_env_value("N8N_VERSION", env_backup["N8N_VERSION"])
        set_env_value("POSTGRES_VERSION", env_backup["POSTGRES_VERSION"])
    env = read_env()

    compose("stop", "-t", "60", "n8n", check=False)
    compose("up", "-d", "postgres")
    wait_postgres()

    for archive, volume in VOLUMES.items():
        run(["docker", "volume", "create", volume])
        with (directory / archive).open("rb") as fh:
            run(["docker", "run", "--rm", "-i", "-v", f"{volume}:/data", HELPER_IMAGE, "sh", "-c",
                 "find /data -mindepth 1 -delete && tar -xzf - -C /data"], stdin=fh, timeout=1800)

    user, db = env["POSTGRES_USER"], env["POSTGRES_DB"]
    run(["docker", "exec", PG_CONTAINER, "dropdb", "-U", user, "--maintenance-db=postgres",
         "--if-exists", "--force", db])
    run(["docker", "exec", PG_CONTAINER, "createdb", "-U", user, "-O", user, db])
    with (directory / "database.dump").open("rb") as fh:
        run(["docker", "exec", "-i", PG_CONTAINER, "pg_restore", "-U", user, "-d", db,
             "--no-owner", "--role", user, "--exit-on-error"], stdin=fh, timeout=3600)
    log("Datenbank und Volumes wiederhergestellt")

    report = {"ok": True, "skipped": True}
    if start:
        compose("up", "-d", "n8n")
        report = wait_healthy(env["N8N_VERSION"])
        log(f"Healthcheck nach Restore: {'OK' if report['ok'] else 'FEHLER'}")
        if not report["ok"]:
            raise N8nCtlError(f"Healthcheck nach Restore fehlgeschlagen: {json.dumps(report['checks'])}")
    return {"restoredFrom": str(directory), "version": env["N8N_VERSION"], "health": report,
            "manifest": manifest["createdAt"]}


def prune() -> list[str]:
    env = read_env()
    days = int(env.get("BACKUP_RETENTION_DAYS", "30"))
    keep_min = int(env.get("BACKUP_KEEP_MIN", "5"))
    if not BACKUP_DIR.exists():
        return []
    dirs = sorted([d for d in BACKUP_DIR.iterdir()
                   if d.is_dir() and re.match(r"^\d{8}-\d{6}-[a-z0-9-]+$", d.name)],
                  key=lambda d: d.name, reverse=True)
    cutoff = dt.datetime.now() - dt.timedelta(days=days)
    removed = []
    for d in dirs[keep_min:]:
        created = dt.datetime.strptime(d.name[:15], "%Y%m%d-%H%M%S")
        if created < cutoff:
            shutil.rmtree(d)
            removed.append(d.name)
    # Abgebrochene Teil-Backups aelter als 1 Tag entfernen
    for d in BACKUP_DIR.glob("*.partial"):
        if time.time() - d.stat().st_mtime > 86400:
            shutil.rmtree(d, ignore_errors=True)
    if removed:
        log(f"Alte Backups entfernt: {removed}")
    return removed


# --------------------------------------------------------------------------- #
# Update-Sperre
# --------------------------------------------------------------------------- #
def lock_active() -> bool:
    if not LOCK_FILE.exists():
        return False
    try:
        info = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        age = time.time() - float(info.get("epoch", 0))
    except Exception:
        age = time.time() - LOCK_FILE.stat().st_mtime
    if age > LOCK_STALE_SECONDS:
        log("Veraltete Update-Sperre entfernt")
        LOCK_FILE.unlink(missing_ok=True)
        return False
    return True


def acquire_lock(version: str, request_id: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock_active()  # entfernt ggf. veraltete Sperre
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise N8nCtlError("Es laeuft bereits ein Update (Sperre aktiv)")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"version": version, "requestId": request_id, "epoch": time.time(),
                   "pid": os.getpid(), "since": now_iso()}, fh)


def release_lock() -> None:
    LOCK_FILE.unlink(missing_ok=True)
    CURRENT_FILE.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Update
# --------------------------------------------------------------------------- #
def preflight(version: str, allow_major: bool = False) -> dict:
    """Prueft, ob ein Update auf VERSION zulaessig ist. Veraendert nichts."""
    semver(version)
    env = read_env()
    installed = env["N8N_VERSION"]
    result: dict = {"targetVersion": version, "installedVersion": installed, "checks": {}}
    c = result["checks"]

    c["newer"] = semver(version) > semver(installed)
    c["sameMajor"] = semver(version)[0] == semver(installed)[0]
    try:
        rel = get_release(version)
        c["officialStableRelease"] = True
        notes = rel.get("body") or ""
        result["releaseUrl"] = rel.get("html_url")
        c["noBreakingChangeNotice"] = not re.search(r"breaking change", notes, re.IGNORECASE)
    except N8nCtlError as exc:
        c["officialStableRelease"] = False
        c["noBreakingChangeNotice"] = False
        result["releaseError"] = str(exc)
    c["imageAvailable"] = run(["docker", "manifest", "inspect", f"{N8N_IMAGE_REPO}:{version}"],
                              check=False, timeout=120).returncode == 0
    try:
        result["disk"] = ensure_disk_space(min_extra_bytes=2 * 1024 ** 3)
        c["diskSpace"] = True
    except N8nCtlError as exc:
        c["diskSpace"] = False
        result["diskError"] = str(exc)
    c["noUpdateRunning"] = not lock_active()
    c["currentInstallationHealthy"] = health_report()["ok"]

    required = ["newer", "officialStableRelease", "imageAvailable", "diskSpace",
                "noUpdateRunning", "currentInstallationHealthy"]
    if not allow_major:
        required += ["sameMajor", "noBreakingChangeNotice"]
    result["required"] = required
    result["ok"] = all(c[k] for k in required)
    result["failed"] = [k for k in required if not c[k]]
    return result


def update(version: str, *, request_id: str | None = None, delay: int = 0,
           lock_held: bool = False, allow_major: bool = False,
           simulate_failure: bool = False, requested_by: str = "cli") -> dict:
    request_id = request_id or uuid.uuid4().hex[:12]
    if not lock_held:
        acquire_lock(version, request_id)
    started = time.time()
    record: dict = {
        "requestId": request_id, "requestedBy": requested_by, "startedAt": now_iso(),
        "versionBefore": None, "targetVersion": version, "versionAfter": None,
        "backup": None, "backupStatus": "not-started", "health": None,
        "status": "running", "rollback": None, "error": None, "steps": [],
        "simulatedFailure": simulate_failure,
    }

    def step(name: str, **extra) -> None:
        entry = {"at": now_iso(), "step": name, **extra}
        record["steps"].append(entry)
        log(f"[update {request_id}] {name} {extra if extra else ''}")
        CURRENT_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")

    try:
        if delay:
            step("waiting", seconds=delay, why="n8n-Ausfuehrung soll vor dem Neustart abschliessen")
            time.sleep(delay)
        env = read_env()
        record["versionBefore"] = env["N8N_VERSION"]
        record["previousImage"] = f"{N8N_IMAGE_REPO}:{env['N8N_VERSION']}"
        digest = run(["docker", "image", "inspect", record["previousImage"], "--format",
                      "{{index .RepoDigests 0}}"], check=False)
        record["previousImageDigest"] = out(digest) or None

        step("preflight")
        if simulate_failure:
            pf = {"ok": True, "simulated": True}
        else:
            # Die eigene Sperre ist hier gesetzt -> noUpdateRunning ignorieren.
            pf = preflight(version, allow_major)
            pf["checks"]["noUpdateRunning"] = True
            pf["failed"] = [k for k in pf["required"] if not pf["checks"][k]]
            pf["ok"] = not pf["failed"]
        record["preflight"] = pf
        if not pf["ok"]:
            raise N8nCtlError(f"Vorabpruefung fehlgeschlagen: {pf['failed']}")

        step("backup")
        record["backupStatus"] = "running"
        bdir = backup("pre-update")
        record["backup"] = str(bdir)
        record["backupStatus"] = "verified"
    except Exception as exc:
        record.update(status="aborted", error=str(exc), finishedAt=now_iso(),
                      durationSeconds=round(time.time() - started, 1))
        if record["backupStatus"] == "running":
            record["backupStatus"] = "failed"
        step("aborted-before-change", error=str(exc))
        append_jsonl(UPDATE_LOG, record)
        release_lock()
        return record

    # Ab hier wird die Installation veraendert.
    try:
        if simulate_failure:
            step("simulated-failure", info="Kein Image-Wechsel; Rollback-Pfad wird getestet")
            raise N8nCtlError("Simulierter Fehler nach dem Backup (Test des Rollbacks)")
        step("pull", image=f"{N8N_IMAGE_REPO}:{version}")
        run(["docker", "pull", f"{N8N_IMAGE_REPO}:{version}"], timeout=1800)
        step("switch-version")
        set_env_value("N8N_VERSION", version)
        # --no-deps: PostgreSQL bleibt unangetastet.
        compose("up", "-d", "--no-deps", "n8n")
        step("healthcheck")
        report = wait_healthy(version)
        record["health"] = report
        if not report["ok"]:
            failed = [k for k, v in report["checks"].items() if not v["ok"]]
            raise N8nCtlError(f"Healthchecks fehlgeschlagen: {failed}")
        record.update(status="success", versionAfter=running_n8n_version())
        step("success")
    except Exception as exc:
        record["error"] = str(exc)
        step("failed", error=str(exc))
        record["rollback"] = rollback(Path(record["backup"]), step)
        record["status"] = "rolled-back" if record["rollback"]["ok"] else "rollback-failed"
        record["versionAfter"] = running_n8n_version()
    finally:
        record["finishedAt"] = now_iso()
        record["durationSeconds"] = round(time.time() - started, 1)
        append_jsonl(UPDATE_LOG, record)
        release_lock()
    return record


def rollback(backup_dir: Path, step) -> dict:
    """Konsistenter Rollback: altes Image + zugehoeriger DB-/Datenstand.

    Ein reines Zurueckwechseln des Images reicht nicht, da die neue Version
    bereits Datenbankmigrationen ausgefuehrt haben kann. Deshalb werden
    Datenbank und n8n-Volumes aus dem Pre-Update-Backup wiederhergestellt.
    """
    step("rollback-start", backup=str(backup_dir))
    try:
        compose("stop", "-t", "30", "n8n", check=False)
        result = restore(backup_dir, safety_backup=False)
        step("rollback-success", version=result["version"])
        return {"ok": True, "restoredVersion": result["version"], "health": result["health"]}
    except Exception as exc:
        step("rollback-failed", error=str(exc))
        return {"ok": False, "error": str(exc)}


# --------------------------------------------------------------------------- #
# HTTP-Schnittstelle fuer den n8n-Workflow
# --------------------------------------------------------------------------- #
ALLOWED_UPDATE_KEYS = {"version", "dryRun", "requestedBy", "executionId"}
ALLOWED_LOG_KEYS = {"checkedAt", "installedVersion", "availableVersion", "decision",
                    "reason", "executionId", "releaseUrl", "updateRequested", "error",
                    "targetVersion", "lastUpdateStatus", "trigger"}
SAFE_TEXT_RE = re.compile(r"^[\w .,:;/@()+#=?&%-]{0,300}$", re.UNICODE)
_spawn_lock = threading.Lock()


class UpdaterHandler(BaseHTTPRequestHandler):
    server_version = "n8n-local-updater/1.0"
    sys_version = ""
    token: bytes = b""

    def log_message(self, fmt, *args):  # in eigene Logdatei
        log(f"http {self.client_address[0]} {fmt % args}")

    def _send(self, code: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        ok = header.startswith("Bearer ") and hmac.compare_digest(header[7:].encode(), self.token)
        if not ok:
            log(f"Abgelehnte Anfrage ohne gueltigen Token von {self.client_address[0]} auf {self.path}")
            time.sleep(1)  # bremst Raten
        return ok

    def _json_body(self, allowed: set[str]) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 4096:
            raise ValueError("Body fehlt oder ist zu gross")
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ValueError("Content-Type muss application/json sein")
        body = json.loads(self.rfile.read(length))
        if not isinstance(body, dict):
            raise ValueError("JSON-Objekt erwartet")
        unknown = set(body) - allowed
        if unknown:
            raise ValueError(f"Unbekannte Felder: {sorted(unknown)}")
        return body

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "service": "n8n-local-updater"})
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/status":
            return self._send(200, status())
        if self.path == "/check":
            try:
                return self._send(200, check_latest())
            except Exception as exc:
                return self._send(502, {"error": str(exc)})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/update":
            return self._update()
        if self.path == "/check-log":
            return self._check_log()
        return self._send(404, {"error": "not found"})

    def _check_log(self):
        try:
            body = self._json_body(ALLOWED_LOG_KEYS)
            record = {}
            for key, val in body.items():
                if isinstance(val, bool) or val is None:
                    record[key] = val
                elif isinstance(val, (str, int, float)) and SAFE_TEXT_RE.match(str(val)):
                    record[key] = str(val)
                else:
                    raise ValueError(f"Ungueltiger Wert fuer {key}")
        except Exception as exc:
            return self._send(400, {"error": str(exc)})
        record["receivedAt"] = now_iso()
        append_jsonl(CHECK_LOG, record)
        return self._send(200, {"logged": True})

    def _update(self):
        try:
            body = self._json_body(ALLOWED_UPDATE_KEYS)
            version = str(body.get("version", ""))
            semver(version)
            dry_run = body.get("dryRun", False) is True
            requested_by = str(body.get("requestedBy", "n8n"))[:64]
            if not re.match(r"^[\w .-]{1,64}$", requested_by):
                raise ValueError("requestedBy ungueltig")
            execution_id = str(body.get("executionId", ""))[:32]
            if execution_id and not re.match(r"^[\w-]+$", execution_id):
                raise ValueError("executionId ungueltig")
        except Exception as exc:
            return self._send(400, {"error": str(exc)})

        with _spawn_lock:
            try:
                pf = preflight(version)
            except Exception as exc:
                return self._send(502, {"error": f"Vorabpruefung nicht moeglich: {exc}"})
            if dry_run:
                log(f"Dry-Run fuer {version}: ok={pf['ok']} failed={pf['failed']}")
                return self._send(200, {"dryRun": True, **pf})
            if not pf["ok"]:
                code = 409 if not pf["checks"]["noUpdateRunning"] else 422
                log(f"Update auf {version} abgelehnt: {pf['failed']}")
                return self._send(code, {"accepted": False, **pf})
            request_id = uuid.uuid4().hex[:12]
            try:
                acquire_lock(version, request_id)
            except N8nCtlError as exc:
                return self._send(409, {"accepted": False, "error": str(exc)})
            try:
                spawn_update(version, request_id, requested_by, execution_id)
            except Exception as exc:
                release_lock()
                return self._send(500, {"accepted": False, "error": f"Start fehlgeschlagen: {exc}"})
        log(f"Update {request_id} auf {version} angenommen (angefordert von {requested_by}, Ausfuehrung {execution_id})")
        return self._send(202, {"accepted": True, "requestId": request_id, "targetVersion": version,
                                "installedVersion": pf["installedVersion"],
                                "startsInSeconds": 20,
                                "note": "Update laeuft als separater Host-Prozess; Ergebnis in logs/updates.jsonl"})


def spawn_update(version: str, request_id: str, requested_by: str, execution_id: str) -> None:
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    interpreter = str(pyw if pyw.exists() else exe)
    args = [interpreter, str(Path(__file__).resolve()), "update", version, "--yes",
            "--lock-held", "--delay", "20", "--request-id", request_id,
            "--requested-by", f"{requested_by}:{execution_id}" if execution_id else requested_by]
    flags = 0
    if os.name == "nt":
        flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                 | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0))
    LOG_DIR.mkdir(exist_ok=True)
    out_file = (LOG_DIR / f"update-{request_id}.out").open("ab")
    try:
        subprocess.Popen(args, cwd=PROJECT_ROOT, stdout=out_file, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    except OSError:
        # Breakaway nicht erlaubt -> ohne Breakaway starten
        flags &= ~getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
        subprocess.Popen(args, cwd=PROJECT_ROOT, stdout=out_file, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)


def serve() -> None:
    env = read_env()
    token = env.get("UPDATER_TOKEN", "")
    if len(token) < 32 or token.startswith("GENERATE"):
        raise N8nCtlError("UPDATER_TOKEN fehlt oder ist zu kurz (min. 32 Zeichen)")
    host = env.get("UPDATER_HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "::1"):
        raise N8nCtlError("Der Updater darf nur an Loopback (127.0.0.1) gebunden werden")
    port = int(env.get("UPDATER_PORT", "5679"))
    UpdaterHandler.token = token.encode()
    httpd = ThreadingHTTPServer((host, port), UpdaterHandler)
    httpd.daemon_threads = True
    log(f"Host-Updater lauscht auf http://{host}:{port}")
    httpd.serve_forever()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="n8nctl", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("health")
    sub.add_parser("check")
    sub.add_parser("prune")
    sub.add_parser("serve")
    b = sub.add_parser("backup")
    b.add_argument("--reason", default="manual")
    b.add_argument("--online", action="store_true", help="n8n waehrend des Backups nicht stoppen")
    v = sub.add_parser("verify")
    v.add_argument("directory")
    r = sub.add_parser("restore")
    r.add_argument("directory")
    r.add_argument("--yes", action="store_true")
    r.add_argument("--restore-env", action="store_true")
    r.add_argument("--no-safety-backup", action="store_true")
    pf = sub.add_parser("preflight")
    pf.add_argument("version")
    pf.add_argument("--allow-major", action="store_true")
    u = sub.add_parser("update")
    u.add_argument("version")
    u.add_argument("--yes", action="store_true")
    u.add_argument("--allow-major", action="store_true")
    u.add_argument("--delay", type=int, default=0)
    u.add_argument("--lock-held", action="store_true", help=argparse.SUPPRESS)
    u.add_argument("--request-id", help=argparse.SUPPRESS)
    u.add_argument("--requested-by", default="cli", help=argparse.SUPPRESS)
    u.add_argument("--simulate-failure", action="store_true",
                   help="Test: nach dem Backup Fehler ausloesen und Rollback ausfuehren")
    a = p.parse_args(argv)

    try:
        if a.cmd == "status":
            result = status()
        elif a.cmd == "health":
            result = health_report()
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["ok"] else 1
        elif a.cmd == "check":
            result = check_latest()
        elif a.cmd == "prune":
            result = {"removed": prune()}
        elif a.cmd == "serve":
            serve()
            return 0
        elif a.cmd == "backup":
            result = {"backup": str(backup(a.reason, stop_n8n=not a.online)), "verified": True}
        elif a.cmd == "verify":
            m = verify(Path(a.directory))
            result = {"verified": True, "createdAt": m["createdAt"], "n8nVersion": m["n8nVersion"]}
        elif a.cmd == "restore":
            if not a.yes:
                ans = input(f"Datenbank und n8n-Daten durch {a.directory} ersetzen? [ja/NEIN] ")
                if ans.strip().lower() != "ja":
                    print("Abgebrochen.")
                    return 1
            result = restore(Path(a.directory), restore_env=a.restore_env,
                             safety_backup=not a.no_safety_backup)
        elif a.cmd == "preflight":
            result = preflight(a.version, a.allow_major)
        elif a.cmd == "update":
            if not a.yes:
                ans = input(f"n8n auf {a.version} aktualisieren? [ja/NEIN] ")
                if ans.strip().lower() != "ja":
                    print("Abgebrochen.")
                    return 1
            result = update(a.version, request_id=a.request_id, delay=a.delay, lock_held=a.lock_held,
                            allow_major=a.allow_major, simulate_failure=a.simulate_failure,
                            requested_by=a.requested_by)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["status"] == "success" else 2
        else:
            return 2
    except (N8nCtlError, ValueError) as exc:
        log(f"FEHLER ({a.cmd}): {exc}")
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
