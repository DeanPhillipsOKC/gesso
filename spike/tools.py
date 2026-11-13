"""Gesso lesson tools: one subcommand per tool, for the paint-lesson skill (#10) or a person to call.

    python spike/tools.py --help                      # every tool, with what it's for
    python spike/tools.py render --help               # one tool's options

Every tool writes its image(s) and prints one JSON line on stdout (paths, settings, cost, seconds), so
an agent can call it and read the result. Human-readable progress goes to stderr. A refusal prints
{"refused": "..."} and exits with code 2.

Filters and composites are free and come first (docs/decisions.md, 2026-11-10). `render` calls the
paid image model, so it needs a reason no filter works and stays under the lesson's caps.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run import IMAGE_MODEL, ROOT, Ledger, edit_image, png_bytes, size_for  # noqa: E402

CACHE_DIR = ROOT / "output" / ".render-cache"
DEFAULT_MAX_COST = 1.00  # dollars of renders per lesson
DEFAULT_MAX_REDOS = 2  # renders per step after the first
STEP_WORDS = 110  # a step's instructions past this many words get listed in publish's long_steps
INSTRUCTION_WORDS = 40  # one instruction past this many words gets listed in publish's long_instructions
QUALITIES = ["low", "medium", "high", "xhigh", "max"]
# Worst cost per render seen in the spike's 290 renders (2026-10-19), used before a lesson has its own.
ESTIMATE_USD = {"low": 0.07, "medium": 0.05, "high": 0.08, "xhigh": 0.15, "max": 0.20}


class Refused(Exception):
    """A tool declined to run. Nothing was called and nothing was spent."""


def emit(result: dict) -> None:
    print(json.dumps(result))


# ---------------------------------------------------------------------------
# Lesson ledger: every render, kept in <lesson>/ledger.json between calls
# ---------------------------------------------------------------------------


class LessonLedger:
    """<lesson>/ledger.json. Several tools.py processes may render for one lesson at once, so every change
    takes a lock file and re-reads the ledger first; otherwise the last process to save drops the others'
    entries (seen 2026-11-10: 5 of 8 parallel renders lost)."""

    def __init__(self, lesson: Path):
        self.path = lesson / "ledger.json"
        self.calls: list[dict] = []
        self.reload()

    def reload(self) -> None:
        self.calls = json.loads(self.path.read_text(encoding="utf-8"))["calls"] if self.path.exists() else []

    @contextlib.contextmanager
    def locked(self, timeout: float = 60.0):
        """Exclusive access to the ledger across processes, with the latest calls loaded."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(".lock")
        deadline = time.time() + timeout
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > timeout:  # left behind by a crashed process
                        lock.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.time() > deadline:
                    raise Refused(f"ledger is locked ({lock}); another render seems stuck")
                time.sleep(0.05)
        try:
            self.reload()
            yield self
        finally:
            lock.unlink(missing_ok=True)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"calls": self.calls, "total_cost_usd": self.total_cost}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def append(self, entry: dict) -> None:
        with self.locked():
            self.calls.append(entry)
            self.save()

    @property
    def renders(self) -> list[dict]:
        return [c for c in self.calls if c.get("tool") == "render"]

    @property
    def total_cost(self) -> float:
        return round(sum(c.get("cost_usd", 0) for c in self.calls), 4)

    def paid_renders_for(self, step: str) -> int:
        return sum(1 for c in self.renders if c["step"] == step and not c.get("cached"))

    def estimate(self, quality: str) -> float:
        seen = [c["cost_usd"] for c in self.renders if c.get("quality") == quality and not c.get("cached")]
        return max(seen + [ESTIMATE_USD[quality]])


# ---------------------------------------------------------------------------
# render (#9)
# ---------------------------------------------------------------------------


def cache_key(inputs: list[Path], prompt: str, size: str, quality: str) -> str:
    h = hashlib.sha256()
    for part in (IMAGE_MODEL, prompt, size, quality):
        h.update(part.encode("utf-8") + b"\0")
    for p in inputs:
        h.update(hashlib.sha256(png_bytes(p)).digest())
    return h.hexdigest()


class QuietLedger(Ledger):
    """The spike's ledger, with progress on stderr so stdout stays one JSON line (and threads don't fight
    over a redirected stdout)."""

    def add(self, step, model, seconds, usage, cost):
        self.calls.append({"step": step, "model": model, "seconds": round(seconds, 1), "usage": usage, "cost_usd": round(cost, 4)})
        print(f"  {step}: {seconds:.0f}s, ~${cost:.3f}", file=sys.stderr)


class Budget:
    """The lesson's ledger plus its caps, safe to share between render threads. A render reserves its
    estimated cost before calling, so parallel renders can't overshoot the cap together."""

    def __init__(self, lesson: Path, max_cost: float, max_redos: int):
        self.ledger = LessonLedger(lesson)
        self.max_cost, self.max_redos = max_cost, max_redos
        self.lock = threading.Lock()
        self.reserved = 0.0
        self.reserved_steps: dict[str, int] = {}

    def reserve(self, step: str, quality: str) -> float:
        with self.lock, self.ledger.locked():  # see other processes' renders too
            done = self.ledger.paid_renders_for(step) + self.reserved_steps.get(step, 0)
            if done > self.max_redos:
                raise Refused(f"step '{step}' already has {done} renders (1 plus {self.max_redos} redos). "
                              "Flag it for the owner instead of rendering again.")
            estimate = self.ledger.estimate(quality)
            spent = self.ledger.total_cost + self.reserved
            if spent + estimate > self.max_cost:
                raise Refused(f"lesson has spent ${spent:.2f} of its ${self.max_cost:.2f} cap and a {quality} render "
                              f"can cost up to ${estimate:.2f}. Flag the step for the owner.")
            self.reserved += estimate
            self.reserved_steps[step] = self.reserved_steps.get(step, 0) + 1
            return estimate

    def record(self, entry: dict, estimate: float = 0.0) -> None:
        with self.lock:
            if estimate:
                self.reserved -= estimate
                self.reserved_steps[entry["step"]] -= 1
            self.ledger.append(entry)

    def release(self, step: str, estimate: float) -> None:
        with self.lock:
            self.reserved -= estimate
            self.reserved_steps[step] -= 1


def render_one(budget: Budget, step: str, inputs: list[Path], prompt: str, out: Path, quality: str, reason: str,
               size: str | None = None, fresh: bool = False, client=None) -> dict:
    """One render under the lesson's caps, from the cache when possible. Raises Refused without spending."""
    reason = (reason or "").strip()
    if not reason:
        raise Refused("--why-not-filter is required: say why no filter or composite can make this step.")
    for p in inputs:
        if not p.exists():
            raise Refused(f"input image not found: {p}")
    size = size or size_for(inputs[0])
    key = cache_key(inputs, prompt, size, quality)
    cached = CACHE_DIR / f"{key}.png"
    entry = {"tool": "render", "step": step, "model": IMAGE_MODEL, "quality": quality, "size": size,
             "reason": reason, "inputs": [str(p) for p in inputs], "out": str(out), "cache_key": key}
    out.parent.mkdir(parents=True, exist_ok=True)

    if cached.exists() and not fresh:
        shutil.copyfile(cached, out)
        entry.update(cached=True, seconds=0, cost_usd=0.0)
        budget.record(entry)
    else:
        estimate = budget.reserve(step, quality)
        try:
            tmp = QuietLedger()
            edit_image(step, inputs, prompt, out, size, quality, tmp, client=client)
        except Exception:
            budget.release(step, estimate)
            raise
        call = tmp.calls[-1]
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out, cached)
        entry.update(cached=False, seconds=call["seconds"], cost_usd=call["cost_usd"], usage=call["usage"])
        budget.record(entry, estimate)

    led = budget.ledger
    return {"out": str(out), "step": step, "cached": entry["cached"], "cost_usd": entry["cost_usd"],
            "seconds": entry["seconds"], "lesson_total_usd": led.total_cost,
            "budget_left_usd": round(budget.max_cost - led.total_cost, 4),
            "paid_renders_for_step": led.paid_renders_for(step)}


def render(a: argparse.Namespace, client=None) -> dict:
    lesson = Path(a.lesson)
    out = Path(a.out) if a.out else lesson / f"{a.step}.png"
    budget = Budget(lesson, a.max_cost, a.max_redos)
    return render_one(budget, a.step, [Path(p) for p in a.inputs], a.prompt, out, a.quality, a.why_not_filter,
                      a.size, a.fresh, client)


def add_render(sub) -> None:
    p = sub.add_parser(
        "render", help="PAID. Use only when no filter or composite can make the step; needs --why-not-filter.",
        description="Render a step with the image model from one or more input images. Costs money, so it needs a "
                    "reason, records every call in <lesson>/ledger.json, and refuses past the lesson's caps. The same "
                    "inputs, prompt, size, and quality come back free from the cache unless --fresh.")
    p.add_argument("--lesson", required=True, help="lesson folder; holds ledger.json")
    p.add_argument("--step", required=True, help="step id, e.g. sky-gradient; redos are counted per step")
    p.add_argument("--inputs", nargs="+", required=True, help="input images (first one sets the size)")
    p.add_argument("--prompt", required=True)
    p.add_argument("--why-not-filter", help="required: why no filter or composite can make this step")
    p.add_argument("--quality", choices=QUALITIES, default="low", help="low while experimenting (docs/decisions.md)")
    p.add_argument("--size", help="e.g. 1024x1536; default matches the first input's shape")
    p.add_argument("--out", help="output path; default <lesson>/<step>.png")
    p.add_argument("--max-cost", type=float, default=DEFAULT_MAX_COST, help=f"dollar cap per lesson (default {DEFAULT_MAX_COST:.2f})")
    p.add_argument("--max-redos", type=int, default=DEFAULT_MAX_REDOS, help=f"redos per step (default {DEFAULT_MAX_REDOS})")
    p.add_argument("--fresh", action="store_true", help="skip the cache and pay for a new render")
    p.set_defaults(func=render)


# ---------------------------------------------------------------------------
# Lesson files (#10): plan.json in, step images and lesson.html out
# ---------------------------------------------------------------------------
#
# <lesson>/plan.json     written by the skill: the spike's LessonPlan fields plus "photo" and "technique" paths
#                        (relative to the repo) and "quality"
# <lesson>/99_finish.png the finished painting; every step copies from it
# <lesson>/00_canvas.png plain white canvas (made on first use)
# <lesson>/NN_<id>.png   step images, NN from 01
# <lesson>/text.json     written by the skill: {"steps": [{stage_id, what_to_do, mixes, watch_out, paint_notes,
#                        made_with, reason, brushes: [{brush, use}], strokes: [{name, how}]}]}
# <lesson>/review.json   optional, written by the skill: {"finish_issues": [...], "review_issues": [...]}


def load_plan(lesson: Path):
    """(plan.json as written, the plan as a version 1 LessonPlan, the technique). A version 2 plan is checked with
    plan2.problems and seen as version 1 through publish2.as_v1, so mix, publish, and the seal read either."""
    import yaml
    import plan2
    from run import LessonPlan

    raw = json.loads((lesson / "plan.json").read_text(encoding="utf-8"))
    technique = yaml.safe_load((ROOT / raw["technique"]).read_text(encoding="utf-8"))
    if raw.get("palette"):  # the painter's own tubes (palettes/<name>.yaml) instead of the technique's five
        technique["palette"], technique["palette_name"] = load_palette(raw["palette"])
    if plan2.is_v2(lesson):
        import publish2
        wrong = plan2.problems(raw)
        if wrong:
            raise Refused("fix plan.json first: " + " | ".join(wrong))
        return raw, publish2.as_v1(raw), technique
    return raw, LessonPlan.model_validate(raw), technique


