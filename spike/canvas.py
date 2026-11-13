"""Fit a picture to the painter's canvas before the lesson is planned (owner, 2026-11-11).

    fit(image, "11x14", focus=(fx, fy), keep=(x0, y0, x1, y1), orientation="auto") -> dict
    default_size(aspect, orientation="auto")  -> "11x14": the standard size closest to a picture's shape
    lesson_canvas(lesson)                     -> canvas.json's contents; a lesson with none gets the default size

A canvas has a shape, and the lesson should match it: if you only have square canvases, you shouldn't have to
imagine how a wide picture fits. Two shapes matter:
- the canvas: the painter's real one, e.g. 11 x 14 in (either way up), 24 x 30, or a wide 10 x 19;
- the frame: the image model only makes 1024x1024, 1536x1024, and 1024x1536, so renders happen in the nearest one,
  with the canvas inside it. Every step picture is cropped back to the canvas box for the page.

The fit, cheapest first:
- none: the picture already has the canvas's shape (within 3%);
- crop (free): cut plain edges to the canvas shape, keeping the subject (`keep`) whole and the focal point as central
  as the edges allow; only when it loses at most 35% of the picture;
- extend (one paid render): the subject wouldn't survive a crop, so the picture is placed whole on the canvas and
  the model paints the rest of the scene into the empty edges.
Either way, if the frame is a different shape from the canvas, the bands outside the canvas are filled by the
same render (they're cropped away, so they only need to continue the scene plausibly).
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from PIL import Image

FRAMES = {"square": (1024, 1024), "landscape": (1536, 1024), "portrait": (1024, 1536)}
PAD = (128, 128, 128)  # flat gray: the render prompt says to replace it
SAME = 0.03  # aspect difference that counts as the same shape
MAX_CROP_LOSS = 0.35  # a 3:2 picture cropped square loses a third; that's fine when the subject survives


def parse(spec: str) -> tuple[float, float]:
    """'11x14', '11 x 14 in', '24x30in', '10X19' -> (11.0, 14.0)."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*(?:in|inch|inches|\")?\s*", spec)
    if not m:
        raise ValueError(f"canvas size {spec!r}: use width x height in inches, like 11x14")
    return float(m.group(1)), float(m.group(2))


def orient(w: float, h: float, picture_aspect: float, orientation: str = "auto") -> tuple[float, float]:
    """A rectangular canvas hangs either way; pick the way closer to the picture unless told."""
    short, long_ = sorted((w, h))
    if orientation == "portrait":
        return short, long_
    if orientation == "landscape":
        return long_, short
    if short == long_:
        return w, h
    return (long_, short) if picture_aspect >= 1 else (short, long_)


# Every version 2 lesson has a canvas size, so its steps say where in inches (#122, owner 2026-11-13: "Rewrite the
# steps in inches"). Without --canvas the lesson takes the standard size closest to the picture's shape.
STANDARD = ["8x10", "9x12", "11x14", "12x16", "16x20"]
DEFAULT = "11x14"  # when two sizes fit equally well (within SAME of the best shape), 11x14 wins, else the nearer size


def default_size(aspect: float, orientation: str = "auto") -> str:
    """The standard canvas closest to a picture's shape, as a size spec ("11x14"). Sizes whose shape is within SAME of
    the best fit equally well: then 11x14 when it's one of them, else the one closest to it in area (a 3:2 picture
    fits 9x12 and 12x16 exactly as well, and gets 12x16)."""
    def off(spec: str) -> float:
        w, h = orient(*parse(spec), aspect, orientation)
        return abs(math.log(aspect / (w / h)))
    best = min(off(s) for s in STANDARD)
    fits = [s for s in STANDARD if off(s) - best <= math.log(1 + SAME)]
    if DEFAULT in fits:
        return DEFAULT
    area = math.prod(parse(DEFAULT))
    return min(fits, key=lambda s: abs(math.prod(parse(s)) - area))


class NoCanvas(ValueError):
    """A version 2 lesson with no canvas size, and none the tools can pick without changing the picture."""


def lesson_canvas(lesson: Path) -> dict:
    """canvas.json's contents. A lesson without one (it skipped fit-canvas, like the test fixtures) gets the standard
    size closest to its finish's shape, recorded with "chosen": "default", when that size has the finish's shape
    (within SAME), so nothing is cropped. Otherwise it's refused: cropping a finished picture would cut parts the
    plan already has, so the canvas is fitted before the finish (skill step 0b2)."""
    lesson = Path(lesson)
    path = lesson / "canvas.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    finish = lesson / "99_finish.png"
    fix = (f"Run fit-canvas <photo> --lesson {lesson} before the finish (without --canvas it picks the standard size "
           "closest to the photo's shape).")
    if not finish.exists():
        raise NoCanvas(f"no canvas size: {path} is missing and there's no 99_finish.png to fit one to. {fix}")
    with Image.open(finish) as im:
        W, H = im.size
    spec = default_size(W / H)
    w, h = orient(*parse(spec), W / H)
    if abs((W / H) / (w / h) - 1) > SAME:
        raise NoCanvas(f"no canvas size: {path} is missing, and the finish ({W} x {H}) isn't the shape of a standard "
                       f"canvas (the nearest is {w:g} x {h:g} in), so the steps can't say where in inches. {fix}")
    canvas = {"w_in": w, "h_in": h, "orientation": "square" if w == h else ("landscape" if w > h else "portrait")}
    info = {"canvas": canvas, "chosen": "default", "mode": "none", "lost_share": 0.0, "canvas_box": [0.0, 0.0, 1.0, 1.0],
            "why": "no --canvas: the standard size closest to the finish's shape", "grid_note": grid_note(canvas)}
    path.write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info


