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
# <lesson>/plan.json     written by the plan's writer: "plan_version": 3, things, paints, stages, plus "photo" and
#                        "technique" paths (relative to the repo); docs/design/pipeline-v3.md section 5
# <lesson>/99_finish.png the finished painting; the chain (chain/) erases it backward, a unit of the plan a render
# <lesson>/v3/plan.json  the plan in version 2's shape (steps3.as_v2), what the later tools read; build-steps keeps it
# <lesson>/NN_<id>.png   step pictures from build-steps, NN from 01 (the last is the finish)
# <lesson>/text.json     draft-text, then the skill: {"steps": [{stage_id, lines: [{kind, text, edited, step?}],
#                        brushes: [{brush, use}], made_with, reason}], "opening": {welcome, light, skills, road},
#                        "stages": {<stage id>: {for, end}}}; v3.1 sections 5 to 7. A lesson made before v3.1 has a
#                        summary and a tip a step, drafted lines, and no opening or stages
# <lesson>/review.json   written by the skill: {"finish_issues": [...], "text_issues": [...]}


def load_plan(lesson: Path):
    """(the plan in version 2's shape as build-steps kept it, the plan as the LessonPlan model mix, publish, and the
    seal read, the technique). Only a version 3 lesson: versions 1 and 2 were removed (#82, #238)."""
    import yaml
    import publish2

    raw = _v3_kept(lesson, pictures=False)["plan"]
    technique = yaml.safe_load((ROOT / raw["technique"]).read_text(encoding="utf-8"))
    if raw.get("palette"):  # the painter's own tubes (palettes/<name>.yaml) instead of the technique's five
        technique["palette"], technique["palette_name"] = load_palette(raw["palette"])
    return raw, publish2.as_v1(raw), technique


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
    """NN_<id>.png for every step. build-steps writes the last step as its own copy of the finish."""
    return [lesson / f"{i + 1:02d}_{s.id}.png" for i, s in enumerate(plan.steps)]


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


def paints_not_listed(stages: list[dict], paints: dict) -> list[dict]:
    """Paints a step's instructions or values table name that aren't in its colors, so their recipe never shows."""

    def said(n: str, text: str) -> bool:
        # "Sea turquoise" inside "Light sea turquoise" is the other paint, not this one
        for longer in sorted((m for m in paints if m != n and n.lower() in m.lower()), key=len, reverse=True):
            text = re.sub(re.escape(longer), " ", text, flags=re.I)
        return bool(re.search(r"\b" + re.escape(n) + r"\b", text, re.I))

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
    """Solve every paint's recipe from the palette tubes against its measured color (#22), and write
    <lesson>/mixes.json."""
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
    lesson = Path(a.lesson)
    raw, plan, technique = load_plan(lesson)
    if not (lesson / "99_finish.png").exists():
        raise Refused(f"no finished painting at {lesson / '99_finish.png'}; make it first")
    mixes = compute_mixes(lesson, plan, technique)
    return {"json": str(lesson / "mixes.json"), "cost_usd": 0.0,
            "paints": [{"name": n, "recipe": m["text"], "target": m["target_hex"], "mixed": m["mixed_hex"],
                        "delta_e": m["delta_e"], "reachable": m["reachable"], "your_recipe": m["guess_recipe"]}
                       for n, m in mixes.items()],
            "unreachable": [n for n, m in mixes.items() if not m["reachable"]]}


NOTES_REQUIRED = ("read", "technique", "order", "steps", "beginner_check")


def busy_problems(lesson: Path, notes: dict) -> list[str]:
    """The busy numbers step 0c records (#109): the photo's always, and with a beginner version, its and the
    finish's. Only that they were measured; no number is a pass or a fail."""
    bv = notes.get("beginner_version")
    got = bv.get("busy") if isinstance(bv, dict) and isinstance(bv.get("busy"), dict) else {}
    want = [("photo", "the photo (the fitted one, 00_canvas_frame.png or 00_canvas_fit.png)")]
    made = bv.get("made") if isinstance(bv, dict) else None
    # The notes say whether a beginner version was made; the file stands in only when they don't say (a render that
    # was looked at and turned down, made: false, may still be on disk)
    if made is True or (made is None and (lesson / "00_beginner.png").exists()):
        want += [("beginner", "00_beginner.png"), ("finish", "99_finish.png")]
    return [f"notes.json beginner_version.busy has no {role} number: run busy {what} --lesson <lesson> (step 0c; it "
            "records the number itself, so keep beginner_version.busy when you write the notes)"
            for role, what in want if not isinstance(got.get(role), dict)]


def seal_problems(lesson: Path, plan, text: dict, review: dict, notes: dict, checks: dict) -> list[str]:
    """What stops a lesson being sealed hands-off: the rules the skill asks for, checked instead of remembered
    (two hands-off runs, 2026-11-12, each let a small rule slip late in a long run).
    There's no image review, no regions, and no word limit on a step (design section 13)."""
    out = []
    ids = [s.id for s in plan.steps]
    if not (lesson / "review.json").exists():
        out.append("review.json is missing (v3/run.md step D4)")
    for key in ("finish_issues", "text_issues"):
        if key not in review:
            out.append(f"review.json has no {key} (an empty list if there were none)")
    # two checkers look at the run (design sections 6 and 10): the chain's, and the words' last check
    answers, looks = lesson / "chain" / "looks" / "answers.json", lesson / "chain" / "looks"
    try:
        said = json.loads(answers.read_text(encoding="utf-8"))
        read = {x.get("look") for x in said if isinstance(x, dict)} if isinstance(said, list) else None
    except (OSError, ValueError):
        read = None
    if read is None:
        out.append("the chain's checker hasn't read the chain as it is now: no chain/looks/answers.json that can "
                   "be read (v3/chain-check.md)")
    elif {f.stem for f in looks.glob("U[0-9][0-9].jpg")} - read:
        out.append("chain/looks/answers.json doesn't answer for every unit: send the checker again")
    if not (lesson / "words" / "dropped.json").exists():
        out.append("the words haven't had their last check: run check-text --final")
    import draft_text
    import lesson_words

    written = any(draft_text.written(t.get("lines")) for t in text.values())
    if written and not (lesson_words.folder_of(lesson) / "arc-dropped.json").exists():
        out.append("the arc hasn't had its last check: run check-text --arc --final (v3/run.md D4)")
    for key in NOTES_REQUIRED:
        if not notes.get(key):
            out.append(f"notes.json is missing {key} (step 8)")
    out += busy_problems(lesson, notes)
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
        # the text is its lines; its strokes come from the plan's stroke and the cards. A step the lesson's writer
        # wrote (v3.1) has no summary: its six lines hold it, and `check` holds them
        for key in ("summary", "lines", "brushes", "made_with"):
            if key == "summary" and draft_text.written(t.get("lines")):
                continue
            if not t.get(key):
                out.append(f"{sid}: text.json has no {key}")
    for key in ("texture_jumps", "paints_not_listed", "duplicate_recipes", "undocumented_diagrams", "long_instructions"):
        if checks.get(key):
            out.append(f"{key}: {checks[key]}")
    if checks.get("missing_aids"):
        out.append("aids/aids.json is missing or was made for other steps: run step-aids, then publish --final again")
    noted = " ".join(n for t in text.values() for n in (t.get("paint_notes") or [])).lower()
    for name in checks.get("unreachable_paints") or []:
        if name.lower() not in noted:
            out.append(f"{name} can't be mixed from these tubes and no step's paint_notes says so")
    return out


