"""Every step's lines drafted from data (pipeline v2, docs/design/pipeline-v2.md section 10, "Step text").

    draft(plan, pictures, masks, canvas_box, canvas) -> one text.json entry per step: its drafted lines, brushes, cards
    merge(old, drafted)                               -> text.json's contents: the draft, with what Claude wrote kept
    left_out(plan)                                    -> {step id: the table's lines this step can't have, and why}

Until version 2, Claude wrote every lesson's text from scratch and cut it to a word limit, so what a beginner was
told changed from run to run and often left out the basics (when to let it dry, rinsing, which paint first, how to
load the brush). Here each line comes from something already measured or checked: the plan, the step masks
(`build_steps.build`), the outlines (`aids.where_words`), the paints, the technique file, and the hand-checked stroke
and basics cards. Nothing here is painting advice of its own: a line the data can't give is left out, and
`left_out` says which and why. Claude then writes each step's `summary` and `tip`, and corrects any drafted line
against the step picture, marking it `"edited": true`; `merge` never touches those.

The same plan and pictures give the same lines, byte for byte.
"""

from __future__ import annotations

import re

import numpy as np

import aids
import build_steps as bs
import cards
import mixing
import outline as ol
import paints as measured
import publish2

KINDS = ("dry", "rinse", "chalk", "where", "paints", "mix", "how", "result", "coats", "watch", "step-back")
MAX_WORDS = 40  # one line; a longer one is two moves (`check` reports a line over this)
OVERLAP = 0.02  # an earlier step's paint under this share of a step's area or more means "let it dry" first
RINSE_DE = 40  # a step's first paint this far (Delta E) from the last step's last paint means "rinse well first"
LIGHT_OVER_DARK = 30  # a paint this much lighter (Lab L) than what it goes over needs two or three coats
LEAVE = 0.10  # a step that leaves more than this share of its part's earlier paint showing says so
SAME = 12  # RGB levels: a pixel that changed less than this in a step still shows the paint under it
DRY_NAMES = 2  # "let ... dry" names at most this many things

# The words around the data. Each says what one row of the design's table says, in a card's own words where a card
# has them (named on each line).
DRY = "Let {what} dry to the touch first. A hair dryer on low speeds it up."  # basics card let-it-dry
RINSE = "Rinse the brush well first. Dirty water tints every color with the last one."  # basics card clean-brush
RINSE_LIGHT = "Rinse the brush fully first: this is the lightest paint yet."  # basics card clean-brush
CHALK = ("Optional: lightly chalk its outline first, from the transfer outline in Before you start, measuring from "
         "the canvas edges with a ruler.")  # design section 10, transfer outline; inches, not tape marks (#122)
COATS = "{paint} is much lighter than what it goes over: expect two or three thin coats, letting each dry."  # light-over-dark
STEP_BACK = "Step back, squint, or take a photo to see it whole, and compare the big shapes with the picture."  # ugly-stage
LEAVE_SHOWING = "Leave what {steps} painted showing around these marks, as in the Result picture."  # technique rules


def _the(name: str) -> str:
    """'The black cap and bib' -> 'the black cap and bib', for the middle of a sentence."""
    n = re.sub(r"^the\s+", "", name.strip(), flags=re.I)
    return "the " + n[:1].lower() + n[1:]


def _lower_first(s: str) -> str:
    s = s.strip()
    word = s.split()[0] if s else ""
    return s if len(word) > 1 and word.isupper() else s[:1].lower() + s[1:]  # leave "OK", "UV" alone