def load_palette(name: str) -> tuple[list[str], str]:
    """palettes/<name>.yaml -> (tube names, palette title), with each tube's color registered for the mixer."""
    import mixing
    import yaml

    path = ROOT / "palettes" / f"{name}.yaml" if not name.endswith(".yaml") else ROOT / name
    if not path.exists():
        raise Refused(f"no palette at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return mixing.register(data["tubes"]), data.get("name", name)


def step_paths(lesson: Path, plan) -> list[Path]:
    """NN_<id>.png for every step. In version 1 the last step is the finish itself; in version 2 build-steps writes
    the last step as its own copy of the finish."""
    import plan2

    paths = [lesson / f"{i + 1:02d}_{s.id}.png" for i, s in enumerate(plan.steps)]
    if not plan2.is_v2(lesson):
        paths[-1] = lesson / "99_finish.png"
    return paths


def render_step(a: argparse.Namespace, client=None) -> dict:
    """Render planned steps with the spike's step prompt, all at once (parallel) or each from the next (anchored)."""
    from concurrent.futures import ThreadPoolExecutor

    from PIL import Image

    from run import planned_prompt

    lesson = Path(a.lesson)
    raw, plan, technique = load_plan(lesson)
    ids = [s.id for s in plan.steps]
    finish = lesson / "99_finish.png"
    if not finish.exists():
        raise Refused(f"no finished painting at {finish}; make it first")
    unknown = [x for x in a.steps if x not in ids]
    if unknown:
        raise Refused(f"unknown step ids {unknown}; plan has {ids}")
    if ids[-1] in a.steps:
        raise Refused(f"'{ids[-1]}' is the last step, which is the finished painting itself")
    if a.fix and len(a.steps) != 1:
        raise Refused("--fix applies to one step at a time")
    canvas = lesson / "00_canvas.png"
    if not canvas.exists():
        Image.new("RGB", Image.open(finish).size, (246, 245, 240)).save(canvas)
    paths = step_paths(lesson, plan)
    budget = Budget(lesson, a.max_cost, a.max_redos)

    def one(step_id: str) -> dict:
        i = ids.index(step_id)
        s = plan.steps[i]
        later = paths[i + 1]
        anchored = a.mode == "anchored" and later != finish
        if anchored and not later.exists():
            return {"step": s.id, "refused": f"anchored mode needs the next step's image first: {later.name}"}
        base = later if anchored else finish
        inputs = ([base] if s.covers_canvas else [base, canvas]) + ([finish] if anchored else [])
        prompt = planned_prompt(technique, s, anchored, [t.paints for t in plan.steps[: i + 1]],
                                [t.paints for t in plan.steps[i + 1:]], a.fix or "")
        try:
            return render_one(budget, s.id, inputs, prompt, paths[i], a.quality, a.why_not_filter, None, a.fresh, client)
        except Refused as e:
            return {"step": s.id, "refused": str(e)}

    if not (a.why_not_filter or "").strip():
        raise Refused("--why-not-filter is required: say why no filter or composite can make these steps.")
    order = sorted(a.steps, key=ids.index, reverse=True)  # latest first, so anchored steps can chain
    if a.mode == "parallel":
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(one, order))
    else:
        results = [one(x) for x in order]
    led = budget.ledger
    return {"steps": results, "lesson_total_usd": led.total_cost, "budget_left_usd": round(a.max_cost - led.total_cost, 4)}


def duplicate_recipes(mixes: dict[str, dict]) -> list[list[str]]:
    import mixing

    names = list(mixes)
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ma, mb = mixes[a], mixes[b]
            if ma["parts"] == mb["parts"] or mixing.delta_e(ma["mixed_hex"], mb["mixed_hex"]) < 3:
                out.append([a, b])
    return out


def paints_not_listed(stages: list[dict], paints: dict, word: bool = True) -> list[dict]:
    """Paints a step's instructions or values table name that aren't in its colors, so their recipe never shows.
    Version 1 matched a name between two backspace characters (a "\\b" lost in an rf-string), so it never found one
    in the text; it keeps that (word=False) so a version 1 lesson publishes and seals as before."""
    edge = r"\b" if word else "\x08"

    def said(n: str, text: str) -> bool:
        if word:  # "Sea turquoise" inside "Light sea turquoise" is the other paint, not this one
            for longer in sorted((m for m in paints if m != n and n.lower() in m.lower()), key=len, reverse=True):
                text = re.sub(re.escape(longer), " ", text, flags=re.I)
        return bool(re.search(edge + re.escape(n) + edge, text, re.I))

    return [{"id": st["id"], "paint": n} for st in stages for n in paints
            if n not in {c["name"] for c in st["colors"]}
            and (said(n, " ".join(st["steps"])) or any(v.get("paint") == n for v in st.get("values", [])))]


def undocumented_diagrams(stages: list[dict], notes: dict) -> list[str]:
    """Steps with a diagram the skill's beginner check didn't explain."""
    check = notes.get("beginner_check") or {}
    return [st["id"] for st in stages if st["construct"] and st["id"] not in
            ((check.get("diagrams") or {}) if isinstance(check, dict) else {})]


def texture_jumps(lesson: Path, paths: list[Path]) -> list[dict]:
    import numpy as np
    from PIL import Image

    import passes

    out, prev = [], None
    for p in paths:
        img = Image.open(p).convert("RGB")
        img.thumbnail((640, 640))
        cur = np.asarray(img)
        if prev is not None and prev.shape == cur.shape:
            share = passes.texture_jump(prev, cur)
            if share > passes.JUMP:
                out.append({"step": p.stem.split("_", 1)[-1], "share": round(share, 3)})
        prev = cur
    return out


def tubes_used(palette: list[str], paints) -> list[str]:
    used = {t for p in paints for t in ((p.get("mix") or {}).get("parts") or {})}
    return [t for t in palette if t in used]


def compute_mixes(lesson: Path, plan, technique) -> dict[str, dict]:
    """Solve every paint's recipe from the palette tubes against its swatch (#22), and write <lesson>/mixes.json.
    The swatches must already be snapped to the finish (sample_swatches)."""
    import mixing

    tubes = technique.get("palette", [])
    try:
        for t in tubes:
            mixing.tube_rgb(t)
    except mixing.UnknownTube as err:
        raise Refused(str(err)) from err
    straight = {p.name: mixing.single_tube(p.name, p.recipe, tubes) for p in plan.paints}
    solved = mixing.solve_lesson({p.name: p.hex for p in plan.paints if not straight[p.name]}, tubes)
    mixes = {}
    for p in plan.paints:
        m = mixing.straight(straight[p.name], p.hex) if straight[p.name] else solved[p.name]
        m["guess_recipe"] = p.recipe
        mixes[p.name] = m
    (lesson / "mixes.json").write_text(json.dumps(mixes, indent=2), encoding="utf-8")
    return mixes


def mix_tool(a: argparse.Namespace) -> dict:
    """Compute the paint recipes for a lesson, so the skill can see them before writing the step text."""
    import plan2
    from run import sample_swatches

    lesson = Path(a.lesson)
    raw, plan, technique = load_plan(lesson)
    finish = lesson / "99_finish.png"
    if not finish.exists():
        raise Refused(f"no finished painting at {finish}; the swatches are sampled from it")
    if not plan2.is_v2(lesson):  # a version 2 paint's hex is already measured from the finish
        sample_swatches(plan, finish)
    mixes = compute_mixes(lesson, plan, technique)
    return {"json": str(lesson / "mixes.json"), "cost_usd": 0.0,
            "paints": [{"name": n, "recipe": m["text"], "target": m["target_hex"], "mixed": m["mixed_hex"],
                        "delta_e": m["delta_e"], "reachable": m["reachable"], "your_recipe": m["guess_recipe"]}
                       for n, m in mixes.items()],
            "unreachable": [n for n, m in mixes.items() if not m["reachable"]]}


NOTES_REQUIRED = ("read", "technique", "order", "steps", "beginner_check")


def seal_problems(lesson: Path, plan, text: dict, review: dict, notes: dict, checks: dict) -> list[str]:
    """What stops a lesson being sealed hands-off: the rules the skill asks for, checked instead of remembered
    (two hands-off runs, 2026-11-12, each let a small rule slip late in a long run).
    A version 2 lesson has no image review and no regions, and no word limit on a step (design section 13)."""
    import plan2

    v2 = plan2.is_v2(lesson)
    out = []
    ids = [s.id for s in plan.steps]
    review_step = "step 7b" if v2 else "step 6b"  # the v2 skill's text review is its step 7b
    if not (lesson / "review.json").exists():
        out.append("review.json is missing (" + ("step 7b" if v2 else "steps 2, 5, 6b") + ")")
    for key in ("finish_issues", "text_issues") if v2 else ("finish_issues", "review_issues", "text_issues"):
        if key not in review:
            out.append(f"review.json has no {key} (an empty list if there were none)")
    if not (lesson / "trials" / "review" / "review.json").exists():
        out.append(f"the text review ({review_step}) hasn't run: no trials/review/review.json")
    for key in NOTES_REQUIRED:
        if not notes.get(key):
            out.append(f"notes.json is missing {key} (step 8)")
    bc = notes.get("beginner_check") or {}
    if not isinstance(bc, dict):  # a note in another shape is shown on the page as text, but can't be checked
        out.append("notes.json beginner_check must be a dict with summary, diagrams, and no_diagram (step 8)")
        bc = {"no_diagram": {sid: "" for sid in ids}}
    seen = set(bc.get("diagrams") or {}) | set(bc.get("no_diagram") or {})
    for sid in ids:
        if sid not in (notes.get("steps") or {}):
            out.append(f"notes.json steps has no entry for {sid}")
        if bc and sid not in seen:
            out.append(f"beginner_check doesn't say whether {sid} needs a diagram")
        t = text.get(sid)
        if t is None:
            out.append(f"text.json has no step {sid}")
            continue
        # version 2 text is its lines; its strokes come from the plan's stroke and the cards
        for key in ("summary", "lines", "brushes", "made_with") if v2 else ("summary", "brushes", "strokes", "made_with"):
            if not t.get(key) and not (key == "strokes" and sid == ids[-1]):
                out.append(f"{sid}: text.json has no {key}")
    for s in plan.steps:
        if not s.regions and not v2:
            out.append(f"{s.id}: no regions in plan.json")
    for key in ("texture_jumps", "paints_not_listed", "duplicate_recipes", "undocumented_diagrams", "long_instructions"):
        if checks.get(key):
            out.append(f"{key}: {checks[key]}")
    if checks.get("missing_aids"):
        out.append("aids/aids.json is missing or was made for other steps: run step-aids, then publish --final again")
    kept = notes.get("long_steps_kept") or {}
    long = [x for x in checks.get("long_steps") or [] if x["id"] not in kept]  # (publish doesn't list them for version 2)
    if long:
        out.append(f"long_steps not cut or explained in notes.long_steps_kept: {long}")
    noted = " ".join(n for t in text.values() for n in (t.get("paint_notes") or [])).lower()
    for name in checks.get("unreachable_paints") or []:
        if name.lower() not in noted:
            out.append(f"{name} can't be mixed from these tubes and no step's paint_notes says so")
    return out


CHECKED = ("texture_jumps", "paints_not_listed", "duplicate_recipes", "undocumented_diagrams", "long_instructions",
           "missing_aids", "unreachable_paints")  # publish's counts that `check` reports for a version 2 lesson


