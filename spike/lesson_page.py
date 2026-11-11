"""The lesson as a page: one generator for the local lesson.html and the Claude artifact (#10).

    page(lesson, technique, folder, embed=False)  -> HTML with images by relative path (lesson.html)
    page(lesson, technique, folder, embed=True)   -> HTML with images inlined as JPEG data URIs, for an artifact

The artifact form follows the Artifact page contract: no doctype/html/head/body of its own, a <title> first,
color tokens for light and dark, side gutters that clear a phone's system bars, and nothing loaded from
anywhere but Google Fonts.
"""

from __future__ import annotations

import base64
import io
from html import escape as e
from pathlib import Path

from PIL import Image, ImageOps

STYLE = """
/* Layout: one reading column; each step pairs its canvas image with what to do, stacking on phones. */
:root{
  --gesso:#fbfbf8; --panel:#f1f2ef; --ink:#1d2430; --muted:#5b6474; --rule:#dcdfe3;
  --ultramarine:#2944a8; --ultramarine-soft:#e3e8f7; --warn:#8a4b12;
  --grid:#e6e8e4; --r-filter:#2f7a4f; --r-throw:#1f7383; --r-seeded:#9a6512; --r-render:#5a3fa8; --stamp:#b0412e;
  --hand:"Caveat", "Segoe Print", cursive;
  --display:"Bricolage Grotesque", "Segoe UI", system-ui, sans-serif;
  --body:"Atkinson Hyperlegible", "Segoe UI", system-ui, sans-serif;
  --mono:"JetBrains Mono", ui-monospace, Consolas, monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --gesso:#14171c; --panel:#1c2027; --ink:#e7e9ee; --muted:#9aa3b2; --rule:#2c323c;
  --ultramarine:#93a8f4; --ultramarine-soft:#232c48; --warn:#e5a86b;
  --grid:#232831; --r-filter:#7fcf9c; --r-throw:#72c7d4; --r-seeded:#e3b25e; --r-render:#b7a4f2; --stamp:#f08f78; color-scheme:dark}}
:root[data-theme="dark"]{
  --gesso:#14171c; --panel:#1c2027; --ink:#e7e9ee; --muted:#9aa3b2; --rule:#2c323c;
  --ultramarine:#93a8f4; --ultramarine-soft:#232c48; --warn:#e5a86b;
  --grid:#232831; --r-filter:#7fcf9c; --r-throw:#72c7d4; --r-seeded:#e3b25e; --r-render:#b7a4f2; --stamp:#f08f78; color-scheme:dark}
body{background:var(--gesso);color:var(--ink);font:1.0625rem/1.6 var(--body);
  padding-left:max(16px, env(safe-area-inset-left, 0px));padding-right:max(16px, env(safe-area-inset-right, 0px))}
.wrap{max-width:68rem;margin:0 auto;padding-block:2rem 4rem;display:grid;gap:2.5rem}
h1,h2,h3{font-family:var(--display);line-height:1.15;text-wrap:balance;margin:0}
h1{font-size:clamp(2rem, 5vw, 3rem);font-weight:700;letter-spacing:-0.01em}
h2{font-size:1.5rem;font-weight:650}
h3{font-size:1.3rem;font-weight:650}
p{margin:0}
.eyebrow{font:600 .75rem/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--ultramarine)}
.lede{color:var(--muted);max-width:42rem}
header{display:grid;gap:.75rem}
.facts{display:flex;flex-wrap:wrap;gap:.5rem 1.25rem;color:var(--muted);font-size:.9rem}
.facts b{color:var(--ink);font-weight:600}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
figure{margin:0;display:grid;gap:.4rem;min-width:0}
figcaption{font-size:.85rem;color:var(--muted)}
img{max-width:100%;width:100%;height:auto;display:block;border-radius:4px;border:1px solid var(--rule)}
section{display:grid;gap:1rem}
.paints{display:grid;grid-template-columns:repeat(auto-fill, minmax(15rem, 1fr));gap:.75rem}
.paint{display:grid;grid-template-columns:2.75rem 1fr;gap:.75rem;align-items:start;min-width:0}
.blob{width:2.75rem;height:2.75rem;border-radius:46% 54% 50% 50% / 55% 45% 55% 45%;border:1px solid var(--rule)}
.paint b{display:block}
.recipe{font:.82rem/1.45 var(--mono);color:var(--muted)}
.kit{display:grid;grid-template-columns:repeat(auto-fit, minmax(16rem, 1fr));gap:1rem}
.kit ul{margin:0;padding-left:1.1rem;display:grid;gap:.3rem}
.strip{display:flex;gap:.5rem;overflow-x:auto;padding-bottom:.25rem}
.strip a{flex:0 0 5.5rem;text-decoration:none;color:var(--muted);font:.72rem/1.3 var(--mono);display:grid;gap:.25rem}
.strip a:focus-visible{outline:2px solid var(--ultramarine);outline-offset:2px}
.step{display:grid;grid-template-columns:minmax(0, 1.1fr) minmax(0, 1fr);gap:1.75rem;align-items:start;
  padding-top:2rem;border-top:1px solid var(--rule)}
.step .text{display:grid;gap:1rem;min-width:0}
.num{font:700 .8rem/1 var(--mono);color:var(--ultramarine);letter-spacing:.08em}
ol.do{margin:0;padding-left:1.3rem;display:grid;gap:.45rem}
.tools{display:grid;gap:.6rem;background:var(--panel);border-radius:6px;padding:1rem}
.label{font:600 .72rem/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:.4rem}
.chip{background:var(--ultramarine-soft);color:var(--ink);border-radius:999px;padding:.2rem .7rem;font-size:.88rem;
  display:inline-flex;align-items:center;gap:.35rem}
/* Brush pictures: the head and the mark it makes, so "#8 round" means something to a beginner. */
.brushpic{width:10rem;height:auto;flex:none;display:block}
.brushpic.sm{width:2.4rem}
.kit li.brush{display:grid;grid-template-columns:10rem 1fr;gap:.6rem;align-items:center}
.kit li.brush .small{display:block}
.kit div:has(li.brush){grid-column:1/-1}
.kit ul:has(li.brush){list-style:none;padding-left:0;grid-template-columns:repeat(auto-fill, minmax(20rem, 1fr));gap:.8rem 1.5rem}
@media (max-width: 480px){.kit li.brush{grid-template-columns:6rem 1fr}.brushpic{width:6rem}}
.stroke b{color:var(--ultramarine)}
.mixes{display:flex;flex-wrap:wrap;gap:.5rem 1rem}
.mix{display:flex;align-items:center;gap:.4rem;font-size:.92rem}
.dot{width:1rem;height:1rem;border-radius:50%;border:1px solid var(--rule);flex:none}
.watch{color:var(--warn);font-size:.95rem}
/* Values table: the dark, mid, and light of a step, so depth is shown, not described. */
table.values{border-collapse:collapse;width:100%;font-size:.92rem}
table.values caption{text-align:left;font:600 .72rem/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);padding-bottom:.4rem}
table.values th,table.values td{text-align:left;padding:.35rem .5rem;border-bottom:1px solid var(--rule);vertical-align:top}
table.values thead th{font:600 .72rem/1.2 var(--mono);color:var(--muted)}
table.values tbody th{font-weight:700;text-transform:capitalize;white-space:nowrap}
table.values td .dot{display:inline-block;vertical-align:-2px;margin-right:.35rem}
.warnc{display:block;color:var(--warn)}.warnc .dot{display:inline-block;vertical-align:-2px}
/* Paints for this step: the mixes it uses, recipes included, so nothing has to be mixed ahead and dry out. */
details.mixfor{background:var(--panel);border-radius:6px;padding:.6rem 1rem}
details.mixfor>summary{display:flex;flex-wrap:wrap;align-items:center;gap:.4rem .7rem}
details.mixfor>summary::before{content:"+";font:600 .95rem/1 var(--mono);color:var(--ultramarine);width:1rem;text-align:center}
details[open].mixfor>summary::before{content:"\\2212"}
details.mixfor .dots{display:flex;gap:.2rem}
.mixlist{margin:.6rem 0 .2rem;display:grid;gap:.7rem}
.mixlist li{display:grid;grid-template-columns:2rem 1fr;gap:.6rem;align-items:start;min-width:0}
.mixlist .blob{width:2rem;height:2rem}
.mixlist .recipe{display:block}
.new{font:600 .68rem/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--r-filter);
  border:1px solid currentColor;border-radius:3px;padding:.15rem .35rem}
.small{font-size:.85rem;color:var(--muted)}
.made{font:.75rem/1.4 var(--mono);color:var(--muted);text-align:center}
ul.plain{list-style:none;padding-left:0!important}
/* Construction diagrams: build a shape from simple pieces, one panel per move, under the step it belongs to. */
.build{grid-column:1/-1;display:grid;gap:.6rem;background:var(--panel);border-radius:8px;padding:1rem;min-width:0}
.panels{display:grid;grid-template-columns:repeat(auto-fill, minmax(8.5rem, 12rem));gap:.75rem}
.panel{gap:.35rem}
.panel svg{width:100%;height:auto;aspect-ratio:1;background:var(--gesso);border:1px solid var(--rule);border-radius:6px;display:block}
.panel figcaption{color:var(--ink);font-size:.88rem}
.panel figcaption b{font:700 .78rem/1 var(--mono);color:var(--ultramarine);margin-right:.25rem}
.flag{border-left:3px solid var(--warn);padding:.4rem .75rem;font-size:.92rem;background:var(--panel)}
/* Behind the easel: the reasoning, folded away so it never gets between the painter and the steps. */
.facts a{color:var(--ultramarine)}
details>summary{list-style:none;cursor:pointer}
details>summary::-webkit-details-marker{display:none}
details>summary:focus-visible{outline:2px solid var(--ultramarine);outline-offset:3px;border-radius:4px}
details.why{border-top:1px dashed var(--rule);padding-top:.6rem}
details.why>summary{display:flex;flex-wrap:wrap;align-items:center;gap:.4rem .6rem;font:600 .75rem/1.3 var(--mono);
  letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
details.why>summary::before,details.note>summary::before{content:"+";font:600 .95rem/1 var(--mono);color:var(--ultramarine);
  width:1rem;flex:none;text-align:center}
details[open].why>summary::before,details[open].note>summary::before{content:"\\2212"}
.why-body{display:grid;gap:.7rem;padding:.75rem 0 .25rem 1.6rem;font-size:.93rem}
.tag{font:600 .68rem/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;border:1px solid currentColor;
  border-radius:3px;padding:.2rem .4rem;white-space:nowrap}
.t-filter{color:var(--r-filter)}.t-throw{color:var(--r-throw)}.t-seeded{color:var(--r-seeded)}.t-render{color:var(--r-render)}
.t-review{color:var(--warn)}.t-diagram{color:var(--ultramarine)}
.diag{border-left:3px solid var(--ultramarine);padding-left:.75rem;display:grid;gap:.35rem}
.diaglist{display:grid;gap:.9rem}.diaglist a{color:var(--ink)}.diaglist p{margin-top:.2rem}
ol.trail{list-style:none;margin:0;padding:0;display:grid;gap:.55rem;border-left:2px solid var(--rule);padding-left:.9rem}
ol.trail li{display:grid;gap:.2rem;min-width:0}
ol.trail .head{display:flex;flex-wrap:wrap;gap:.3rem .5rem;align-items:center;font:.78rem/1.3 var(--mono);color:var(--muted)}
.behind{background-color:var(--panel);border-radius:10px;padding:clamp(1rem, 3vw, 2rem);display:grid;gap:1.25rem;
  background-image:linear-gradient(var(--grid) 1px, transparent 1px),linear-gradient(90deg, var(--grid) 1px, transparent 1px);
  background-size:22px 22px;scroll-margin-top:1rem}
.behind>header{display:grid;gap:.5rem}
.margin{font:500 1.35rem/1.2 var(--hand);color:var(--stamp);transform:rotate(-1.5deg);transform-origin:left;width:fit-content}
.ladder{display:grid;gap:.5rem;background:var(--gesso);border:1px solid var(--rule);border-radius:8px;padding:1rem}
.rung{display:grid;grid-template-columns:minmax(8.5rem, 11rem) 1fr;gap:.75rem;align-items:center;padding:.5rem 0;
  border-bottom:2px solid var(--rule)}
.rung:last-child{border-bottom:0}
.rname{display:grid;gap:.1rem}.rname b{font:650 1rem/1.2 var(--display)}.rname span{font:.75rem/1.2 var(--mono);color:var(--muted)}
.rchips{display:flex;flex-wrap:wrap;gap:.35rem}
.pip{font:600 .78rem/1 var(--mono);border-radius:999px;padding:.3rem .6rem;color:var(--gesso);text-decoration:none}
.pip.tried{background:transparent!important;border:1.5px dashed currentColor;text-decoration:line-through}
.pip.none{color:var(--muted);background:transparent;font-weight:400;padding-inline:0}
.p-filter{background:var(--r-filter);color:var(--gesso)}.p-throw{background:var(--r-throw);color:var(--gesso)}
.p-seeded{background:var(--r-seeded);color:var(--gesso)}.p-render{background:var(--r-render);color:var(--gesso)}
.pip.tried.p-filter{color:var(--r-filter)}.pip.tried.p-throw{color:var(--r-throw)}.pip.tried.p-seeded{color:var(--r-seeded)}
details.note{border-top:1px solid var(--rule);background:var(--gesso);border-radius:8px;padding:0 1rem}
details.note>summary{display:flex;align-items:baseline;gap:.6rem;padding:.9rem 0;font:650 1.1rem/1.25 var(--display)}
details.note>summary .hint{font:400 .85rem/1.3 var(--body);color:var(--muted);margin-left:auto;text-align:right}
.note-body{display:grid;gap:1rem;padding:0 0 1.25rem 1.6rem;min-width:0}
.note-body ul,.note-body ol{margin:0;padding-left:1.2rem;display:grid;gap:.35rem}
.pick{display:grid;gap:.75rem;grid-template-columns:repeat(auto-fit, minmax(15rem, 1fr))}
.card{border:1px solid var(--rule);border-radius:8px;padding:.9rem;display:grid;gap:.4rem;align-content:start;position:relative}
.card.chosen{border:2px solid var(--ultramarine)}
.card .tag{justify-self:start}
.stamp{font:700 .7rem/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--stamp);border:2px solid currentColor;
  border-radius:4px;padding:.25rem .45rem;transform:rotate(-4deg);justify-self:start}
.stamp.keep{color:var(--r-filter)}
.board{list-style:none;padding:0!important;display:grid!important;gap:.75rem!important}
.board li{display:grid;grid-template-columns:4.5rem 1fr;gap:.75rem;align-items:start}
.board img{border-radius:3px}
.board b{font-family:var(--display)}
.sheet{display:grid;grid-template-columns:repeat(auto-fill, minmax(12.5rem, 1fr));gap:1rem}
.sheet figure{background:var(--panel);border-radius:6px;padding:.6rem;gap:.45rem;align-content:start}
.sheet code,.mono{font:.75rem/1.4 var(--mono);color:var(--muted);overflow-wrap:anywhere}
.receipt{font:.82rem/1.5 var(--mono);max-width:26rem;width:100%;background:var(--gesso);border:1px solid var(--rule);
  border-block:2px dashed var(--muted);padding:1rem 1.1rem;display:grid;gap:.15rem;justify-self:start}
.receipt .row{display:flex;justify-content:space-between;gap:1rem}
.receipt .row span:first-child{min-width:0;overflow-wrap:anywhere}
.receipt .sub{color:var(--muted);font-size:.72rem;padding-left:1rem}
.receipt .total{border-top:1px dashed var(--muted);margin-top:.4rem;padding-top:.4rem;font-weight:600}
.receipt .thanks{font:500 1.2rem/1.2 var(--hand);color:var(--stamp);text-align:center;margin-top:.5rem}
@media (max-width: 560px){.rung{grid-template-columns:1fr;gap:.4rem}.note-body,.why-body{padding-left:0}
  details.note>summary .hint{display:none}}
@media (max-width: 760px){.step,.pair{grid-template-columns:1fr}}
"""

FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700'
         '&family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=Caveat:wght@500&family=JetBrains+Mono:wght@400;600&display=swap">')


def image_src(folder: Path, name: str, embed: bool, max_side: int = 900) -> str:
    if not embed:
        return e(name)
    img = ImageOps.exif_transpose(Image.open(folder / name)).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def dims(path: Path) -> str:
    """width/height attributes, so the browser reserves each image's space before it decodes. Without them the page
    grows while images load, and a jump to #behind or #step-N lands somewhere else."""
    try:
        w, h = ImageOps.exif_transpose(Image.open(path)).size
    except OSError:
        return ""
    return f' width="{w}" height="{h}"'


def title_for(lesson: dict, folder: Path | None = None) -> str:
    """Named after the original photo, which the lesson folder carries (<photo stem>_skill_<time>), since the photo
    the lesson uses may be a crop or a beginner version. Words like screenshot are dropped."""
    stem = Path(lesson["photo"]).stem
    if folder is not None and "_skill_" in folder.name:  # cropped or beginner-version photos have working names
        stem = folder.name.split("_skill_")[0]
    words = [w for w in stem.replace("-", " ").replace("_", " ").split() if w.lower() not in ("screenshot", "screen", "cropped")]
    return f"{' '.join(words).title() or 'Painting'} Lesson"