def _and(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    last = ", and " if any(" and " in x for x in items) else " and "  # "the mountains and fields, and the sky"
    return ", ".join(items[:-1]) + last + items[-1]


def _then(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + ", then " + items[-1]


def _steps_words(nums: list[int]) -> str:
    return ("step " if len(nums) == 1 else "steps ") + _and([str(n) for n in nums])


def split(text: str, kind: str) -> list[dict]:
    """A text as one or more lines of at most MAX_WORDS words, split between sentences."""
    sentences = [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z(\"'])", text.strip()) if x]
    out, cur = [], []
    for s in sentences:
        if cur and len(" ".join(cur + [s]).split()) > MAX_WORDS:
            out.append(" ".join(cur))
            cur = []
        cur.append(s)
    if cur:
        out.append(" ".join(cur))
    return [{"kind": kind, "text": t, "edited": False} for t in out]


def paint_order(step: dict, hexes: dict[str, str], picture: np.ndarray | None, mask: np.ndarray | None) -> list[str]:
    """The step's paints in the order they go on: darkest first; a blend's top to bottom, where each lands in the
    step picture."""
    ids = list(step.get("paints") or [])
    if step.get("show") == "blend" and picture is not None and mask is not None and mask.any() and len(ids) > 1:
        labels = aids.paint_map(picture, mask, [hexes[c] for c in ids])
        ys = np.arange(labels.shape[0])[:, None]
        mean_y = [float((ys * (labels == k)).sum() / max(1, (labels == k).sum())) for k in range(len(ids))]
        return [ids[k] for k in sorted(range(len(ids)), key=lambda k: (mean_y[k], k))]
    return sorted(ids, key=lambda c: (measured.lightness(hexes[c]), ids.index(c)))


def _card_brush_kinds(card: dict) -> set[str]:
    import brushes

    return {k for b in card.get("brushes") or [] if (k := brushes.kind(b))}


def draft(plan: dict, pictures: list[np.ndarray], masks: list[np.ndarray], canvas_box: list[float] | None = None,
          canvas: dict | None = None, known: dict | None = None, lesson=None) -> list[dict]:
    """text.json's entries for every step, drafted. `pictures` and `masks` are build_steps.build's (in the frame);
    `canvas_box` and `canvas` are canvas.json's (where the painter's canvas sits in the frame, and its size)."""
    known = cards.strokes() if known is None else known
    import elements as els

    picked = els.step_elements(plan, els.known(lesson))
    steps = bs.flat_steps(plan)
    parts = {p["id"]: p for p in plan["parts"]}
    stage_name = {st["id"]: st.get("name") or st["id"] for st in plan["stages"]}
    names = publish2.paint_names(plan)
    hexes = {c["id"]: c["hex"] for c in plan.get("paints") or []}
    last_in_stage = {st["steps"][-1]["id"] for st in plan["stages"] if st.get("steps")}
    first_of_part: dict[str, int] = {}
    for i, s in enumerate(steps):
        first_of_part.setdefault(s["part"], i)
    uses: dict[str, list[int]] = {}
    for i, s in enumerate(steps):
        for c in s.get("paints") or []:
            uses.setdefault(c, []).append(i)
    blank = np.empty_like(pictures[0])
    blank[:] = bs.ff.CANVAS
    out = []
    prev_last: str | None = None  # the last paint the brush carried
    lightest = -1.0
    for i, s in enumerate(steps):
        mask, pic, before = masks[i], pictures[i], pictures[i - 1] if i else blank
        order = paint_order(s, hexes, pic, mask)
        lines: list[dict] = []

        # dry: earlier steps' paint under this step's area. Named by its stage, or by its part inside this stage; the
        # two most recent (what's under those has had longer to dry).
        area = max(int(mask.sum()), 1)
        labels: list[str] = []
        for j in reversed(range(i)):
            if (mask & masks[j]).sum() / area < OVERLAP:
                continue
            same = steps[j]["stage"] == s["stage"]
            label = _the(parts[steps[j]["part"]].get("name") or steps[j]["part"]) if same else \
                _the(stage_name[steps[j]["stage"]])
            if label not in labels:
                labels.append(label)
            if len(labels) == DRY_NAMES:
                break
        if labels:
            lines.append({"kind": "dry", "text": DRY.format(what=_and(labels)), "edited": False})

        # rinse: a far color from the last one on the brush, or the lightest paint yet
        if order and prev_last is not None:
            first = hexes[order[0]]
            if measured.lightness(first) > lightest:
                lines.append({"kind": "rinse", "text": RINSE_LIGHT, "edited": False})
            elif mixing.delta_e(first, hexes[prev_last]) > RINSE_DE:
                lines.append({"kind": "rinse", "text": RINSE, "edited": False})

        # chalk: the first step of an object with no parent
        part = parts[s["part"]]
        if part["kind"] == "object" and not part.get("parent") and first_of_part[s["part"]] == i:
            lines.append({"kind": "chalk", "text": CHALK, "edited": False})

        # where: the step's area on the canvas, from its outline
        lines += split(aids.where_words(aids.to_canvas(mask, canvas_box), canvas), "where")

        # paints, in the order they go on
        if order:
            pn = [names[c] for c in order]
            if len(pn) == 1:
                text = f"Paint: {pn[0]}."
            elif s.get("show") == "blend":
                text = f"Paints, top to bottom: {_then(pn)}."
            else:
                text = f"Paints, darkest first: {_then(pn)}. The paint map shows where each goes."
            lines.append({"kind": "paints", "text": text, "edited": False})

        # mix: a paint used again in later steps, mixed once where it's first used
        for c in order:
            later = [k + 1 for k in uses[c] if k > i]
            if uses[c][0] == i and later:
                lines.append({"kind": "mix", "text": f"Mix enough {names[c]} for this step and {_steps_words(later)}; "
                                                      "cover it between them.", "edited": False})

        # how: the brush, then the card's load and motion
        card = known.get(s.get("stroke") or "")
        brush = s.get("brush") or ""
        if brush or (card and card.get("load")):
            head = f"Brush: {brush}." if brush else ""
            load = f"Load: {card['load'].strip()}" if card and card.get("load") else ""
            lines += split(" ".join(x for x in (head, load) if x), "how")
        if card and card.get("motion"):
            lines += split(card["motion"], "how")

        # result: what the card says the stroke leaves; and, for a pass, the paint underneath that stays
        if card and card.get("result"):
            lines += split("It should leave " + _lower_first(card["result"]), "result")
        own_before = [j for j in range(i) if steps[j]["part"] == s["part"]]
        if own_before:  # measured: where this part's earlier paint is still there after this step
            earlier = np.zeros_like(mask)
            for j in own_before:
                earlier |= masks[j]
            kept = earlier & (np.abs(pic.astype(np.int16) - before.astype(np.int16)).max(2) < SAME)
            if earlier.any() and kept.sum() / earlier.sum() > LEAVE:
                lines.append({"kind": "result", "text": LEAVE_SHOWING.format(steps=_steps_words([j + 1 for j in own_before])),
                              "edited": False})

        # coats: a paint much lighter than what it goes over
        if mask.any():
            labels = aids.paint_map(pic, mask, [hexes[c] for c in order]) if len(order) > 1 else None
            L_before = ol.lab(before)[..., 0]
            for k, c in enumerate(order):
                where = mask if labels is None else labels == k
                if where.any() and measured.lightness(hexes[c]) - float(np.median(L_before[where])) > LIGHT_OVER_DARK:
                    lines.append({"kind": "coats", "text": COATS.format(paint=names[c]), "edited": False})
                    break

        # watch: the element technique's mistake for this step when it has one (#12), else the card's first mistake;
        # the rest stay on the card
        m = (picked.get(s["id"]) or {}).get("mistake") or (card["mistakes"][0] if card and card.get("mistakes") else None)
        if m:
            text = f"Watch out: {m['mistake'].strip()}" + (f" {m['why'].strip()}" if m.get("why") else "")
            lines += split(text + f" Fix: {_lower_first(m['fix'])}", "watch")

        if s["id"] in last_in_stage:
            lines.append({"kind": "step-back", "text": STEP_BACK, "edited": False})

        if order:
            prev_last = order[-1]
            lightest = max(lightest, *(measured.lightness(hexes[c]) for c in order))
        entry = {"stage_id": s["id"], "lines": lines,
                 "brushes": [{"brush": brush, "use": s.get("name") or s["id"]}] if brush else [],
                 "stroke_cards": [s["stroke"]] if s.get("stroke") in known else [],
                 "made_with": publish2.MADE_WITH, "reason": publish2.REASON}
        out.append(entry)
    return out


def left_out(plan: dict, known: dict | None = None) -> dict[str, list[str]]:
    """{step id: the rows of the design's table this step's text has no data for}: missing cards and card fields."""
    known = cards.strokes() if known is None else known
    out: dict[str, list[str]] = {}
    for s in bs.flat_steps(plan):
        card = known.get(s.get("stroke") or "")
        gaps = []
        if not card:
            gaps.append(f"no stroke card {s.get('stroke')!r}, so no load, motion, result, or watch-out line")
        else:
            for key, line in (("load", "load"), ("motion", "motion"), ("result", "result"), ("mistakes", "watch-out")):
                if not card.get(key):
                    gaps.append(f"card {card['id']} has no {key}, so no {line} line")
        if gaps:
            out[s["id"]] = gaps
    return out


def _slots(lines: list[dict]) -> list[tuple[str, int]]:
    seen: dict[str, int] = {}
    out = []
    for x in lines:
        k = x.get("kind", "")
        out.append((k, seen.get(k, 0)))
        seen[k] = seen.get(k, 0) + 1
    return out


def merge_lines(old: list[dict], new: list[dict]) -> list[dict]:
    """The drafted lines, with every line Claude edited (`"edited": true`) kept in its place: an edited line replaces
    the drafted line in the same slot (the nth line of its kind); one with no such slot (a line Claude added) stays,
    after the lines of its kind. An edited line with empty text removes the drafted line in its slot."""
    edited = {slot: x for slot, x in zip(_slots(old), old) if x.get("edited")}
    out = []
    used = set()
    for slot, x in zip(_slots(new), new):
        if slot in edited:
            out.append(edited[slot])
            used.add(slot)
        else:
            out.append(x)
    rank = {k: n for n, k in enumerate(KINDS)}
    for slot, x in edited.items():
        if slot in used:
            continue
        r = rank.get(x.get("kind"), len(KINDS))
        at = max([n + 1 for n, y in enumerate(out) if rank.get(y.get("kind"), len(KINDS)) <= r], default=0)
        out.insert(at, x)
    return out


KEEP = ("summary", "tip")  # what Claude writes; never drafted


def merge(old: dict | None, drafted: list[dict]) -> dict:
    """text.json's contents: one entry per drafted step, in the plan's order. From an old entry it keeps everything
    draft-text doesn't write (summary, tip, construct, paint_notes, ...), every edited line, and brushes Claude
    wrote for the same brush. Steps no longer in the plan are dropped."""
    by_id = {t.get("stage_id"): t for t in (old or {}).get("steps") or []}
    steps = []
    for d in drafted:
        o = by_id.get(d["stage_id"]) or {}
        entry = dict(o)
        entry["stage_id"] = d["stage_id"]
        entry["lines"] = merge_lines(o.get("lines") or [], d["lines"])
        if [b.get("brush") for b in o.get("brushes") or []] != [b["brush"] for b in d["brushes"]]:
            entry["brushes"] = d["brushes"]
        entry["stroke_cards"] = d["stroke_cards"]
        entry.setdefault("made_with", d["made_with"])
        entry.setdefault("reason", d["reason"])
        steps.append(entry)
    out = {k: v for k, v in (old or {}).items() if k != "steps"}
    out["steps"] = steps
    return out
