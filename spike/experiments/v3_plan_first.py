"""Spike for #172 (pipeline v3, S7): plan the lesson as a painter's process before the pixels, with steps that cross
parts.

Not part of the pipeline. v2 renders the finish, outlines its parts, and then fits steps to the parts: one step paints
inside one part. Here the plan comes first. A writer who sees no outline writes the lesson as a painter would teach it
(painter.json): the things in the picture, the stages, and what each step lays down, on one thing or on several. The
layers are then fitted to that plan with v2's own tools, and the result is folded back into the painter's steps.

    python spike/experiments/v3_plan_first.py painter-check <painter.json>     # is the painter's plan well formed?
    python spike/experiments/v3_plan_first.py start highland-cow --painter <painter.json>   # a bench folder to fit in
    python spike/experiments/v3_plan_first.py check <lesson>                   # the fit against the painter's plan
    python spike/experiments/v3_plan_first.py fold <lesson>                    # the lesson in the painter's steps
    python spike/experiments/v3_plan_first.py differ <plan a> <plan b> [--things map.json --picture NAME]
    python spike/experiments/v3_plan_first.py results                          # writes v3_plan_first.json

Words:
    painter's plan   painter.json: things (no boxes), stages, and steps. A step is one move (one brush, one stroke, one
                     to three paints) and names every thing it lays paint on (`lays`). More than one thing: it crosses
                     parts.
    fit              a version 2 plan.json made to carry the painter's plan through v2's tools. A painter's step that
                     lays on k parts is k v2 steps in a row, each with "of": "<the painter's step id>". Every part says
                     which of the painter's things it belongs to ("thing").
    fold             the fitted lesson put back into the painter's steps: one step per painter's step, its picture the
                     one after its last v2 step, its lines merged. The A/B page and the fault counter read this.

The briefs the writers and fitters are given are v3_plan_first_painter.md and v3_plan_first_fit.md, beside this file.
Lesson folders go in spike/experiments/bench/runs/plan-first/ (git-ignored); the plans and numbers that are kept go in
spike/experiments/bench/plan-first/. docs/spikes/v3-plan-first.md has the results.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "spike"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "bench"))

import plan2  # noqa: E402

BENCH = ROOT / "spike" / "experiments" / "bench"
OUT = BENCH / "runs" / "plan-first"
KEPT = BENCH / "plan-first"  # the painter's plans, the fitted plans and the folded lessons' words, in git
RUNS = Path("/home/user/gesso-baseline/output")  # the v2 baseline runs (docs/spikes/v3-yardstick.md, section 5)
TECHNIQUE = "techniques/acrylic-paint-along-beginner.yaml"
# The pictures this spike starts on (docs/decisions.md: 3 or 4, the ones most likely to show the effect): the owner's
# lowest three on "I could paint each step from its words" (2, 2, 2), each with something a part-by-part plan handles
# badly: a face no step paints, a shadow that crosses the cat and its blanket, a dozen trunks painted in one order.
PICTURES = ["highland-cow", "sleeping-cat", "birch-grove"]
KINDS = ("dry", "rinse", "chalk", "where", "paints", "mix", "how", "result", "coats", "watch", "step-back")
BY_PART = ("where", "paints")  # lines that say which part they're about when a step's parts give different ones
MAX_PAINTS = plan2.MAX_PAINTS


def read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))


def technique() -> dict:
    import yaml

    return yaml.safe_load((ROOT / TECHNIQUE).read_text(encoding="utf-8"))


def painter_steps(painter: dict) -> list[dict]:
    return [s for st in painter.get("stages") or [] for s in st.get("steps") or []]


# ---------------------------------------------------------------------------
# The painter's plan
# ---------------------------------------------------------------------------

def painter_problems(painter: dict, tech: dict | None = None, elements: set[str] | None = None,
                     strokes: set[str] | None = None) -> list[str]:
    """What's wrong with a painter's plan, each with what to change. Shape only: nothing here knows the picture.
    `elements` and `strokes` are the library's ids (read from techniques/ when None)."""
    tech = technique() if tech is None else tech
    if elements is None:
        import elements as el

        elements = set(el.library())
    if strokes is None:
        import cards

        strokes = set(cards.strokes())
    out: list[str] = []
    things: dict[str, dict] = {}
    for t in painter.get("things") or []:
        tid = t.get("id", "")
        if not plan2.SLUG.match(tid):
            out.append(f"thing id {tid!r} must be a lowercase slug like 'far-hill'")
        if tid in things:
            out.append(f"{tid}: two things have this id")
        if not t.get("name"):
            out.append(f"{tid}: a thing needs a name, as the page will say it")
        if t.get("element") not in elements:
            out.append(f"{tid}: its element {t.get('element')!r} isn't in techniques/elements. Pick the closest one "
                       "and say in `why` what it lacks.")
        things[tid] = t
    if not things:
        return ["the plan lists no things"]
    stages = painter.get("stages") or []
    steps = painter_steps(painter)
    if not steps:
        return out + ["the plan has no stages with steps"]
    lo, hi = tech.get("v2_step_range") or (None, None)
    if lo is not None and not lo <= len(steps) <= hi:
        out.append(f"the plan has {len(steps)} steps; the technique wants {lo} to {hi}")
    lo, hi = tech.get("v2_stage_range") or (None, None)
    if lo is not None and not lo <= len(stages) <= hi:
        out.append(f"the plan has {len(stages)} stages; the technique wants {lo} to {hi}")
    named = {p.get("name") for p in painter.get("paints") or []}
    ids: set[str] = set()
    laid: set[str] = set()
    for st in stages:
        if not plan2.SLUG.match(st.get("id", "")) or st.get("id") in ids:
            out.append(f"stage id {st.get('id')!r} must be a lowercase slug no other stage or step has")
        ids.add(st.get("id"))
        if not st.get("name"):
            out.append(f"{st.get('id')}: a stage needs a name")
        if not st.get("steps"):
            out.append(f"{st.get('id')}: a stage needs at least one step")
    for s in steps:
        sid = s.get("id", "")
        if not plan2.SLUG.match(sid) or sid in ids:
            out.append(f"step id {sid!r} must be a lowercase slug no other stage or step has")
        ids.add(sid)
        for key in ("name", "after"):
            if not s.get(key):
                out.append(f"{sid}: no `{key}`")
        lays = s.get("lays") or []
        if not lays:
            out.append(f"{sid}: name the things this step lays paint on (`lays`)")
        seen = set()
        for lay in lays:
            if lay.get("thing") not in things:
                out.append(f"{sid}: lays on {lay.get('thing')!r}, which isn't in things")
            elif lay["thing"] in seen:
                out.append(f"{sid}: lays on {lay['thing']} twice. One entry per thing: say all of it in `what`.")
            if not lay.get("what"):
                out.append(f"{sid}: say what it lays on {lay.get('thing')} (`what`)")
            seen.add(lay.get("thing"))
        laid |= seen
        paints = s.get("paints") or []
        if not paints:
            out.append(f"{sid}: name the paints this step uses")
        if len(paints) > MAX_PAINTS and not s.get("blend"):
            out.append(f"{sid}: {len(paints)} paints in one step. Split it, or mark it `\"blend\": true` if the "
                       "colors are blended wet in one go.")
        for p in paints:
            if p not in named:
                out.append(f"{sid}: paint {p!r} isn't in the plan's paints")
        if s.get("stroke") not in strokes:
            out.append(f"{sid}: its stroke {s.get('stroke')!r} isn't a card in techniques/strokes")
        if not s.get("brush"):
            out.append(f"{sid}: name its brush")
    for tid in things:
        if tid not in laid:
            out.append(f"{tid}: no step lays paint on it. Give it a step, or take it out of things.")
    return out


