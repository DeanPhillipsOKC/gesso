"""Stroke cards and basics cards: how to do a stroke, written once and checked by the owner (pipeline v2,
docs/design/pipeline-v2.md section 10).

    strokes() -> {id: card}        techniques/strokes/*.yaml
    basics()  -> {id: card}        techniques/basics/*.yaml
    problems() -> what's wrong with the cards, each naming the file (empty when they're fine)
    page()    -> one HTML page of every card, for the owner to read

How to load the brush, how thick the paint, the motion, what it leaves, and what goes wrong used to be written
fresh by Claude in every lesson, in a sentence or two, differently each time. A card says it once, from the
research file with its sources, and a lesson shows the card. A field the research doesn't cover is left out, never
filled in from memory (docs/decisions.md, 2026-11-11 and 2026-11-12).
"""

from __future__ import annotations

from html import escape as e
from pathlib import Path

import brushes
import construct
import yaml_files

ROOT = Path(__file__).resolve().parent.parent
STROKES = ROOT / "techniques" / "strokes"
BASICS = ROOT / "techniques" / "basics"
TECHNIQUE = ROOT / "techniques" / "acrylic-paint-along-beginner.yaml"
STROKE_NEEDS = ("id", "stroke_result", "name", "result", "sources", "checked")
BASIC_NEEDS = ("id", "name", "when", "lines", "sources", "checked")
TEXT_FIELDS = (("load", "Load"), ("motion", "Motion"), ("result", "What it leaves"), ("then", "Then"))


def _load(folder: Path) -> dict[str, dict]:
    out = {}
    for path in sorted(folder.glob("*.yaml")):
        card = yaml_files.read(path) or {}
        card["_file"] = str(path.relative_to(ROOT))
        out[card.get("id", path.stem)] = card
    return out


def strokes() -> dict[str, dict]:
    return _load(STROKES)


def basics() -> dict[str, dict]:
    return _load(BASICS)


def stroke_results(technique: Path = TECHNIQUE) -> list[str]:
    return [r["stroke"] for r in yaml_files.read(technique).get("stroke_results") or []]


def problems(stroke_cards: dict | None = None, basic_cards: dict | None = None, results: list[str] | None = None) -> list[str]:
    stroke_cards = strokes() if stroke_cards is None else stroke_cards
    basic_cards = basics() if basic_cards is None else basic_cards
    results = stroke_results() if results is None else results
    out = []
    covered = set()
    for cid, c in stroke_cards.items():
        f = c.get("_file", cid)
        for key in STROKE_NEEDS:
            if c.get(key) in (None, "", []):
                out.append(f"{f}: no {key}")
        if Path(f).stem != cid and "_file" in c:
            out.append(f"{f}: its id is {cid!r}; the file name and the id must match")
        if c.get("stroke_result") and c["stroke_result"] not in results:
            out.append(f"{f}: stroke_result isn't an entry of the technique's stroke_results, word for word")
        covered.add(c.get("stroke_result"))
        for b in c.get("brushes") or []:
            if not brushes.kind(b):
                out.append(f"{f}: brush {b!r} isn't one spike/brushes.py can draw")
        if c.get("diagram") and not construct.strip(c["diagram"], {}, f"card-{cid}"):
            out.append(f"{f}: its diagram doesn't draw (see spike/construct.py for the format)")
        out += construct.problems(c.get("diagram"), {}, f)  # a card has no plan paints: #hex only
        if not c.get("diagram"):
            out.append(f"{f}: no diagram")
        for m in c.get("mistakes") or []:
            if not m.get("mistake") or not m.get("fix"):
                out.append(f"{f}: every mistake needs 'mistake' and 'fix'")
    for r in results:
        if r not in covered:
            out.append(f"no stroke card for the technique's stroke result {r!r}")
    for cid, c in basic_cards.items():
        f = c.get("_file", cid)
        for key in BASIC_NEEDS:
            if c.get(key) in (None, "", []):
                out.append(f"{f}: no {key}")
        if c.get("when") and c["when"] not in WHEN:
            out.append(f"{f}: when {c['when']!r} isn't one of {', '.join(WHEN)}")
        if c.get("fold") and c.get("when") != "start":
            out.append(f"{f}: only a start card can be folded")
    return out


