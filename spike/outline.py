"""A real outline for every part of the finished painting (pipeline v2, docs/design/pipeline-v2.md section 6).

    outline(finish, parts, sam=None) -> (masks, owner, stats)

A plan's boxes can't tell the sky's gold from the field's gold, which is why the from-finish spike couldn't cut the
sky steps from the finish (docs/spikes/from-finish.md). Here each part gets its exact shape, so every step picture
can be cut from the one finish and nothing drifts between steps.

Parts are listed back to front, the order they're painted. How a part's shape is found depends on its kind:

- "area", "object": the Segment Anything model (SAM ViT-B, quantized ONNX, CPU) from the part's boxes. Clean on anything
  with a visible edge (docs/spikes/outline-probe.md). An area whose box is the whole picture is the backdrop: it
  takes every pixel nothing else claims, with no model.
- "marks": paint with no single edge, on top of another part: clouds, haze, foliage clumps, a sun path, a bird's
  black cap. A pixel is a mark when its color is nearer the part's `points_in` colors than its `points_out` colors.
- "thin": a branch, a mast, a rail. A larger model (SAM-HQ ViT-L), asked with one box around the part's paths and the plan's
  points, then limb by limb for any path that answer misses, all kept inside a band around the paths
  (docs/spikes/outline-models.md, #129). The marks rule when the model finds nothing there.

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
# Two outline models, each pinned by SHA-256 so a changed download is refused instead of quietly giving different
# outlines. SAM ViT-B (rembg's export, 108 MB) outlines areas and objects. SAM-HQ ViT-L (X-AnyLabeling's export, the
# encoder quantized, 345 MB) outlines thin parts, and is loaded only for a plan that has one (#129). The spike for #85
# found SAM-HQ ViT-L the one model that returned the chickadee's branch whole from one box
# (docs/spikes/outline-models.md); swapped in for every part, it dropped the lavender fixture's hedge rows from the
# fields under them, which ViT-B keeps, so areas and objects stay on ViT-B.
VIT_B, HQ_L = "vit-b", "hq-l"
MODEL_FILES = {  # model -> (release, {file: SHA-256}): the encoder first
    VIT_B: ("https://github.com/danielgatis/rembg/releases/download/v0.0.0/", {
        "vit_b-encoder-quant.onnx": "cf99a3b79eea0ac4f7c9b06cdce5b2763ff41a3f631213c748d497cba233df6a",
        "vit_b-decoder-quant.onnx": "40b02c2f694bb87b8360bb04ad8aaa84eab9673f4092b4911e0513890812b42e"}),
    HQ_L: ("https://github.com/CVHub520/X-AnyLabeling/releases/download/v2.0.0/", {
        "sam_hq_vit_l_encoder_quant.onnx": "ffcdd1134e4078b30649a976a4ded694ffb13600bd390b8ac84f363e8d4591d8",
        "sam_hq_vit_l_decoder.onnx": "77a3697b68d5ce4ae9a76218cff7cbc73aab5f8b01ea570ef8eb6b4380f3e1ac"}),
}
FILES = {name: sha for _, files in MODEL_FILES.values() for name, sha in files.items()}
RELEASES = {name: release for release, files in MODEL_FILES.values() for name in files}
BACKDROP_SHARE = 0.9  # an area whose boxes cover this much of the picture is the backdrop
SPECK = 0.0005  # pieces of a part smaller than this share of the picture go to whatever surrounds them
MARGIN = 0.0  # Lab units a marks pixel must be nearer its own colors than the colors behind it
SEED_WINDOW = 0.006  # half the side of the patch a point's color is read from, as a share of the long side
BAND = 1.6  # a thin part may reach this many times its stated width from its path
HOLE = 0.03  # an area enclosing more than this share of the picture that went to a part behind it is told
HOLE_BRIDGE = 0.02  # gaps in an area's outline narrower than about twice this (of the long side) count as closed


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
    """A Segment Anything model, quantized ONNX, on CPU: SAM ViT-B (the default, for areas and objects) or SAM-HQ
    ViT-L (`Sam(HQ_L)`, for thin parts). The files are fetched and loaded on the first `embed`, so a model a plan
    doesn't need costs nothing. `embed` once per picture (ViT-B about 4 s on 4 cores, SAM-HQ ViT-L about 8 s), `mask`
    per prompt (a box and/or points)."""

    def __init__(self, model: str = VIT_B, folder: Path = MODELS):
        try:
            import onnxruntime  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise NoModel("onnxruntime isn't installed: pip install -r spike/requirements.txt") from e
        self.model, self.folder = model, folder
        self.enc = self.dec = self.emb = None

    def load(self) -> None:
        import onnxruntime as ort
        paths = [fetch(name, self.folder) for name in MODEL_FILES[self.model][1]]
        # All cores. The outlines came out the same, byte for byte, on repeated runs on one machine
        # (docs/spikes/outlines.md for ViT-B, docs/spikes/outline-models.md for SAM-HQ ViT-L).
        self.enc = ort.InferenceSession(str(paths[0]), providers=["CPUExecutionProvider"])
        self.dec = ort.InferenceSession(str(paths[1]), providers=["CPUExecutionProvider"])

    def embed(self, rgb: np.ndarray) -> None:
        if self.enc is None:
            self.load()
        h, w = rgb.shape[:2]
        self.shape, self.scale = (h, w), 1024 / max(h, w)
        self.nh, self.nw = int(h * self.scale + 0.5), int(w * self.scale + 0.5)
        x = cv2.resize(rgb, (self.nw, self.nh), interpolation=cv2.INTER_LINEAR).astype(np.float32)
        if self.model == VIT_B:  # rembg's export: normalized and padded here
            x = (x - [123.675, 116.28, 103.53]) / [58.395, 57.12, 57.375]
            padded = np.zeros((1024, 1024, 3), np.float32)
            padded[:self.nh, :self.nw] = x
            self.emb, self.interm = self.enc.run(None, {"x": padded.transpose(2, 0, 1)[None]})[0], None
        else:  # X-AnyLabeling's export normalizes and pads inside, and also gives the encoder's four middle layers,
            out = self.enc.run(None, {"input_image": x})  # which SAM-HQ's decoder uses to keep thin things
            self.emb, self.interm = out[0], np.stack(out[1:], axis=0)

    def logits(self, box=None, points_in=(), points_out=()) -> tuple[np.ndarray, float]:
        """The model's answer for a box and/or points (all 0-1) at the picture's size (above 0 is the part), and its
        own confidence (0-1)."""
        h, w = self.shape
        pts = [[x * w, y * h] for x, y in points_in] + [[x * w, y * h] for x, y in points_out]
        labels = [1.0] * len(points_in) + [0.0] * len(points_out)
        if box:
            pts += [[box[0] * w, box[1] * h], [box[2] * w, box[3] * h]]
            labels += [2.0, 3.0]
        else:
            pts.append([0.0, 0.0])
            labels.append(-1.0)
        feed = {"image_embeddings": self.emb,
                "point_coords": (np.array(pts, np.float32) * self.scale)[None],
                "point_labels": np.array(labels, np.float32)[None],
                "mask_input": np.zeros((1, 1, 256, 256), np.float32),
                "has_mask_input": np.zeros(1, np.float32),
                "orig_im_size": np.array([h, w], np.float32)}
        if self.interm is not None:
            feed["interm_embeddings"] = self.interm
        _, iou, low = self.dec.run(None, feed)
        # `low` covers the padded 1024 square at 256 x 256: enlarge, cut the padding off, then back to the picture.
        # The decoder's full-size output skips the padding step and comes back stretched for a non-square picture.
        up = cv2.resize(low[0, 0], (1024, 1024), interpolation=cv2.INTER_LINEAR)[:self.nh, :self.nw]
        return cv2.resize(up, (w, h), interpolation=cv2.INTER_LINEAR), float(iou.ravel()[0])

    def mask(self, box=None, points_in=(), points_out=()) -> tuple[np.ndarray, float]:
        """The outline for a box and/or points (all 0-1), and the model's own confidence (0-1)."""
        lg, conf = self.logits(box, points_in, points_out)
        return lg > 0, conf


