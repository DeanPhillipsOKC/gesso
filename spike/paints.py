"""The colors a part is actually painted in, measured from the finish (pipeline v2, docs/design/pipeline-v2.md section 9).

    part_colors(finish, mask, k) -> [{"hex", "share", "x", "y"}], darkest first

Claude used to name a lesson's paints and guess where each one sits. Measured, the same finish gives the same
paints every run, and a part's dark, middle, and light come out in the order they're painted.
"""

from __future__ import annotations

import cv2
import numpy as np

MAX_SAMPLE = 40_000  # pixels clustered per part: plenty for a few colors, and quick


def part_colors(finish: np.ndarray, mask: np.ndarray, k: int) -> list[dict]:
    """The part's k main colors (k-means in Lab, fixed seed), darkest first, each with its share of the part and
    a spot (0-1) deep inside a patch of it."""
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return []
    L = cv2.cvtColor(cv2.GaussianBlur(finish, (0, 0), 1.0).astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)
    px = L[ys, xs]
    step = max(1, len(px) // MAX_SAMPLE)
    sample = np.ascontiguousarray(px[::step], np.float32)
    k = max(1, min(k, len(sample)))
    cv2.setRNGSeed(7)
    _, _, centers = cv2.kmeans(sample, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.2), 5,
                               cv2.KMEANS_PP_CENTERS)
    centers = centers[np.argsort(centers[:, 0], kind="stable")]
    label = np.argmin(((px[:, None, :] - centers[None]) ** 2).sum(2), axis=1)
    h, w = mask.shape
    out = []
    for i, c in enumerate(centers):
        rgb = cv2.cvtColor(c.reshape(1, 1, 3).astype(np.float32), cv2.COLOR_LAB2RGB)[0, 0]
        rgb = np.clip(np.round(rgb * 255), 0, 255).astype(int)
        here = np.zeros((h, w), np.uint8)
        here[ys[label == i], xs[label == i]] = 1
        if here.any():
            dist = cv2.distanceTransform(here, cv2.DIST_L2, 3)
            y, x = np.unravel_index(int(dist.argmax()), dist.shape)
        else:
            y, x = int(ys[0]), int(xs[0])
        out.append({"hex": "#%02x%02x%02x" % tuple(rgb), "share": round(float((label == i).mean()), 3),
                    "x": round(x / w, 3), "y": round(y / h, 3)})
    return out
