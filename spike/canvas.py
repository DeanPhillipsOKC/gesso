"""Fit a picture to the painter's canvas before the lesson is planned (owner, 2026-11-11).

    fit(image, "11x14", focus=(fx, fy), keep=(x0, y0, x1, y1), orientation="auto") -> dict

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

import re

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


def frame_for(aspect: float) -> tuple[int, int]:
    """The model size the canvas fills the most of, so the least is rendered only to be cropped away."""
    def used(f):
        fa = f[0] / f[1]
        return aspect / fa if aspect < fa else fa / aspect
    return max(FRAMES.values(), key=used)


def _crop_box(W: int, H: int, target: float, focus: tuple[float, float]) -> tuple[int, int, int, int]:
    """The biggest box of the target shape, centered on the focal point as far as the edges allow."""
    if W / H > target:
        cw, ch = round(H * target), H
    else:
        cw, ch = W, round(W / target)
    fx, fy = focus[0] * W, focus[1] * H

    def place(f: float, size: int, full: int) -> int:
        # Center the focal point, as far as the edges allow. The picture's own composition already put it where
        # it looks right; keeping it near the middle of what's left changes that the least.
        return round(min(max(f - size / 2, 0), full - size)) if size < full else 0

    x0, y0 = place(fx, cw, W), place(fy, ch, H)
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
        box = _crop_box(W, H, target, focus)
        lost = 1 - (box[2] - box[0]) * (box[3] - box[1]) / (W * H)
        k = keep or (focus[0], focus[1], focus[0], focus[1])
        keeps = box[0] <= k[0] * W and box[1] <= k[1] * H and box[2] >= k[2] * W and box[3] >= k[3] * H
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
