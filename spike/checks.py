"""Every measured check on a version 2 lesson, in one list (pipeline v2, docs/design/pipeline-v2.md section 12).

    run(lesson, text=None, built=None) -> {"failures": [...], "notes": [...]}

Version 1 caught drift, shape changes, and split edges with two image review rounds, redos, and a lock. Version 2
step pictures are cut from one finish inside real outlines, so those can't happen; what's left to catch is measured
here instead: the plan, the outlines, the step pictures, the stroke cards, the drafted text, and what `publish`
already counted. Each failure names the step, part, or paint and says what to change. `publish` runs this for a
version 2 lesson and `publish --final` won't seal one while anything fails. `notes` are things worth knowing that
aren't failures.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

PERCENT = re.compile(r"\d\s*%|\bper\s?cent\b", re.I)
# #122: steps say where in inches; the tape marks are gone. Only placing by tape is flagged, so a real tip such as
# "masking tape gives a crisp horizon" isn't (review of #122).
TAPE = re.compile(r"\btape marks?\b|\b(?:top|side|edge)'?s? tape\b|\bmark\w*\b[^.]{0,20}\btape\b|\btape\b[^.]{0,20}\bmark"
                  r"|\b(?:middle|half|quarter|line it up with|along) (?:of |on )?(?:the |your )?tape\b", re.I)
SUMMARY_CHARS = 90


def _technique(lesson: Path, plan: dict) -> dict:
    import yaml

    import tools

    technique = yaml.safe_load((tools.ROOT / plan["technique"]).read_text(encoding="utf-8")) if plan.get("technique") else {}
    if plan.get("palette"):
        technique["palette"], technique["palette_name"] = tools.load_palette(plan["palette"])
    return technique


def build(lesson: Path, plan: dict):
    """(owner, pictures, rows, masks) for a version 2 lesson, as build-steps makes them; None without outlines."""
    import build_steps as bs
    from filters import load

    path = lesson / "parts" / "owner.png"
    finish_path = lesson / "99_finish.png"
    if not path.exists() or not finish_path.exists():
        return None
    from PIL import Image

    owner = np.array(Image.open(path)).astype("int32")
    finish = load(finish_path, max_side=100_000)
    if owner.max() >= len(plan["parts"]) or owner.shape != finish.shape[:2]:
        return None
    plate = lesson / "98_background.png"
    pictures, rows, masks = bs.build(finish, plan, owner, load(plate, max_side=100_000) if plate.exists() else None)
    return owner, pictures, rows, masks


def _canvas(lesson: Path) -> tuple[list | None, dict]:
    """canvas.json's canvas box and size. A lesson with none gets the default size (canvas.lesson_canvas), or
    canvas.NoCanvas is raised: every version 2 step says where in inches (#122)."""
    import canvas as cv

    info = cv.lesson_canvas(lesson)
    return info.get("canvas_box"), info["canvas"]


def counts(plan: dict, technique: dict) -> list[str]:
    """Steps, stages, and top-level parts against the technique's version 2 limits."""
    out = []
    steps = [s for st in plan.get("stages") or [] for s in st.get("steps") or []]
    lo, hi = technique.get("v2_step_range") or (None, None)
    if lo is not None and not lo <= len(steps) <= hi:
        out.append(f"the plan has {len(steps)} steps; the technique wants {lo} to {hi}. "
                   + ("Split the biggest steps into smaller moves (a coat, then one pass per paint)." if len(steps) < lo
                      else "Merge passes that add little, or drop a part the picture doesn't need."))
    lo, hi = technique.get("v2_stage_range") or (None, None)
    n = len(plan.get("stages") or [])
    if lo is not None and not lo <= n <= hi:
        out.append(f"the plan has {n} stages; the technique wants {lo} to {hi}. "
                   + ("Split a stage that paints two things into one stage each." if n < lo
                      else "Group neighboring stages that paint the same thing."))
    top = [p["id"] for p in plan.get("parts") or [] if not p.get("parent")]
    most = (technique.get("detail_budget") or {}).get("max_parts")
    if most is not None and len(top) > most:
        out.append(f"{len(top)} parts with no parent ({', '.join(top)}); the technique's detail budget is {most}. Make "
                   "small things children of the part they sit on, or merge parts (a pass can carry a color).")
    return out


def strokes_and_brushes(plan: dict, known: dict) -> list[str]:
    """Every step's stroke has a card, its brush is one brushes.py can draw, and the card can be done with it."""
    import brushes

    out = []
    for st in plan.get("stages") or []:
        for s in st.get("steps") or []:
            stroke, brush = s.get("stroke"), s.get("brush")
            card = known.get(stroke or "")
            if not stroke:
                out.append(f"{s['id']}: no stroke. Give it a stroke card's id (ls techniques/strokes).")
            elif not card:
                out.append(f"{s['id']}: stroke {stroke!r} has no card in techniques/strokes. Use a card's id, or draft "
                           "a card in the lesson folder and file it for the owner.")
            if not brush:
                out.append(f"{s['id']}: no brush. Name one (\"#6 round\", \"1/2 inch flat\", \"liner\").")
                continue
            kind = brushes.kind(brush)
            if not kind:
                out.append(f"{s['id']}: brush {brush!r} isn't one spike/brushes.py knows (flat, round, liner, fan, "
                           "filbert, angle, old stiff flat). Name it as one of those.")
                continue
            want = {k for b in (card or {}).get("brushes") or [] if (k := brushes.kind(b))}
            if want and kind not in want:
                out.append(f"{s['id']}: stroke {stroke} is done with a {' or '.join(sorted(want))} brush (its card), "
                           f"not a {kind} like {brush!r}. Change the brush, or the stroke to one this brush does.")
    return out


def text_problems(plan: dict, text: dict[str, dict], redrafted: dict[str, list] | None) -> list[str]:
    """What Claude still has to write, percentages, long lines, and lines that no longer match the plan."""
    out = []
    for st in plan.get("stages") or []:
        for s in st.get("steps") or []:
            sid = s["id"]
            if not s.get("name"):
                out.append(f"{sid}: no name in plan.json. Give it a short instruction (\"Block in the body\").")
            t = text.get(sid)
            if t is None or not t.get("lines"):
                out.append(f"{sid}: no drafted lines in text.json. Run draft-text.")
                continue
            if not (t.get("summary") or "").strip():
                out.append(f"{sid}: no summary in text.json. Write one plain sentence, under {SUMMARY_CHARS} characters.")
            elif len(t["summary"]) > SUMMARY_CHARS:
                out.append(f"{sid}: its summary is {len(t['summary'])} characters. Cut it under {SUMMARY_CHARS}.")
            if not (t.get("tip") or "").strip():
                out.append(f"{sid}: no tip in text.json. Write one to three sentences only this photo needs (which way "
                           "the strokes run here, which side the light is on, what to leave showing).")
            for where, words in [("summary", t.get("summary") or ""), ("tip", t.get("tip") or "")] + \
                                [(f"line {n + 1}", x.get("text") or "") for n, x in enumerate(t["lines"])] + \
                                [(f"paint note {n + 1}", x) for n, x in enumerate(t.get("paint_notes") or [])]:
                if PERCENT.search(words):
                    out.append(f"{sid}: its {where} gives a percentage. Say where by the outline, or in inches from "
                               "an edge.")
                if TAPE.search(words):
                    out.append(f"{sid}: its {where} places things by tape marks, and the painter has no tape. Say where "
                               "in inches from an edge.")
            for n, x in enumerate(t["lines"]):
                if len((x.get("text") or "").split()) > 40:
                    out.append(f"{sid}: line {n + 1} is {len(x['text'].split())} words. A long line is two moves: "
                               "split it in two.")
            if redrafted is not None and redrafted.get(sid) is not None and redrafted[sid] != t["lines"]:
                out.append(f"{sid}: its drafted lines don't match the plan and pictures any more. Run draft-text again "
                           "(lines marked \"edited\": true are kept).")
    return out


def paint_names(plan: dict) -> list[str]:
    out = []
    for c in plan.get("paints") or []:
        missing = [k for k in ("name", "used_for") if not c.get(k)]
        if missing:
            out.append(f"paint {c['id']}: no {' or '.join(missing)} in plan.json. Name it as a painter would "
                       "(\"Bark brown\") and say what it's for; paints writes ids only.")
    return out


def unused_paints(plan: dict) -> list[str]:
    """#136: a paint no step uses, such as one `paints --add` made for a step that was dropped. `paints` never
    merges an added paint, so nothing else would clear it, and the painter would see a mix they never use. A paint
    a used tint or shade is made from (its `of`) counts as used."""
    import plan2

    used = {c for s in plan2.steps(plan) for c in s.get("paints") or []}
    of = {c.get("id"): c.get("of") for c in plan.get("paints") or []}
    for c in list(used):
        while of.get(c) and of[c] not in used:
            c = of[c]
            used.add(c)
    return [f"paint {c['id']}: no step uses it. Take it out of paints in plan.json, or add it to the step that "
            "should use it." for c in plan.get("paints") or [] if c.get("id") not in used]


def texture_jumps(lesson: Path, plan: dict) -> list[dict]:
    """tools.texture_jumps over a version 2 lesson's step pictures, for `full` steps only: a part that goes from
    bare canvas to finished texture in one step. A `blend` is one wet move by definition. A `flat` coat is flat by construction (what's measured
    there is its new edge), and a `pass` is one paint in one stroke, which is how a texture is taught: a dab pass
    over a whole lavender field is one move however much of the picture it covers. Holding passes to the 10% rule
    sent three of the first six hands-off runs round the tools three times each with no clean fix (2026-11-13).
    `check` and `publish` both report this list for version 2."""
    import build_steps as bs
    import tools

    steps = bs.flat_steps(plan)
    whole = {s["id"] for s in steps if s.get("show", "full") == "full"}
    paths = [lesson / f"{i + 1:02d}_{s['id']}.png" for i, s in enumerate(steps)]
    return [j for j in tools.texture_jumps(lesson, paths) if j["step"] in whole]


def run(lesson: Path, text: dict[str, dict] | None = None, built=None) -> dict:
    """Every check on a version 2 lesson. `text` is text.json's steps by id (read from the lesson when None),
    `built` is build()'s result when the caller already has it."""
    import build_steps as bs
    import cards
    import draft_text
    import outline as ol
    import plan2
    import publish2
    import tools

    lesson = Path(lesson)
    plan = plan2.load(lesson)
    technique = _technique(lesson, plan)
    failures = list(plan2.problems(plan, technique))
    notes = []
    if failures:
        return {"failures": failures + ["fix plan.json first; the other checks need a plan that loads"], "notes": notes}
    failures += counts(plan, technique)
    known = cards.strokes()
    failures += strokes_and_brushes(plan, known)
    failures += paint_names(plan)
    failures += unused_paints(plan)
    failures += cards.problems(known)
    import elements

    failures += elements.problems()
    failures += elements.plan_problems(plan, lesson=lesson)

    built = built if built is not None else build(lesson, plan)
    steps = bs.flat_steps(plan)
    names = [f"{i + 1:02d}_{s['id']}.png" for i, s in enumerate(steps)]
    if built is None:
        failures.append(f"no outlines that fit the plan: run outline --lesson {lesson}, then build-steps")
    else:
        owner, pictures, rows, masks = built
        stats_path = lesson / "parts" / "stats.json"
        if stats_path.exists():
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
        else:
            stats = [{"confidence": None, **x} for x in ol.owner_stats(plan["parts"], owner)]
            notes.append("no parts/stats.json: the outline checks were measured from parts/owner.png, without the "
                         "outline model's confidence")
        failures += ol.problems(plan["parts"], stats)
        failures += bs.problems(plan, rows)
        notes += bs.faint_ghosts(plan, rows)
        missing = [n for n in names if not (lesson / n).exists()]
        if missing:
            failures.append(f"missing step pictures {missing[:3]}{' ...' if len(missing) > 3 else ''}: run build-steps")
        else:
            from filters import load

            stale = next((n for n, p in zip(names, pictures)
                          if not np.array_equal(load(lesson / n, max_side=100_000), p)), None)
            if stale:
                failures.append(f"{stale} doesn't match the plan: run build-steps, then step-aids, again")
            for j in texture_jumps(lesson, plan):
                failures.append(f"{j['step']}: turns {j['share']:.0%} of the picture from flat to textured in one "
                                "step. Make it two or more steps: a flat coat in the part's main paint, then a pass per paint (run paints --add for the part if it has only one), then build-steps.")
        import canvas as cv
        try:
            canvas_box, canvas = _canvas(lesson)
        except cv.NoCanvas as err:
            failures.append(str(err))
            built = None  # nothing to draft against: the lines can't be compared
        else:
            drafted = {d["stage_id"]: d["lines"]
                       for d in draft_text.draft(plan, pictures, masks, canvas_box, canvas, known, lesson,
                                                        owner=owner)}
    text_path = lesson / "text.json"
    if text is None:
        text = ({t["stage_id"]: t for t in json.loads(text_path.read_text(encoding="utf-8"))["steps"]}
                if text_path.exists() else {})
    redrafted = None
    if built is not None:
        redrafted = {sid: draft_text.merge_lines((text.get(sid) or {}).get("lines") or [], lines)
                     for sid, lines in drafted.items()}
    failures += text_problems(plan, text, redrafted)
    gaps = draft_text.left_out(plan, known)
    if gaps:
        notes.append("lines the data can't give (none drafted): "
                     + "; ".join(f"{sid}: {', '.join(g)}" for sid, g in gaps.items()))

    # what publish counts: paints a line names but the step doesn't list, recipes, diagrams, the step aids
    extras = publish2.paint_extras(plan)  # what publish puts on each paint (of, plus, parts...), so the page agrees
    by_name = {n: {**extras.get(n, {}), "name": n, "hex": c["hex"]} for c in plan.get("paints") or []
               for n in [publish2.paint_names(plan)[c["id"]]]}
    stages = publish2.stages(plan, text, by_name, names, {"dry_time": technique.get("dry_time", "")}, lesson)
    import construct

    named = publish2.paint_names(plan)
    diagram_paints = construct.lookup([{"id": c["id"], "name": named[c["id"]], "hex": c["hex"]}
                                       for c in plan.get("paints") or []])
    for st in stages:
        failures += construct.problems(st.get("construct"), diagram_paints, st["id"])
    for x in tools.paints_not_listed(stages, by_name):
        failures.append(f"{x['id']}: its text names {x['paint']}, which isn't one of its paints, so its recipe isn't "
                        "shown. Add the paint to the step in plan.json, or don't name it.")
    mixes_path = lesson / "mixes.json"
    mixes = json.loads(mixes_path.read_text(encoding="utf-8")) if mixes_path.exists() else {}
    if set(mixes) != set(by_name) or any(mixes[n].get("target_hex", "").lower() != by_name[n]["hex"].lower() for n in mixes):
        failures.append("mixes.json is missing or was made for other paints: run mix")
    else:
        for a, b in tools.duplicate_recipes(mixes):
            failures.append(f"paints {a} and {b} mix to the same color. Merge them into one paint in plan.json.")
        noted = " ".join(n for t in text.values() for n in (t.get("paint_notes") or [])).lower()
        for n, m in mixes.items():
            if not m["reachable"] and n.lower() not in noted:
                failures.append(f"paint {n} can't be mixed from these tubes and no step's paint_notes says so. Add a "
                                "paint note to the step that first uses it.")
    lesson_notes = json.loads((lesson / "notes.json").read_text(encoding="utf-8")) if (lesson / "notes.json").exists() else {}
    for sid in tools.undocumented_diagrams(stages, lesson_notes):
        failures.append(f"{sid}: has a diagram that notes.json's beginner_check.diagrams doesn't explain. Say why it "
                        "needs one there.")
    aids_path = lesson / "aids" / "aids.json"
    aids_rows = json.loads(aids_path.read_text(encoding="utf-8")).get("steps") if aids_path.exists() else None
    if [r.get("id") for r in aids_rows or []] != [s["id"] for s in steps]:
        failures.append("aids/aids.json is missing or was made for other steps: run step-aids")
    else:  # the area each step covers: where the page puts the colors-dry-darker card (#95)
        for st, r in zip(stages, aids_rows):
            st["aids"] = {"area": r["area"]} if "area" in r else {}
    notes += cards.unplaced(stages)
    page = lesson / "lesson-standalone.html"
    if page.exists() and page.stat().st_size > publish2.MAX_PAGE_BYTES:
        failures.append(f"the page is {page.stat().st_size / 1e6:.1f} MB, over {publish2.MAX_PAGE_BYTES / 1e6:g} MB. "
                        "Merge small steps in the plan, then build-steps, step-aids, and publish again.")
    return {"failures": failures, "notes": notes}