def fetch(name: str, folder: Path = MODELS) -> Path:
    path = folder / name
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        try:
            urllib.request.urlretrieve(RELEASES[name] + name, tmp)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            raise NoModel(f"couldn't download {name} from {RELEASES[name]} ({e}). Download it by hand into {folder}/.") from e
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
    paths = paths_of(part)
    if not paths:
        raise ValueError(f"{part['id']}: a thin part needs paths (points along its middle)")
    thick = max(3, int(part.get("width", 0.05) * w * BAND))
    for path in paths:
        pts = np.array([[int(x * w), int(y * h)] for x, y in path], np.int32)
        cv2.polylines(m, [pts], False, 1, thick, cv2.LINE_AA)
    return m > 0


def paths_of(part: dict) -> list:
    return part.get("paths") or ([part["path"]] if part.get("path") else [])


def paths_box(paths: list, margin: float) -> list[float]:
    """A box around paths (0-1), grown by `margin` on every side."""
    pts = np.array([q for path in paths for q in path], float)
    return [float(max(0.0, pts[:, 0].min() - margin)), float(max(0.0, pts[:, 1].min() - margin)),
            float(min(1.0, pts[:, 0].max() + margin)), float(min(1.0, pts[:, 1].max() + margin))]


def along(path: list, step: float) -> list[list[float]]:
    """Points along a path (0-1), about `step` apart, both ends included."""
    p = np.array(path, float)
    if len(p) == 1:
        return [list(map(float, p[0]))]
    seg = np.sqrt((np.diff(p, axis=0) ** 2).sum(1))
    ends = np.cumsum(seg)
    out = []
    for d in np.linspace(0, float(ends[-1]), max(2, int(ends[-1] / step) + 1)):
        i = int(min(np.searchsorted(ends, d), len(seg) - 1))
        t = (d - (ends[i] - seg[i])) / max(seg[i], 1e-9)
        out.append([float(v) for v in p[i] + (p[i + 1] - p[i]) * min(max(t, 0.0), 1.0)])
    return out


