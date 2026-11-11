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
import shutil
import sys
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
    def __init__(self, lesson: Path):
        self.path = lesson / "ledger.json"
        self.calls: list[dict] = json.loads(self.path.read_text(encoding="utf-8"))["calls"] if self.path.exists() else []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"calls": self.calls, "total_cost_usd": self.total_cost}
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

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


def render(a: argparse.Namespace, client=None) -> dict:
    reason = (a.why_not_filter or "").strip()
    if not reason:
        raise Refused("--why-not-filter is required: say why no filter or composite can make this step.")
    inputs = [Path(p) for p in a.inputs]
    for p in inputs:
        if not p.exists():
            raise Refused(f"input image not found: {p}")

    lesson = Path(a.lesson)
    ledger = LessonLedger(lesson)
    size = a.size or size_for(inputs[0])
    out = Path(a.out) if a.out else lesson / f"{a.step}.png"
    key = cache_key(inputs, a.prompt, size, a.quality)
    cached = CACHE_DIR / f"{key}.png"
    entry = {"tool": "render", "step": a.step, "model": IMAGE_MODEL, "quality": a.quality, "size": size,
             "reason": reason, "inputs": [str(p) for p in inputs], "out": str(out), "cache_key": key}

    if cached.exists() and not a.fresh:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached, out)
        entry.update(cached=True, seconds=0, cost_usd=0.0)
    else:
        done = ledger.paid_renders_for(a.step)
        if done > a.max_redos:
            raise Refused(f"step '{a.step}' already has {done} renders (1 plus {a.max_redos} redos). "
                          "Flag it for the owner instead of rendering again.")
        estimate = ledger.estimate(a.quality)
        if ledger.total_cost + estimate > a.max_cost:
            raise Refused(f"lesson has spent ${ledger.total_cost:.2f} of its ${a.max_cost:.2f} cap and a "
                          f"{a.quality} render can cost up to ${estimate:.2f}. Flag the step for the owner.")
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = Ledger()
        with contextlib.redirect_stdout(sys.stderr):
            edit_image(a.step, inputs, a.prompt, out, size, a.quality, tmp, client=client)
        call = tmp.calls[-1]
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out, cached)
        entry.update(cached=False, seconds=call["seconds"], cost_usd=call["cost_usd"], usage=call["usage"])

    ledger.calls.append(entry)
    ledger.save()
    return {
        "out": str(out), "step": a.step, "cached": entry["cached"], "cost_usd": entry["cost_usd"],
        "seconds": entry["seconds"], "lesson_total_usd": ledger.total_cost,
        "budget_left_usd": round(a.max_cost - ledger.total_cost, 4),
        "paid_renders_for_step": ledger.paid_renders_for(a.step),
    }


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
# Command line
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tools.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="tool", required=True, metavar="TOOL")
    add_render(sub)
    return ap


def main(argv: list[str] | None = None, client=None) -> int:
    a = build_parser().parse_args(argv)
    started = time.time()
    try:
        result = a.func(a, client=client) if a.tool == "render" else a.func(a)
    except Refused as e:
        emit({"refused": str(e)})
        return 2
    result.setdefault("seconds", round(time.time() - started, 2))
    emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
