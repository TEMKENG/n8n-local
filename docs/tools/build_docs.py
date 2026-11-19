#!/usr/bin/env python3
"""
Erzeugt die HTML-Dokumentation aus den Markdown-Quellen in docs/.

    python3 docs/tools/build_docs.py          # HTML neu erzeugen
    python3 docs/tools/build_docs.py --check  # nur pruefen (Exit 1 bei Abweichung)

Markdown ist die einzige Quelle. Die HTML-Dateien werden vollstaendig daraus
generiert, damit beide Formate inhaltlich identisch bleiben. Mermaid-Bloecke mit
"%% svg: <name>" werden im HTML durch die eingebetteten SVG-Diagramme aus
diagrams.py ersetzt. Die Pruefung umfasst:
  * HTML entspricht exakt der aktuellen Generierung aus Markdown
  * alle relativen Links und Anker zwischen den Dokumenten existieren
  * jeder Mermaid-Block hat ein zugehoeriges SVG-Diagramm
Benoetigt: markdown-it-py  (pip install markdown-it-py)
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from html import escape
from pathlib import Path

try:
    from markdown_it import MarkdownIt
except ImportError:  # pragma: no cover
    sys.exit("markdown-it-py fehlt: pip install markdown-it-py")

sys.path.insert(0, str(Path(__file__).parent))
from diagrams import DIAGRAMS  # noqa: E402

DOCS = Path(__file__).resolve().parent.parent
PAGES = [
    ("installation-guide", "Installationsanleitung", "Neuinstallation Schritt für Schritt"),
    ("architecture", "Architektur", "Aufbau, Updater, Sicherheit"),
    ("maintenance", "Wartung & Administration", "Betrieb, Backup, Restore, Updates"),
]


def slugify(text: str) -> str:
    """GitHub-kompatible Anker (gleich wie in VS Code / GitHub-Vorschau)."""
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def plain(inline_token) -> str:
    return "".join(c.content for c in (inline_token.children or []) if c.type in ("text", "code_inline"))


def render_markdown(source: str) -> tuple[str, list[tuple[int, str, str]], str, list[str]]:
    md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False}).enable("table")
    tokens = md.parse(source)
    toc: list[tuple[int, str, str]] = []
    used: dict[str, int] = {}
    title = ""
    mermaid_names: list[str] = []

    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            text = plain(tokens[i + 1])
            slug = slugify(text)
            if slug in used:
                used[slug] += 1
                slug = f"{slug}-{used[slug]}"
            else:
                used[slug] = 0
            tok.attrSet("id", slug)
            level = int(tok.tag[1])
            if level == 1:
                title = text
            elif level in (2, 3):
                toc.append((level, text, slug))
        if tok.type == "link_open":
            href = tok.attrGet("href") or ""
            m = re.match(r"^([\w-]+)\.md(#.*)?$", href)
            if m:
                tok.attrSet("href", f"{m.group(1)}.html{m.group(2) or ''}")
            elif href.startswith("http"):
                tok.attrSet("rel", "noopener")

    default_fence = md.renderer.rules.get("fence")

    def fence(tokens_, idx, options, env):
        tok = tokens_[idx]
        lang = (tok.info or "").strip().split()[0] if tok.info else ""
        if lang == "mermaid":
            m = re.search(r"%%\s*svg:\s*([\w-]+)", tok.content)
            if not m or m.group(1) not in DIAGRAMS:
                raise SystemExit(f"Mermaid-Block ohne passendes SVG: {tok.content[:60]!r}")
            name = m.group(1)
            mermaid_names.append(name)
            caption, func = DIAGRAMS[name]
            return (f'<figure class="diagram" id="diagramm-{name}">{func()}'
                    f'<figcaption>Abbildung: {escape(caption)}</figcaption></figure>\n')
        label = {"powershell": "PowerShell", "yaml": "YAML", "text": "Text", "json": "JSON"}.get(lang, lang or "Code")
        code = escape(tok.content)
        return (f'<div class="code"><div class="code-head"><span>{label}</span>'
                f'<button type="button" class="copy" aria-label="Code kopieren">Kopieren</button></div>'
                f'<pre><code class="lang-{escape(lang)}">{code}</code></pre></div>\n')

    md.renderer.rules["fence"] = fence

    def blockquote_open(tokens_, idx, options, env):
        # Hinweis-/Warnboxen anhand des ersten fetten Wortes
        kind = "note"
        for t in tokens_[idx + 1: idx + 4]:
            if t.type == "inline":
                txt = t.content.lower()
                if txt.startswith("**warnung"):
                    kind = "warn"
                elif txt.startswith("**hinweis"):
                    kind = "info"
                break
        return f'<aside class="callout {kind}" role="note">\n'

    md.renderer.rules["blockquote_open"] = blockquote_open
    md.renderer.rules["blockquote_close"] = lambda *a: "</aside>\n"

    def table_open(tokens_, idx, options, env):
        return '<div class="table-wrap"><table>\n'

    md.renderer.rules["table_open"] = table_open
    md.renderer.rules["table_close"] = lambda *a: "</table></div>\n"

    html = md.renderer.render(tokens, md.options, {})
    # Erste H1 kommt in den Seitenkopf
    html = re.sub(r"^<h1[^>]*>.*?</h1>\n", "", html, count=1, flags=re.S)
    return html, toc, title, mermaid_names


CSS = r"""
:root{
  --bg:#f7f8fa;--surface:#ffffff;--text:#1d2330;--muted:#556070;--border:#dfe3ea;
  --accent:#2a5bd7;--accent-soft:#e9f0ff;--code-bg:#0f172a;--code-text:#e2e8f0;--code-head:#1e293b;
  --inline-code:#eef1f6;--warn-bg:#fff5f2;--warn:#c2410c;--info-bg:#eef6ff;--info:#1d4ed8;
  --row:#f9fafc;
  --d-box:#ffffff;--d-stroke:#5b6b7f;--d-stroke-soft:#b3bdca;--d-region:#f3f5f8;--d-text:#1f2937;--d-muted:#4b5563;
  --d-line:#475569;--d-halo:#f3f5f8;--d-acc:#2a5bd7;--d-acc-bg:#e9f0ff;--d-ok:#15803d;--d-ok-bg:#e7f7ee;
  --d-bad:#b91c1c;--d-bad-bg:#fdecec;--d-net:#edf7f1;--d-net-stroke:#6aa287;--d-int:#f5effa;--d-int-stroke:#9a76b5;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0e1117;--surface:#161b22;--text:#e6e9ef;--muted:#9aa4b2;--border:#2a313c;
  --accent:#7aa2ff;--accent-soft:#1b2640;--code-bg:#0b0f16;--code-head:#141a24;--inline-code:#222a36;
  --warn-bg:#2a1a14;--warn:#fb923c;--info-bg:#132033;--info:#7aa2ff;--row:#1a2029;
  --d-box:#1c232d;--d-stroke:#8b98a9;--d-stroke-soft:#3b4552;--d-region:#141a22;--d-text:#e6e9ef;--d-muted:#a6b0bd;
  --d-line:#9aa6b6;--d-halo:#141a22;--d-acc:#7aa2ff;--d-acc-bg:#1b2640;--d-ok:#4ade80;--d-ok-bg:#12291c;
  --d-bad:#f87171;--d-bad-bg:#2d1618;--d-net:#13211a;--d-net-stroke:#4f8a6d;--d-int:#1f1828;--d-int-stroke:#8e6fab;
}}
:root[data-theme="dark"]{
  --bg:#0e1117;--surface:#161b22;--text:#e6e9ef;--muted:#9aa4b2;--border:#2a313c;
  --accent:#7aa2ff;--accent-soft:#1b2640;--code-bg:#0b0f16;--code-head:#141a24;--inline-code:#222a36;
  --warn-bg:#2a1a14;--warn:#fb923c;--info-bg:#132033;--info:#7aa2ff;--row:#1a2029;
  --d-box:#1c232d;--d-stroke:#8b98a9;--d-stroke-soft:#3b4552;--d-region:#141a22;--d-text:#e6e9ef;--d-muted:#a6b0bd;
  --d-line:#9aa6b6;--d-halo:#141a22;--d-acc:#7aa2ff;--d-acc-bg:#1b2640;--d-ok:#4ade80;--d-ok-bg:#12291c;
  --d-bad:#f87171;--d-bad-bg:#2d1618;--d-net:#13211a;--d-net-stroke:#4f8a6d;--d-int:#1f1828;--d-int-stroke:#8e6fab;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:16px}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.65 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--accent);text-underline-offset:2px}
.layout{display:grid;grid-template-columns:290px minmax(0,1fr);max-width:1400px;margin:0 auto}
.sidebar{position:sticky;top:0;height:100vh;overflow-y:auto;padding:28px 20px 40px;border-right:1px solid var(--border);background:var(--surface)}
.brand{font-weight:700;font-size:15px;letter-spacing:.01em;margin:0 0 4px}
.brand-sub{color:var(--muted);font-size:13px;margin:0 0 22px}
.nav-docs{list-style:none;margin:0 0 26px;padding:0;display:grid;gap:4px}
.nav-docs a{display:block;padding:8px 10px;border-radius:8px;text-decoration:none;color:var(--text)}
.nav-docs a small{display:block;color:var(--muted);font-size:12.5px}
.nav-docs a:hover{background:var(--row)}
.nav-docs a[aria-current="page"]{background:var(--accent-soft);color:var(--accent);font-weight:600}
.toc-title{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 8px;font-weight:600}
.toc{list-style:none;margin:0;padding:0;font-size:14px}
.toc li{margin:0}
.toc a{display:block;padding:3px 0 3px 10px;border-left:2px solid transparent;color:var(--muted);text-decoration:none}
.toc a:hover,.toc a.active{color:var(--text);border-left-color:var(--accent)}
.toc .l3 a{padding-left:24px;font-size:13px}
main{padding:40px 56px 80px;min-width:0}
.page-head{border-bottom:1px solid var(--border);margin-bottom:28px;padding-bottom:20px}
.eyebrow{color:var(--accent);font-weight:600;font-size:13px;letter-spacing:.06em;text-transform:uppercase;margin:0 0 6px}
h1{font-size:2.1rem;line-height:1.2;margin:0 0 8px;text-wrap:balance}
.meta{color:var(--muted);font-size:14px;margin:0}
h2{font-size:1.5rem;line-height:1.3;margin:2.6em 0 .7em;padding-top:.4em;border-top:1px solid var(--border)}
h2:first-of-type{border-top:0;margin-top:1.2em}
h3{font-size:1.15rem;margin:2em 0 .6em}
h2,h3{scroll-margin-top:16px}
p,ul,ol{margin:0 0 1em}
li{margin:.25em 0}
ol>li::marker{font-weight:600;color:var(--accent)}
code{font:0.88em/1.5 ui-monospace,"Cascadia Code",Consolas,monospace;background:var(--inline-code);padding:.12em .38em;border-radius:5px;overflow-wrap:anywhere}
.code{margin:0 0 1.2em;border-radius:10px;overflow:hidden;background:var(--code-bg);border:1px solid var(--border)}
.code-head{display:flex;justify-content:space-between;align-items:center;padding:6px 12px;background:var(--code-head);color:#94a3b8;font-size:12px;font-weight:600;letter-spacing:.04em}
.copy{background:transparent;border:1px solid #334155;color:#cbd5e1;border-radius:6px;font:inherit;padding:2px 10px;cursor:pointer}
.copy:hover{border-color:#64748b}
pre{margin:0;padding:14px 16px;overflow-x:auto}
pre code{background:none;padding:0;color:var(--code-text);font-size:13.5px;line-height:1.6;white-space:pre;overflow-wrap:normal}
.table-wrap{overflow-x:auto;margin:0 0 1.3em;border:1px solid var(--border);border-radius:10px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:14.5px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:top}
th{background:var(--row);font-weight:600;white-space:nowrap}
tr:last-child td{border-bottom:0}
td code{white-space:nowrap}
.callout{margin:0 0 1.3em;padding:12px 16px 2px;border-radius:10px;border-left:4px solid var(--info);background:var(--info-bg)}
.callout.warn{border-left-color:var(--warn);background:var(--warn-bg)}
.callout.warn strong:first-child{color:var(--warn)}
.callout.info strong:first-child{color:var(--info)}
.diagram{margin:1.2em 0 1.8em;padding:14px;border:1px solid var(--border);border-radius:12px;background:var(--d-region)}
.diagram-svg{display:block;width:100%;height:auto}
.diagram figcaption{color:var(--muted);font-size:13px;text-align:center;margin-top:8px}
.foot{margin-top:56px;padding-top:16px;border-top:1px solid var(--border);color:var(--muted);font-size:13px}
.pager{display:flex;justify-content:space-between;gap:12px;margin-top:48px}
.pager a{flex:1;border:1px solid var(--border);border-radius:10px;padding:12px 16px;text-decoration:none;background:var(--surface)}
.pager a small{display:block;color:var(--muted)}
.pager .next{text-align:right}
.theme-toggle{margin-top:24px;background:var(--row);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:6px 10px;font:inherit;font-size:13px;cursor:pointer}
.menu-btn{display:none}
@media (max-width:960px){
  .layout{display:block}
  .sidebar{position:static;height:auto;border-right:0;border-bottom:1px solid var(--border);padding:16px}
  .sidebar .toc-block{display:none}
  .sidebar.open .toc-block{display:block}
  .menu-btn{display:inline-block;margin:0 0 8px;background:var(--row);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:6px 12px;font:inherit;font-size:14px}
  main{padding:24px 16px 60px}
  h1{font-size:1.7rem}
  .pager{flex-direction:column}
}
@media print{
  body{background:#fff;color:#000;font-size:11pt}
  .sidebar,.copy,.pager,.theme-toggle,.menu-btn{display:none!important}
  .layout{display:block}
  main{padding:0}
  a{color:#000}
  .code{border:1px solid #999;background:#fff}
  .code-head{background:#eee;color:#333}
  pre code{color:#000;white-space:pre-wrap}
  .table-wrap{overflow:visible;border-color:#999}
  h2{break-after:avoid;border-top-color:#999}
  .diagram,table,.callout,.code{break-inside:avoid}
  .diagram{background:#fff}
}
"""

JS = r"""
(function(){
  var root=document.documentElement,key='n8n-docs-theme';
  try{var t=localStorage.getItem(key);if(t)root.setAttribute('data-theme',t);}catch(e){}
  document.addEventListener('click',function(ev){
    var b=ev.target.closest('.copy');
    if(b){var code=b.closest('.code').querySelector('code').innerText;
      (navigator.clipboard?navigator.clipboard.writeText(code):Promise.reject()).then(function(){b.textContent='Kopiert';setTimeout(function(){b.textContent='Kopieren'},1500)},function(){b.textContent='Markieren + Strg+C'});}
    if(ev.target.closest('.theme-toggle')){
      var dark=root.getAttribute('data-theme')==='dark'||(!root.getAttribute('data-theme')&&matchMedia('(prefers-color-scheme: dark)').matches);
      var next=dark?'light':'dark';root.setAttribute('data-theme',next);try{localStorage.setItem(key,next);}catch(e){}
    }
    if(ev.target.closest('.menu-btn')){document.querySelector('.sidebar').classList.toggle('open');}
  });
  var links=[].slice.call(document.querySelectorAll('.toc a'));
  if('IntersectionObserver' in window&&links.length){
    var map={};links.forEach(function(a){map[a.getAttribute('href').slice(1)]=a;});
    var obs=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){links.forEach(function(l){l.classList.remove('active')});var a=map[e.target.id];if(a)a.classList.add('active');}});},{rootMargin:'0px 0px -75% 0px'});
    document.querySelectorAll('main h2[id],main h3[id]').forEach(function(h){obs.observe(h);});
  }
})();
"""


def build_page(slug: str) -> tuple[str, dict]:
    src_path = DOCS / f"{slug}.md"
    source = src_path.read_text(encoding="utf-8-sig")
    body, toc, title, mermaids = render_markdown(source)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    idx = [p[0] for p in PAGES].index(slug)
    page_title, page_sub = PAGES[idx][1], PAGES[idx][2]

    nav = "".join(
        f'<li><a href="{s}.html"{" aria-current=\"page\"" if s == slug else ""}>{escape(t)}<small>{escape(d)}</small></a></li>'
        for s, t, d in PAGES)
    toc_html = "".join(f'<li class="l{lvl}"><a href="#{a}">{escape(t)}</a></li>' for lvl, t, a in toc)
    prev_link = next_link = ""
    if idx > 0:
        s, t, _ = PAGES[idx - 1]
        prev_link = f'<a class="prev" href="{s}.html"><small>← Zurück</small>{escape(t)}</a>'
    if idx < len(PAGES) - 1:
        s, t, _ = PAGES[idx + 1]
        next_link = f'<a class="next" href="{s}.html"><small>Weiter →</small>{escape(t)}</a>'

    html = f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="docs/tools/build_docs.py">
<meta name="source" content="{slug}.md sha256:{digest}">
<title>{escape(page_title)} · n8n-local</title>
<style>{CSS}</style>
</head>
<body>
<div class="layout">
<nav class="sidebar" aria-label="Navigation">
  <p class="brand">n8n-local</p>
  <p class="brand-sub">Lokale n8n-Installation mit PostgreSQL</p>
  <button type="button" class="menu-btn" aria-label="Inhaltsverzeichnis ein-/ausblenden">Inhalt ☰</button>
  <ul class="nav-docs">{nav}</ul>
  <div class="toc-block">
    <p class="toc-title">Auf dieser Seite</p>
    <ul class="toc">{toc_html}</ul>
    <button type="button" class="theme-toggle">Hell / Dunkel</button>
  </div>
</nav>
<main id="inhalt">
<header class="page-head">
  <p class="eyebrow">n8n-local Dokumentation</p>
  <h1>{escape(title)}</h1>
  <p class="meta">Quelle: <code>docs/{slug}.md</code> · generiert mit <code>docs/tools/build_docs.py</code></p>
</header>
{body}
<div class="pager">{prev_link}{next_link}</div>
<footer class="foot">Generiert aus <code>{slug}.md</code> (SHA-256 {digest}). Nicht von Hand bearbeiten – Änderungen in der Markdown-Datei vornehmen und den Generator ausführen.</footer>
</main>
</div>
<script>{JS}</script>
</body>
</html>
"""
    info = {"anchors": {a for _, _, a in toc} | set(re.findall(r'id="([^"]+)"', body)),
            "links": re.findall(r'href="([^"#:]+\.html)(#[^"]*)?"', body), "mermaid": mermaids,
            "mermaid_src": len(re.findall(r"```mermaid", source))}
    return html, info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="nur pruefen, nichts schreiben")
    args = ap.parse_args()
    results = {slug: build_page(slug) for slug, _, _ in PAGES}
    problems = []
    for slug, (html, info) in results.items():
        if info["mermaid_src"] != len(info["mermaid"]):
            problems.append(f"{slug}: Mermaid-Bloecke ohne SVG")
        for target, anchor in info["links"]:
            tslug = target[:-5]
            if tslug not in results:
                problems.append(f"{slug}: Link auf unbekanntes Dokument {target}")
            elif anchor and anchor[1:] not in results[tslug][1]["anchors"]:
                problems.append(f"{slug}: Anker {target}{anchor} existiert nicht")
        out = DOCS / f"{slug}.html"
        if args.check:
            if not out.exists() or out.read_text(encoding="utf-8") != html:
                problems.append(f"{slug}.html ist nicht aktuell (Generator ausfuehren)")
        else:
            out.write_text(html, encoding="utf-8", newline="\n")
            print(f"geschrieben: {out.name} ({len(html) // 1024} KB, {len(info['mermaid'])} Diagramme)")
    if not args.check:
        diag_dir = DOCS / "diagrams"
        diag_dir.mkdir(exist_ok=True)
        for name, (_, func) in DIAGRAMS.items():
            (diag_dir / f"{name}.svg").write_text(func(), encoding="utf-8", newline="\n")
    for p in problems:
        print("FEHLER:", p)
    if args.check and not problems:
        print("OK: Markdown und HTML sind konsistent, alle Links und Diagramme vorhanden.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