# --- Where each basics card shows (#95) -----------------------------------------------------------------------------
# A basics card shows once: in "Before you start" (`when: start`), or open in the step where it first matters. Every
# moment is found from what lesson.json's stages already say (show, part, group, paints, lines, aids area), so the
# page and `check` find the same step, with no image work.

WHEN = {
    "start": "in Before you start",
    "first_layer": "the first step that paints over an earlier step's paint (a dry line, or a pass on its own part)",
    "light_over_dark": "the first step with a coats line: a paint much lighter than what it goes over",
    "first_tint": "the first step using a tint or shade of another paint",
    "first_big_coat": "the first coat (flat, full, or blend) over a big area",
    "first_light_value": "the first pass lighter than everything its part had before",
    "midway": "the first stage that starts halfway through the lesson or later",
}
NEEDED = ("first_layer", "midway")  # every lesson of two steps or more has these: a card for one must find its step
BIG_COAT = 0.15  # a coat over at least this share of the canvas (aids area) is a big area
COATS = ("flat", "full", "blend")


def _kinds(s: dict) -> set[str]:
    return {x.get("kind") for x in s.get("lines") or []}


def _lightest(s: dict) -> float | None:
    import paints

    ls = [paints.lightness(c["hex"]) for c in s.get("colors") or [] if c.get("hex")]
    return max(ls) if ls else None


def moment(when: str, stages: list[dict]) -> int | None:
    """The step (0-based) where a `when` moment first comes in these lesson.json stages; None when it never does."""
    def first(test) -> int | None:
        return next((i for i, s in enumerate(stages) if test(i, s)), None)

    def earlier_own(i: int) -> list[dict]:
        return [t for t in stages[:i] if t.get("part") == stages[i].get("part")]

    if when == "first_layer":
        return first(lambda i, s: "dry" in _kinds(s) or (s.get("show") == "pass" and earlier_own(i)))
    if when == "light_over_dark":
        return first(lambda i, s: "coats" in _kinds(s))
    if when == "first_tint":
        return first(lambda i, s: any(c.get("of") for c in s.get("colors") or []))
    if when == "first_big_coat":
        if any("area" in (s.get("aids") or {}) for s in stages):
            return first(lambda i, s: s.get("show") in COATS and (s.get("aids") or {}).get("area", 0) >= BIG_COAT)
        return first(lambda i, s: s.get("show") in COATS)  # no step aids yet: the first coat
    if when == "first_light_value":
        def lighter(i, s):
            mine = _lightest(s)
            before = [x for t in earlier_own(i) if (x := _lightest(t)) is not None]
            return s.get("show") == "pass" and mine is not None and bool(before) and mine > max(before)
        return first(lighter)
    if when == "midway":
        if len(stages) < 2:
            return None
        half = len(stages) // 2
        starts = [i for i, s in enumerate(stages) if i == 0 or s.get("group") != stages[i - 1].get("group")]
        return next((i for i in starts if i >= half), half)
    return None


def places(stages: list[dict], basic_cards: dict | None = None) -> dict[str, int | str]:
    """{basics card id: "start", or the step (0-based) it shows in}. A card whose moment never comes is left out."""
    basic_cards = basics() if basic_cards is None else basic_cards
    out: dict[str, int | str] = {}
    for cid, c in basic_cards.items():
        when = c.get("when")
        if when == "start":
            out[cid] = "start"
        elif when in WHEN and (i := moment(when, stages)) is not None:
            out[cid] = i
    return out


def unplaced(stages: list[dict], basic_cards: dict | None = None) -> list[str]:
    """`check`'s problems: a basics card this lesson should show (its moment comes in every lesson) with no step for it."""
    basic_cards = basics() if basic_cards is None else basic_cards
    if len(stages) < 2:
        return []
    got = places(stages, basic_cards)
    return [f"basics card {cid} shows at {WHEN[c['when']]}, and no step is that, so its card isn't shown. Check the "
            "steps' show and paints in plan.json, then run draft-text again."
            for cid, c in basic_cards.items() if c.get("when") in NEEDED and cid not in got]


