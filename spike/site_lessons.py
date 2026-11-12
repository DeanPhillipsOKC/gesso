"""The lessons site: a small static site of finished lessons, so the owner and their partner can each open the
same lesson on a phone or tablet while painting (owner, 2026-11-11).

    add(lesson_folder, slug) -> site/lessons/<slug>/index.html + thumb.jpg, then rebuilds site/index.html

Each lesson is one self-contained HTML page (lesson-standalone.html: images inlined), so later animations and
interactive pieces work like on any web page. Deployed with Cloudflare Pages from the repo's site/ folder and kept
private with Cloudflare Access (docs/lessons-site.md). Nothing here names who can see it.
"""

from __future__ import annotations

import json
import shutil
from html import escape as e
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def add(lesson: Path, slug: str, site: Path = SITE) -> dict:
    data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
    page = lesson / "lesson-standalone.html"
    if not page.exists():
        raise FileNotFoundError(f"{page} is missing; run publish first")
    out = site / "lessons" / slug
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(page, out / "index.html")
    finish = lesson / data["stages"][-1]["image"]
    thumb = ImageOps.exif_transpose(Image.open(finish)).convert("RGB")
    thumb.thumbnail((640, 640))
    thumb.save(out / "thumb.jpg", quality=82, optimize=True)
    canvas = data.get("canvas") or {}
    entry = {
        "slug": slug,
        "title": data["photo_read"]["subject"].split(",")[0].split(" with ")[0][:80],
        "subject": data["photo_read"]["subject"],
        "steps": len(data["stages"]),
        "canvas": f'{canvas["w_in"]:g} x {canvas["h_in"]:g} in' if canvas else "",
        "tubes": len(data.get("tubes") or []),
        # the version that made it, not the one that last republished it
        "version": ((data.get("gesso") or {}).get("made") or data.get("gesso") or {}).get("version", ""),
        "published": ((data.get("gesso") or {}).get("made") or data.get("gesso") or {}).get("published", ""),
        "source": lesson.name,
    }
    manifest = site / "lessons.json"
    lessons = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    lessons = [x for x in lessons if x["slug"] != slug] + [entry]
    manifest.write_text(json.dumps(lessons, indent=2), encoding="utf-8")
    build_index(site, lessons)
    return {"url_path": f"/lessons/{slug}/", "lessons": len(lessons),
            "kb": round((out / "index.html").stat().st_size / 1024)}


INDEX_STYLE = """
:root{--bg:#fbfbf8;--card:#f1f2ef;--ink:#1d2430;--muted:#5b6474;--rule:#dcdfe3;--accent:#2944a8}
@media (prefers-color-scheme: dark){:root{--bg:#14171c;--card:#1c2027;--ink:#e7e9ee;--muted:#9aa3b2;--rule:#2c323c;--accent:#93a8f4;color-scheme:dark}}
body{margin:0;background:var(--bg);color:var(--ink);font:1.0625rem/1.55 "Atkinson Hyperlegible","Segoe UI",system-ui,sans-serif;
  padding-left:max(16px, env(safe-area-inset-left, 0px));padding-right:max(16px, env(safe-area-inset-right, 0px))}
.wrap{max-width:64rem;margin:0 auto;padding-block:2rem 4rem;display:grid;gap:1.5rem}
h1{font:700 clamp(1.8rem,5vw,2.6rem)/1.1 "Bricolage Grotesque","Segoe UI",sans-serif;margin:0}
.lede{color:var(--muted);margin:0;max-width:40rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(17rem,1fr));gap:1rem}
a.card{display:grid;gap:.6rem;background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:.75rem;
  color:inherit;text-decoration:none}
a.card:hover,a.card:focus-visible{border-color:var(--accent);outline:none}
a.card img{width:100%;height:auto;border-radius:8px;display:block}
a.card b{font:650 1.1rem/1.25 "Bricolage Grotesque","Segoe UI",sans-serif}
.facts{display:flex;flex-wrap:wrap;gap:.3rem .9rem;font-size:.85rem;color:var(--muted)}
.ver{flex-basis:100%;font:.75rem/1.3 ui-monospace,Consolas,monospace}
footer{font:.75rem/1.4 ui-monospace,Consolas,monospace;color:var(--muted)}
"""


def build_index(site: Path, lessons: list[dict]) -> Path:
    cards = "".join(
        f'<a class="card" href="lessons/{e(x["slug"])}/"><img src="lessons/{e(x["slug"])}/thumb.jpg" alt="" loading="lazy">'
        f'<b>{e(x["title"])}</b><span class="facts"><span>{x["steps"]} steps</span>'
        + (f'<span>{e(x["canvas"])} canvas</span>' if x["canvas"] else "")
        + (f'<span>{x["tubes"]} tubes</span>' if x["tubes"] else "")
        + (f'<span class="ver">Made with Gesso {e(x["version"])}</span>' if x.get("version") else "")
        + "</span></a>"
        for x in sorted(lessons, key=lambda x: x.get("published", ""), reverse=True))
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<title>Our Painting Lessons</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=Bricolage+Grotesque:opsz,wght@12..96,650;12..96,700&display=swap">
<style>{INDEX_STYLE}</style></head><body><div class="wrap">
<header style="display:grid;gap:.5rem"><h1>Our painting lessons</h1>
<p class="lede">Pick one and open it on your phone or tablet next to the easel. Each one has every step's picture, the paints to
mix, and the brushes.</p></header>
<div class="grid">{cards}</div>
<footer>Made with Gesso · <a href="history/" style="color:inherit">Lesson history</a></footer>
</div></body></html>"""
    site.mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text(html, encoding="utf-8")
    headers = site / "_headers"
    if not headers.exists():  # keep it out of search engines, on top of the Access lock
        headers.write_text("/*\n  X-Robots-Tag: noindex, nofollow\n", encoding="utf-8")
    return site / "index.html"
