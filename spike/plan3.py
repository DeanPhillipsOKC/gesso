"""The version 3 lesson plan: a painter's plan written before any picture is cut (docs/design/pipeline-v3.md,
section 5).

    problems(plan, technique) -> what's wrong with the plan, each with what to change (empty when it's fine)
    notes(plan, technique)    -> what isn't wrong but the run should know: the paint count, mixes to mix again
    units(plan)               -> the renders the chain makes, in painting order: one a unit

A version 2 plan lists parts with boxes, and each step paints inside one part's outline. A version 3 plan lists
things with no boxes, and each step says what it lays on which things. The pictures are made to fit it: the finish
is erased backward a unit at a time (`erase`), and a thing's shape is what its render changed.

Words:
    thing     something the painter paints, as a painter names it (the sky, the cow). No box, no outline.
    unit      a run of steps in one stage on the same thing. One render a unit. A block-in or a blend is a unit by
              itself, and
              so is a step whose paints its unit has all used already (two steps of one render that share a paint
              can't be told apart in it).
    kind      what a unit's render is asked for: "first" (the first unit: never erased), "bare" (its things are new
              and have bare canvas behind), "behind" (new, on things already painted), "back" (a later stage of a
              thing already there: only its last layer comes off).
"""

from __future__ import annotations

import json
from pathlib import Path

import plan2

SLUG, HEX, MAX_PAINTS = plan2.SLUG, plan2.HEX, plan2.MAX_PAINTS
CLOSE = 12.0  # Delta E: two base paints nearer than this could be one mix (paints.MAX_MERGE, the owner's 2026-11-12)
APART = 3  # a paint used again this many steps or more after its last use has dried on the palette: mix it again


def version(lesson: Path) -> int | None:
    """The lesson's plan version (2 or 3), or None when it has no plan.json."""
    path = Path(lesson) / "plan.json"
    if not path.exists():
        return None
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:  # not JSON: no version. The tool that reads the plan next says what is wrong with it
        return None
    return plan.get("plan_version") if isinstance(plan, dict) else None


def is_v3(lesson: Path) -> bool:
    return version(lesson) == 3


def load(lesson: Path) -> dict:
    plan = json.loads((Path(lesson) / "plan.json").read_text(encoding="utf-8"))
    if plan.get("plan_version") != 3:
        raise ValueError(f"{lesson}/plan.json isn't a version 3 plan (no \"plan_version\": 3)")
    return plan


def steps(plan: dict) -> list[dict]:
    """Every step in painting order, each with its stage's id and name."""
    return [dict(s, stage=st.get("id"), stage_name=st.get("name") or st.get("id"))
            for st in plan.get("stages") or [] for s in st.get("steps") or []]


def things_of(step: dict) -> list[str]:
    """The things a step lays paint on, in the order it names them, each once."""
    return list(dict.fromkeys(lay.get("thing") for lay in step.get("lays") or []))


def slug(name: str) -> str:
    return "-".join("".join(ch if ch.isalnum() and ch.isascii() else " " for ch in name.lower()).split())


def _runs(plan: dict) -> list[dict]:
    """One run for the steps of a stage that share a thing (`units` in spike/experiments/v4_forward.py, #207). A
    step on a thing an earlier run of the same stage painted joins that run, and takes the runs between with it:
    a chain erases one run at a time, and those were painted before the step that comes back."""
    out: list[dict] = []
    i = 0
    for st in plan.get("stages") or []:
        mine: list[dict] = []
        for s in st.get("steps") or []:
            t = things_of(s)
            hit = [k for k, u in enumerate(mine) if set(u["things"]) & set(t)]
            if hit:
                for late in mine[hit[0] + 1:]:
                    mine[hit[0]]["things"] += [x for x in late["things"] if x not in mine[hit[0]]["things"]]
                    mine[hit[0]]["steps"] += late["steps"]
                del mine[hit[0] + 1:]
                u = mine[hit[0]]
            else:
                u = {"stage": st.get("id"), "things": [], "steps": []}
                mine.append(u)
            u["things"] += [x for x in t if x not in u["things"]]
            u["steps"].append(i)
            i += 1
        out += mine
    return out