CHECKED = ("texture_jumps", "paints_not_listed", "duplicate_recipes", "undocumented_diagrams", "long_instructions",
           "missing_aids", "unreachable_paints")  # publish's counts that `check` also reports


def publish(a: argparse.Namespace) -> dict:
    """Build lesson.json and lesson.html from plan.json, text.json, the images, and the ledger."""
    import checks
    import elements
    import publish2
    from lesson_page import page
    from run import CLAUDE_MODEL

    lesson = Path(a.lesson)
    raw, plan, technique = load_plan(lesson)
    paths = step_paths(lesson, plan)
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise Refused(f"missing step images: {missing}. Run build-steps --lesson {lesson}.")
    mixes = compute_mixes(lesson, plan, technique)
    text_path = lesson / "text.json"
    text_all = json.loads(text_path.read_text(encoding="utf-8")) if text_path.exists() else {}
    text = {t["stage_id"]: t for t in text_all.get("steps") or []}
    review_path = lesson / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
    notes_path = lesson / "notes.json"  # the skill's reasoning: technique, order, filters
    notes = json.loads(notes_path.read_text(encoding="utf-8")) if notes_path.exists() else {}
    led = LessonLedger(lesson)

    extras = publish2.paint_extras(raw)  # a paint keeps its id and parts beside the LessonPlan keys

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

    view = canvas_view(lesson, [p.name for p in paths])
    prune_canvas_view(lesson, [p.name for p in paths])
    stages = publish2.stages(raw, text, paints, [view.get(p.name, p.name) for p in paths], technique, lesson)
    from version import stamp
    old = lesson / "lesson.json"
    from version import with_made
    old_stamp = (json.loads(old.read_text(encoding="utf-8")).get("gesso") or {}) if old.exists() else None
    previous = old_stamp.get("version", "before stamps") if old_stamp is not None else None
    lesson_data = {
        "gesso": with_made(stamp(), old_stamp or None),
        "canvas": _lesson_canvas(lesson)[1],
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
        # beside the keys every reader of lesson.json uses: the plan's stages, for the page's headings, and the aids
        "plan_version": 2, "groups": publish2.groups(raw), "aids": publish2.attach_aids(lesson, stages),
    }
    lesson_data["pipeline"] = 3  # made by pipeline v3 and read by the page in version 2's shape
    # the arc (v3.1, check-text --arc --final): read once before step 1, and a line at each stage's start and end. A
    # lesson made before it has neither, and its page shows what it has
    if text_all.get("opening"):
        lesson_data["opening"] = text_all["opening"]
    if any((v or {}).get("for") or (v or {}).get("end") for v in (text_all.get("stages") or {}).values()):
        lesson_data["stage_lines"] = {k: v for k, v in text_all["stages"].items() if v}
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
    if len(standalone.encode("utf-8")) > publish2.MAX_PAGE_BYTES:
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
    result = {"html": str(lesson / "lesson.html"), "artifact": str(artifact),
            "artifact_mb": round(artifact.stat().st_size / 1e6, 2), "embed": embed,
            "gesso": lesson_data["gesso"], "provenance": lesson_data["provenance"], "previous_version": previous, "steps": len(stages), "steps_by_source": by_source,
            "diagrams": sum(1 for st in stages if st["construct"]),
            # a diagram the page can't explain: the skill's beginner check didn't write down why
            "undocumented_diagrams": undocumented_diagrams(stages, notes),
            "unreachable_paints": [n for n, m in mixes.items() if not m["reachable"]],
            # (no word limit on a step, design section 10, so no long_steps)
            # paints an instruction names that aren't in the step's colors, so their recipe never shows
            "paints_not_listed": paints_not_listed(stages, paints),
            # paints whose computed recipes come out the same (or mix within Delta E 3): two names, one color
            "duplicate_recipes": duplicate_recipes(mixes),
            # steps that finish a big area from flat to textured at once: the same list check reports
            "texture_jumps": checks.texture_jumps(lesson, raw),
            # single instructions past the skill's budget (about 35 words): usually two moves to split
            "long_instructions": [{"id": st["id"], "n": k + 1, "words": len(x.split())} for st in stages
                                  for k, x in enumerate(st["steps"]) if len(x.split()) > INSTRUCTION_WORDS],
            "paid_renders": sum(1 for c in renders if not c.get("cached")),
            "cached_renders": sum(1 for c in renders if c.get("cached")), "image_cost_usd": led.total_cost,
            # the steps' teaching pictures (step-aids), and the page's size
            "missing_aids": not lesson_data.get("aids"), "page_mb": round(len(standalone.encode("utf-8")) / 1e6, 2)}
    found = checks.run(lesson, text)  # every measured check in one list (design section 12)
    result.update(check=found["failures"], check_notes=found["notes"])
    if getattr(a, "final", False):  # the skill's last publish: check everything, then seal it hands-off
        # what check already reports (in its own words) is left out of the seal's list so it isn't said twice
        problems = seal_problems(lesson, plan, text, review, notes,
                                 {k: v for k, v in result.items() if k not in CHECKED}) + result["check"]
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
    from construct import lookup, strip
    from lesson_page import STYLE, image_src

    lesson = Path(a.lesson)
    data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8")) if (lesson / "lesson.json").exists() else None
    if not data:
        raise Refused("run publish first: the preview reads lesson.json")
    paints = lookup(data["photo_read"]["mixes"])
    rows, specced, broken = [], [], []
    for i, st in enumerate(data["stages"], 1):
        html = strip(st.get("construct"), paints, st["id"])
        if st.get("construct"):
            specced.append(st["id"])
        if st.get("construct") and not html:
            broken.append(st["id"])
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
    result = {"diagrams": len(rows), "specced": len(specced), "drawn": len(specced) - len(broken), "broken": broken,
              "html": str(page), "png": None}
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


