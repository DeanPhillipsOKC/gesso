"""The version 2 parts of the lesson page (pipeline v2, docs/design/pipeline-v2.md section 11). lesson_page.page
calls these for a lesson.json with "plan_version": 2; a version 1 page never reaches this file.

    sprite(lesson, folder, embed)           -> every step picture once, for the Where and Result views to share
    contents(lesson)                        -> the stages, each with its step count
    before_you_start(lesson, folder, embed) -> basics cards, the tape marks, the transfer outline, strokes to try
    step(lesson, i, parts)                  -> one step: the Where / Result switch, its lines, paints, and folds

A step's Where view is the picture before it with this step's area outlined (aids/aids.json, from step-aids),
drawn as SVG over the previous step's picture, so it costs no image of its own: each step picture is put in the
page once (in the sprite) and both views point at it. The switch is two radio buttons and CSS, no script.
"""

from __future__ import annotations

import base64
from html import escape as e
from pathlib import Path

import cards

CANVAS = "#faf9f5"  # from_finish.CANVAS: the bare canvas before step 1
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
PICTURE_PX = 900  # step pictures on the page, at most this many pixels on the long side
OPEN_CLOSE_UP = 0.03  # a close-up starts open when the step's area is under this share: too small to see otherwise

STYLE = """
/* Version 2: where this step's paint goes, close-ups, paint maps, cards, and stopping places. */
.sprite{position:absolute;width:0;height:0;overflow:hidden}
.sw{position:relative;display:grid;gap:.5rem;min-width:0}
.sw>input{position:absolute;opacity:0;pointer-events:none;width:1px;height:1px}
.sw-tabs{display:flex;gap:.25rem;background:var(--panel);border-radius:999px;padding:.2rem;justify-self:start}
.sw-tabs label{font:600 .85rem/1 var(--body);padding:.45rem .95rem;border-radius:999px;cursor:pointer;color:var(--muted)}
.sw-w:checked~.sw-tabs .lw,.sw-r:checked~.sw-tabs .lr{background:var(--ultramarine);color:var(--gesso)}
.sw-w:focus-visible~.sw-tabs .lw,.sw-r:focus-visible~.sw-tabs .lr{outline:2px solid var(--ultramarine);outline-offset:2px}
.sw-r:checked~.sw-where,.sw-w:checked~.sw-res{display:none}
svg.pic{width:100%;height:auto;display:block;border-radius:4px;border:1px solid var(--rule);background:#faf9f5}
.area-halo{fill:none;stroke:#fff;stroke-width:5;stroke-linejoin:round;vector-effect:non-scaling-stroke}
.area-line{fill:none;stroke:#111;stroke-width:2;stroke-linejoin:round;vector-effect:non-scaling-stroke}
.grid4{fill:none;stroke:#1d2430;stroke-opacity:.45;stroke-width:1;stroke-dasharray:6 5;vector-effect:non-scaling-stroke}
.grid2{fill:none;stroke:#1d2430;stroke-opacity:.6;stroke-width:1.4;vector-effect:non-scaling-stroke}
.grid8{fill:none;stroke:#1d2430;stroke-opacity:.35;stroke-width:1;stroke-dasharray:3 4;vector-effect:non-scaling-stroke}
.where-words{font-size:.92rem;color:var(--ink)}
.where-words b{font-family:var(--display)}
.tip{border-left:3px solid var(--r-filter);padding:.3rem .75rem;background:var(--panel);border-radius:0 6px 6px 0}
details.aid{background:var(--panel);border-radius:6px;padding:.6rem 1rem;min-width:0}
details.aid>summary{display:grid;grid-template-columns:1rem 1fr;align-items:baseline;gap:.1rem .6rem;font:600 .95rem/1.3 var(--body)}
details.aid>summary::before{content:"+";font:600 .95rem/1 var(--mono);color:var(--ultramarine);text-align:center}
details.aid>summary .small{grid-column:2}
details[open].aid>summary::before{content:"\\2212"}
details.aid>summary .small{font-weight:400}
.aid-body{display:grid;gap:.75rem;padding-top:.75rem;min-width:0}
.twin{display:grid;grid-template-columns:1fr 1fr;gap:.6rem}
.twin figcaption{font-weight:600}
ol.legend{list-style:none;margin:0;padding:0;display:grid;gap:.35rem}
ol.legend li{display:flex;align-items:center;gap:.5rem;font-size:.92rem}
.badge{display:inline-grid;place-items:center;width:1.5rem;height:1.5rem;border-radius:50%;background:#1d2430;color:#fff;
  font:700 .78rem/1 var(--mono);flex:none}
.mapnum circle{fill:#1d2430;stroke:#fff;stroke-width:2;vector-effect:non-scaling-stroke}
.mapnum text{fill:#fff;font:700 15px/1 var(--mono);text-anchor:middle;dominant-baseline:central}
.aid .card{background:var(--gesso);border:1px solid var(--rule);border-radius:8px;padding:.9rem;display:grid;gap:.45rem;min-width:0}
.aid .card h3{font-size:1.1rem}
.aid .card .brushpic{display:inline-block;vertical-align:middle;margin-right:.3rem}
.aid .panels{grid-template-columns:repeat(auto-fill, minmax(6.5rem, 1fr))}
.aid .build{padding:.75rem}
.aid .card ul{margin:0;padding-left:1.2rem;display:grid;gap:.3rem}
.aid .card .aka{font:400 .85rem/1.3 var(--body);color:var(--muted)}
.aid .card .note{color:var(--muted);font-size:.92rem}
.unchecked{justify-self:start;font:600 .72rem/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--warn);
  border:1px dashed currentColor;border-radius:3px;padding:.25rem .45rem}
.strokelink{font-size:.92rem}.strokelink a,.toc a,.start a{color:var(--ultramarine)}
.stop{display:flex;align-items:center;gap:.75rem;font:500 1.3rem/1.2 var(--hand);color:var(--stamp);margin-top:-1rem}
.stop::before,.stop::after{content:"";flex:1;border-top:2px dashed var(--rule)}
nav.toc ol{margin:0;padding-left:1.4rem;display:grid;gap:.35rem}
nav.toc li span{color:var(--muted);font-size:.9rem}
.start{display:grid;gap:1rem}
.start .basics{display:grid;gap:.5rem;grid-template-columns:repeat(auto-fill, minmax(min(100%, 18rem), 1fr));align-items:start}
.tape{display:grid;grid-template-columns:minmax(0, 14rem) 1fr;gap:1rem;align-items:center}
.tape svg{width:100%;height:auto}
.transfer{display:grid;grid-template-columns:minmax(0, 1fr) minmax(0, 1fr);gap:1rem;align-items:start}
ul.strokes{margin:0;padding-left:1.2rem;display:grid;gap:.4rem}
@media (max-width: 760px){.tape,.transfer{grid-template-columns:1fr}.tape svg{max-width:16rem}}
.p-cut{background:var(--r-filter);color:var(--gesso)}.t-cut{color:var(--r-filter)}
"""


