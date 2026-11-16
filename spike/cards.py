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

import copy
import re
from html import escape as e
from pathlib import Path

import brushes
import construct
import loads
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
        out += loads.problems(c.get("load"), f)  # one vocabulary for how thick and how much (#99)
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
        for key, words in _technique_text(c):
            named = subjects(words)
            if named:
                out.append(f"{f}: its {key} names a subject ({', '.join(named)}). A card is shown on any painting, so "
                           "say only what the brush does and leaves, and move the example to uses.")
    for r in results:
        if r not in covered:
            out.append(f"no stroke card for the technique's stroke result {r!r}")
    for cid, c in basic_cards.items():
        f = c.get("_file", cid)
        for key in BASIC_NEEDS:
            if c.get(key) in (None, "", []):
                out.append(f"{f}: no {key}")
        if c.get("when") and (not isinstance(c["when"], str) or c["when"] not in WHEN):
            out.append(f"{f}: when {c['when']!r} isn't one of {', '.join(WHEN)}")
        if c.get("fold") and c.get("when") != "start":
            out.append(f"{f}: only a start card can be folded")
        if c.get("terms") is not None or cid == loads.CARD:
            out += _term_problems(c, f, basic_cards)
        for n, line in enumerate(c.get("lines") or []):
            named = subjects(str(line), basics=True)
            if named:
                out.append(f"{f}: line {n + 1} names a subject ({', '.join(named)}). A basics card is for every "
                           "painting: say it without one.")
    return out


# --- Cards say only the technique (#96) -----------------------------------------------------------------------------
# A card is shown on whatever is being painted, so its motion, result, then, and mistakes name no subject: on the
# chickadee's sun the small-circles card said it made "a cloud's bumpy top edge". Examples go in `uses`, and a lesson
# adapts the card's words to its own subject in text.json's card_text (below).

SUBJECT = re.compile(r"\b(clouds?|sky|skies|suns?|moons?|trees?|branch(?:es)?|grass(?:es)?|pumpkins?|flowers?|water|"
                     r"leaf|leaves|birds?)\b", re.I)
# water that thins paint or rinses a brush is a material, not a subject: "Add water.", "no water on the brush"
MATERIAL_WATER = re.compile(r"\b(?:add|adding|no|of|with|little|more|less|much|clean|dirty|rinse)\s+water\b|"
                            r"\bwater\s+(?:jars?|on the brush|to the brush)\b", re.I)


def subjects(text: str, basics: bool = False) -> list[str]:
    """The subject words (design section 10, #96) a card's text names, lowercased, each once. On a basics card water
    is always the material (water jars, how much water), never a subject."""
    text = MATERIAL_WATER.sub(" ", text)
    out = []
    for m in SUBJECT.finditer(text):
        w = m.group(1).lower()
        if (basics and w == "water") or w in out:
            continue
        out.append(w)
    return out


def _technique_text(card: dict) -> list[tuple[str, str]]:
    """(field, its words) for the fields a card's technique is in: motion, result, then, and each mistake."""
    out = [(k, str(card[k])) for k in ("motion", "result", "then") if card.get(k)]
    for n, m in enumerate(card.get("mistakes") or []):
        if isinstance(m, dict):
            out.append((f"mistake {n + 1}", " ".join(str(m.get(k) or "") for k in ("mistake", "why", "fix"))))
    return out


def _term_problems(card: dict, f: str, basic_cards: dict) -> list[str]:
    """The paint-load card (#99): one line and one picture for each of loads.TERMS, each once."""
    out = []
    terms = card.get("terms") or []
    got = [t.get("term") for t in terms if isinstance(t, dict)]
    for t in loads.TERMS:
        if got.count(t) != 1:
            out.append(f"{f}: term {t!r} shows {got.count(t)} times; every load term needs one line and one picture")
    for t in terms:
        if not isinstance(t, dict) or t.get("term") not in loads.TERMS:
            out.append(f"{f}: {t!r} isn't one of the load terms ({', '.join(loads.TERMS)})")
            continue
        if not t.get("line"):
            out.append(f"{f}: term {t['term']!r} has no line")
        if not loads.picture(t["term"]):
            out.append(f"{f}: term {t['term']!r} has no picture in spike/loads.py")
        if t.get("see") and t["see"] not in basic_cards:
            out.append(f"{f}: term {t['term']!r} points at basics card {t['see']!r}, which doesn't exist")
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
    "midway": "the stage start nearest the halfway step, never the first or last step",
}
NEEDED = ("first_layer",)  # nearly every lesson has this moment: check notes a lesson where its card finds no step
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
        starts = [i for i in range(1, len(stages) - 1) if stages[i].get("group") != stages[i - 1].get("group")]
        return min(starts, key=lambda i: (abs(i - half), i)) if starts else half  # one stage: the halfway step
    return None


