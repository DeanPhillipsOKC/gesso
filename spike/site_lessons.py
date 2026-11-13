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


def hands_off(run: Path) -> bool:
    from provenance import of
    data = json.loads((run / "lesson.json").read_text(encoding="utf-8"))
    return of(run, data)["kind"] == "hands-off"


def add(lesson: Path, slug: str, site: Path = SITE) -> dict:
    data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
    if not hands_off(lesson):  # owner, 2026-11-12: the site shows what the tool makes on its own
        from provenance import of
        raise ValueError(f"{lesson.name} isn't hands-off ({of(lesson, data)['kind']}); only lessons the skill made and "
                         "sealed (publish --final) go on the site. Fix the tool and run again.")
    page = lesson / "lesson-standalone.html"
    if not page.exists():
        raise FileNotFoundError(f"{page} is missing; run publish first")
    out = site / "lessons" / slug
    out.mkdir(parents=True, exist_ok=True)
    manifest = site / "lessons.json"
    lessons = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    before = next((x for x in lessons if x["slug"] == slug), {})
    old = before.get("source", "")
    if old and old != lesson.name and (out / "index.html").exists():  # #83: the old default stays as a version
        keep = out / "v" / old.split("_skill_")[-1] / "index.html"
        if not keep.exists():
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out / "index.html", keep)
    shutil.copyfile(page, out / "index.html")
    dup = out / "v" / lesson.name.split("_skill_")[-1]
    if dup.is_dir():  # its old version page: the tile page is it now, and a later add() keeps the live page instead
        shutil.rmtree(dup)
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
    entry["versions"] = add_versions(site, slug, lesson.name, lesson.parent, before.get("versions"))
    entry["known"] = known_problems_for(site, entry, lesson.parent)
    lessons = [x for x in lessons if x["slug"] != slug] + [entry]
    manifest.write_text(json.dumps(lessons, indent=2), encoding="utf-8")
    build_index(site, lessons)
    return {"url_path": f"/lessons/{slug}/", "lessons": len(lessons), "versions": len(entry["versions"]),
            "kb": round((out / "index.html").stat().st_size / 1024)}


def kind(data: dict) -> str:
    """What made the step pictures: 'cut from the finish', 'some steps cut from the finish', or '' (rendered)."""
    made = [s.get("made_with", "") for s in data.get("stages", [])[:-1]]
    cut = sum(1 for m in made if m.startswith("composite:from-finish"))
    return "" if not cut else "steps cut from the finish" if cut == len(made) else "some steps cut from the finish"


def standalone(run: Path) -> str:
    """The run's self-contained page, or one built from its saved lesson.json for runs from before those existed
    (nothing is rerun: same pictures, text, and recipes)."""
    page_file = run / "lesson-standalone.html"
    if page_file.exists():
        return page_file.read_text(encoding="utf-8")
    import yaml
    from lesson_page import page
    data = json.loads((run / "lesson.json").read_text(encoding="utf-8"))
    raw = json.loads((run / "plan.json").read_text(encoding="utf-8")) if (run / "plan.json").exists() else {}
    technique = yaml.safe_load((ROOT / (raw.get("technique") or "techniques/acrylic-paint-along-beginner.yaml"))
                               .read_text(encoding="utf-8"))
    return page(data, technique, run, embed=True, standalone=True)


def add_versions(site: Path, slug: str, current: str, output: Path, listed: list[dict] | None = None,
                 remove: tuple[str, ...] = ()) -> list[dict]:
    """Every kept run of the same picture as a version of the lesson (owner, 2026-11-12: pick a version on the
    tile and open it). Each one's page goes to lessons/<slug>/v/<run time>/ once and is never rewritten, so a
    version stays exactly what it was. The current one is the lesson's own page.

    Only adds (#83): a version already `listed` whose page is on the site stays, whether or not its run folder is in
    `output` (which isn't in git, so a fresh checkout has none of the older runs). Runs found in `output` are added
    or updated. A version leaves the list only when named in `remove`."""
    from history import run_time, stamp_at
    photo = current.split("_skill_")[0]
    current_id = current.split("_skill_")[-1]
    lesson_dir = site / "lessons" / slug
    versions: dict[str, dict] = {}
    for v in listed or []:
        page = lesson_dir / ("index.html" if v["id"] == current_id else f"v/{v['id']}/index.html")
        if v["id"] not in remove and page.exists():
            versions[v["id"]] = dict(v)
    for run in sorted(output.glob(f"{photo}_skill_*")):
        rid = run.name.split("_skill_")[-1]
        if rid in remove or not (run / "lesson.json").exists():
            continue
        if not hands_off(run):
            if rid in versions:
                print(f"kept {run.name} on the site though it's no longer hands-off; site-refresh --remove {rid} "
                      "takes it off")
            continue  # recuts and edited runs stay in the lesson history only
        data = json.loads((run / "lesson.json").read_text(encoding="utf-8"))
        g = data.get("gesso") or {}
        made = g.get("made") or g or stamp_at(run.name) or {}
        if run.name != current:
            out = lesson_dir / "v" / rid / "index.html"
            if not out.exists():
                try:
                    html = standalone(run)
                except (OSError, KeyError, ValueError, TypeError) as err:  # a run too old to show: leave it out
                    print(f"skipped {run.name}: {err}")
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(html, encoding="utf-8")
        versions[rid] = {"id": rid, "version": made.get("version", "before stamps"), "when": run_time(run.name),
                         "guessed": bool(made.get("guessed")), "kind": kind(data), "steps": len(data["stages"])}
    for rid, v in versions.items():
        v["href"] = f"lessons/{slug}/" if rid == current_id else f"lessons/{slug}/v/{rid}/"
        v["current"] = rid == current_id
    return sorted(versions.values(), key=lambda v: v["id"], reverse=True)


