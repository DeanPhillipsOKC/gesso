"""Element techniques: how a kind of part is usually painted (a sky, foliage, lavender rows, a reflection), as
fixed data the plan follows (#12, docs/design/pipeline-v2.md section 10).

    library()              -> {id: element}      techniques/elements/*.yaml
    drafted(lesson)        -> {id: element}      <lesson>/elements/*.yaml, drafted during a run
    problems(library)      -> what's wrong with the element files themselves
    plan_problems(plan, known, lesson) -> what's wrong with the plan's picks and the steps that follow them
    match(steps, element, hexes) -> (slot of each step, or None, and what doesn't fit)
    page()                 -> one HTML page of every element, for the owner to check

A part names its element (`"element": "<id>"`, with `"element_why"`: one line on why it fits this part at this
level). The element lists the part's steps in order, each with the kinds of `show` and the stroke cards it may use
and the value it paints (dark, mid, light). Steps marked `optional` may be left out; `repeat` may be two or more
steps in a row (one per stripe, one per paint). So the plan still chooses the paints and how many passes, but not a
different way to paint the thing: the lavender rows are always flat rows, then dark, mid, and light stamps
(owner, 2026-11-12 on #12).

How each stroke is done stays in the stroke cards; an element only names cards. Every line comes from
docs/research/ or the technique file, with sources, never from the model's memory (docs/decisions.md, 2026-11-11).
When no element fits a part, the run drafts one in `<lesson>/elements/<id>.yaml` (`drafted: true`,
`checked: false`), its steps are marked "technique not checked yet" on the page, and it's filed for the owner
(`filed: <issue url>`) before the lesson seals.
"""

from __future__ import annotations

from itertools import islice
from html import escape as e
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ELEMENTS = ROOT / "techniques" / "elements"
STROKES = ROOT / "techniques" / "strokes"
SHOWS = ("flat", "pass", "full", "blend")
KINDS = ("area", "object", "thin", "marks")
VALUES = {"dark": 0, "mid": 1, "light": 2}
NEEDS = ("id", "name", "for", "kinds", "medium", "levels", "steps", "sources")
# Lab lightness a step marked lighter may fall short of one marked darker before it's a problem: paints are measured
# from the finish, and two passes of one part can land close together.
VALUE_SLACK = 3.0
MAX_FITS = 5000  # ways to fit a part's steps to its element looked at; a real part has a handful


def _read(folder: Path, base: Path) -> dict[str, dict]:
    out = {}
    for path in sorted(Path(folder).glob("*.yaml")):
        el = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        try:
            el["_file"] = str(path.relative_to(base))
        except ValueError:
            el["_file"] = str(path)
        out[el.get("id", path.stem)] = el
    return out


def library() -> dict[str, dict]:
    return _read(ELEMENTS, ROOT)


def drafted(lesson: Path) -> dict[str, dict]:
    folder = Path(lesson) / "elements"
    return _read(folder, Path(lesson)) if folder.is_dir() else {}


def known(lesson: Path | None = None) -> dict[str, dict]:
    """The library, plus what this lesson drafted (a draft can't take a library id: problems says so)."""
    out = library()
    for k, v in (drafted(lesson) if lesson else {}).items():
        out[k] = {**out[k], "_draft_clash": True} if k in out else v
    return out


def _list(x) -> list:
    return x if isinstance(x, list) else [x] if x else []