def aid_src(folder: Path, rel: str, embed: bool) -> str:
    """A teaching picture as the page refers to it: its path, or inlined with its own format kept (a paint map
    stays an indexed PNG)."""
    if not embed:
        return e(rel)
    path = folder / rel
    return f"data:{MIME.get(path.suffix.lower(), 'image/png')};base64," + base64.b64encode(path.read_bytes()).decode()


def view_of(lesson: dict) -> tuple[int, int]:
    v = (lesson.get("aids") or {}).get("view") or [1000, 786]
    return int(v[0]), int(v[1])


def sprite(lesson: dict, folder: Path, embed: bool) -> str:
    """Every step picture once, at page coordinates, for the views to <use>."""
    from lesson_page import image_src

    w, h = view_of(lesson)
    pics = "".join(f'<image id="pic-{i + 1}" width="{w}" height="{h}" preserveAspectRatio="none" '
                   f'href="{image_src(folder, s["image"], embed, PICTURE_PX)}"/>' for i, s in enumerate(lesson["stages"]))
    return f'<svg class="sprite" aria-hidden="true" focusable="false"><defs>{pics}</defs></svg>'


def _grid(w: int, h: int, n: int, x0: float = 0, y0: float = 0, x1: float | None = None, y1: float | None = None) -> str:
    """Lines at every 1/n of the canvas (halves drawn stronger), clipped to a box in page coordinates."""
    x1, y1 = w if x1 is None else x1, h if y1 is None else y1
    weak, strong = [], []
    for k in range(1, n):
        (strong if 2 * k == n else weak).append((k * w / n, k * h / n))
    def d(lines):
        return "".join(f"M{x:.1f} {y0}V{y1}" for x, _ in lines if x0 < x < x1) + \
               "".join(f"M{x0} {y:.1f}H{x1}" for _, y in lines if y0 < y < y1)
    cls = "grid4" if n == 4 else "grid8"
    return f'<path class="{cls}" d="{d(weak)}"/><path class="grid2" d="{d(strong)}"/>'


