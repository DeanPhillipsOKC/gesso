"""Paint helpers build_steps.py uses to lay a part's paint under what's painted on top of it.

    continue_paint(img, src) -> src's colors carried into the gaps between them
    flat_paint(finish, area, colors) -> the finish's broad color over an area, snapped to the nearest paint

Once the v1 tool that cut every step from the finish by regions (`from-finish`, #8). v2 cuts steps inside real
outlines (build_steps.py, docs/design/pipeline-v2.md) and keeps only these; the rest went with v1 (#82).
"""

from __future__ import annotations

import cv2
import numpy as np

CANVAS = (250, 249, 245)  # the bare canvas before step 1


def lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)


def hex_lab(h: str) -> np.ndarray:
    h = h.lstrip("#")
    rgb = np.array([[[int(h[i:i + 2], 16) for i in (0, 2, 4)]]], np.uint8)
    return lab(rgb)[0, 0]


def _fill_from(img: np.ndarray, src: np.ndarray, sigma: float) -> tuple[np.ndarray, np.ndarray]:
    """Normalized blur: img's colors spread out from the src pixels, and how much support each pixel had."""
    m = src.astype(np.float32)
    num = cv2.GaussianBlur(img.astype(np.float32) * m[..., None], (0, 0), sigma)
    den = cv2.GaussianBlur(m, (0, 0), sigma)
    return num / np.maximum(den, 1e-6)[..., None], den


def continue_paint(img: np.ndarray, src: np.ndarray) -> np.ndarray:
    """The src pixels' colors carried into the gaps between them, the way paint goes on straight through where
    something will be painted on top. Inpainted from the gap's edges (OpenCV Telea) at a quarter size, so the sky
    under the balloon matches the sky right around it instead of the average of the whole sky (a balloon-shaped
    ghost of blue in the first try), then softened."""
    h, w = img.shape[:2]
    small = cv2.resize(img, (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_AREA)
    hole = cv2.resize((~src).astype(np.uint8), (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
    filled = cv2.inpaint(cv2.cvtColor(small, cv2.COLOR_RGB2BGR), hole, 7, cv2.INPAINT_TELEA)
    filled = cv2.cvtColor(filled, cv2.COLOR_BGR2RGB).astype(np.float32)
    # Telea smears straight lines out from the edge (cones under the balloon); soften the inside of big gaps
    inside = cv2.GaussianBlur(cv2.erode(hole, np.ones((5, 5), np.uint8)).astype(np.float32), (0, 0), 3)[..., None]
    filled = filled * (1 - inside) + cv2.GaussianBlur(filled, (0, 0), 6) * inside
    return cv2.resize(filled, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)


def flat_paint(finish: np.ndarray, area: np.ndarray, colors: list[str]) -> np.ndarray:
    """The finish's broad color over the area, snapped to the step's nearest paint: flat, no texture."""
    broad, _ = _fill_from(finish, area, max(finish.shape[:2]) * 0.008)
    if not colors:
        return broad.astype(np.uint8)
    cols = np.array([hex_lab(c) for c in colors])
    rgbs = np.array([[int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)] for c in colors], np.float32)
    L = lab(np.clip(broad, 0, 255).astype(np.uint8))
    idx = np.argmin(((L[:, :, None, :] - cols[None, None]) ** 2).sum(3), axis=2).astype(np.uint8)
    idx = cv2.medianBlur(idx, 7)
    return rgbs[idx]
