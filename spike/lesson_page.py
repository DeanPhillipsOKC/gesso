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
  --display:"Bricolage Grotesque", "Segoe UI", system-ui, sans-serif;
  --body:"Atkinson Hyperlegible", "Segoe UI", system-ui, sans-serif;
  --mono:"JetBrains Mono", ui-monospace, Consolas, monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --gesso:#14171c; --panel:#1c2027; --ink:#e7e9ee; --muted:#9aa3b2; --rule:#2c323c;
  --ultramarine:#93a8f4; --ultramarine-soft:#232c48; --warn:#e5a86b; color-scheme:dark}}
:root[data-theme="dark"]{
  --gesso:#14171c; --panel:#1c2027; --ink:#e7e9ee; --muted:#9aa3b2; --rule:#2c323c;
  --ultramarine:#93a8f4; --ultramarine-soft:#232c48; --warn:#e5a86b; color-scheme:dark}
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
.chip{background:var(--ultramarine-soft);color:var(--ink);border-radius:999px;padding:.2rem .7rem;font-size:.88rem}
.stroke b{color:var(--ultramarine)}
.mixes{display:flex;flex-wrap:wrap;gap:.5rem 1rem}
.mix{display:flex;align-items:center;gap:.4rem;font-size:.92rem}
.dot{width:1rem;height:1rem;border-radius:50%;border:1px solid var(--rule);flex:none}
.watch{color:var(--warn);font-size:.95rem}
.small{font-size:.85rem;color:var(--muted)}
.made{font:.75rem/1.4 var(--mono);color:var(--muted)}
.flag{border-left:3px solid var(--warn);padding:.4rem .75rem;font-size:.92rem;background:var(--panel)}
@media (max-width: 760px){.step,.pair{grid-template-columns:1fr}}
@media (prefers-reduced-motion: no-preference){html{scroll-behavior:smooth}}
"""

FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700'
         '&family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=JetBrains+Mono:wght@400;600&display=swap">')


def image_src(folder: Path, name: str, embed: bool, max_side: int = 900) -> str:
    if not embed:
        return e(name)
    img = ImageOps.exif_transpose(Image.open(folder / name)).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def title_for(lesson: dict) -> str:
    stem = Path(lesson["photo"]).stem.replace("-", " ").replace("_", " ").strip()
    return f"{stem.title()} Lesson"


def items(xs, cls="") -> str:
    return "".join(f"<li{f' class={cls}' if cls else ''}>{e(x)}</li>" for x in xs)


def page(lesson: dict, technique: dict, folder: Path, embed: bool = False) -> str:
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

    photo = image_src(folder, lesson["photo_file"], embed) if lesson.get("photo_file") else ""
    finish = image_src(folder, stages[-1]["image"], embed)
    imgs = [image_src(folder, s["image"], embed, 1000) for s in stages]
    thumbs = [image_src(folder, s["image"], embed, 200) for s in stages] if embed else imgs

    paint_cards = "".join(
        f'<div class="paint"><span class="blob" style="background:{e(p["hex"])}"></span><div><b>{e(p["name"])}</b>'
        f'<span class="recipe">{e(p["recipe"])}</span><br><span class="small">{e(p.get("used_for", ""))}</span></div></div>'
        for p in paints)
    brush_items = "".join(f"<li><b>{e(b)}</b>" + (f": {e(u)}" if u else "") + "</li>" for b, u in brushes.items())
    kit = (f'<div><p class="label">Tubes</p><ul>{items(tubes)}</ul></div>'
           f'<div><p class="label">Brushes</p><ul>{brush_items}</ul></div>'
           f'<div><p class="label">Also</p><ul><li>White canvas or canvas board</li><li>Water jar and paper towel</li>'
           f'<li>Palette or paper plate for mixing</li></ul></div>')
    strip = "".join(f'<a href="#step-{i + 1}"><img src="{thumbs[i]}" alt="" loading="lazy">Step {i + 1}</a>'
                    for i in range(len(stages)))

    steps_html = []
    for i, s in enumerate(stages):
        blist = s.get("brush_list") or ([{"brush": s["brushes"], "use": ""}] if s.get("brushes") else [])
        chips = "".join(f'<span class="chip" title="{e(b.get("use", ""))}">{e(b["brush"])}</span>' for b in blist)
        strokes = "".join(f'<p class="stroke"><b>{e(t["name"])}.</b> {e(t["how"])}</p>' for t in s.get("strokes", []))
        mixes = "".join(
            f'<span class="mix"><span class="dot" style="background:{e(by_name[c]["hex"])}"></span>{e(c)}</span>'
            for c in [c["name"] for c in s.get("colors", [])] if c in by_name)
        notes = "".join(f'<p class="small">{e(n)}</p>' for n in s.get("paint_notes", []))
        watch = "".join(f'<p class="watch">Watch out: {e(w)}</p>' for w in s.get("watch_out", []))
        flags = "".join(f'<p class="flag">Heads up, this picture is a little off: {e(x)} Paint what the steps say.</p>'
                        for x in left.get(s["id"], []))
        made = f'<p class="made">Image made with {e(s.get("made_with", "render"))}</p>' if not embed else ""
        steps_html.append(f"""
<article class="step" id="step-{i + 1}">
  <figure><img src="{imgs[i]}" alt="The canvas after step {i + 1}: {e(s['name'])}" loading="lazy"></figure>
  <div class="text">
    <div><p class="num">STEP {i + 1} OF {len(stages)}</p><h3>{e(s['name'])}</h3></div>
    <ol class="do">{items(s['steps'])}</ol>
    {f'<div class="mixes">{mixes}</div>' if mixes else ''}{notes}
    <div class="tools">
      <p class="label">Brushes</p><div class="chips">{chips}</div>
      {f'<p class="label">Strokes</p>{strokes}' if strokes else ''}
    </div>
    {watch}{flags}
    <p class="small">Drying: {e(s.get('dry_time', ''))}</p>{made}
  </div>
</article>""")

    head = (f'<title>{e(title_for(lesson))}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            f'{FONTS}\n<style>{STYLE}</style>')
    body = f"""
<div class="wrap">
  <header>
    <p class="eyebrow">Acrylic paint-along · {e(technique.get('level', 'beginner'))}</p>
    <h1>{e(read['subject'])}</h1>
    <p class="lede">{e(technique.get('summary', ''))}</p>
    <div class="facts"><span><b>{len(stages)}</b> steps</span><span>Focal point: <b>{e(read['focal_point'])}</b></span>
      <span>Light: <b>{e(read['light'])}</b></span></div>
  </header>
  <div class="pair">
    {f'<figure><img src="{photo}" alt="The original photo"><figcaption>Your photo</figcaption></figure>' if photo else ''}
    <figure><img src="{finish}" alt="The finished painting"><figcaption>Where you'll end up</figcaption></figure>
  </div>
  <section><h2>What you need</h2><div class="kit">{kit}</div></section>
  <section><h2>Your paints</h2><p class="small">Mix these from the tubes before you start. Parts are by volume.</p>
    <div class="paints">{paint_cards}</div></section>
  <section><h2>The steps</h2><nav class="strip" aria-label="Jump to a step">{strip}</nav></section>
  {''.join(steps_html)}
</div>"""
    if embed:
        return head + body
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">{head}</head><body>{body}</body></html>'