def items(xs, cls="") -> str:
    return "".join(f"<li{f' class={cls}' if cls else ''}>{e(x)}</li>" for x in xs)


def page(lesson: dict, technique: dict, folder: Path, embed: bool = False) -> str:
    from construct import strip as build_strip
    from lesson_notes import behind, step_why
    from version import line
    read = lesson["photo_read"]
    stages = lesson["stages"]
    # Problems the review found and left (caps or rounds ran out), shown on their step so the painter knows.
    left: dict[str, list[str]] = {}
    for x in lesson.get("review_issues", []):
        if x.get("action") == "left":
            left.setdefault(x["step_id"], []).append(x["problem"])
    paints = read.get("mixes", [])
    by_name = {p["name"]: p for p in paints}

    # Everything the painter needs before starting, gathered from the steps.
    brushes: dict[str, str] = {}
    for s in stages:
        for b in s.get("brush_list", []):
            brushes.setdefault(b["brush"], b.get("use", ""))
    tubes = technique.get("palette", [])
    cv = lesson.get("canvas") or {}
    canvas_item = (f'A {cv["w_in"]:g} x {cv["h_in"]:g} in canvas, {cv["orientation"]}'
                   + ("" if cv["orientation"] == "square" else " (hang it that way)") +
                   f'. Positions in the steps are percentages across and down: each 10% is {cv["w_in"] / 10:g} in '
                   f'across and {cv["h_in"] / 10:g} in down.') if cv else "White canvas or canvas board"

    photo = image_src(folder, lesson["photo_file"], embed) if lesson.get("photo_file") else ""
    finish = image_src(folder, stages[-1]["image"], embed)
    imgs = [image_src(folder, s["image"], embed, 1000) for s in stages]
    thumbs = [image_src(folder, s["image"], embed, 200) for s in stages] if embed else imgs

    # The step each paint is first needed in. Beginners mix as they go, since acrylics dry on the palette.
    first: dict[str, int] = {}
    for i, s in enumerate(stages):
        for c in s.get("colors", []):
            first.setdefault(c["name"], i + 1)

    def closest(p: dict) -> str:
        m = p.get("mix") or {}
        if not m or m.get("reachable", True):
            return ""
        return (f'<span class="small warnc">Closest you can get from these tubes '
                f'<span class="dot" style="background:{e(m["mixed_hex"])}"></span>. Match the step picture as best you can.</span>')

    def when(name: str) -> str:
        return f"First needed in step {first[name]}" if name in first else ""

    paint_cards = "".join(
        f'<div class="paint"><span class="blob" style="background:{e(p["hex"])}"></span><div><b>{e(p["name"])}</b>'
        f'<span class="recipe">{e(p["recipe"])}</span><br><span class="small">{e(p.get("used_for", ""))}'
        f'{" · " + when(p["name"]) if when(p["name"]) else ""}</span>{closest(p)}</div></div>'
        for p in paints)
    from brushes import describe, picture
    brush_items = "".join(
        f'<li class="brush">{picture(b)}<div><b>{e(b)}</b>' + (f": {e(u)}" if u else "")
        + (f'<span class="small">{e(describe(b))}</span>' if describe(b) else "") + "</div></li>"
        for b, u in brushes.items())
    kit = (f'<div><p class="label">Tubes</p><ul>{items(tubes)}</ul></div>'
           f'<div><p class="label">Brushes</p><ul>{brush_items}</ul></div>'
           f'<div><p class="label">Also</p><ul><li>{e(canvas_item)}</li><li>Water jar and paper towel</li>'
           f'<li>Palette or paper plate for mixing</li></ul></div>')
    sizes = [dims(folder / s["image"]) for s in stages]
    strip = "".join(f'<a href="#step-{i + 1}"><img src="{thumbs[i]}"{sizes[i]} alt="" loading="lazy">Step {i + 1}</a>'
                    for i in range(len(stages)))

    steps_html = []
    for i, s in enumerate(stages):
        blist = s.get("brush_list") or ([{"brush": s["brushes"], "use": ""}] if s.get("brushes") else [])
        chips = "".join(f'<span class="chip" title="{e(describe(b["brush"]) or b.get("use", ""))}">{picture(b["brush"], "small")}'
                        f'{e(b["brush"])}</span>' for b in blist)
        strokes = "".join(f'<p class="stroke"><b>{e(t["name"])}.</b> {e(t["how"])}</p>' for t in s.get("strokes", []))
        used = [by_name[c["name"]] for c in s.get("colors", []) if c["name"] in by_name]
        fresh = [p for p in used if first.get(p["name"]) == i + 1]
        mix_rows = "".join(
            f'<li><span class="blob" style="background:{e(p["hex"])}"></span><div><b>{e(p["name"])}</b> '
            + ('<span class="new">new</span>' if first.get(p["name"]) == i + 1 else
               f'<span class="small">from step {first.get(p["name"])}, mix more if it has dried</span>')
            + f'<span class="recipe">{e(p["recipe"])}</span>{closest(p)}</div></li>' for p in used)
        dots = "".join(f'<span class="dot" style="background:{e(p["hex"])}"></span>' for p in used)
        mixes = (f'<details class="mixfor" open><summary><span class="label">Paints for this step</span>'
                 f'<span class="dots">{dots}</span>'
                 f'<span class="small">{len(used)} paint{"s" if len(used) != 1 else ""}'
                 f'{f", {len(fresh)} new" if fresh else ""}</span></summary><ul class="plain mixlist">{mix_rows}</ul></details>'
                 ) if used else ""
        vrows = "".join(
            f'<tr><th scope="row">{e(v.get("value", ""))}</th><td>'
            + (f'<span class="dot" style="background:{e(by_name[v["paint"]]["hex"])}"></span>' if v.get("paint") in by_name else "")
            + f'{e(v.get("paint", ""))}</td><td>{e(v.get("where", ""))}</td></tr>' for v in s.get("values", []))
        values = (f'<table class="values"><caption>Build the depth, dark first</caption><thead><tr><th>Value</th>'
                  f'<th>Paint</th><th>Where</th></tr></thead><tbody>{vrows}</tbody></table>') if vrows else ""
        notes = "".join(f'<p class="small">{e(n)}</p>' for n in s.get("paint_notes", []))
        watch = "".join(f'<p class="watch">Watch out: {e(w)}</p>' for w in s.get("watch_out", []))
        flags = "".join(f'<p class="flag">Heads up, this picture is a little off: {e(x)} Paint what the steps say.</p>'
                        for x in left.get(s["id"], []))
        steps_html.append(f"""
<article class="step" id="step-{i + 1}">
  <figure><img src="{imgs[i]}"{sizes[i]} alt="The canvas after step {i + 1}: {e(s['name'])}" loading="lazy"></figure>
  <div class="text">
    <div><p class="num">STEP {i + 1} OF {len(stages)}</p><h3>{e(s['name'])}</h3></div>
    <ol class="do">{items(s['steps'])}</ol>
    {values}{mixes}{notes}
    <div class="tools">
      <p class="label">Brushes</p><div class="chips">{chips}</div>
      {f'<p class="label">Strokes</p>{strokes}' if strokes else ''}
    </div>
    {watch}{flags}
    <p class="small">Drying: {e(s.get('dry_time', ''))}</p>
    {step_why(lesson, s, i == len(stages) - 1)}
  </div>
  {build_strip(s.get('construct'), {n: p['hex'] for n, p in by_name.items()}, s['id'])}
</article>""")

    head = (f'<title>{e(title_for(lesson, folder))}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            f'{FONTS}\n<style>{STYLE}</style>')
    body = f"""
<div class="wrap">
  <header>
    <p class="eyebrow">Acrylic paint-along · {e(technique.get('level', 'beginner'))}</p>
    <h1>{e(read['subject'])}</h1>
    <p class="lede">{e(technique.get('summary', ''))}</p>
    <div class="facts"><span><b>{len(stages)}</b> steps</span>{f'<span>Canvas: <b>{cv["w_in"]:g} x {cv["h_in"]:g} in</b></span>' if cv else ''}<span>Focal point: <b>{e(read['focal_point'])}</b></span>
      <span>Light: <b>{e(read['light'])}</b></span><a href="#behind">How this lesson was made</a></div>
  </header>
  <div class="pair">
    {f'<figure><img src="{photo}"{dims(folder / lesson["photo_file"])} alt="The original photo"><figcaption>Your photo</figcaption></figure>' if photo else ''}
    <figure><img src="{finish}"{sizes[-1]} alt="The finished painting"><figcaption>Where you'll end up</figcaption></figure>
  </div>
  <section><h2>What you need</h2><div class="kit">{kit}</div></section>
  <section><h2>Your paints</h2><p class="small">Every paint in the lesson. You don't have to mix them all at the start: each step lists
    the paints it uses with their recipes, so you can mix a little as you go before it dries. Parts are by volume.</p>
    <div class="paints">{paint_cards}</div></section>
  <section><h2>The steps</h2><nav class="strip" aria-label="Jump to a step">{strip}</nav></section>
  {''.join(steps_html)}
  {behind(lesson, technique, folder, embed, thumbs, sizes)}
  {f'<footer class="made">Made with {e(line(lesson["gesso"]))}</footer>' if lesson.get("gesso") else ""}
</div>"""
    if embed:
        return head + body
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">{head}</head><body>{body}</body></html>'