def known_problems_for(site: Path, x: dict, output: Path) -> int:
    """Refresh the known-problems section on the lesson's page and every version's page. Returns how many the
    current one has (left as they are, plus open issues), for its tile."""
    from known_problems import refresh_page
    photo = x["source"].split("_skill_")[0]
    count = 0
    for v in x.get("versions") or []:
        page = site / v["href"] / "index.html"
        run = output / f"{photo}_skill_{v['id']}"
        if page.exists() and (run / "lesson.json").exists():
            r = refresh_page(page, run)
            if v.get("current"):
                count = r.get("left", 0) + len(r.get("issues_open", []))
    return count


def newest_hands_off(photo: str, output: Path, remove: tuple[str, ...] = ()) -> Path | None:
    """The newest sealed, hands-off run of a picture in `output` that can be shown, or None."""
    for run in sorted(output.glob(f"{photo}_skill_*"), reverse=True):
        if (run.name.split("_skill_")[-1] not in remove and (run / "lesson.json").exists()
                and (run / "lesson-standalone.html").exists() and hands_off(run)):
            return run
    return None


def refresh(site: Path = SITE, output: Path = ROOT / "output", remove: tuple[str, ...] = ()) -> dict:
    """Pick up new runs of every lesson on the site as versions, make each tile open its newest hands-off run (owner,
    2026-11-13: "Should use newest untouched run"), and rebuild the list. It only adds (#83): a version leaves a
    tile, and its page the site, only when its run time is named in `remove` (it stays in the history)."""
    manifest = site / "lessons.json"
    lessons = json.loads(manifest.read_text(encoding="utf-8"))
    for x in list(lessons):
        photo = x["source"].split("_skill_")[0]
        newest = newest_hands_off(photo, output, remove)
        if newest is not None and newest.name > f"{photo}_skill_{x['source'].split('_skill_')[-1]}":
            add(newest, x["slug"], site)  # the old default stays as a version (#83)
    lessons = json.loads(manifest.read_text(encoding="utf-8"))
    for x in lessons:
        gone = tuple(r for r in remove if r != x["source"].split("_skill_")[-1])  # never the default's own page
        x["versions"] = add_versions(site, x["slug"], x["source"], output, x.get("versions"), gone)
        for rid in gone:
            page = site / "lessons" / x["slug"] / "v" / rid
            if page.is_dir():
                shutil.rmtree(page)
        x["known"] = known_problems_for(site, x, output)
    manifest.write_text(json.dumps(lessons, indent=2), encoding="utf-8")
    build_index(site, lessons)
    return {x["slug"]: len(x["versions"]) for x in lessons}


