"""Spike #52: can tools do the busy check, the beginner version, and the painting order?

Experiment code, not a lesson tool. Run from the repo root:
    python spike/experiments/issue52.py busy    <picture> [<picture> ...]
    python spike/experiments/issue52.py beginner <picture> --out <folder>
    python spike/experiments/issue52.py order   <lesson folder or plan.json:owner.png> [...]
The write-up is docs/spikes/tools-before-plan.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import filters  # noqa: E402

WORK = 1000  # every measure is taken at this long side, so pictures of different sizes compare


def load(path: Path, canvas_box: list[float] | None = None) -> np.ndarray:
    rgb = filters.load(path)
    if canvas_box:
        h, w = rgb.shape[:2]
        x0, y0, x1, y1 = canvas_box
        rgb = rgb[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    s = WORK / max(rgb.shape[:2])
    return cv2.resize(rgb, (round(rgb.shape[1] * s), round(rgb.shape[0] * s)), interpolation=cv2.INTER_AREA)


def canvas_box_for(path: Path) -> list[float] | None:
    """A lesson's pictures are in the image model's frame; measure only the canvas inside it."""
    cj = path.parent / "canvas.json"
    if cj.exists() and path.name != "photo_cropped.png":
        return json.loads(cj.read_text()).get("canvas_box")
    return None


# ---------------------------------------------------------------------------
# 1. Busy check
# ---------------------------------------------------------------------------


def shapes(rgb: np.ndarray, colors: int = 12) -> tuple[np.ndarray, np.ndarray]:
    """The picture as separate shapes: smoothed (brush texture gone), snapped to a few colors, then every
    connected patch of one color is a shape. Returns (label map, area of each shape as a share of the picture)."""
    smooth = filters.simplify(rgb, strength=2, method="meanshift")
    lab = cv2.cvtColor(smooth, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    labels, _ = filters._fit_assign(lab, colors)
    labels = labels.reshape(rgb.shape[:2])
    out = np.zeros(labels.shape, np.int32)
    n = 0
    for c in range(colors):
        k, comp = cv2.connectedComponents((labels == c).astype(np.uint8), connectivity=8)
        comp[comp > 0] += n
        out += comp
        n += k - 1
    areas = np.bincount(out.ravel(), minlength=n + 1)[1:] / out.size
    return out, areas


SPECK, SMALL = 0.0002, 0.005  # shares of the picture: under 0.02% is a speck, up to 0.5% is a small shape


def busy(rgb: np.ndarray) -> dict:
    gray = cv2.GaussianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (0, 0), 1.5)
    edge = cv2.Canny(gray, 40, 120) > 0
    # Share of the picture that is fine texture: 40 px tiles where more than 1 pixel in 8 is an edge.
    t = 40
    h, w = edge.shape
    tiles = edge[:h // t * t, :w // t * t].reshape(h // t, t, w // t, t).mean(axis=(1, 3))
    _, areas = shapes(rgb)
    small = (areas >= SPECK) & (areas < SMALL)
    return {
        "edge_density": round(float(edge.mean()), 4),
        "textured_share": round(float((tiles > 0.125).mean()), 3),
        "small_shapes": int(small.sum()),
        "specks": int((areas < SPECK).sum()),
        "small_share": round(float(areas[areas < SMALL].sum()), 3),
        "big_shapes": int((areas >= 0.02).sum()),
    }


def cmd_busy(args) -> None:
    for p in args.pictures:
        p = Path(p)
        print(json.dumps({"picture": str(p), **busy(load(p, canvas_box_for(p)))}))


# ---------------------------------------------------------------------------
# 2. Beginner version by filter
# ---------------------------------------------------------------------------


def drop_small(labels: np.ndarray, min_share: float) -> np.ndarray:
    """Give every shape smaller than min_share of the picture to whatever surrounds it, smallest first."""
    labels = labels.copy()
    for _ in range(6):
        areas = np.bincount(labels.ravel())
        small = np.flatnonzero((areas > 0) & (areas < min_share * labels.size))
        if not len(small):
            break
        gone = np.isin(labels, small)
        # Nearest kept pixel's label, for every dropped pixel.
        _, idx = cv2.distanceTransformWithLabels(gone.astype(np.uint8), cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL)
        kept_labels = np.zeros(idx.max() + 1, labels.dtype)
        kept_labels[idx[~gone]] = labels[~gone]
        labels[gone] = kept_labels[idx[gone]]
        k, labels = relabel(labels)
    return labels


def relabel(labels: np.ndarray) -> tuple[int, np.ndarray]:
    """Connected patches of one label become shapes numbered from 0."""
    out = np.zeros(labels.shape, np.int32)
    n = 0
    for c in np.unique(labels):
        k, comp = cv2.connectedComponents((labels == c).astype(np.uint8), connectivity=4)
        out[comp > 0] = comp[comp > 0] + n - 1
        n += k - 1
    return n, out


def shapes_filter(rgb: np.ndarray, colors: int = 16, min_share: float = 0.003, soften: float = 2.0) -> np.ndarray:
    """The issue's recipe: edge-keeping smoothing, fewer colors, specks dropped. Every shape left is painted in
    its own mean color, with its edges softened a little."""
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    for _ in range(2):
        bgr = cv2.edgePreservingFilter(bgr, flags=cv2.RECURS_FILTER, sigma_s=60, sigma_r=0.45)
    smooth = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    lab = cv2.cvtColor(smooth, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    labels, _ = filters._fit_assign(lab, colors)
    _, labels = relabel(labels.reshape(rgb.shape[:2]))
    labels = drop_small(labels, min_share)
    n = labels.max() + 1
    counts = np.bincount(labels.ravel(), minlength=n).astype(np.float32)
    out = np.dstack([np.bincount(labels.ravel(), weights=rgb[:, :, c].ravel(), minlength=n) / np.maximum(counts, 1)
                     for c in range(3)])[0][labels]
    out = out.astype(np.uint8)
    return cv2.GaussianBlur(out, (0, 0), soften) if soften else out


def beginner_variants(rgb: np.ndarray) -> dict[str, np.ndarray]:
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return {
        "kuwahara-5": filters.simplify(rgb, strength=5),
        "meanshift-heavy": cv2.cvtColor(cv2.pyrMeanShiftFiltering(bgr, sp=40, sr=45), cv2.COLOR_BGR2RGB),
        "stylization": cv2.cvtColor(cv2.stylization(bgr, sigma_s=100, sigma_r=0.5), cv2.COLOR_BGR2RGB),
        "shapes-0.3": shapes_filter(rgb, 16, 0.003),
        "shapes-1.0": shapes_filter(rgb, 12, 0.010),
        "kuwahara+shapes": shapes_filter(filters.simplify(rgb, strength=4), 16, 0.003, soften=0)
        // 2 + filters.simplify(rgb, strength=5) // 2,
    }


def cmd_beginner(args) -> None:
    p = Path(args.picture)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rgb = load(p, canvas_box_for(p))
    print(json.dumps({"picture": "photo", **busy(rgb)}))
    filters.save(rgb, out / "photo.png")
    for name, img in beginner_variants(rgb).items():
        filters.save(img, out / f"{name}.png")
        print(json.dumps({"picture": name, **busy(img)}))


# ---------------------------------------------------------------------------
# 3. Painting order
# ---------------------------------------------------------------------------

DEPTH_MODEL = Path(__file__).resolve().parents[2] / "models" / "depth_anything_v2_vits.onnx"
# Depth Anything V2 small (Apache 2.0), ONNX export, 99 MB:
# https://github.com/fabio-sim/Depth-Anything-ONNX/releases/download/v2.0.0/depth_anything_v2_vits.onnx
_depth_session = None


def nearness(rgb: np.ndarray) -> np.ndarray:
    """How near each pixel is, 0 (farthest in this picture) to 1 (nearest), from a local depth model."""
    global _depth_session
    import onnxruntime as ort
    if _depth_session is None:
        _depth_session = ort.InferenceSession(str(DEPTH_MODEL), providers=["CPUExecutionProvider"])
    x = cv2.resize(rgb, (518, 518), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255
    x = (x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    out = _depth_session.run(None, {"l_x_": x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
    out = cv2.resize(out, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_CUBIC)
    return (out - out.min()) / max(out.max() - out.min(), 1e-6)


def top_level(parts: list[dict], owner: np.ndarray) -> list[dict]:
    """One row per part with no parent, with its children's pixels counted as its own."""
    root = {}
    for p in parts:
        root[p["id"]] = root.get(p.get("parent"), p.get("parent")) or p["id"]
    rows = []
    for k, p in enumerate(parts):
        if p.get("parent"):
            continue
        fam = [i for i, q in enumerate(parts) if root[q["id"]] == p["id"]]
        rows.append({"id": p["id"], "kind": p["kind"], "claude": len(rows), "mask": np.isin(owner, fam)})
    return rows


