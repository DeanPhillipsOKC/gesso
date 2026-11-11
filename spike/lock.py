"""Keep finished areas from changing in later step pictures (Gesso issue 30).

    lock(lesson_folder, step_images, finish) -> per-step share of the canvas put back

Each step picture is rendered on its own, and the image model doesn't hold earlier work perfectly still: clouds
shift, a finished pumpkin gets repainted, grass appears in a highlights step. The step review found that in a
third of its problems (#24). A beginner comparing their canvas with the step picture sees changes nobody asked for.

Two rules, from first step to last:
1. Each step says where it paints (and, inside that, what it must leave alone: `protect` boxes, where only the
   step's own paints may change anything) (`regions` in plan.json: boxes, 0-1 from the top left). Outside them, nothing may
   change, so any change there goes back to the previous step's pixels. This catches work arriving early (grass in
   a highlights step) and random repainting.
2. A step with no regions falls back to this: an area is *finished* once the canvas there already looks like the finished
painting (same color and the same amount of texture). A later step has no reason to change a finished area, since
the painting ends up looking like that. So wherever a step's render changes a finished area, the previous step's
pixels go back, with a soft edge. Everything else (new paint, and areas still on their way to the finish) is kept.

Free: no renders. The raw renders are kept in trials/raw/, so locking can be rerun or undone.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

DONE_COLOR = 10.0  # Lab distance (blurred) under which an area matches the finish
DONE_TEXTURE = 6.0  # and a local texture difference under which it has the finish's texture too
CHANGED = 14.0  # Lab distance over which the step changed the area (same as the step review's change map)


def _lab(rgb: np.ndarray, sigma: float = 3) -> np.ndarray:
    return cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), sigma), cv2.COLOR_RGB2LAB).astype(np.float32)


def _texture(rgb: np.ndarray) -> np.ndarray:
    """Local detail: how much lightness varies around each pixel. Flat paint is low, dabs and strokes are high."""
    L = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[:, :, 0].astype(np.float32)
    mean = cv2.GaussianBlur(L, (0, 0), 4)
    return np.sqrt(np.maximum(cv2.GaussianBlur(L * L, (0, 0), 4) - mean * mean, 0))


def _dist(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(((a - b) ** 2).sum(axis=2))


def finished_mask(current: np.ndarray, finish: np.ndarray, canvas: np.ndarray | None = None) -> np.ndarray:
    """Where the canvas already looks like the finished painting: same color and about the same texture. Bare
    canvas never counts, even where the finish is a cream close to it (pumpkin test: blank canvas matched the
    cream vines and was put back as holes)."""
    color = _dist(_lab(current), _lab(finish)) < DONE_COLOR
    texture = np.abs(_texture(current) - _texture(finish)) < DONE_TEXTURE
    mask = color & texture
    if canvas is not None:
        mask &= _dist(_lab(current), _lab(canvas)) > CHANGED
    mask = mask.astype(np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))


def region_mask(shape: tuple[int, int], boxes: list[list[float]] | None, margin: float = 0.03) -> np.ndarray | None:
    """Where a step may paint: its boxes, grown by a small margin so strokes at the edges aren't clipped."""
    if not boxes:
        return None
    h, w = shape
    m = np.zeros((h, w), np.uint8)
    for x0, y0, x1, y1 in boxes:
        m[max(0, int((y0 - margin) * h)):min(h, int((y1 + margin) * h) + 1),
          max(0, int((x0 - margin) * w)):min(w, int((x1 + margin) * w) + 1)] = 1
    return m


STEP_COLOR = 22.0  # Lab distance under which a changed pixel counts as one of the step's own paints


LIGHTNESS_WEIGHT = 0.35  # a paint in shadow or highlight is still that paint: lightness counts for little