def problems(elements: dict[str, dict] | None = None, stroke_ids: set[str] | None = None,
             draft: bool = False) -> list[str]:
    """What's wrong with element files: a missing field, a show or kind that doesn't exist, a stroke with no card,
    an id that doesn't match its file. With `draft`, the files a run drafted: they must say so and stay unchecked."""
    elements = library() if elements is None else elements
    stroke_ids = {p.stem for p in STROKES.glob("*.yaml")} if stroke_ids is None else stroke_ids
    out = []
    for eid, el in elements.items():
        f = el.get("_file", eid)
        for key in NEEDS:
            if el.get(key) in (None, "", []):
                out.append(f"{f}: no {key}")
        if "checked" not in el:
            out.append(f"{f}: no checked (false until the owner has read it)")
        if "_file" in el and Path(f).stem != eid:
            out.append(f"{f}: its id is {eid!r}; the file name and the id must match")
        for k in _list(el.get("kinds")):
            if k not in KINDS:
                out.append(f"{f}: kind {k!r} isn't one of {', '.join(KINDS)}")
        required = 0
        for n, slot in enumerate(el.get("steps") or [], 1):
            where = f"{f}: step {n}"
            if not slot.get("name"):
                out.append(f"{where}: no name")
            shows = _list(slot.get("show"))
            if not shows or any(s not in SHOWS for s in shows):
                out.append(f"{where}: show must list some of {', '.join(SHOWS)}")
            strokes = _list(slot.get("strokes"))
            if not strokes:
                out.append(f"{where}: no strokes (stroke card ids)")
            for s in strokes:
                if s not in stroke_ids:
                    out.append(f"{where}: stroke {s!r} has no card in techniques/strokes")
            if slot.get("value") is not None and slot["value"] not in VALUES:
                out.append(f"{where}: value must be one of {', '.join(VALUES)}")
            m = slot.get("mistake")
            if m is not None and (not isinstance(m, dict) or not m.get("mistake") or not m.get("fix")):
                out.append(f"{where}: its mistake needs 'mistake' and 'fix'")
            required += not slot.get("optional")
        if el.get("steps") and not required:
            out.append(f"{f}: every step is optional; at least one must be painted")
        if draft:
            if not el.get("drafted"):
                out.append(f"{f}: a technique drafted in a run needs drafted: true")
            if el.get("checked"):
                out.append(f"{f}: a drafted technique stays checked: false. Only the owner checks one, in the library.")
    return out


def _value_rank(slot: dict) -> int | None:
    return VALUES.get(slot.get("value") or "")


def match(steps: list[dict], element: dict, lightness: dict[str, float] | None = None) -> tuple[list[int | None], list[str]]:
    """Fit a part's steps, in order, to its element's steps. Returns which element step (0-based) each plan step
    fits, and what doesn't fit, each saying what to change. `lightness` (paint id -> Lab L) checks the values:
    a step on a lighter element step must not be darker than one on a darker element step."""
    slots = element.get("steps") or []
    shows = [_list(s.get("show")) for s in slots]
    strokes = [_list(s.get("strokes")) for s in slots]

    def fits(step: dict, k: int) -> bool:
        return step.get("show", "full") in shows[k] and step.get("stroke") in strokes[k]

    n, m = len(steps), len(slots)

    def fresh(i: int, k: int):
        """Every fit of steps[i:] to slots[k:], slot k holding no step yet: the slot of each step."""
        if k == m:
            if i == n:
                yield ()
            return
        if i < n and fits(steps[i], k):
            for rest in held(i + 1, k):
                yield (k,) + rest
        if slots[k].get("optional"):
            yield from fresh(i, k + 1)

    def held(i: int, k: int):
        """The same, slot k already holding a step: take one more when it may repeat, or move on."""
        if slots[k].get("repeat") and i < n and fits(steps[i], k):
            for rest in held(i + 1, k):
                yield (k,) + rest
        yield from fresh(i, k + 1)

    eid = element.get("id", "?")
    recipe = "; ".join(f"{j + 1}. {s.get('name', '')} ({'/'.join(shows[j])}, {' or '.join(strokes[j])}"
                       f"{', optional' if s.get('optional') else ''}{', may repeat' if s.get('repeat') else ''})"
                       for j, s in enumerate(slots))
    fits_all = list(islice(fresh(0, 0), MAX_FITS))
    if not fits_all:
        first_bad = _first_misfit(steps, slots, fits)
        why = (f"{first_bad['id']} ({first_bad.get('show', 'full')}, {first_bad.get('stroke')}) doesn't fit where it comes"
               if first_bad else "a step it needs is missing")
        return [None] * n, [f"its steps don't follow the {eid} technique: {why}. Its steps, in order: {recipe}. "
                            "Change the steps to follow it, or pick another element (tools.py elements lists them)."]
    # of the fits, the one whose values agree best with the paints (a pass on the shade slot or the light slot
    # can use the same strokes: the paint says which it is); the first such fit, so the same plan gives the same fit
    # among fits that agree as well, the one with the fewest steps on element steps that have no value (sections,
    # shine, details), so a shade or light pass lands where its value is checked and its watch-out applies; then the
    # first (review of #111)
    scored = [(len(_value_problems(steps, slots, f, lightness, eid)) if lightness else 0,
               sum(1 for k in f if _value_rank(slots[k]) is None), n_, f) for n_, f in enumerate(fits_all)]
    *_, best = min(scored)
    where: list[int | None] = list(best)
    return where, (_value_problems(steps, slots, best, lightness, eid) if lightness else [])


