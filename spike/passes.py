"""Texture jumps between steps, and free in-between passes for them.

    texture_jump(before, after) -> share of the canvas that goes from flat paint to heavy texture in one step
    value_passes(before, after, n) -> n-1 in-between pictures: the step's new marks arriving darkest first

A beginner can't go from flat lavender rows to a field of dabs in one step, and the picture can't show it in one
step either (owner, 2026-11-11: "they're straight lines, then they're textured"; it happened twice). A teacher
builds texture in passes, dark marks first, then lighter ones. So the in-between pictures keep the step's new
paint where it's darkest first and fill in lighter marks later, over the same flat base: dark dabs on flat rows,
then the mid dabs, then everything. Free, no renders.
"""

from __future__ import annotations

import cv2
import numpy as np

CHANGED = 14.0  # Lab distance over which a step changed the area (the step review's change map uses the same)


def _lab(rgb: np.ndarray, sigma: float = 3) -> np.ndarray:
    return cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), sigma), cv2.COLOR_RGB2LAB).astype(np.float32)


def _texture(rgb: np.ndarray) -> np.ndarray:
    """Local detail: how much lightness varies around each pixel. Flat paint is low, dabs and strokes are high."""
    L = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[:, :, 0].astype(np.float32)
    mean = cv2.GaussianBlur(L, (0, 0), 4)
    return np.sqrt(np.maximum(cv2.GaussianBlur(L * L, (0, 0), 4) - mean * mean, 0))


def _dist(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(((a - b) ** 2).sum(axis=2))

FLAT = 6.0  # local texture under which paint reads as flat
TEXTURED = 10.0  # how much texture a step has to add to count as going from flat to textured
JUMP = 0.10  # share of the canvas over which a jump is too much for one step (the lavender dab step was 0.21)


def texture_jump(before: np.ndarray, after: np.ndarray) -> float:
    t0, t1 = _texture(before), _texture(after)
    return float(((t1 - t0 > TEXTURED) & (t0 < FLAT)).mean())


def value_passes(before: np.ndarray, after: np.ndarray, n: int = 3) -> list[np.ndarray]:
    """The n-1 pictures between `before` and `after`, each adding the next-lighter part of the step's new paint."""
    changed = cv2.GaussianBlur((_dist(_lab(before), _lab(after)) > CHANGED).astype(np.float32), (0, 0), 1.5) > 0.5
    L = cv2.cvtColor(after, cv2.COLOR_RGB2LAB)[:, :, 0].astype(np.float32)
    values = L[changed]
    out = []
    for k in range(1, n):
        cut = np.quantile(values, k / n) if values.size else 0
        keep = changed & (L <= cut)
        keep = cv2.morphologyEx(keep.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        alpha = cv2.GaussianBlur(keep.astype(np.float32), (0, 0), 0.8)[..., None]
        out.append(np.clip(before * (1 - alpha) + after * alpha, 0, 255).astype(np.uint8))
    return out
