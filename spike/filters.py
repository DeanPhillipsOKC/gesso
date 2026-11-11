"""Free, local image filters for painting lessons (#7). Each takes and returns an RGB numpy array.

Called through `spike/tools.py`; kept here so the skill, the contact sheet, and tests share them.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

MAX_SIDE = 1536  # same as the image model's inputs; keeps the slower filters quick


def load(path: Path, max_side: int = MAX_SIDE) -> np.ndarray:
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((max_side, max_side))
    return np.asarray(img).copy()


def save(rgb: np.ndarray, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(path)
    return path


def lightness(rgb: np.ndarray) -> np.ndarray:
    """Perceived lightness, 0-255 (the L of Lab), which matches how values read to a painter."""
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[:, :, 0]


def gray3(channel: np.ndarray) -> np.ndarray:
    return np.dstack([channel] * 3)


def kmeans(samples: np.ndarray, k: int, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """k-means on float32 rows; returns (labels, centers). Seeded so the same picture gives the same result."""
    cv2.setRNGSeed(seed)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, labels, centers = cv2.kmeans(samples.astype(np.float32), k, None, criteria, 4, cv2.KMEANS_PP_CENTERS)
    return labels.ravel(), centers


def _fit_assign(rows: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Fit k-means on a sample of rows (fast on big pictures) and assign every row to its nearest center."""
    rng = np.random.default_rng(7)
    sample = rows if len(rows) <= 60_000 else rows[rng.choice(len(rows), 60_000, replace=False)]
    _, centers = kmeans(sample, k)
    d = ((rows[:, None, :].astype(np.float32) - centers[None, :, :]) ** 2).sum(axis=2)
    return d.argmin(axis=1), centers


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def value_study(rgb: np.ndarray, tones: int = 3) -> np.ndarray:
    """Grayscale reduced to `tones` values, spread evenly from dark to light."""
    L = lightness(rgb)
    labels, centers = _fit_assign(L.reshape(-1, 1), tones)
    order = np.argsort(centers.ravel())
    rank = np.empty(tones, dtype=int)
    rank[order] = np.arange(tones)
    levels = np.linspace(25, 240, tones).astype(np.uint8)  # a painter's darkest dark and lightest light, not pure black/white
    return gray3(levels[rank[labels]].reshape(L.shape))