def publish(a: argparse.Namespace) -> dict:
    """Build lesson.json and lesson.html from plan.json, text.json, the images, and the ledger."""
    import plan2
    import publish2
    from lesson_page import page
    from run import CLAUDE_MODEL, sample_swatches

    lesson = Path(a.lesson)
    v2 = plan2.is_v2(lesson)
    raw, plan, technique = load_plan(lesson)
    paths = step_paths(lesson, plan)
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise Refused(f"missing step images: {missing}" + (f". Run build-steps --lesson {lesson}." if v2 else ""))
    if not v2:  # a version 2 paint's hex is already measured from the finish
        sample_swatches(plan, paths[-1])
    mixes = compute_mixes(lesson, plan, technique)
    text_path = lesson / "text.json"
    text = {t["stage_id"]: t for t in json.loads(text_path.read_text(encoding="utf-8"))["steps"]} if text_path.exists() else {}
    review_path = lesson / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
    notes_path = lesson / "notes.json"  # the skill's reasoning: technique, order, filters, throwaways
    notes = json.loads(notes_path.read_text(encoding="utf-8")) if notes_path.exists() else {}
    led = LessonLedger(lesson)

    extras = publish2.paint_extras(raw) if v2 else {}  # a version 2 paint keeps its id and parts beside the v1 keys

    def paint_dict(p) -> dict:
        d = {**extras.get(p.name, {}), **p.model_dump()}
        m = mixes.get(p.name)
        if m:  # the computed recipe replaces the one written by eye, which is kept for the notes
            d.update(guess_recipe=d["recipe"], recipe=m["text"], mix=m)
        return d

    paints = {p.name: paint_dict(p) for p in plan.paints}

    photo = ROOT / raw["photo"]
    photo_copy = lesson / f"photo{photo.suffix}"
    if photo.exists() and not photo_copy.exists():
        shutil.copyfile(photo, photo_copy)

    def txt(s, key, default):
        return text[s.id].get(key, default) if s.id in text else default

    view = canvas_view(lesson, [p.name for p in paths])
    prune_canvas_view(lesson, [p.name for p in paths])
    stages = [
        {
            "id": s.id, "name": s.name, "image": view.get(paths[i].name, paths[i].name), "paints": s.paints, "looks_like": s.looks_like,
            "steps": txt(s, "what_to_do", s.how), "mixes": txt(s, "mixes", []),
            "colors": [paints[c] for c in s.colors if c in paints],
            "paint_notes": txt(s, "paint_notes", []), "watch_out": txt(s, "watch_out", s.watch_out),
            "brushes": s.brushes, "dry_time": technique["dry_time"],
            "made_with": txt(s, "made_with", "render"), "reason": txt(s, "reason", ""), "summary": txt(s, "summary", ""), "values": txt(s, "values", []),
            "brush_list": txt(s, "brushes", []), "strokes": txt(s, "strokes", []), "construct": txt(s, "construct", {}),
        }
        for i, s in enumerate(plan.steps)
    ] if not v2 else publish2.stages(raw, text, paints, [view.get(p.name, p.name) for p in paths], technique, lesson)
    from version import stamp
    old = lesson / "lesson.json"
    from version import with_made
    old_stamp = (json.loads(old.read_text(encoding="utf-8")).get("gesso") or {}) if old.exists() else None
    previous = old_stamp.get("version", "before stamps") if old_stamp is not None else None
    lesson_data = {
        "gesso": with_made(stamp(), old_stamp or None),
        "canvas": _v2_canvas(lesson)[1] if v2 else
                  (json.loads((lesson / "canvas.json").read_text(encoding="utf-8")) if (lesson / "canvas.json").exists() else {}).get("canvas"),
        "photo": photo.name, "photo_file": photo_copy.name if photo_copy.exists() else "", "technique": technique["id"], "mode": "paint-lesson skill", "variant": "claude-code",
        "quality": raw.get("quality", "low"), "image_model": IMAGE_MODEL, "claude_model": f"{CLAUDE_MODEL} (Claude Code)",
        "photo_read": {"subject": plan.subject, "focal_point": plan.focal_point, "light": plan.light,
                       "components": plan.components, "mixes": list(paints.values())},
        "finish_issues": review.get("finish_issues", []), "review_issues": review.get("review_issues", []),
        "text_issues": review.get("text_issues", []),
        # the tubes to buy or get out: with a painter's big palette, only the ones the recipes use
        "tubes": tubes_used(technique["palette"], paints.values()) if technique.get("palette_name") else technique.get("palette", []),
        "palette_name": technique.get("palette_name", ""),
        "notes": notes, "stages": stages, "calls": led.calls, "total_cost_usd": led.total_cost,
        "total_seconds": round(sum(c.get("seconds", 0) for c in led.calls), 1),
    }
    if v2:  # new keys beside the version 1 ones: the plan's stages, for the page's headings, and the step aids
        lesson_data.update(plan_version=2, groups=publish2.groups(raw), aids=publish2.attach_aids(lesson, stages))
        import elements

        if any(p.get("element") for p in raw.get("parts") or []):  # the technique picks (#12), for the owner's review
            lesson_data["technique_picks"] = {"technique_why": raw.get("technique_why", ""), "parts": elements.picks(raw)}
        if review.get("review_context"):  # "same": no fresh reviewer could be started; Known problems says so
            lesson_data["review_context"] = review["review_context"]
    import provenance
    lesson_data["provenance"] = provenance.of(lesson, lesson_data)
    (lesson / "lesson.json").write_text(json.dumps(lesson_data, indent=2), encoding="utf-8")
    (lesson / "lesson.html").write_text(page(lesson_data, technique, lesson), encoding="utf-8")
    artifact = lesson / "lesson-artifact.html"
    artifact.write_text(page(lesson_data, technique, lesson, embed=True), encoding="utf-8")
    # one self-contained HTML document (images inlined), for the lessons site or to send as a file
    standalone = page(lesson_data, technique, lesson, embed=True, standalone=True)
    (lesson / "lesson-standalone.html").write_text(standalone, encoding="utf-8")
    if v2 and len(standalone.encode("utf-8")) > publish2.MAX_PAGE_BYTES:
        raise Refused(f"the page is {len(standalone.encode('utf-8')) / 1e6:.1f} MB, over the {publish2.MAX_PAGE_BYTES / 1e6:g} MB "
                      "a phone should load. Merge small steps in the plan, or lower aids.CLOSE_UP so fewer steps get a "
                      "close-up, then run build-steps, step-aids, and publish again.")
    from lesson_embed import export
    embed = export(lesson_data, technique, lesson)  # one folder a blog post or another page can show as a walkthrough

    by_source: dict[str, int] = {}
    for st in stages:
        k = st["made_with"].split(":")[0]
        by_source[k] = by_source.get(k, 0) + 1
    renders = [c for c in led.calls if c.get("tool") == "render"]
    if v2:
        import checks
        jumps = checks.texture_jumps(lesson, raw)
    else:
        jumps = texture_jumps(lesson, paths)
    result = {"html": str(lesson / "lesson.html"), "artifact": str(artifact),
            "artifact_mb": round(artifact.stat().st_size / 1e6, 2), "embed": embed,
            "gesso": lesson_data["gesso"], "provenance": lesson_data["provenance"], "previous_version": previous, "steps": len(stages), "steps_by_source": by_source,
            "diagrams": sum(1 for st in stages if st["construct"]),
            # a diagram the page can't explain: the skill's beginner check didn't write down why
            "undocumented_diagrams": undocumented_diagrams(stages, notes),
            "unreachable_paints": [n for n, m in mixes.items() if not m["reachable"]],
            # steps whose instructions run past the word budget in the skill (about 100 words)
            # (not checked for version 2: no word limit on a step, design section 10)
            "long_steps": [{"id": st["id"], "words": n} for st in stages
                           if (n := sum(len(x.split()) for x in st["steps"])) > STEP_WORDS and not v2],
            # paints an instruction or values table names that aren't in the step's colors, so their recipe never shows
            "paints_not_listed": paints_not_listed(stages, paints, word=v2),
            # paints whose computed recipes come out the same (or mix within Delta E 3): two names, one color
            "duplicate_recipes": duplicate_recipes(mixes),
            # steps that turn a big area from flat to textured at once: split them with split-texture (version 2:
            # the same list check reports, which leaves out flat coats)
            "texture_jumps": jumps,
            # single instructions past the skill's budget (about 35 words): usually two moves to split
            "long_instructions": [{"id": st["id"], "n": k + 1, "words": len(x.split())} for st in stages
                                  for k, x in enumerate(st["steps"]) if len(x.split()) > INSTRUCTION_WORDS],
            "paid_renders": sum(1 for c in renders if not c.get("cached")),
            "cached_renders": sum(1 for c in renders if c.get("cached")), "image_cost_usd": led.total_cost}
    if v2:  # the step's teaching pictures (step-aids), and the page's size
        result.update(missing_aids=not lesson_data.get("aids"), page_mb=round(len(standalone.encode("utf-8")) / 1e6, 2))
        import checks
        found = checks.run(lesson, text)  # every measured check in one list (design section 12)
        result.update(check=found["failures"], check_notes=found["notes"])
    if getattr(a, "final", False):  # the skill's last publish: check everything, then seal it hands-off
        if v2:  # what check already reports (in its own words), left out of the seal's list so it isn't said twice
            problems = seal_problems(lesson, plan, text, review, notes,
                                     {k: v for k, v in result.items() if k not in CHECKED}) + result["check"]
        else:
            problems = seal_problems(lesson, plan, text, review, notes, result)
        if problems:
            raise Refused("not sealed; fix these and run publish --final again: " + " | ".join(problems))
        provenance.seal(lesson, lesson_data)
        lesson_data["provenance"] = result["provenance"] = provenance.of(lesson, lesson_data)
        (lesson / "lesson.json").write_text(json.dumps(lesson_data, indent=2), encoding="utf-8")
    # every publish that changes the lesson is kept, with its version (site/history/, owner, 2026-11-12)
    # ... but only a real run's: a scratch or test folder published from elsewhere wrote into the real site/history/.
    # GESSO_HISTORY (tests set it to a temp folder) records anywhere.
    if history_wanted(lesson):
        from history import record
        result["history"] = record(lesson, lesson_data, result)
    else:
        result["history"] = "skipped: not under output/"
    return result


def history_wanted(lesson: Path) -> bool:
    """Whether publish records this lesson in the lesson history: a run under the repo's output/ folder, or anything
    when GESSO_HISTORY points the history somewhere else."""
    if os.environ.get("GESSO_HISTORY"):
        return True
    return (ROOT / "output").resolve() in Path(lesson).resolve().parents


BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome", "/usr/bin/chromium"]


def preview_diagrams(a: argparse.Namespace) -> dict:
    """Draw every construction diagram next to its step image, as HTML and (with Chrome or Edge) a PNG to Read."""
    import subprocess
    from construct import strip
    from lesson_page import STYLE, image_src

    lesson = Path(a.lesson)
    data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8")) if (lesson / "lesson.json").exists() else None
    if not data:
        raise Refused("run publish first: the preview reads lesson.json")
    paints = {m["name"]: m["hex"] for m in data["photo_read"]["mixes"]}
    rows = []
    for i, st in enumerate(data["stages"], 1):
        html = strip(st.get("construct"), paints, st["id"])
        if st.get("construct") and not html:
            html = '<p class="flag">This spec is broken: it draws nothing. Check its shapes and path data.</p>'
        if html:
            rows.append(f'<section style="display:grid;grid-template-columns:320px 1fr;gap:16px;align-items:start">'
                        f'<figure><img src="{image_src(lesson, st["image"], True, 640)}" alt=""><figcaption>Step {i}: '
                        f'{st["name"]}</figcaption></figure><div style="display:grid">{html}</div></section>')
    trials = lesson / "trials"
    trials.mkdir(exist_ok=True)
    page = trials / "diagrams.html"
    page.write_text(f'<!doctype html><meta charset="utf-8"><style>{STYLE}</style><body><div class="wrap" '
                    f'style="max-width:1200px">{"".join(rows) or "<p>No diagrams.</p>"}</div></body>', encoding="utf-8")
    result = {"diagrams": len(rows), "html": str(page), "png": None}
    browser = next((b for b in BROWSERS if Path(b).exists()), None)
    if browser and rows:
        png = trials / "diagrams.png"
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-color-profile=srgb",
                        f"--window-size=1240,{120 + 380 * len(rows)}", f"--screenshot={png.resolve()}",
                        page.resolve().as_uri()], capture_output=True, timeout=120)
        result["png"] = str(png) if png.exists() else None
    if not rows:
        result["note"] = ("No diagrams in lesson.json. If you just added `construct` to text.json, run publish first: "
                          "this preview reads the published lesson.json.")
    elif not result["png"]:
        result["note"] = "No PNG: no Chrome or Edge found. Open the HTML in a browser, or serve the folder and look."
    return result


