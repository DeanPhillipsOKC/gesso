"""The image model and the plan model the lesson tools share (spike/tools.py, publish2.py).

    edit_image(step, inputs, prompt, out, size, quality, ledger) -> one paid render, its cost in the ledger
    LessonPlan, Paint, PlannedStep -> the plan as mix, publish, and the seal read it (publish2.as_v1)

This was once the v1 pipeline spike (#3: `python spike/run.py <photo>`, a render per step, Claude planning and
reviewing through the API). That went with the rest of v1 (#82); lessons are made with the /paint-lesson skill.
"""

from __future__ import annotations

import base64
import io
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image, ImageOps
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CLAUDE_MODEL = "claude-opus-5-5"  # the model the skill runs on, stamped on each lesson
IMAGE_MODEL = "gpt-image-2.5-sunburst"

# Published per-million-token rates, checked 2026-10-19. Used only to estimate cost.
PRICES = {
    IMAGE_MODEL: {"text_input": 5.00, "image_input": 8.00, "image_output": 30.00},
}


# ---------------------------------------------------------------------------
# The plan, as publish reads it (a version 2 plan is seen through publish2.as_v1)
# ---------------------------------------------------------------------------


class Paint(BaseModel):
    name: str  # e.g. "Sunset orange"; reused across steps for the same paint
    recipe: str  # e.g. "2 parts yellow, 1 part red, a touch of white"
    hex: str  # "#rrggbb", measured from the finish (paints)
    used_for: str
    sample_x: float  # a spot in the finished painting where this paint shows clearly, 0-1 from the left
    sample_y: float  # 0-1 from the top
    guess_hex: str | None = None  # v1 only (its sampled swatches); kept so lesson.json keeps the key


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
    regions: list[list[float]] | None = None  # v1 only (boxes the lock used); a version 2 step has none
    protect: list[list[float]] | None = None  # v1 only, as regions


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



# ---------------------------------------------------------------------------
# Image model
# ---------------------------------------------------------------------------


# The OpenAI SDK won't build a client without a key. In a cloud session the network proxy adds the
# real key to every request to api.openai.com, so a placeholder is enough to get the request out (#89).
PROXY_KEY_PLACEHOLDER = "sk-proxy-supplies-the-key"


def openai_client():
    from openai import OpenAI

    if not os.environ.get("OPENAI_API_KEY") and (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")):
        return OpenAI(api_key=PROXY_KEY_PLACEHOLDER)
    return OpenAI()



def edit_image(step: str, inputs: list[Path], prompt: str, out: Path, size: str, quality: str, ledger: Ledger,
               client=None) -> Path:
    if client is None:
        client = openai_client()

    files = [(p.name, png_bytes(p), "image/png") for p in inputs]
    started = time.time()
    result = client.images.edit(
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

