"""Step pictures built from the finished painting, with no renders (Gesso #8).

    build(finish, steps) -> (one picture per step, the owner map)

Rendering each step on its own makes the picture drift between steps, and most of the skill's repair work (the
image review, lock-steps, the backward pass, tone seams) exists to undo that. Here every step is cut from the one
finished painting, so nothing can drift (owner, 2026-11-12: more tools, less inference).

1. Each pixel of the finish belongs to one step, its *owner*: among the steps whose regions (plan.json boxes)
   contain it, the one whose paints are closest in color. Later steps win close calls, since they're painted on top.
   A lavender field split into dark, mid, and light dab steps comes apart by value this way, the dark marks first.
2. Each step paints an *area*: its region, minus whatever earlier steps own. That's the back-to-front rule: the sky
   is painted straight through where the balloon will go, and the lavender rows go down flat where dabs come later.
3. Inside its area, a step shows the finish where it owns the pixel. Where a later step will paint over, it shows
   its own flat paint: the finish smoothed from the pixels it owns when it owns enough of its area, or else the
   finish's broad color snapped to the step's nearest paint (flat rows under the dabs).
4. Step N is the white canvas with the areas of steps 1 to N laid on in order. The last step is the finish.
"""

from __future__ import annotations

import cv2
import numpy as np

LATER_WINS = 3.0  # Lab units the last step's paint may be farther off than the first's and still own a pixel (it's on top)
CANVAS = (250, 249, 245)


def lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)


def hex_lab(h: str) -> np.ndarray:
    h = h.lstrip("#")
    rgb = np.array([[[int(h[i:i + 2], 16) for i in (0, 2, 4)]]], np.uint8)
    return lab(rgb)[0, 0]


def box_mask(shape: tuple[int, int], boxes: list) -> np.ndarray:
    h, w = shape
    if not boxes:
        return np.ones((h, w), bool)
    m = np.zeros((h, w), bool)
    for x0, y0, x1, y1 in boxes:
        m[int(round(y0 * h)):int(round(y1 * h)), int(round(x0 * w)):int(round(x1 * w))] = True
    return m


def new_colors(steps: list[dict]) -> list[list[str]]:
    """Each step's paints that no earlier step used. A later step that reuses a paint is touching up, so the pixels
    of that color belong to the step that brought it in (the lavender plan lists violet in both the mid and the
    light dab steps; the light step took every violet pixel and the mid step got none)."""
    seen: set[str] = set()
    out = []
    for s in steps:
        new = [c for c in s["colors"] if c not in seen]
        seen.update(s["colors"])
        out.append(new or s["colors"])
    return out


def owners(finish: np.ndarray, steps: list[dict]) -> np.ndarray:
    """steps: [{"regions": boxes, "colors": [hex, ...]}]. Returns the owning step's index for every pixel."""
    L = lab(cv2.GaussianBlur(finish, (0, 0), 1.2))
    h, w = L.shape[:2]
    dists, insides = [], []
    for k, (s, colors) in enumerate(zip(steps, new_colors(steps))):
        cols = [hex_lab(c) for c in colors] or [L.reshape(-1, 3).mean(0)]
        dists.append(np.min([np.sqrt(((L - c) ** 2).sum(2)) for c in cols], axis=0)
                     - LATER_WINS * k / max(len(steps) - 1, 1))
        insides.append(box_mask((h, w), s["regions"]))

    def pick(extra=None) -> np.ndarray:
        best = np.full((h, w), np.inf, np.float32)
        owner = np.full((h, w), -1, np.int32)
        anywhere = np.full((h, w), np.inf, np.float32)
        anywhere_owner = np.zeros((h, w), np.int32)
        for k, d in enumerate(dists):
            d = d - (extra[k] if extra is not None else 0)
            take = insides[k] & (d < best)
            best[take], owner[take] = d[take], k
            alt = d < anywhere
            anywhere[alt], anywhere_owner[alt] = d[alt], k
        owner[owner < 0] = anywhere_owner[owner < 0]  # in no step's region: the closest paint anywhere
        return owner

    # Color alone gives the sky stray lavender pixels that happen to match its blue. So a second pass also counts
    # how much of each step is nearby: a pixel among lavender goes to the lavender, unless its color says otherwise
    # by more than NEARBY. Steps over the same area (dab passes) are equally nearby, so color still splits them.
    owner = pick()
    sigma = 0.015 * max(h, w)
    same = [[j for j, t in enumerate(steps) if t["regions"] == s["regions"]] for s in steps]
    near = [cv2.GaussianBlur(np.isin(owner, same[k]).astype(np.float32), (0, 0), sigma) for k in range(len(steps))]
    owner = pick([NEARBY * n for n in near])
    split_passes(L[:, :, 0], owner, steps, insides)
    for k, s in enumerate(steps):  # a thing in its own small box (balloon, tree) is cut out whole, whatever its colors
        if is_object(s, (h, w)):
            cut = cut_out(finish, s["regions"][0]).astype(np.uint8)
            core = cut > 0
            ring = (cv2.dilate(cut, np.ones((9, 9), np.uint8)) > 0) & ~core  # its painted edge, so no rim is left
            # only where it looks enough like the object's paints, not like what's behind (GrabCut took a corner of
            # the mountains and the hill with the tree): loosely deep inside the cut-out, strictly at its edge
            current = np.take_along_axis(np.stack(dists), np.maximum(owner, 0)[None], 0)[0]
            take = (core & (dists[k] - OBJECT_CORE_MARGIN <= current)) | (ring & (dists[k] - OBJECT_MARGIN <= current))
            owner[take & box_mask((h, w), s["regions"]) & (owner < k)] = k
    return owner