def _value_problems(steps, slots, where, lightness, eid) -> list[str]:
    """A step on a lighter element step whose paint is darker than one on a darker element step."""
    out: list[str] = []
    ranked = [(steps[i], _value_rank(slots[k]), _step_lightness(steps[i], lightness))
              for i, k in enumerate(where) if k is not None and _value_rank(slots[k]) is not None]
    for a in range(len(ranked)):
        for b in range(a + 1, len(ranked)):
            (sa, ra, la), (sb, rb, lb) = ranked[a], ranked[b]
            if None in (la, lb) or ra == rb:
                continue
            dark, light = ((sa, la), (sb, lb)) if ra < rb else ((sb, lb), (sa, la))
            if light[1] < dark[1] - VALUE_SLACK:
                slot = slots[where[steps.index(light[0])]]
                out.append(f"{light[0]['id']} is where the {eid} technique's step \"{slot.get('name')}\" ({slot.get('value')}) "
                           f"goes, but its paint is darker than {dark[0]['id']}'s (lightness {light[1]:.0f} against "
                           f"{dark[1]:.0f}). If {light[0]['id']} is a different step, the part is missing that one: add "
                           "it (paints --add gives the part a lighter or darker color). Or swap the two steps' paints.")
    return out


def _first_misfit(steps, slots, fits) -> dict | None:
    """The first step no prefix of the recipe can reach: for the message only."""
    reach = {0}
    for s in steps:
        nxt = set()
        for k in sorted(reach):
            j = k
            while j < len(slots):
                if fits(s, j):
                    nxt.add(j + 1)
                    if slots[j].get("repeat"):
                        nxt.add(j)
                if not slots[j].get("optional"):
                    break
                j += 1
        if not nxt:
            return s
        reach = nxt
    return None


def _step_lightness(step: dict, lightness: dict[str, float]) -> float | None:
    vals = [lightness[c] for c in step.get("paints") or [] if c in lightness]
    return sum(vals) / len(vals) if vals else None


def plan_problems(plan: dict, elements: dict[str, dict] | None = None, lesson: Path | None = None) -> list[str]:
    """What's wrong with a version 2 plan's technique picks: `technique_why`, every part's `element` and
    `element_why`, an element for another kind of part, steps that don't follow the element, and a drafted element
    that's broken or not filed for the owner yet."""
    elements = known(lesson) if elements is None else elements
    out: list[str] = []
    if not (plan.get("technique_why") or "").strip():
        out.append("no technique_why: one line on why this approach fits the picture and the level")
    lightness = plan_lightness(plan)
    by_part: dict[str, list[dict]] = {}
    for st in plan.get("stages") or []:
        for s in st.get("steps") or []:
            by_part.setdefault(s.get("part"), []).append(s)
    used_drafts = set()
    for p in plan.get("parts") or []:
        pid = p.get("id", "")
        eid = p.get("element")
        if not eid:
            out.append(f"{pid}: no element. Pick the element technique that fits it (tools.py elements lists them) and "
                       "say why in element_why, or draft one in the lesson's elements/ folder.")
            continue
        el = elements.get(eid)
        if el is None:
            out.append(f"{pid}: element {eid!r} isn't in techniques/elements or the lesson's elements/ folder")
            continue
        if el.get("_draft_clash"):
            out.append(f"{pid}: elements/{eid}.yaml in the lesson has a library element's id. Give the draft its own id.")
        if el.get("drafted"):
            used_drafts.add(eid)
        if not (p.get("element_why") or "").strip():
            out.append(f"{pid}: no element_why: one line on why {eid} fits this part")
        kinds = _list(el.get("kinds"))
        if kinds and p.get("kind") not in kinds:
            out.append(f"{pid}: element {eid} is for {' or '.join(kinds)} parts, and {pid} is {p.get('kind')}. Pick "
                       "another element, or change the part's kind.")
        mine = by_part.get(pid)
        if mine:
            _, wrong = match(mine, el, lightness)
            out += [f"{pid}: {w}" for w in wrong]
    if lesson is not None:
        drafts = drafted(lesson)
        out += problems(drafts, draft=True)
        for eid in sorted(set(drafts) - used_drafts):
            out.append(f"elements/{eid}.yaml was drafted but no part uses it. Delete it, or name it on the part it was "
                       "drafted for.")
        for eid in sorted(used_drafts):
            if not (drafts.get(eid) or {}).get("filed"):
                out.append(f"elements/{eid}.yaml was drafted for this lesson and isn't filed for the owner yet. File it "
                           "now, as step 2b says (search first; reuse a matching issue), and put its url in filed.")
    return out