def measure_parts(rows: list[dict], near: np.ndarray) -> None:
    h, w = near.shape
    ys = np.arange(h)[:, None] / h
    for r in rows:
        m = r["mask"]
        if not m.any():
            r.update(share=0.0, bottom=0.0, near=0.0)
            continue
        yy = np.broadcast_to(ys, m.shape)[m]
        r.update(share=float(m.mean()), bottom=float(np.percentile(yy, 98)), top=float(np.percentile(yy, 2)),
                 near=float(np.median(near[m])))


def in_front(a: np.ndarray, b: np.ndarray) -> float:
    """How much of part a sits inside part b's filled shape: a thing that cuts a hole or a notch in b is in front
    of it. b is filled by closing gaps up to 6% of the long side and filling holes."""
    k = max(3, int(0.06 * max(b.shape))) | 1
    small = cv2.resize(b.astype(np.uint8), None, fx=0.25, fy=0.25, interpolation=cv2.INTER_NEAREST)
    kk = max(3, k // 4) | 1
    pad = cv2.copyMakeBorder(small, kk, kk, kk, kk, cv2.BORDER_REPLICATE)
    closed = cv2.morphologyEx(pad, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kk, kk)))
    closed = closed[kk:-kk, kk:-kk]
    # Fill holes: whatever the outside can't reach.
    flood = cv2.copyMakeBorder(closed, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    cv2.floodFill(flood, None, (0, 0), 2)
    filled = flood[1:-1, 1:-1] != 2
    asmall = cv2.resize(a.astype(np.uint8), None, fx=0.25, fy=0.25, interpolation=cv2.INTER_NEAREST) > 0
    return float((asmall & filled).sum() / max(asmall.sum(), 1))


def touching(a: np.ndarray, b: np.ndarray) -> bool:
    k = np.ones((5, 5), np.uint8)
    return bool((cv2.dilate(a.astype(np.uint8), k) & b.astype(np.uint8)).sum() > 0.002 * max(a.shape))


def propose(rows: list[dict], rule: str) -> list[str]:
    """An order for the top-level parts, back to front."""
    if rule == "position":  # what ends higher up the picture is farther away
        key = lambda r: (r["bottom"], r["near"])
    elif rule == "depth":
        key = lambda r: (r["near"], r["bottom"])
    else:  # depth+kind: the design's rule (the whole background first, then the objects), depth inside each
        key = lambda r: (r["kind"] in ("object", "thin"), r["near"], r["bottom"])
    return [r["id"] for r in sorted(rows, key=key)]


def agreement(rows: list[dict], order: list[str]) -> dict:
    pos = {i: n for n, i in enumerate(order)}
    out = {"pairs": 0, "agree": 0, "touching": 0, "touching_agree": 0, "differ": []}
    for a, b in combinations(rows, 2):  # a is before b in Claude's list
        same = pos[a["id"]] < pos[b["id"]]
        touch = touching(a["mask"], b["mask"])
        out["pairs"] += 1
        out["agree"] += same
        out["touching"] += touch
        out["touching_agree"] += touch and same
        if not same:
            out["differ"].append(f"{b['id']} before {a['id']}" + ("" if touch else " (apart)"))
    return out


def overlap_conflicts(rows: list[dict], thresh: float = 0.6) -> list[str]:
    """Pairs where the outlines say one part is in front of the other and the list has them the other way."""
    out = []
    for a, b in combinations(rows, 2):  # a is listed before b, so the list says b is in front
        if not touching(a["mask"], b["mask"]):
            continue
        a_on_b, b_on_a = in_front(a["mask"], b["mask"]), in_front(b["mask"], a["mask"])
        if a_on_b > thresh and a_on_b > b_on_a + 0.3:
            out.append(f"{a['id']} sits inside {b['id']} ({a_on_b:.0%}) but is listed before it")
    return out


def local_front(a: np.ndarray, b: np.ndarray, near: np.ndarray) -> float | None:
    """Along the edge two parts share, how much nearer b's side is than a's (positive: b is in front).
    None when they don't touch."""
    r = max(3, int(0.015 * max(a.shape)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    edge = (cv2.dilate(a.astype(np.uint8), k) & cv2.dilate(b.astype(np.uint8), k)) > 0
    sa, sb = edge & a, edge & b
    if min(sa.sum(), sb.sum()) < 0.002 * max(a.shape) * r:
        return None
    return float(np.median(near[sb]) - np.median(near[sa]))


def pairwise(rows: list[dict], near: np.ndarray, eps: float = 0.03) -> list[dict]:
    """For every pair of parts that touch: which one the picture says is in front, and why."""
    out = []
    for a, b in combinations(rows, 2):  # a is before b in Claude's list
        d = local_front(a["mask"], b["mask"], near)
        if d is None:
            continue
        a_in_b, b_in_a = in_front(a["mask"], b["mask"]), in_front(b["mask"], a["mask"])
        if abs(a_in_b - b_in_a) > 0.3:  # one sits inside the other's shape: it's on top
            front, why = (b, "inside") if b_in_a > a_in_b else (a, "inside")
        elif abs(d) >= eps:
            front, why = (b, "depth") if d > 0 else (a, "depth")
        else:
            front, why = None, "can't tell"
        out.append({"back": a["id"], "front": b["id"], "tool_front": front and front["id"], "why": why,
                    "depth_step": round(d, 3), "inside": [round(a_in_b, 2), round(b_in_a, 2)]})
    return out


def lesson_inputs(arg: str) -> tuple[str, Path, Path, Path]:
    if ":" in arg:
        plan, owner, finish = (Path(x) for x in arg.split(":"))
        return plan.stem, plan, owner, finish
    d = Path(arg)
    return d.name, d / "plan.json", d / "parts" / "owner.png", d / "99_finish.png"


def cmd_order(args) -> None:
    from PIL import Image
    for arg in args.lessons:
        name, plan_p, owner_p, finish_p = lesson_inputs(arg)
        parts = json.loads(plan_p.read_text())["parts"]
        owner = np.asarray(Image.open(owner_p))
        finish = np.asarray(Image.open(finish_p).convert("RGB").resize(owner.shape[::-1]))
        near = nearness(finish)
        rows = top_level(parts, owner)
        measure_parts(rows, near)
        res = {"lesson": name, "claude": [r["id"] for r in rows],
               "measured": {r["id"]: [r["kind"], round(r["bottom"], 2), round(r["near"], 2)] for r in rows}}
        for rule in ("position", "depth", "depth+kind"):
            order = propose(rows, rule)
            res[rule] = {"order": order, **agreement(rows, order)}
        res["overlap_conflicts"] = overlap_conflicts(rows)
        res["pairs"] = pairwise(rows, near)
        if args.depth_out:
            out = Path(args.depth_out)
            out.mkdir(parents=True, exist_ok=True)
            filters.save(cv2.applyColorMap((near * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)[:, :, ::-1],
                         out / f"{name}-depth.png")
        print(json.dumps(res))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("busy")
    b.add_argument("pictures", nargs="+")
    b.set_defaults(fn=cmd_busy)
    g = sub.add_parser("beginner")
    g.add_argument("picture")
    g.add_argument("--out", required=True)
    g.set_defaults(fn=cmd_beginner)
    o = sub.add_parser("order")
    o.add_argument("lessons", nargs="+", help="a lesson folder, or plan.json:owner.png:finish")
    o.add_argument("--depth-out")
    o.set_defaults(fn=cmd_order)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