def inside_box(points: list, box: list[float]) -> list:
    return [q for q in points if box[0] <= q[0] <= box[2] and box[1] <= q[1] <= box[3]]


def drop_small(mask: np.ndarray, floor: float = SPECK) -> np.ndarray:
    """A mask with its pieces under `floor` of the picture taken out."""
    n, lab_, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.flatnonzero(st[:, cv2.CC_STAT_AREA] >= max(4, floor * mask.size))
    keep = keep[keep != 0]
    return np.isin(lab_, keep) if keep.size else np.zeros_like(mask, bool)


def covered(mask: np.ndarray, path: list, width: float) -> float:
    """How much of a path the mask has: the share of points along it with some of the mask within half the part's
    width."""
    h, w = mask.shape
    r = max(1, int(width * w / 2))
    pts = along(path, max(width, 0.005))
    hit = 0
    for x, y in pts:
        cx, cy = min(w - 1, int(x * w)), min(h - 1, int(y * h))
        hit += bool(mask[max(0, cy - r):cy + r + 1, max(0, cx - r):cx + r + 1].any())
    return hit / len(pts)


THIN_STEP = 0.03  # points along a limb for its own prompt, this share of the picture apart
LIMB_COVERED = 0.8  # a path whose points the one-box answer has fewer of than this is asked for on its own


def thin(sam: "Sam", L: np.ndarray, part: dict, inside: np.ndarray) -> tuple[np.ndarray, dict]:
    """A thin part from the outline model, kept inside `inside` (its band, and its parent's family).

    First one prompt: a box around all the part's paths (grown by its width) with its points_in and the points_out
    inside that box. That gives a branch's body clean, with no stray background, but can lose a thin limb (twigs on
    the chickadee fixture, a sailboat's boom). So then each path that answer covers less than LIMB_COVERED of is
    asked for on its own (a box around that path, points along it, the points_out in its box), kept inside that
    path's own band and to pixels whose color is nearer the part's than what's behind it: asked limb by limb, the
    model took a wedge of foliage where three paths ran close together (spike for #85). Pieces under SPECK go.
    A part with colors_in but no points_in is asked with points along its paths instead. Returns the outline and
    what was done, for stats.json."""
    h, w = L.shape[:2]
    paths, width = paths_of(part), part.get("width", 0.05)
    pin = list(part.get("points_in") or ()) or [q for path in paths for q in along(path, THIN_STEP)]
    pout = part.get("points_out") or []
    box = paths_box(paths, width)
    one, conf = sam.mask(box, pin, inside_box(pout, box))
    claim = drop_small(one & inside)
    limbs, colors = [], None
    for i, path in enumerate(paths):
        if covered(claim, path, width) >= LIMB_COVERED:
            continue
        if colors is None:  # the color rule, as a veto on what a limb's answer adds
            colors = marks(L, part, inside)
        b = paths_box([path], width)
        lone, c = sam.mask(b, along(path, THIN_STEP), inside_box(pout, b))
        claim |= lone & band((h, w), {**part, "paths": [path]}) & inside & colors
        limbs.append(i)
    claim = drop_small(claim)
    return claim, {"confidence": round(conf, 3), "limbs": limbs}


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


ISLAND = 0.02  # a stray piece of an area smaller than this share of the picture, inside another part, joins that part
ISLAND_INSIDE = 0.6  # how much of the piece's edge must be against that one other part