def units(plan: dict) -> list[dict]:
    """The plan's units in painting order: {"stage", "things", "steps" (indexes into `steps`), "kind", "id",
    "name"}. A run of steps is cut where a step's paints are all ones the unit has used already, and before
    and after a block-in or a blend (`units` in spike/experiments/v3_combined.py, #210).

    A unit that starts one thing takes that thing's id and name. Any other unit (a later stage of a thing, or one
    that starts several things at once) is named by its first step's `unit`; `problems` asks for it."""
    all_steps = steps(plan)
    # alone in its unit: a block-in, and a blend (colors worked wet into each other can't be told apart by paint, so
    # no other step can share its render)
    block_in = {s.get("id") for s in all_steps if s.get("block_in") or s.get("blend")}
    out: list[dict] = []
    for run in _runs(plan):
        cur: dict = {"stage": run["stage"], "things": [], "steps": []}
        used: set[str] = set()
        for i in run["steps"]:
            s = all_steps[i]
            paints = set(s.get("paints") or [])
            if cur["steps"] and (paints <= used or s.get("id") in block_in
                                 or all_steps[cur["steps"][-1]].get("id") in block_in):
                out.append(cur)
                cur, used = {"stage": run["stage"], "things": [], "steps": []}, set()
            cur["steps"].append(i)
            cur["things"] += [t for t in things_of(s) if t not in cur["things"]]
            used |= paints
        out.append(cur)
    thing = {t.get("id"): t for t in plan.get("things") or []}
    done: set[str] = set()
    for n, u in enumerate(out):
        new = [t for t in u["things"] if t not in done]
        if n == 0:
            u["kind"] = "first"
        elif len(new) < len(u["things"]):
            u["kind"] = "back"
        else:
            u["kind"] = "behind" if any((thing.get(t) or {}).get("behind") for t in u["things"]) else "bare"
        said = (all_steps[u["steps"][0]].get("unit") or "").strip()
        if said:
            u["id"], u["name"] = slug(said), said
        elif len(u["things"]) == 1 and new:
            u["id"], u["name"] = u["things"][0], (thing.get(u["things"][0]) or {}).get("name") or u["things"][0]
        else:
            u["id"], u["name"] = None, None
        done |= set(u["things"])
    return out


def _list(x) -> list:
    return x if isinstance(x, list) else [] if x is None else [x]


HUE = 40.0  # degrees: a paint this far round the color wheel from another isn't that paint with white or a dark added
GRAY = 12.0  # Lab chroma: under this a color has no hue to compare
LIGHTER = 4.0  # Lab L: a version of a paint is at least this much lighter or darker than it


def _version(color: str, of: str) -> bool:
    """Could `color` be `of` with white or a dark added? By the rough colors: the same hue (when both have one), and
    lighter or darker. White and darks pull chroma down, so chroma isn't compared."""
    import math

    import mixing

    (l1, a1, b1), (l2, a2, b2) = mixing._lab(mixing.hex_rgb(color)), mixing._lab(mixing.hex_rgb(of))
    if abs(l1 - l2) < LIGHTER:
        return False
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    if c2 < GRAY:  # a gray has no hue: its versions are grays too
        return c1 < 2 * GRAY
    if c1 < GRAY:  # nearly white or nearly black: a strong color with a lot of white or dark in it (a cream of an ochre)
        return True
    turn = abs(math.degrees(math.atan2(b1, a1) - math.atan2(b2, a2))) % 360
    return min(turn, 360 - turn) <= HUE


def _delta_e(a: str, b: str) -> float:
    import mixing  # only here: the rest of this file needs no color math

    return mixing.delta_e(a, b)


def bases(plan: dict) -> list[dict]:
    """The paints that count as a mix of their own: not a lighter or darker version of another (`of`)."""
    return [p for p in plan.get("paints") or [] if not p.get("of")]


HEADER = {"photo": "the photo's path, as the run gave it", "subject": "what the painting is of",
          "focal_point": "where the eye should land", "light": "where the light comes from, in words"}


def _range(x) -> tuple:
    ok = isinstance(x, (list, tuple)) and len(x) == 2 and all(isinstance(v, int) for v in x)
    return tuple(x) if ok else (None, None)


def _target(technique: dict | None) -> int | None:
    t = (technique or {}).get("max_mixes") if isinstance(technique, dict) else None
    return t if isinstance(t, int) else None


def kit_of(plan: dict, technique: dict | None) -> dict | None:
    """The technique's kit limits, when the plan is a kit lesson (`"kit": true`), else None."""
    kit = (technique or {}).get("kit") if isinstance(technique, dict) else None
    return kit if plan.get("kit") is True and isinstance(kit, dict) else None