def plan_lightness(plan: dict) -> dict[str, float] | None:
    """{paint id: Lab lightness} from the plan's measured paints, or None before there are any. Every caller of
    match on a plan uses it, so check, draft-text, and the page see the same fit."""
    hexes = {c["id"]: c["hex"] for c in plan.get("paints") or [] if c.get("hex")}
    if not hexes:
        return None
    import mixing

    return {k: mixing._lab(mixing.hex_rgb(h))[0] for k, h in hexes.items()}


def step_elements(plan: dict, elements: dict[str, dict]) -> dict[str, dict]:
    """{step id: {"element", "name", "checked", "drafted", "slot", "mistake"}} for every step whose part names an
    element that exists: what the page and draft-text show."""
    out: dict[str, dict] = {}
    lightness = plan_lightness(plan)
    by_part: dict[str, list[dict]] = {}
    for st in plan.get("stages") or []:
        for s in st.get("steps") or []:
            by_part.setdefault(s.get("part"), []).append(s)
    for p in plan.get("parts") or []:
        el = elements.get(p.get("element") or "")
        if not el:
            continue
        steps = by_part.get(p["id"]) or []
        where, _ = match(steps, el, lightness)
        slots = el.get("steps") or []
        for s, k in zip(steps, where):
            slot = slots[k] if k is not None else {}
            out[s["id"]] = {"element": el["id"], "name": el.get("name", el["id"]), "checked": bool(el.get("checked")),
                            "drafted": bool(el.get("drafted")), "slot": k, "mistake": slot.get("mistake")}
    return out


def picks(plan: dict) -> list[dict]:
    """The plan's technique picks, for lesson.json and the owner's review: one row per part."""
    return [{"part": p["id"], "name": p.get("name", p["id"]), "element": p.get("element"),
             "why": p.get("element_why", ""), "left_out": p.get("element_left_out", "")}
            for p in plan.get("parts") or []]


STYLE = """
body{font:16px/1.5 system-ui,sans-serif;color:#22262b;background:#fbfaf7;max-width:720px;margin:0 auto;padding:16px}
h2{margin-top:2rem;border-bottom:1px solid #d9dde3} .card{border:1px solid #d9dde3;border-radius:8px;padding:12px 16px;
margin:14px 0;background:#fff} .src,.small{color:#6b7480;font-size:.85rem}
.unchecked{display:inline-block;background:#fff3cd;border-radius:4px;padding:0 6px;font-size:.8rem}
"""


def html(el: dict) -> str:
    flag = "" if el.get("checked") else "<span class='unchecked'>Not checked yet</span>"
    rows = []
    for n, s in enumerate(el.get("steps") or [], 1):
        how = f"{'/'.join(_list(s.get('show')))}; strokes: {', '.join(_list(s.get('strokes')))}"
        extra = ", ".join(x for x in ("optional" if s.get("optional") else "", "may repeat" if s.get("repeat") else "",
                                      f"value: {s['value']}" if s.get("value") else "") if x)
        m = s.get("mistake")
        watch = f"<br><i>Watch out: {e(m['mistake'])} {e(m.get('why', ''))} Fix: {e(m['fix'])}</i>" if m else ""
        rows.append(f"<li><b>{e(s.get('name', ''))}</b> <span class='small'>({e(how)}{'; ' + e(extra) if extra else ''})"
                    f"</span><br>{e(s.get('does', ''))}{watch}</li>")
    rules = "".join(f"<li>{e(r)}</li>" for r in el.get("rules") or [])
    return (f"<section class='card' id='element-{e(el['id'])}'><h3>{e(el['name'])} {flag}</h3><p>{e(el.get('for', ''))}"
            f"</p><p class='small'>For {e(', '.join(_list(el.get('kinds'))))} parts. Like: "
            f"{e(', '.join(_list(el.get('examples'))))}</p><ol>{''.join(rows)}</ol>"
            + (f"<p><b>Rules</b></p><ul>{rules}</ul>" if rules else "")
            + f"<p class='src'>{e(el.get('_file', ''))}. From: {e('; '.join(_list(el.get('sources'))))}</p></section>")


def page() -> str:
    lib = library()
    wrong = problems(lib)
    out = ["<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
           f"<title>Gesso element techniques</title><style>{STYLE}</style><h1>Element techniques ({len(lib)})</h1>",
           "<p>How each kind of part is painted, step by step, built only from the research file and the technique "
           "file. A lesson's plan follows these. Read each one; when it's right, set <code>checked: true</code> in its "
           "file.</p>"]
    if wrong:
        out.append("<h2>Problems</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in wrong) + "</ul>")
    out += [html(el) for el in lib.values()]
    return "".join(out)
