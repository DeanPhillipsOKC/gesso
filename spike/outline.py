"""A real outline for every part of the finished painting (pipeline v2, docs/design/pipeline-v2.md section 6).

    outline(finish, parts, sam=None) -> (masks, owner, stats)

A plan's boxes can't tell the sky's gold from the field's gold, which is why the from-finish spike couldn't cut the
sky steps from the finish (docs/spikes/from-finish.md). Here each part gets its exact shape, so every step picture
can be cut from the one finish and nothing drifts between steps.

Parts are listed back to front, the order they're painted. How a part's shape is found depends on its kind:

- "area", "object": the Segment Anything model (SAM, quantized ONNX, CPU) from the part's boxes. Clean on anything
  with a visible edge (docs/spikes/outline-probe.md). An area whose box is the whole picture is the backdrop: it
  takes every pixel nothing else claims, with no model.
- "marks": paint with no single edge, on top of another part: clouds, haze, foliage clumps, a sun path, a bird's
  black cap. A pixel is a mark when its color is nearer the part's `points_in` colors than its `points_out` colors.
- "thin": a branch, a mast, a rail. The marks rule, kept inside a band around the part's `paths`.

Every pixel then belongs to exactly one part: the latest (nearest the painter) that claims it.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
RELEASE = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"
FILES = {  # name -> SHA-256, so a changed download is refused instead of quietly giving different outlines
    "vit_b-encoder-quant.onnx": "cf99a3b79eea0ac4f7c9b06cdce5b2763ff41a3f631213c748d497cba233df6a",
    "vit_b-decoder-quant.onnx": "40b02c2f694bb87b8360bb04ad8aaa84eab9673f4092b4911e0513890812b42e",
}
BACKDROP_SHARE = 0.9  # an area whose boxes cover this much of the picture is the backdrop
SPECK = 0.0005  # pieces of a part smaller than this share of the picture go to whatever surrounds them
MARGIN = 0.0  # Lab units a marks pixel must be nearer its own colors than the colors behind it
SEED_WINDOW = 0.006  # half the side of the patch a point's color is read from, as a share of the long side
BAND = 1.6  # a thin part may reach this many times its stated width from its path


class NoModel(RuntimeError):
    pass


def lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)


def boxes_of(part: dict) -> list[list[float]]:
    return part.get("boxes") or ([part["box"]] if part.get("box") else [[0.0, 0.0, 1.0, 1.0]])


def box_mask(shape: tuple[int, int], boxes: list) -> np.ndarray:
    h, w = shape
    m = np.zeros((h, w), bool)
    for x0, y0, x1, y1 in boxes:
        m[int(round(y0 * h)):int(round(y1 * h)), int(round(x0 * w)):int(round(x1 * w))] = True
    return m


class Sam:
    """Segment Anything, ViT-B, quantized ONNX. `embed` once per picture (about 5 s on CPU), `mask` per box."""

    def __init__(self, folder: Path = MODELS):
        try:
            import onnxruntime as ort
        except ImportError as e:  # pragma: no cover
            raise NoModel("onnxruntime isn't installed: pip install -r spike/requirements.txt") from e
        paths = [fetch(name, folder) for name in FILES]
        # All cores: about 5 s a picture on 4 cores, against 24 s on one. The outlines came out the same, byte for
        # byte, on repeated runs on one machine (tests/test_outline.py checks it when the model files are present).
        self.enc = ort.InferenceSession(str(paths[0]), providers=["CPUExecutionProvider"])
        self.dec = ort.InferenceSession(str(paths[1]), providers=["CPUExecutionProvider"])
        self.emb = None

    def embed(self, rgb: np.ndarray) -> None:
        h, w = rgb.shape[:2]
        self.shape, self.scale = (h, w), 1024 / max(h, w)
        self.nh, self.nw = int(h * self.scale + 0.5), int(w * self.scale + 0.5)
        x = cv2.resize(rgb, (self.nw, self.nh), interpolation=cv2.INTER_LINEAR).astype(np.float32)
        x = (x - [123.675, 116.28, 103.53]) / [58.395, 57.12, 57.375]
        padded = np.zeros((1024, 1024, 3), np.float32)
        padded[:self.nh, :self.nw] = x
        self.emb = self.enc.run(None, {"x": padded.transpose(2, 0, 1)[None]})[0]

    def mask(self, box=None, points_in=(), points_out=()) -> tuple[np.ndarray, float]:
        """The outline for a box and/or points (all 0-1), and the model's own confidence (0-1)."""
        h, w = self.shape
        pts = [[x * w, y * h] for x, y in points_in] + [[x * w, y * h] for x, y in points_out]
        labels = [1.0] * len(points_in) + [0.0] * len(points_out)
        if box:
            pts += [[box[0] * w, box[1] * h], [box[2] * w, box[3] * h]]
            labels += [2.0, 3.0]
        else:
            pts.append([0.0, 0.0])
            labels.append(-1.0)
        _, iou, low = self.dec.run(None, {
            "image_embeddings": self.emb,
            "point_coords": (np.array(pts, np.float32) * self.scale)[None],
            "point_labels": np.array(labels, np.float32)[None],
            "mask_input": np.zeros((1, 1, 256, 256), np.float32),
            "has_mask_input": np.zeros(1, np.float32),
            "orig_im_size": np.array([h, w], np.float32)})
        # `low` covers the padded 1024 square at 256 x 256: enlarge, cut the padding off, then back to the picture.
        # The decoder's full-size output skips the padding step and comes back stretched for a non-square picture.
        up = cv2.resize(low[0, 0], (1024, 1024), interpolation=cv2.INTER_LINEAR)[:self.nh, :self.nw]
        return cv2.resize(up, (w, h), interpolation=cv2.INTER_LINEAR) > 0, float(iou.ravel()[0])