def crossing(painter: dict) -> list[dict]:
    """The painter's steps that lay paint on more than one thing."""
    return [s for s in painter_steps(painter) if len({x.get("thing") for x in s.get("lays") or []}) > 1]


# ---------------------------------------------------------------------------
# The fit: a version 2 plan that carries the painter's plan
# ---------------------------------------------------------------------------

def groups_of(plan: dict) -> list[tuple[str, list[dict]]]:
    """The fitted plan's steps as runs of v2 steps in a row with the same `of`: [(painter's step id, its v2 steps)]."""
    out: list[tuple[str, list[dict]]] = []
    for s in plan2.steps(plan):
        if out and out[-1][0] == s.get("of"):
            out[-1][1].append(s)
        else:
            out.append((s.get("of"), [s]))
    return out


def fit_problems(painter: dict, plan: dict) -> list[str]:
    """Where a fitted plan.json doesn't carry the painter's plan. A painter's step the layers can't show, or a thing
    with no part, is allowed when the plan says why (`painter_dropped`, `things_dropped`); `deviations` counts them."""
    out: list[str] = []
    steps = painter_steps(painter)
    order = {s["id"]: i for i, s in enumerate(steps)}
    stage_of = {s["id"]: st["id"] for st in painter.get("stages") or [] for s in st.get("steps") or []}
    things = {t["id"] for t in painter.get("things") or []}
    dropped = plan.get("painter_dropped") or {}
    no_part = plan.get("things_dropped") or {}
    for p in plan.get("parts") or []:
        if p.get("thing") not in things:
            out.append(f"part {p.get('id')}: say which of the painter's things it belongs to (\"thing\": one of "
                       f"{sorted(things)})")
    have = {p.get("thing") for p in plan.get("parts") or []}
    for t in sorted(things - have - set(no_part)):
        out.append(f"thing {t}: no part carries it. Give it a part, or say why not in plan.json's things_dropped.")
    for st in plan.get("stages") or []:
        for s in st.get("steps") or []:
            if s.get("of") not in order:
                out.append(f"{s.get('id')}: `of` must name the painter's step it's part of, not {s.get('of')!r}")
            elif stage_of[s["of"]] != st.get("id"):
                out.append(f"{s.get('id')}: it's in stage {st.get('id')}, but the painter's step {s['of']} is in "
                           f"stage {stage_of[s['of']]}. Keep the painter's stages.")
    if out:
        return out
    wanted = [st["id"] for st in painter.get("stages") or []
              if any(s["id"] not in dropped for s in st.get("steps") or [])]
    got = [st.get("id") for st in plan.get("stages") or []]
    if got != wanted:
        out.append(f"the stages are {got}; the painter's are {wanted}. Same ids, same order.")
    groups = groups_of(plan)
    seen: list[str] = []
    for of, subs in groups:
        if of in seen:
            out.append(f"{of}: its v2 steps aren't in a row ({subs[0]['id']} comes after another step's). A painter's "
                       "step is one move: keep its parts together.")
        elif seen and order[of] < order[seen[-1]]:
            out.append(f"{of}: comes after {seen[-1]}, which the painter paints later. Keep the painter's order.")
        seen.append(of)
        moves = {(s.get("stroke"), s.get("brush")) for s in subs}
        if len(moves) > 1:
            out.append(f"{of}: its v2 steps use {len(moves)} different strokes or brushes ({sorted(map(str, moves))}). "
                       "A painter's step is one stroke with one brush.")
        want = next(s for s in steps if s["id"] == of)
        parts = {p["id"]: p for p in plan.get("parts") or []}
        on = {parts[s["part"]].get("thing") for s in subs if s.get("part") in parts}
        lays = {x["thing"] for x in want.get("lays") or []}
        gone = sorted(t for t in lays - on if t not in no_part)
        if gone and not (plan.get("lays_dropped") or {}).get(of):
            out.append(f"{of}: the painter lays paint on {gone} here and no v2 step of it does. Add one, or say why "
                       "not in plan.json's lays_dropped.")
        extra = sorted(on - lays)
        if extra:
            out.append(f"{of}: paints {extra}, which the painter's step doesn't name")
    for sid in order:
        if sid not in seen and sid not in dropped:
            out.append(f"{sid}: the painter's step has no v2 step. Give it one, or say why not in plan.json's "
                       "painter_dropped.")
    return out


