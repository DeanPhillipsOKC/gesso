"""Gesso pipeline spike (#3): photo in, step-by-step painting lesson out, as a folder and an HTML page.

    python spike/run.py photos/sleeping-cat.jpg
    python spike/run.py photos/sleeping-cat.jpg --mode forward --variant templates --quality max

Pipeline:
  0. Simplify the photo into a reference matched to the skill level.
  1. (claude variant) Claude reads the photo and reference: focal point, mixes, a note per stage.
  2. Paint the finished painting from the reference.
  3. Make the earlier stages (see --mode).
  4. (claude variant) Claude writes each step's instructions from the finished stage images.
  5. Write lesson.json, lesson.html, and the cost and time of every call.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import time
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from PIL import Image, ImageOps
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CLAUDE_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
IMAGE_MODEL = "gpt-image-2.5-sunburst"

# Published per-million-token rates, checked 2026-10-19. Used only to estimate cost.
PRICES = {
    CLAUDE_MODEL: {"input": 4.00, "output": 20.00},
    IMAGE_MODEL: {"text_input": 5.00, "image_input": 8.00, "image_output": 30.00},
}


# ---------------------------------------------------------------------------
# Structured outputs from Claude
# ---------------------------------------------------------------------------


class Mix(BaseModel):
    name: str  # e.g. "Shadow blue"
    recipe: str  # e.g. "Ultramarine, a touch of burnt sienna, white"
    used_for: str


class StageNote(BaseModel):
    stage_id: str
    note: str  # what this stage means for this particular picture


class PhotoRead(BaseModel):
    subject: str
    focal_point: str
    big_shapes: list[str]
    light: str
    mixes: list[Mix]
    stage_notes: list[StageNote]


class StepText(BaseModel):
    stage_id: str
    what_to_do: list[str]
    mixes: list[str]
    watch_out: list[str]


class LessonText(BaseModel):
    steps: list[StepText]


class Paint(BaseModel):
    name: str  # e.g. "Sunset orange"; reused across steps for the same paint
    recipe: str  # e.g. "2 parts yellow, 1 part red, a touch of white"
    hex: str  # approximate swatch color, "#rrggbb"
    used_for: str


class PlannedStep(BaseModel):
    id: str  # short slug, e.g. "sky-gradient"
    name: str  # e.g. "Paint the sunset sky"
    paints: str  # which parts of the picture this step adds
    looks_like: str  # the whole canvas after this step, including what isn't painted yet
    covers_canvas: bool  # true once no white canvas shows anywhere
    colors: list[str]  # Paint names used in this step
    brushes: str
    how: list[str]
    watch_out: list[str]


class LessonPlan(BaseModel):
    subject: str
    focal_point: str
    light: str
    components: list[str]  # the parts of the picture, farthest first
    paints: list[Paint]
    steps: list[PlannedStep]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class Ledger:
    """Records the time and estimated cost of every API call."""

    def __init__(self):
        self.calls: list[dict] = []

    def add(self, step: str, model: str, seconds: float, usage: dict, cost: float):
        self.calls.append({"step": step, "model": model, "seconds": round(seconds, 1), "usage": usage, "cost_usd": round(cost, 4)})
        print(f"  {step}: {seconds:.0f}s, ~${cost:.3f}")

    @property
    def total_cost(self) -> float:
        return round(sum(c["cost_usd"] for c in self.calls), 3)

    @property
    def total_seconds(self) -> float:
        return round(sum(c["seconds"] for c in self.calls), 1)


def size_for(path: Path) -> str:
    w, h = ImageOps.exif_transpose(Image.open(path)).size  # honor the camera's rotation flag
    if w > h * 1.15:
        return "1536x1024"
    if h > w * 1.15:
        return "1024x1536"
    return "1024x1024"


def png_bytes(path: Path, max_side: int = 1536) -> bytes:
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def image_block(path: Path) -> dict:
    data = base64.b64encode(png_bytes(path, 1024)).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}


# ---------------------------------------------------------------------------
# Image model
# ---------------------------------------------------------------------------


def edit_image(step: str, inputs: list[Path], prompt: str, out: Path, size: str, quality: str, ledger: Ledger) -> Path:
    from openai import OpenAI

    files = [(p.name, png_bytes(p), "image/png") for p in inputs]
    started = time.time()
    result = OpenAI().images.edit(
        model=IMAGE_MODEL,
        image=files if len(files) > 1 else files[0],
        prompt=prompt,
        size=size,
        quality=quality,
        output_format="png",
    )
    seconds = time.time() - started
    out.write_bytes(base64.b64decode(result.data[0].b64_json))

    usage = result.usage.model_dump() if getattr(result, "usage", None) else {}
    details = usage.get("input_tokens_details") or {}
    p = PRICES[IMAGE_MODEL]
    cost = (
        details.get("text_tokens", 0) * p["text_input"]
        + details.get("image_tokens", 0) * p["image_input"]
        + usage.get("output_tokens", 0) * p["image_output"]
    ) / 1_000_000
    ledger.add(step, IMAGE_MODEL, seconds, usage, cost)
    return out


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------


def ask_claude(step: str, content: list[dict], schema: type[BaseModel], ledger: Ledger):
    import anthropic

    started = time.time()
    response = anthropic.Anthropic().beta.messages.parse(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"effort": "medium"},
        output_format=schema,
        messages=[{"role": "user", "content": content}],
    )
    seconds = time.time() - started
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined the {step} request")
    if response.stop_reason == "max_tokens":
        raise RuntimeError(f"Claude ran out of room in {step}")

    u = response.usage
    p = PRICES[CLAUDE_MODEL]
    cost = (u.input_tokens * p["input"] + u.output_tokens * p["output"]) / 1_000_000
    ledger.add(step, CLAUDE_MODEL, seconds, {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens}, cost)
    return response.parsed_output


def read_photo(photo: Path, reference: Path, technique: dict, ledger: Ledger) -> PhotoRead:
    stage_list = "\n".join(f"- {s['id']}: {s['name']}. {s['looks_like']}" for s in technique["stages"])
    prompt = f"""You're helping a beginner paint the second image (a simplified reference made from the first) in acrylic, using this technique: {technique['name']}. {technique['summary']}

