"""Teaching pictures for every step, all free and all from the outlines (pipeline v2, docs/design/pipeline-v2.md
section 10).

    make(plan, pictures, masks, canvas_box, canvas, out) -> aids.json's contents, with its pictures written to out/
    where_words(area, canvas)                             -> "Inside the outlined area. Its top is about 2 in ..."
    path_mask(path, size)                                 -> the pixels an outline path covers (for tests and checks)

A step picture shows the canvas after the step. A beginner also needs to see where this step's paint goes, a closer
look when it's small, and which paint goes where. Each of those is cut from what build-steps already knows: every
step's painted area (`build_steps.build`'s third value) and its picture. Nothing is inferred or rendered.

- Where (every step): the step's painted area as an SVG path, drawn on the page over the picture before the step.
- Close-up (an area under CLOSE_UP of the canvas): before and after, cropped to the area with a margin.
- Paint map (the first step of a part, and any flat, pass, or blend step with 2 or more paints): the area in flat
  patches, one per paint, numbered in painting order, as a small indexed PNG.
- Transfer outline (once per lesson): the outlines of the objects with no parent, on the quarter grid.

Everything the painter measures is in the canvas (canvas.json's `canvas_box`), not the image model's frame: masks
and pictures are cropped to the canvas first. Page coordinates are VIEW units on the canvas's long side.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import build_steps as bs
import outline as ol
from from_finish import CANVAS, hex_lab

VIEW = 1000  # the page's picture coordinates: this many units along the canvas's long side
CLOSE_UP = 0.2  # a step whose area is under this share of the canvas gets a close-up
CLOSE_SPAN = 0.5  # but not when the area reaches across more than this share of the canvas's long side (scattered
# marks, a long branch): the close-up would be hardly closer than the step picture
CLOSE_PX = 600  # close-ups are at most this many pixels on their long side
CLOSE_MIN = 0.22  # a close-up shows at least this share of the canvas's long side each way, so it isn't all blur
CLOSE_MARGIN = 0.35  # and a margin of this share of the area's own size around it
MAP_PX = 480  # paint maps are at most this many pixels on their long side
TRANSFER_PX = 900
JOIN = 0.008  # marks closer than this share of the long side are joined into one outlined area
SPECK = 0.00004  # outlined pieces (and holes) smaller than this share of the canvas are left out
PATCH = 0.012  # paint map patches are smoothed over this share of the long side, so they read as patches
OUTSIDE, EDGE = (239, 238, 233), (91, 100, 116)  # paint map colors outside the area, and its edge
MAP_SHOWS = ("flat", "pass", "blend")


def canvas_px(shape: tuple[int, int], box: list[float] | None) -> tuple[int, int, int, int]:
    """The canvas box in pixels of a picture in the frame, rounded the way canvas.crop_to_canvas rounds it."""
    h, w = shape[:2]
    b = box or [0, 0, 1, 1]
    return round(b[0] * w), round(b[1] * h), round(b[2] * w), round(b[3] * h)


def to_canvas(a: np.ndarray, box: list[float] | None) -> np.ndarray:
    x0, y0, x1, y1 = canvas_px(a.shape, box)
    return a[y0:y1, x0:x1]


def view_size(shape: tuple[int, int]) -> tuple[int, int]:
    h, w = shape[:2]
    return (VIEW, max(1, round(VIEW * h / w))) if w >= h else (max(1, round(VIEW * w / h)), VIEW)


def _odd(n: float) -> int:
    n = max(3, int(round(n)))
    return n if n % 2 else n + 1


def _disk(r: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


# --- Where: the step's area as an outline ---


def view_mask(area: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """A canvas-sized mask at page coordinates, joined into areas a painter can see: nearby marks merge, specks go.
    It only grows the area (join, keep any covered pixel), so the outline always holds what the step paints."""
    vw, vh = size
    small = cv2.resize(area.astype(np.float32), (vw, vh), interpolation=cv2.INTER_AREA) > 0.02
    r = max(1, int(JOIN * VIEW))
    joined = cv2.morphologyEx(small.astype(np.uint8), cv2.MORPH_CLOSE, _disk(r), borderType=cv2.BORDER_REPLICATE)
    return joined > 0


def outline_path(area: np.ndarray, size: tuple[int, int]) -> str:
    """SVG path data (page coordinates, fill-rule evenodd) around a canvas-sized mask."""
    m = view_mask(area, size)
    floor = SPECK * size[0] * size[1]
    contours, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        if cv2.contourArea(c) < floor:
            continue
        c = cv2.approxPolyDP(c, 0.8, True).reshape(-1, 2)
        if len(c) < 3:
            continue
        out.append("M" + " ".join(f"{x} {y}" for x, y in c) + "Z")
    return "".join(out)


def path_mask(path: str, size: tuple[int, int]) -> np.ndarray:
    """The pixels (page coordinates) inside an outline path, filled even-odd like the page draws it, edge
    included."""
    vw, vh = size
    polys = [np.array([int(v) for v in re.findall(r"-?\d+", p)], np.int32).reshape(-1, 2)
             for p in path.split("M") if p.strip()]
    m = np.zeros((vh, vw), np.uint8)
    if polys:
        cv2.fillPoly(m, polys, 1)
        cv2.polylines(m, polys, True, 1)
    return m > 0


# --- Where, in words ---


def _inches(x: float, step: float | None = None) -> str:
    """A length to the nearest half inch (quarter under 2 in, or `step`), as a painter would read a ruler."""
    step = step or (0.25 if x < 2 else 0.5)
    q = round(x / step) * step
    whole, frac = int(q), q - int(q)
    f = {0.25: "1/4", 0.5: "1/2", 0.75: "3/4"}.get(round(frac, 2), "")
    if not whole:
        return f"{f or '0'} in"
    return f"{whole} {f} in" if f else f"{whole} in"


MARKS_ACROSS = ["the left edge", "the 1/4 mark on the top tape", "the middle mark on the top tape",
                "the 3/4 mark on the top tape", "the right edge"]
MARKS_DOWN = ["the top edge", "the 1/4 mark on the side tape", "the middle mark on the side tape",
              "the 3/4 mark on the side tape", "the bottom edge"]


def _near_mark(v: float, names: list[str], before: str, past: str) -> str:
    """Where a share of the canvas falls among the halves and quarters marked on the tape."""
    k = v * 4
    n = round(k)
    if abs(k - n) <= 0.15:
        return f"at {names[n]}"
    lo = int(np.floor(k))
    return f"{past} {names[lo]}" if k - lo < 0.5 else f"{before} {names[lo + 1]}"


EDGE_SHARE = 0.02  # an area within this share of the canvas's edge reaches the edge
WHOLE = 0.9  # an area covering this share of the canvas is "the whole canvas" (the chickadee's branch reaches all four
# edges but covers 18%: it was called the whole canvas until #51)


def where_words(area: np.ndarray, canvas: dict | None) -> str:
    """Where a step's area is, for the painter to find on the canvas: the outline, plus two or three anchor points
    in inches from the canvas's edges, or, with no canvas size, against the halves and quarters marked on the tape.
    `area` is a mask already cropped to the canvas. No percentages."""
    if not area.any():
        return "Inside the outlined area."
    h, w = area.shape
    ys, xs = np.nonzero(area)
    x0, x1, y0, y1 = xs.min() / w, (xs.max() + 1) / w, ys.min() / h, (ys.max() + 1) / h
    left, right, top, bottom = x0 < EDGE_SHARE, x1 > 1 - EDGE_SHARE, y0 < EDGE_SHARE, y1 > 1 - EDGE_SHARE
    if canvas:
        cw, ch = float(canvas["w_in"]), float(canvas["h_in"])

        def across(v, from_right):
            return f"{_inches((1 - v) * cw)} from the right edge" if from_right else f"{_inches(v * cw)} from the left edge"

        def down(v, from_bottom):
            return f"{_inches((1 - v) * ch)} from the bottom edge" if from_bottom else f"{_inches(v * ch)} from the top edge"
    else:
        def across(v, from_right):
            return _near_mark(v, MARKS_ACROSS, "a little left of", "a little right of")

        def down(v, from_bottom):
            return _near_mark(v, MARKS_DOWN, "a little above", "a little below")

    if left and right and top and bottom:  # a branch can reach all four edges and still be a thin shape
        return ("Inside the outlined area: the whole canvas." if area.mean() >= WHOLE else
                "Inside the outlined area. It reaches all four edges of the canvas.")
    about = "about " if canvas else ""

    def ends(lead: str, near: tuple[bool, bool], names: tuple[str, str], at: tuple[float, float], say) -> str:
        """A band all the way across (or top to bottom): the edges it reaches, then where its other ends are."""
        lead += "".join(f" {w} the {e_} edge" for reach, w, e_ in zip(near, ("from", "to"), names) if reach)
        free = [f"its {side} is {about}{say(v, v > 0.5)}" for reach, side, v in
                zip(near, ("top" if names[0] == "top" else "left side", "bottom" if names[0] == "top" else "right side"), at)
                if not reach]
        return f"Inside the outlined area, {lead}. " + " and ".join(free)[0].upper() + " and ".join(free)[1:] + "."

    if left and right:
        return ends("all the way across", (top, bottom), ("top", "bottom"), (y0, y1), down)
    if top and bottom:
        return ends("top to bottom", (left, right), ("left", "right"), (x0, x1), across)
    # a thing somewhere on the canvas: its nearer top or bottom, its nearer side, and its size
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    from_bottom, from_right = cy > 0.5, cx > 0.5
    v_edge = ("bottom", y1) if from_bottom else ("top", y0)
    h_edge = ("right side", x1) if from_right else ("left side", x0)

    def place(v: float, flag: bool, say, edge: str) -> str:
        if min(v, 1 - v) < EDGE_SHARE:
            return f"at the {edge} edge"
        return about + say(v, flag) if canvas else say(v, False)

    v_say = place(v_edge[1], from_bottom, down, "bottom" if from_bottom else "top")
    h_say = place(h_edge[1], from_right, across, "right" if from_right else "left")
    size = f"; it's about {_inches((x1 - x0) * cw)} wide and {_inches((y1 - y0) * ch)} tall" if canvas else ""
    return f"Inside the outlined area. Its {v_edge[0]} is {v_say}, and its {h_edge[0]} is {h_say}{size}."


# --- Close-ups ---


def _span(area_view: np.ndarray) -> int:
    """How far the area reaches along its longer direction, in page units."""
    ys, xs = np.nonzero(area_view)
    return int(max(xs.max() - xs.min(), ys.max() - ys.min())) + 1


def close_box(area_view: np.ndarray) -> list[int]:
    """[x0, y0, x1, y1] in page coordinates: the area with a margin, at least CLOSE_MIN of the long side each way."""
    vh, vw = area_view.shape
    ys, xs = np.nonzero(area_view)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    margin = max(CLOSE_MARGIN * max(x1 - x0, y1 - y0), 0.03 * VIEW)
    side = CLOSE_MIN * VIEW
    box = []
    for lo, hi, full in ((x0, x1, vw), (y0, y1, vh)):
        a, b = lo - margin, hi + margin
        if b - a < side:
            grow = (side - (b - a)) / 2
            a, b = a - grow, b + grow
        if a < 0:
            a, b = 0, min(full, b - a)
        if b > full:
            a, b = max(0, a - (b - full)), full
        box.append((int(np.floor(a)), int(np.ceil(b))))
    return [box[0][0], box[1][0], box[0][1], box[1][1]]


def crop_view(picture: np.ndarray, box: list[int], size: tuple[int, int], max_px: int) -> Image.Image:
    """A canvas-sized picture cut to a box in page coordinates, at its own resolution up to max_px."""
    h, w = picture.shape[:2]
    sx, sy = w / size[0], h / size[1]
    crop = picture[round(box[1] * sy):round(box[3] * sy), round(box[0] * sx):round(box[2] * sx)]
    img = Image.fromarray(np.ascontiguousarray(crop))
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    return img


def save_jpeg(img: Image.Image, path: Path) -> None:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=82, optimize=True)
    path.write_bytes(buf.getvalue())


# --- Paint maps ---


def paint_map(colors: np.ndarray, area: np.ndarray, hexes: list[str]) -> np.ndarray:
    """Which of the paints each pixel of the area is nearest to, smoothed into patches: an index into hexes per
    pixel, and -1 outside the area."""
    long_side = max(area.shape)
    L = ol.lab(cv2.GaussianBlur(colors, (0, 0), max(1.0, 0.003 * long_side)))
    d = np.stack([((L - hex_lab(c)) ** 2).sum(2) for c in hexes])
    near = d.argmin(0).astype(np.uint8)
    near = cv2.medianBlur(near, min(_odd(PATCH * long_side), 255))
    out = near.astype(np.int16)
    out[~area] = -1
    return out


def map_png(labels: np.ndarray, hexes: list[str], path: Path) -> tuple[list[int], dict[int, list[int]]]:
    """Write the paint map as a small indexed PNG: 0 outside, 1 the area's edge, then one index per paint. Returns
    the box it covers (page units of `labels`) and where to put each paint's number on it (its own pixels)."""
    ys, xs = np.nonzero(labels >= 0)
    lh, lw = labels.shape
    pad = max(2, int(0.03 * max(lh, lw)))
    x0, x1 = max(0, xs.min() - pad), min(lw, xs.max() + 1 + pad)
    y0, y1 = max(0, ys.min() - pad), min(lh, ys.max() + 1 + pad)
    cut = labels[y0:y1, x0:x1]
    scale = min(1.0, MAP_PX / max(cut.shape))
    mw, mh = max(1, round(cut.shape[1] * scale)), max(1, round(cut.shape[0] * scale))
    small = cv2.resize((cut + 1).astype(np.uint8), (mw, mh), interpolation=cv2.INTER_NEAREST).astype(np.int16) - 1
    inside = small >= 0
    edge = inside & ~(cv2.erode(inside.astype(np.uint8), np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT,
                                borderValue=0) > 0)
    index = np.where(inside, small + 2, 0).astype(np.uint8)
    index[edge] = 1
    palette = [*OUTSIDE, *EDGE]
    for h in hexes:
        palette += [int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)]
    img = Image.fromarray(index, mode="P")
    img.putpalette(palette + [0] * (768 - len(palette)))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    path.write_bytes(buf.getvalue())
    at = {}
    for k in range(len(hexes)):
        mine = (small == k).astype(np.uint8)
        if not mine.any():
            continue
        dist = cv2.distanceTransform(np.pad(mine, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
        y, x = np.unravel_index(int(dist.argmax()), dist.shape)
        at[k] = [int(x), int(y)]
    return [mw, mh], at


# --- The transfer outline ---


def transfer_png(owner_canvas: np.ndarray, parts: list[dict], path: Path) -> list[dict]:
    """The outlines of the objects with no parent, as dark lines on the quarter grid at the canvas's shape."""
    h, w = owner_canvas.shape
    scale = TRANSFER_PX / max(h, w)
    tw, th = max(1, round(w * scale)), max(1, round(h * scale))
    img = np.full((th, tw), 255, np.uint8)
    for k in (1, 2, 3):
        x, y = round(tw * k / 4), round(th * k / 4)
        tone = 170 if k == 2 else 210
        cv2.line(img, (x, 0), (x, th - 1), tone, 1)
        cv2.line(img, (0, y), (tw - 1, y), tone, 1)
    cv2.rectangle(img, (0, 0), (tw - 1, th - 1), 150, 1)
    shown = []
    line = max(2, round(0.0035 * TRANSFER_PX))
    for k, p in enumerate(parts):
        if p.get("parent") or p["kind"] != "object":
            continue
        family = bs._family(parts, k)
        m = np.isin(owner_canvas, family)
        if not m.any():
            continue
        small = cv2.resize(m.astype(np.uint8), (tw, th), interpolation=cv2.INTER_NEAREST)
        small = cv2.morphologyEx(small, cv2.MORPH_CLOSE, _disk(max(1, int(JOIN * TRANSFER_PX))))
        contours, _ = cv2.findContours(small, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contours = [cv2.approxPolyDP(c, 1.0, True) for c in contours if cv2.contourArea(c) > 0.0004 * tw * th]
        if not contours:
            continue
        cv2.polylines(img, contours, True, 40, line, cv2.LINE_AA)
        n = len(shown) + 1
        dist = cv2.distanceTransform(np.pad(small, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
        y, x = np.unravel_index(int(dist.argmax()), dist.shape)  # the number goes deep inside the shape
        cv2.putText(img, str(n), (int(x) - 8, int(y) + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 40, 2, cv2.LINE_AA)
        shown.append({"n": n, "part": p["id"], "name": p.get("name") or p["id"]})
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG", optimize=True)
    path.write_bytes(buf.getvalue())
    return shown


# --- Everything, for every step ---


def map_steps(plan: dict) -> dict[int, tuple[str, list[str]]]:
    """{step index: ("part" or "step", the paint ids the map shows)}: the first step of each part maps all of the
    part's paints over the whole part; a later flat, pass, or blend step with 2 or more paints maps its own. A map
    with one paint would be the Where outline again, so there isn't one."""
    steps = bs.flat_steps(plan)
    first: dict[str, int] = {}
    part_paints: dict[str, list[str]] = {}
    for i, s in enumerate(steps):
        first.setdefault(s["part"], i)
        for c in s.get("paints") or []:
            if c not in part_paints.setdefault(s["part"], []):
                part_paints[s["part"]].append(c)
    out = {}
    for i, s in enumerate(steps):
        if first[s["part"]] == i and len(part_paints[s["part"]]) >= 2:
            out[i] = ("part", part_paints[s["part"]])
        elif s.get("show") in MAP_SHOWS and len(s.get("paints") or []) >= 2:
            out[i] = ("step", list(s["paints"]))
    return out


def make(plan: dict, pictures: list[np.ndarray], masks: list[np.ndarray], owner: np.ndarray,
         canvas_box: list[float] | None, canvas: dict | None, out: Path, images: list[str]) -> dict:
    """Write every step's teaching pictures into `out` (the lesson's aids/ folder) and return aids.json's
    contents. `pictures` and `masks` are build_steps.build's, in the frame; `images` the step pictures' names."""
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*"):
        if old.is_file() and old.suffix in (".png", ".jpg"):
            old.unlink()
    steps = bs.flat_steps(plan)
    paints = {c["id"]: c for c in plan.get("paints") or []}
    pics = [to_canvas(p, canvas_box) for p in pictures]
    areas = [to_canvas(m, canvas_box) for m in masks]
    size = view_size(pics[0].shape)
    blank = np.empty_like(pics[0])
    blank[:] = CANVAS
    maps = map_steps(plan)
    rel = out.name
    rows = []
    for i, (s, area) in enumerate(zip(steps, areas)):
        share = float(area.mean())
        row = {"id": s["id"], "image": images[i], "area": round(share, 4),
               "path": outline_path(area, size), "where_words": where_words(area, canvas)}
        stem = f"{i + 1:02d}_{s['id']}"
        vm = view_mask(area, size) if area.any() and share < CLOSE_UP else None
        if vm is not None and vm.any() and _span(vm) <= CLOSE_SPAN * VIEW:
            box = close_box(vm)
            before = crop_view(pics[i - 1] if i else blank, box, size, CLOSE_PX)
            after = crop_view(pics[i], box, size, CLOSE_PX)
            save_jpeg(before, out / f"{stem}_before.jpg")
            save_jpeg(after, out / f"{stem}_after.jpg")
            row["closeup"] = {"box": box, "before": f"{rel}/{stem}_before.jpg", "after": f"{rel}/{stem}_after.jpg"}
        if i in maps:
            kind, ids = maps[i]
            if kind == "part":
                mine = [j for j, t in enumerate(steps) if t["part"] == s["part"]]
                where = np.zeros_like(area)
                colors = pics[i].copy()
                for j in mine:  # each pixel as the part's own steps last left it
                    colors[areas[j]] = pics[j][areas[j]]
                    where |= areas[j]
            else:
                where, colors = area, pics[i]
            if where.any():
                labels = paint_map(colors, where, [paints[c]["hex"] for c in ids])
                order = list(range(len(ids)))
                if s.get("show") == "blend":  # a blend's paints go on top to bottom
                    ys = np.arange(labels.shape[0])[:, None]
                    mean_y = [float((ys * (labels == k)).sum() / max(1, (labels == k).sum())) for k in order]
                    order.sort(key=lambda k: mean_y[k])
                # number the patches in painting order: renumber labels so index n-1 is paint n
                relabel = np.full(len(ids) + 1, -1, np.int16)
                for n, k in enumerate(order):
                    relabel[k] = n
                labels = np.where(labels >= 0, relabel[labels], -1)
                hexes = [paints[ids[k]]["hex"] for k in order]
                vh_labels = cv2.resize((labels + 1).astype(np.uint8), size, interpolation=cv2.INTER_NEAREST).astype(np.int16) - 1
                msize, at = map_png(vh_labels, hexes, out / f"{stem}_map.png")
                total = max(1, int((labels >= 0).sum()))
                row["map"] = {"image": f"{rel}/{stem}_map.png", "size": msize, "of": kind,
                              "legend": [{"n": n + 1, "paint": ids[k], "name": paints[ids[k]].get("name") or ids[k],
                                          "hex": paints[ids[k]]["hex"],
                                          "share": round(float((labels == n).sum()) / total, 3), "at": at.get(n)}
                                         for n, k in enumerate(order)]}
        rows.append(row)
    transfer = transfer_png(to_canvas(owner, canvas_box), plan["parts"], out / "transfer.png")
    return {"view": list(size), "canvas": canvas, "canvas_box": canvas_box or [0, 0, 1, 1],
            "steps": rows, "transfer": {"image": f"{rel}/transfer.png", "parts": transfer} if transfer else None}