def places(stages: list[dict], basic_cards: dict | None = None) -> dict[str, int | str]:
    """{basics card id: "start", or the step (0-based) it shows in}. A card whose moment never comes is left out."""
    basic_cards = basics() if basic_cards is None else basic_cards
    out: dict[str, int | str] = {}
    for cid, c in basic_cards.items():
        when = c.get("when")
        if not isinstance(when, str):
            continue  # cards.problems reports it
        if when == "start":
            out[cid] = "start"
        elif when in WHEN and (i := moment(when, stages)) is not None:
            out[cid] = i
    return out


def unplaced(stages: list[dict], basic_cards: dict | None = None) -> list[str]:
    """`check`'s notes: a basics card nearly every lesson shows (NEEDED) with no step for it. A note, not a failure: a
    lesson whose parts never overlap is fine, and only loses the card."""
    basic_cards = basics() if basic_cards is None else basic_cards
    if len(stages) < 2:
        return []
    got = places(stages, basic_cards)
    return [f"basics card {cid} shows at {WHEN[c['when']]}, and no step is that, so the page doesn't show it. If a "
            "step does paint over earlier paint, run draft-text again."
            for cid, c in basic_cards.items() if c.get("when") in NEEDED and cid not in got]


# --- A card adapted for one painting (#96) --------------------------------------------------------------------------
# text.json's card_text: {step id: {card id: {motion, result, then, mistakes, diagram, "from": card id}}}. `card-adapt`
# copies the general card's fields there for each card a step opens (the first step using it); the run then swaps
# the subject words and paints in step 6, keeping the technique. `adapted_problems` (run by `check`) reports one that
# drifted from its card: a field missing or added, more mistakes, a different brush, or a diagram with other stages.

ADAPT_FIELDS = ("motion", "result", "then", "mistakes", "diagram")
MISTAKE_KEYS = ("mistake", "why", "fix")
# brush words in a card's text, to catch an adapted card that names another brush ("with a fan brush")
BRUSH_WORDS = re.compile(r"\b(?:liner|rigger|filbert|fan|toothbrush|sponge|palette knife|"
                         r"(?:flat|round|angle|angled|bright|wash|stiff|soft) brush|#\d+\s+[a-z]+|"
                         r"\d+(?:/\d+)?\s+inch\s+[a-z]+)\b", re.I)


def opened(steps: list[dict], known: dict | None = None) -> list[tuple[str, str]]:
    """(step id, card id) for every card a lesson opens, in step order: the first step whose stroke is that card.
    Later steps with the same stroke link back to it, so that's the one step its card is adapted for."""
    known = strokes() if known is None else known
    out, seen = [], set()
    for s in steps:
        cid = s.get("stroke")
        if cid in known and cid not in seen:
            seen.add(cid)
            out.append((s["id"], cid))
    return out


def adapt(card: dict) -> dict:
    """A copy of a card's fields that a lesson may reword (ADAPT_FIELDS, the ones it has), with "from": its id."""
    out = {k: copy.deepcopy(card[k]) for k in ADAPT_FIELDS if card.get(k) not in (None, "", [])}
    out["from"] = card["id"]
    return out


def adapt_lesson(text: dict, steps: list[dict], known: dict | None = None) -> dict:
    """Start text.json's card_text: each card a step opens gets a copy of the general card, unless it has one
    already (an edited copy is never overwritten). Changes `text` in place; returns what it added and kept."""
    known = strokes() if known is None else known
    have = text.setdefault("card_text", {})
    added, kept = [], []
    for sid, cid in opened(steps, known):
        mine = have.setdefault(sid, {})
        if cid in mine:
            kept.append(f"{sid}.{cid}")
        else:
            mine[cid] = adapt(known[cid])
            added.append(f"{sid}.{cid}")
    stale = [f"{sid}.{cid}" for sid, row in have.items() for cid in (row or {})
             if (sid, cid) not in set(opened(steps, known))]
    return {"added": added, "kept": kept, "stale": stale}