def notan(rgb: np.ndarray, threshold: int | None = None) -> tuple[np.ndarray, int]:
    """Two values, dark and light. Picks the threshold automatically (Otsu) unless one is given."""
    L = cv2.GaussianBlur(lightness(rgb), (0, 0), max(rgb.shape[:2]) / 400)  # drop speckle so shapes read
    if threshold is None:
        threshold, out = cv2.threshold(L, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        _, out = cv2.threshold(L, threshold, 255, cv2.THRESH_BINARY)
    return gray3(out), int(threshold)


def squint(rgb: np.ndarray, amount: float = 2.0) -> np.ndarray:
    """Heavy blur, like squinting at the subject: details go and the big shapes and values stay."""
    return cv2.GaussianBlur(rgb, (0, 0), max(rgb.shape[:2]) * amount / 100)


def palette(rgb: np.ndarray, colors: int = 6) -> list[dict]:
    """The main colors (k-means in Lab), largest share first: [{"hex", "share", "rgb"}]."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).reshape(-1, 3)
    labels, centers = _fit_assign(lab, colors)
    counts = np.bincount(labels, minlength=colors)
    swatches = []
    for i in np.argsort(-counts):
        c = cv2.cvtColor(centers[i].reshape(1, 1, 3).astype(np.uint8), cv2.COLOR_LAB2RGB)[0, 0]
        swatches.append({"hex": "#%02x%02x%02x" % tuple(int(v) for v in c), "share": round(float(counts[i]) / len(labels), 3),
                         "rgb": [int(v) for v in c]})
    return swatches


def swatch_image(swatches: list[dict], width: int = 900, height: int = 160) -> np.ndarray:
    """A strip of the palette, each color as wide as its share of the picture."""
    out = np.zeros((height, width, 3), np.uint8)
    x = 0
    for i, s in enumerate(swatches):
        w = width - x if i == len(swatches) - 1 else max(1, round(s["share"] * width))
        out[:, x:x + w] = s["rgb"]
        x += w
    return out


def kuwahara(rgb: np.ndarray, radius: int) -> np.ndarray:
    """Edge-keeping smoothing: each pixel takes the mean of whichever of its four corner windows is flattest.
    Flattens texture into painterly patches while keeping edges sharp."""
    img = rgb.astype(np.float32)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    k = radius + 1
    total = np.zeros_like(img)
    weight_sum = np.zeros_like(gray)
    for ax in (0, radius):
        for ay in (0, radius):
            def box(a):
                return cv2.boxFilter(a, -1, (k, k), anchor=(ax, ay), normalize=True, borderType=cv2.BORDER_REFLECT)
            mean = box(img)
            gm = box(gray)
            var = np.maximum(box(gray * gray) - gm * gm, 0)
            # Soft pick: flatter windows weigh far more, but no hard switch, so no square blocks.
            w = 1.0 / (1.0 + var / 25.0) ** 4
            total += mean * w[:, :, None]
            weight_sum += w
    return np.clip(total / weight_sum[:, :, None], 0, 255).astype(np.uint8)


def simplify(rgb: np.ndarray, strength: int = 2, method: str = "kuwahara") -> np.ndarray:
    """Fewer, flatter shapes. strength 1 (light) to 5 (heavy), scaled to the picture's size."""
    scale = max(rgb.shape[:2]) / 1024
    if method == "meanshift":
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        out = cv2.pyrMeanShiftFiltering(bgr, sp=int(8 * strength * scale), sr=12 + 6 * strength)
        return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
    out = rgb
    radius = max(2, int(round((2 + 2 * strength) * scale)))
    for _ in range(1 + strength // 2):  # repeated passes merge small patches into bigger ones
        out = kuwahara(out, radius)
    return out


def posterize(rgb: np.ndarray, colors: int = 6, palette_rgb: list[list[int]] | None = None) -> np.ndarray:
    """Every pixel snapped to one of a few colors: its own k-means colors, or the given palette's."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    if palette_rgb:
        pal = np.array(palette_rgb, np.uint8).reshape(-1, 1, 3)
        centers = cv2.cvtColor(pal, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
        labels = ((lab[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    else:
        labels, centers = _fit_assign(lab, colors)
    out_lab = centers[labels].reshape(rgb.shape).astype(np.uint8)
    return cv2.cvtColor(out_lab, cv2.COLOR_LAB2RGB)


def edges(rgb: np.ndarray, detail: str = "medium") -> np.ndarray:
    """A clean line drawing for tracing: dark lines on white, small texture dropped."""
    scale = max(rgb.shape[:2]) / 1024
    passes = {"low": 3, "medium": 2, "high": 1}[detail]
    smooth = rgb
    for _ in range(passes):  # flatten texture first so only shape edges remain
        smooth = kuwahara(smooth, max(2, int(4 * scale)))
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    med = float(np.median(gray))
    low, high = int(max(0, 0.66 * med)), int(min(255, 1.33 * med))
    e = cv2.Canny(gray, low, high, L2gradient=True)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(e, connectivity=8)
    min_len = {"low": 60, "medium": 35, "high": 15}[detail] * scale
    keep = np.zeros(n, bool)
    keep[1:] = np.maximum(stats[1:, cv2.CC_STAT_WIDTH], stats[1:, cv2.CC_STAT_HEIGHT]) >= min_len
    e = np.where(keep[labels], 255, 0).astype(np.uint8)
    e = cv2.dilate(e, np.ones((2, 2), np.uint8)) if scale >= 1 else e
    return gray3(255 - e)


def grid(rgb: np.ndarray, cells: int = 4) -> np.ndarray:
    """Square grid over the picture, `cells` squares along the longer side, for transferring the drawing."""
    out = rgb.copy()
    h, w = rgb.shape[:2]
    step = max(h, w) / cells
    thick = max(1, int(max(h, w) / 600))
    color = (40, 40, 40) if lightness(rgb).mean() > 110 else (230, 230, 230)
    x = step
    while x < w - 1:
        cv2.line(out, (int(x), 0), (int(x), h), color, thick)
        x += step
    y = step
    while y < h - 1:
        cv2.line(out, (0, int(y)), (w, int(y)), color, thick)
        y += step
    return out


def _variety(lines: np.ndarray) -> np.ndarray:
    """How many different colors each row of `lines` has (5 bits a channel). Photos and paintings have hundreds;
    app bars, buttons, and text on a flat background have a handful."""
    q = (lines >> 3).astype(np.int32)
    code = (q[..., 0] << 10) | (q[..., 1] << 5) | q[..., 2]
    return np.array([len(np.unique(r)) for r in code])


def _longest_run(mask: np.ndarray, gap: int) -> tuple[int, int]:
    """Start and end (exclusive) of the longest run of True, bridging gaps of up to `gap` False entries."""
    best, start, last = (0, 0), None, None
    for i, m in enumerate(mask):
        if not m:
            continue
        if start is None or i - last > gap + 1:
            start = i
        last = i
        if last + 1 - start > best[1] - best[0]:
            best = (start, last + 1)
    return best


def find_picture(rgb: np.ndarray, min_colors: int = 30) -> dict:
    """Find the picture inside a screenshot: the biggest block of colorful rows, then colorful columns within it.
    Returns the box in pixels, how much of the image it covers, and whether it's the whole image anyway."""
    h, w = rgb.shape[:2]
    y0, y1 = _longest_run(_variety(rgb) >= min_colors, gap=max(4, h // 200))
    band = rgb[y0:y1]
    x0, x1 = _longest_run(_variety(band.transpose(1, 0, 2)) >= min_colors, gap=max(4, w // 200))
    if y1 - y0 < h * 0.1 or x1 - x0 < w * 0.1:
        return {"box": [0, 0, w, h], "coverage": 1.0, "whole_image": True}
    coverage = round((x1 - x0) * (y1 - y0) / (w * h), 3)
    return {"box": [int(x0), int(y0), int(x1), int(y1)], "coverage": coverage, "whole_image": coverage > 0.92}


def crop(rgb: np.ndarray, box: list[int]) -> np.ndarray:
    x0, y0, x1, y1 = box
    return rgb[max(0, y0):y1, max(0, x0):x1].copy()