FINISHER_STEP_SIDE = 384  # pixels: the finisher's step pictures (#267's f-lean)
FINISHER_FINISH_SIDE = 512


def small_pictures(a: argparse.Namespace) -> dict:
    """Every step picture at 384 pixels and the finish at 512, in <lesson>/small/, for step 8's finisher to look at
    in place of the full-size ones. Design v3.1, section 8."""
    from PIL import Image

    lesson = Path(a.lesson)
    raw, plan, technique = load_plan(lesson)
    paths = step_paths(lesson, plan)
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise Refused(f"missing step images: {missing}. Run build-steps --lesson {lesson}.")
    fin = lesson / "99_finish.png"
    if not fin.exists():
        raise Refused(f"no 99_finish.png in {lesson}")
    out = lesson / "small"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    files = []
    for src, side in [(p, FINISHER_STEP_SIDE) for p in paths] + [(fin, FINISHER_FINISH_SIDE)]:
        im = Image.open(src).convert("RGB")
        im.thumbnail((side, side), Image.LANCZOS)
        dst = out / f"{src.stem}.jpg"
        im.save(dst, quality=88)
        files.append(f"small/{dst.name}")
    return {"problems": [], "folder": str(out), "files": files, "steps": len(paths),
            "advice": "Look at these, not the full-size pictures, for step 8.", "cost_usd": 0.0}


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
    """Drop crops of step images that no longer exist (after the plan's steps change)."""
    out = lesson / "canvas"
    if not out.exists():
        return []
    gone = [p.name for p in out.glob("*.png") if not (lesson / p.name).exists() and p.name not in keep]
    for name in gone:
        (out / name).unlink()
    return gone