def _brush_kinds(text: str) -> set[str]:
    return {brushes.kind(m.group(0)) or m.group(0).lower() for m in BRUSH_WORDS.finditer(text)}


def _all_text(card: dict) -> str:
    return " ".join(w for _, w in _technique_text(card))


def adapted_problems(card_text: dict | None, steps: list[dict], known: dict | None = None,
                     paints: dict | None = None) -> tuple[list[str], list[str]]:
    """(failures, notes) for text.json's card_text. A note for each card a step opens with no adapted copy (the page
    shows the general card, which is never wrong, only less helpful). A failure for an adapted card that has drifted
    from its card, each saying what to put back. `paints` is construct.lookup of the plan's paints."""
    known = strokes() if known is None else known
    card_text = card_text or {}
    fails, notes = [], []
    wanted = opened(steps, known)
    for sid, cid in wanted:
        if cid not in (card_text.get(sid) or {}):
            notes.append(f"step {sid} opens the {cid} card with no copy adapted for this painting, so the page shows "
                         "the general card. Run card-adapt and adapt it (skill step 6c).")
    if not isinstance(card_text, dict):
        return ["text.json's card_text isn't a list of steps by id: run card-adapt"], notes
    for sid, row in card_text.items():
        for cid, a in (row or {}).items():
            where = f"card_text.{sid}.{cid}"
            if (sid, cid) not in wanted:
                fails.append(f"{where}: step {sid} doesn't open the {cid} card, so the page never shows it. Take it "
                             "out of text.json (card-adapt lists what's left over after a plan change).")
                continue
            card = known[cid]
            if not isinstance(a, dict):
                fails.append(f"{where}: isn't a card. Take it out and run card-adapt again.")
                continue
            if unchanged(card, a):
                notes.append(f"{where} is still the general card word for word, so the page shows the general card. "
                             "Adapt its words and diagram for this painting (skill step 6c).")
            if a.get("from") != cid:
                fails.append(f"{where}: its from is {a.get('from')!r}. Put back \"from\": \"{cid}\", the card it's "
                             "adapted from.")
            for k in ADAPT_FIELDS:
                if card.get(k) not in (None, "", []) and k not in a:
                    fails.append(f"{where}: has no {k}. Put back the {cid} card's {k}, with only its subject words "
                                 "changed.")
            for k in a:
                if k in ("from",):
                    continue
                if k == "brushes":
                    if a[k] != card.get("brushes"):
                        fails.append(f"{where}: has other brushes ({a[k]}). The card is done with "
                                     f"{card.get('brushes')}: take brushes out.")
                    continue
                if k not in ADAPT_FIELDS or card.get(k) in (None, "", []):
                    fails.append(f"{where}: has a {k} the {cid} card hasn't. Take it out: an adapted card keeps the "
                                 "card's technique and adds none.")
            for k in ("motion", "result", "then"):
                if k in a and card.get(k) and not (isinstance(a[k], str) and a[k].strip()):
                    fails.append(f"{where}: its {k} is empty. Put back the card's {k}, with the subject words swapped.")
            ms = a.get("mistakes")
            if "mistakes" in a and card.get("mistakes"):
                if not isinstance(ms, list):
                    fails.append(f"{where}: mistakes isn't a list. Put back the card's mistakes.")
                    ms = []
                if len(ms) > len(card["mistakes"]):
                    fails.append(f"{where}: has {len(ms)} mistakes; the {cid} card has {len(card['mistakes'])}. Keep the "
                                 "card's mistakes in order, dropping only one that can't happen here; don't add one.")
                for n, m in enumerate(ms):
                    if not isinstance(m, dict) or not m.get("mistake") or not m.get("fix"):
                        fails.append(f"{where}: mistake {n + 1} needs its mistake and fix, from the card.")
                    elif set(m) - set(MISTAKE_KEYS):
                        fails.append(f"{where}: mistake {n + 1} has {', '.join(sorted(set(m) - set(MISTAKE_KEYS)))}. "
                                     "Keep only mistake, why, and fix.")
            extra = _brush_kinds(_all_text({k: a.get(k) for k in ("motion", "result", "then", "mistakes")
                                            if k in a})) - _brush_kinds(_all_text(card)) - {
                brushes.kind(b) or b for b in [*(card.get("brushes") or []), *(card.get("tools") or [])]}
            if extra:
                fails.append(f"{where}: names a brush the {cid} card doesn't use ({', '.join(sorted(extra))}). Put back "
                             "the card's brush.")
            if "diagram" in a and card.get("diagram"):
                fails += _diagram_drift(where, a["diagram"], card["diagram"], paints or {})
    return fails, notes