def drop_islands(owner: np.ndarray, parts: list[dict]) -> np.ndarray:
    """A small piece of an area (with whatever is painted on it) that sits apart from the area's main body, mostly
    inside one other area, goes to that area. Pixels nothing claimed fall to the backdrop, so bits of soil between
    lavender rows became "sky", the sky's clouds then took them by color, and the sky's first step painted them
    on bare canvas for eleven steps (2026-11-13). An area's family is the area and everything with it as its
    root; marks and objects with no area under them are left alone: several separate pieces is what they are."""
    h, w = owner.shape
    out = owner.copy()
    small = ISLAND * h * w
    ring = np.ones((5, 5), np.uint8)
    index = {p["id"]: i for i, p in enumerate(parts)}
    root = []
    for i, p in enumerate(parts):
        while p.get("parent") in index:
            i = index[p["parent"]]
            p = parts[i]
        root.append(i)
    root = np.array(root)
    is_area = np.array([parts[r]["kind"] == "area" for r in root])
    for k, p in enumerate(parts):
        if p["kind"] != "area" or p.get("parent"):
            continue
        family = root[out] == k
        n, lab_, stats, _ = cv2.connectedComponentsWithStats(family.astype(np.uint8), connectivity=8)
        if n <= 2:
            continue
        main = 1 + int(stats[1:, cv2.CC_STAT_AREA].argmax())
        for i in range(1, n):
            if i == main or stats[i, cv2.CC_STAT_AREA] >= small:
                continue
            piece = lab_ == i
            edge = (cv2.dilate(piece.astype(np.uint8), ring) > 0) & ~piece
            # only into another area: a gap of sky between twigs or under a bird's tail is still sky, and the
            # branch must not take it. The area's own marks count with it (soil paths on a field).
            around = root[out[edge]]
            around = around[(around != k) & is_area[around]]
            if not around.size:
                continue
            ids, counts = np.unique(around, return_counts=True)
            if counts.max() >= ISLAND_INSIDE * edge.sum():
                out[piece] = ids[counts.argmax()]
    return out


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
            given: dict[str, np.ndarray] | None = None, thin_sam: Sam | None = None) -> tuple[dict[str, np.ndarray], np.ndarray, list[dict]]:
    """finish: RGB. parts: plan.json's parts, back to front. sam: the model for areas and objects (ViT-B); thin_sam:
    the one for thin parts (SAM-HQ ViT-L). given: ready-made outlines by part id (tests).

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
            claim = None
            if p["kind"] == "thin":
                if given is not None and p["id"] in given:
                    claim, row["how"] = given[p["id"]] & inside, "given"
                elif thin_sam is not None:
                    if thin_sam.emb is None:
                        thin_sam.embed(finish)
                    claim, got = thin(thin_sam, L, p, inside)
                    row.update(got)
                    row["how"] = "model" + (" and limbs" if got["limbs"] else "")
                    if not claim.any():  # the model found nothing in the band: the color rule, as before
                        claim, row["how"], row["confidence"] = None, "color rule (the model found nothing)", None
                else:
                    raise NoModel(f"{p['id']}: no thin-part outline model loaded and no ready-made outline given")
            if claim is None:
                claim = marks(L, p, inside)
        else:
            raise ValueError(f"{p['id']}: unknown kind {p['kind']!r}")
        if p.get("parent") and p["kind"] in ("area", "object"):
            claim = claim & inbox
        owner[claim] = k
        row["claimed"] = round(float(claim.mean()), 4)
        stats.append(row)
    owner = fill_from_nearest(owner, owner < 0)
    owner = drop_islands(drop_specks(owner), parts)
    masks = {p["id"]: owner == k for k, p in enumerate(parts)}
    for row, measured in zip(stats, owner_stats(parts, owner)):
        row.update(measured)
    return masks, owner, stats


def owner_stats(parts: list[dict], owner: np.ndarray) -> list[dict]:
    """What the outline checks measure on the final outlines: each part's share of the picture, its pieces, and how
    much of its box it fills. `check` uses it for a lesson with parts/owner.png but no parts/stats.json."""
    h, w = owner.shape
    out = []
    for k, p in enumerate(parts):
        m = owner == k
        n, _, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
        big = int((st[1:, cv2.CC_STAT_AREA] >= max(4, SPECK * h * w * 4)).sum()) if n > 1 else 0
        inbox = box_mask((h, w), boxes_of(p))
        row = {"share": round(float(m.mean()), 4), "pieces": big,
               "box_fill": round(float((m & inbox).sum() / max(inbox.sum(), 1)), 3)}
        if p.get("kind") == "area":
            row.update(hole(parts, owner, k, inbox))
        out.append(row)
    return out


def hole(parts: list[dict], owner: np.ndarray, k: int, inbox: np.ndarray) -> dict:
    """What of an area's box lies inside its filled outline but went to an earlier area or object (behind it): earth
    paths between lavender rows that went to the sky (2026-11-13). The box's sides on the picture's edge count as the
    area's own, so a gap that runs out to the edge is still enclosed. Returns {"hole", "hole_from", "hole_at"}:
    its share of the picture, the earlier part owning most of it, and a spot (0-1) in its biggest piece."""
    h, w = owner.shape
    family = {parts[k]["id"]}  # the area and everything painted on it (the lavender's blooms)
    for p in parts[k + 1:]:
        if p.get("parent") in family:
            family.add(p["id"])
    m = np.isin(owner, [j for j, p in enumerate(parts) if p["id"] in family]).astype(np.uint8)
    x0, y0, x1, y1 = (int(round(v)) for v in (inbox.any(0).argmax(), inbox.any(1).argmax(),
                                              w - inbox.any(0)[::-1].argmax(), h - inbox.any(1)[::-1].argmax()))
    pad = np.pad(m, 1)
    rows, cols = slice(y0 + 1, y1 + 1), slice(x0 + 1, x1 + 1)  # the box's span, in the padded picture
    for side, on_edge in (((rows, 0), x0 == 0), ((rows, -1), x1 == w), ((0, cols), y0 == 0), ((-1, cols), y1 == h)):
        if on_edge:
            pad[side] = 1
    r = max(1, int(HOLE_BRIDGE * max(h, w)))  # paths that run out to the area's far edge are closed off there
    pad = cv2.morphologyEx(pad, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    filled = pad.copy()
    contours, _ = cv2.findContours(pad, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(filled, contours, -1, 1, cv2.FILLED)
    # only what fell to an area or object behind (the backdrop takes whatever nobody claimed); a marks or thin part
    # listed before this area took its pixels by its own colors, on purpose
    fell = np.isin(owner, [j for j in range(k) if parts[j].get("kind") in ("area", "object")])
    gap = (filled[1:-1, 1:-1] > 0) & (m == 0) & inbox & fell
    if not gap.any():
        return {"hole": 0.0}
    behind = np.bincount(owner[gap], minlength=len(parts))
    n, lab_, st, _ = cv2.connectedComponentsWithStats(gap.astype(np.uint8), connectivity=8)
    biggest = 1 + int(st[1:, cv2.CC_STAT_AREA].argmax())
    dist = cv2.distanceTransform(np.pad((lab_ == biggest).astype(np.uint8), 1), cv2.DIST_L2, 3)[1:-1, 1:-1]
    y, x = np.unravel_index(int(dist.argmax()), dist.shape)  # its fattest point, away from the picture's edge
    return {"hole": round(float(gap.mean()), 4), "hole_from": parts[int(behind.argmax())]["id"],
            "hole_at": [round(float(x / w), 3), round(float(y / h), 3)]}


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
        if s["confidence"] is not None and s["confidence"] < 0.80 and p["kind"] == "thin":
            out.append(f"{p['id']}: the outline model is unsure of this thin part (confidence {s['confidence']}). "
                       "Give it points_in on the part and points_out right beside it, and a path along every limb.")
        elif s["confidence"] is not None and s["confidence"] < 0.80:
            out.append(f"{p['id']}: the outline model is unsure (confidence {s['confidence']}). Tighten the box, or add "
                       "points_in / points_out.")
        if p["kind"] == "object":
            if s["box_fill"] < 0.15:
                out.append(f"{p['id']}: fills only {s['box_fill']:.0%} of its box. The box is too loose, or it missed.")
            if s["box_fill"] > 0.98 and not p.get("parent"):
                out.append(f"{p['id']}: fills its whole box, so it probably took the background. Loosen the box.")
            if s["pieces"] > 3 * n_boxes:
                out.append(f"{p['id']}: came back in {s['pieces']} pieces. Use one box per thing, or make it marks.")
        if p["kind"] == "area" and (s.get("hole") or 0) > HOLE:
            x, y = s["hole_at"]
            out.append(f"{p['id']}: {s['hole']:.0%} of the picture inside its outline went to {s['hole_from']}, which "
                       f"is behind it (around x {x}, y {y}). If that's {p['id']}, add points_in there; if it's "
                       f"something on {p['id']}, make it a marks part with parent {p['id']}.")
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