Palette: {', '.join(technique['palette'])}.

Stages:
{stage_list}

Describe what matters for painting this particular picture:
- subject and focal point
- the big shapes, largest first
- where the light comes from and how it falls
- the 4 to 8 paint mixes they'll need, each as a recipe from the palette and what it's for
- for each stage, one or two sentences on what that stage means for this picture (which shapes are dark, what gets blended, which details matter). Use the stage ids above."""
    return ask_claude("read photo", [image_block(photo), image_block(reference), {"type": "text", "text": prompt}], PhotoRead, ledger)


def plan_lesson(photo: Path, reference: Path, technique: dict, ledger: Ledger) -> LessonPlan:
    lo, hi = technique["step_range"]
    rules = "\n".join(f"- {r}" for r in technique["rules"])
    moves = "\n".join(f"- {m}" for m in technique["brush_moves"])
    prompt = f"""You're planning a beginner acrylic painting lesson for the second image (a simplified reference made from the first photo), using the technique "{technique['name']}": {technique['summary']}

Palette (the only tubes): {', '.join(technique['palette'])}.
The painter starts on a plain white canvas.

Rules:
{rules}

Brush moves to choose from:
{moves}

Plan it:
1. Name the subject, the focal point, and where the light comes from.
2. List the parts of this picture (components), farthest back first, e.g. sky gradient, clouds, sun glow, distant tree line, field, trunks, branches.
3. List the paints: every mix the lesson needs, each with a short memorable name, a recipe in parts from the palette tubes, an approximate swatch color as #rrggbb, and what it's for.
4. Plan {lo} to {hi} steps that follow the rules, using as many as this picture needs and no more. For each step:
   - id: short lowercase slug, unique
   - paints: which components it adds
   - looks_like: the WHOLE canvas right after this step, so an image model can paint exactly that state. Say what is painted, and that every part painted in later steps is not there at all yet (not even outlines or gaps). Say which areas, if any, are still plain white canvas.
   - covers_canvas: true once no white canvas shows anywhere
   - colors: names from your paints list
   - brushes, how (2 to 5 short instructions, each naming its brush move), watch_out (1 or 2 beginner mistakes)
   The last step's looks_like is exactly "The finished painting."."""
    plan = ask_claude("plan lesson", [image_block(photo), image_block(reference), {"type": "text", "text": prompt}], LessonPlan, ledger)

    known = {p.name for p in plan.paints}
    seen: set[str] = set()
    for s in plan.steps:
        s.colors = [c for c in s.colors if c in known]
        while s.id in seen:  # keep image file names unique
            s.id += "-2"
        seen.add(s.id)
    if not lo <= len(plan.steps) <= hi:
        print(f"  note: plan has {len(plan.steps)} steps, outside {lo}-{hi}")
    return plan


