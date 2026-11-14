"""The version 2 lesson plan: parts, paints, stages, and small steps (docs/design/pipeline-v2.md section 5).

    problems(plan) -> what's wrong with the plan, each with what to change (empty when it's fine)

A version 1 plan lists steps with rough boxes, and every step picture is rendered. A version 2 plan lists the
picture's parts back to front, and each step paints inside one part, so the pictures can be cut from the finish.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KINDS = ("area", "object", "thin", "marks")
SHOWS = ("flat", "pass", "full", "blend")
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_PAINTS = 3  # paints in one step, except a blend
NO_STAGES = "the plan has no stages with steps"  # all that's wrong with a plan between `paints` and its stages


def load(lesson: Path) -> dict:
    plan = json.loads((Path(lesson) / "plan.json").read_text(encoding="utf-8"))
    if plan.get("plan_version") != 2:
        raise ValueError(f"{lesson}/plan.json isn't a version 2 plan (no \"plan_version\": 2)")
    return plan


def is_v2(lesson: Path) -> bool:
    path = Path(lesson) / "plan.json"
    return path.exists() and json.loads(path.read_text(encoding="utf-8")).get("plan_version") == 2


def steps(plan: dict) -> list[dict]:
    return [s for st in plan.get("stages") or [] for s in st.get("steps") or []]


def _boxes_ok(boxes) -> bool:
    return all(len(b) == 4 and 0 <= b[0] < b[2] <= 1 and 0 <= b[1] < b[3] <= 1 for b in boxes)


def parts_problems(plan: dict) -> list[str]:
    """What's wrong with the plan's parts alone: all `outline` and `part-colors` need, before there are paints or
    stages. `problems` includes these."""
    out: list[str] = []
    parts = plan.get("parts") or []
    if not parts:
        return ["the plan has no parts"]
    seen: dict[str, dict] = {}
    for p in parts:
        pid = p.get("id", "")
        if not SLUG.match(pid):
            out.append(f"part id {pid!r} must be a lowercase slug like 'far-hill'")
        if pid in seen:
            out.append(f"{pid}: two parts have this id")
        if p.get("kind") not in KINDS:
            out.append(f"{pid}: kind must be one of {', '.join(KINDS)}")
        boxes = p.get("boxes") or ([p["box"]] if p.get("box") else [])
        if p.get("kind") != "thin" and not boxes:
            out.append(f"{pid}: needs a box (or boxes), measured with grid --percent")
        if not _boxes_ok(boxes + (p.get("covers") or [])):
            out.append(f"{pid}: every box is [x0, y0, x1, y1] with 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1")
        if p.get("parent") and p["parent"] not in seen:
            out.append(f"{pid}: its parent {p['parent']!r} must be an earlier part")
        if p.get("kind") in ("marks", "thin"):
            for side, what in (("in", "on it"), ("out", "on what's behind it")):
                if not p.get(f"points_{side}") and not p.get(f"colors_{side}"):
                    out.append(f"{pid}: a {p['kind']} part needs points_{side} or colors_{side} ({what})")
        if p.get("kind") == "thin" and not (p.get("paths") or p.get("path")):
            out.append(f"{pid}: a thin part needs paths: points along its middle")
        elif p.get("kind") == "thin" and not all(
                isinstance(path, list) and path and all(isinstance(q, (list, tuple)) and len(q) == 2
                                                        and all(isinstance(v, (int, float)) for v in q) for q in path)
                for path in (p.get("paths") or [p.get("path")])):
            out.append(f"{pid}: a thin part has an empty path or a point that isn't [x, y]: each path lists points "
                       "along one limb")
        parent = seen.get(p.get("parent") or "")
        if parent and p.get("kind") in ("marks", "thin") and parent.get("kind") in ("marks", "thin"):
            # a marks or thin child only takes pixels its parent's family owns (or nobody does), and a marks or thin
            # parent owns only pixels of its own colors, so the child finds nothing (the sailboat's mast reflection, 2026-11-13)
            instead = (f"give it {parent['parent']!r} as its parent (what {parent['id']} sits on)" if parent.get("parent")
                       else "give it no parent")
            out.append(f"{pid}: a {p['kind']} part can't have the {parent['kind']} part {parent['id']} as its parent: "
                       f"it would outline nothing. List it after {parent['id']} and {instead}.")
        seen[pid] = p
    return out


def problems(plan: dict, technique: dict | None = None) -> list[str]:
    """What's wrong with a version 2 plan: its parts (parts_problems), its paints, and its stages and steps. With the
    technique, also more base mixes than its `max_mixes` while two could still merge by `paints`' rules: neither
    is an accent or was made by `paints --add`, they're at most paints.MAX_MERGE apart, and at most one of them is
    a paint a step uses (that one is never merged away). Two paints a pass was split into stay apart."""
    out = parts_problems(plan)
    if out == ["the plan has no parts"]:
        return out
    seen = {p.get("id", ""): p for p in plan.get("parts") or []}
    paints: dict[str, dict] = {}
    for c in plan.get("paints") or []:
        if c.get("id") in paints:
            out.append(f"paint {c.get('id')}: two paints have this id")
        if not HEX.match(c.get("hex", "")):
            out.append(f"paint {c.get('id')}: hex must look like #a1b2c3")
        if c.get("sample_x") is None or c.get("sample_y") is None:
            out.append(f"paint {c.get('id')}: no sample_x/sample_y (a spot of it in the finish). Run paints, which "
                       "measures them.")
        paints[c.get("id")] = c
    for c in paints.values():
        if c.get("of") and c["of"] not in paints:
            out.append(f"paint {c.get('id')}: it's a tint or shade of {c['of']!r}, which isn't in paints")
    bases = [c for c in paints.values() if not c.get("of") and HEX.match(c.get("hex", ""))]
    target = (technique or {}).get("max_mixes")
    if target is not None and len(bases) > target:
        import paints as measured  # only here: it needs OpenCV, and the rest of this file doesn't

        everything = [c for c in paints.values() if HEX.match(c.get("hex", ""))]
        # what `paints` would still merge: never a paint a step uses into another, never one `paints --add` made
        used = {c for s in steps(plan) for c in s.get("paints") or []}
        added = {c["id"] for c in everything if c.get("added")}
        pairs = measured.mergeable(bases, measured.accents(everything), used, added)
        if pairs:  # over the target with nothing close enough left to merge is allowed (design section 9)
            de, a, b = min((measured.mixing.delta_e(a["hex"], b["hex"]), a["id"], b["id"]) for a, b in pairs)
            out.append(f"{len(bases)} paints to mix, above the technique's target of {target}, and {a} and {b} are only "
                       f"Delta E {de:.1f} apart, close enough to merge. Run paints again.")
    all_steps = steps(plan)
    if not all_steps:
        return out + [NO_STAGES]
    ids: set[str] = set()
    by_part: dict[str, list[dict]] = {}
    for s in all_steps:
        sid = s.get("id", "")
        if not SLUG.match(sid):
            out.append(f"step id {sid!r} must be a lowercase slug")
        if sid in ids:
            out.append(f"{sid}: two steps have this id")
        ids.add(sid)
        if s.get("part") not in seen:
            out.append(f"{sid}: its part {s.get('part')!r} isn't in parts")
            continue
        show = s.get("show", "full")
        if show not in SHOWS:
            out.append(f"{sid}: show must be one of {', '.join(SHOWS)}")
        used = s.get("paints") or []
        for c in used:
            if c not in paints:
                out.append(f"{sid}: paint {c!r} isn't in paints")
            elif s["part"] not in (paints[c].get("parts") or []):
                out.append(f"{sid}: paints {s['part']} with {c}, but {c}'s parts don't list {s['part']}. Add it to "
                           f"its parts, or use one of {s['part']}'s own paints.")
        if not used:
            out.append(f"{sid}: name the paints this step uses")
        if len(used) > MAX_PAINTS and show != "blend":
            out.append(f"{sid}: {len(used)} paints in one step. Split it (splitting is free), or make it a blend if "
                       "the colors are blended wet in one go.")
        by_part.setdefault(s["part"], []).append(s)
    for pid, p in seen.items():
        mine = by_part.get(pid)
        if not mine:
            out.append(f"{pid}: no step paints this part. Give it a step, or take it out of parts.")
            continue
        if mine[-1].get("show") == "flat":
            out.append(f"{pid}: its last step ({mine[-1]['id']}) is flat, so the part never looks finished. Add a pass "
                       "or make it full.")
        if mine[0].get("show") == "pass" and p.get("kind") in ("area", "object"):
            out.append(f"{pid}: starts with a pass ({mine[0]['id']}). An area or object needs a flat step first, so no "
                       "canvas shows through.")
        for a, b in zip(mine, mine[1:]):
            if a.get("show") in ("full", "blend"):
                out.append(f"{pid}: {a['id']} already shows the whole part, so {b['id']} has nothing to add. Make "
                           f"{a['id']} flat or a pass.")
    return out