def frame_for(aspect: float) -> tuple[int, int]:
    """The model size the canvas fills the most of, so the least is rendered only to be cropped away."""
    def used(f):
        fa = f[0] / f[1]
        return aspect / fa if aspect < fa else fa / aspect
    return max(FRAMES.values(), key=used)


def _crop_box(W: int, H: int, target: float, focus: tuple[float, float], keep=None) -> tuple[int, int, int, int]:
    """The biggest box of the target shape. It starts centered on the picture, so the cut is split evenly between
    both sides and the picture's own composition changes least, then shifts only as far as it must to keep the
    subject (or, without one, the focal point) inside (11x14 run, 2026-11-11: centering on an off-center focal
    point took the whole cut from one side, into the hill)."""
    if W / H > target:
        cw, ch = round(H * target), H
    else:
        cw, ch = W, round(W / target)
    k = keep or (focus[0], focus[1], focus[0], focus[1])

    def place(lo: float, hi: float, size: int, full: int) -> int:
        if size >= full:
            return 0
        start = (full - size) / 2  # split evenly
        start = min(start, lo)  # shift so the subject's near edge is in
        start = max(start, hi - size)  # and its far edge
        return round(min(max(start, 0), full - size))

    x0 = place(k[0] * W, k[2] * W, cw, W)
    y0 = place(k[1] * H, k[3] * H, ch, H)
    return x0, y0, x0 + cw, y0 + ch


def fit(img: Image.Image, canvas: str, focus=(0.5, 0.5), keep=None, orientation: str = "auto") -> dict:
    img = img.convert("RGB")
    W, H = img.size
    cw_in, ch_in = orient(*parse(canvas), W / H, orientation)
    target = cw_in / ch_in
    result = {"canvas": {"w_in": cw_in, "h_in": ch_in, "orientation": "square" if cw_in == ch_in else
                         ("landscape" if cw_in > ch_in else "portrait")}}

    # 1. the picture on the canvas
    if abs((W / H) / target - 1) <= SAME:
        mode, on_canvas, lost = "none", img, 0.0
    else:
        box = _crop_box(W, H, target, focus, keep)
        lost = 1 - (box[2] - box[0]) * (box[3] - box[1]) / (W * H)
        k = keep or (focus[0], focus[1], focus[0], focus[1])
        keeps = (box[0] <= k[0] * W + 1 and box[1] <= k[1] * H + 1 and box[2] >= k[2] * W - 1
                 and box[3] >= k[3] * H - 1)  # a pixel of rounding either way
        if keeps and lost <= MAX_CROP_LOSS:
            mode, on_canvas = "crop", img.crop(box)
            result["crop_box"] = list(box)
        else:
            mode = "extend"
            cw, ch = (W, round(W / target)) if W / H > target else (round(H * target), H)
            on_canvas = Image.new("RGB", (cw, ch), PAD)
            on_canvas.paste(img, ((cw - W) // 2, (ch - H) // 2))
            lost = 0.0
    result.update(mode=mode, lost_share=round(lost, 3))

    # 2. the canvas in the model's frame
    FW, FH = frame_for(target)
    if mode == "crop" and abs((W / H) / (FW / FH) - 1) <= SAME:
        # The picture already has the frame's shape, so the frame is just the picture: what the crop cut off is
        # exactly what fills the bands. No render (11x14 run, 2026-11-11).
        box = result["crop_box"]
        result["frame"] = img.resize((FW, FH), Image.LANCZOS)
        result["frame_size"] = [FW, FH]
        result["canvas_box"] = [round(box[0] / W, 4), round(box[1] / H, 4), round(box[2] / W, 4), round(box[3] / H, 4)]
        result["needs_render"] = False
        return result
    if abs((FW / FH) / target - 1) <= SAME:
        bw, bh = FW, FH
    elif FW / FH > target:
        bw, bh = round(FH * target), FH
    else:
        bw, bh = FW, round(FW / target)
    x0, y0 = (FW - bw) // 2, (FH - bh) // 2
    frame = Image.new("RGB", (FW, FH), PAD)
    frame.paste(on_canvas.resize((bw, bh), Image.LANCZOS), (x0, y0))
    result["frame"] = frame
    result["frame_size"] = [FW, FH]
    result["canvas_box"] = [round(x0 / FW, 4), round(y0 / FH, 4), round((x0 + bw) / FW, 4), round((y0 + bh) / FH, 4)]
    result["needs_render"] = mode == "extend" or (bw, bh) != (FW, FH)
    return result


def crop_to_canvas(img: Image.Image, box: list[float]) -> Image.Image:
    W, H = img.size
    return img.crop((round(box[0] * W), round(box[1] * H), round(box[2] * W), round(box[3] * H)))


def grid_note(canvas: dict) -> str:
    """'Each 10% is 1.1 in across and 1.4 in down.' so grid positions can be marked with a ruler."""
    return f"Each 10% is {canvas['w_in'] / 10:g} in across and {canvas['h_in'] / 10:g} in down."