def _outline(path: str) -> str:
    return (f'<path class="area-halo" fill-rule="evenodd" d="{path}"/>'
            f'<path class="area-line" fill-rule="evenodd" d="{path}"/>') if path else ""


def where_view(lesson: dict, i: int) -> str:
    """The picture before step i (0-based), dimmed except where this step paints, the area outlined, and the
    quarter grid that matches the tape on the canvas's edges."""
    w, h = view_of(lesson)
    a = lesson["stages"][i].get("aids") or {}
    path = a.get("path", "")
    n = i + 1
    before = f'<use href="#pic-{i}"/>' if i else f'<rect width="{w}" height="{h}" fill="{CANVAS}"/>'
    hole = f'<path d="{path}" fill="#000" fill-rule="evenodd"/>' if path else ""
    return (f'<svg class="pic" viewBox="0 0 {w} {h}" role="img" aria-label="Where step {n} goes: the canvas before it, '
            f'with this step\'s area outlined">'
            f'<defs><mask id="m-{n}"><rect width="{w}" height="{h}" fill="#fff"/>{hole}</mask></defs>{before}'
            f'<rect width="{w}" height="{h}" fill="#fff" fill-opacity=".6" mask="url(#m-{n})"/>'
            f'{"" if i or not path else _tint(path)}{_grid(w, h, 4)}{_outline(path)}</svg>')


def _tint(path: str) -> str:
    """On the bare canvas (step 1) dimming shows nothing, so the area is tinted instead."""
    return f'<path d="{path}" fill="#2944a8" fill-opacity=".14" fill-rule="evenodd"/>'


def result_view(lesson: dict, i: int) -> str:
    w, h = view_of(lesson)
    s = lesson["stages"][i]
    return (f'<svg class="pic" viewBox="0 0 {w} {h}" role="img" aria-label="The canvas after step {i + 1}: {e(s["name"])}">'
            f'<use href="#pic-{i + 1}"/></svg>')


def switch(lesson: dict, i: int) -> str:
    n = i + 1
    a = lesson["stages"][i].get("aids") or {}
    if not a:  # no step-aids yet: the canvas after the step, as version 1 shows it
        return f'<figure>{result_view(lesson, i)}</figure>'
    said = any(x.get("kind") == "where" for x in lesson["stages"][i].get("lines") or [])  # drafted text says it
    words = f'<p class="where-words"><b>Where:</b> {e(a["where_words"])}</p>' if a.get("where_words") and not said else ""
    return (f'<div class="sw"><input type="radio" class="sw-w" name="v{n}" id="v{n}w" checked>'
            f'<input type="radio" class="sw-r" name="v{n}" id="v{n}r">'
            f'<div class="sw-tabs"><label class="lw" for="v{n}w">Where</label><label class="lr" for="v{n}r">Result</label></div>'
            f'<div class="sw-where">{where_view(lesson, i)}</div><div class="sw-res">{result_view(lesson, i)}</div>'
            f'{words}</div>')


