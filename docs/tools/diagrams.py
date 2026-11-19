"""Erzeugt die SVG-Diagramme der HTML-Dokumentation.

Jedes Diagramm entspricht inhaltlich einem Mermaid-Block in den Markdown-Dateien
(Kennzeichnung "%% svg: <name>"). Farben kommen aus CSS-Variablen der HTML-Seite,
mit Fallbacks, damit die SVG-Dateien auch eigenstaendig lesbar sind.
"""
from __future__ import annotations

from html import escape

STYLE = """
<style>
.bx{fill:var(--d-box,#fff);stroke:var(--d-stroke,#5b6b7f);stroke-width:1.4}
.bx.acc{fill:var(--d-acc-bg,#e8f1ff);stroke:var(--d-acc,#2563eb);stroke-width:1.8}
.bx.ok{fill:var(--d-ok-bg,#e7f7ee);stroke:var(--d-ok,#15803d)}
.bx.bad{fill:var(--d-bad-bg,#fdecec);stroke:var(--d-bad,#b91c1c)}
.bx.dash{stroke-dasharray:5 4}
.rg{fill:var(--d-region,#f4f6f9);stroke:var(--d-stroke-soft,#a9b4c2);stroke-width:1.2}
.rg.net{fill:var(--d-net,#eef6f1);stroke:var(--d-net-stroke,#6aa287);stroke-dasharray:6 4}
.rg.int{fill:var(--d-int,#f6effa);stroke:var(--d-int-stroke,#9a76b5);stroke-dasharray:6 4}
.t{fill:var(--d-text,#1f2937);font:600 14px system-ui,-apple-system,"Segoe UI",sans-serif}
.s{fill:var(--d-muted,#4b5563);font:12.5px system-ui,-apple-system,"Segoe UI",sans-serif}
.rt{fill:var(--d-muted,#4b5563);font:600 12.5px system-ui,-apple-system,"Segoe UI",sans-serif;letter-spacing:.02em}
.lb{fill:var(--d-text,#1f2937);font:12px system-ui,-apple-system,"Segoe UI",sans-serif;paint-order:stroke;stroke:var(--d-halo,#fff);stroke-width:4px;stroke-linejoin:round}
.ln{fill:none;stroke:var(--d-line,#475569);stroke-width:1.6}
.ln.dash{stroke-dasharray:6 4}
.ln.bad{stroke:var(--d-bad,#b91c1c)}
.ah{fill:var(--d-line,#475569)}
.ahb{fill:var(--d-bad,#b91c1c)}
</style>"""


class Svg:
    def __init__(self, w: int, h: int, title: str, desc: str):
        self.w, self.h, self.title, self.desc = w, h, title, desc
        self.parts: list[str] = []

    # -- Grundformen ------------------------------------------------------
    def region(self, x, y, w, h, label, kind="", label_pos="top"):
        self.parts.append(f'<rect class="rg {kind}" x="{x}" y="{y}" width="{w}" height="{h}" rx="12"/>')
        ly = y + 20 if label_pos == "top" else y + h - 10
        self.parts.append(f'<text class="rt" x="{x + 14}" y="{ly}">{escape(label)}</text>')

    def box(self, x, y, w, h, lines, kind="", rx=8):
        self.parts.append(f'<rect class="bx {kind}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>')
        self._lines(x + w / 2, y + h / 2, lines)

    def cyl(self, x, y, w, h, lines, kind=""):
        e = 7
        self.parts.append(
            f'<path class="bx {kind}" d="M{x},{y + e} a{w / 2},{e} 0 0,1 {w},0 v{h - 2 * e} '
            f'a{w / 2},{e} 0 0,1 {-w},0 z"/>'
            f'<path class="bx {kind}" style="fill:none" d="M{x},{y + e} a{w / 2},{e} 0 0,0 {w},0"/>')
        self._lines(x + w / 2, y + h / 2 + 3, lines)

    def diamond(self, cx, cy, w, h, lines, kind=""):
        self.parts.append(f'<polygon class="bx {kind}" points="{cx},{cy - h / 2} {cx + w / 2},{cy} '
                          f'{cx},{cy + h / 2} {cx - w / 2},{cy}"/>')
        self._lines(cx, cy, lines)

    def _lines(self, cx, cy, lines):
        if isinstance(lines, str):
            lines = [lines]
        n = len(lines)
        start = cy - (n - 1) * 9
        for i, text in enumerate(lines):
            cls = "t" if i == 0 else "s"
            self.parts.append(f'<text class="{cls}" x="{cx}" y="{start + i * 18 + 5}" '
                              f'text-anchor="middle">{escape(text)}</text>')

    def arrow(self, pts, label=None, lx=None, ly=None, kind="", anchor="middle", head=True):
        d = "M" + " L".join(f"{x},{y}" for x, y in pts)
        marker = ""
        if head:
            marker = ' marker-end="url(#ahb)"' if "bad" in kind else ' marker-end="url(#ah)"'
        self.parts.append(f'<path class="ln {kind}" d="{d}"{marker}/>')
        if label:
            if lx is None:
                (x1, y1), (x2, y2) = pts[0], pts[-1]
                lx, ly = (x1 + x2) / 2, (y1 + y2) / 2 - 6
            self.parts.append(f'<text class="lb" x="{lx}" y="{ly}" text-anchor="{anchor}">{escape(label)}</text>')

    def text(self, x, y, s, cls="s", anchor="start"):
        self.parts.append(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{escape(s)}</text>')

    def render(self, ident: str) -> str:
        defs = ('<defs>'
                '<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
                '<path class="ah" d="M0,0 L10,5 L0,10 z"/></marker>'
                '<marker id="ahb" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
                '<path class="ahb" d="M0,0 L10,5 L0,10 z"/></marker></defs>')
        # Marker-IDs pro Diagramm eindeutig machen (mehrere SVGs pro Seite)
        body = "".join(self.parts).replace("url(#ah)", f"url(#ah-{ident})").replace("url(#ahb)", f"url(#ahb-{ident})")
        defs = defs.replace('id="ah"', f'id="ah-{ident}"').replace('id="ahb"', f'id="ahb-{ident}"')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" role="img" '
                f'aria-labelledby="{ident}-t {ident}-d" class="diagram-svg">'
                f'<title id="{ident}-t">{escape(self.title)}</title><desc id="{ident}-d">{escape(self.desc)}</desc>'
                f'{STYLE}{defs}{body}</svg>')