def add_lesson_tools(sub) -> None:
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

    p = sub.add_parser("store-photo", help="Free. Store a run's source picture in photos/ (tracked in git) unless it's there.",
                       description="Copies the picture to photos/<its stem>.<ext> when no picture of that name is stored, so "
                                   "any session can rerun the lesson from a fresh clone (#147). A picture in photos/private/ "
                                   "stays out of the repo. 'next' says to commit it with the run. Only AI-made pictures or "
                                   "ones the owner has the rights to go in the repo, never a personal photo.")
    p.add_argument("photo")
    p.set_defaults(func=lambda a: {**__import__("pictures").store(Path(a.photo)), "cost_usd": 0.0})

    p = sub.add_parser("site-add", help="Free. Add a published lesson to the private lessons site (site/).",
                       description="Copies the lesson's self-contained page to site/lessons/<slug>/, with a thumbnail, and "
                                   "rebuilds the site's index. Commit and push site/ to deploy (docs/lessons-site.md).")
    p.add_argument("--lesson", required=True)
    p.add_argument("--slug", required=True, help="the lesson's address on the site, e.g. lavender-balloon")
    p.set_defaults(func=lambda a: {**__import__("site_lessons").add(Path(a.lesson), a.slug),
                                   "warnings": __import__("site_lessons").missing_pictures(), "cost_usd": 0.0})
    p = sub.add_parser("site-refresh", help="Free. Add new runs of the site's lessons as versions, and open each tile on its newest hands-off run.",
                       description="For every lesson on the site, each kept run of the same picture in output/ becomes a "
                                   "version in the tile's pick list (its page goes to lessons/<slug>/v/<run>/ once, never "
                                   "rewritten). Each tile then opens its newest hands-off run (owner, 2026-11-13); the old "
                                   "default stays as a version. It never drops a version: those already listed stay even "
                                   "when their run folder isn't in output/, unless named in --remove. Only runs made "
                                   "with POC 1.0.0 or later are taken, and never one listed in site/kept-off.json "
                                   "(#141). Commit and push site/ after. Its warnings name each tile whose source picture "
                                   "isn't stored and committed in photos/ (#147).")
    p.add_argument("--remove", nargs="+", default=[], metavar="RUN_TIME",
                   help="take these versions off the site by run time (e.g. 20261112-100455); they stay in the history")
    p.set_defaults(func=lambda a: {"versions": __import__("site_lessons").refresh(remove=tuple(a.remove)),
                                   "warnings": __import__("site_lessons").missing_pictures(), "cost_usd": 0.0})
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

    p = sub.add_parser("small-pictures", help="Free. Every step picture at 384 pixels and the finish at 512, in <lesson>/small/, for step 8.",
                       description="Writes <lesson>/small/NN_<id>.jpg (384 pixels on the long side) for every step "
                                   "and 99_finish.jpg (512): what step 8's finisher looks at in place of the "
                                   "full-size pictures.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=small_pictures)
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
# The step tools: a lesson's step pictures, teaching pictures, drafted lines and checks, from its chain. The later
# tools read the plan in version 2's shape (steps3.as_v2), as build-steps kept it (lesson3)
# ---------------------------------------------------------------------------


def _v3_kept(lesson: Path, pictures: bool = True) -> dict:
    """What build-steps kept for a version 3 lesson (lesson3.read), or a refusal that says what to run."""
    import lesson3
    import plan3

    if not (lesson / "plan.json").exists():
        raise Refused(f"no plan.json in {lesson}")
    if not plan3.is_v3(lesson):
        raise Refused(f"{lesson}/plan.json isn't a version 3 plan (no \"plan_version\": 3). Version 1 and 2 lessons "
                      "can't be built, checked or published any more (#82, #238); make the lesson again with "
                      "/paint-lesson")
    try:
        return lesson3.read(lesson, pictures)
    except lesson3.Stale as e:
        raise Refused(str(e))


def save_png(rgb, path: Path) -> None:
    """A step picture as a PNG."""
    from PIL import Image

    Image.fromarray(rgb).save(path)


def build_steps_tool(a: argparse.Namespace) -> dict:
    """build-steps: the paints fitted to the chain, a step picture a step, and what the later tools read
    (lesson3.make). Design sections 7 and 8."""
    import build_steps as bs
    import erase3
    import lesson3
    import plan3
    import steps3
    from PIL import Image

    lesson = Path(a.lesson)
    plan, _, finish = _v3_ready(lesson)
    try:
        built = lesson3.make(lesson, plan, finish, save_png)
    except erase3.Refused as e:
        raise Refused(str(e))
    (lesson / "trials").mkdir(exist_ok=True)
    sheet = lesson / "trials" / "steps.jpg"
    Image.fromarray(bs.contact_sheet(built["pictures"], plan3.steps(plan))).save(sheet, quality=88)
    bad, notes = steps3.problems(built)
    return {"steps": built["steps"], "sheet": str(sheet), "rows": built["rows"], "paints": built["paints"],
            "problems": bad, "notes": notes,
            "checks": {k: built[k] for k in ("final_gap", "outside_unit_max", "from_its_paints_median")},
            "advice": "Read the sheet. Every step should add one thing; nothing else should change. `notes` can't be "
                      "fixed without a new plan and a new chain: record each in notes.json as a known problem. Then "
                      "step-aids, mix, draft-text.", "cost_usd": 0.0}


def _lesson_canvas(lesson: Path) -> tuple[list | None, dict]:
    """A lesson's canvas box and size: canvas.json, or the default size picked now (#122)."""
    import canvas as cv
    import checks

    try:
        return checks._canvas(lesson)
    except cv.NoCanvas as err:
        raise Refused(str(err)) from err


def step_aids_tool(a: argparse.Namespace) -> dict:
    """Write aids/: every step's teaching pictures (where its paint goes, a close-up, a paint map) and the transfer
    outline, from what build-steps kept. No renders, the same bytes every run."""
    import aids

    lesson = Path(a.lesson)
    kept = _v3_kept(lesson)
    plan = kept["plan"]
    names = kept["build"]["steps"]
    canvas_box, canvas = _lesson_canvas(lesson)
    view = canvas_view(lesson, names)
    data = aids.make(plan, kept["pictures"], kept["masks"], kept["owner"], canvas_box, canvas, lesson / "aids",
                     [view.get(n, n) for n in names])
    (lesson / "aids" / "aids.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    rows = data["steps"]
    return {"aids": str(lesson / "aids" / "aids.json"), "steps": len(rows),
            "closeups": sum(1 for r in rows if r.get("closeup")), "maps": sum(1 for r in rows if r.get("map")),
            "transfer": bool(data["transfer"]),
            "advice": "Run publish to put them on the page. Run this again whenever build-steps runs.", "cost_usd": 0.0}


def draft_text_tool(a: argparse.Namespace) -> dict:
    """Write text.json's lines for every step from data: the plan, the step masks, the shapes, the paints, the
    technique, and the cards. Keeps every summary, tip, and edited line already there. Design section 10."""
    import draft_text

    lesson = Path(a.lesson)
    kept = _v3_kept(lesson)
    plan = kept["plan"]
    canvas_box, canvas = _lesson_canvas(lesson)
    drafted = draft_text.draft(plan, kept["pictures"], kept["masks"], canvas_box, canvas, lesson=lesson,
                               owner=kept["owner"])
    path = lesson / "text.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    text = draft_text.merge(old, drafted)
    for t in text["steps"]:  # the receipt says how the step picture was made
        t["reason"] = V3_REASON
    path.write_text(json.dumps(text, indent=1) + "\n", encoding="utf-8")
    todo = [f"{t['stage_id']}: " + " and ".join(k for k in draft_text.KEEP if not (t.get(k) or "").strip())
            for t in text["steps"] if any(not (t.get(k) or "").strip() for k in draft_text.KEEP)]
    return {"text": str(path), "steps": len(text["steps"]), "lines": sum(len(t["lines"]) for t in text["steps"]),
            "edited_kept": sum(1 for t in text["steps"] for x in t["lines"] if x.get("edited")),
            "for_claude": todo, "left_out": draft_text.left_out(plan),
            "advice": "Run check, then the chain's checker; the lesson's writer writes each step's words "
                      "(packets, v3/run.md step D).", "cost_usd": 0.0}


def check_tool(a: argparse.Namespace) -> dict:
    """Every measured check on a lesson, each failure saying what to change. Design section 8."""
    import checks
    import plan3

    lesson = Path(a.lesson)
    if not (lesson / "plan.json").exists():
        raise Refused(f"no plan.json in {lesson}")
    if not plan3.is_v3(lesson):
        raise Refused("check is for a version 3 lesson (plan.json with \"plan_version\": 3); version 1 and 2 lessons "
                      "can't be checked any more (#82, #238); make the lesson again with /paint-lesson")
    r = checks.run(lesson)
    # `problems` is `failures` under the name every other tool prints (the skill: "every tool prints problems")
    return {"problems": r["failures"], "failures": r["failures"], "notes": r["notes"], "ok": not r["failures"],
            "advice": "Fix each failure as it says, then run check again. publish --final won't seal while any is left.",
            "cost_usd": 0.0}


GRAY = (128, 128, 128)  # the bands around a picture that isn't the image model's shape


def _to_frame(finish, size: str):
    """The picture placed in the image model's frame (bands of gray where the shapes differ), and where it sits."""
    from PIL import Image

    fw, fh = (int(x) for x in size.split("x"))
    h, w = finish.shape[:2]
    scale = min(fw / w, fh / h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    x0, y0 = (fw - nw) // 2, (fh - nh) // 2
    frame = Image.new("RGB", (fw, fh), GRAY)
    frame.paste(Image.fromarray(finish).resize((nw, nh), Image.LANCZOS), (x0, y0))
    return frame, (x0, y0, x0 + nw, y0 + nh)


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
    """The element techniques (#12): the library to pick from (plan-check holds a plan's picks to it)."""
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
    return out


def busy_tool(a: argparse.Namespace) -> dict:
    """How much of a picture is fine texture, and where (#109). An aid for step 0c, not a judge."""
    import busy

    lesson, path = Path(a.lesson), Path(a.picture)
    if not lesson.is_dir():
        raise Refused(f"no lesson folder {lesson}")
    if not path.exists() and (lesson / path.name).exists():
        path = lesson / path.name
    if not path.exists():
        raise Refused(f"no picture {path}")
    try:
        r = busy.run(path, lesson, a.role)
    except ValueError as e:
        raise Refused(str(e)) from e
    return {**r, "problems": [], "cost_usd": 0.0}


def add_step_tools(sub) -> None:
    p = sub.add_parser("busy", help="Free. How much of a picture is fine texture, and where: for the beginner-sized check.",
                       description="Measures the canvas part of the picture (canvas.json's canvas_box) at 1000 px on the "
                                   "long side: fine_texture is the share of 40 px tiles dense with edges (stalks, grass, "
                                   "leaves), edges the share of edge pixels. Writes busy/<name>.jpg (the texture's tiles "
                                   "outlined on a faded copy) and records the numbers in notes.json's "
                                   "beginner_version.busy as photo, beginner (00_beginner.png), or finish (99_finish.png). "
                                   "With a beginner version, says whether fine texture came down from the photo's. Not a "
                                   "threshold: it doesn't see tiny separate things or count parts.")
    p.add_argument("picture", help="the picture: the fitted photo, 00_beginner.png, or 99_finish.png")
    p.add_argument("--lesson", required=True)
    p.add_argument("--as", dest="role", choices=["photo", "beginner", "finish"],
                   help="what the picture stands for. Needed for any picture but 00_canvas_frame.png or "
                        "00_canvas_fit.png (the photo), 00_beginner.png, and 99_finish.png; its number replaces that "
                        "role's")
    p.set_defaults(func=busy_tool)
    p = sub.add_parser("elements", help="Free. The element techniques a plan picks from, one per thing.",
                       description="Lists techniques/elements (and, with --lesson, the lesson's drafted ones in "
                                   "<lesson>/elements/): what each is for, which kinds of thing, and its steps in order "
                                   "with the stroke cards each may use. plan-check holds the plan's picks to them. --out "
                                   "writes one page of them all for the owner to check.")
    p.add_argument("--lesson")
    p.add_argument("--out")
    p.set_defaults(func=elements_tool)
    p = sub.add_parser("cards", help="Free. One page of every stroke card and basics card, for the owner to check.",
                       description="Writes techniques/strokes/*.yaml and techniques/basics/*.yaml as one HTML page, each "
                                   "card with its sources and what the research didn't cover.")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cards_tool)
    p = sub.add_parser("build-steps", help="Free. Fit the paints to the chain and make every step picture from it.",
                       description="Run after erase. Fits each of the plan's paints to what its units changed, writes "
                                   "NN_<step id>.png for every step (a unit's last step is the chain's picture) and "
                                   "trials/steps.jpg (all of them on one sheet), and keeps what the later tools read "
                                   "(v3/, parts/owner.png). `notes` are faults only a new plan and chain can fix.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=build_steps_tool)
    p = sub.add_parser("step-aids", help="Free. Every step's teaching pictures (where, close-up, paint map) and the transfer outline.",
                       description="Run after build-steps. Writes aids/aids.json and its pictures: each step's painted "
                                   "area as an outline for the page, a close-up of small areas, a paint map where a step "
                                   "or part has 2 or more paints, the position in words (inches on the canvas from "
                                   "canvas.json; a lesson with none gets the standard size closest to the finish's "
                                   "shape, or is refused), and aids/transfer.png.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=step_aids_tool)
    p = sub.add_parser("draft-text", help="Free. Draft every step's lines in text.json from the plan, the step pictures, the paints, and the cards.",
                       description="Run after build-steps (and step-aids). Writes text.json's lines for every step: let "
                                   "it dry, rinse, the optional chalk outline, where, the paints in order, mix once, the "
                                   "brush, load, and motion, what it should leave, two or three coats, watch out, and "
                                   "step back. Never overwrites a summary, a tip, or a line marked \"edited\": true.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=draft_text_tool)
    p = sub.add_parser("check", help="Free. Every measured check (plan, steps, cards, text, recipes), each saying what to change.",
                       description="Gathers the plan's and the step pictures' checks, strokes and brushes, the cards, "
                                   "the text (percentages, long lines, missing summaries and tips, stale drafts, every "
                                   "number against the fact sheet), and what publish counts. publish runs it; publish "
                                   "--final won't seal a lesson while anything fails.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=check_tool)


# ---------------------------------------------------------------------------
# Pipeline v3: a painter's plan first, the finish erased backward to fit it (docs/design/pipeline-v3.md)
# ---------------------------------------------------------------------------


def _v3_plan(lesson: Path) -> tuple[dict, dict]:
    """A version 3 lesson's plan as written and its technique, or a refusal that says what's missing. The plan may
    still have problems: `plan-check` lists them."""
    import yaml

    if not (lesson / "plan.json").exists():
        raise Refused(f"no plan.json in {lesson}")
    try:
        plan = json.loads((lesson / "plan.json").read_text(encoding="utf-8"))
    except ValueError as e:
        raise Refused(f"plan.json isn't valid JSON: {e}")
    if not isinstance(plan, dict) or plan.get("plan_version") != 3:
        raise Refused(f"{lesson}/plan.json isn't a version 3 plan (no \"plan_version\": 3)")
    name = plan.get("technique")
    path = (ROOT / name).resolve() if isinstance(name, str) and name else None
    if path is None or not path.is_file() or (ROOT / "techniques").resolve() not in path.parents:
        raise Refused(f"plan.json's \"technique\" ({name!r}) isn't a file in techniques/: name the approach, e.g. "
                      "techniques/acrylic-paint-along-beginner.yaml")
    technique = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(technique, dict):
        raise Refused(f"{name} isn't a technique file (it has no keys)")
    return plan, technique


def plan_check_tool(a: argparse.Namespace) -> dict:
    """What's wrong with a version 3 plan, each problem saying what to change, and the units its chain will render.
    Design section 5."""
    import elements
    import plan3

    lesson = Path(a.lesson)
    plan, technique = _v3_plan(lesson)
    wrong = plan3.problems(plan, technique, elements=elements.library())
    if plan3.shape_problems(plan):  # nothing more can be read from it
        return {"problems": wrong, "ok": False, "advice": "Fix the file's shape as each problem says, then run "
                "plan-check again for the rest.", "cost_usd": 0.0}
    steps = plan3.steps(plan)
    units = [{"unit": n, "id": u["id"], "name": u["name"], "kind": u["kind"], "things": u["things"],
              "steps": [steps[i].get("id") for i in u["steps"]]} for n, u in enumerate(plan3.units(plan))]
    renders = max(0, len(units) - 1)
    return {"problems": wrong, "ok": not wrong, "steps": len(steps), "stages": len(plan.get("stages") or []),
            "units": units, "renders": renders, **plan3.notes(plan, technique),
            "advice": ("Fix each problem as it says and run plan-check again. " if wrong else "") +
                      f"The chain will make {renders} renders, one a unit after the first (`erase`). A unit named "
                      "null needs its first step's `unit`.",
            "cost_usd": 0.0}


def library_tool(a: argparse.Namespace) -> dict:
    """The library's list for the plan's writer, or with --picks, the files it picked in <lesson>/library/.
    Design v3.1, section 8."""
    import plan_writer

    lesson = Path(a.lesson)
    if not lesson.is_dir():
        raise Refused(f"no lesson folder {lesson}")
    if not a.picks:
        listed = elements_tool(argparse.Namespace(lesson=str(lesson), out=None))
        return {"problems": listed["problems"], "elements": listed["elements"], **plan_writer.library_list(),
                "advice": "Pick what you'll read: the element of every thing, the card of every stroke you'll use, "
                          "the research sections your picture needs (by heading, as listed; \"For Gesso\" is always "
                          "sent). Write them to a file as {\"elements\": [...], \"strokes\": [...], \"research\": "
                          "[...]} and run library --picks <that file>. Ask once, so take every one you might use.",
                "cost_usd": 0.0}
    try:
        picks = json.loads(Path(a.picks).read_text(encoding="utf-8"))
        r = plan_writer.write_library(lesson, picks)
    except FileNotFoundError:
        raise Refused(f"no picks file {a.picks}")
    except ValueError as e:
        return {"problems": [f"the picks can't be read: {e}. Nothing was written."], "cost_usd": 0.0}
    problems = [f"no {kind[:-1] if kind != 'research' else 'research section'} {x!r}: pick one from library's list"
                for kind, xs in r["unknown"].items() for x in xs]
    return {"problems": problems, **r,
            "advice": f"Read every file in {r['folder']} and nothing else from techniques/ or docs/. "
                      + ("Fix the names problems lists and run library --picks again (what matched is kept)."
                         if problems else ""),
            "cost_usd": 0.0}


def plan_change_tool(a: argparse.Namespace) -> dict:
    """The plan's writer's changes made to plan.json, then plan-check. A whole plan is taken as it is. Changes that
    don't apply leave plan.json as it was. Design v3.1, section 8."""
    import plan_writer

    lesson = Path(a.lesson)
    plan, _ = _v3_plan(lesson)
    try:
        ch = json.loads(Path(a.changes).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Refused(f"no changes file {a.changes}")
    except ValueError as e:
        return {"problems": [f"{a.changes} isn't valid JSON ({e}); plan.json is as it was. Write the changes again."],
                "applied": False, "cost_usd": 0.0}
    try:
        new = plan_writer.apply_plan_changes(plan, ch)
    except ValueError as e:
        return {"problems": [f"the changes don't apply: {e}. plan.json is as it was: send the changes again, fixed."],
                "applied": False, "cost_usd": 0.0}
    whole = plan_writer.is_whole_plan(ch)
    (lesson / "plan.json").write_text(json.dumps(new, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    log = lesson / "plan-changes.json"
    try:
        kept = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
    except ValueError:
        kept = []
    kept.append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "whole_plan": whole,
                 "changes": None if whole else ch})
    log.write_text(json.dumps(kept, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {**plan_check_tool(a), "applied": True, "whole_plan": whole}


def _v3_ready(lesson: Path):
    """A version 3 lesson's plan with nothing wrong in it, and its finish, or a refusal."""
    import elements
    import plan3
    from filters import load

    plan, technique = _v3_plan(lesson)
    wrong = plan3.problems(plan, technique, elements=elements.library())
    if wrong:
        raise Refused("fix plan.json first (plan-check lists everything): " + " | ".join(wrong[:3]))
    finish = lesson / "99_finish.png"
    if not finish.exists():
        raise Refused(f"no 99_finish.png in {lesson}")
    return plan, technique, load(finish, max_side=100_000)


CHAIN_RENDER_USD = 0.025  # a low render of the chain, rounded up (1.8 to 2 cents in the spikes)
ERASE_WHY = ("v3: every step picture is the finish erased backward by the image model, one render a unit of the plan "
             "(docs/design/pipeline-v3.md, section 6)")


def _erase_render(lesson: Path, a: argparse.Namespace, client):
    """The chain's renderer: one edit of a picture under the lesson's cost cap, in the ledger and the render cache,
    the answer brought back to the picture's own size."""
    import numpy as np
    from PIL import Image

    # `erase` counts a unit's tries itself (erase3.TRIES). Its cap is the chain's own: what the lesson spent before
    # the chain (the finish) isn't counted against it, so a cap sized to the chain means the same on every lesson
    before = sum(c.get("cost_usd", 0) for c in LessonLedger(lesson).calls if not str(c.get("step", "")).startswith("erase-"))
    budget = Budget(lesson, before + a.max_cost, 10 ** 6)

    def render(name: str, src: Path, prompt: str, fresh: bool):
        picture = np.array(Image.open(src).convert("RGB"))
        size = size_for(src)
        frame, box = _to_frame(picture, size)
        padded = box != (0, 0) + frame.size
        if padded:  # a picture that isn't the image model's shape goes in with gray bands, as `background` sends it
            frame.save(src)
            prompt = prompt.replace("No text, signature", "Keep the plain gray bands at the edges exactly as they are. "
                                                          "No text, signature")
        raw = src.with_name(f"{name}_raw.png")
        try:
            r = render_one(budget, f"erase-{name[:3]}", [src], prompt, raw, a.quality, ERASE_WHY, size, fresh=fresh,
                           client=client)
        finally:
            if padded:
                Image.fromarray(picture).save(src)
        got = Image.open(raw).convert("RGB")
        if got.size != frame.size:
            got = got.resize(frame.size, Image.LANCZOS)
        if padded:
            got = got.crop(box)
        if got.size != (picture.shape[1], picture.shape[0]):
            got = got.resize((picture.shape[1], picture.shape[0]), Image.LANCZOS)
        return np.array(got), {"seconds": r["seconds"], "cost_usd": r["cost_usd"], "cached": r["cached"]}

    return render


def erase_tool(a: argparse.Namespace, client=None) -> dict:
    """PAID, one low render a unit: the finish erased backward by the plan's units, chained and guarded by the
    change. Design section 6."""
    import erase3
    import plan3
    from PIL import Image

    lesson = Path(a.lesson)
    plan, _, finish = _v3_ready(lesson)
    us = plan3.units(plan)
    if a.max_cost is None:  # the chain once, every unit asked again once, and room for the last render's reserve
        a.max_cost = round(2 * CHAIN_RENDER_USD * (len(us) - 1) + ESTIMATE_USD["low"], 2)
    render = _erase_render(lesson, a, client)
    if a.probe is not None:
        if a.redo:
            raise Refused("--probe renders one unit from the finish and asks for nothing again: leave --redo out")
        if not 1 <= a.probe < len(us):
            raise Refused(f"there is no unit {a.probe} to probe: the chain renders units 1 to {len(us) - 1}")
        folder = lesson / "chain" / "probe"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"U{a.probe:02d}"
        src = folder / f"{name}_in.png"
        Image.fromarray(finish).save(src)
        raw, info = render(name, src, erase3.request(plan, us, a.probe), False)
        out, D = erase3.erase_one(finish, raw, us[a.probe]["kind"] == "bare", finish[..., 0] < 0)
        Image.fromarray(erase3.look(finish, out, D)).save(folder / f"{name}.jpg", quality=88)
        return {"probe": a.probe, "name": us[a.probe]["name"], "kind": us[a.probe]["kind"],
                "look": str(folder / f"{name}.jpg"), "erased_share": round(float(D.mean()), 4), **info,
                "advice": "Read the look: the finish, the unit erased from it, and what changed in magenta. A probe "
                          "erases one unit from the finish alone; only the last unit's is the chain's own render."}
    redo: dict[int, str] = {}
    for word in [w for w in (a.redo or "").split(",") if w.strip()]:
        n, _, why = word.strip().partition(":")
        if not n.isdigit() or why not in erase3.WHY:
            raise Refused(f"--redo takes <unit>:<why>, comma-separated, why one of {', '.join(erase3.WHY)}: "
                          f"e.g. 8:stray,10:left. Got {word!r}.")
        if int(n) in redo:
            raise Refused(f"--redo names unit {n} twice: once a run, with the reason that matters more")
        redo[int(n)] = why
    try:
        r = erase3.run(lesson, plan, finish, render, redo, auto=not a.no_auto)
    except erase3.Refused as e:
        raise Refused(str(e))
    todo, kept = erase3.problems(r)
    return {"renders": r["renders"], "paid": r["paid"], "cost_usd": r["cost_usd"], "render_seconds": r["render_seconds"],
            "again": r["again"], "problems": todo, "left": kept, "sheet": str(lesson / "chain" / "chain.jpg"),
            "looks": str(lesson / "chain" / "looks"),
            "rows": [{k: x[k] for k in ("unit", "name", "kind", "again", "left_standing", "erased_share", "kept_whole",
                                         "cached")} for x in r["rows"]],
            "advice": "Have a checker in a fresh context read chain/looks/ (v3/chain-check.md). Ask again for each unit "
                      "it marks, in one run: erase --redo <unit>:stray or <unit>:left. A unit is asked again at most "
                      f"{erase3.TRIES} times; every unit before it in painting order is rendered again from its new "
                      "picture."}


V3_REASON = "the finish erased back to this step by the image model, a render a stage of a thing"


def packets_tool(a: argparse.Namespace) -> dict:
    """The fact sheet and the lesson writer's folder, words/lesson/. Design v3.1, section 5."""
    import lesson_words

    lesson = Path(a.lesson)
    if not (lesson / "text.json").exists():
        raise Refused(f"no text.json in {lesson}: run draft-text first (it makes each step's header)")
    try:
        r = lesson_words.packet(lesson)
    except lesson_words.Refused as e:
        raise Refused(str(e))
    return {"problems": [], **r,
            "advice": "Start one writer, in a fresh context, with: \"Follow brief.md in <lesson>/words/lesson. Read "
                      "only that folder. Write out.json there.\" Then run check-text.", "cost_usd": 0.0}


def check_text_tool(a: argparse.Namespace) -> dict:
    """The lesson writer's words into text.json, checked round by round against the fact sheet and the step's
    paints; with --arc, the arc. Design v3.1, sections 5 and 6."""
    import facts
    import lesson_words

    lesson = Path(a.lesson)
    if not (lesson / facts.WORK).is_dir() or not (lesson / "text.json").exists():
        raise Refused(f"no writer's packet in {lesson}: run draft-text, then packets")
    try:
        if a.arc:
            r = lesson_words.arc_round(lesson, final=a.final)
        else:
            r = lesson_words.steps_round(lesson, lambda: draft_text_tool(a), final=a.final)
    except lesson_words.Refused as e:
        raise Refused(str(e))
    return {**r, "cost_usd": 0.0}


def add_v3_tools(sub) -> None:
    p = sub.add_parser("packets", help="Free. The fact sheet and the lesson writer's folder (words/lesson/).",
                       description="Measures the fact sheet from the step pictures (words/sheet.json) and writes "
                                   "words/lesson/ for the lesson's one writer: brief.md and arc-brief.md, steps.md "
                                   "(each step's header and stroke card), cards.md, stages.md, plan.json, facts.md "
                                   "(the sheet's rows as sentences, lean), a before-and-after picture and a change "
                                   "picture a step, the photo and the finish. Run after draft-text.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=packets_tool)
    p = sub.add_parser("check-text", help="Free. The lesson writer's words into text.json, round by round, each number and side checked against the sheet.",
                       description="Lays words/lesson/out.json and the writer's answers (fix-1.json, fix-2.json) "
                                   "into text.json as each step's six lines, and runs the next round: round 1 sends "
                                   "back check-text's failures, round 2 the sentences that name a paint their step "
                                   "doesn't list and the lines over 40 words (feedback.md says which file to write). "
                                   "--final takes out any sentence that still fails (words/dropped.json). --arc does "
                                   "the same for the arc (arc.json, arc-fix.json), and --arc --final writes it in.")
    p.add_argument("--lesson", required=True)
    p.add_argument("--final", action="store_true", help="take out the sentences that still fail, after the rounds")
    p.add_argument("--arc", action="store_true", help="the arc's round (after check-text --final)")
    p.set_defaults(func=check_text_tool)
    p = sub.add_parser("erase", help="PAID, one low render a unit. v3: erase the finish backward by the plan's units (the chain).",
                       description="Makes <lesson>/chain/: P<nn>.png (the picture with every unit after nn erased), "
                                   "D<nn>.png (what unit nn adds), C<nn>.png (its core), chain.json, chain.jpg and "
                                   "looks/ (one picture a unit for the checker, with asked.json). One render a unit "
                                   "after the first, each made from the last picture; of each only what changed by a "
                                   "lot is kept. The same picture and request come back from the render cache for "
                                   "nothing, so running it again pays only for what changed. A unit whose thing was "
                                   "left standing is asked for again by itself. plan-check prints the number of "
                                   "renders before any is paid for (about 2 cents each).")
    p.add_argument("--lesson", required=True)
    p.add_argument("--redo", help="units to ask for again and why, e.g. 8:stray,10:left (left: part of it was left "
                                  "standing; stray: the render changed something else)")
    p.add_argument("--probe", type=int, help="render this one unit erased from the finish alone, to see whether its "
                                             "request works, into chain/probe/")
    p.add_argument("--no-auto", action="store_true", help="don't ask again by itself for a unit left standing")
    p.add_argument("--quality", choices=QUALITIES, default="low")
    p.add_argument("--max-cost", type=float, help="dollar cap on the chain's own renders, redos included (default: "
                                                  "5 cents a unit plus 7, twice what the chain costs once)")
    p.set_defaults(func=erase_tool)
    p = sub.add_parser("plan-check", help="Free. v3: what's wrong with a version 3 plan, and the units its chain will render.",
                       description="Checks plan.json (\"plan_version\": 3) against itself, the technique's ranges, the "
                                   "element techniques and the stroke cards. Prints `problems`, each saying what to "
                                   "change; `units`, one for each render the chain will make, with what the render is "
                                   "asked for (`kind`: first, bare, behind, back); `mixes` against the technique's "
                                   "`max_mixes`; and `mix_again`, the paints used again after they've dried on the "
                                   "palette. It knows nothing of the picture.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=plan_check_tool)
    p = sub.add_parser("library", help="Free. v3.1: the library's list for the plan's writer, and the files it picks.",
                       description="With no --picks: every element technique (as `elements` prints it), every "
                                   "stroke card in a line (id, name, result), the research's \"For Gesso\" section "
                                   "and the headings of its other sections. With --picks <file> ({\"elements\": [], "
                                   "\"strokes\": [], \"research\": [headings]}): copies what was picked into "
                                   "<lesson>/library/ (elements/, strokes/, research.md with \"For Gesso\" first), "
                                   "added to what was picked before. A heading matches without its #s or number.")
    p.add_argument("--lesson", required=True)
    p.add_argument("--picks", help="a JSON file of the picks")
    p.set_defaults(func=library_tool)
    p = sub.add_parser("plan-change", help="Free. v3.1: make the plan's writer's changes to plan.json, then plan-check.",
                       description="Applies a changes file (the shape is in plan-brief.md: fields to set on a thing, "
                                   "paint, stage or step, paints to rename or merge, steps to add or move) to "
                                   "plan.json and prints plan-check's output. A file that is a whole plan replaces "
                                   "plan.json. Changes that don't apply are a problem and leave plan.json as it was. "
                                   "Each one applied is kept in plan-changes.json.")
    p.add_argument("--lesson", required=True)
    p.add_argument("--changes", required=True, help="a JSON file of the changes, or a whole plan")
    p.set_defaults(func=plan_change_tool)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tools.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="tool", required=True, metavar="TOOL")
    add_filters(sub)
    add_render(sub)
    add_lesson_tools(sub)
    add_step_tools(sub)
    add_v3_tools(sub)
    return ap


def main(argv: list[str] | None = None, client=None) -> int:
    a = build_parser().parse_args(argv)
    started = time.time()
    try:
        result = a.func(a, client=client) if a.tool in ("render", "erase") else a.func(a)
    except Refused as e:
        emit({"refused": str(e)})
        return 2
    result.setdefault("seconds", round(time.time() - started, 2))
    emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