def fold(title: str, hint: str, body: str, open_: bool = False, cls: str = "") -> str:
    return (f'<details class="aid{" " + cls if cls else ""}"{" open" if open_ else ""}><summary>{e(title)}'
            f'{f" <span class=small>{e(hint)}</span>" if hint else ""}</summary><div class="aid-body">{body}</div></details>')


def closeup(lesson: dict, i: int, folder: Path, embed: bool) -> str:
    c = (lesson["stages"][i].get("aids") or {}).get("closeup")
    if not c:
        return ""
    w, h = view_of(lesson)
    x0, y0, x1, y1 = c["box"]
    path = (lesson["stages"][i].get("aids") or {}).get("path", "")

    def fig(src: str, label: str, line: bool) -> str:
        return (f'<figure><svg class="pic" viewBox="{x0} {y0} {x1 - x0} {y1 - y0}" role="img" aria-label="{label}, up close">'
                f'<image x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" preserveAspectRatio="none" '
                f'href="{aid_src(folder, src, embed)}"/>{_grid(w, h, 8, x0, y0, x1, y1)}'
                f'{_outline(path) if line else ""}</svg><figcaption>{label}</figcaption></figure>')
    body = (f'<div class="twin">{fig(c["before"], "Before", True)}{fig(c["after"], "After", False)}</div>'
            '<p class="small">The dotted lines are eighths of the canvas: halfway between the tape marks.</p>')
    small = (lesson["stages"][i].get("aids") or {}).get("area", 1) < OPEN_CLOSE_UP
    return fold("Close-up", "before and after", body, open_=small)


def paint_map(lesson: dict, i: int, folder: Path, embed: bool) -> str:
    s = lesson["stages"][i]
    m = (s.get("aids") or {}).get("map")
    if not m:
        return ""
    mw, mh = m["size"]
    r = max(11, round(0.03 * max(mw, mh)))
    nums = "".join(f'<g class="mapnum"><circle cx="{x["at"][0]}" cy="{x["at"][1]}" r="{r}"/>'
                   f'<text x="{x["at"][0]}" y="{x["at"][1]}" font-size="{round(r * 1.3)}">{x["n"]}</text></g>'
                   for x in m["legend"] if x.get("at"))
    legend = "".join(f'<li><span class="badge">{x["n"]}</span><span class="dot" style="background:{e(x["hex"])}"></span>'
                     f'{e(x["name"])}{"" if x.get("at") else " <span class=small>(only a few touches)</span>"}</li>'
                     for x in m["legend"])
    what = (f"Which paint goes where on {s['paints']}, across all its steps." if m.get("of") == "part"
            else "Which of this step's paints goes where.")
    order = " Top to bottom, as the blend goes on." if s.get("show") == "blend" else " Numbered in the order they go on."
    body = (f'<figure><svg class="pic" viewBox="0 0 {mw} {mh}" role="img" aria-label="Paint map">'
            f'<image width="{mw}" height="{mh}" href="{aid_src(folder, m["image"], embed)}" style="image-rendering:pixelated"/>'
            f'{nums}</svg></figure><p class="small">{e(what + order)}</p><ol class="legend">{legend}</ol>')
    return fold("Paint map", f"{len(m['legend'])} paints", body)


def first_uses(lesson: dict) -> dict[str, int]:
    """{stroke card id: the step (0-based) that first uses it}: where its card is shown open."""
    out: dict[str, int] = {}
    for i, s in enumerate(lesson["stages"]):
        for c in s.get("stroke_cards") or []:
            out.setdefault(c, i)
    return out


