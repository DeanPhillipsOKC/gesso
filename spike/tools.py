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
    import yaml
    from run import LessonPlan

    raw = json.loads((lesson / "plan.json").read_text(encoding="utf-8"))
    technique = yaml.safe_load((ROOT / raw["technique"]).read_text(encoding="utf-8"))
    if raw.get("palette"):  # the painter's own tubes (palettes/<name>.yaml) instead of the technique's five
        technique["palette"], technique["palette_name"] = load_palette(raw["palette"])
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
    paths = [lesson / f"{i + 1:02d}_{s.id}.png" for i, s in enumerate(plan.steps)]
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
    from run import sample_swatches

    lesson = Path(a.lesson)
    raw, plan, technique = load_plan(lesson)
    finish = lesson / "99_finish.png"
    if not finish.exists():
        raise Refused(f"no finished painting at {finish}; the swatches are sampled from it")
    sample_swatches(plan, finish)
    mixes = compute_mixes(lesson, plan, technique)
    return {"json": str(lesson / "mixes.json"), "cost_usd": 0.0,
            "paints": [{"name": n, "recipe": m["text"], "target": m["target_hex"], "mixed": m["mixed_hex"],
                        "delta_e": m["delta_e"], "reachable": m["reachable"], "your_recipe": m["guess_recipe"]}
                       for n, m in mixes.items()],
            "unreachable": [n for n, m in mixes.items() if not m["reachable"]]}