def deviations(painter: dict, plan: dict) -> dict:
    """How far the fit had to leave the painter's plan, counted."""
    groups = groups_of(plan)
    return {"painter_steps": len(painter_steps(painter)), "fitted_steps": len(groups),
            "v2_steps": len(plan2.steps(plan)), "crossing_steps": sum(1 for _, subs in groups if len(subs) > 1),
            "steps_dropped": plan.get("painter_dropped") or {}, "things_dropped": plan.get("things_dropped") or {},
            "lays_dropped": plan.get("lays_dropped") or {}}


RANGE = re.compile(r"^the plan has \d+ (steps|stages); the technique wants")
UNWRITTEN = re.compile(r"^(?P<id>[a-z0-9-]+): no (summary|tip) in text\.json")


def check(lesson: Path) -> dict:
    """The fit against the painter's plan, then v2's own checks on the fitted plan with the two that don't apply to
    it taken out: step and stage counts (counted on the painter's steps, by painter_problems), and a summary and tip
    for a v2 step that isn't the first of its painter's step (the fold takes the first's)."""
    import checks

    lesson = Path(lesson)
    painter, plan = read(lesson / "painter.json"), plan2.load(lesson)
    problems = [f"painter.json: {p}" for p in painter_problems(painter)] + fit_problems(painter, plan)
    first = {subs[0]["id"] for _, subs in groups_of(plan)}
    r = checks.run(lesson)
    for f in r["failures"]:
        m = UNWRITTEN.match(f)
        if RANGE.match(f) or (m and m["id"] not in first):
            continue
        problems.append(f)
    return {"problems": problems, "notes": r["notes"], "deviations": deviations(painter, plan), "ok": not problems}