def brushes(plan: dict) -> list[str]:
    """Every brush the plan's steps name, once each, in the order they are first used. Two spellings of one brush
    ("1 Inch  flat") are one brush."""
    seen: dict[str, str] = {}
    for s in steps(plan):
        b = s.get("brush")
        if _str(b):
            seen.setdefault(" ".join(b.lower().split()), " ".join(b.split()))
    return list(seen.values())


def _str(x) -> bool:
    return isinstance(x, str) and bool(x.strip())


def shape_problems(plan) -> list[str]:
    """What's wrong with the file's shape: a value of the wrong type anywhere the rules read. A plan is written by
    a writer and read as it comes, so `problems` runs its rules only on a plan this passes, and `units` and `notes`
    are only for such a plan."""
    if not isinstance(plan, dict):
        return ["plan.json must be an object: {\"plan_version\": 3, \"things\": [...], \"paints\": [...], "
                "\"stages\": [...]}"]
    out: list[str] = []

    def rows(holder: dict, key: str, where: str) -> list[dict]:
        got = holder.get(key)
        if got is None:
            return []
        if not isinstance(got, list):
            out.append(f"{where}`{key}` must be a list")
            return []
        bad = [x for x in got if not isinstance(x, dict)]
        if bad:
            out.append(f"{where}every entry of `{key}` must be an object like {{...}}, not {bad[0]!r}")
        return [x for x in got if isinstance(x, dict)]

    def text(holder: dict, keys: tuple, where: str, need: tuple = ()) -> None:
        for k in keys:
            if (k in holder or k in need) and not _str(holder.get(k)):
                out.append(f"{where}`{k}` must be a word or a phrase in quotes, not {holder.get(k)!r}")

    def names(holder: dict, key: str, where: str) -> None:
        got = holder.get(key)
        if got is not None and not (isinstance(got, list) and all(_str(x) for x in got)):
            like = '["Sky blue"]' if key == "paints" else '["sky"]'
            out.append(f"{where}`{key}` must be a list of names in quotes, like {like}, not {got!r}")

    def flag(holder: dict, keys: tuple, where: str) -> None:
        for k in keys:
            if k in holder and not isinstance(holder[k], bool):
                out.append(f"{where}`{k}` must be true or false (no quotes), not {holder[k]!r}")

    flag(plan, ("kit",), "")
    for t in rows(plan, "things", ""):
        where = f"thing {t.get('id')!r}: "
        text(t, ("id", "name", "element", "plain", "called"), where, need=("id", "name", "element"))
        names(t, "behind", where)
    for p in rows(plan, "paints", ""):
        where = f"paint {p.get('name')!r}: "
        text(p, ("name", "looks", "color", "of"), where, need=("name",))
    for st in rows(plan, "stages", ""):
        text(st, ("id", "name"), f"stage {st.get('id')!r}: ", need=("id",))
        for s in rows(st, "steps", f"stage {st.get('id')!r}: "):
            where = f"step {s.get('id')!r}: "
            text(s, ("id", "name", "after", "stroke", "brush", "unit"), where, need=("id",))
            names(s, "paints", where)
            flag(s, ("block_in", "blend"), where)
            for lay in rows(s, "lays", where):
                text(lay, ("thing", "what"), where + "in `lays`, ", need=("thing",))
    return out