def write_steps(technique: dict, stages: list[dict], stage_images: list[Path], read: BaseModel | None, ledger: Ledger) -> LessonText:
    content: list[dict] = []
    for stage, img in zip(stages, stage_images):
        content.append({"type": "text", "text": f"Stage {stage['id']} ({stage['name']}):"})
        content.append(image_block(img))
    template = json.dumps([{k: s[k] for k in ("id", "name", "steps", "watch_out")} for s in stages], indent=1)
    context = f"\nWhat we know about this picture: {read.model_dump_json()}\n" if read else ""
    content.append(
        {
            "type": "text",
            "text": f"""These images show a beginner acrylic painting at each stage of the technique "{technique['name']}". Palette: {', '.join(technique['palette'])}.
{context}
Planned steps for each stage:
{template}

For each stage, rewrite the steps for this painting so they match what its image actually shows: name the real shapes and areas, give the mixes to use (by the paint names above, when there are any), and keep the planned advice that still applies. Plain words a beginner understands, short steps, 2 to 5 per stage. Use the stage ids above.""",
        }
    )
    return ask_claude("write steps", content, LessonText, ledger)


# ---------------------------------------------------------------------------
# Lesson
# ---------------------------------------------------------------------------


def stage_prompt(technique: dict, stage: dict, note: str, kind: str) -> str:
    extra = f" For this picture: {note}" if note else ""
    framing = technique["framing"]
    if kind == "backward-covered":
        return (
            "The image is an acrylic painting in progress at a later stage. Show the SAME canvas one stage earlier "
            f"in the technique '{technique['name']}': {stage['looks_like']}{extra} Keep the composition, shapes, and "
            "placement identical. Paint still covers the entire canvas at this stage: no bare or toned canvas shows "
            f"anywhere. Make it rougher and simpler, not emptier. {framing}"
        )
    if kind == "backward":
        ground = "plain white canvas" if technique.get("ground") == "white" else "toned canvas"
        return (
            "The first image is an acrylic painting in progress at a later stage. Show the SAME canvas at an earlier "
            f"stage of the technique '{technique['name']}': {stage['looks_like']}{extra} Keep the composition, shapes, "
            f"and placement identical; only remove what wouldn't be painted yet. Anywhere that isn't painted at this stage "
            f"must show the {ground} exactly as in the second image. {framing}"
        )
    if kind == "forward-first":
        return (
            f"Show the canvas at the very first stage of painting this picture: {stage['looks_like']}{extra} "
            f"The image provided shows where the painting is headed; use it only for placement. {framing}"
        )
    return (
        "The first image is the canvas so far. The second image shows where it's headed. Paint the next stage of "
        f"the technique '{technique['name']}' on top of the first image: {stage['looks_like']}{extra} Don't jump ahead "
        f"to later stages. Keep everything already on the canvas in place. {framing}"
    )