def fit_canvas(a: argparse.Namespace) -> dict:
    """Fit the photo to the painter's canvas (and the model's frame) before planning."""
    import canvas as cv
    from PIL import Image, ImageOps

    lesson = Path(a.lesson)
    lesson.mkdir(parents=True, exist_ok=True)
    src = Path(a.input)
    if not src.exists():
        raise Refused(f"input image not found: {src}")
    img = ImageOps.exif_transpose(Image.open(src))
    # No --canvas: the standard size closest to the photo's shape, so every lesson can say where in inches (#122).
    size = a.canvas or cv.default_size(img.width / img.height, a.orientation)
    try:
        r = cv.fit(img, size, tuple(a.focus), tuple(a.keep) if a.keep else None, a.orientation)
    except ValueError as err:
        raise Refused(str(err)) from err
    out = lesson / "00_canvas_frame.png"
    r.pop("frame").save(out)
    info = {**r, "chosen": "given" if a.canvas else "default", "input": str(src), "frame": str(out), "why": a.why,
            "grid_note": cv.grid_note(r["canvas"])}
    (lesson / "canvas.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    LessonLedger(lesson).append({"tool": "filter", "filter": "fit-canvas", "step": "", "why": a.why, "input": str(src),
                                 "out": str(out), "settings": {"canvas": size, "chosen": info["chosen"], "mode": r["mode"]},
                                 "cost_usd": 0.0})
    advice = ("The frame is the photo as is: use it as the photo." if not r["needs_render"] else
              "Render once to fill the flat gray areas, then use the result as the photo: "
              f"render --step canvas --inputs {out} --quality medium --out {lesson / '00_canvas_fit.png'} "
              '--why-not-filter "no filter can paint the scene past the edges of the picture" --prompt "Replace every '
              "flat gray area by continuing the painting naturally: the same sky, land, water, and light, in the same "
              'style and brushwork. Change nothing that is already painted. No new objects."')
    return {**{k: v for k, v in info.items() if k != "why"}, "advice": advice, "cost_usd": 0.0}