def problems(plan: dict, technique: dict | None = None, elements: dict[str, dict] | None = None,
             strokes: set[str] | None = None) -> list[str]:
    """What's wrong with a version 3 plan, each with what to change. It checks the plan against itself, the
    technique's ranges and the library; nothing here knows the picture. `elements` is the element techniques by id
    and `strokes` the stroke cards' ids (read from techniques/ when None)."""
    if elements is None:
        import elements as el

        elements = el.library()
    if strokes is None:
        import cards

        strokes = set(cards.strokes())
    out = shape_problems(plan)
    if out:
        return out
    for key, what in HEADER.items():  # the page and the receipt read these
        if not _str(plan.get(key)):
            out.append(f"the plan has no `{key}`: {what}")
    technique = technique if isinstance(technique, dict) else {}
    things: dict[str, dict] = {}
    for t in plan.get("things") or []:
        tid = t.get("id", "")
        if not SLUG.match(tid):
            out.append(f"thing id {tid!r} must be a lowercase slug like 'far-hill'")
        if tid in things:
            out.append(f"{tid}: two things have this id")
        if not t.get("name"):
            out.append(f"{tid}: a thing needs a name, as the page will say it")
        elif t["name"].strip().lower() in {(x.get("name") or "").strip().lower() for x in things.values()}:
            out.append(f"{tid}: another thing is already named {t['name']!r}. Give each thing its own name.")
        if t.get("element") not in elements:
            out.append(f"{tid}: its element {t.get('element')!r} isn't in techniques/elements. Pick the closest one "
                       "and say in `why` what it lacks.")
        if not isinstance(t.get("behind"), list):
            out.append(f"{tid}: say what is behind it (`behind`): the ids of the things already painted that it "
                       "sits on, or [] when it goes on bare canvas")
        things[tid] = t
    if not things:
        return ["the plan lists no things"]
    stages = plan.get("stages") or []
    all_steps = steps(plan)
    if not all_steps:
        return out + [plan2.NO_STAGES]
    lo, hi = _range(technique.get("v2_step_range"))
    if lo is not None and not lo <= len(all_steps) <= hi:
        out.append(f"the plan has {len(all_steps)} steps; the technique wants {lo} to {hi}")
    lo, hi = _range(technique.get("v2_stage_range"))
    if lo is not None and not lo <= len(stages) <= hi:
        out.append(f"the plan has {len(stages)} stages; the technique wants {lo} to {hi}")

    paints: dict[str, dict] = {}
    for p in plan.get("paints") or []:
        name = p.get("name") or ""
        if not name:
            out.append("a paint has no name")
            continue
        if name in paints:
            out.append(f"paint {name!r}: two paints have this name")
        elif slug(name) in {slug(x) for x in paints}:
            other = next(x for x in paints if slug(x) == slug(name))
            out.append(f"paint {name!r}: too like the name {other!r} (the tools tell paints apart by their letters "
                       "and digits). Rename one.")
        elif not slug(name):
            out.append(f"paint {name!r}: a paint's name needs letters or digits in it")
        if not HEX.match(p.get("color") or ""):
            out.append(f"paint {name!r}: give its rough color (`color`) as a hex like #a1b2c3. The paints are fitted "
                       "to the painting from it.")
        if not p.get("looks"):
            out.append(f"paint {name!r}: say what it looks like (`looks`)")
        paints[name] = p
    for name, p in paints.items():
        of = p.get("of")
        if of and (of not in paints or of == name or paints[of].get("of")):
            out.append(f"paint {name!r}: it's a lighter or darker version of {of!r}, which must be another paint "
                       "that isn't itself a version of one")
        elif of and HEX.match(p.get("color") or "") and HEX.match(paints[of].get("color") or "") \
                and not _version(p["color"], paints[of]["color"]):
            out.append(f"paint {name!r}: `of` says it is {of!r} with white or a dark added, but by their `color` it "
                       f"is another hue, or no lighter or darker. Take `of` off: it is a mix of its own.")

    ids: set[str] = set()
    for st in stages:
        if not SLUG.match(st.get("id", "")) or st.get("id") in ids:
            out.append(f"stage id {st.get('id')!r} must be a lowercase slug no other stage or step has")
        ids.add(st.get("id"))
        if not st.get("name"):
            out.append(f"{st.get('id')}: a stage needs a name")
        if not st.get("steps"):
            out.append(f"{st.get('id')}: a stage needs at least one step")
    first: dict[str, int] = {}  # each thing's first step
    last: dict[str, int] = {}
    used: set[str] = set()
    for i, s in enumerate(all_steps):
        sid = s.get("id", "")
        if not SLUG.match(sid) or sid in ids:
            out.append(f"step id {sid!r} must be a lowercase slug no other stage or step has")
        ids.add(sid)
        for key in ("name", "after"):
            if not s.get(key):
                out.append(f"{sid}: no `{key}`" + (": say what the canvas shows when the step is done. A render is "
                                                    "asked to take the painting back to it." if key == "after" else ""))
        lays = s.get("lays") or []
        if not lays:
            out.append(f"{sid}: name the things this step lays paint on (`lays`)")
        seen: set[str] = set()
        for lay in lays:
            if lay.get("thing") not in things:
                out.append(f"{sid}: lays on {lay.get('thing')!r}, which isn't in things")
                continue
            if lay["thing"] in seen:
                out.append(f"{sid}: lays on {lay['thing']} twice. One entry per thing: say all of it in `what`.")
            if not lay.get("what"):
                out.append(f"{sid}: say what it lays on {lay.get('thing')} (`what`)")
            seen.add(lay["thing"])
        for t in seen:
            first.setdefault(t, i)
            last[t] = i
        mine = s.get("paints") or []
        if not mine:
            out.append(f"{sid}: name the paints this step uses")
        if len(mine) > MAX_PAINTS and not s.get("blend"):
            out.append(f"{sid}: {len(mine)} paints in one step. Split it, or mark it `\"blend\": true` if the "
                       "colors are blended wet in one go.")
        for p in mine:
            if p not in paints:
                out.append(f"{sid}: paint {p!r} isn't in the plan's paints")
        used |= set(mine)
        if s.get("stroke") not in strokes:
            out.append(f"{sid}: its stroke {s.get('stroke')!r} isn't a card in techniques/strokes")
        else:
            for e in sorted({things[t].get("element") for t in seen if things[t].get("element") in elements}):
                allowed = {x for st in elements[e].get("steps") or [] for x in _list(st.get("strokes"))}
                if s["stroke"] not in allowed:
                    out.append(f"{sid}: its stroke {s['stroke']!r} isn't one that {e} lists. Use one of: "
                               f"{', '.join(sorted(allowed))}." + (" A step that crosses things is one move: a "
                               "stroke every one of their elements lists." if len(seen) > 1 else ""))
        if not s.get("brush"):
            out.append(f"{sid}: name its brush")
        if s.get("block_in"):
            late = sorted(t for t in seen if first[t] != i)
            if late:
                out.append(f"{sid}: a block-in is a thing's first coat, and {', '.join(late)} "
                           f"{'was' if len(late) == 1 else 'were'} painted before it. Take `block_in` off.")
            if s.get("blend"):
                out.append(f"{sid}: a block-in is one flat coat and a blend isn't. Keep one of `block_in` and `blend`.")
    for tid in things:
        if tid not in first:
            out.append(f"{tid}: no step lays paint on it. Give it a step, or take it out of things.")
    for name in paints:
        if name not in used:
            out.append(f"paint {name!r}: no step uses it. Name it in a step, or take it out of paints.")
    for i, s in enumerate(all_steps):
        if s.get("block_in"):
            alone = sorted(t for t in things_of(s) if t in things and last.get(t) == i)
            if alone:
                out.append(f"{s.get('id')}: a block-in is flat, and no later step paints {', '.join(alone)}, so "
                           f"{'it' if len(alone) == 1 else 'they'} would never look finished. Add the step that "
                           "finishes it, or take `block_in` off.")
    for tid, t in things.items():
        for b in t.get("behind") if isinstance(t.get("behind"), list) else []:
            if b not in things or b == tid:
                out.append(f"{tid}: `behind` names {b!r}, which isn't another thing")
            elif tid in first and b in first and first[b] >= first[tid]:
                out.append(f"{tid}: `behind` names {b}, which is first painted in step {first[b] + 1}, not before "
                           f"{tid}'s first step ({first[tid] + 1}). Back to front: what's behind is painted first.")

    us = units(plan)
    seen_units: dict[str, int] = {}
    seen_names: set[str] = set()
    per_thing: dict[str, int] = {}
    for n, u in enumerate(us):
        s = all_steps[u["steps"][0]]
        own = not (s.get("unit") or "").strip()  # named after the one thing it starts
        # a unit may take the name of a thing it starts (the tall grass, laid with more of the meadow)
        others = set(things) - {t for t in u["things"] if per_thing.get(t, 0) == 0}
        if not own and not u["id"]:
            out.append(f"{s.get('id')}: its `unit` name {u['name']!r} needs letters or digits in it")
        elif not u["id"]:
            why = ("it starts several things at once" if u["kind"] != "back" else
                   f"it comes back to {', '.join(t for t in u['things'] if t in things)}")
            out.append(f"{s.get('id')}: this step starts a new picture of its own ({why}). Name what it and the steps "
                       f"with it add (`unit`), as the page will say it: \"The cow's shaggy coat\".")
        elif not own and (u["id"] in seen_units or u["name"].strip().lower() in seen_names or u["id"] in others
                          or u["name"].strip().lower() in {(things[t].get("name") or "").strip().lower() for t in others}):
            out.append(f"{s.get('id')}: its `unit` name {u['name']!r} is already the name of a thing or of another "
                       "unit. Name what this one adds.")
        for i in u["steps"][1:]:
            if (all_steps[i].get("unit") or "").strip():
                out.append(f"{all_steps[i].get('id')}: its `unit` is never read: it shares one picture with "
                           f"{s.get('id')}, and that step names it. Take it off.")
        if u["id"]:
            seen_units[u["id"]] = n
            seen_names.add(u["name"].strip().lower())
        for t in u["things"]:
            per_thing[t] = per_thing.get(t, 0) + 1
    for tid, n in per_thing.items():
        if n > 1 and tid in things and not (things[tid].get("plain") or "").strip():
            out.append(f"{tid}: it is painted in {n} units, so say how it looks after the first (`plain`): \"the "
                       "plain gray cat shape\". A render asked to keep it while it is still plain is told that name.")

    kit = kit_of(plan, technique)
    target = None if kit else _target(technique)  # a kit lesson counts every paint (below), versions too
    near = closest(plan)
    if target is not None and len(bases(plan)) > target and near and near[0] <= CLOSE:
        de, a, b = near
        out.append(f"{len(bases(plan))} paints to mix, above the technique's target of {target}, and {a!r} and {b!r} "
                   f"are only Delta E {de:.1f} apart by their `color`. Use one for both; or, if one is the other "
                   "with white or a dark added, give it `of` (the other's name), which isn't counted.")
    if kit:
        most, mine = kit.get("max_brushes"), brushes(plan)
        if isinstance(most, int) and len(mine) > most:
            out.append(f"a kit lesson uses at most {most} brushes, and the steps name {len(mine)}: {', '.join(mine)}. "
                       "Plan every step for one small kit, and give steps that can share a brush the same one.")
        most, mine = kit.get("max_recipes"), [p.get("name") for p in plan.get("paints") or []]
        if isinstance(most, int) and len(mine) > most:
            out.append(f"a kit lesson has at most {most} paints to mix, lighter and darker versions (`of`) counted "
                       f"too, and the plan has {len(mine)}. Use one paint where two are close, and keep a version "
                       "only where a painter would miss it.")
    return out