def stroke_folds(lesson: dict, i: int, known: dict) -> str:
    s = lesson["stages"][i]
    first = first_uses(lesson)
    out = []
    for c in s.get("stroke_cards") or []:
        card = known.get(c)
        if not card:
            continue
        if first[c] == i:
            hint = "how to do it" + ("" if card.get("checked") else ", not checked yet")
            out.append(fold(f"Stroke: {card['name']}", hint, cards.stroke_html(card, f"{c}-{i + 1}"), open_=True, cls="stroke"))
        else:
            out.append(f'<p class="strokelink">Stroke: <a href="#stroke-{e(c)}">{e(card["name"])}</a>, '
                       f'as in step {first[c] + 1}.</p>')
    for t in s.get("strokes") or []:  # a stroke with no card yet: its name only
        if not any(known.get(c, {}).get("name") == t["name"] for c in s.get("stroke_cards") or []):
            out.append(f'<p class="strokelink">Stroke: {e(t["name"])} <span class="unchecked">No card yet</span></p>')
    return "".join(out)


def step(lesson: dict, i: int, folder: Path, embed: bool, known: dict, mixes: str, chips: str, why: str,
         diagram: str) -> str:
    """One step of a version 2 lesson: the picture with its Where / Result switch, then what to do, its paints and
    brushes, and the folds (close-up, paint map, stroke card, diagram)."""
    s = lesson["stages"][i]
    stages = lesson["stages"]
    group = next((g for g in lesson.get("groups") or [] if s["id"] in g["steps"]), None)
    where_in = (f' · {e(group["name"])}, {group["steps"].index(s["id"]) + 1} of {len(group["steps"])}' if group else "")
    lines = s.get("lines") or []
    do = f'<ol class="do">{"".join(f"<li>{e(x["text"])}</li>" for x in lines)}</ol>' if lines else ""
    tip = f'<p class="tip"><b>Tip:</b> {e(s["tip"])}</p>' if s.get("tip") else ""
    el = s.get("element") or {}
    if el.get("drafted"):  # a technique drafted for this lesson, not in the hand-checked library yet (#12)
        tip += (f'<p class="strokelink">Technique: {e(el.get("name", ""))} '
                '<span class="unchecked">Technique not checked yet</span></p>')
    folds = "".join([closeup(lesson, i, folder, embed), paint_map(lesson, i, folder, embed), stroke_folds(lesson, i, known),
                     fold("Diagram", "how to build the shape", diagram) if diagram else ""])
    return f"""
<article class="step" id="step-{i + 1}">
  {switch(lesson, i)}
  <div class="text">
    <div><p class="num">STEP {i + 1} OF {len(stages)}{where_in}</p><h3>{e(s['name'])}</h3></div>
    {do}{tip}{mixes}
    <div class="tools"><p class="label">Brushes</p><div class="chips">{chips}</div></div>
    {folds}
    <p class="small">Drying: {e(s.get('dry_time', ''))}</p>
    {why}
  </div>
</article>"""


def stop(group: dict) -> str:
    return f'<p class="stop" role="note">End of {e(group["name"])}: a good place to stop</p>'


def contents(lesson: dict) -> str:
    num = {s["id"]: i + 1 for i, s in enumerate(lesson["stages"])}
    rows = []
    for g in lesson.get("groups") or []:
        if not g.get("steps"):
            continue
        a, b = num[g["steps"][0]], num[g["steps"][-1]]
        n = len(g["steps"])
        rows.append(f'<li><a href="#stage-{e(g["id"])}">{e(g["name"])}</a> <span>{n} step{"s" if n != 1 else ""}, '
                    f'{"step " + str(a) if a == b else f"steps {a} to {b}"}</span></li>')
    return f'<nav class="toc" aria-label="Stages"><ol>{"".join(rows)}</ol></nav>' if rows else ""