# ---------------------------------------------------------------------------
# The fold: the fitted lesson in the painter's steps
# ---------------------------------------------------------------------------

NUMBERS = re.compile(r"\bsteps? (\d+(?:(?:, and | and |, )\d+)*)")


def renumber(text: str, number_of: dict[int, int], n: int) -> str:
    """A drafted line with its v2 step numbers turned into the folded lesson's. A number that folds into this very
    step is taken out; a line left naming no step ("Leave what step 4 painted showing" when step 4 is part of this
    step) is dropped (returns '')."""
    import draft_text

    gone = False

    def swap(m: re.Match) -> str:
        nonlocal gone
        nums = []
        for x in re.findall(r"\d+", m.group(1)):
            k = number_of.get(int(x), int(x))
            if k != n and k not in nums:
                nums.append(k)
        if not nums:
            gone = True
            return ""
        return draft_text._steps_words(sorted(nums))

    out = NUMBERS.sub(swap, text)
    return "" if gone else out


def _cap(name: str) -> str:
    return name[:1].upper() + name[1:]


def _one_sentence(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Lines that are one sentence about different steps ("Leave what steps 9 and 10 painted showing", from one part,
    and "Leave what steps 11 and 12 painted showing", from another) said once, about all of those steps."""
    import draft_text

    out: list[tuple[str, str]] = []
    at: dict[str, int] = {}
    nums: dict[str, list[int]] = {}
    for part, text in rows:
        found = NUMBERS.findall(text)
        if len(found) != 1:
            out.append((part, text))
            continue
        frame = NUMBERS.sub("\0", text)
        nums.setdefault(frame, [])
        nums[frame] += [int(x) for x in re.findall(r"\d+", found[0]) if int(x) not in nums[frame]]
        if frame not in at:
            at[frame] = len(out)
            out.append((part, text))
        out[at[frame]] = (out[at[frame]][0], frame.replace("\0", draft_text._steps_words(sorted(nums[frame]))))
    return out


def fold_lines(subs: list[dict], number_of: dict[int, int], n: int) -> list[dict]:
    """One painter's step's lines from its v2 steps' lines (lesson.json stages, each with `part_name`): kind by kind
    in the drafted order, a line two parts share said once, and the lines that differ by part (where, paints) led by
    the part's name."""
    out: list[dict] = []
    for kind in KINDS:
        rows: list[tuple[str, str]] = []
        for sub in subs:
            for line in sub.get("lines") or []:
                if line.get("kind") != kind:
                    continue
                text = renumber(line.get("text") or "", number_of, n)
                if text and (sub["part_name"], text) not in rows:
                    rows.append((sub["part_name"], text))
        rows = _one_sentence(rows)
        texts = list(dict.fromkeys(t for _, t in rows))
        by_part: dict[str, list[str]] = {}
        for part, text in rows:
            by_part.setdefault(part, []).append(text)
        if kind in BY_PART and len(by_part) > 1 and len({tuple(v) for v in by_part.values()}) > 1:
            out += [{"kind": kind, "text": f"{_cap(part)}: {text}"} for part, text in rows]
        else:
            out += [{"kind": kind, "text": t} for t in texts]
    return out


def fold(lesson: Path, out: Path | None = None) -> dict:
    """Write the fitted lesson again as a folder the A/B page and the fault counter's packet read (lesson.json, the
    step pictures, the photo, the finish, canvas.json), with one step per painter's step. Needs the lesson published
    as a draft first (`publish --lesson`), so lesson.json has every v2 step's lines, paints and picture."""
    lesson = Path(lesson)
    painter, plan, data = read(lesson / "painter.json"), plan2.load(lesson), read(lesson / "lesson.json")
    wrong = fit_problems(painter, plan)
    if wrong:
        raise SystemExit("the fit doesn't carry the painter's plan: " + " | ".join(wrong))
    v2 = {s["id"]: s for s in data.get("stages") or []}
    ids = [s["id"] for s in plan2.steps(plan)]
    if list(v2) != ids:
        raise SystemExit("lesson.json's steps aren't plan.json's: run publish --lesson again")
    parts = {p["id"]: p for p in plan["parts"]}
    names = {s["id"]: s for s in painter_steps(painter)}
    groups = groups_of(plan)
    number_of = {ids.index(s["id"]) + 1: k + 1 for k, (_, subs) in enumerate(groups) for s in subs}
    out = Path(out) if out else lesson.with_name(lesson.name + "-folded")
    if out.exists():
        shutil.rmtree(out)
    (out / "canvas").mkdir(parents=True)
    stages = []
    for k, (of, steps) in enumerate(groups):
        subs = [{**v2[s["id"]], "part_name": parts[s["part"]].get("name") or s["part"]} for s in steps]
        image = f"canvas/{k + 1:02d}_{of}.png"
        shutil.copyfile(lesson / subs[-1]["image"], out / image)
        colors, seen = [], set()
        for sub in subs:
            for c in sub.get("colors") or []:
                if c.get("name") not in seen:
                    seen.add(c.get("name"))
                    colors.append(c)
        lines = fold_lines(subs, number_of, k + 1)
        tips = list(dict.fromkeys(t for t in (sub.get("tip") or "" for sub in subs) if t.strip()))
        stages.append({
            "id": of, "name": names[of]["name"], "image": image,
            "paints": ", ".join(dict.fromkeys(sub["part_name"] for sub in subs)),
            "steps": [x["text"] for x in lines], "lines": lines, "tip": " ".join(tips),
            "summary": next((sub.get("summary") for sub in subs if sub.get("summary")), ""),
            "colors": colors, "brushes": "; ".join(dict.fromkeys(sub.get("brushes") or "" for sub in subs)),
            "parts": [s["part"] for s in steps], "v2_steps": [s["id"] for s in steps],
            "group": next(st["id"] for st in plan["stages"] if any(s["id"] == steps[0]["id"] for s in st["steps"])),
        })
    folded = {"plan_version": 2, "plan_first": 1, "folded_from": lesson.name, "canvas": data.get("canvas"),
              "groups": [{"id": st["id"], "name": st.get("name") or st["id"],
                          "steps": list(dict.fromkeys(s["of"] for s in st["steps"]))} for st in plan["stages"]],
              "stages": stages}
    write(out / "lesson.json", folded)
    for name in ("canvas.json", "bench.json", "painter.json", "plan.json", "photo.png", "photo.jpg", "99_finish.png"):
        if (lesson / name).exists():
            shutil.copyfile(lesson / name, out / name)
    return {"folded": str(out), "steps": len(stages), "v2_steps": len(ids),
            "crossing_steps": sum(1 for _, subs in groups if len(subs) > 1)}


# ---------------------------------------------------------------------------
# A bench folder to fit a painter's plan in
# ---------------------------------------------------------------------------

def baseline_run(picture: str, runs: Path = RUNS) -> Path:
    key = read(BENCH / "baseline" / "key.json")["packets"]
    return Path(runs) / next(v["lesson"] for v in key.values() if v["picture"] == picture)


SEED = ("plan_version", "technique", "technique_why", "subject", "focal_point", "light", "palette")


def start(picture: str, painter: Path, into: Path = OUT, runs: Path = RUNS, name: str | None = None) -> Path:
    """A bench lesson folder (skill steps 0 and 1 frozen) holding the painter's plan and, as material to fit it with,
    what the baseline run of the same finish already made: its parts with their outlines, its measured paints, and its
    background render. No stages: those come from the painter's plan. Starting from the baseline's layers keeps the
    A/B to one change (the plan and its words) and saves the outlining that takes most of a run; the fitter changes a
    part only where the painter's plan needs it."""
    import bench

    problems = painter_problems(read(painter))
    if problems:
        raise SystemExit("painter.json: " + " | ".join(problems))
    run = baseline_run(picture, runs)
    folder = bench.build(picture, Path(into), name=name or f"{run.name}-plan-first")
    shutil.copyfile(painter, folder / "painter.json")
    base = read(run / "plan.json")
    plan = {k: base[k] for k in SEED if k in base}
    plan["photo"] = read(folder / "bench.json")["plan_photo"]
    plan["parts"], plan["paints"], plan["stages"] = base["parts"], base.get("paints") or [], []
    write(folder / "plan.json", plan)
    shutil.copytree(run / "parts", folder / "parts")
    if (run / "98_background.png").exists():
        shutil.copyfile(run / "98_background.png", folder / "98_background.png")
    return folder


# ---------------------------------------------------------------------------
# How much two plans differ
# ---------------------------------------------------------------------------

def shape(plan: dict, things: dict[str, str] | None = None) -> list[dict]:
    """A plan as its steps in order, each {id, stage, things, strokes}: a painter's plan by its `lays`, a v2 plan by
    its parts (one step each), a fitted plan by its painter's steps. `things` maps this plan's thing or part ids to
    names shared with the plan it's compared with (a hand-made table: two writers name things differently); an id
    that isn't in it keeps its own name."""
    things = things or {}

    def canon(ids) -> list[str]:
        return sorted({things.get(i, i) for i in ids})

    if plan.get("plan_first"):
        return [{"id": s["id"], "stage": st["id"], "things": canon(x["thing"] for x in s.get("lays") or []),
                 "strokes": [s.get("stroke")]} for st in plan["stages"] for s in st["steps"]]
    stage_of = {s["id"]: st["id"] for st in plan.get("stages") or [] for s in st.get("steps") or []}
    if all(s.get("of") for s in plan2.steps(plan)):
        return [{"id": of, "stage": stage_of[subs[0]["id"]], "things": canon(s["part"] for s in subs),
                 "strokes": sorted({s.get("stroke") for s in subs})} for of, subs in groups_of(plan)]
    return [{"id": s["id"], "stage": stage_of[s["id"]], "things": canon([s["part"]]), "strokes": [s.get("stroke")]}
            for s in plan2.steps(plan)]


def _first(steps: list[dict]) -> dict[str, int]:
    first: dict[str, int] = {}
    for i, s in enumerate(steps):
        for t in s["things"]:
            first.setdefault(t, i)
    return first


def _sign(x: int) -> int:
    return (x > 0) - (x < 0)


def differ(a: list[dict], b: list[dict]) -> dict:
    """How much two plans of one picture differ, from their shapes (1 = the same, on every share):
    - things: the things both name, over the things either names;
    - order: over every pair of things both name, +1 when both plans start them in the same order (or both in one
      step), -1 when in opposite orders, 0 when only one plan starts them together; the mean (Kendall's tau, with
      ties). 1 means the same painting order;
    - sequence: how much of the two step lists lines up, step by step, a step being the things it paints
      (difflib's ratio);
    - moves: the (thing, stroke) pairs both use, over the pairs either uses."""
    fa, fb = _first(a), _first(b)
    shared = sorted(set(fa) & set(fb))
    pairs = [(x, y) for i, x in enumerate(shared) for y in shared[i + 1:]]
    score = 0
    for x, y in pairs:
        sa, sb = _sign(fa[x] - fa[y]), _sign(fb[x] - fb[y])
        score += 1 if sa == sb else (-1 if sa and sb else 0)
    ma = {(t, k) for s in a for t in s["things"] for k in s["strokes"]}
    mb = {(t, k) for s in b for t in s["things"] for k in s["strokes"]}
    ta, tb = ["+".join(s["things"]) for s in a], ["+".join(s["things"]) for s in b]

    def side(steps: list[dict]) -> dict:
        return {"steps": len(steps), "stages": len(dict.fromkeys(s["stage"] for s in steps)),
                "crossing": sum(1 for s in steps if len(s["things"]) > 1)}

    union = set(fa) | set(fb)
    return {"a": side(a), "b": side(b),
            "things": round(len(shared) / len(union), 2) if union else 1.0,
            "only_a": sorted(set(fa) - set(fb)), "only_b": sorted(set(fb) - set(fa)),
            "order": round(score / len(pairs), 2) if pairs else None,
            "sequence": round(difflib.SequenceMatcher(None, ta, tb, autojunk=False).ratio(), 2),
            "moves": round(len(ma & mb) / len(ma | mb), 2) if ma | mb else 1.0}


# ---------------------------------------------------------------------------
# The write-up's numbers
# ---------------------------------------------------------------------------

RESULTS = Path(__file__).with_suffix(".json")
THINGS = Path(__file__).with_name("v3_plan_first_things.json")  # hand-made: each plan's ids -> shared thing names


def results(kept: Path = KEPT, runs: Path = RUNS) -> dict:
    """Gather what's kept under bench/plan-first/<picture>/ (painter-a.json, painter-b.json, and after a fit plan.json
    and lesson.json) with the baseline's plan, into one file of numbers."""
    table = read(THINGS) if THINGS.exists() else {}
    out = {}
    for folder in sorted(p for p in Path(kept).iterdir() if p.is_dir()) if Path(kept).exists() else []:
        picture, names = folder.name, table.get(folder.name) or {}
        plans = {k: read(folder / f"{k}.json") for k in ("painter-a", "painter-b") if (folder / f"{k}.json").exists()}
        run = baseline_run(picture, runs)
        if (run / "plan.json").exists():
            plans["v2"] = read(run / "plan.json")
        if (folder / "plan.json").exists():
            plans["fit"] = read(folder / "plan.json")
        # a fitted plan's parts are the baseline's, plus any it added: the v2 names, then its own
        names["fit"] = {**(names.get("v2") or {}), **(names.get("fit") or {})}
        shapes = {k: shape(p, names.get(k)) for k, p in plans.items()}
        row = {"plans": {k: {"steps": len(s), "stages": len(dict.fromkeys(x["stage"] for x in s)),
                             "crossing": sum(1 for x in s if len(x["things"]) > 1),
                             "things": len(_first(s))} for k, s in shapes.items()},
               "differ": {f"{x} / {y}": differ(shapes[x], shapes[y])
                          for x, y in (("painter-a", "painter-b"), ("painter-a", "v2"), ("painter-b", "v2"))
                          if x in shapes and y in shapes}}
        for k in ("painter-a", "painter-b"):
            if k in plans:
                row["plans"][k]["problems"] = painter_problems(plans[k])
        if "fit" in plans and "painter-a" in plans:
            row["fit"] = {**deviations(plans["painter-a"], plans["fit"]),
                          "problems": fit_problems(plans["painter-a"], plans["fit"]),
                          "parts": len(plans["fit"]["parts"]), "v2_parts": len(plans["v2"]["parts"]) if "v2" in plans else None,
                          "parts_added": sorted({p["id"] for p in plans["fit"]["parts"]}
                                                - {p["id"] for p in (plans.get("v2") or {}).get("parts") or []}),
                          "parts_removed": sorted({p["id"] for p in (plans.get("v2") or {}).get("parts") or []}
                                                  - {p["id"] for p in plans["fit"]["parts"]})}
        out[picture] = row
    write(RESULTS, out)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("painter-check", help="what's wrong with a painter's plan (shape only)")
    p.add_argument("painter")
    p = sub.add_parser("start", help="a bench lesson folder with the painter's plan and the baseline's layers")
    p.add_argument("picture")
    p.add_argument("--painter", required=True)
    p.add_argument("--into", default=str(OUT))
    p = sub.add_parser("check", help="the fit against the painter's plan, then v2's checks on the fitted plan")
    p.add_argument("lesson")
    p = sub.add_parser("fold", help="the fitted lesson as one step per painter's step, for the A/B page and packet")
    p.add_argument("lesson")
    p.add_argument("--out")
    p = sub.add_parser("differ", help="how much two plans of one picture differ")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--things", help="a JSON table {picture: {plan label: {id: shared name}}}")
    p.add_argument("--picture")
    p.add_argument("--labels", nargs=2, default=["painter-a", "painter-b"], help="the two plans' labels in the table")
    sub.add_parser("results", help="write v3_plan_first.json from what's kept under bench/plan-first/")
    a = ap.parse_args(argv)
    if a.cmd == "painter-check":
        problems = painter_problems(read(a.painter))
        out = {"problems": problems, "steps": len(painter_steps(read(a.painter))),
               "crossing": [s["id"] for s in crossing(read(a.painter))]}
    elif a.cmd == "start":
        out = {"lesson": str(start(a.picture, Path(a.painter), Path(a.into))), "problems": []}
    elif a.cmd == "check":
        out = check(Path(a.lesson))
    elif a.cmd == "fold":
        out = {**fold(Path(a.lesson), Path(a.out) if a.out else None), "problems": []}
    elif a.cmd == "differ":
        names = (read(a.things).get(a.picture) or {}) if a.things else {}
        out = differ(shape(read(a.a), names.get(a.labels[0])), shape(read(a.b), names.get(a.labels[1])))
    else:
        out = {"pictures": sorted(results()), "wrote": str(RESULTS.relative_to(ROOT))}
    print(json.dumps(out, indent=1))
    return 1 if out.get("problems") else 0


if __name__ == "__main__":
    sys.exit(main())