def closest(plan: dict) -> tuple[float, str, str] | None:
    """The two base paints nearest each other by their rough `color`: (Delta E, one's name, the other's)."""
    mixes = [p for p in bases(plan) if p.get("name") and HEX.match(p.get("color") or "")]
    pairs = [(_delta_e(a["color"], b["color"]), a["name"], b["name"]) for k, a in enumerate(mixes) for b in mixes[k + 1:]]
    return min(pairs) if pairs else None


def notes(plan: dict, technique: dict | None = None) -> dict:
    """What `plan-check` reports beside problems: how many mixes the plan asks for, and each paint used again after
    it has dried on the palette (design section 5: a painter's order pulls a mix's uses apart, so the words say
    "mix it again")."""
    all_steps = steps(plan)
    uses: dict[str, list[int]] = {}
    for i, s in enumerate(all_steps):
        for p in s.get("paints") or []:
            uses.setdefault(p, []).append(i + 1)
    again = [{"paint": p, "steps": at, "mix_again_at": [b for a, b in zip(at, at[1:]) if b - a >= APART]}
             for p, at in uses.items() if any(b - a >= APART for a, b in zip(at, at[1:]))]
    kit = kit_of(plan, technique)
    target = _target(technique)
    n = len(bases(plan))
    out = {"mixes": n, "max_mixes": target, "versions": len(plan.get("paints") or []) - n, "mix_again": again}
    near = closest(plan)
    if target is not None and n > target and not (near and near[0] <= CLOSE):
        out["over_target"] = (f"{n} paints to mix, above the target of {target}, and no two are close enough to be "
                              "one. Allowed: a lesson ends above the target rather than lose a color a painter can "
                              "see.")
    if kit:
        out.pop("over_target", None)  # the kit's limit is the one that holds, and it counts versions
        out["kit"] = {"brushes": brushes(plan), "max_brushes": kit.get("max_brushes"),
                      "recipes": len(plan.get("paints") or []), "max_recipes": kit.get("max_recipes")}
    return out
