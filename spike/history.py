"""Lesson history: every publish is kept, so a lesson that got worse can be traced to the version that did it.

    record(lesson, data, checks) -> adds a publish to site/history/<photo>/<run>/ (record.json + strip-<n>.jpg) and
                                    keeps the full lesson in <lesson>/versions/<n>/; skips a publish that changed nothing
    backfill(output) -> records every finished run already in output/ (their last publish only)
    build_page() -> site/history/index.html: each photo's runs, newest first, with what changed in between

The owner, 2026-11-12: "we could be making things worse and not know exactly at what point it got worse because so
much of this is subjective." So nothing is overwritten. Each run (an output folder) keeps every publish that changed
its pictures or text, with the version and commit that made it, the cost, the checks, and a strip of every step.
The page lists the changelog entries between one run and the run before it, which is where to look when a run is
worse, and the owner's scores (ratings.json) sit next to each run.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
from html import escape as e
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "site" / "history"
CHANGELOG = ROOT / "docs" / "changelog.md"


def home(history: Path | None = None) -> Path:
    """site/history/, or GESSO_HISTORY (tests point it at a temp folder so they never touch the real history)."""
    return Path(history or os.environ.get("GESSO_HISTORY") or HISTORY)


RUN_TIME = re.compile(r"_(\d{8})-(\d{6})$")
CHECKS = ["long_steps", "long_instructions", "paints_not_listed", "unreachable_paints", "texture_jumps",
          "duplicate_recipes", "undocumented_diagrams"]


def photo_key(data: dict, lesson: Path) -> str:
    """The picture a run is of. The run folder names it (balloon-lavender_skill_...); the plan's photo can be a
    crop or canvas fit (00_canvas_fit.png), so it's only the fallback."""
    name = lesson.name.split("_skill_")[0] if "_skill_" in lesson.name else Path(data.get("photo") or lesson.name).stem
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")


def run_time(name: str) -> str:
    """'2026-11-11 14:27' from an output folder name ending in _20261111-142734."""
    m = RUN_TIME.search(name)
    if not m:
        return ""
    d, t = m.groups()
    return f"{d[:4]}-{d[4:6]}-{d[6:]} {t[:2]}:{t[2:4]}"


def digest(lesson: Path, data: dict) -> str:
    """Changes when any step picture, instruction, or paint does; not when only the stamp does."""
    h = hashlib.sha256()
    for s in data.get("stages", []):
        p = lesson / s["image"]
        h.update(p.read_bytes() if p.exists() else s["image"].encode())
        h.update(json.dumps([s.get("steps"), s.get("colors"), s.get("values")], sort_keys=True,
                            default=str).encode())
    return h.hexdigest()[:16]