def _diagram_drift(where: str, mine, card: dict, paints: dict) -> list[str]:
    stages = mine.get("stages") if isinstance(mine, dict) else None
    want = card.get("stages") or []
    if not isinstance(stages, list):
        return [f"{where}: its diagram has no stages. Put back the card's diagram."]
    if len(stages) != len(want):
        return [f"{where}: its diagram has {len(stages)} stages; the card's has {len(want)}. Keep the card's stages, "
                "each with its arrows, and change only the paints, the example shape, and the captions' words."]
    out = []
    for k, (a, b) in enumerate(zip(stages, want)):
        got = len(a.get("arrows") or []) if isinstance(a, dict) else 0
        if got != len(b.get("arrows") or []):
            out.append(f"{where}: its diagram's panel {k + 1} has {got} arrows; the card's has "
                       f"{len(b.get('arrows') or [])}. Put back the card's arrows.")
    if not construct.strip(mine, paints, "adapted"):
        out.append(f"{where}: its diagram doesn't draw (see spike/construct.py for the format).")
    out += construct.problems(mine, paints, where)
    return out


def unchanged(card: dict, mine) -> bool:
    """True when an adapted copy still says exactly what the general card does: card-adapt's copy, not edited yet.
    The page shows the general card for it, without the "adapted" line."""
    return isinstance(mine, dict) and all(mine.get(k) == card.get(k) for k in ADAPT_FIELDS if k in mine)


def adapted(card: dict, mine: dict) -> dict:
    """The card as a lesson shows it: the general card with the adapted fields in place of its own."""
    return {**card, **{k: v for k, v in mine.items() if k in ADAPT_FIELDS}}


def stroke_html(card: dict, uid: str = "", paints: dict | None = None, here: str = "", banner: str = "",
                anchor: str | None = None) -> str:
    """One stroke card as HTML: the lesson page and the owner's review page both use it. On a lesson page `paints`
    (construct.lookup) lets an adapted diagram name the lesson's paints, `here` is the step's close-up shown beside
    the diagram, `banner` a line under the title (the adapted card's), and `anchor` the section's id."""
    def field(key: str) -> str:  # the load with its words linked to the paint-load card and its pictures (#99)
        return loads.linked(loads.text(card[key]), pictures=False) if key == "load" else e(str(card[key]))

    rows = "".join(f"<p><b>{label}.</b> {field(key)}</p>" for key, label in TEXT_FIELDS if card.get(key))
    tools = [*(card.get("brushes") or []), *(card.get("tools") or [])]
    pics = "".join(brushes.picture(b, "small") for b in card.get("brushes") or [])
    head = f"<h3>{e(card['name'])}"
    if card.get("also_called"):
        head += f" <span class='aka'>also called {e(', '.join(card['also_called']))}</span>"
    head += "</h3>"
    if banner:
        head += banner
    elif not card.get("checked"):
        head += "<p class='unchecked'>Not checked yet</p>"
    with_ = f"<p><b>With.</b> {pics} {e('; '.join(tools))}</p>" if tools else ""
    uses = f"<p><b>Good for.</b> {e(', '.join(card['uses']))}</p>" if card.get("uses") else ""
    wrong = ""
    for m in card.get("mistakes") or []:
        why = f" {e(m['why'])}" if m.get("why") else ""
        wrong += f"<li><b>{e(m['mistake'])}</b>{why} <i>{e(m['fix'])}</i></li>"
    wrong = f"<p><b>If it goes wrong.</b></p><ul>{wrong}</ul>" if wrong else ""
    extra = "".join(f"<p class='note'>{e(card[k])}</p>" for k in ("practice", "note") if card.get(k))
    diagram = construct.strip(card.get("diagram") or {}, paints or {}, f"card-{uid or card['id']}")
    if here:
        diagram = f"<div class='cardpics'>{here}{diagram}</div>"
    sid = anchor if anchor is not None else f"stroke-{card['id']}"
    return f"<section class='card' id='{e(sid)}'>{head}{with_}{rows}{uses}{diagram}{wrong}{extra}</section>"