def step_paint(render: np.ndarray, colors: list[tuple[int, int, int]]) -> np.ndarray:
    """Where the render shows one of the step's paints, in light or shade (hue and colorfulness matter, lightness
    much less: the pumpkin test's blue-grey shaded vine tendrils were eaten when lightness counted fully), a little
    grown so the edges of a stroke stay too."""
    lab = _lab(render, 1.5)
    near = np.zeros(render.shape[:2], bool)
    for c in colors:
        swatch = cv2.cvtColor(np.uint8([[c]]), cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]
        d = lab - swatch
        near |= np.sqrt((d[..., 0] * LIGHTNESS_WEIGHT) ** 2 + d[..., 1] ** 2 + d[..., 2] ** 2) < STEP_COLOR
    return cv2.dilate(near.astype(np.uint8), np.ones((5, 5), np.uint8))


def lock_one(prev: np.ndarray, render: np.ndarray, finish: np.ndarray, region: np.ndarray | None = None,
             canvas: np.ndarray | None = None, protect: np.ndarray | None = None,
             colors: list[tuple[int, int, int]] | None = None) -> tuple[np.ndarray, float]:
    """The render with every change outside the step's region put back to `prev`. Inside its region the step is
    trusted (balloon test: the finished rule bit a piece out of a newly painted sun), except in its `protect`
    boxes: there only the step's own paints may change things (a vine over a pumpkin stays; the pumpkin repainted
    under it goes back; pumpkin test, 2026-11-11). With no region, changes to already-finished areas are put back
    instead. Returns (image, share of the canvas put back)."""
    changed = (_dist(_lab(prev), _lab(render)) > CHANGED).astype(np.uint8)
    off_limits = finished_mask(prev, finish, canvas) if region is None else (1 - region).astype(np.uint8)
    revert = cv2.morphologyEx(off_limits & changed, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    revert = cv2.dilate(revert, np.ones((5, 5), np.uint8))  # cover the halo around each drifted patch
    alpha = cv2.GaussianBlur(revert.astype(np.float32), (0, 0), 4)  # soft edge, no seams
    if protect is not None and colors:
        guarded = protect & changed & (1 - step_paint(render, colors))
        guarded = cv2.morphologyEx(guarded.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        # a crisp edge here, so the step's new marks next to a protected area stay sharp, not glowy or see-through
        alpha = np.maximum(alpha, cv2.GaussianBlur(guarded.astype(np.float32), (0, 0), 1))
        revert |= guarded
    alpha = alpha[..., None]
    out = render.astype(np.float32) * (1 - alpha) + prev.astype(np.float32) * alpha
    return np.clip(out, 0, 255).astype(np.uint8), float(revert.mean())


def lock(lesson: Path, steps: list[Path], finish: Path, canvas: Path | None = None,
         regions: list[list[list[float]] | None] | None = None,
         protects: list[list[list[float]] | None] | None = None,
         colors: list[list[tuple[int, int, int]]] | None = None) -> dict:
    """Lock every step picture before the finish, in order. `steps` excludes the finish itself; `regions[i]` is
    step i's boxes, or None to use the finished-area rule alone."""
    fin = np.asarray(Image.open(finish).convert("RGB"))
    size = (fin.shape[1], fin.shape[0])
    raw_dir = lesson / "trials" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    prev = (np.asarray(Image.open(canvas).convert("RGB").resize(size)) if canvas and canvas.exists()
            else np.full_like(fin, 246))
    blank = prev.copy()
    report = {}
    for i, path in enumerate(steps):
        raw = raw_dir / path.name
        if not raw.exists():
            shutil.copyfile(path, raw)  # first lock: keep the render as it came
        render = np.asarray(Image.open(raw).convert("RGB").resize(size))
        boxes = regions[i] if regions and i < len(regions) else None
        guard = protects[i] if protects and i < len(protects) else None
        locked, share = lock_one(prev, render, fin, region_mask(fin.shape[:2], boxes), blank,
                                 region_mask(fin.shape[:2], guard, margin=0), colors[i] if colors else None)
        Image.fromarray(locked).save(path)
        report[path.stem] = round(share, 3)
        prev = locked
    return report