def insert_steps(lesson: Path, before_id: str, new_steps: list[dict], images: list) -> list[str]:
    """Insert planned steps (with their pictures) before `before_id`, renumbering every step image after them, and
    their raw copies and lock record, so splitting a step is one call (#41)."""
    from PIL import Image

    raw = json.loads((lesson / "plan.json").read_text(encoding="utf-8"))
    _, plan, _ = load_plan(lesson)
    ids = [s.id for s in plan.steps]
    if before_id not in ids:
        raise Refused(f"unknown step {before_id}; plan has {ids}")
    if before_id == ids[-1]:
        raise Refused("can't insert before the finish this way; split the step before it")
    old = step_paths(lesson, plan)
    at = ids.index(before_id)
    raw["steps"][at:at] = new_steps
    raw_dir, state_path = lesson / "trials" / "raw", lesson / "trials" / "raw" / "locked.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    # rename from the last step backward so nothing is overwritten
    moves = []
    for i in range(len(old) - 2, at - 1, -1):  # every planned step image from `at` on, not the finish
        src = old[i]
        dst = lesson / f"{i + 1 + len(new_steps):02d}_{plan.steps[i].id}.png"
        moves.append((src, dst))
    for src, dst in moves:
        for folder in (lesson, raw_dir):
            a_, b_ = folder / src.name, folder / dst.name
            if a_.exists():
                a_.replace(b_)
        if src.name in state:
            state[dst.name] = state.pop(src.name)
    names = []
    for k, (step, img) in enumerate(zip(new_steps, images)):
        path = lesson / f"{at + 1 + k:02d}_{step['id']}.png"
        Image.fromarray(img).save(path)
        names.append(path.name)
    if state:
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    (lesson / "plan.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    return names


def split_texture(a: argparse.Namespace) -> dict:
    """Free in-between passes for a step that jumps from flat to textured: its new marks arrive darkest first."""
    import numpy as np
    from PIL import Image

    import passes

    lesson = Path(a.lesson)
    raw, plan, _ = load_plan(lesson)
    ids = [s.id for s in plan.steps]
    if a.step not in ids or ids.index(a.step) == 0:
        raise Refused(f"pick a step after the first; plan has {ids}")
    paths = step_paths(lesson, plan)
    i = ids.index(a.step)
    before = np.asarray(Image.open(paths[i - 1]).convert("RGB"))
    after = np.asarray(Image.open(paths[i]).convert("RGB").resize(before.shape[1::-1]))
    mids = passes.value_passes(before, after, len(a.ids) + 1)
    target = raw["steps"][i]
    n = len(a.ids) + 1
    which = ["the darkest", "the mid-dark", "the middle", "the lighter"]
    new = [{**{k: target[k] for k in ("brushes", "regions", "protect") if k in target},
            # its own pass, not a copy of the parent's: the skill writes its colors and text from its picture
            "colors": [], "paints": f"{which[min(k, 3)]} marks of: {target.get('paints', '')}",
            "id": sid, "name": name, "looks_like": f"pass {k + 1} of {n}: {which[min(k, 3)]} marks only, over the base",
            "covers_canvas": target.get("covers_canvas", False), "how": [], "watch_out": []}
           for k, (sid, name) in enumerate(zip(a.ids, a.names))]
    names = insert_steps(lesson, a.step, new, mids)
    chain = [before] + mids + [after]
    return {"inserted": names, "before": a.step, "cost_usd": 0.0,
            "texture_jumps": [round(passes.texture_jump(x, y), 3) for x, y in zip(chain, chain[1:])],
            "next": "give each new step its colors in plan.json and its own text in text.json, from its picture (only "
                    "the marks it adds, darkest first); trim the original step's text to only what it still adds; then "
                    "lock-steps, publish, step-pairs"}


def carry_forward(a: argparse.Namespace) -> dict:
    """Copy a later step's pixels inside boxes onto an earlier step, so a subject's shape and markings match from
    the step that paints them on. Free (chickadee, 2026-11-11: the head step's cap and cheek band differed from the
    feather step's; the head step was made from the feather step's head on the body step's plain bird)."""
    import cv2
    import numpy as np
    from PIL import Image

    lesson = Path(a.lesson)
    _, plan, _ = load_plan(lesson)
    ids = [s.id for s in plan.steps]
    for sid in (a.source, a.target):
        if sid not in ids:
            raise Refused(f"unknown step {sid}; plan has {ids}")
    if ids.index(a.source) <= ids.index(a.target):
        raise Refused("--from must be a later step than --to")
    paths = step_paths(lesson, plan)
    to_path, from_path = paths[ids.index(a.target)], paths[ids.index(a.source)]
    dst = np.asarray(Image.open(to_path).convert("RGB")).astype(np.float32)
    src = np.asarray(Image.open(from_path).convert("RGB").resize(dst.shape[1::-1])).astype(np.float32)
    h, w = dst.shape[:2]
    mask = np.zeros((h, w), np.float32)
    for x0, y0, x1, y1 in a.box:
        mask[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = 1
    mask = cv2.GaussianBlur(mask, (0, 0), 3)[..., None]
    Image.fromarray(np.clip(dst * (1 - mask) + src * mask, 0, 255).astype(np.uint8)).save(to_path)
    LessonLedger(lesson).append({"tool": "filter", "filter": "carry-forward", "step": a.target, "why": a.why,
                                 "input": str(from_path), "out": str(to_path), "settings": {"box": a.box}, "cost_usd": 0.0})
    return {"out": str(to_path), "from": a.source, "cost_usd": 0.0,
            "next": "lock-steps, then publish and step-pairs, and look at the subject across its steps"}


def finish_from_step(a: argparse.Namespace, client=None) -> dict:
    """Rebuild the finished painting from the last step, adding only what the last step paints, so the subject
    can't change shape at the very end (chickadee, 2026-11-11: the finish drew the bird smaller and more upright
    than every step before it). The old finish is kept in trials/."""
    lesson = Path(a.lesson)
    _, plan, technique = load_plan(lesson)
    paths = step_paths(lesson, plan)
    base = paths[-2]
    if not base.exists():
        raise Refused(f"missing {base.name}")
    finish = paths[-1]
    keep = lesson / "trials" / f"99_finish_before_{time.strftime('%H%M%S')}.png"
    keep.parent.mkdir(parents=True, exist_ok=True)
    if finish.exists():
        shutil.copyfile(finish, keep)
    prompt = (f"This is a nearly finished acrylic painting. Add only: {a.add}. Change nothing else: keep every "
              f"shape, size, position, color, and brushstroke exactly as it is. {technique.get('framing', '')}")
    budget = Budget(lesson, a.max_cost, a.max_redos)
    out = lesson / "trials" / "finish_from_step.png"
    r = render_one(budget, "finish", [base], prompt, out, a.quality, a.why_not_filter, None, False, client)
    from PIL import Image

    Image.open(out).convert("RGB").resize(Image.open(base).size).save(finish)
    return {**r, "finish": str(finish), "previous_finish": str(keep),
            "next": "read the new finish against the last step: only the listed details added. Then sample swatches "
                    "again (mix), lock-steps, publish, step-pairs"}


def from_finish_tool(a: argparse.Namespace) -> dict:
    """Every step picture cut from the finished painting (#8): no renders, nothing can drift. Copies the lesson to a
    new run folder first, so the rendered lesson stays as it was and both show in the lesson history."""
    import datetime as dt
    import numpy as np
    from PIL import Image
    from from_finish import build

    src = Path(a.lesson)
    if a.in_place:
        # the skill's own step 6a, inside its run: the same lesson, so it can still be sealed hands-off
        if (src / "sealed.json").exists():
            raise Refused("this lesson is sealed; a change now would mark it edited. Make a new run, or a recut "
                          "without --in-place.")
        dst = src
    else:
        stem = src.name.split("_skill_")[0]
        dst = src.parent / f"{stem}_skill_{dt.datetime.now():%Y%m%d-%H%M%S}"
        skip = {"trials", "versions", "embed", "canvas"}
        shutil.copytree(src, dst, ignore=lambda d, names: [n for n in names if Path(d) == src and n in skip])
        from provenance import derive
        derive(dst, src, f"from-finish{' --steps ' + ' '.join(a.steps) if a.steps else ''}: {a.why}")
    raw, plan, technique = load_plan(dst)
    paths = step_paths(dst, plan)
    hexes = {p.name: p.hex for p in plan.paints}
    steps = [{"id": s.id, "regions": [list(b) for b in (s.regions or [])], "colors": [hexes[c] for c in s.colors if c in hexes]}
             for s in plan.steps]
    finish = np.array(Image.open(paths[-1]).convert("RGB"))
    raw_dir = dst / "trials" / "rendered"
    raw_dir.mkdir(parents=True, exist_ok=True)
    pictures, owner = build(finish, steps)
    chosen = set(a.steps or [s["id"] for s in steps])
    unknown = chosen - {s["id"] for s in steps}
    if unknown:
        raise Refused(f"no such steps: {sorted(unknown)}")
    from from_finish import box_mask
    previous = None
    for k, (path, pic) in enumerate(zip(paths, pictures)):
        if path.exists():
            shutil.copyfile(path, raw_dir / path.name)
        if steps[k]["id"] not in chosen:
            previous = np.array(Image.open(path).convert("RGB")) if path.exists() else pic
            continue
        if a.steps and previous is not None and k < len(steps) - 1:
            # hybrid: the cut picture inside the step's regions, the step before it (rendered) everywhere else
            inside = box_mask(pic.shape[:2], steps[k]["regions"])[..., None]
            pic = np.where(inside, pic, previous)
        Image.fromarray(pic).save(path)
        previous = pic
    text_path = dst / "text.json"
    if text_path.exists():
        text = json.loads(text_path.read_text(encoding="utf-8"))
        for t in text["steps"]:
            if t["stage_id"] != plan.steps[-1].id and t["stage_id"] in chosen:
                t["made_with"], t["reason"] = "composite:from-finish", "cut from the finished painting (#8)"
        text_path.write_text(json.dumps(text, indent=2), encoding="utf-8")
    for name in ("lesson.json", "lesson.html", "lesson-artifact.html", "lesson-standalone.html") if dst != src else ():
        (dst / name).unlink(missing_ok=True)  # a new lesson: stamped with this version, not the one it came from
    led = LessonLedger(dst)
    with led.locked():
        # keep what this lesson still uses (the finish and the prep pictures); the step renders aren't used
        if dst != src:  # a recut keeps only the renders it still uses; in place, the run's own ledger stays whole
            steps_only = {s.id for s in plan.steps[:-1]} & chosen
            led.calls = [c for c in led.calls if c.get("step") not in steps_only]
        led.calls.append({"tool": "filter", "filter": "from-finish", "step": "", "why": a.why, "input": str(paths[-1]),
                          "out": str(dst), "settings": {"from": src.name}, "cost_usd": 0.0})
        led.save()
    return {"lesson": str(dst), "from": src.name, "steps": len(paths),
            "owned_share": {s["id"]: round(float((owner == k).mean()), 3) for k, s in enumerate(steps)}, "cost_usd": 0.0}


def lock_steps(a: argparse.Namespace) -> dict:
    """Keep finished areas and areas a step doesn't paint from changing (#30). Free."""
    import lock as lk

    lesson = Path(a.lesson)
    raw, plan, technique = load_plan(lesson)
    paths = step_paths(lesson, plan)
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise Refused(f"missing step images: {missing}")
    from run import sample_swatches
    sample_swatches(plan, paths[-1])  # the step paints' real colors, from the finish
    hexes = {p.name: p.hex for p in plan.paints}

    def rgb(h: str) -> tuple[int, int, int]:
        return tuple(int(h.lstrip("#")[k:k + 2], 16) for k in (0, 2, 4))

    regions = [s.regions for s in plan.steps[:-1]]
    protects = [s.protect for s in plan.steps[:-1]]
    colors = [[rgb(hexes[c]) for c in s.colors if c in hexes] for s in plan.steps[:-1]]
    report = lk.lock(lesson, paths[:-1], paths[-1], lesson / "00_canvas.png", regions, protects, colors,
                     plan.steps[-1].regions)
    LessonLedger(lesson).append({"tool": "filter", "filter": "lock-steps", "step": "", "why": a.why or "lock finished areas",
                                 "input": str(lesson), "out": str(lesson), "settings": {"put_back": report}, "cost_usd": 0.0})
    return {"put_back": report, "steps_without_regions": [s.id for s in plan.steps if not s.regions],
            "backward_pass": "done" if "backward" in report else "skipped: every step, the last one too, needs regions",
            "raw": str(lesson / "trials" / "raw"), "cost_usd": 0.0}


def canvas_view(lesson: Path, names: list[str]) -> dict[str, str]:
    """Step pictures cropped to the canvas box, in <lesson>/canvas/, for the page, the embed, and the review.
    Renders stay in the model's frame (later steps are rendered from them); only what the painter sees is cropped."""
    import canvas as cv
    from PIL import Image

    info_path = lesson / "canvas.json"
    if not info_path.exists():
        return {}
    box = json.loads(info_path.read_text(encoding="utf-8"))["canvas_box"]
    if box == [0, 0, 1, 1] or box == [0.0, 0.0, 1.0, 1.0]:
        return {}
    out = lesson / "canvas"
    out.mkdir(exist_ok=True)
    names = [Path(n).name for n in names]  # a full path works too, not just a file name
    view = {}
    for name in names:
        src, dst = lesson / name, out / name
        if src.exists() and (not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime):
            cv.crop_to_canvas(Image.open(src).convert("RGB"), box).save(dst)
        view[name] = f"canvas/{name}"
    return view


def prune_canvas_view(lesson: Path, keep: list[str]) -> list[str]:
    """Drop crops of step images that no longer exist (after split-texture renumbers steps)."""
    out = lesson / "canvas"
    if not out.exists():
        return []
    gone = [p.name for p in out.glob("*.png") if not (lesson / p.name).exists() and p.name not in keep]
    for name in gone:
        (out / name).unlink()
    return gone


def add_lesson_tools(sub) -> None:
    p = sub.add_parser(
        "render-step", help="PAID. Render planned steps from <lesson>/plan.json with the spike's step prompt.",
        description="Render one or more planned steps, each copying from the finished painting (parallel) or from the "
                    "next step and the finish (anchored). Same reason, caps, ledger, and cache as render.")
    p.add_argument("--lesson", required=True)
    p.add_argument("--steps", nargs="+", required=True, help="step ids from plan.json (not the last one)")
    p.add_argument("--mode", choices=["parallel", "anchored"], default="parallel")
    p.add_argument("--fix", help="redo instruction for one step, from the review")
    p.add_argument("--why-not-filter", help="required: why no filter or composite can make these steps")
    p.add_argument("--quality", choices=QUALITIES, default="low")
    p.add_argument("--max-cost", type=float, default=DEFAULT_MAX_COST)
    p.add_argument("--max-redos", type=int, default=DEFAULT_MAX_REDOS)
    p.add_argument("--fresh", action="store_true")
    p.set_defaults(func=render_step)

    p = sub.add_parser("publish", help="Free. Build lesson.json, lesson.html, and lesson-artifact.html once every step image exists.",
                       description="Snap paint swatches to the finish, merge plan.json, text.json, review.json, notes.json, and "
                                   "the ledger, and write lesson.json, lesson.html, and lesson-artifact.html (images inlined, "
                                   "for publishing as a Claude artifact).")
    p.add_argument("--lesson", required=True)
    p.add_argument("--final", action="store_true",
                   help="the skill's last publish: seals the lesson as made hands-off. Any later change marks it edited.")
    p.set_defaults(func=publish)

    p = sub.add_parser("provenance-mark", help="Free. Mark a run from before seals as hands-off or edited, with a reason.",
                       description="For runs made before publish --final existed: records what's known about how the run was "
                                   "made (provenance.json). Only hands-off runs go on the lessons site.")
    p.add_argument("--lesson", required=True)
    p.add_argument("--kind", choices=["hands-off", "edited"], required=True)
    p.add_argument("--note", required=True, help="why: how the run was made and what, if anything, was changed after")
    p.set_defaults(func=lambda a: {**__import__("provenance").mark(Path(a.lesson), a.kind, a.note), "cost_usd": 0.0})

    p = sub.add_parser("mix", help="Free. Compute every paint's recipe from the palette tubes (pigment mixing, not by eye).",
                       description="Snap paint swatches to the finish, then solve each paint's recipe from the technique's "
                                   "tubes with a pigment mixing model (Mixbox). Writes <lesson>/mixes.json with the recipe, "
                                   "the mixed color, and how far it lands from the swatch (Delta E). publish runs it too.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=mix_tool)

    p = sub.add_parser("fit-canvas", help="Free. Fit the photo to the painter's canvas size: crop, or set up an extend render.",
                       description="Before planning: fits the photo to a canvas (e.g. 11x14, either way up; 10x10; or, with "
                                   "no --canvas, the standard size closest to its shape) and to "
                                   "the image model's nearest frame. Writes <lesson>/00_canvas_frame.png and canvas.json. "
                                   "When needs_render is true, render it once to fill the gray areas (see the skill, 0b2).")
    p.add_argument("input")
    p.add_argument("--lesson", required=True)
    p.add_argument("--canvas", help="width x height in inches, e.g. 11x14. Left out: the standard size (8x10, 9x12, "
                                    "11x14, 12x16, 16x20) closest to the photo's shape, recorded as \"chosen\": \"default\"")
    p.add_argument("--orientation", choices=["auto", "portrait", "landscape"], default="auto")
    p.add_argument("--focus", type=float, nargs=2, metavar=("X", "Y"), default=[0.5, 0.5],
                   help="the focal point, 0-1 from the top left")
    p.add_argument("--keep", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"),
                   help="the subject's box, 0-1; a crop must keep it whole")
    p.add_argument("--why", required=True, help="what the subject is and what must stay in the picture")
    p.set_defaults(func=fit_canvas)

    p = sub.add_parser("site-add", help="Free. Add a published lesson to the private lessons site (site/).",
                       description="Copies the lesson's self-contained page to site/lessons/<slug>/, with a thumbnail, and "
                                   "rebuilds the site's index. Commit and push site/ to deploy (docs/lessons-site.md).")
    p.add_argument("--lesson", required=True)
    p.add_argument("--slug", required=True, help="the lesson's address on the site, e.g. lavender-balloon")
    p.set_defaults(func=lambda a: {**__import__("site_lessons").add(Path(a.lesson), a.slug), "cost_usd": 0.0})
    p = sub.add_parser("site-refresh", help="Free. Add new runs of the site's lessons as versions, and open each tile on its newest hands-off run.",
                       description="For every lesson on the site, each kept run of the same picture in output/ becomes a "
                                   "version in the tile's pick list (its page goes to lessons/<slug>/v/<run>/ once, never "
                                   "rewritten). Each tile then opens its newest hands-off run (owner, 2026-11-13); the old "
                                   "default stays as a version. It never drops a version: those already listed stay even "
                                   "when their run folder isn't in output/, unless named in --remove. Commit and push "
                                   "site/ after.")
    p.add_argument("--remove", nargs="+", default=[], metavar="RUN_TIME",
                   help="take these versions off the site by run time (e.g. 20261112-100455); they stay in the history")
    p.set_defaults(func=lambda a: {"versions": __import__("site_lessons").refresh(remove=tuple(a.remove)),
                                   "cost_usd": 0.0})
    p = sub.add_parser("history-backfill", help="Free. Record every finished run in output/ in the lesson history.",
                       description="Adds each run's last publish to site/history/ (a strip of its steps and a record of its "
                                   "version, cost, and checks), then rebuilds site/history/index.html. Runs already "
                                   "recorded and unchanged are skipped.")
    p.set_defaults(func=lambda a: {"runs": __import__("history").backfill(), "cost_usd": 0.0})
    p = sub.add_parser("history-rate", help="Free. Record the owner's 1-5 score for a run in the lesson history.",
                       description="Writes site/history/ratings.json and rebuilds the history page. The run is the output "
                                   "folder name, or '<folder>#<n>' for one publish of it.")
    p.add_argument("--run", required=True)
    p.add_argument("--score", type=int)
    p.add_argument("--note", default="", help="what the owner said, in their words")
    p.set_defaults(func=lambda a: {**__import__("history").rate(a.run, a.score, a.note), "cost_usd": 0.0})
    p = sub.add_parser("from-finish", help="Free. Cut every step picture from the finished painting, in a copy of the lesson (#8).",
                       description="Copies the lesson to a new run folder, then builds each step from 99_finish.png: each pixel "
                                   "goes to the step whose region and paints fit it, earlier steps paint straight through "
                                   "where later ones go, the first of several steps over one area is a flat coat and the "
                                   "rest go on darkest first. The rendered steps are kept in trials/rendered/. Publish after.")
    p.add_argument("--lesson", required=True)
    p.add_argument("--steps", nargs="+", help="only these steps (the rest stay rendered): best for a group of passes "
                                           "over one area, like lavender rows and their dab passes")
    p.add_argument("--in-place", action="store_true",
                   help="change this lesson instead of a copy: the skill's own step 6a, before the seal")
    p.add_argument("--why", required=True)
    p.set_defaults(func=from_finish_tool)
    p = sub.add_parser("carry-forward", help="Free. Copy a later step's subject (in boxes) onto an earlier step so its shape matches.",
                       description="For a subject that changes shape between steps: copies the later step's pixels inside the "
                                   "boxes onto the earlier step, with a soft edge. Lock again afterwards.")
    p.add_argument("--lesson", required=True)
    p.add_argument("--from", dest="source", required=True, help="the later step id, whose shape is right")
    p.add_argument("--to", dest="target", required=True, help="the earlier step id to correct")
    p.add_argument("--box", type=float, nargs=4, action="append", required=True, metavar=("X0", "Y0", "X1", "Y1"),
                   help="0-1 box to copy; repeat for more")
    p.add_argument("--why", required=True)
    p.set_defaults(func=carry_forward)

    p = sub.add_parser("finish-from-step", help="PAID. Rebuild the finished painting from the last step, adding only its details.",
                       description="When the finish changes the subject's shape compared with the steps before it: renders "
                                   "a new finish from the last step with only the listed details added. Keeps the old one.")
    p.add_argument("--lesson", required=True)
    p.add_argument("--add", required=True, help="what the last step adds, e.g. 'the eye, beak, and feet; leaf veins'")
    p.add_argument("--why-not-filter", required=True)
    p.add_argument("--quality", choices=QUALITIES, default="high")
    p.add_argument("--max-cost", type=float, default=DEFAULT_MAX_COST)
    p.add_argument("--max-redos", type=int, default=DEFAULT_MAX_REDOS)
    p.set_defaults(func=finish_from_step)

    p = sub.add_parser("split-texture", help="Free. Split a step that jumps from flat to textured into passes, darkest marks first.",
                       description="Makes in-between pictures from the step before and the step itself (its new paint arriving "
                                   "darkest first: dark marks on the flat base, then mid, then the rest), inserts them as "
                                   "steps before it in plan.json, and renumbers the step images. Use when publish or step-pairs "
                                   "reports a texture jump.")
    p.add_argument("--lesson", required=True)
    p.add_argument("--step", required=True, help="the step that jumps")
    p.add_argument("--ids", nargs="+", required=True, help="ids for the new in-between steps, in order")
    p.add_argument("--names", nargs="+", required=True, help="their names, e.g. 'Dab the dark lavender'")
    p.set_defaults(func=split_texture)

    p = sub.add_parser("lock-steps", help="Free. Put back changes a step makes outside where it paints, or to finished areas (#30).",
                       description="After the step renders and their review: for each step in order, any change outside its "
                                   "plan.json `regions`, or to an area that already looks like the finish, goes back to the "
                                   "previous step's pixels. Raw renders are kept in trials/raw/.")
    p.add_argument("--lesson", required=True)
    p.add_argument("--why", help="what you're locking for (logged)")
    p.set_defaults(func=lock_steps)

    p = sub.add_parser("canvas-view", help="Free. Crop images to the painter's canvas (after fit-canvas), into <lesson>/canvas/.",
                       description="Renders stay in the model's frame; the painter sees the canvas. Measure positions for the "
                                   "step text on these crops (e.g. grid on canvas/99_finish.png), not on the frame.")
    p.add_argument("images", nargs="+", help="image file names inside the lesson folder")
    p.add_argument("--lesson", required=True)
    def _view(a):
        missing = [n for n in a.images if not (Path(a.lesson) / Path(n).name).exists()]
        if missing:
            raise Refused(f"not in the lesson folder: {missing}")
        return {"canvas": canvas_view(Path(a.lesson), a.images) or "no canvas crop needed", "cost_usd": 0.0}
    p.set_defaults(func=_view)

    p = sub.add_parser("step-pairs", help="Free. Before/after/what-changed sheets for every step, for the step review (#24).",
                       description="After publish: writes <lesson>/trials/review/NN_<id>.png (before, after, and a measured "
                                   "change map, all on a 10% grid) and packet.json with each step's text and the "
                                   "technique's stroke_results. A fresh reviewer follows .claude/skills/paint-lesson/step-review.md.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=lambda a: __import__("step_review").packet(Path(a.lesson)))

    p = sub.add_parser("preview-diagrams", help="Free. Draw every construction diagram next to its step image (HTML, and a PNG to Read).",
                       description="After publish: writes <lesson>/trials/diagrams.html and, when Chrome or Edge is "
                                   "installed, trials/diagrams.png, so you can check each diagram against its step.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=preview_diagrams)


# ---------------------------------------------------------------------------
# Filters (#7): free and local
# ---------------------------------------------------------------------------


def filter_out(a: argparse.Namespace, suffix: str = "png") -> Path:
    if a.out:
        return Path(a.out)
    folder = Path(a.lesson) if a.lesson else ROOT / "output" / "filters"
    return folder / f"{Path(a.input).stem}_{a.tool}.{suffix}"


def run_filter(a: argparse.Namespace) -> dict:
    import filters as f

    src = Path(a.input)
    if not src.exists():
        raise Refused(f"input image not found: {src}")
    if a.lesson and not (a.why or "").strip():
        raise Refused("--why is required with --lesson: say what you want this filter to show you")
    rgb = f.load(src, max_side=100_000) if a.tool == "crop" else f.load(src)  # crop keeps every pixel
    settings: dict = {}
    extra: dict = {}
    if a.tool == "crop":
        found = f.find_picture(rgb)
        box = list(a.box) if a.box else found["box"]
        img = f.crop(rgb, box)
        settings = {"box": box, "found_by": "--box" if a.box else "find_picture"}
        extra = {"found": found, "size": [int(img.shape[1]), int(img.shape[0])],
                 "advice": ("The picture fills the image; no crop needed." if found["whole_image"] and not a.box else
                            "Read the output and check it holds the whole picture and nothing else before using it.")}
    elif a.tool == "value-study":
        img = f.value_study(rgb, a.tones)
        settings = {"tones": a.tones}
    elif a.tool == "notan":
        img, used = f.notan(rgb, a.threshold)
        settings = {"threshold": used}
    elif a.tool == "squint":
        img = f.squint(rgb, a.amount)
        settings = {"amount": a.amount}
    elif a.tool == "palette":
        swatches = f.palette(rgb, a.colors)
        img = f.swatch_image(swatches)
        settings = {"colors": a.colors}
        out_json = filter_out(a).with_suffix(".json")
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(swatches, indent=2), encoding="utf-8")
        extra = {"json": str(out_json), "swatches": [{"hex": s["hex"], "share": s["share"]} for s in swatches]}
    elif a.tool == "simplify":
        img = f.simplify(rgb, a.strength, a.method)
        settings = {"strength": a.strength, "method": a.method}
    elif a.tool == "posterize":
        pal = [s["rgb"] for s in json.loads(Path(a.palette).read_text(encoding="utf-8"))] if a.palette else None
        img = f.posterize(rgb, a.colors, pal)
        settings = {"colors": len(pal) if pal else a.colors, "palette": a.palette}
    elif a.tool == "edges":
        img = f.edges(rgb, a.detail)
        settings = {"detail": a.detail}
    elif a.tool == "grid":
        img = f.grid(rgb, a.cells, a.percent)
        settings = {"percent": True} if a.percent else {"cells": a.cells}
    else:
        raise Refused(f"unknown filter {a.tool}")
    out = f.save(img, filter_out(a))
    result = {"tool": a.tool, "input": str(src), "out": str(out), "settings": settings, "cost_usd": 0.0, **extra}
    if a.lesson:
        # Free, but logged like a render so the lesson page can show which filters were tried and why.
        LessonLedger(Path(a.lesson)).append({"tool": "filter", "filter": a.tool, "step": a.step or "", "why": a.why,
                                             "input": str(src), "out": str(out), "settings": settings, "cost_usd": 0.0})
    return result


FILTERS = {
    # name: (use this for, extra arguments)
    "crop": ("cutting the picture out of a screenshot or a photo of a screen (app bars, buttons, captions, page "
             "around it). Finds the picture by itself, or takes --box",
             [("--box", dict(type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"),
                             help="pixels in the original image; default finds the picture"))]),
    "value-study": ("values: the lights, middles, and darks to block in (3 to 5 tones)",
                    [("--tones", dict(type=int, default=3, choices=range(2, 8), help="number of values (default 3)"))]),
    "notan": ("the big dark and light pattern, two values; checks a composition reads",
              [("--threshold", dict(type=int, help="0-255; default picks one automatically"))]),
    "squint": ("seeing big shapes and values with details gone, like squinting",
               [("--amount", dict(type=float, default=2.0, help="blur as percent of the long side (default 2)"))]),
    "palette": ("the picture's main colors as swatches plus JSON (hex, share); mixing targets",
                [("--colors", dict(type=int, default=6, help="number of colors (default 6)"))]),
    "simplify": ("block-in and simplified-reference looks: flat painterly patches, sharp edges kept",
                 [("--strength", dict(type=int, default=2, choices=range(1, 6), help="1 light to 5 heavy (default 2)")),
                  ("--method", dict(choices=["kuwahara", "meanshift"], default="kuwahara"))]),
    "posterize": ("a few flat colors, its own or a palette's; color blocking stages",
                  [("--colors", dict(type=int, default=6, help="number of colors (default 6)")),
                   ("--palette", dict(help="palette JSON from the palette tool; snaps to those colors"))]),
    "edges": ("a clean line drawing to trace for the sketch step",
              [("--detail", dict(choices=["low", "medium", "high"], default="medium"))]),
    "grid": ("a square grid over the picture for transferring the drawing",
             [("--cells", dict(type=int, default=4, help="squares along the long side (default 4)")),
              ("--percent", dict(action="store_true", help="lines at every 10%% of width and height, labeled: "
                                                            "use this to measure positions for step text"))]),
}


def add_filters(sub) -> None:
    for name, (use_for, args) in FILTERS.items():
        p = sub.add_parser(name, help=f"Free. Use for {use_for}.", description=f"Free filter. Use for {use_for}.")
        p.add_argument("input", help="image to filter")
        p.add_argument("--lesson", help="lesson folder to write into (default output/filters/)")
        p.add_argument("--out", help="output path; default <folder>/<input name>_<tool>.png")
        p.add_argument("--why", help="with --lesson, required: what you want this filter to show you; "
                                     "logged in the ledger and shown on the lesson page")
        p.add_argument("--step", help="the plan step this filter is for, if any")
        for flag, kw in args:
            p.add_argument(flag, **kw)
        p.set_defaults(func=run_filter)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Pipeline v2: outlines, and step pictures cut from the finish (docs/design/pipeline-v2.md)
# ---------------------------------------------------------------------------


def _v2(lesson: Path):
    """A version 2 lesson's plan and finish, or a refusal that says what's missing."""
    import plan2
    from filters import load

    if not (lesson / "plan.json").exists():
        raise Refused(f"no plan.json in {lesson}")
    try:
        plan = plan2.load(lesson)
    except ValueError as e:
        raise Refused(str(e))
    wrong = plan2.problems(plan)
    if wrong:
        raise Refused("fix plan.json first: " + " | ".join(wrong))
    finish = lesson / "99_finish.png"
    if not finish.exists():
        raise Refused(f"no 99_finish.png in {lesson}")
    return plan, load(finish, max_side=100_000)


def _read_owner(lesson: Path, plan: dict):
    import numpy as np
    from PIL import Image

    path = lesson / "parts" / "owner.png"
    if not path.exists():
        raise Refused(f"no outlines yet: run outline --lesson {lesson} first")
    owner = np.array(Image.open(path)).astype("int32")
    if owner.max() >= len(plan["parts"]):
        raise Refused("parts/owner.png is from a different part list: run outline again")
    return owner


def outline_tool(a: argparse.Namespace) -> dict:
    """Write parts/<id>.png, parts/owner.png, and parts/preview.jpg for a version 2 plan."""
    import numpy as np
    import outline as ol
    from PIL import Image

    lesson = Path(a.lesson)
    plan, finish = _v2_parts_only(lesson)  # outline runs before there are paints or stages (design section 4)
    try:
        masks, owner, stats = ol.outline(finish, plan["parts"], ol.Sam())
    except ol.NoModel as e:
        raise Refused(str(e))
    except ValueError as e:
        raise Refused(str(e))
    folder = lesson / "parts"
    folder.mkdir(exist_ok=True)
    for old in folder.glob("*.png"):
        old.unlink()
    Image.fromarray(owner.astype(np.uint8)).save(folder / "owner.png")
    for pid, m in masks.items():
        Image.fromarray((m * 255).astype(np.uint8)).save(folder / f"{pid}.png")
    Image.fromarray(ol.preview(finish, plan["parts"], owner)).save(folder / "preview.jpg", quality=88)
    (folder / "stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    return {"preview": str(folder / "preview.jpg"), "parts": stats, "problems": ol.problems(plan["parts"], stats),
            "advice": "Read the preview once. Fix any part that's visibly wrong (its box, points, or colors) and run "
                      "this again: at most 2 rounds per part.", "cost_usd": 0.0}


def part_colors_tool(a: argparse.Namespace) -> dict:
    """Each part's main colors, measured from the finish inside its outline."""
    import paints

    lesson = Path(a.lesson)
    plan, finish = _v2_parts_only(lesson)
    owner = _read_owner(lesson, plan)
    out = {p["id"]: paints.part_colors(finish, owner == k, a.colors) for k, p in enumerate(plan["parts"])}
    return {"colors": out, "advice": "Darkest first, with each color's share of the part and a spot (0-1) inside it.",
            "cost_usd": 0.0}


def paints_tool(a: argparse.Namespace) -> dict:
    """Measure the plan's paints from the finish, mark tints and shades, merge the rest to the technique's
    max_mixes, and write them (and the steps pointed at them) into plan.json. Design section 9."""
    import mixing
    import paints
    import plan2
    import yaml
    from PIL import Image

    lesson = Path(a.lesson)
    plan, finish = _v2_parts_only(lesson)
    owner = _read_owner(lesson, plan)
    if owner.shape != finish.shape[:2]:
        raise Refused("parts/owner.png doesn't match 99_finish.png's size: run outline again")
    technique = yaml.safe_load((ROOT / plan["technique"]).read_text(encoding="utf-8")) if plan.get("technique") else {}
    tubes = load_palette(plan["palette"])[0] if plan.get("palette") else technique.get("palette") or []
    try:
        white = next((mixing.tube_rgb(t) for t in tubes if "white" in t.lower()), (255, 255, 255))
        colored = [t for t in tubes if "white" not in t.lower()]
        dark = min(colored, key=lambda t: mixing._lab(mixing.tube_rgb(t))[0]) if colored else None
    except mixing.UnknownTube as e:
        raise Refused(str(e))
    max_mixes = technique.get("max_mixes")
    tubes = (white, mixing.tube_rgb(dark) if dark else (20, 20, 22), dark or "black")
    if a.add:
        try:
            r = paints.add(finish, plan, owner, a.add, max_mixes, *tubes)
        except ValueError as e:
            raise Refused(str(e))
    else:
        r = paints.measure(finish, plan, owner, max_mixes, *tubes)
    plan["paints"] = r["paints"]  # never the steps: which paints a step uses is Claude's to choose
    (lesson / "plan.json").write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")
    (lesson / "trials").mkdir(exist_ok=True)
    sheet = lesson / "trials" / "paints.jpg"
    Image.fromarray(paints.swatch_sheet(finish, plan["parts"], r["paints"], r["shares"])).save(sheet, quality=90)
    names = {p["id"]: p.get("name") or p["id"] for p in r["paints"]}
    merged = [f"{', '.join(m['parts'])}: {m['hex']}" + (f" ({m['id']})" if m.get("id") else "")
              + f" merged into {m['into']}, {m['delta_e']} apart" + (", in the same part" if m["same_part"] else "")
              for m in r["merges"]]
    changed = [f"{c['id']} moved Delta E {c['delta_e']} ({c['from']} to {c['to']})"
               + ("; it keeps its name" if c["name_kept"] else "; name it again (and its used_for)")
               for c in r["changed"]]
    removed = [f"{x['id']} removed: its parts ({', '.join(x['parts']) or 'none'}) are gone"
               + (f"; steps that still name it: {', '.join(x['steps'])}. Point them at another paint." if x["steps"] else "")
               for x in r["removed"]]
    bases = paints.base_mixes(r["paints"])
    over = []
    if r["over_target"]:
        over = [f"{len(bases)} base mixes, above the target of {max_mixes}. Every pair left is an accent, a paint a "
                f"step uses, a paint paints --add made, or more than Delta E {paints.MAX_MERGE:g} apart. That's "
                "allowed; don't raise max_mixes or merge by hand."]
        over += [f"{names[o['id']]} stays" + "".join(f" ({why})" for why, on in (("an accent", o["accent"]),
                 ("a step uses it", o["used"]), ("added", o["added"])) if on)
                 + f": nearest is {names[o['nearest']]}, {o['delta_e']} away" for o in r["over_target"]]
    problems = plan2.problems(plan, technique)
    if not plan2.steps(plan):  # paints runs before the stages are written: that's not a problem yet
        problems = [p for p in problems if p != plan2.NO_STAGES]
    problems = r.get("problems", []) + problems
    if r["first"]:
        advice = ("First measurement. Read the sheet. Name each paint and say what it's for; then write the stages, "
                  "each step choosing from these paints. Run paints again only after outline changes the parts.")
    elif a.add:
        advice = (f"Point the step that should use {r['added']} at it (split a pass in two: darker paint first), name "
                  "it, then run build-steps." if r["added"] else "Nothing was added: see problems.")
    else:
        advice = ("Measured again: every paint kept its id; no paint a step uses was merged or moved to another step. "
                  "Name any paint that lost its name, give each new paint a step, then run build-steps.")
    return {"paints": [{k: p[k] for k in ("id", "name", "hex", "of", "plus", "parts", "added") if k in p}
                       for p in r["paints"]],
            "first": r["first"], "base_mixes": len(bases), "max_mixes": max_mixes, "merged": merged,
            "changed": changed, "kept": r["kept"], "new": r["new"], "removed": removed, "added": r.get("added"),
            "accents": r["accents"], "kept_names": r["kept_names"], "sheet": str(sheet), "over_target": over,
            "problems": problems, "advice": advice, "cost_usd": 0.0}


def _v2_parts_only(lesson: Path):
    """Like _v2, for the tools that run before the plan has paints and steps (outline, part-colors, paints): only
    the parts must be right."""
    import plan2
    from filters import load

    if not (lesson / "plan.json").exists():
        raise Refused(f"no plan.json in {lesson}")
    try:
        plan = plan2.load(lesson)
    except ValueError as e:
        raise Refused(str(e))
    wrong = plan2.parts_problems(plan)
    if wrong:
        raise Refused("fix plan.json's parts first: " + " | ".join(wrong))
    finish = lesson / "99_finish.png"
    if not finish.exists():
        raise Refused(f"no 99_finish.png in {lesson}")
    return plan, load(finish, max_side=100_000)


def build_steps_tool(a: argparse.Namespace) -> dict:
    """Write NN_<step id>.png for every step of a version 2 plan, cut from the finish. No renders."""
    import build_steps as bs
    from filters import load
    from PIL import Image

    lesson = Path(a.lesson)
    plan, finish = _v2(lesson)
    owner = _read_owner(lesson, plan)
    if owner.shape != finish.shape[:2]:
        raise Refused("parts/owner.png doesn't match 99_finish.png's size: run outline again")
    plate = lesson / "98_background.png"
    background = load(plate, max_side=100_000) if plate.exists() else None
    pictures, rows, _ = bs.build(finish, plan, owner, background)
    steps = bs.flat_steps(plan)
    for old in lesson.glob("[0-9][0-9]_*.png"):
        if not old.name.startswith(("00_", "98_", "99_")):
            old.unlink()
    names = []
    for i, (pic, s) in enumerate(zip(pictures, steps)):
        name = f"{i + 1:02d}_{s['id']}.png"
        Image.fromarray(pic).save(lesson / name)
        names.append(name)
    (lesson / "trials").mkdir(exist_ok=True)
    sheet = lesson / "trials" / "steps.jpg"
    Image.fromarray(bs.contact_sheet(pictures, steps)).save(sheet, quality=88)
    front = round(float((~bs.back_parts(plan["parts"]))[owner].mean()), 3)
    advice = "Read the sheet. Every step should add one thing; nothing else should change."
    if background is None and front > bs.NEEDS_BACKGROUND:
        advice += (f" Objects cover {front:.0%} of the picture and there's no 98_background.png, so what's behind them "
                   "is a rough fill until they're painted: a blurred ghost of them shows in every step before their "
                   "own. Run background (one render, about 2 cents), then build-steps again (design section 7).")
    faint = bs.faint_ghosts(plan, rows)
    if faint:
        advice += " Look for these on the sheet: " + "; ".join(faint) + "."
    return {"steps": names, "sheet": str(sheet), "rows": rows, "problems": bs.problems(plan, rows),
            "objects_share": front, "background": plate.name if background is not None else None,
            "needs_background": background is None and front > bs.NEEDS_BACKGROUND,
            "advice": advice, "cost_usd": 0.0}


def _v2_canvas(lesson: Path) -> tuple[list | None, dict]:
    """A version 2 lesson's canvas box and size: canvas.json, or the default size picked now (#122)."""
    import canvas as cv
    import checks

    try:
        return checks._canvas(lesson)
    except cv.NoCanvas as err:
        raise Refused(str(err)) from err


def step_aids_tool(a: argparse.Namespace) -> dict:
    """Write aids/: every step's teaching pictures (where its paint goes, a close-up, a paint map) and the transfer
    outline, from the outlines, the plan, and the step pictures. No renders, the same bytes every run."""
    import aids
    import build_steps as bs
    import numpy as np
    from filters import load

    lesson = Path(a.lesson)
    plan, finish = _v2(lesson)
    owner = _read_owner(lesson, plan)
    if owner.shape != finish.shape[:2]:
        raise Refused("parts/owner.png doesn't match 99_finish.png's size: run outline again")
    steps = bs.flat_steps(plan)
    names = [f"{i + 1:02d}_{s['id']}.png" for i, s in enumerate(steps)]
    missing = [n for n in names if not (lesson / n).exists()]
    if missing:
        raise Refused(f"missing step pictures {missing}: run build-steps --lesson {lesson} first")
    plate = lesson / "98_background.png"
    built, _, masks = bs.build(finish, plan, owner, load(plate, max_side=100_000) if plate.exists() else None)
    pictures = [load(lesson / n, max_side=100_000) for n in names]
    stale = [n for n, p, b in zip(names, pictures, built) if p.shape != b.shape or not np.array_equal(p, b)]
    if stale:
        raise Refused(f"the step pictures don't match the plan ({stale[0]} first): run build-steps --lesson {lesson} again")
    canvas_box, canvas = _v2_canvas(lesson)
    view = canvas_view(lesson, names)
    data = aids.make(plan, pictures, masks, owner, canvas_box, canvas, lesson / "aids", [view.get(n, n) for n in names])
    (lesson / "aids" / "aids.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    rows = data["steps"]
    return {"aids": str(lesson / "aids" / "aids.json"), "steps": len(rows),
            "closeups": sum(1 for r in rows if r.get("closeup")), "maps": sum(1 for r in rows if r.get("map")),
            "transfer": bool(data["transfer"]),
            "advice": "Run publish to put them on the page. Run this again whenever build-steps runs.", "cost_usd": 0.0}


def draft_text_tool(a: argparse.Namespace) -> dict:
    """Write text.json's lines for every step from data: the plan, the step masks, the outlines, the paints, the
    technique, and the cards. Keeps every summary, tip, and edited line Claude wrote. Design section 10."""
    import checks
    import draft_text

    lesson = Path(a.lesson)
    plan, _ = _v2(lesson)
    _read_owner(lesson, plan)
    built = checks.build(lesson, plan)
    if built is None:
        raise Refused("parts/owner.png doesn't match 99_finish.png or the plan: run outline again")
    _, pictures, _, masks = built
    canvas_box, canvas = _v2_canvas(lesson)
    drafted = draft_text.draft(plan, pictures, masks, canvas_box, canvas, lesson=lesson)
    path = lesson / "text.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    text = draft_text.merge(old, drafted)
    path.write_text(json.dumps(text, indent=1) + "\n", encoding="utf-8")
    todo = [f"{t['stage_id']}: " + " and ".join(k for k in draft_text.KEEP if not (t.get(k) or "").strip())
            for t in text["steps"] if any(not (t.get(k) or "").strip() for k in draft_text.KEEP)]
    return {"text": str(path), "steps": len(text["steps"]), "lines": sum(len(t["lines"]) for t in text["steps"]),
            "edited_kept": sum(1 for t in text["steps"] for x in t["lines"] if x.get("edited")),
            "for_claude": todo, "left_out": draft_text.left_out(plan),
            "advice": "Read each step's lines against its picture. Write its summary (under 90 characters) and tip (one "
                      "to three sentences only this photo needs). Correct a drafted line in place and mark it "
                      "\"edited\": true; draft-text keeps it. Then run check.", "cost_usd": 0.0}


def check_tool(a: argparse.Namespace) -> dict:
    """Every measured check on a version 2 lesson, each failure saying what to change. Design section 12."""
    import checks
    import plan2

    lesson = Path(a.lesson)
    if not (lesson / "plan.json").exists():
        raise Refused(f"no plan.json in {lesson}")
    if not plan2.is_v2(lesson):
        raise Refused("check is for a version 2 lesson (plan.json with \"plan_version\": 2); a version 1 lesson is "
                      "checked by publish --final")
    r = checks.run(lesson)
    # `problems` is `failures` under the name every other v2 tool prints (the skill: "every tool prints problems")
    return {"problems": r["failures"], "failures": r["failures"], "notes": r["notes"], "ok": not r["failures"],
            "advice": "Fix each failure as it says, then run check again. publish --final won't seal while any is left.",
            "cost_usd": 0.0}


GRAY = (128, 128, 128)  # the bands around a finish that isn't the image model's shape


def _to_frame(finish, size: str):
    """The finish placed in the image model's frame (bands of gray where the shapes differ), and where it sits."""
    from PIL import Image

    fw, fh = (int(x) for x in size.split("x"))
    h, w = finish.shape[:2]
    scale = min(fw / w, fh / h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    x0, y0 = (fw - nw) // 2, (fh - nh) // 2
    frame = Image.new("RGB", (fw, fh), GRAY)
    frame.paste(Image.fromarray(finish).resize((nw, nh), Image.LANCZOS), (x0, y0))
    return frame, (x0, y0, x0 + nw, y0 + nh)


def background_tool(a: argparse.Namespace, client=None) -> dict:
    """PAID, one render: the finish with everything in front taken out, for what's behind the objects."""
    import build_steps as bs
    import numpy as np
    from filters import load
    from PIL import Image

    lesson = Path(a.lesson)
    plan, finish = _v2(lesson)
    owner = _read_owner(lesson, plan)
    parts = plan["parts"]
    is_back = bs.back_parts(parts)
    front = ~is_back[owner]
    if not front.any():
        raise Refused("this plan has no objects in front of the background, so there's nothing to take out")
    out = lesson / "98_background.png"
    if out.exists() and not a.redo:
        raise Refused(f"{out.name} already exists. Pass --redo to render it once more.")
    name = lambda p: p.get("name") or p["id"]  # noqa: E731
    remove = [name(p) for k, p in enumerate(parts) if not is_back[k] and not p.get("parent")]
    keep = [name(p) for k, p in enumerate(parts) if is_back[k]]
    size = size_for(lesson / "99_finish.png")
    frame, box = _to_frame(finish, size)
    padded = box != (0, 0) + frame.size
    (lesson / "trials").mkdir(exist_ok=True)
    frame_path = lesson / "trials" / "background_in.png"
    frame.save(frame_path)
    prompt = ("This is an acrylic painting. Remove these things from it completely: " + "; ".join(remove) + ". "
              "Where they were, paint what is behind them: continue the background (" + "; ".join(keep) + ") exactly as it "
              "is around them, in the same colors and the same brushwork. Leave no trace, outline, or shadow of what "
              "you removed. Change nothing else: everything that stays keeps its exact place, shape, and color. "
              + ("Keep the plain gray bands at the edges exactly as they are. " if padded else "")
              + "No text, signature, or watermark.")
    raw = lesson / "trials" / "background_raw.png"
    budget = Budget(lesson, a.max_cost, 1)  # one render and at most one redo
    r = render_one(budget, "background", [frame_path], prompt, raw, a.quality,
                   "what's behind the objects isn't in the finish, and they cover too much of it for a fill",
                   size, fresh=a.redo, client=client)
    got = Image.open(raw).convert("RGB")
    if got.size != frame.size:
        got = got.resize(frame.size, Image.LANCZOS)
    Image.fromarray(np.array(got.crop(box).resize((finish.shape[1], finish.shape[0]), Image.LANCZOS))).save(out)
    problems, numbers = bs.background_problems(finish, load(out, max_side=100_000), front)
    return {**r, "out": str(out), "removed": remove, "problems": problems, **numbers,
            "advice": "Run build-steps again and Read the sheet: no trace of the objects before their own steps."}


def cards_tool(a: argparse.Namespace) -> dict:
    """One HTML page of every stroke card and basics card, for the owner to read and check."""
    import cards

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(cards.page(), encoding="utf-8")
    s, b = cards.strokes(), cards.basics()
    return {"out": str(out), "strokes": len(s), "basics": len(b), "problems": cards.problems(s, b),
            "unchecked": sorted(k for k, c in {**s, **b}.items() if not c.get("checked")), "cost_usd": 0.0}


def elements_tool(a: argparse.Namespace) -> dict:
    """The element techniques (#12): the library to pick from, and with --lesson, how the plan's picks fit."""
    import elements

    lesson = Path(a.lesson) if a.lesson else None
    lib = elements.known(lesson)
    out = {"elements": [{"id": k, "name": el.get("name"), "for": el.get("for"), "kinds": el.get("kinds"),
                         "steps": [f"{x.get('name')} ({'/'.join(elements._list(x.get('show')))}: "
                                   f"{', '.join(elements._list(x.get('strokes')))}"
                                   f"{', optional' if x.get('optional') else ''}{', may repeat' if x.get('repeat') else ''})"
                                   for x in el.get("steps") or []],
                         **({"drafted": True} if el.get("drafted") else {})}
                        for k, el in lib.items()],
           "problems": elements.problems(elements.library()), "cost_usd": 0.0}
    if a.out:
        path = Path(a.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(elements.page(), encoding="utf-8")
        out["out"] = str(path)
    if lesson:
        plan, _ = _v2(lesson)
        out["picks"] = elements.picks(plan)
        out["problems"] += elements.plan_problems(plan, lesson=lesson)
    return out


def add_v2_tools(sub) -> None:
    p = sub.add_parser("elements", help="Free. v2: the element techniques to pick per part, and how the plan's picks fit.",
                       description="Lists techniques/elements (and a lesson's drafted ones): what each is for, which part "
                                   "kinds, and its steps in order with the shows and stroke cards each may use. With "
                                   "--lesson, also every part's pick and what doesn't fit (a part with no element, steps "
                                   "that don't follow theirs, a drafted one not filed yet). --out writes one page of "
                                   "them all for the owner to check.")
    p.add_argument("--lesson")
    p.add_argument("--out")
    p.set_defaults(func=elements_tool)
    p = sub.add_parser("outline", help="Free. v2: find every part's exact outline in the finished painting.",
                       description="For a version 2 plan (plan.json with parts). Writes parts/<id>.png, parts/owner.png, and "
                                   "parts/preview.jpg (the finish with each part tinted and labeled). Downloads the outline "
                                   "model (108 MB) to models/ the first time.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=outline_tool)
    p = sub.add_parser("part-colors", help="Free. v2: each part's main colors, measured inside its outline.",
                       description="Run after outline. Use it to choose a part's paints, and to give a marks part its "
                                   "colors_in / colors_out when points can't be trusted to land on the paint.")
    p.add_argument("--lesson", required=True)
    p.add_argument("--colors", type=int, default=3, help="colors per part (default 3)")
    p.set_defaults(func=part_colors_tool)
    p = sub.add_parser("paints", help="Free. v2: measure the plan's paints from the finish and merge them toward max_mixes.",
                       description="Run after outline; no stages needed. First run (no paints yet): each part gets the "
                                   "fewest colors that fit (ids <part>-<n>, darkest first; a tint or shade of a part's "
                                   "main paint gets \"of\" and \"plus\" and doesn't count), merged toward the technique's "
                                   "max_mixes (never two far apart: it says what kept it over). Run again after outline "
                                   "changes: every paint is measured again and keeps its id (and its name when it moved "
                                   "under Delta E 3); a paint a step uses is never merged; a paint whose part is gone is "
                                   "removed. Never changes the steps. --add <part>: one more measured color for that "
                                   "part, nothing merged. Writes trials/paints.jpg.")
    p.add_argument("--lesson", required=True)
    p.add_argument("--add", metavar="PART", help="give this part one more measured color (to split a pass, or for a "
                                                  "dropped part it now carries); never merges anything")
    p.set_defaults(func=paints_tool)
    p = sub.add_parser("background", help="PAID, one render. v2: the finish with the objects taken out, for what's behind them.",
                       description="Run when build-steps prints \"needs_background\": true. Writes 98_background.png; "
                                   "build-steps then uses only its pixels behind the objects, so the render can't move "
                                   "or recolor anything else. Counted in the lesson's ledger and cached like any render.")
    p.add_argument("--lesson", required=True)
    p.add_argument("--quality", choices=QUALITIES, default="low")
    p.add_argument("--redo", action="store_true", help="render it once more (one redo at most)")
    p.add_argument("--max-cost", type=float, default=DEFAULT_MAX_COST, help=f"dollar cap per lesson (default {DEFAULT_MAX_COST:.2f})")
    p.set_defaults(func=background_tool)
    p = sub.add_parser("cards", help="Free. One page of every stroke card and basics card, for the owner to check.",
                       description="Writes techniques/strokes/*.yaml and techniques/basics/*.yaml as one HTML page, each "
                                   "card with its sources and what the research didn't cover.")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cards_tool)
    p = sub.add_parser("build-steps", help="Free. v2: cut every step picture from the finished painting.",
                       description="Run after outline. Writes NN_<step id>.png for every step and trials/steps.jpg (all of "
                                   "them on one sheet). Uses 98_background.png (the finish with the objects taken out) for "
                                   "what's behind objects when it exists.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=build_steps_tool)
    p = sub.add_parser("step-aids", help="Free. v2: every step's teaching pictures (where, close-up, paint map) and the transfer outline.",
                       description="Run after build-steps. Writes aids/aids.json and its pictures: each step's painted "
                                   "area as an outline for the page, a close-up of small areas, a paint map where a step "
                                   "or part has 2 or more paints, the position in words (inches on the canvas from "
                                   "canvas.json; a lesson with none gets the standard size closest to the finish's "
                                   "shape, or is refused), and aids/transfer.png.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=step_aids_tool)
    p = sub.add_parser("draft-text", help="Free. v2: draft every step's lines in text.json from the plan, outlines, paints, and cards.",
                       description="Run after build-steps (and step-aids). Writes text.json's lines for every step: let "
                                   "it dry, rinse, the optional chalk outline, where, the paints in order, mix once, the "
                                   "brush, load, and motion, what it should leave, two or three coats, watch out, and "
                                   "step back. Never overwrites a summary, a tip, or a line marked \"edited\": true.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=draft_text_tool)
    p = sub.add_parser("check", help="Free. v2: every measured check (plan, outlines, steps, cards, text, recipes), each saying what to change.",
                       description="Gathers the plan, outline, step picture, and card checks, the step and stage counts, "
                                   "strokes and brushes, texture jumps, the text (percentages, long lines, missing "
                                   "summaries and tips, stale drafts), and what publish counts. publish runs it; "
                                   "publish --final won't seal a version 2 lesson while anything fails.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=check_tool)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tools.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="tool", required=True, metavar="TOOL")
    add_filters(sub)
    add_render(sub)
    add_lesson_tools(sub)
    add_v2_tools(sub)
    return ap


def main(argv: list[str] | None = None, client=None) -> int:
    a = build_parser().parse_args(argv)
    started = time.time()
    try:
        result = a.func(a, client=client) if a.tool in ("render", "render-step", "finish-from-step", "background") else a.func(a)
    except Refused as e:
        emit({"refused": str(e)})
        return 2
    result.setdefault("seconds", round(time.time() - started, 2))
    emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