TERM_ROWS = (("thickness", "How thick the paint is"), ("amount", "How much is on the brush"))


def terms_html(card: dict, basic_cards: dict | None = None) -> str:
    """The paint-load card's pictures (#99): a row for how thick, a row for how much, each term's picture over its name
    and one line. A term with `see` points at that basics card (thin paint at How much water)."""
    by = {t.get("term"): t for t in card.get("terms") or [] if isinstance(t, dict)}
    if not by:
        return ""
    names = {cid: c.get("name", cid) for cid, c in (basics() if basic_cards is None else basic_cards).items()}
    rows = []
    for kind, title in TERM_ROWS:
        figs = []
        for term, (k, words) in loads.TERMS.items():
            if k != kind or term not in by:
                continue
            t = by[term]
            see = (f" See <a href='#basic-{e(t['see'])}'>{e(names.get(t['see'], t['see']))}</a>."
                   if t.get("see") else "")
            figs.append(f"<figure class='loadterm' id='load-{term}'>{loads.picture(term)}<figcaption><b>"
                        f"{e(words[0].upper() + words[1:])}.</b> {e(t.get('line', ''))}{see}</figcaption></figure>")
        rows.append(f"<p class='label'>{e(title)}</p><div class='loadterms'>{''.join(figs)}</div>")
    return "".join(rows)


def basic_html(card: dict, basic_cards: dict | None = None) -> str:
    lines = "".join(f"<li>{e(x)}</li>" for x in card.get("lines") or [])
    flag = "" if card.get("checked") else "<p class='unchecked'>Not checked yet</p>"
    return (f"<section class='card' id='basic-{e(card['id'])}'><h3>{e(card['name'])}</h3>{flag}<ul>{lines}</ul>"
            f"{terms_html(card, basic_cards)}</section>")


STYLE = """
:root{--gesso:#fbfaf7;--panel:#f1f2ef;--ink:#22262b;--muted:#6b7480;--rule:#d9dde3;--ultramarine:#2b4bbd;--r-seeded:#a0622d;--bg:#fbfaf7}
body{font:16px/1.5 system-ui,sans-serif;color:var(--ink);background:var(--bg);max-width:720px;margin:0 auto;padding:16px}
h1{font-size:1.5rem} h2{margin-top:2rem;border-bottom:1px solid var(--rule)} h3{margin:.2rem 0}
.card{border:1px solid var(--rule);border-radius:8px;padding:12px 16px;margin:14px 0;background:#fff}
.card p{margin:.35rem 0} .aka,.src{color:var(--muted);font-weight:400;font-size:.85rem}
.unchecked{display:inline-block;background:#fff3cd;border-radius:4px;padding:0 6px;font-size:.8rem}
.note{color:var(--muted)} .panels{display:flex;gap:10px;flex-wrap:wrap} .panel{margin:0;width:150px}
.panel svg{width:150px;height:150px;border:1px solid var(--rule);border-radius:6px;background:#f6f4ee}
.panel figcaption,.small,.label{font-size:.85rem} .brushpic.sm{height:18px;vertical-align:middle}
""" + loads.STYLE


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
        if isinstance(c.get("load"), dict):
            missing += [f"how {w} (load {k})" for k, w in (("thickness", "thick"), ("amount", "much")) if not c["load"].get(k)]
        gaps = f" Not in the research, so left out: {', '.join(missing)}." if missing else ""
        parts.append(stroke_html(c) + f"<p class='src'>{e(c['_file'])}. From: {e('; '.join(c.get('sources') or []))}.{e(gaps)}</p>")
    return "".join(parts)