def system_overview() -> str:
    s = Svg(960, 540, "Systemübersicht n8n-local",
            "Lokaler Windows-, Linux- oder macOS-Host mit Browser, optionalem Host-Updater und Projektordner; Docker Engine mit n8n und PostgreSQL in getrennten Netzen und drei Volumes.")
    s.box(430, 12, 200, 50, ["GitHub Releases API", "api.github.com"])
    s.region(20, 90, 300, 430, "LOKALER HOST")
    s.box(40, 135, 260, 48, ["Browser", "http://localhost:5678"])
    s.box(40, 215, 260, 64, ["Optionaler Host-Updater", "n8nctl.py · 127.0.0.1:5680"], "acc")
    s.box(40, 315, 200, 48, ["Docker CLI / Compose"])
    s.box(40, 400, 260, 64, ["Projektordner", ".env · backups/ · logs/"])
    s.region(360, 90, 580, 430, "DOCKER ENGINE")
    s.region(380, 128, 300, 134, "n8n-local_egress (Bridge)", "net", "bottom")
    s.box(430, 150, 200, 64, ["n8n 2.47.7", "Port 5678 · UID 1000"], "acc")
    s.region(380, 290, 300, 150, "n8n-local_backend (internal)", "int", "bottom")
    s.cyl(430, 316, 200, 70, ["PostgreSQL 17.12", "Port 5432"])
    s.cyl(720, 140, 200, 44, ["n8n_data"])
    s.cyl(720, 196, 200, 44, ["n8n_binary"])
    s.cyl(720, 330, 200, 44, ["postgres_data"])
    s.box(720, 455, 200, 44, ["volume-init (einmalig)"], "dash")
    s.text(390, 476, "n8n ist an beide Netze angeschlossen.", "s")
    s.arrow([(600, 150), (600, 64)], "HTTPS", 608, 80, anchor="start")
    s.arrow([(300, 159), (428, 170)], "localhost:5678", 364, 150)
    s.arrow([(430, 200), (302, 245)], "Bearer-Token", 366, 236)
    s.arrow([(140, 279), (140, 313)])
    s.arrow([(280, 279), (280, 398)], "schreibt", 286, 388, anchor="start")
    s.arrow([(240, 339), (358, 339)], "nur Projekt", 300, 330, "dash")
    s.arrow([(530, 214), (530, 314)], "5432 intern", 560, 270, anchor="start")
    s.arrow([(630, 170), (718, 162)], head=False)
    s.arrow([(630, 196), (718, 218)], head=False)
    s.arrow([(630, 351), (718, 352)], head=False)
    return s.render("sys")


