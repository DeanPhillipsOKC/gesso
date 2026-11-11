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
    return raw, LessonPlan.model_validate(raw), technique


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
    mixes = {}
    for p in plan.paints:
        m = mixing.solve(p.hex, tubes)
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

    stages = [
        {
            "id": s.id, "name": s.name, "image": paths[i].name, "paints": s.paints, "looks_like": s.looks_like,
            "steps": txt(s, "what_to_do", s.how), "mixes": txt(s, "mixes", []),
            "colors": [paints[c] for c in s.colors if c in paints],
            "paint_notes": txt(s, "paint_notes", []), "watch_out": txt(s, "watch_out", s.watch_out),
            "brushes": s.brushes, "dry_time": technique["dry_time"],
            "made_with": txt(s, "made_with", "render"), "reason": txt(s, "reason", ""),
            "brush_list": txt(s, "brushes", []), "strokes": txt(s, "strokes", []), "construct": txt(s, "construct", {}),
        }
        for i, s in enumerate(plan.steps)
    ]
    lesson_data = {
        "photo": photo.name, "photo_file": photo_copy.name if photo_copy.exists() else "", "technique": technique["id"], "mode": "paint-lesson skill", "variant": "claude-code",
        "quality": raw.get("quality", "low"), "image_model": IMAGE_MODEL, "claude_model": f"{CLAUDE_MODEL} (Claude Code)",
        "photo_read": {"subject": plan.subject, "focal_point": plan.focal_point, "light": plan.light,
                       "components": plan.components, "mixes": list(paints.values())},
        "finish_issues": review.get("finish_issues", []), "review_issues": review.get("review_issues", []),
        "notes": notes, "stages": stages, "calls": led.calls, "total_cost_usd": led.total_cost,
        "total_seconds": round(sum(c.get("seconds", 0) for c in led.calls), 1),
    }
    (lesson / "lesson.json").write_text(json.dumps(lesson_data, indent=2), encoding="utf-8")
    (lesson / "lesson.html").write_text(page(lesson_data, technique, lesson), encoding="utf-8")
    artifact = lesson / "lesson-artifact.html"
    artifact.write_text(page(lesson_data, technique, lesson, embed=True), encoding="utf-8")

    by_source: dict[str, int] = {}
    for st in stages:
        k = st["made_with"].split(":")[0]
        by_source[k] = by_source.get(k, 0) + 1
    renders = [c for c in led.calls if c.get("tool") == "render"]
    return {"html": str(lesson / "lesson.html"), "artifact": str(artifact),
            "artifact_mb": round(artifact.stat().st_size / 1e6, 2), "steps": len(stages), "steps_by_source": by_source,
            "diagrams": sum(1 for st in stages if st["construct"]),
            # a diagram the page can't explain: the skill's beginner check didn't write down why
            "undocumented_diagrams": [st["id"] for st in stages if st["construct"] and st["id"] not in
                                      ((notes.get("beginner_check") or {}).get("diagrams") or {})],
            "unreachable_paints": [n for n, m in mixes.items() if not m["reachable"]],
            "paid_renders": sum(1 for c in renders if not c.get("cached")),
            "cached_renders": sum(1 for c in renders if c.get("cached")), "image_cost_usd": led.total_cost}


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
    if not result["png"]:
        result["note"] = "No PNG: no Chrome or Edge found. Open the HTML in a browser, or serve the folder and look."
    return result


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
        img = f.grid(rgb, a.cells)
        settings = {"cells": a.cells}
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
             [("--cells", dict(type=int, default=4, help="squares along the long side (default 4)"))]),
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
        result = a.func(a, client=client) if a.tool in ("render", "render-step") else a.func(a)
    except Refused as e:
        emit({"refused": str(e)})
        return 2
    result.setdefault("seconds", round(time.time() - started, 2))
    emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