NEARBY = 15.0  # Lab units a step's presence all around a pixel is worth when deciding who owns it
OBJECT_SHARE = 0.12
OBJECT_MARGIN = 10.0  # Lab units an object's paint may be farther off than the background's and still claim a pixel
OBJECT_CORE_MARGIN = 30.0  # the same, inside the cut-out (balloon stripes and outline match the sunset)
BRUSH = 0.7  # how much of the finish's brush texture shows through paint that goes on under later steps
BRUSH_MAX = 10.0  # the biggest brush mark carried over, in RGB levels


def split_passes(light: np.ndarray, owner: np.ndarray, steps: list[dict], insides: list[np.ndarray]) -> None:
    """Steps over the same area after its base coat are texture passes. Their marks go in by value, darkest first,
    in equal shares, instead of by which plan paint each mark happens to be nearest: the lavender plan named violet
    for two passes and one of them got no marks at all. A last step whose regions include the area (the finish's
    lightest tips) is the last pass."""
    done: set[int] = set()
    last = len(steps) - 1
    for k, s in enumerate(steps):
        group = [j for j, t in enumerate(steps) if t["regions"] == s["regions"]]
        if k in done or len(group) < 3:
            continue
        done.update(group)
        passes = group[1:]
        area = insides[k]
        if last not in group and all(b in steps[last]["regions"] for b in s["regions"]):
            passes.append(last)
        mine = area & np.isin(owner, group + [last])
        values = light[mine]
        if not values.size:
            continue
        cuts = np.quantile(values, [i / len(passes) for i in range(1, len(passes))])
        owner[mine] = np.array(passes)[np.searchsorted(cuts, values)]  # a step whose one box covers less of the canvas than this paints a thing, not an area


def is_object(step: dict, shape: tuple[int, int]) -> bool:
    return len(step["regions"]) == 1 and box_mask(shape, step["regions"]).mean() < OBJECT_SHARE