def network() -> str:
    s = Svg(960, 410, "Netzwerkstruktur",
            "n8n hängt an egress und backend; PostgreSQL nur am internen backend-Netz ohne Internetzugang; Host-Ports nur auf 127.0.0.1.")
    s.region(20, 16, 920, 96, "WINDOWS-HOST · LOOPBACK 127.0.0.1")
    s.box(50, 50, 260, 46, ["127.0.0.1:5678", "veröffentlichter n8n-Port"])
    s.box(350, 50, 260, 46, ["127.0.0.1:5680", "Host-Updater"], "acc")
    s.box(650, 50, 270, 46, ["LAN / Internet → Host", "kein Zugriff (nur Loopback)"], "bad dash")
    s.region(20, 140, 450, 170, "n8n-local_egress · Bridge · 172.19.0.0/16", "net")
    s.region(490, 140, 450, 170, "n8n-local_backend · internal · 172.18.0.0/16", "int")
    s.box(385, 200, 190, 64, ["n8n", "in beiden Netzen"], "acc")
    s.cyl(715, 196, 180, 70, ["postgres", "5432"])
    s.box(80, 345, 270, 46, ["Internet", "api.github.com (HTTPS)"])
    s.arrow([(180, 96), (180, 126), (420, 126), (420, 198)], "Port-Weiterleitung", 300, 122)
    s.arrow([(540, 200), (540, 126), (490, 126), (490, 98)], "host.docker.internal", 550, 122, anchor="start")
    s.arrow([(575, 232), (713, 232)], "SQL", 644, 224)
    s.arrow([(410, 264), (300, 343)], "ausgehend", 330, 300)
    s.arrow([(805, 268), (805, 352)], kind="bad dash")
    s.text(820, 336, "kein Internet", "lb")
    s.text(820, 354, "(internal: true)", "s")
    return s.render("net")


def dataflow() -> str:
    s = Svg(960, 320, "Datenfluss", "Browser spricht mit n8n; n8n speichert in PostgreSQL und in den Volumes; Credentials verschlüsselt.")
    cols = [(120, "Browser"), (380, "n8n"), (640, "PostgreSQL"), (860, "n8n-Volumes")]
    for x, name in cols:
        s.box(x - 85, 14, 170, 42, [name], "acc" if name == "n8n" else "")
        s.arrow([(x, 56), (x, 300)], kind="dash", head=False)
    s.arrow([(120, 100), (378, 100)], "HTTP 127.0.0.1:5678 (Editor, REST)", 250, 92)
    s.arrow([(380, 150), (638, 150)], "Workflows, Credentials, Executions", 510, 142)
    s.arrow([(638, 180), (382, 180)], "Ergebnisse", 510, 196)
    s.arrow([(380, 230), (858, 230)], "Binärdaten, Konfiguration, Event-Log", 620, 222)
    s.box(300, 252, 420, 44, ["Credentials: AES-verschlüsselt mit N8N_ENCRYPTION_KEY", "vor dem Speichern in credentials_entity"], "ok")
    return s.render("flow")


