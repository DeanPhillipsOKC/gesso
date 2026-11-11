"""Packets for the step review (#24): does each step's text get a beginner from its before picture to its after?

    packet(lesson_folder) -> <lesson>/trials/review/NN_<id>.png for every step, plus packet.json

Each PNG is three panels side by side, all with the same 10% grid and labels:
  before | after | what changed (the after picture, dimmed, with changed areas outlined)
The change map is measured, not judged, so a reviewer can point at real changes and can't invent ones that
aren't there. packet.json carries each step's text, strokes, brushes, paints, how much of the canvas changed,
and the technique's stroke_results (what each stroke really leaves), which the review checks strokes against.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

SIDE = 640  # each panel's long side
PAD = 28  # room for the grid labels


def _load(path: Path, size: tuple[int, int] | None = None) -> np.ndarray:
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if size:
        img = img.resize(size, Image.LANCZOS)
    else:
        img.thumbnail((SIDE, SIDE))
    return np.asarray(img).copy()


def changed_mask(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Where the paint changed: Lab difference, blurred so canvas grain and render noise don't count."""
    a = cv2.cvtColor(cv2.GaussianBlur(before, (0, 0), 3), cv2.COLOR_RGB2LAB).astype(np.float32)
    b = cv2.cvtColor(cv2.GaussianBlur(after, (0, 0), 3), cv2.COLOR_RGB2LAB).astype(np.float32)
    diff = np.sqrt(((a - b) ** 2).sum(axis=2))
    mask = (diff > 14).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))


def _change_panel(after: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = (after.astype(np.float32) * 0.35 + 255 * 0.65).astype(np.uint8)  # dim everything
    out[mask > 0] = after[mask > 0]  # changed areas at full strength
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, contours, -1, (220, 30, 60), 2)
    return out


def _grid(img: Image.Image, x0: int, y0: int, w: int, h: int, draw: ImageDraw.ImageDraw, font) -> None:
    for k in range(1, 10):
        x, y = x0 + w * k / 10, y0 + h * k / 10
        draw.line([(x, y0), (x, y0 + h)], fill=(0, 0, 0, 70), width=1)
        draw.line([(x0, y), (x0 + w, y)], fill=(0, 0, 0, 70), width=1)
        draw.text((x - 8, y0 - PAD + 6), f"{k * 10}", fill=(60, 60, 60, 255), font=font)
        draw.text((x0 - PAD + 2, y - 7), f"{k * 10}", fill=(60, 60, 60, 255), font=font)


def sheet(before: np.ndarray, after: np.ndarray, mask: np.ndarray, title: str) -> Image.Image:
    h, w = after.shape[:2]
    panels = [before, after, _change_panel(after, mask)]
    labels = ["BEFORE", "AFTER", "WHAT CHANGED (outlined)"]
    W, H = PAD + 3 * (w + PAD), PAD * 2 + h + 22
    img = Image.new("RGBA", (W, H), (250, 250, 247, 255))
    try:
        font = ImageFont.truetype("arial.ttf", 13)
        big = ImageFont.truetype("arialbd.ttf", 15)
    except OSError:
        font = big = ImageFont.load_default()
    draw = ImageDraw.Draw(img, "RGBA")
    draw.text((PAD, 4), title, fill=(20, 20, 20, 255), font=big)
    for i, (p, lab) in enumerate(zip(panels, labels)):
        x0, y0 = PAD + i * (w + PAD), PAD + 22
        img.paste(Image.fromarray(p), (x0, y0))
        _grid(img, x0, y0, w, h, draw, font)
        draw.text((x0, y0 + h + 4), lab, fill=(20, 20, 20, 255), font=font)
    return img.convert("RGB")


def packet(lesson: Path) -> dict:
    import yaml

    data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
    plan = json.loads((lesson / "plan.json").read_text(encoding="utf-8"))
    technique = yaml.safe_load((Path(__file__).resolve().parent.parent / plan["technique"]).read_text(encoding="utf-8"))
    out = lesson / "trials" / "review"
    out.mkdir(parents=True, exist_ok=True)
    stages = data["stages"]
    steps = []
    for i, s in enumerate(stages):
        after = _load(lesson / s["image"])
        h, w = after.shape[:2]
        prev = lesson / ("00_canvas.png" if i == 0 else stages[i - 1]["image"])
        before = _load(prev, (w, h)) if prev.exists() else np.full_like(after, 246)
        mask = changed_mask(before, after)
        path = out / f"{i + 1:02d}_{s['id']}.png"
        sheet(before, after, mask, f"Step {i + 1} of {len(stages)}: {s['name']}").save(path)
        steps.append({
            "n": i + 1, "id": s["id"], "name": s["name"], "sheet": str(path),
            "changed_share": round(float(mask.mean()), 3),
            "what_to_do": s.get("steps", []), "strokes": s.get("strokes", []),
            "brushes": [b["brush"] for b in s.get("brush_list", [])],
            "paints": [{"name": c["name"], "recipe": c.get("recipe", "")} for c in s.get("colors", [])],
            "watch_out": s.get("watch_out", []),
        })
    result = {"lesson": str(lesson), "level": technique.get("level", "beginner"),
              "stroke_results": technique.get("stroke_results", []), "steps": steps}
    (out / "packet.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return {"packet": str(out / "packet.json"), "sheets": len(steps),
            "changed_share": {s["id"]: s["changed_share"] for s in steps}}