def cut_out(finish: np.ndarray, box: list[float]) -> np.ndarray:
    """The thing inside a box, apart from what's behind it (OpenCV GrabCut, seeded with the box). The balloon's red
    and gold stripes match the sunset, so color alone gave the sky half the balloon in the first step."""
    h, w = finish.shape[:2]
    x0, y0, x1, y1 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
    pad = max(4, int(0.02 * max(h, w)))
    X0, Y0, X1, Y1 = max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)
    crop = cv2.cvtColor(finish[Y0:Y1, X0:X1], cv2.COLOR_RGB2BGR)
    mask = np.zeros(crop.shape[:2], np.uint8)
    rect = (x0 - X0, y0 - Y0, max(1, x1 - x0), max(1, y1 - y0))
    try:
        cv2.grabCut(crop, mask, rect, np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64), 5,
                    cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        return box_mask((h, w), [box])
    fg = ((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    out = np.zeros((h, w), bool)
    out[Y0:Y1, X0:X1] = fg > 0
    return out


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


def row_paint(img: np.ndarray, src: np.ndarray) -> np.ndarray:
    """Each gap filled across its row, from the src paint on its left to the src paint on its right. Skies and
    fields run in horizontal bands, so the band carries on behind the balloon instead of blending to gray."""
    f = img.astype(np.float32)
    out = f.copy()
    xs = np.arange(img.shape[1])
    for y in range(img.shape[0]):
        ok = src[y]
        if ok.any() and not ok.all():
            for c in range(3):
                out[y, ~ok, c] = np.interp(xs[~ok], xs[ok], f[y, ok, c])
    return cv2.GaussianBlur(out, (0, 0), sigmaX=2, sigmaY=6)


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


BASE_SHARE = 0.15  # a step owning less of its region than this is a base coat: flat paint under what comes later
EDGE = 6  # pixels a step's paint runs past what it owns, under the next step's edge


def borrowed_marks(marks: np.ndarray, objects: np.ndarray, steps: list[dict], shape: tuple[int, int]) -> np.ndarray:
    """Brush marks for paint that goes on under an object, taken from right beside it: the object's own marks are
    its outline (a ghost), and no marks at all leaves a smooth patch that gives the object away."""
    h, w = shape
    out = marks.copy()
    for s in steps:
        if is_object(s, shape):
            x0, _, x1, _ = s["regions"][0]
            dx = max(1, int((x1 - x0) * w))
            beside = np.clip(np.roll(marks, dx if x0 * w >= dx else -dx, axis=1), -3 * BRUSH_MAX, 3 * BRUSH_MAX)
            box = box_mask(shape, s["regions"]) & objects
            out[box] = beside[box]
    return out


def build(finish: np.ndarray, steps: list[dict]) -> tuple[list[np.ndarray], np.ndarray]:
    owner = owners(finish, steps)
    h, w = owner.shape
    regions = [box_mask((h, w), s["regions"]) for s in steps]
    first = np.full((h, w), len(steps), np.int32)
    for k in reversed(range(len(steps))):
        first[regions[k]] = k
    first = np.minimum(first, owner)  # the first step to put paint on each pixel
    canvas = np.empty((h, w, 3), np.float32)
    canvas[:] = CANVAS
    objects = np.isin(owner, [k for k, s in enumerate(steps) if is_object(s, (h, w))])
    objects = cv2.dilate(objects.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * EDGE + 1, 2 * EDGE + 1))
    pictures = []
    for k, s in enumerate(steps):
        # the first of several steps over the same area (lavender rows, then dab passes) goes on as a flat coat, and
        # the marks it owned in the finish arrive with the first pass after it
        group = [j for j, t in enumerate(steps) if t["regions"] == s["regions"]]
        group_start = len(group) > 1 and group[0] == k
        if group_start:
            owner[(owner == k) & regions[group[1]]] = group[1]
        own = owner == k
        later = owner > k
        coat = group_start or own.sum() < BASE_SHARE * (regions[k] & (owner >= k)).sum()
        under = later & ((first == k) | (cv2.dilate(own.astype(np.uint8), kernel) > 0) | (coat & regions[k]))
        lay = finish.astype(np.float32).copy()
        if under.any():
            if coat or not own.any():
                fill = flat_paint(finish, regions[k] & (owner >= k), s["colors"])
            else:  # the step's own colors carried under, with the finish's brush marks so it reads as paint
                f = finish.astype(np.float32)
                # small marks only: big differences are the outlines of what comes later (they embossed a ghost)
                marks = f - cv2.GaussianBlur(f, (0, 0), 3)
                marks = np.where(objects[..., None], marks, np.clip(marks, -BRUSH_MAX, BRUSH_MAX))
                fill = continue_paint(finish, own)
                behind = objects[..., None]  # behind an object: the bands carried across, with real brush marks
                fill = fill * ~behind + row_paint(finish, own) * behind
                fill = fill + borrowed_marks(marks, objects, steps, (h, w)) * np.where(behind, 1.0, BRUSH)
            lay[under] = fill[under]
        area = own | under
        a = cv2.GaussianBlur(area.astype(np.float32), (0, 0), 0.8)[..., None]
        canvas = canvas * (1 - a) + lay * a
        pictures.append(np.clip(canvas, 0, 255).astype(np.uint8))
    pictures[-1] = finish.copy()
    return pictures, owner


def owner_preview(owner: np.ndarray, n: int) -> np.ndarray:
    rng = np.random.default_rng(3)
    pal = rng.integers(40, 230, (n, 3)).astype(np.uint8)
    return pal[owner]