def update_flow() -> str:
    s = Svg(960, 1000, "Automatisierter Update-Prozess",
            "Workflow-Schritte von Montag 03:00 bis zur Protokollierung und die vom Host-Updater ausgeführten Schritte Backup, Pull, Wechsel, Healthchecks, Rollback.")
    s.region(20, 4, 620, 884, "N8N-WORKFLOW · WEEKLY N8N VERSION CHECKER & AUTO UPDATER")
    X, W = 150, 300
    cx = X + W / 2
    s.box(X, 40, W, 46, ["Montag 03:00 (Europe/Berlin)", "Schedule Trigger · + manueller Test"], "acc", rx=23)
    s.box(X, 116, W, 50, ["Installierte Version ermitteln", "GET /status (Host-Updater)"])
    s.box(X, 196, W, 50, ["Stabile Releases abrufen", "GitHub API · n8n-io/n8n"])
    s.box(470, 196, 150, 50, ["Fehler", "aufbereiten"], "bad")
    s.box(X, 276, W, 50, ["Versionen vergleichen", "Semver · ohne Vorabversionen"])
    s.diamond(cx, 386, 230, 76, ["Neue Version", "gleiche Major?"])
    s.box(X, 456, W, 50, ["Vorabprüfung (Dry-Run)", "POST /update · dryRun"])
    s.diamond(cx, 566, 190, 70, ["bestanden?"])
    s.box(X, 636, W, 50, ["Update anfordern", "POST /update → 202 Accepted"], "acc")
    s.box(X, 726, W, 50, ["Protokolleintrag erstellen", "decision · reason · Versionen"])
    s.box(X, 812, W, 50, ["Ergebnis protokollieren", "POST /check-log → logs/"])
    for a, b in [(86, 114), (166, 194), (246, 274), (326, 346), (424, 454), (506, 529), (601, 634), (686, 724), (776, 810)]:
        s.arrow([(cx, a), (cx, b)])
    s.text(cx + 10, 446, "ja", "lb")
    s.text(cx + 10, 624, "ja", "lb")
    s.arrow([(X + W, 221), (468, 221)])
    s.arrow([(545, 246), (545, 837), (452, 837)])
    s.arrow([(cx - 115, 386), (60, 386), (60, 751), (X - 2, 751)], "nein", 96, 378)
    s.arrow([(cx - 95, 566), (90, 566), (90, 751)], "nein", 116, 558)
    # Host-Updater
    s.region(660, 396, 280, 596, "HOST-UPDATER · SEPARATER PROZESS")
    HX, HW = 680, 240
    hcx = HX + HW / 2
    s.box(HX, 456, HW, 50, ["Sperre setzen", "Vorabprüfung wiederholen"])
    s.box(HX, 530, HW, 50, ["Backup erstellen", "und verifizieren"])
    s.box(HX, 604, HW, 50, ["Image pullen", "docker.n8n.io/n8nio/n8n:x.y.z"])
    s.box(HX, 678, HW, 56, ["N8N_VERSION setzen", "compose up -d --no-deps n8n"])
    s.diamond(hcx, 800, 190, 70, ["Healthchecks", "6 Prüfungen"])
    s.box(672, 872, 122, 56, ["Version", "bestätigt"], "ok")
    s.box(808, 872, 122, 56, ["Rollback", "DB+Volumes"], "bad")
    s.box(808, 942, 122, 42, ["rolled-back"], "bad")
    for a, b in [(506, 528), (580, 602), (654, 676), (734, 763)]:
        s.arrow([(hcx, a), (hcx, b)])
    s.arrow([(hcx - 60, 818), (733, 870)], "ok", 712, 848)
    s.arrow([(hcx + 60, 818), (869, 870)], "Fehler", 900, 848)
    s.arrow([(869, 928), (869, 940)])
    s.arrow([(X + W, 661), (600, 661), (600, 481), (HX - 2, 481)], "20 s später", 600, 410 + 60, kind="dash")
    s.text(800, 442, "Abbruch ohne Änderung bei Backup-Fehler", "s", "middle")
    return s.render("upd")


def backup_rollback() -> str:
    s = Svg(960, 430, "Backup- und Rollback-Ablauf",
            "Backup in acht Schritten von der Speicherprüfung bis zur Aufbewahrung; Rollback stellt Datenbank, Volumes und Version gemeinsam wieder her.")
    s.region(10, 8, 940, 250, "BACKUP (scripts/backup.ps1 · automatisch vor jedem Update)")
    row1 = [["Speicherplatz", "prüfen"], ["n8n stoppen", "konsistenter Zeitpunkt"],
            ["pg_dump -Fc", "+ globals"], ["tar n8n_data", "+ n8n_binary"]]
    row2 = [[".env + compose", "+ manifest (SHA-256)"], ["Verifikation", "Hashes · pg_restore --list"],
            ["n8n starten", ".partial → final"], ["Aufbewahrung", "30 Tage · min. 5"]]
    xs = [30, 260, 490, 720]
    for i, lines in enumerate(row1):
        s.box(xs[i], 44, 205, 60, lines)
        if i:
            s.arrow([(xs[i - 1] + 205, 74), (xs[i] - 2, 74)])
    for i, lines in enumerate(row2):
        x = xs[3 - i]
        s.box(x, 170, 205, 60, lines, "ok" if i == 1 else "")
        if i:
            s.arrow([(xs[4 - i], 200), (x + 207, 200)])
    s.arrow([(822, 104), (822, 168)])
    s.region(10, 278, 940, 140, "ROLLBACK (bei fehlgeschlagenem Update)", "")
    steps = [["Update", "fehlgeschlagen"], ["n8n stoppen", ""], ["Restore aus", "Pre-Update-Backup"],
             ["Healthchecks", "alte Version"]]
    for i, lines in enumerate(steps):
        kind = "bad" if i == 0 else ("ok" if i == 3 else "")
        s.box(xs[i], 316, 205, 60, [l for l in lines if l], kind)
        if i:
            s.arrow([(xs[i - 1] + 205, 346), (xs[i] - 2, 346)])
    s.text(480, 404, "Restore = alte N8N_VERSION + Datenbank (drop/create + pg_restore) + beide n8n-Volumes", "s", "middle")
    return s.render("bak")


DIAGRAMS = {
    "system-overview": ("Systemübersicht", system_overview),
    "network": ("Netzwerkstruktur", network),
    "dataflow": ("Datenfluss", dataflow),
    "update-flow": ("Automatisierter Update-Prozess", update_flow),
    "backup-rollback": ("Backup- und Rollback-Ablauf", backup_rollback),
}