def fetch(name: str, folder: Path = MODELS) -> Path:
    path = folder / name
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        try:
            urllib.request.urlretrieve(RELEASE + name, tmp)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            raise NoModel(f"couldn't download {name} from {RELEASE} ({e}). Download it by hand into {folder}/.") from e
        tmp.rename(path)
    want = FILES[name]
    if want:
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != want:
            raise NoModel(f"{path} isn't the file this was tested with (SHA-256 {got[:12]}..., expected {want[:12]}...)")
    return path


def seed_colors(L: np.ndarray, points: list) -> np.ndarray:
    """The color at each point: the median of a small patch, so one brush mark doesn't decide it."""
    h, w = L.shape[:2]
    r = max(1, int(SEED_WINDOW * max(h, w)))
    out = []
    for x, y in points:
        cx, cy = min(w - 1, int(x * w)), min(h - 1, int(y * h))
        patch = L[max(0, cy - r):cy + r + 1, max(0, cx - r):cx + r + 1].reshape(-1, 3)
        out.append(np.median(patch, axis=0))
    return np.array(out, np.float32)


def nearest(L: np.ndarray, colors: np.ndarray) -> np.ndarray:
    """Each pixel's distance (Lab) to the nearest of the colors."""
    return np.min([np.sqrt(((L - c) ** 2).sum(2)) for c in colors], axis=0)


def hex_colors(hexes: list[str]) -> np.ndarray:
    rgb = np.array([[[int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)] for h in hexes]], np.uint8)
    return lab(rgb)[0]


def side_colors(L: np.ndarray, part: dict, side: str) -> np.ndarray:
    """One side's colors for the marks rule: read at its points, plus any given outright as hex. Hex colors are for
    when a point can't be trusted to land on the paint (a thin path, scattered sparkles): take them from the
    measured colors of the part behind (tools.py part-colors)."""
    cols = []
    if part.get(f"points_{side}"):
        cols.append(seed_colors(L, part[f"points_{side}"]))
    if part.get(f"colors_{side}"):
        cols.append(hex_colors(part[f"colors_{side}"]))
    if not cols:
        raise ValueError(f"{part['id']}: a {part['kind']} part needs points_{side} or colors_{side} "
                         f"({'on it' if side == 'in' else 'on what is behind it'})")
    return np.concatenate(cols)


def marks(L: np.ndarray, part: dict, inside: np.ndarray) -> np.ndarray:
    """Pixels inside `inside` whose color is nearer the part's own colors than the colors behind it."""
    mine = nearest(L, side_colors(L, part, "in"))
    theirs = nearest(L, side_colors(L, part, "out"))
    m = (mine + part.get("margin", MARGIN) < theirs) & inside
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    return cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, k) > 0


def band(shape: tuple[int, int], part: dict) -> np.ndarray:
    """Where a thin part may be: within BAND times its width of its paths."""
    h, w = shape
    m = np.zeros((h, w), np.uint8)
    paths = part.get("paths") or ([part["path"]] if part.get("path") else [])
    if not paths:
        raise ValueError(f"{part['id']}: a thin part needs paths (points along its middle)")
    thick = max(3, int(part.get("width", 0.05) * w * BAND))
    for path in paths:
        pts = np.array([[int(x * w), int(y * h)] for x, y in path], np.int32)
        cv2.polylines(m, [pts], False, 1, thick, cv2.LINE_AA)
    return m > 0