def strip(lesson: Path, data: dict, out: Path, size: int = 200, cols: int = 6) -> Path:
    """Every step's picture in one small numbered grid."""
    thumbs = []
    for s in data.get("stages", []):
        p = lesson / s["image"]
        im = Image.open(p).convert("RGB") if p.exists() else Image.new("RGB", (size, size), (200, 200, 200))
        im.thumbnail((size, size))
        thumbs.append(im)
    if not thumbs:
        raise ValueError(f"{lesson} has no steps")
    w, h = max(t.width for t in thumbs), max(t.height for t in thumbs)
    rows = -(-len(thumbs) // cols)
    gap = 4
    sheet = Image.new("RGB", (min(cols, len(thumbs)) * (w + gap) - gap, rows * (h + gap) - gap), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for i, t in enumerate(thumbs):
        x, y = (i % cols) * (w + gap), (i // cols) * (h + gap)
        sheet.paste(t, (x, y))
        label = "F" if i == len(thumbs) - 1 else str(i + 1)
        draw.rectangle([x, y, x + 9 + 7 * len(label), y + 16], fill=(255, 255, 255))
        draw.text((x + 4, y + 2), label, fill=(0, 0, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=72, optimize=True)
    return out


def metrics(data: dict, checks: dict | None) -> dict:
    calls = data.get("calls") or []
    renders = [c for c in calls if c.get("tool") == "render"]
    review = data.get("review_issues") or []
    m = {
        "steps": len(data.get("stages") or []),
        "words": sum(len(x.split()) for s in data.get("stages") or [] for x in (s.get("steps") or [])),
        "tubes": len(data.get("tubes") or []),
        "cost_usd": round(data.get("total_cost_usd") or 0, 3),
        "minutes": round((data.get("total_seconds") or 0) / 60, 1),
        "paid_renders": sum(1 for c in renders if not c.get("cached")),
        "redos": sum(1 for r in review if "redo" in str(r.get("action", ""))),
        "review_problems": len(review),
        "text_problems": len(data.get("text_issues") or []),
    }
    if checks is not None:
        m["checks"] = {k: len(checks.get(k) or []) for k in CHECKS}
    return m


def _stamp(data: dict) -> tuple[dict, dict]:
    g = data.get("gesso") or {}
    return g, g.get("made") or {k: g[k] for k in ("version", "commit", "published") if k in g}


def record(lesson: Path, data: dict, checks: dict | None = None, history: Path | None = None,
           stamp_override: dict | None = None) -> dict:
    lesson, history = Path(lesson), home(history)
    key, run = photo_key(data, lesson), lesson.name
    folder = history / key / run
    path = folder / "record.json"
    rec = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "photo": key, "run": run, "started": run_time(run), "publishes": []}
    d = digest(lesson, data)
    if rec["publishes"] and rec["publishes"][-1]["digest"] == d:
        return {"recorded": False, "reason": "nothing changed since the last publish", "run": run}
    n = len(rec["publishes"]) + 1
    g, made = _stamp(data)
    if stamp_override:
        g, made = stamp_override, stamp_override
    strip(lesson, data, folder / f"strip-{n}.jpg")
    rec["publishes"].append({
        "n": n, "digest": d, "strip": f"strip-{n}.jpg",
        "published_with": {k: g.get(k) for k in ("version", "commit", "dirty", "published")},
        "made_with": made, "palette": data.get("palette_name") or "", "technique": data.get("technique", ""),
        "canvas": data.get("canvas"), "metrics": metrics(data, checks),
        "steps": [{"id": s["id"], "name": s.get("name", ""), "made_with": s.get("made_with", "")}
                  for s in data.get("stages") or []],
    })
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    keep = lesson / "versions" / str(n)  # the whole lesson, locally, to open or diff later
    keep.mkdir(parents=True, exist_ok=True)
    for name in ("lesson.json", "lesson-standalone.html", "plan.json", "text.json"):
        if (lesson / name).exists():
            shutil.copyfile(lesson / name, keep / name)
    return {"recorded": True, "run": run, "publish": n, "page": str(build_page(history))}


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def stamp_at(run: str) -> dict | None:
    """For a run from before stamps: the main commit and version current when the run started."""
    t = run_time(run)
    if not t:
        return None
    commit = _git("log", "-1", f"--before={t}", "--format=%h", "main")
    if not commit:
        return None
    ver = _git("show", f"{commit}:spike/VERSION") or "before stamps"
    return {"version": ver, "commit": commit, "published": t[:10], "dirty": None, "guessed": True}


def backfill(output: Path = ROOT / "output", history: Path | None = None) -> list[dict]:
    history = home(history)
    done = []
    for lesson in sorted(Path(output).glob("*_skill_*")):
        if lesson.name.startswith("locktest_") or not (lesson / "lesson.json").exists():
            continue
        data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
        override = None if (data.get("gesso") or {}).get("version") else stamp_at(lesson.name)
        try:
            done.append(record(lesson, data, None, history, override))
        except (ValueError, OSError) as err:
            done.append({"recorded": False, "run": lesson.name, "reason": str(err)})
    build_page(history)
    return done


def vkey(v: str) -> tuple:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(x) for x in nums[:3]) if nums else (-1,)


def changelog(path: Path = CHANGELOG) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    cur = None
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        m = re.match(r"## (POC [\d.]+)", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur and line.startswith("- "):
            out[cur].append(line[2:].strip())
        elif cur and line.startswith("  ") and out[cur]:
            out[cur][-1] += " " + line.strip()
    return out


def between(log: dict[str, list[str]], older: str, newer: str) -> list[tuple[str, list[str]]]:
    lo, hi = vkey(older), vkey(newer)
    return sorted(((v, b) for v, b in log.items() if lo < vkey(v) <= hi), key=lambda x: vkey(x[0]))


PAGE_STYLE = """
[hidden]{display:none!important}
:root{--bg:#fbfbf8;--card:#f1f2ef;--ink:#1d2430;--muted:#5b6474;--rule:#dcdfe3;--accent:#2944a8;--good:#1f7a4d;--bad:#b3261e}
@media (prefers-color-scheme: dark){:root{--bg:#14171c;--card:#1c2027;--ink:#e7e9ee;--muted:#9aa3b2;--rule:#2c323c;--accent:#93a8f4;--good:#6fd39c;--bad:#ff8a80;color-scheme:dark}}
body{margin:0;background:var(--bg);color:var(--ink);font:1rem/1.5 "Atkinson Hyperlegible","Segoe UI",system-ui,sans-serif;
  padding-left:max(16px, env(safe-area-inset-left, 0px));padding-right:max(16px, env(safe-area-inset-right, 0px))}
.wrap{max-width:72rem;margin:0 auto;padding-block:2rem 4rem;display:grid;gap:2rem}
h1{font:700 clamp(1.7rem,5vw,2.4rem)/1.1 "Bricolage Grotesque","Segoe UI",sans-serif;margin:0}
h2{font:650 1.35rem/1.2 "Bricolage Grotesque","Segoe UI",sans-serif;margin:0}
.lede{color:var(--muted);margin:0;max-width:44rem}
section{display:grid;gap:1rem}
.run{background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:.9rem;display:grid;gap:.6rem;min-width:0}
.run.picked{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent)}
.head{display:flex;flex-wrap:wrap;gap:.3rem 1rem;align-items:baseline}
.head b{font:650 1.05rem/1.2 "Bricolage Grotesque","Segoe UI",sans-serif}
.mono{font:.8rem/1.4 ui-monospace,Consolas,monospace;color:var(--muted)}
.facts{display:flex;flex-wrap:wrap;gap:.2rem .9rem;font-size:.85rem;color:var(--muted)}
.score{font-weight:700}.score.hi{color:var(--good)}.score.lo{color:var(--bad)}
.run img{width:100%;height:auto;border-radius:6px;display:block}
details{font-size:.9rem}summary{cursor:pointer;color:var(--accent)}
details ul{margin:.4rem 0 0;padding-left:1.2rem}details li{margin:.2rem 0}
label.pick{font-size:.85rem;display:flex;gap:.4rem;align-items:center;cursor:pointer}
#compare{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--bg);border-bottom:1px solid var(--rule);
  padding-block:.6rem;display:grid;gap:.5rem}
#compare .pair{display:grid;grid-template-columns:1fr;gap:.5rem;max-height:70vh;overflow:auto}
@media (min-width:60rem){#compare .pair{grid-template-columns:1fr 1fr}}
#compare figure{margin:0;display:grid;gap:.25rem;min-width:0}#compare img{width:100%;height:auto;display:block;border-radius:6px}#compare figcaption{font-size:.8rem;color:var(--muted)}
#compare button{justify-self:start;font:inherit;padding:.3rem .8rem;border-radius:8px;border:1px solid var(--rule);
  background:var(--card);color:var(--ink);cursor:pointer}
"""


def _ratings(history: Path) -> dict:
    p = history / "ratings.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def build_page(history: Path | None = None) -> Path:
    history = home(history)
    log = changelog()
    ratings = _ratings(history)
    sections = []
    groups = [p for p in history.iterdir() if p.is_dir()] if history.exists() else []
    # the picture with the newest run first
    groups.sort(key=lambda g: max((run_time(r.name) for r in g.iterdir() if r.is_dir()), default=""), reverse=True)
    for group in groups:
        recs = [json.loads(r.read_text(encoding="utf-8")) for r in group.glob("*/record.json")]
        entries = [(r, p) for r in recs for p in r["publishes"]]
        entries.sort(key=lambda rp: (rp[0]["started"], rp[1]["n"]))
        cards = []
        prev_ver = None
        for r, p in entries:
            made = p.get("made_with") or {}
            ver = made.get("version", "")
            new = between(log, prev_ver, ver) if prev_ver and ver != prev_ver else []
            prev_ver = ver or prev_ver
            m = p["metrics"]
            rid = f'{r["run"]}#{p["n"]}'
            rate = ratings.get(rid) or (ratings.get(r["run"]) if p["n"] == len(r["publishes"]) else None)
            score = ""
            if rate:
                s = rate.get("score")
                cls = "hi" if s and s >= 4 else "lo" if s and s <= 2 else ""
                score = (f'<span class="score {cls}">Rated {s}/5</span>' if s else "") + (
                    f' <span>{e(rate.get("note", ""))}</span>' if rate.get("note") else "")
            checks = m.get("checks")
            fails = sum(checks.values()) if checks else None
            facts = [f'{m["steps"]} steps', f'{m["words"]} words', f'${m["cost_usd"]:.2f}', f'{m["paid_renders"]} paid renders',
                     f'{m["redos"]} redos', f'{m["review_problems"] + m["text_problems"]} review fixes']
            if m.get("tubes"):
                facts.append(f'{m["tubes"]} tubes')
            if fails is not None:
                facts.append(f"{fails} check flags")
            img = f'{group.name}/{r["run"]}/{p["strip"]}'
            guessed = " (guessed from the date)" if made.get("guessed") else ""
            repub = (p.get("published_with") or {}).get("version")
            repub_txt = f", published with {e(repub)}" if repub and repub != ver else ""
            changed = ""
            if new:
                items = "".join(f"<li><b>{e(v)}</b>: {e(b)}</li>" for v, bs in new for b in bs)
                changed = (f'<details><summary>{len(new)} version{"s" if len(new) > 1 else ""} since the run before '
                           f'({e(new[0][0])} to {e(new[-1][0])})</summary><ul>{items}</ul></details>')
            cards.append(
                f'<article class="run" data-id="{e(rid)}" data-img="{e(img)}" data-label="{e(ver)} {e(r["started"])}">'
                f'<div class="head"><b>{e(ver or "unknown version")}</b>'
                f'<span class="mono">{e(made.get("commit", ""))}{e(guessed)}{repub_txt}</span>'
                f'<span class="mono">{e(r["started"])} · publish {p["n"]}</span>{score}</div>'
                f'<span class="facts">{"".join(f"<span>{x}</span>" for x in facts)}</span>'
                f'<img src="{e(img)}" alt="Every step of this run" loading="lazy">{changed}'
                f'<label class="pick"><input type="checkbox"> Compare</label>'
                f'<span class="mono">{e(rid)}</span></article>')
        sections.append(f'<section><h2>{e(group.name.replace("-", " ").capitalize())}</h2>'
                        f'<p class="lede">{len(entries)} kept, newest first.</p>{"".join(reversed(cards))}</section>')
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<title>Lesson History</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=Bricolage+Grotesque:opsz,wght@12..96,650;12..96,700&display=swap">
<style>{PAGE_STYLE}</style></head><body><div class="wrap">
<header style="display:grid;gap:.5rem"><h1>Lesson history</h1>
<p class="lede">Every run of every picture, and every republish that changed it, with the Gesso version that made it.
When one looks worse than the run before, open "since the run before" for what changed in between. Tick two runs to
see them side by side.</p><p class="mono"><a href="../">Back to the lessons</a></p></header>
<div id="compare" hidden><div class="pair"></div><button type="button">Clear</button></div>
{"".join(sections)}
</div><script>
const box=document.getElementById('compare'),pair=box.querySelector('.pair');let picked=[];
function show(){{pair.replaceChildren(...picked.map(a=>{{const f=document.createElement('figure'),i=new Image(),c=document.createElement('figcaption');
i.src=a.dataset.img;i.alt='';c.textContent=a.dataset.label;f.append(c,i);return f}}));box.hidden=!picked.length;
document.querySelectorAll('.run').forEach(a=>{{a.classList.toggle('picked',picked.includes(a));a.querySelector('input').checked=picked.includes(a)}})}}
document.querySelectorAll('.run input').forEach(cb=>cb.addEventListener('change',()=>{{const a=cb.closest('.run');
picked=cb.checked?[...picked.filter(x=>x!==a),a].slice(-2):picked.filter(x=>x!==a);show()}}));
box.querySelector('button').addEventListener('click',()=>{{picked=[];show()}});
</script></body></html>"""
    history.mkdir(parents=True, exist_ok=True)
    (history / "index.html").write_text(html, encoding="utf-8")
    return history / "index.html"


def rate(run: str, score: int | None, note: str = "", history: Path | None = None) -> dict:
    """The owner's score for a run (or 'run#n' for one publish), 1 to 5."""
    history = home(history)
    if score is not None and not 1 <= score <= 5:
        raise ValueError("score is 1 to 5")
    ratings = _ratings(history)
    ratings[run] = {"score": score, "note": note, "rated": dt.date.today().isoformat()}
    history.mkdir(parents=True, exist_ok=True)
    (history / "ratings.json").write_text(json.dumps(ratings, indent=2), encoding="utf-8")
    build_page(history)
    return {"run": run, **ratings[run]}