def publish(a: argparse.Namespace) -> dict:
    """Build lesson.json and lesson.html from plan.json, text.json, the images, and the ledger."""
    from lesson_page import page
    from run import CLAUDE_MODEL, sample_swatches

    lesson = Path(a.lesson)
    raw, plan, technique = load_plan(lesson)
    paths = step_paths(lesson, plan)
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise Refused(f"missing step images: {missing}")
    sample_swatches(plan, paths[-1])
    mixes = compute_mixes(lesson, plan, technique)
    text_path = lesson / "text.json"
    text = {t["stage_id"]: t for t in json.loads(text_path.read_text(encoding="utf-8"))["steps"]} if text_path.exists() else {}
    review_path = lesson / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
    notes_path = lesson / "notes.json"  # the skill's reasoning: technique, order, filters, throwaways
    notes = json.loads(notes_path.read_text(encoding="utf-8")) if notes_path.exists() else {}
    led = LessonLedger(lesson)

    def paint_dict(p) -> dict:
        d = p.model_dump()
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
    ]
    from version import stamp
    old = lesson / "lesson.json"
    from version import with_made
    old_stamp = (json.loads(old.read_text(encoding="utf-8")).get("gesso") or {}) if old.exists() else None
    previous = old_stamp.get("version", "before stamps") if old_stamp is not None else None
    lesson_data = {
        "gesso": with_made(stamp(), old_stamp or None),
        "canvas": (json.loads((lesson / "canvas.json").read_text(encoding="utf-8")) if (lesson / "canvas.json").exists() else {}).get("canvas"),
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
    (lesson / "lesson.json").write_text(json.dumps(lesson_data, indent=2), encoding="utf-8")
    (lesson / "lesson.html").write_text(page(lesson_data, technique, lesson), encoding="utf-8")
    artifact = lesson / "lesson-artifact.html"
    artifact.write_text(page(lesson_data, technique, lesson, embed=True), encoding="utf-8")
    # one self-contained HTML document (images inlined), for the lessons site or to send as a file
    (lesson / "lesson-standalone.html").write_text(page(lesson_data, technique, lesson, embed=True, standalone=True),
                                                 encoding="utf-8")
    from lesson_embed import export
    embed = export(lesson_data, technique, lesson)  # one folder a blog post or another page can show as a walkthrough

    by_source: dict[str, int] = {}
    for st in stages:
        k = st["made_with"].split(":")[0]
        by_source[k] = by_source.get(k, 0) + 1
    renders = [c for c in led.calls if c.get("tool") == "render"]
    result = {"html": str(lesson / "lesson.html"), "artifact": str(artifact),
            "artifact_mb": round(artifact.stat().st_size / 1e6, 2), "embed": embed,
            "gesso": lesson_data["gesso"], "previous_version": previous, "steps": len(stages), "steps_by_source": by_source,
            "diagrams": sum(1 for st in stages if st["construct"]),
            # a diagram the page can't explain: the skill's beginner check didn't write down why
            "undocumented_diagrams": [st["id"] for st in stages if st["construct"] and st["id"] not in
                                      ((notes.get("beginner_check") or {}).get("diagrams") or {})],
            "unreachable_paints": [n for n, m in mixes.items() if not m["reachable"]],
            # steps whose instructions run past the word budget in the skill (about 100 words)
            "long_steps": [{"id": st["id"], "words": n} for st in stages
                           if (n := sum(len(x.split()) for x in st["steps"])) > STEP_WORDS],
            # paints an instruction or values table names that aren't in the step's colors, so their recipe never shows
            "paints_not_listed": [{"id": st["id"], "paint": n} for st in stages for n in paints
                                  if n not in {c["name"] for c in st["colors"]}
                                  and (re.search(rf"{re.escape(n)}", " ".join(st["steps"]), re.I)
                                       or any(v.get("paint") == n for v in st.get("values", [])))],
            # paints whose computed recipes come out the same (or mix within Delta E 3): two names, one color
            "duplicate_recipes": duplicate_recipes(mixes),
            # steps that turn a big area from flat to textured at once: split them with split-texture
            "texture_jumps": texture_jumps(lesson, paths),
            # single instructions past the skill's budget (about 35 words): usually two moves to split
            "long_instructions": [{"id": st["id"], "n": k + 1, "words": len(x.split())} for st in stages
                                  for k, x in enumerate(st["steps"]) if len(x.split()) > INSTRUCTION_WORDS],
            "paid_renders": sum(1 for c in renders if not c.get("cached")),
            "cached_renders": sum(1 for c in renders if c.get("cached")), "image_cost_usd": led.total_cost}
    # every publish that changes the lesson is kept, with its version (site/history/, owner, 2026-11-12)
    from history import record
    result["history"] = record(lesson, lesson_data, result)
    return result


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
    try:
        r = cv.fit(ImageOps.exif_transpose(Image.open(src)), a.canvas, tuple(a.focus), tuple(a.keep) if a.keep else None,
                   a.orientation)
    except ValueError as err:
        raise Refused(str(err)) from err
    out = lesson / "00_canvas_frame.png"
    r.pop("frame").save(out)
    info = {**r, "input": str(src), "frame": str(out), "why": a.why, "grid_note": cv.grid_note(r["canvas"])}
    (lesson / "canvas.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    LessonLedger(lesson).append({"tool": "filter", "filter": "fit-canvas", "step": "", "why": a.why, "input": str(src),
                                 "out": str(out), "settings": {"canvas": a.canvas, "mode": r["mode"]}, "cost_usd": 0.0})
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
    stem = src.name.split("_skill_")[0]
    dst = src.parent / f"{stem}_skill_{dt.datetime.now():%Y%m%d-%H%M%S}"
    skip = {"trials", "versions", "embed", "canvas"}
    shutil.copytree(src, dst, ignore=lambda d, names: [n for n in names if Path(d) == src and n in skip])
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
    for name in ("lesson.json", "lesson.html", "lesson-artifact.html", "lesson-standalone.html"):
        (dst / name).unlink(missing_ok=True)  # a new lesson: stamped with this version, not the one it came from
    led = LessonLedger(dst)
    with led.locked():
        # keep what this lesson still uses (the finish and the prep pictures); the step renders aren't used
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
    p.set_defaults(func=publish)

    p = sub.add_parser("mix", help="Free. Compute every paint's recipe from the palette tubes (pigment mixing, not by eye).",
                       description="Snap paint swatches to the finish, then solve each paint's recipe from the technique's "
                                   "tubes with a pigment mixing model (Mixbox). Writes <lesson>/mixes.json with the recipe, "
                                   "the mixed color, and how far it lands from the swatch (Delta E). publish runs it too.")
    p.add_argument("--lesson", required=True)
    p.set_defaults(func=mix_tool)

    p = sub.add_parser("fit-canvas", help="Free. Fit the photo to the painter's canvas size: crop, or set up an extend render.",
                       description="Before planning: fits the photo to a canvas (e.g. 11x14, either way up; 10x10) and to "
                                   "the image model's nearest frame. Writes <lesson>/00_canvas_frame.png and canvas.json. "
                                   "When needs_render is true, render it once to fill the gray areas (see the skill, 0b2).")
    p.add_argument("input")
    p.add_argument("--lesson", required=True)
    p.add_argument("--canvas", required=True, help="width x height in inches, e.g. 11x14")
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
    p = sub.add_parser("site-refresh", help="Free. Add new runs of the site's lessons as versions on their tiles.",
                       description="For every lesson on the site, each kept run of the same picture in output/ becomes a "
                                   "version in the tile's pick list (its page goes to lessons/<slug>/v/<run>/ once, never "
                                   "rewritten). Commit and push site/ after.")
    p.set_defaults(func=lambda a: {"versions": __import__("site_lessons").refresh(), "cost_usd": 0.0})
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


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tools.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="tool", required=True, metavar="TOOL")
    add_filters(sub)
    add_render(sub)
    add_lesson_tools(sub)
    return ap


def main(argv: list[str] | None = None, client=None) -> int:
    a = build_parser().parse_args(argv)
    started = time.time()
    try:
        result = a.func(a, client=client) if a.tool in ("render", "render-step", "finish-from-step") else a.func(a)
    except Refused as e:
        emit({"refused": str(e)})
        return 2
    result.setdefault("seconds", round(time.time() - started, 2))
    emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