def drop_specks(owner: np.ndarray, floor: float = SPECK) -> np.ndarray:
    """Pieces of a part smaller than `floor` of the picture go to the part that surrounds them."""
    h, w = owner.shape
    small = max(4, int(floor * h * w))
    loose = np.zeros((h, w), bool)
    for k in np.unique(owner):
        n, lab_, stats, _ = cv2.connectedComponentsWithStats((owner == k).astype(np.uint8), connectivity=4)
        tiny = np.flatnonzero(stats[:, cv2.CC_STAT_AREA] < small)
        tiny = tiny[tiny != 0]
        if tiny.size:
            loose |= np.isin(lab_, tiny)
    return fill_from_nearest(owner, loose)


def fill_from_nearest(owner: np.ndarray, holes: np.ndarray) -> np.ndarray:
    """The `holes` pixels take the owner of the nearest pixel that isn't a hole."""
    if not holes.any() or holes.all():
        return owner
    _, idx = cv2.distanceTransformWithLabels(holes.astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(~holes)
    lut = np.zeros(idx.max() + 1, owner.dtype)
    lut[idx[ys, xs]] = owner[ys, xs]
    out = owner.copy()
    out[holes] = lut[idx[holes]]
    return out


def fill_along_rows(owner: np.ndarray, holes: np.ndarray) -> np.ndarray:
    """The `holes` pixels take the owner of the nearest pixel in their own row that isn't a hole, so an edge that
    runs across the picture (a horizon, a shoreline) carries straight on behind an object instead of bulging
    around it. Rows that are all hole fall back to the nearest pixel anywhere."""
    h, w = owner.shape
    out = owner.copy()
    xs = np.arange(w)
    left_over = np.zeros((h, w), bool)
    for y in np.flatnonzero(holes.any(1)):
        ok = ~holes[y]
        if not ok.any():
            left_over[y] = True
            continue
        good = xs[ok]
        pos = np.clip(np.searchsorted(good, xs), 0, len(good) - 1)
        prev = np.clip(pos - 1, 0, len(good) - 1)
        pick = np.where(np.abs(good[pos] - xs) <= np.abs(good[prev] - xs), good[pos], good[prev])
        out[y, holes[y]] = owner[y, pick[holes[y]]]
    return fill_from_nearest(out, left_over)


def order_check(parts: list[dict]) -> None:
    seen: set[str] = set()
    for p in parts:
        if p.get("parent") and p["parent"] not in seen:
            raise ValueError(f"{p['id']}: its parent {p['parent']} must come earlier in parts")
        seen.add(p["id"])


def outline(finish: np.ndarray, parts: list[dict], sam: Sam | None = None,
            given: dict[str, np.ndarray] | None = None) -> tuple[dict[str, np.ndarray], np.ndarray, list[dict]]:
    """finish: RGB. parts: plan.json's parts, back to front. given: ready-made SAM outlines by part id (tests).

    Returns each part's outline (the pixels it owns), the owner map (the part's index for every pixel), and one
    row of numbers per part for the checks.
    """
    order_check(parts)
    h, w = finish.shape[:2]
    L = lab(cv2.GaussianBlur(finish, (0, 0), 1.2))
    index = {p["id"]: i for i, p in enumerate(parts)}
    owner = np.full((h, w), -1, np.int32)
    stats = []
    for k, p in enumerate(parts):
        boxes = boxes_of(p)
        inbox = box_mask((h, w), boxes)
        row = {"id": p["id"], "kind": p["kind"], "confidence": None}
        if p["kind"] in ("area", "object"):
            if p["kind"] == "area" and inbox.mean() >= BACKDROP_SHARE and not p.get("parent"):
                claim = np.ones((h, w), bool)  # the backdrop: whatever nothing in front of it claims
            elif given is not None and p["id"] in given:
                claim = given[p["id"]]
            else:
                if sam is None:
                    raise NoModel(f"{p['id']}: no outline model loaded and no ready-made outline given")
                if sam.emb is None:
                    sam.embed(finish)
                claim, conf = np.zeros((h, w), bool), []
                for i, box in enumerate(boxes):
                    solo = len(boxes) == 1  # points only make sense for a part that is one thing
                    one, c = sam.mask(box, (p.get("points_in") or ()) if solo else (),
                                      (p.get("points_out") or ()) if solo else ())
                    claim |= one & box_mask((h, w), [grow(box, 0.02)])
                    conf.append(c)
                row["confidence"] = round(min(conf), 3)
        elif p["kind"] in ("marks", "thin"):
            inside = inbox if p["kind"] == "marks" else band((h, w), p)
            if p.get("parent"):  # marks on a part stay on that part (and on its other children)
                family = [index[p["parent"]]] + [index[q["id"]] for q in parts[:k] if q.get("parent") == p["parent"]]
                inside = inside & np.isin(owner, family)
            claim = marks(L, p, inside)
        else:
            raise ValueError(f"{p['id']}: unknown kind {p['kind']!r}")
        if p.get("parent") and p["kind"] in ("area", "object"):
            claim = claim & inbox
        owner[claim] = k
        row["claimed"] = round(float(claim.mean()), 4)
        stats.append(row)
    owner = fill_from_nearest(owner, owner < 0)
    owner = drop_specks(owner)
    masks = {}
    for k, p in enumerate(parts):
        m = owner == k
        masks[p["id"]] = m
        n, _, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
        big = int((st[1:, cv2.CC_STAT_AREA] >= max(4, SPECK * h * w * 4)).sum()) if n > 1 else 0
        inbox = box_mask((h, w), boxes_of(p))
        stats[k].update(share=round(float(m.mean()), 4), pieces=big,
                        box_fill=round(float((m & inbox).sum() / max(inbox.sum(), 1)), 3))
    return masks, owner, stats


def grow(box: list[float], by: float) -> list[float]:
    return [max(0.0, box[0] - by), max(0.0, box[1] - by), min(1.0, box[2] + by), min(1.0, box[3] + by)]


def problems(parts: list[dict], stats: list[dict]) -> list[str]:
    """What's wrong with the outlines, each with what to change. Empty when they're fine."""
    out = []
    for p, s in zip(parts, stats):
        n_boxes = len(boxes_of(p))
        if s["share"] == 0:
            out.append(f"{p['id']}: nothing was outlined. Check its box and points against the picture.")
            continue
        if s["confidence"] is not None and s["confidence"] < 0.80:
            out.append(f"{p['id']}: the outline model is unsure (confidence {s['confidence']}). Tighten the box, or add "
                       "points_in / points_out.")
        if p["kind"] == "object":
            if s["box_fill"] < 0.15:
                out.append(f"{p['id']}: fills only {s['box_fill']:.0%} of its box. The box is too loose, or it missed.")
            if s["box_fill"] > 0.98 and not p.get("parent"):
                out.append(f"{p['id']}: fills its whole box, so it probably took the background. Loosen the box.")
            if s["pieces"] > 3 * n_boxes:
                out.append(f"{p['id']}: came back in {s['pieces']} pieces. Use one box per thing, or make it marks.")
    return out


TINTS = [(230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180), (70, 240, 240),
         (240, 50, 230), (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255), (170, 110, 40),
         (128, 0, 0), (170, 255, 195), (128, 128, 0), (0, 0, 128)]


def preview(finish: np.ndarray, parts: list[dict], owner: np.ndarray) -> np.ndarray:
    """The finish with every part tinted, edged in white, and labeled, to check the outlines by eye."""
    out = finish.astype(np.float32)
    for k in range(len(parts)):
        m = owner == k
        out[m] = out[m] * 0.5 + np.array(TINTS[k % len(TINTS)], np.float32) * 0.5
    edges = np.zeros(owner.shape, bool)
    edges[:, 1:] |= owner[:, 1:] != owner[:, :-1]
    edges[1:, :] |= owner[1:, :] != owner[:-1, :]
    out[cv2.dilate(edges.astype(np.uint8), np.ones((2, 2), np.uint8)) > 0] = 255
    out = np.ascontiguousarray(out.astype(np.uint8))
    scale = max(owner.shape) / 1000
    for k, p in enumerate(parts):
        m = (owner == k).astype(np.uint8)
        if not m.any():
            continue
        dist = cv2.distanceTransform(m, cv2.DIST_L2, 3)  # label the part at its fattest point
        y, x = np.unravel_index(int(dist.argmax()), dist.shape)
        text = f"{k + 1} {p['id']}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45 * scale, max(1, int(scale)))
        x = int(min(max(2, x - tw // 2), owner.shape[1] - tw - 2))
        y = int(min(max(th + 2, y), owner.shape[0] - 2))
        cv2.putText(out, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45 * scale, (0, 0, 0), max(3, int(3 * scale)), cv2.LINE_AA)
        cv2.putText(out, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45 * scale, (255, 255, 255), max(1, int(scale)), cv2.LINE_AA)
    return out