INDEX_STYLE = """
:root{--bg:#fbfbf8;--card:#f1f2ef;--ink:#1d2430;--muted:#5b6474;--rule:#dcdfe3;--accent:#2944a8;--warn:#b3261e}
@media (prefers-color-scheme: dark){:root{--bg:#14171c;--card:#1c2027;--ink:#e7e9ee;--muted:#9aa3b2;--rule:#2c323c;--accent:#93a8f4;--warn:#ff8a80;color-scheme:dark}}
body{margin:0;background:var(--bg);color:var(--ink);font:1.0625rem/1.55 "Atkinson Hyperlegible","Segoe UI",system-ui,sans-serif;
  padding-left:max(16px, env(safe-area-inset-left, 0px));padding-right:max(16px, env(safe-area-inset-right, 0px))}
.wrap{max-width:64rem;margin:0 auto;padding-block:2rem 4rem;display:grid;gap:1.5rem}
h1{font:700 clamp(1.8rem,5vw,2.6rem)/1.1 "Bricolage Grotesque","Segoe UI",sans-serif;margin:0}
.lede{color:var(--muted);margin:0;max-width:40rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(17rem,1fr));gap:1rem}
.card{display:grid;gap:.6rem;align-content:start;background:var(--card);border:1px solid var(--rule);border-radius:12px;
  padding:.75rem;min-width:0}
.card:focus-within,.card:hover{border-color:var(--accent)}
.card img{width:100%;height:auto;border-radius:8px;display:block}
.card a{color:inherit;text-decoration:none}
.card .name{font:650 1.1rem/1.25 "Bricolage Grotesque","Segoe UI",sans-serif}
.card a.known{color:var(--warn);font-weight:700;text-decoration:underline}
.pick{display:grid;gap:.25rem;font-size:.8rem;color:var(--muted)}
.pick select{font:inherit;font-size:.9rem;color:var(--ink);background:var(--bg);border:1px solid var(--rule);border-radius:8px;
  padding:.45rem .5rem;min-height:2.75rem;width:100%;min-width:0}
.card a.open{justify-self:start;background:var(--accent);color:var(--bg);font-weight:700;border-radius:8px;padding:.5rem 1rem;
  min-height:2.75rem;display:inline-flex;align-items:center}
.facts{display:flex;flex-wrap:wrap;gap:.3rem .9rem;font-size:.85rem;color:var(--muted)}
.ver{flex-basis:100%;font:.75rem/1.3 ui-monospace,Consolas,monospace}
footer{font:.75rem/1.4 ui-monospace,Consolas,monospace;color:var(--muted)}
"""


def version_label(v: dict) -> str:
    """'POC 0.20.0 · Nov 11, 2:27 PM · current'."""
    import datetime as dt
    when = v["when"]
    try:
        t = dt.datetime.strptime(when, "%Y-%m-%d %H:%M")
        hour = t.hour % 12 or 12
        when = f"{t:%b} {t.day}, {hour}:{t:%M} {'AM' if t.hour < 12 else 'PM'}"
    except ValueError:
        pass
    guessed = v.get("guessed") and v["version"] != "before stamps"
    text = f'{v["version"]}{" (guessed)" if guessed else ""} · {when}'
    if v.get("kind"):
        text += f' · {v["kind"]}'
    return text + (" · current" if v.get("current") else "")


def card(x: dict) -> str:
    slug = e(x["slug"])
    versions = x.get("versions") or []
    href = f"lessons/{slug}/"
    known = x.get("known") or 0
    facts = (f'<span class="steps">{x["steps"]} steps</span>'
             + (f'<span>{e(x["canvas"])} canvas</span>' if x["canvas"] else "")
             + (f'<span>{x["tubes"]} tubes</span>' if x["tubes"] else "")
             + (f'<a class="known" href="{href}#known-problems">{known} known problem{"s" if known != 1 else ""}</a>'
                if known else ""))
    if len(versions) > 1:
        options = "".join(
            f'<option value="{e(v["href"])}" data-steps="{v["steps"]}"{" selected" if v.get("current") else ""}>'
            f'{e(version_label(v))}</option>' for v in versions)
        picker = f'<label class="pick"><span>Version</span><select>{options}</select></label>'
    else:
        picker = f'<span class="ver">Made with Gesso {e(x.get("version", ""))}</span>' if x.get("version") else ""
    return (f'<div class="card"><a class="pic" href="{href}"><img src="lessons/{slug}/thumb.jpg" alt="" loading="lazy"></a>'
            f'<a class="name" href="{href}">{e(x["title"])}</a><span class="facts">{facts}</span>{picker}'
            f'<a class="open" href="{href}">Open lesson</a></div>')


PICKER_JS = """
document.querySelectorAll('.card select').forEach(sel => sel.addEventListener('change', () => {
  const card = sel.closest('.card'), opt = sel.selectedOptions[0];
  card.querySelectorAll('a').forEach(a => { a.href = opt.value; });
  card.querySelector('.steps').textContent = opt.dataset.steps + ' steps';
}));
window.addEventListener('pageshow', () => document.querySelectorAll('.card select').forEach(sel => sel.dispatchEvent(new Event('change'))));
"""


def build_index(site: Path, lessons: list[dict]) -> Path:
    cards = "".join(card(x) for x in sorted(lessons, key=lambda x: (x.get("published", ""), x.get("slug", "")),
                                            reverse=True))
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
</div><script>{PICKER_JS}</script></body></html>"""
    site.mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text(html, encoding="utf-8")
    headers = site / "_headers"
    if not headers.exists():  # keep it out of search engines, on top of the Access lock
        headers.write_text("/*\n  X-Robots-Tag: noindex, nofollow\n", encoding="utf-8")
    return site / "index.html"