def stroke_html(card: dict, uid: str = "") -> str:
    """One stroke card as HTML: the lesson page and the owner's review page both use it."""
    rows = "".join(f"<p><b>{label}.</b> {e(str(card[key]))}</p>" for key, label in TEXT_FIELDS if card.get(key))
    tools = [*(card.get("brushes") or []), *(card.get("tools") or [])]
    pics = "".join(brushes.picture(b, "small") for b in card.get("brushes") or [])
    head = f"<h3>{e(card['name'])}"
    if card.get("also_called"):
        head += f" <span class='aka'>also called {e(', '.join(card['also_called']))}</span>"
    head += "</h3>"
    if not card.get("checked"):
        head += "<p class='unchecked'>Not checked yet</p>"
    with_ = f"<p><b>With.</b> {pics} {e('; '.join(tools))}</p>" if tools else ""
    uses = f"<p><b>Good for.</b> {e(', '.join(card['uses']))}</p>" if card.get("uses") else ""
    wrong = ""
    for m in card.get("mistakes") or []:
        why = f" {e(m['why'])}" if m.get("why") else ""
        wrong += f"<li><b>{e(m['mistake'])}</b>{why} <i>{e(m['fix'])}</i></li>"
    wrong = f"<p><b>If it goes wrong.</b></p><ul>{wrong}</ul>" if wrong else ""
    extra = "".join(f"<p class='note'>{e(card[k])}</p>" for k in ("practice", "note") if card.get(k))
    diagram = construct.strip(card.get("diagram") or {}, {}, f"card-{uid or card['id']}")
    return f"<section class='card' id='stroke-{e(card['id'])}'>{head}{with_}{rows}{uses}{diagram}{wrong}{extra}</section>"


def basic_html(card: dict) -> str:
    lines = "".join(f"<li>{e(x)}</li>" for x in card.get("lines") or [])
    flag = "" if card.get("checked") else "<p class='unchecked'>Not checked yet</p>"
    return f"<section class='card' id='basic-{e(card['id'])}'><h3>{e(card['name'])}</h3>{flag}<ul>{lines}</ul></section>"


STYLE = """
:root{--ink:#22262b;--muted:#6b7480;--rule:#d9dde3;--ultramarine:#2b4bbd;--r-seeded:#a0622d;--bg:#fbfaf7}
body{font:16px/1.5 system-ui,sans-serif;color:var(--ink);background:var(--bg);max-width:720px;margin:0 auto;padding:16px}
h1{font-size:1.5rem} h2{margin-top:2rem;border-bottom:1px solid var(--rule)} h3{margin:.2rem 0}
.card{border:1px solid var(--rule);border-radius:8px;padding:12px 16px;margin:14px 0;background:#fff}
.card p{margin:.35rem 0} .aka,.src{color:var(--muted);font-weight:400;font-size:.85rem}
.unchecked{display:inline-block;background:#fff3cd;border-radius:4px;padding:0 6px;font-size:.8rem}
.note{color:var(--muted)} .panels{display:flex;gap:10px;flex-wrap:wrap} .panel{margin:0;width:150px}
.panel svg{width:150px;height:150px;border:1px solid var(--rule);border-radius:6px;background:#f6f4ee}
.panel figcaption,.small,.label{font-size:.85rem} .brushpic.sm{height:18px;vertical-align:middle}
"""


def page() -> str:
    """Every card on one page, with each card's sources and the gaps, for the owner to check."""
    s, b = strokes(), basics()
    wrong = problems(s, b)
    parts = ["<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
             f"<title>Gesso cards</title><style>{STYLE}</style><h1>Stroke cards and basics cards</h1>",
             "<p>Each card is built only from the research file and the technique file. A field the research doesn't "
             "cover is left out. Read each one; when it's right, set <code>checked: true</code> in its file.</p>"]
    if wrong:
        parts.append("<h2>Problems</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in wrong) + "</ul>")
    parts.append(f"<h2>Basics ({len(b)})</h2>")
    for c in b.values():
        parts.append(basic_html(c) + f"<p class='src'>{e(c['_file'])}. From: {e('; '.join(c.get('sources') or []))}</p>")
    parts.append(f"<h2>Strokes ({len(s)})</h2>")
    for c in s.values():
        missing = [label for key, label in (("brushes", "brush"), ("load", "load"), ("motion", "motion"), ("mistakes", "mistakes"))
                   if not c.get(key) and not (key == "brushes" and c.get("tools"))]
        gaps = f" Not in the research, so left out: {', '.join(missing)}." if missing else ""
        parts.append(stroke_html(c) + f"<p class='src'>{e(c['_file'])}. From: {e('; '.join(c.get('sources') or []))}.{e(gaps)}</p>")
    return "".join(parts)