def run(photo: Path, technique_path: Path, mode: str, variant: str, quality: str, out_root: Path) -> Path:
    technique = yaml.safe_load(technique_path.read_text(encoding="utf-8"))
    planned = "stages" not in technique  # rules-only technique: Claude plans the steps for this picture
    tag = "" if technique["id"] == "acrylic-block-in-beginner" else f"{technique['id']}_"  # older runs have no tag
    out = out_root / f"{photo.stem}_{tag}{mode}_{variant}_{quality}_{datetime.now():%Y%m%d-%H%M%S}"
    out.mkdir(parents=True)
    size = size_for(photo)
    ledger = Ledger()
    print(f"{photo.name}: {technique['name']}, mode={mode}, variant={variant}, quality={quality}, size={size}")

    reference = edit_image("simplify", [photo], f"{technique['simplify']['prompt']}", out / "00_reference.png", size, quality, ledger)

    plan = None
    if planned:
        if variant != "claude" or mode == "finish-last":
            raise SystemExit("A rules-only technique needs --variant claude and a finished painting to aim at.")
        plan = plan_lesson(photo, reference, technique, ledger)
        paints = {p.name: p for p in plan.paints}
        stages = [
            {"id": s.id, "name": s.name, "looks_like": s.looks_like, "covers_canvas": s.covers_canvas,
             "steps": s.how, "watch_out": s.watch_out, "brushes": s.brushes, "dry_time": technique["dry_time"],
             "colors": [paints[c].model_dump() for c in s.colors]}
            for s in plan.steps
        ]
        read, notes = None, {}
    else:
        stages = technique["stages"]
        read = read_photo(photo, reference, technique, ledger) if variant == "claude" else None
        notes = {n.stage_id: n.note for n in read.stage_notes} if read else {}

    images: dict[str, Path] = {}
    last = stages[-1]
    finish_prompt = f"{technique['finish']['prompt']} {notes.get(last['id'], '')} {technique['framing']}"

    if mode in ("backward", "anchored", "forward"):
        images[last["id"]] = edit_image("finish", [reference], finish_prompt, out / f"{len(stages):02d}_{last['id']}.png", size, quality, ledger)

    if mode in ("backward", "anchored"):
        if technique.get("ground") == "white":
            # Plain white canvas: no stage and no API call, just the blank surface unpainted areas show.
            tone = out / "00_canvas.png"
            Image.new("RGB", tuple(int(n) for n in size.split("x")), (246, 245, 240)).save(tone)
            lowest = 0
        else:
            # The toned canvas comes first, so every earlier stage can show it in the unpainted areas.
            first = stages[0]
            tone = edit_image(
                first["id"], [images[last["id"]]],
                f"Show only the bare canvas before any painting of this picture: {first['looks_like']} {technique['framing']}",
                out / f"01_{first['id']}.png", size, quality, ledger,
            )
            images[first["id"]] = tone
            lowest = 1
        later = images[last["id"]]
        for i in range(len(stages) - 2, lowest - 1, -1):
            s = stages[i]
            if s.get("trace_finish"):
                # A sketch outlines everything, so trace it from the finish rather than the stage after it.
                images[s["id"]] = edit_image(
                    s["id"], [images[last["id"]], tone],
                    "Draw the sketch for this painting on the toned canvas from the second image: "
                    f"{s['looks_like']}{(' For this picture: ' + notes[s['id']]) if notes.get(s['id']) else ''} "
                    "Trace the big shapes of the first image in the same places and sizes, so later layers line up "
                    f"with the lines. Everything except the lines must look exactly like the second image. {technique['framing']}",
                    out / f"{i + 1:02d}_{s['id']}.png", size, quality, ledger,
                )
                continue
            covered = s.get("covers_canvas", False)
            inputs = [later] if covered else [later, tone]
            prompt = stage_prompt(technique, s, notes.get(s["id"], ""), "backward-covered" if covered else "backward")
            if mode == "anchored" and later != images[last["id"]]:
                # Copying shapes from the finish, not just the stage after, keeps drift from compounding.
                inputs.append(images[last["id"]])
                prompt += (" The last image is the finished painting: copy the shape, edge, and placement of everything "
                           "this stage shows from it exactly, so this stage lines up with the finished painting.")
            later = edit_image(s["id"], inputs, prompt, out / f"{i + 1:02d}_{s['id']}.png", size, quality, ledger)
            images[s["id"]] = later
    else:
        target = images.get(last["id"], reference)  # forward aims at the finish; finish-last aims at the reference
        prev = None
        todo = stages[:-1] if mode == "forward" else stages
        for i, s in enumerate(todo):
            path = out / f"{i + 1:02d}_{s['id']}.png"
            if prev is None:
                prompt = stage_prompt(technique, s, notes.get(s["id"], ""), "forward-first")
                prev = edit_image(s["id"], [target], prompt, path, size, quality, ledger)
            elif s is last:
                prev = edit_image(s["id"], [prev, reference], f"Finish the painting on the first image. {finish_prompt}", path, size, quality, ledger)
            else:
                prev = edit_image(s["id"], [prev, target], stage_prompt(technique, s, notes.get(s["id"], ""), "forward"), path, size, quality, ledger)
            images[s["id"]] = prev

    ordered = [images[s["id"]] for s in stages]
    text = write_steps(technique, stages, ordered, plan or read, ledger) if variant == "claude" else None
    steps_by_id = {t.stage_id: t for t in text.steps} if text else {}
    if plan:  # same shape as a photo read, plus the components and swatches
        read_out = {"subject": plan.subject, "focal_point": plan.focal_point, "light": plan.light,
                    "components": plan.components, "mixes": [p.model_dump() for p in plan.paints]}
    else:
        read_out = read.model_dump() if read else None

    lesson = {
        "photo": photo.name,
        "technique": technique["id"],
        "mode": mode,
        "variant": variant,
        "quality": quality,
        "image_model": IMAGE_MODEL,
        "claude_model": CLAUDE_MODEL if variant == "claude" else None,
        "photo_read": read_out,
        "stages": [
            {
                "id": s["id"],
                "name": s["name"],
                "image": ordered[i].name,
                "steps": steps_by_id[s["id"]].what_to_do if s["id"] in steps_by_id else s["steps"],
                "mixes": steps_by_id[s["id"]].mixes if s["id"] in steps_by_id else [],
                "colors": s.get("colors", []),  # planned lessons: the step's paints with recipes and swatches
                "watch_out": steps_by_id[s["id"]].watch_out if s["id"] in steps_by_id else s["watch_out"],
                "brushes": s["brushes"],
                "dry_time": s["dry_time"],
            }
            for i, s in enumerate(stages)
        ],
        "calls": ledger.calls,
        "total_cost_usd": ledger.total_cost,
        "total_seconds": ledger.total_seconds,
    }
    (out / "lesson.json").write_text(json.dumps(lesson, indent=2), encoding="utf-8")
    photo_copy = out / f"photo{photo.suffix}"
    photo_copy.write_bytes(photo.read_bytes())
    (out / "lesson.html").write_text(render_html(lesson, technique, photo_copy.name), encoding="utf-8")
    print(f"Done: {out / 'lesson.html'}  (~${ledger.total_cost}, {ledger.total_seconds}s of API time)")
    return out


