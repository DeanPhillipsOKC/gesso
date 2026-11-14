"""Texture jumps between steps.

    texture_jump(before, after) -> share of the canvas that goes from flat paint to heavy texture in one step

A beginner can't go from flat lavender rows to a field of dabs in one step, and the picture can't show it in one
step either (owner, 2026-11-11: "they're straight lines, then they're textured"; it happened twice). A teacher
builds texture in passes. `check` uses this on a version 2 lesson's `full` steps (checks.texture_jumps).
"""

from __future__ import annotations

import cv2
import numpy as np

FLAT = 6.0  # local texture under which paint reads as flat
TEXTURED = 10.0  # how much texture a step has to add to count as going from flat to textured
JUMP = 0.10  # share of the canvas over which a jump is too much for one step (the lavender dab step was 0.21)


def _texture(rgb: np.ndarray) -> np.ndarray:
    """Local detail: how much lightness varies around each pixel. Flat paint is low, dabs and strokes are high."""
    L = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[:, :, 0].astype(np.float32)
    mean = cv2.GaussianBlur(L, (0, 0), 4)
    return np.sqrt(np.maximum(cv2.GaussianBlur(L * L, (0, 0), 4) - mean * mean, 0))


def texture_jump(before: np.ndarray, after: np.ndarray) -> float:
    t0, t1 = _texture(before), _texture(after)
    return float(((t1 - t0 > TEXTURED) & (t0 < FLAT)).mean())