def _tape_svg() -> str:
    """A canvas with tape along its top and left edges, the halves and quarters marked."""
    marks = "".join(f'<path d="M{20 + k * 45} 6v12"/><path d="M6 {24 + k * 35}h12"/>' for k in (1, 3))
    halves = '<path d="M110 2v18" stroke-width="3"/><path d="M2 94h18" stroke-width="3"/>'
    return ('<svg viewBox="0 0 210 170" role="img" aria-label="Tape along the top and the side of the canvas, marked '
            'at the middle and the quarters"><rect x="20" y="24" width="180" height="140" fill="#fff" stroke="#9aa3b2"/>'
            '<rect x="20" y="4" width="180" height="16" fill="#e9dcb8"/><rect x="2" y="24" width="16" height="140" fill="#e9dcb8"/>'
            f'<g stroke="#1d2430" stroke-width="2">{marks}{halves}</g>'
            '<g stroke="#1d2430" stroke-opacity=".35" stroke-dasharray="4 4">'
            '<path d="M65 24v140M110 24v140M155 24v140M20 59h180M20 94h180M20 129h180"/></g></svg>')


def _measure(canvas: dict | None) -> str:
    if not canvas:
        return ""
    from aids import _inches
    w, h = float(canvas["w_in"]), float(canvas["h_in"])
    return (f" On your {w:g} x {h:g} in canvas the marks across the top are {_inches(w / 4, 0.25)} apart and the marks "
            f"down the side {_inches(h / 4, 0.25)} apart.")


def before_you_start(lesson: dict, folder: Path, embed: bool, known: dict) -> str:
    aids = lesson.get("aids") or {}
    tape = (f'<div class="tape">{_tape_svg()}<div><h3>Mark halves and quarters on tape</h3><p>Run a strip of masking tape '
            f'along the top edge of the canvas and one down a side, and mark the middle and the quarters on each.'
            f'{e(_measure(lesson.get("canvas")))} Every step\'s Where picture has the same lines, so you can find its '
            'place on your canvas. (Chalk lines on the canvas would be painted over by the first coat; the tape stays.)'
            '</p></div></div>')
    t = aids.get("transfer")
    transfer = ""
    if t and (folder / t["image"]).exists():
        names = "; ".join(f'{x["n"]} {x["name"]}' for x in t["parts"])
        transfer = (f'<div class="transfer"><figure><img src="{aid_src(folder, t["image"], embed)}" alt="Outlines of the '
                    f'main shapes on the quarter grid" loading="lazy"></figure><div><h3>The transfer outline (optional)</h3>'
                    f'<p>The outlines of the main shapes, on the same quarter grid as your tape: {e(names)}. Before the '
                    'stage that starts one, you can lightly chalk its outline on the canvas, using the tape marks to '
                    'place it.</p></div></div>')
    first = first_uses(lesson)
    tries = "".join(
        f'<li><a href="#stroke-{e(c)}">{e(known[c]["name"])}</a>, first in step {i + 1}.'
        + (f' {e(known[c]["practice"])}' if known[c].get("practice") else "") + "</li>"
        for c, i in sorted(first.items(), key=lambda x: x[1]) if c in known)
    strokes = (f'<div><h3>Strokes to try on scrap paper first</h3><p class="small">Each one\'s card is open in the step '
               f'that first uses it.</p><ul class="strokes">{tries}</ul></div>') if tries else ""
    basics = "".join(fold(c["name"], "" if c.get("checked") else "not checked yet", cards.basic_html(c))
                     for c in sorted(cards.basics().values(), key=lambda c: c["id"] != "set-up"))  # setting up first
    return (f'<section class="start" id="start"><h2>Before you start</h2>{tape}{transfer}{strokes}'
            f'<div><h3>The basics</h3><div class="basics">{basics}</div></div></section>')