def render_html(lesson: dict, technique: dict, photo_name: str) -> str:
    from html import escape as e

    def items(xs):
        return "".join(f"<li>{e(x)}</li>" for x in xs)

    read = lesson["photo_read"]
    mixes = ""
    if read:
        mixes = "<h2>Your mixes</h2><ul>" + "".join(
            f"<li><b>{e(m['name'])}:</b> {e(m['recipe'])} <span class=muted>({e(m['used_for'])})</span></li>" for m in read["mixes"]
        ) + f"</ul><p><b>Focal point:</b> {e(read['focal_point'])}</p>"

    stages = "".join(
        f"""<section class=stage><img src="{s['image']}" alt="{e(s['name'])}"><div>
<h3>Step {i + 1}: {e(s['name'])}</h3><ol>{items(s['steps'])}</ol>
{''.join(f'<p><span style="display:inline-block;width:1em;height:1em;border-radius:3px;vertical-align:-2px;background:{e(c["hex"])}"></span> <b>{e(c["name"])}:</b> {e(c["recipe"])}</p>' for c in s.get('colors', []))
 or ('<p><b>Mixes:</b> ' + e('; '.join(s['mixes'])) + '</p>' if s['mixes'] else '')}
<p><b>Brushes:</b> {e(s['brushes'])}<br><b>Drying:</b> {e(s['dry_time'])}</p>
<p class=muted><b>Watch out:</b></p><ul class=muted>{items(s['watch_out'])}</ul></div></section>"""
        for i, s in enumerate(lesson["stages"])
    )
    calls = "".join(
        f"<tr><td>{e(c['step'])}</td><td>{e(c['model'])}</td><td>{c['seconds']}s</td><td>${c['cost_usd']:.3f}</td></tr>" for c in lesson["calls"]
    )
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width, initial-scale=1">
<title>Gesso lesson: {e(lesson['photo'])}</title><style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:0 auto;padding:16px;background:#faf8f5;color:#222}}
img{{width:100%;border-radius:8px;display:block}} .pair{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.stage{{display:grid;grid-template-columns:1.2fr 1fr;gap:20px;margin:28px 0;align-items:start}}
.muted{{color:#666}} table{{border-collapse:collapse;font-size:14px}} td{{padding:3px 10px;border-bottom:1px solid #ddd}}
@media (max-width:700px){{.stage,.pair{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>{e(technique['name'])} <span class=muted>(acrylic, beginner)</span></h1>
<p class=muted>{e(lesson['mode'])} / {e(lesson['variant'])} / quality {e(lesson['quality'])} / ~${lesson['total_cost_usd']} / {lesson['total_seconds']}s</p>
<div class=pair><figure><img src="{photo_name}"><figcaption>Your photo</figcaption></figure>
<figure><img src="00_reference.png"><figcaption>Simplified reference</figcaption></figure></div>
{mixes}{stages}
<h2>Calls</h2><table>{calls}</table></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo", type=Path)
    ap.add_argument("--technique", type=Path, default=ROOT / "techniques" / "acrylic-block-in-beginner.yaml")
    ap.add_argument("--mode", choices=["backward", "anchored", "forward", "finish-last"], default="anchored",
                    help="backward: finish first, then each earlier stage by stripping layers off the next. "
                         "anchored: backward, but every stage also copies shapes from the finish. "
                         "forward: finish first, then build up from the start toward it. "
                         "finish-last: build up from the start with no finished target.")
    ap.add_argument("--variant", choices=["claude", "templates"], default="claude")
    ap.add_argument("--quality", choices=["low", "medium", "high", "xhigh", "max"], default="low",
                    help="Image quality. Low while experimenting (docs/decisions.md); raise it if a run stops following directions.")
    ap.add_argument("--out", type=Path, default=ROOT / "output")
    a = ap.parse_args()
    run(a.photo, a.technique, a.mode, a.variant, a.quality, a.out)


if __name__ == "__main__":
    main()
