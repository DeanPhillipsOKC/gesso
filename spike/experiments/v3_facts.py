"""Spike S8 (#173): every step's words from a measured fact sheet, and a checker for every number and side.

Not part of the pipeline. Run from the repo root:

    python spike/experiments/v3_facts.py sheet <lesson> [--out facts.json]   the fact sheet, as JSON
    python spike/experiments/v3_facts.py check <lesson> [--strict]           every claim in text.json, checked
    python spike/experiments/v3_facts.py sealed [<lesson> ...]               the checker over sealed lessons
    python spike/experiments/v3_facts.py mutate [<lesson> ...]               plant faults, count the ones caught

The write-up is docs/spikes/v3-words-from-facts.md. Lesson folders are only read; nothing is written into them.

**The sheet** (`sheet`) is measured per step from the step pictures and the plan, with the measure the Where lines
use (`build_steps.visible`, cropped to the canvas, without stray specks: `aids.main_area`), so a sheet and its Where
line always agree. Per step: the step's area (its box in inches from each canvas edge, its size, its middle, the
edges it reaches, and where it meets an edge), the part as the finish shows it, the marks the step adds (each piece
of what it changes, placed on the canvas and inside its part), the paints it names and the color it really adds,
and every other part with which side of it the step sits on and whether they touch. Every number is a measured
fact; `TOLERANCE` says how far a claim may be from it.

**The checker** (`check_text`) reads every number and every side or position word in a step's summary, tip, lines,
and paint notes, sorts each into a claim (or a word that isn't one: a stroke direction, a brush size, a step number,
a label such as "the left path"), and checks each claim against the one fact on that step's sheet it names ("its
top ... from the top edge" against the top of the step's area, not any value on the sheet). A claim fails when that
fact doesn't support it, and says which words, what the sheet says, and where they are. `mutate` plants faults in
the words (lengths moved, sides swapped, edges moved, stripes mirrored) and counts how many the checker catches. A claim whose subject or
reference it can't find on the sheet is `unresolved`: not a failure unless `strict` (a writer working from the
sheet would use the sheet's own names, so in the A/B run every claim must resolve).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "spike"))

import aids  # noqa: E402
import build_steps as bs  # noqa: E402
import draft_text  # noqa: E402
import mixing  # noqa: E402
import publish2  # noqa: E402

CHANGED = draft_text.SAME  # RGB levels: a pixel that moved less than this in a step isn't something the step added
MARK_MIN = 0.04  # a piece of what a step adds is one of its marks when it's at least this share of all it adds
MAX_MARKS = 8
JOIN = 0.004  # pieces closer than this share of the long side are one mark (a stripe broken by a highlight)
NEAR = 0.02  # another part within this share of the long side of a step's area is next to it
EDGE_BAND = 0.02  # where a thing meets a canvas edge: its pixels within this share of that edge (aids.EDGE_SHARE)
SIDE = 0.05  # a thing is left of another when its middle is this share of the canvas (or part) further left
JUST = 0.2  # "just left of the center": within this share of the reference's width
JUST_GAP = 0.12  # "just above X": the gap between them is at most this share of the canvas's height or width
PART_SIDE = 0.15  # a mark "along the left edge" of its part starts within this share of the part's width of it
NEAR_PAINT = 25  # Lab units: a changed pixel this near one of the step's paints is where that paint went
OWN_PAINT_MIN = 0.02  # ... read from those pixels when they're at least this share of what changed (a deck line is
# a sliver of what the hull's last step changes; at 10% the sailboat's deck read as the whole hull's texture)
MOST_SIDE = 0.5  # "the olive goes on the left side": at least this share of what the step adds is in that half
SOME_SIDE = 0.15  # "add some along the left side too": at least this share

# How far a claim may be from the fact it's checked against. A Where line rounds a length to the quarter inch under
# 2 in and the half inch above (aids._inches), so the measured value is within half that step of what it says; a
# claim gets that and a hair of slack, and no more.
TOLERANCE = {
    "inches_under_2": 0.145,  # 1/8 in (half the quarter-inch step) + 0.02 in
    "inches": 0.27,  # 1/4 in (half the half-inch step) + 0.02 in (with 0.05, a Where line moved 1/2 in passed 9% of
    # the time: PR #182 review)
    "share": 0.06,  # "a third of the way in": within 0.06 of the canvas's (or the part's) width
}


def tol(inches: float) -> float:
    return TOLERANCE["inches_under_2"] if inches < 2 else TOLERANCE["inches"]


# --- The sheet ---


def _r(x: float) -> float:
    return round(float(x), 2)


def box_fact(mask: np.ndarray, canvas: dict, speckless: bool = True) -> dict | None:
    """A thing's place on the canvas in inches: how far each side is from its own edge of the canvas, its size, its
    middle (the mean of its pixels, from the left and top edges), the canvas edges it reaches, and where along each
    of those it meets the edge (runs of it in the band by the edge: two paths meet the bottom edge twice). `mask`
    is cropped to the canvas. Measured as the Where words are: without stray specks (aids.main_area)."""
    m = aids.main_area(mask) if speckless else mask
    if not m.any():
        return None
    h, w = m.shape
    cw, ch = float(canvas["w_in"]), float(canvas["h_in"])
    ys, xs = np.nonzero(m)
    x0, x1, y0, y1 = xs.min() / w, (xs.max() + 1) / w, ys.min() / h, (ys.max() + 1) / h
    e = aids.EDGE_SHARE
    edges = [n for n, hit in (("left", x0 < e), ("right", x1 > 1 - e), ("top", y0 < e), ("bottom", y1 > 1 - e)) if hit]
    band = max(1, int(EDGE_BAND * max(h, w)))
    meets = {}
    for name in edges:
        strip = {"left": m[:, :band].mean(1), "right": m[:, -band:].mean(1), "top": m[:band].mean(0),
                 "bottom": m[-band:].mean(0)}[name] >= 0.25  # its width in the band, not its widest row
        along, size = (ch, h) if name in ("left", "right") else (cw, w)
        runs = [(a, b) for a, b in _runs(strip) if (b - a) >= 0.005 * size]
        meets[name] = [{"from": _r(a / size * along), "to": _r(b / size * along), "mid": _r((a + b) / 2 / size * along)}
                       for a, b in runs]
    # the top point (a hill's peak, a sail's tip): where its highest rows are, across
    top_rows = m[ys.min():ys.min() + max(1, int(0.01 * h))]
    peak = float(np.nonzero(top_rows.any(0))[0].mean()) / w
    foot = m[max(ys.min(), ys.max() + 1 - max(1, int(0.05 * (ys.max() + 1 - ys.min())))):ys.max() + 1].any(0)
    base = max((b - a for a, b in _runs(foot)), default=0) / w  # its widest run across its lowest rows (a trunk's base)
    rows = cv2.blur(m.sum(1).astype(np.float32).reshape(-1, 1), (1, max(1, int(0.02 * h) | 1))).ravel()
    widest = (int(rows.argmax()) / h - y0) / max(y1 - y0, 1e-6)  # how far down the thing it's widest (a balloon: 1/3)
    return {"widest_down": _r(widest), "base_wide": _r(base * cw),"left": _r(x0 * cw), "right": _r((1 - x1) * cw), "top": _r(y0 * ch), "bottom": _r((1 - y1) * ch),
            "wide": _r((x1 - x0) * cw), "tall": _r((y1 - y0) * ch), "cx": _r(xs.mean() / w * cw),
            "cy": _r(ys.mean() / h * ch), "peak_x": _r(peak * cw), "edges": edges, "meets": meets,
            "share": round(float(m.mean()), 4)}


def _runs(flags: np.ndarray) -> list[tuple[int, int]]:
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((start, i))
            start = None
    return out


def marks(added: np.ndarray, canvas: dict, part: dict | None) -> list[dict]:
    """The pieces of what a step adds, biggest first up to MAX_MARKS, each at least MARK_MIN of it, then put in
    order left to right. Each carries its box_fact and, when the part's box is given, where its middle sits inside
    the part: `in_part` [across, down] as shares of the part's box (0 is the part's left or top)."""
    if not added.any():
        return []
    r = max(1, int(JOIN * max(added.shape)))
    joined = cv2.morphologyEx(added.astype(np.uint8), cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0
    n, labels, stats, _ = cv2.connectedComponentsWithStats(joined.astype(np.uint8), connectivity=8)
    total = float(added.sum())
    sizes = [(int((added & (labels == k)).sum()), k) for k in range(1, n)]
    keep = [k for s, k in sorted(sizes, reverse=True)[:MAX_MARKS] if s >= MARK_MIN * total]
    out = []
    for k in keep:
        f = box_fact(added & (labels == k), canvas, speckless=False)
        if f is None:
            continue
        if part:
            f["in_part"] = [_r((f["cx"] - part["left"]) / max(part["wide"], 1e-6)),
                            _r((f["cy"] - part["top"]) / max(part["tall"], 1e-6))]
        out.append(f)
    return sorted(out, key=lambda f: f["cx"])


BAND = 0.04  # crossings are read on the rows (or columns) this share of the part's size either side of its middle
CROSS_MIN = 0.04  # a crossing narrower than this share of the part is a speck or a rim, not a stripe
CROSS_JOIN = 0.02  # two runs this close (share of the part) are one crossing
BANDS = (0.25, 0.4, 0.55, 0.7)  # stripes beside stripes are also read on these rows (shares down the part): a short
# stripe can miss the middle row (the lavender run's teal sits beside the blue only in the balloon's upper half)


def crossings(added: np.ndarray, part: dict | None, canvas: dict) -> dict:
    """Where what a step adds crosses the middle of its part: `across` are the runs of it along the part's middle
    rows (stripes down a balloon, left to right), `down` along its middle columns (rails, top to bottom), each
    {"from", "to", "mid"} in inches from the left (or top) edge and `in_part`, the run's middle as a share of the
    part's width (or height). Two stripes joined at the top of a balloon are one mark but two crossings, which is
    what "left of" and "inside" between stripes are read on (#159)."""
    out = {"across": [], "down": [], "bands": [[] for _ in BANDS]}
    if part is None or not added.any():
        return out
    h, w = added.shape
    cw, ch = float(canvas["w_in"]), float(canvas["h_in"])
    rows = [("across", w, cw, part["left"], part["wide"], part["cy"] / ch * h),
            ("down", h, ch, part["top"], part["tall"], part["cx"] / cw * w)]
    rows += [(k, w, cw, part["left"], part["wide"], (part["top"] + at * part["tall"]) / ch * h)
             for k, at in enumerate(BANDS)]
    for key, size, along, lo, extent, mid in rows:
        flat = key != "down"
        other = h if flat else w
        half = max(1, int(BAND * (part["tall"] / ch if flat else part["wide"] / cw) * other))
        a, b = max(0, int(mid) - half), min(other, int(mid) + half + 1)
        band = added[a:b] if flat else added[:, a:b].T
        if band.size == 0:
            continue
        into = out["bands"][key] if isinstance(key, int) else out[key]
        on = band.mean(0) >= 0.5
        floor = CROSS_MIN * extent / along * size
        joined = []
        for x0, x1 in _runs(on):  # a stripe split by a fleck of the paint under it is one stripe
            if joined and x0 - joined[-1][1] < CROSS_JOIN * extent / along * size:
                joined[-1] = (joined[-1][0], x1)
            else:
                joined.append((x0, x1))
        for x0, x1 in joined:
            if x1 - x0 < floor:
                continue
            m = (x0 + x1) / 2 / size * along
            into.append({"from": _r(x0 / size * along), "to": _r(x1 / size * along), "mid": _r(m),
                         "in_part": _r((m - lo) / max(extent, 1e-6))})
    return out


def relation(a: dict, b: dict, canvas: dict) -> list[str]:
    """Where thing `a` sits against thing `b` (two box facts): the words true of it ("left of", "above", "inside",
    ...). Left and right compare their middles, by more than SIDE of the canvas; so do above and below. Inside is
    a's box within b's (give or take NEAR)."""
    cw, ch = float(canvas["w_in"]), float(canvas["h_in"])
    out = []
    if b["cx"] - a["cx"] > SIDE * cw:
        out.append("left of")
    if a["cx"] - b["cx"] > SIDE * cw:
        out.append("right of")
    if b["cy"] - a["cy"] > SIDE * ch:
        out.append("above")
    if a["cy"] - b["cy"] > SIDE * ch:
        out.append("below")
    slack = NEAR * max(cw, ch)
    if (a["left"] >= b["left"] - slack and a["right"] >= b["right"] - slack and a["top"] >= b["top"] - slack
            and a["bottom"] >= b["bottom"] - slack):
        out.append("inside")
    return out


LOCAL_PX = 500  # masks are compared at this long side for where one thing sits beside another
LOCAL_MIN = 0.02  # a thing is beside another on a side when at least this share of its paint near the first is there


def relate(a: np.ndarray, b: np.ndarray, canvas: dict) -> dict:
    """Where thing `a` sits against thing `b`, from their masks (cropped to the canvas): `a` is above `b` when, in
    a's own columns, some of b's paint lies below a's lowest row, with `gap_down` the inches between them; left of
    it when, in a's rows, some of b lies right of a's rightmost column; and so on. Read locally like this, the sun
    is above the mountains where they dip under it, though both are in one band of the canvas. `touch` when they
    meet within NEAR."""
    h, w = a.shape
    s = LOCAL_PX / max(h, w)
    size = (max(1, round(w * s)), max(1, round(h * s)))
    a = cv2.resize(a.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0
    b = cv2.resize(b.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0
    words, gaps = [], {}
    if not a.any() or not b.any():
        return {"words": words, "gap_down": None, "gap_across": None, "touch": False}
    ph, pw = float(canvas["h_in"]) / a.shape[0], float(canvas["w_in"]) / a.shape[1]
    floor = max(3, LOCAL_MIN * min(a.sum(), b.sum()))
    flip = {"above": "below", "below": "above", "left of": "right of", "right of": "left of"}
    # both ways round: b beside a in a's own rows and columns, and a beside b in b's (a wide band is right of the
    # sun where it runs on past the sun, though the sun's rows hold band on both sides)
    for first, second, swap in ((a, b, False), (b, a, True)):
        ys, xs = np.nonzero(first)
        in_cols = second[:, xs.min():xs.max() + 1]
        in_rows = second[ys.min():ys.max() + 1]
        for word, sel, dist, key in (
                ("above", in_cols[ys.max() + 1:], lambda r: np.nonzero(r.any(1))[0].min() * ph, "gap_down"),
                ("below", in_cols[:ys.min()], lambda r: (r.shape[0] - 1 - np.nonzero(r.any(1))[0].max()) * ph,
                 "gap_down"),
                ("left of", in_rows[:, xs.max() + 1:], lambda r: np.nonzero(r.any(0))[0].min() * pw, "gap_across"),
                ("right of", in_rows[:, :xs.min()], lambda r: (r.shape[1] - 1 - np.nonzero(r.any(0))[0].max()) * pw,
                 "gap_across")):
            if sel.sum() >= floor:
                words.append(flip[word] if swap else word)
                g = round(float(dist(sel)), 2)
                gaps[key] = g if key not in gaps else min(gaps[key], g)
    words = sorted(set(words))
    r = max(1, int(NEAR * LOCAL_PX))
    grown = cv2.dilate(a.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0
    return {"words": words, "gap_down": gaps.get("gap_down"), "gap_across": gaps.get("gap_across"),
            "touch": bool((grown & b).any())}


def gap(a: dict, b: dict, canvas: dict) -> dict:
    """The gaps between two box facts in inches, across and down (0 when they overlap that way)."""
    cw, ch = float(canvas["w_in"]), float(canvas["h_in"])
    ax0, ax1, bx0, bx1 = a["left"], cw - a["right"], b["left"], cw - b["right"]
    ay0, ay1, by0, by1 = a["top"], ch - a["bottom"], b["top"], ch - b["bottom"]
    return {"across": _r(max(0.0, bx0 - ax1, ax0 - bx1)), "down": _r(max(0.0, by0 - ay1, ay0 - by1))}


def _color_words(name: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", name.lower()) if w not in STOP]


STOP = {"the", "a", "an", "and", "of", "its", "in", "on", "to", "with", "far", "big", "small"}


def make_sheet(plan: dict, pictures: list[np.ndarray], masks: list[np.ndarray], owner: np.ndarray,
               canvas_box: list[float] | None, canvas: dict) -> dict:
    """The lesson's fact sheet: {"canvas", "tolerance", "parts": {id: what the finish shows of it}, "steps": [...]}.
    `pictures` and `masks` are build_steps.build's (in the frame), `owner` parts/owner.png."""
    parts = plan["parts"]
    steps = bs.flat_steps(plan)
    names = publish2.paint_names(plan)
    hexes = {c["id"]: c["hex"] for c in plan.get("paints") or []}
    seen = bs.visible(plan, owner, masks)
    owner_c = aids.to_canvas(owner, canvas_box)
    index = {p["id"]: i for i, p in enumerate(parts)}
    part_facts = {}
    fam = {p["id"]: np.isin(owner_c, bs._family(parts, k)) for k, p in enumerate(parts)}
    for k, p in enumerate(parts):
        f = box_fact(fam[p["id"]], canvas)
        if f:
            part_facts[p["id"]] = {"name": p.get("name") or p["id"], "kind": p["kind"], "parent": p.get("parent"), **f}
    for pid, f in part_facts.items():  # where each part sits against every other, as the finish shows them
        f["beside"] = {}
        for qid, g in part_facts.items():
            if qid == pid or g.get("parent") == pid or f.get("parent") == qid:
                continue
            loc = relate(aids.main_area(fam[pid]), fam[qid], canvas)
            f["beside"][qid] = {"this_is": sorted(set(loc["words"]) | ({"inside"} & set(relation(f, g, canvas)))),
                                "touches": loc["touch"], "gap": {"down": loc["gap_down"], "across": loc["gap_across"]}}
    first = {}
    for i, s in enumerate(steps):
        first.setdefault(s["part"], i)
    blank = np.empty_like(pictures[0])
    blank[:] = bs.ff.CANVAS
    out = []
    for i, s in enumerate(steps):
        before = pictures[i - 1] if i else blank
        area_c = aids.to_canvas(seen[i], canvas_box)
        area = box_fact(area_c, canvas)
        changed = np.abs(pictures[i].astype(np.int16) - before.astype(np.int16)).max(2) >= CHANGED
        added = aids.to_canvas(changed & masks[i], canvas_box)
        # where the step's own paints land: a part's last step shows everything left of the finish (texture, other
        # colors), so its marks are read from the pixels near one of its paints when those are enough of it
        pic_c = aids.to_canvas(pictures[i], canvas_box)
        own_paint = added
        if added.any() and s.get("paints"):
            L = bs.ff.lab(pic_c[added][None])[0]
            d = np.min([np.sqrt(((L - bs.ff.hex_lab(hexes[c])) ** 2).sum(-1)) for c in s["paints"]], axis=0)
            near = np.zeros_like(added)
            near[added] = d <= NEAR_PAINT
            if near.sum() >= OWN_PAINT_MIN * added.sum():
                own_paint = near
        part = part_facts.get(s["part"])
        mk = marks(own_paint, canvas, part)
        # the color it really adds: the median of what changed, and how far each named paint is from it
        adds = None
        if added.any():
            rgb = np.median(pic_c[added], axis=0).astype(int)
            hx = "#%02x%02x%02x" % tuple(rgb)
            ys, xs = np.nonzero(own_paint)
            cw_, ch_ = float(canvas["w_in"]), float(canvas["h_in"])
            px, py = xs / added.shape[1] * cw_, ys / added.shape[0] * ch_
            adds = {"hex": hx, "paints": {names[c]: round(mixing.delta_e(hx, hexes[c]), 1) for c in s.get("paints") or []},
                    "cx": _r(px.mean()), "cy": _r(py.mean())}
            if part:  # how much of what it adds is in each half of its part
                mx, my = part["left"] + part["wide"] / 2, part["top"] + part["tall"] / 2
                adds["halves"] = {"left": _r((px < mx).mean()), "right": _r((px >= mx).mean()),
                                  "top": _r((py < my).mean()), "bottom": _r((py >= my).mean())}
        # the paints under it: the earlier steps of the part, and a paint this step lays on itself (#159 step 13)
        own_before = [j for j in range(i) if steps[j]["part"] == s["part"]]
        under = sorted({c for j in own_before[-1:] for c in steps[j].get("paints") or []})
        same_as_under = [names[c] for c in s.get("paints") or [] if c in under and s.get("show") == "pass"]
        # every other part: which side this step's area sits on, whether they touch, and how far apart
        own = set(bs._family(parts, index[s["part"]]))
        others = []
        for k, p in enumerate(parts):
            pf = part_facts.get(p["id"])
            if k in own or pf is None or area is None:
                continue
            loc = relate(aids.main_area(area_c), np.isin(owner_c, bs._family(parts, k)), canvas)
            words = sorted(set(loc["words"]) | ({"inside"} & set(relation(area, pf, canvas))))
            others.append({"part": p["id"], "name": pf["name"], "painted": first.get(p["id"], len(steps)) < i,
                           "touches": loc["touch"], "this_is": words,
                           "gap": {"down": loc["gap_down"], "across": loc["gap_across"]}})
        out.append({"n": i + 1, "id": s["id"], "name": s.get("name") or s["id"], "part": s["part"],
                    "part_name": parts[index[s["part"]]].get("name") or s["part"],
                    "kind": parts[index[s["part"]]]["kind"], "show": s.get("show"),
                    "first_of_part": first[s["part"]] == i,
                    "paints": [{"id": c, "name": names[c], "words": _color_words(names[c])} for c in s.get("paints") or []],
                    "area": area, "marks": mk, "crossings": crossings(own_paint, part, canvas), "adds": adds,
                    "same_paint_as_under": same_as_under,
                    "earlier_steps_of_part": [j + 1 for j in own_before], "others": others,
                    "where": aids.where_words(area_c, canvas)})
    return {"canvas": {"w_in": float(canvas["w_in"]), "h_in": float(canvas["h_in"])}, "tolerance": TOLERANCE,
            "parts": part_facts, "steps": out}


def lesson_sheet(lesson: Path) -> tuple[dict, dict]:
    """(sheet, plan) for a lesson folder, built as `check` builds it. Read only: a lesson with no canvas.json gets
    the default size without one being written."""
    import checks
    import plan2

    lesson = Path(lesson)
    plan = plan2.load(lesson)
    built = checks.build(lesson, plan)
    if built is None:
        raise SystemExit(f"{lesson}: no outlines that fit the plan")
    owner, pictures, _rows, masks = built
    box, canvas = canvas_of(lesson, pictures[0].shape)
    return make_sheet(plan, pictures, masks, owner, box, canvas), plan


def canvas_of(lesson: Path, shape) -> tuple[list | None, dict]:
    import canvas as cv

    path = Path(lesson) / "canvas.json"
    if path.exists():
        info = json.loads(path.read_text(encoding="utf-8"))
        return info.get("canvas_box"), info["canvas"]
    h, w = shape[:2]
    cw, chh = cv.orient(*cv.parse(cv.default_size(w / h)), w / h)
    return None, {"w_in": cw, "h_in": chh}


# --- The checker ---
#
# What counts as a claim (each kind is checked against the step's sheet; docs/spikes/v3-words-from-facts.md):
#   length    a number with an inch unit, not a brush size: "about 2 in from the left edge", "3/4 inch across",
#             "two inches wide", "half an inch". Checked against the sheet's lengths on its axis (wide/across/from the
#             left or right edge across; tall/down/below/from the top or bottom edge down; none given: either).
#   edge      a canvas edge reached or not: "at the right edge", "reaches the bottom edge", "from the top edge",
#             "all the way across", "top to bottom" (as a reach, not a stroke), "all four edges", "stops short of".
#   fraction  "a third of the way in", "two-thirds in", "halfway down", "three-quarters across": on the canvas, or
#             inside the part ("widest a third of the way down").
#   center    "(just) left/right of (the) center/middle": the canvas's middle for an area or a thing's first step,
#             the part's middle for marks added inside a painted part.
#   relation  "above / below / left of / right of / inside / outside / beside / next to <something>", "on its right":
#             against another part, or against marks an earlier step put on the same part (named by their color).
#   position  "at the upper right", "on the left side of the canvas", "the lower half of the canvas".
#   side      "on the left side of the tree", "down the post's left half": where a pass adds paint inside its part.
#   agree     two sizes of the step's own thing on one axis in one step must agree (the line says 3 in, the tip 2 1/2).
# What isn't (counted, never failed): stroke directions ("left to right", "side to side", "top to bottom" as a
# stroke), brush sizes ("1/2 inch flat", "#6 round"), step numbers, counts ("two coats", "three stripes"), side words
# used as a label to pick one of several things ("the left path", "the right-hand triangle": the label picks which
# marks a number or relation is checked on), the light's direction ("light from the left"), and a side within a
# thing's own shape on its first step ("the head on its upper right").

NUMW = ("one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
        "seventeen|eighteen|nineteen|twenty")
WORDS = {w: k + 1 for k, w in enumerate(NUMW.split("|"))}
UNICODE_FRACS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875}
_UF = "".join(UNICODE_FRACS)
NUM = (r"\d+-\d+/\d+|\d+\s+\d+/\d+|\d+/\d+|\d*[" + _UF + r"]|\d*\.\d+|\d+|\b(?:" + NUMW +
       r")(?:\s+and\s+a\s+(?:half|quarter))?")
LENGTH = re.compile(
    r"(?P<q>\b(?:under|less than|at most|no more than|over|more than|at least)\s+)?"
    r"(?:about\s+|roughly\s+|nearly\s+|almost\s+|only\s+about\s+|only\s+)?"
    r"(?P<num>" + NUM + r"|\b(?:an|a)\b(?=\s+inch)|\bhalf\s+an|\ba\s+half|\ba\s+quarter(?:\s+of\s+an)?"
    r"|\bthree[- ]quarters\s+of\s+an|\ba\s+third\s+of\s+an)"
    r"(?:\s*(?:-|–|to|or)\s*(?P<num2>" + NUM + r"))?"  # a range: "2 to 3 inches", "2-3 in"
    r"\s*-?\s*(?P<unit>in\b\.?(?!\s+(?:the|a|an|its|their|each|every|this|that|these|those|there|here|front|place|"
    r"half|one|two)\b)|inch(?:es)?\b)"
    r"(?P<and>\s+and\s+a\s+(?:half|quarter))?", re.I)
BRUSH = re.compile(r"^\s*(?:wide\s+)?(?:flat|bright|filbert|angle|angled|round|mop|fan|brush|liner|dagger)\b", re.I)
SIDES = "left|right|top|bottom"
EDGE = re.compile(r"\b(?P<side>" + SIDES + r")(?:\s+canvas)?\s+edge\b(?P<of>\s+of\s+(?:the\s+)?(?P<owner>[\w-]+))?", re.I)
REACH_BEFORE = re.compile(r"(?:\bat|\bto|\breach(?:es|ing)?|\btouch(?:es|ing)?|\bmeets?|\bagainst|\balong|\boff|\bfrom|\bon"
                          r"|\binto|\bpast|\bup to|\bdown to|\bacross to)\s+(?:the\s+)?(?:very\s+|far\s+)?$", re.I)
NOT_REACH = re.compile(r"(?:short of|before|clear of|away from|not\s+(?:reach|touch)\w*|n't\s+(?:reach|touch)\w*)\s+"
                       r"(?:the\s+)?(?:very\s+|far\s+)?$", re.I)
ACROSS = re.compile(r"\ball the way across\b|\bedge to edge\b|\bfrom the left edge to the right(?: edge)?\b", re.I)
TOP_BOTTOM = re.compile(r"(?:\barea,\s*|\b(?:runs?|reach(?:es)?|goes|go|stretch(?:es)?|spans?)\s+(?:all the way\s+)?"
                        r"(?:from\s+)?)top to bottom\b", re.I)
FOUR = re.compile(r"\ball four edges\b", re.I)
FRACTION = re.compile(
    r"\b(?P<f>(?:a|one|two|three)[- ](?:third|quarter|fourth)s?|halfway|half way)(?:\s+of\s+the\s+way)?\s+"
    r"(?P<dir>in\b|across|along|down|up|from the (?:left|right|top|bottom)(?: edge)?)", re.I)
CENTER = re.compile(r"\b(?P<q>just |a little |slightly |a bit |a touch )?(?P<side>left|right) of (?:the )?(?:center|centre|middle)"
                    r"(?!\s+(?!of\b)[a-z])"  # not "left of the center red stripe": that's a relation to the stripe
                    r"(?: of (?:the )?(?P<of>canvas|painting|[\w-]+(?: [\w-]+)?))?", re.I)
# the reference ends at and/or/then/while/but (N1 of PR #182's second review): in "just outside the left red stripe
# and one just left of the center red stripe" the second relation is a claim of its own
RELATION = re.compile(r"\b(?P<q>just |right |directly |a little |slightly |straight |well )?"
                      r"(?P<rel>above|below|beneath|to the left of|to the right of|left of|right of|inside|outside|beside|"
                      r"next to)\s+(?P<ref>(?:(?!\b(?:and|or|then|while|but)\b)[^,.;:()])+)", re.I)
ON_ITS = re.compile(r"\bon\s+(?:its|their|the\s+(?P<ref>[\w\s-]+?)'s?)\s+(?P<side>left|right)\b"
                    r"(?!\s*(?:-hand|side|edge|half|end|part))", re.I)
POSITION = re.compile(r"(?<!\bto )(?<!\bdown )\b(?:at|in|on|near)\s+the\s+(?:far\s+)?(?P<v>upper|lower|top|bottom)[ -]"
                      r"(?P<h>left|right)(?:\s+corner)?\b(?!\s+(?:of|side of|edge of)\s+(?!the canvas))"
                      r"|\b(?:on|in|along|down|up|across|to|toward|towards|into)\s+the\s+(?P<s>left|right|top|bottom|upper|lower)"
                      r"\s+(?:side|half|third)\s+of\s+the\s+(?:canvas|painting)\b", re.I)
SIDE_OF = re.compile(r"\b(?:on|along|down|to|at|over|into|up)\s+(?:the\s+|its\s+|their\s+)?(?:(?P<owner>[\w-]+)'s?\s+)?"
                     r"(?P<side>left|right|top|bottom|upper|lower)\s+(?P<what>side|edge|half|end|part)\b"
                     r"(?:\s+of\s+(?:the\s+|each\s+)?(?P<of>[\w-]+))?", re.I)
STRIPE = re.compile(r"\b(?:stripes?|lines?|bands?|strips?|bars?|streaks?|dash(?:es)?|rails?)\b", re.I)
LEAVE = re.compile(r"\bleav(?:e|ing)\b|\bshowing\b", re.I)
LABEL = re.compile(r"\b(?:the\s+)?(?P<far>far\s+|very\s+)?(?P<label>left|right|center|centre|middle)(?:[- ]?hand|most)?\s+"
                   r"(?!(?:edges?|sides?|of|is|are|and|or|half|end|ends|part|to|corner|third|quarter|in|on|at|from)\b)"
                   r"(?:one|ones|[a-z]+)", re.I)
LABEL_WORDS = re.compile(r"\b(?:left|right|center|centre|middle|top|bottom|upper|lower)(?:[- ]?hand|most)?\s+(?!edges?\b)"
                         r"[a-z]+|\b(?:its|their|the)\s+(?:left|right|top|bottom|upper|lower)\b", re.I)
# words that aren't claims, by why (counted, so the false-alarm rate can be read beside them)
NOT_CLAIMS = [
    ("stroke direction", re.compile(r"\b(?:left|right|top|bottom|side|up|down|bow|stern)\s+(?:to|and)\s+(?:left|right|top|"
                                    r"bottom|side|up|down|bow|stern)\b|\bfrom the (?:top|bottom) down\b"
                                    r"|\b(?:to|toward|towards|into)\s+the\s+(?:upper|lower|top|bottom)[ -](?:left|right)\b",
                                    re.I)),
    ("brush size", re.compile(r"(?:\d+(?:/\d+)?\s*(?:-\s*)?inch(?:es)?|#\s*\d+)\s+(?:wide\s+)?(?:flat|bright|round|filbert|"
                              r"angle|angled|liner|mop|fan|brush)|#\s*\d+", re.I)),
    ("step number", re.compile(r"\bsteps?\s+\d+(?:\s*(?:,|and|to)\s*\d+)*", re.I)),
    ("light", re.compile(r"\b(?:light|lit|sun|glow)\w*\b[^.;]{0,40}\b(?:from|on) the (?:upper |lower )?(?:left|right)\b"
                         r"|\bfacing the (?:sun|light|moon)\b", re.I)),
    ("label", LABEL_WORDS),
    ("count", re.compile(r"\b(?:\d+|" + NUMW + r"|a few|a dozen|dozens?)\b", re.I)),
]
SIDE_WORD = re.compile(r"\b(?:left|right|top|bottom|upper|lower|center|centre|middle|edges?)\b|\b\d+(?:/\d+)?\b|\b(?:"
                       + NUMW + r")\b", re.I)
PREP = (r"\b(?:of|on|onto|above|below|under|over|to|from|beside|near|behind|into|around|toward|towards|in|at|by|with|"
        r"between|past|across|along|through|up|down|against|than|like)")
GENERIC = {"light", "dark", "deep", "pale", "soft", "warm", "cool", "bright", "muted", "shadow", "sunset", "golden"}


def number(num: str) -> float:
    """One number as a length says it: "1 1/2", "1-1/2", "1½", ".5", "two", "two and a half", "half an"."""
    num = re.sub(r"\s+", " ", num.lower().strip())
    if num and num[-1] in UNICODE_FRACS:
        return float(int(num[:-1]) if num[:-1] else 0) + UNICODE_FRACS[num[-1]]
    hit = re.fullmatch(r"(\d+)[ -](\d+)/(\d+)", num)
    if hit:
        return int(hit.group(1)) + int(hit.group(2)) / int(hit.group(3))
    if "/" in num:
        a, b = num.split("/")
        return int(a) / int(b)
    if re.fullmatch(r"\d*\.?\d+", num):
        return float(num)
    if re.match(r"three[- ]quarters", num):
        return 0.75
    if num.split()[0] in WORDS:
        return WORDS[num.split()[0]] + (0.5 if "half" in num else 0.25 if "quarter" in num else 0)
    if num in ("a", "an"):
        return 1.0
    if num.startswith("half") or num == "a half":
        return 0.5
    if num.startswith("a quarter"):
        return 0.25
    return 1 / 3  # a third of an inch


def span(m: re.Match) -> tuple[float, float]:
    """The lengths a LENGTH match says, in inches: (lo, hi), the same twice unless it's a range ("2 to 3 in")."""
    v = number(m.group("num"))
    if m.group("and"):
        v += 0.5 if "half" in m.group("and") else 0.25
    w = number(m.group("num2")) if m.group("num2") else v
    return min(v, w), max(v, w)


def inches(m: re.Match) -> float:
    """The length a LENGTH match says, in inches (a range's middle)."""
    lo, hi = span(m)
    return (lo + hi) / 2


def share_of(word: str) -> float:
    w = word.lower().replace("-", " ")
    if w in ("halfway", "half way"):
        return 0.5
    n, frac = w.split()
    k = {"a": 1, "one": 1, "two": 2, "three": 3}[n]
    return k * {"third": 1 / 3, "thirds": 1 / 3, "quarter": 0.25, "quarters": 0.25, "fourth": 0.25, "fourths": 0.25}[frac]


class Lesson:
    """A lesson's sheet with what the checker needs to find parts by their words."""

    def __init__(self, sheet: dict):
        self.sheet = sheet
        self.cw, self.ch = sheet["canvas"]["w_in"], sheet["canvas"]["h_in"]
        self.parts = sheet["parts"]
        self.steps = {s["n"]: s for s in sheet["steps"]}
        pats = []
        for pid, p in self.parts.items():
            name = re.sub(r"^the\s+", "", p["name"].lower()).strip()
            words = [w for w in re.findall(r"[a-z]+", name) if w not in STOP]
            alts = {re.escape(name), re.escape(pid.replace("-", " ")), re.escape(pid)}
            heads = {words[-1]} if words else set()
            if " and " in name:
                heads |= set(words)
            for hd in heads:  # a plural name is named only in the plural: "the trunk" isn't "Far misty trunks"
                plural = len(hd) > 3 and hd.endswith("s") and not hd.endswith("ss")
                alts.add(re.escape(hd) if plural else re.escape(hd) + r"(?:s|es)?")
            pats.append((pid, re.compile(r"\b(?:" + "|".join(sorted(alts, key=len, reverse=True)) + r")\b", re.I)))
        self.part_patterns = pats

    def mentions(self, text: str) -> list[tuple[int, int, str]]:
        """(start, end, part id) of every part the text names, the longest where two overlap."""
        found = [(m.start(), m.end(), pid) for pid, pat in self.part_patterns for m in pat.finditer(text)]
        found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        out = []
        for f in found:
            if out and f[0] < out[-1][1]:
                continue
            out.append(f)
        return out

    def subjects(self, text: str) -> list[tuple[int, int, str]]:
        """The mentions that can be what a sentence is about: not the object of a preposition ("on the top of the
        big hill"), except a place named by what goes there ("around where the sun will go")."""
        out = []
        for a, b, pid in self.mentions(text):
            before = text[:a]
            if re.search(r"\bwhere\s+(?:the\s+|its\s+)?(?:\w+\s+)?$", before, re.I) or \
                    not re.search(PREP + r"\s+(?:the\s+|its\s+|their\s+|a\s+|each\s+|both\s+)?(?:[\w-]+\s+){0,2}$",
                                  before, re.I):
                out.append((a, b, pid))
        return out


def _things(st: dict, lesson: Lesson) -> list[dict]:
    """The step's own things: its area, the marks it adds, and its part as the finish shows it."""
    out = []
    if st["area"]:
        out.append(dict(st["area"], what="the step's area"))
    out += [dict(m, what=f"mark {k + 1}") for k, m in enumerate(st["marks"])]
    p = lesson.parts.get(st["part"])
    if p:
        out.append(dict(p, what=st["part_name"].lower()))
    return out


def _items(st: dict) -> list[dict]:
    """Every placed piece of the step, as {from, to, mid} across (inches from the left) with `what`: marks, crossings,
    and the runs where it meets the top or bottom edge. A label ("the right path") picks among these."""
    out = [{"from": m["left"], "to": None, "mid": m["cx"], "what": f"mark {k + 1}", "box": m}
           for k, m in enumerate(st["marks"])]
    out += [dict(c, what=f"crossing {k + 1}") for k, c in enumerate(st["crossings"]["across"])]
    for e in ("bottom", "top"):
        out += [dict(r, what=f"where it meets the {e} edge") for r in ((st["area"] or {}).get("meets") or {}).get(e, [])]
    return out


def _pick(items: list[dict], label: str | None, center: float) -> list[dict]:
    """The one of several pieces a label names: the leftmost, the rightmost, or the one nearest the middle."""
    if not label or len(items) < 2:
        return items
    label = label.lower()
    if label == "left":
        return [min(items, key=lambda x: x["mid"])]
    if label == "right":
        return [max(items, key=lambda x: x["mid"])]
    if label in ("center", "centre", "middle"):
        return [min(items, key=lambda x: abs(x["mid"] - center))]
    return items


def _positions(t: dict, cw: float, ch: float) -> dict[str, list[float]]:
    """A thing's places (x from the left edge, y from the top edge) and sizes (w across, h down) in inches."""
    if "wide" not in t:  # a crossing or an edge run: only across
        xs = [v for v in (t.get("from"), t.get("to"), t.get("mid")) if v is not None]
        return {"x": xs, "y": [], "w": [t["to"] - t["from"]] if t.get("to") is not None else [], "h": []}
    x = [t["left"], cw - t["right"], t["cx"], t["peak_x"]]
    y = [t["top"], ch - t["bottom"], t["cy"]]
    w, h = [t["wide"]], [t["tall"]]
    for e, runs in (t.get("meets") or {}).items():
        for r in runs:
            if e in ("top", "bottom"):
                x += [r["from"], r["to"], r["mid"]]
                w.append(r["to"] - r["from"])
            else:
                y += [r["from"], r["to"], r["mid"]]
                h.append(r["to"] - r["from"])
    return {"x": x, "y": y, "w": w, "h": h}


def _fmt(vals: list[float], said: float) -> str:
    near = sorted({round(v, 2) for v in vals}, key=lambda v: abs(v - said))[:3]
    return ", ".join(f"{v:g} in" for v in near) if near else "nothing"


class Reader:
    """Reads one step's words into claims and checks each against the step's sheet."""

    def __init__(self, lesson: Lesson, st: dict):
        self.L, self.st = lesson, st
        self.cw, self.ch = lesson.cw, lesson.ch
        self.part = lesson.parts.get(st["part"])
        self.family = [st["part"]]
        ids = {st["part"]}
        for pid, p in lesson.parts.items():
            if p.get("parent") in ids:
                ids.add(pid)
                self.family.append(pid)

    def subject(self, sentence: str, pos: int) -> tuple[list[dict], str | None, str]:
        """The things a claim at `pos` is about, the label that picks among them, and who they are: another part
        named in the same clause before it (or at the start of the sentence), else the step's own things."""
        start = max([m.end() for m in re.finditer(r"[,;:()]|\b(?:and|then|while|so)\b", sentence[:pos])], default=0)
        clause = sentence[start:pos]
        lm = list(LABEL.finditer(clause))
        label = lm[-1].group("label") if lm else None
        named = self.L.subjects(clause) or self.L.subjects(sentence[:pos])  # the first thing the clause is about
        self.subject_part = None
        if named and named[0][2] != self.st["part"]:  # another part, or a child of this one (the sun in the sky)
            self.subject_part = named[0][2]
            p = self.L.parts[named[0][2]]
            return [dict(p, what=p["name"].lower())], None, p["name"]
        return _things(self.st, self.L), label, "this step"

    def claim(self, kind, field, sentence, m_or_span, ok, sheet, why=""):
        span = m_or_span if isinstance(m_or_span, tuple) else m_or_span.span()
        return {"step": self.st["n"], "id": self.st["id"], "field": field, "kind": kind,
                "words": sentence[span[0]:span[1]].strip(), "sentence": sentence.strip(), "ok": ok, "sheet": sheet,
                "why": why, "span": span}

    def read(self, sentence: str, field: str) -> tuple[list[dict], list[tuple[str, str]]]:
        """The claims in one sentence, and the side words and numbers in it that aren't claims, with why."""
        used: list[tuple[int, int]] = []
        out: list[dict] = []

        def free(a, b):
            return all(b <= u0 or a >= u1 for u0, u1 in used)

        def take(c):
            used.append(c["span"])
            # what's left showing (gaps, the paint under) isn't on the sheet: a place said of it can't be checked
            start = max([x.end() for x in re.finditer(r"[,;:]", sentence[:c["span"][0]])], default=0)
            if c["ok"] is False and (LEAVE.search(sentence[start:c["span"][0]]) or re.match(r"\s*leav", sentence, re.I)):
                c.update(ok=None, why="said of what's left showing, which the sheet doesn't hold")
            out.append(c)

        for m in LENGTH.finditer(sentence):
            if free(*m.span()) and not BRUSH.match(sentence[m.end():]):
                take(self.length(sentence, field, m))
        for pat, sides in ((ACROSS, ["left", "right"]), (TOP_BOTTOM, ["top", "bottom"]),
                           (FOUR, ["left", "right", "top", "bottom"])):
            for m in pat.finditer(sentence):
                if free(*m.span()):
                    take(self.edges(sentence, field, m, sides, True))
        for m in EDGE.finditer(sentence):
            if not free(*m.span()):
                continue
            before = sentence[:m.start()]
            owner = (m.group("owner") or "").lower()
            # the part's own edge, named as such: "along the far left edge of the balloon", "along its left edge"
            own_edge = bool(m.group("of") and any(pid in self.family for _a, _b, pid in self.L.mentions(owner))) or \
                bool(re.search(r"\b(?:its|their)\s+(?:very\s+|far\s+)?$", before, re.I))
            if m.group("of") and owner not in ("canvas", "painting") and not own_edge:
                continue  # the edge of another thing, not of the canvas
            if own_edge and (self.st["first_of_part"] or field.endswith("(where)")):
                continue  # a thing's first step is at its own edges by definition: no claim
            before = re.sub(r"\b(?:its|their)\s+((?:very\s+|far\s+)?)$", r"the \1", before)
            if NOT_REACH.search(before):
                take(self.edges(sentence, field, m, [m.group("side").lower()], False, own_edge))
            elif REACH_BEFORE.search(before):
                take(self.edges(sentence, field, m, [m.group("side").lower()], True, own_edge))
        for m in FRACTION.finditer(sentence):
            if free(*m.span()):
                take(self.fraction(sentence, field, m))
        for m in CENTER.finditer(sentence):
            if free(*m.span()):
                take(self.center(sentence, field, m))
        prev = None
        rels = sorted([(m, "rel") for m in RELATION.finditer(sentence)] + [(m, "on") for m in ON_ITS.finditer(sentence)],
                      key=lambda x: x[0].start())
        for m, how in rels:
            if free(*m.span()):
                c, prev = self.relation(sentence, field, m, how, prev)
                if c:
                    take(c)
        for m in POSITION.finditer(sentence):
            if free(*m.span()):
                take(self.position(sentence, field, m))
        for m in SIDE_OF.finditer(sentence):
            if free(*m.span()):
                c = self.side_of(sentence, field, m)
                if c:
                    take(c)
        rest = []
        for m in SIDE_WORD.finditer(sentence):
            if free(*m.span()):
                why = next((name for name, pat in NOT_CLAIMS for x in pat.finditer(sentence)
                            if x.start() <= m.start() < x.end()), "other")
                rest.append((why, m.group(0)))
        return out, rest

    # -- the kinds of claim --

    def length(self, sentence, field, m):
        """A length is checked against the one fact it names (H2 of the PR #182 review): "its top is 2 in from the
        top edge" against the top of the thing, "3 in wide" against its width. The thing is the step's area for a
        Where line; for other words, the part the clause names, or the labeled mark ("the right one"), or the step's
        area, its part and its marks (one value each). A length that names no axis, edge, or size is unresolved."""
        lo, hi = span(m)
        said = (lo + hi) / 2
        after, before = sentence[m.end():m.end() + 40].lower(), sentence[max(0, m.start() - 30):m.start()].lower()
        start = max([x.end() for x in re.finditer(r"[,;:()]|\b(?:and|then|while)\b", sentence[:m.start()])], default=0)
        clause = sentence[start:m.start()].lower()
        things, label, who = self.subject(sentence, m.start())
        where_line = field.endswith("(where)")
        items = []
        if where_line:
            things = [dict(self.st["area"], what="the step's area")] if self.st["area"] else []
        elif label and who == "this step":
            items = _pick(_items(self.st), label, self._center_x())
            things = [i["box"] for i in items if "box" in i] or things
        pieces = [i for i in items if "box" not in i]  # crossings and edge runs: across only
        # the anchor the clause names: its top, its left side, its middle...
        anc = re.findall(r"\b(?:its|their|the)\s+(top|bottom|base|left side|right side|left end|right end|left|right|"
                         r"middle|center|centre|peak)\b(?!\s+(?:canvas\s+)?edge)", clause)
        anchor = anc[-1].split()[0] if anc else None
        anchor = {"base": "bottom", "centre": "middle", "center": "middle"}.get(anchor, anchor)

        def coord(t, a, axis):
            """The thing's coordinate (inches from the left or top edge) for anchor a on an axis."""
            if "wide" not in t:  # a crossing or an edge run
                return {"left": t.get("from"), "right": t.get("to"), "middle": t.get("mid")}.get(a) if axis == "x" else None
            x = {"left": t["left"], "right": self.cw - t["right"], "middle": t["cx"], "peak": t["peak_x"]}
            y = {"top": t["top"], "bottom": self.ch - t["bottom"], "middle": t["cy"]}
            return (x if axis == "x" else y).get(a)

        def from_edge(e):
            axis = "x" if e in ("left", "right") else "y"
            near = {"left": "left", "right": "right", "top": "top", "bottom": "bottom"}[e]
            anchors = [anchor] if anchor else [near, "middle"]
            if not anchor and axis == "x" and re.search(r"\b(?:top|peak|tip)\b", clause):
                anchors.append("peak")  # "to a soft round top about 2 in in"
            extra = pieces
            if not where_line and not label and who == "this step" and axis == "x":
                extra = pieces + self.st["crossings"]["across"]  # the bars it paints, where they cross the middle row
            vals = [coord(t, a, axis) for t in things + extra for a in anchors]
            full = self.cw if axis == "x" else self.ch
            return [v if e in ("left", "top") else full - v for v in vals if v is not None]

        def sizes(axis):
            out = [t["wide" if axis == "x" else "tall"] for t in things if "wide" in t]
            if axis == "x":
                out += [p["to"] - p["from"] for p in pieces if p.get("to") is not None]
                if not where_line and not label and who == "this step":  # its width at the part's middle row
                    out += [c["to"] - c["from"] for c in self.st["crossings"]["across"]]
                if re.search(r"\bat (?:the|its) (?:bottom|top|base)\b", sentence[m.end():m.end() + 30], re.I):
                    for t in things:  # its width where it meets an edge, or at its foot
                        for e in ("bottom", "top"):
                            out += [r["to"] - r["from"] for r in (t.get("meets") or {}).get(e, [])]
                        out += [t["base_wide"]] if "base_wide" in t else []
            elif not where_line and not label and who == "this step" and STRIPE.search(clause):
                out += [c["to"] - c["from"] for c in self.st["crossings"]["down"]]
            return out

        cue, cands, extra = None, [], 0
        edge = r"(?:\s+(?:canvas\s+)?edge)?"
        for pat, name, vals in (
                (r"\s*(?:wide|in width|thick)\b", "wide", lambda: sizes("x")),
                (r"\s*(?:tall|high|in height|deep)\b", "tall", lambda: sizes("y")),
                (r"\s*(?:across|long|in size|round)\b", "size", lambda: sizes("x") + sizes("y")),
                (r"\s*(?:in\s+)?(?:from|off) the left" + edge, "from the left edge", lambda: from_edge("left")),
                (r"\s*(?:in\s+)?(?:from|off) the right" + edge, "from the right edge", lambda: from_edge("right")),
                (r"\s*(?:in\s+)?(?:from|below|under|off|down from) the top" + edge, "from the top edge",
                 lambda: from_edge("top")),
                (r"\s*(?:in\s+)?(?:from|above|off|up from) the bottom" + edge, "from the bottom edge",
                 lambda: from_edge("bottom")),
                (r"\s*apart\b", "apart", lambda: self._gaps(sentence)["apart"]),
                (r"\s*(?:below|under|above|down|up|lower|higher)\b", "down",
                 lambda: sizes("y") + self._gaps(sentence[m.end():])["down"]),
                (r"\s*in\b", "in from an edge", lambda: from_edge("left") + from_edge("right"))):
            hit = re.match(pat, after)
            if hit:
                cue, cands, extra = name, vals(), hit.end()
                break
        if cue is None and re.search(r"\b(?:down|up)\s+(?:only\s+)?(?:about\s+)?$", before):
            cue, cands = "down", sizes("y")
        q = (m.group("q") or "").strip().lower()
        if cue is None:
            ok = None  # a length with no axis, edge or size named: nothing on the sheet to check it against
        elif q in ("under", "less than", "at most", "no more than"):
            ok = any(v <= hi + tol(hi) for v in cands)
        elif q in ("over", "more than", "at least"):
            ok = any(v >= lo - tol(lo) for v in cands)
        else:  # "about 2 in" is read on the half inch; a range anywhere in it
            ok = any(lo - tol(max(lo, v)) <= v <= hi + tol(max(hi, v)) for v in cands)
        what = f"{who}" + (f", its {anchor}" if anchor and cue and cue.startswith("from") else "")
        c = self.claim("length", field, sentence, (m.start(), m.end() + extra), ok,
                       f"{what}: nearest {cue or 'length'} {_fmt(cands, said)}" if cue else "no axis, edge or size named",
                       "" if ok else (f"says {said:g} in" + (f" {cue}" if cue else "") if cue else
                                      "a length with nothing named to measure it against"))
        # a size of the step's own thing (for `agree`): said in a Where line, or of the step's part by name or as
        # "it", not of one piece of it ("each", "at the bottom", "a bell-shaped glass")
        near = sentence[max(0, m.start() - 40):m.end() + 30]
        named_own = any(pid in self.family for _a, _b, pid in self.L.subjects(sentence[:m.start()]))
        own = (field.endswith("(where)") or named_own or re.match(r"\s*(?:it|its|it's)\b", sentence, re.I)) \
            and who == "this step" and not label and not q \
            and not re.search(r"\beach\b|\bat (?:the|its) (?:bottom|top|base)\b", near, re.I)
        c.update(said=round(said, 3), cue=cue, own=bool(own))
        return c

    def _gaps(self, sentence) -> dict[str, list[float]]:
        """Distances between things: the step's area and every other part it touches or the sentence names (the
        gaps across and down, and between their top and bottom sides), and between the step's own marks and
        crossings."""
        named = {pid for _a, _b, pid in self.L.mentions(sentence)}  # only the parts these words name
        a = self.st["area"]
        down, apart = [], []
        if a:
            for o in self.st["others"]:
                if o["part"] in named:
                    p = self.L.parts[o["part"]]
                    down += [v for v in (o["gap"]["down"],) if v is not None]
                    down += [abs(a["top"] - p["top"]), abs(a["bottom"] - p["bottom"]),
                             abs(a["top"] - (self.ch - p["bottom"])), abs((self.ch - a["bottom"]) - p["top"])]
        ms = self.st["marks"]
        for p, q in zip(ms, ms[1:]):  # neighboring marks: middle to middle
            apart += [abs(q["cx"] - p["cx"]), abs(q["cy"] - p["cy"])]
            down += [abs(q["cy"] - p["cy"]), abs(q["top"] - p["top"]), abs(q["bottom"] - p["bottom"])]
        for key in ("across", "down"):
            cs = self.st["crossings"][key]
            for p, q in zip(cs, cs[1:]):
                apart += [q["mid"] - p["mid"], q["from"] - p["to"]]
                if key == "down":
                    down += [q["mid"] - p["mid"]]
        return {"down": down, "apart": apart}

    def _center_x(self) -> float:
        p = self.part or self.st["area"]
        return p["left"] + p["wide"] / 2 if p else self.cw / 2

    def edges(self, sentence, field, m, sides, reach, own_edge=False):
        """A canvas edge reached (or not). In a Where line the thing is the step's area alone. The part's own edge
        (H1 of the PR #182 review) is read only for a pass's words that name it ("its left edge", "the left edge of
        the balloon") or run a stripe "along the (far) left edge" of an object: never for a Where line, and never
        as a second chance for words about the canvas."""
        things, _label, who = self.subject(sentence, m.start())
        if field.endswith("(where)"):
            things = [dict(self.st["area"], what="the step's area")] if self.st["area"] else []
        has = set()
        if who == "this step" and not field.endswith("(where)") and not self.st["first_of_part"] and self.st["marks"]:
            things = [dict(k, what=f"mark {n + 1}") for n, k in enumerate(self.st["marks"])]  # N2: a pass's paint is
            # its marks, not the whole part it's painted on
        for t in things:
            has |= set(t.get("edges") or [])
        if who == "this step" and not field.endswith("(where)"):
            for c in self.st["crossings"]["across"]:
                if c["from"] <= aids.EDGE_SHARE * self.cw:
                    has.add("left")
                if c["to"] >= (1 - aids.EDGE_SHARE) * self.cw:
                    has.add("right")
        ok = all((s in has) == reach for s in sides)
        part_ok = False
        along = re.search(r"\balong\s+(?:the\s+|its\s+)?(?:very\s+|far\s+)?$", sentence[:m.start()], re.I)
        part_words = own_edge or (along and self.part and self.part["kind"] != "area"
                                  and not re.search(r"\bcanvas\b", sentence, re.I))
        if own_edge:
            ok = False if reach else None
        halves = (self.st.get("adds") or {}).get("halves")
        if own_edge and reach and halves and who == "this step" and not self.st["first_of_part"]:
            # "down the left edge of the mast": the paint goes on that side of the part (as `side` reads it)
            share = min(halves[x] for x in sides)
            ok = share >= MOST_SIDE
            return self.claim("edge", field, sentence, m, ok,
                              f"{share:.0%} of the paint it adds is in the {' and '.join(sides)} half of "
                              f"{self.st['part_name'].lower()}",
                              "" if ok else f"says the paint goes along its {' and '.join(sides)} edge")
        clause_start = max([x.end() for x in re.finditer(r"[,;:]|\band\b", sentence[:m.start()])], default=0)
        anc = re.findall(r"\b(?:its|their)\s+(top|bottom|left|right)\b", sentence[clause_start:m.start()].lower())
        if anc and reach and len(sides) == 1 and anc[-1] != sides[0]:
            # "its bottom is at the top edge": that side of the thing, at that edge
            a, e = anc[-1], sides[0]
            vals = []
            for t in things:
                if "wide" in t and (a in ("top", "bottom")) == (e in ("top", "bottom")):
                    v = {"top": t["top"], "bottom": self.ch - t["bottom"], "left": t["left"],
                         "right": self.cw - t["right"]}[a]
                    full = self.ch if e in ("top", "bottom") else self.cw
                    vals.append(v if e in ("top", "left") else full - v)
            ok = bool(vals) and min(vals) <= aids.EDGE_SHARE * (self.ch if e in ("top", "bottom") else self.cw)
            return self.claim("edge", field, sentence, m, ok,
                              f"{who}'s {a} is " + ", ".join(f"{v:.2f}" for v in vals) + f" in from the {e} edge",
                              "" if ok else f"says its {a} is at the {e} edge")
        if (own_edge or not ok) and part_words and reach and who == "this step" and not self.st["first_of_part"] \
                and self.part and not field.endswith("(where)"):
            p = self.part
            pieces = [dict(left=k["left"], right=k["right"], top=k["top"], bottom=k["bottom"]) for k in self.st["marks"]]
            pieces += [dict(left=c["from"], right=self.cw - c["to"], top=None, bottom=None)
                       for c in self.st["crossings"]["across"]]
            for k in pieces:
                for s in sides:
                    size = p["wide"] if s in ("left", "right") else p["tall"]
                    if k[s] is not None and k[s] - p[s] <= PART_SIDE * size:
                        part_ok = True
            ok = part_ok
        why = ""
        if not ok:
            t = next((t for t in things if "wide" in t), None)
            dist = "; ".join(f"its {s} side is {t[s]:g} in from the {s} edge" for s in sides) if t else ""
            why = ("says it " + ("reaches" if reach else "stops short of") + " the " + " and ".join(sides) + " edge"
                   + ("s" if len(sides) > 1 else "") + (f" ({dist})" if dist else ""))
        sheet = f"{who} reaches " + (", ".join(sorted(has)) or "no edge") + (
            "; a mark is at its part's own edge" if part_ok else "")
        return self.claim("edge", field, sentence, m, ok, sheet, why)

    def fraction(self, sentence, field, m):
        s = share_of(m.group("f"))
        d = m.group("dir").lower()
        things, label, who = self.subject(sentence, m.start())
        items = _pick(_items(self.st), label, self._center_x()) if who == "this step" and label else []
        horiz = d in ("in", "across", "along") or "left" in d or "right" in d
        vert = d in ("down", "up", "along") or "top" in d or "bottom" in d
        flip = d == "up" or "right" in d or "bottom" in d
        cands = []
        for t in ([i.get("box") or i for i in items] if items else things):
            p = _positions(t, self.cw, self.ch)
            cands += [v / self.cw for v in p["x"]] if horiz else []
            cands += [v / self.ch for v in p["y"]] if vert else []
        inner = []  # shares inside the part: where its marks and crossings sit, and where it's widest
        if who == "this step":
            if horiz:
                inner += [i["in_part"] for i in items if isinstance(i.get("in_part"), float)]
                inner += [i["box"]["in_part"][0] for i in items if "box" in i and "in_part" in i["box"]]
                if not items:
                    inner += [k["in_part"][0] for k in self.st["marks"] if "in_part" in k]
                    inner += [c["in_part"] for c in self.st["crossings"]["across"]]
            if vert:
                inner += [k["in_part"][1] for k in self.st["marks"] if "in_part" in k]
                inner += [c["in_part"] for c in self.st["crossings"]["down"]]
                inner += [t["widest_down"] for t in things if "widest_down" in t]
        allv = [1 - v for v in cands + inner] if flip else cands + inner
        ok = any(abs(s - v) <= TOLERANCE["share"] for v in allv)
        near = sorted(allv, key=lambda v: abs(v - s))[:3]
        sheet = f"{who}" + (f" (the {label} one)" if items else "") + ": nearest " + \
            ", ".join(f"{v:.2f}" for v in near) + " of the way"
        return self.claim("fraction", field, sentence, m, ok, sheet, "" if ok else f"says {s:.2f} of the way {d}")

    def center(self, sentence, field, m):
        side, q, of = m.group("side").lower(), m.group("q"), (m.group("of") or "").lower()
        things, label, who = self.subject(sentence, m.start())
        of_part = self.L.mentions(of) if of and of not in ("canvas", "painting") else []
        inside = who == "this step" and not self.st["first_of_part"] and self.part and self.part["kind"] != "area"
        if of_part:
            p = self.L.parts[of_part[0][2]]
            c, width, ref = p["left"] + p["wide"] / 2, p["wide"], f"the middle of {p['name'].lower()}"
        elif inside and of not in ("canvas", "painting"):
            c, width, ref = self._center_x(), self.part["wide"], f"the middle of {self.st['part_name'].lower()}"
        else:
            c, width, ref = self.cw / 2, self.cw, "the canvas's middle"
        if inside:  # stripes are read where they cross the part's middle; marks only when nothing crosses it
            pieces = [i for i in _items(self.st) if i["what"].startswith("crossing")] or \
                [i for i in _items(self.st) if i["what"].startswith("mark")]
            picked = _pick(pieces, label, c) if label else \
                ([min(pieces, key=lambda i: abs(i["mid"] - c))] if pieces else [])  # M2: the one nearest the middle
            mids = [i["mid"] for i in picked]
        else:
            mids = [t["cx"] for t in things if "cx" in t]
        ok = any((v < c if side == "left" else v > c) and (not q or abs(v - c) <= JUST * width) for v in mids)
        sheet = f"{ref} is {c:.2f} in from the left edge; {who}'s middles: " + ", ".join(f"{v:.2f}" for v in mids)
        return self.claim("center", field, sentence, m, ok, sheet, "" if ok else f"says {q or ''}{side} of the middle")

    def _resolve_ref(self, ref: str, prev):
        """What a relation's reference names: marks an earlier step put on this part (by their paint's color word,
        with a label to pick one), another part, or the last reference ('its'). None when nothing on the sheet."""
        r = ref.strip().lower()
        if re.match(r"^(?:it|its|them|their|this|that)\b", r):
            return prev
        words = set(re.findall(r"[a-z]+", r))
        for n in reversed(self.st["earlier_steps_of_part"]):
            e = self.L.steps[n]
            colors = {w for p in e["paints"] for w in p["words"]} - GENERIC
            if words & colors and e["crossings"]["across"]:
                lm = re.search(r"\b(?:far\s+)?(left|right|center|centre|middle)\b", r)
                label = lm.group(1) if lm else None
                rows = [e["crossings"]["across"]] + e["crossings"].get("bands", [])
                return {"kind": "marks", "rows": [_pick(x, label, self._center_x()) for x in rows],
                        "items": _pick(e["crossings"]["across"], label, self._center_x()),
                        "what": f"step {n}'s {' '.join(sorted(words & colors))} " + (f"({label} one)" if lm else "marks")}
        ms = self.L.mentions(r)
        if ms:
            pid = ms[0][2]
            return {"kind": "part", "part": pid, "what": self.L.parts[pid]["name"]}
        return None

    def relation(self, sentence, field, m, how, prev):
        if how == "on":
            ref_text, rel, q = m.group("ref") or "its", m.group("side").lower() + " of", "just"
        else:
            ref_text, rel, q = m.group("ref"), m.group("rel").lower(), (m.group("q") or "").strip().lower()
            rel = {"to the left of": "left of", "to the right of": "right of", "beneath": "below"}.get(rel, rel)
            if re.match(r"\s*(?:the\s+)?(?:(?:center|centre|middle)\s*(?:$|of\b)|outlined area\b)", ref_text, re.I):
                return None, prev  # "Inside the outlined area" opens every Where line; center is CENTER's
            if rel in ("left of", "right of") and re.search(r"\b(?:upper|lower|top|bottom|the|its|their)\s+$",
                                                            sentence[:m.start("rel")], re.I):
                return None, prev  # "the upper right of what it lights": a region of a thing, not a relation
        ref = self._resolve_ref(ref_text, prev)
        if rel == "outside" and (ref is None or ref["kind"] == "part"):
            return None, prev  # "the leaves outside the window": out of doors, not a side
        if ref is None:
            return self.claim("relation", field, sentence, m, None, "nothing on the sheet",
                              f"can't find '{ref_text.strip()}' on the sheet"), prev
        near = q in ("just", "right", "directly") or rel in ("beside", "next to")
        if ref["kind"] == "marks":
            pc = self._center_x()
            adj = 0.05 * (self.part["wide"] if self.part else self.cw)
            # M2 of the PR #182 review: each reference stripe is judged by this step's stripe nearest it, on one row:
            # the part's middle row, or else the first band where this step has a stripe near the reference
            found = []
            reach = 0.15 * (self.part["wide"] if self.part else self.cw)
            mine_rows = [self.st["crossings"]["across"]] + self.st["crossings"].get("bands", [])

            def gap_of(cc, r):
                return max(0.0, cc["from"] - r["to"], r["from"] - cc["to"])

            for refs, mine in zip(ref["rows"], mine_rows):
                if not any(gap_of(cc, r) <= reach for r in refs for cc in mine):
                    continue
                for r in refs:
                    cc = min(mine, key=lambda x: (gap_of(x, r), abs(x["mid"] - r["mid"])))
                    if near and gap_of(cc, r) > adj:
                        continue
                    inward = (cc["mid"] > r["mid"]) == (r["mid"] < pc)
                    found.append((cc, {"left of" if cc["mid"] < r["mid"] else "right of", "beside", "next to",
                                       "inside" if inward else "outside"}))
                break
            ok = any(rel in w for _c, w in found)
            sheet = (f"{ref['what']} at " + ", ".join(f"{r['from']:g}-{r['to']:g} in" for r in ref["items"])
                     + "; this step's " + ("touching " if near else "") + "stripes: "
                     + (", ".join(f"{c['from']:g}-{c['to']:g} in ({', '.join(sorted(w - {'beside', 'next to'}))})"
                                  for c, w in found) or "none"))
            return self.claim("relation", field, sentence, m, ok, sheet,
                              "" if ok else f"says {q + ' ' if q else ''}{rel} {ref['what']}"), ref
        _things_, _label, who = self.subject(sentence, m.start())
        p = self.L.parts[ref["part"]]
        if who == "this step":
            if ref["part"] in self.family:
                return None, ref  # the step's own part: a side within its own shape
            fact = next((x for x in self.st["others"] if x["part"] == ref["part"]), None)
            who = "this step's area"
        else:
            fact = self.L.parts[self.subject_part].get("beside", {}).get(ref["part"])
        if fact is None:
            return None, ref  # a part and its own child: one is painted on the other
        words = set(fact["this_is"])
        g = fact["gap"]
        if fact["touches"] or min([v for v in g.values() if v is not None], default=99) <= JUST_GAP * min(self.cw, self.ch):
            words |= {"beside", "next to"}
        if "inside" not in words:
            words.add("outside")
        if near and rel in ("above", "below") and (g["down"] or 0) > JUST_GAP * self.ch:
            words.discard(rel)
        if near and rel in ("left of", "right of") and (g["across"] or 0) > JUST_GAP * self.cw:
            words.discard(rel)
        ok = rel in words
        if {"above", "below", "left of", "right of"} <= set(fact["this_is"]) and rel in ("above", "below", "left of",
                                                                                         "right of"):
            ok = None  # L3: it's all round this thing (the sky round a balloon): a side says nothing checkable
        shown = sorted(words - {"beside", "next to", "outside"})
        sheet = (f"{who} is {', '.join(shown) or 'level with'} {p['name'].lower()}"
                 + (f", {g['down']:g} in apart down" if g["down"] is not None else "")
                 + (f", {g['across']:g} in apart across" if g["across"] is not None else "")
                 + (", touching" if fact["touches"] else ""))
        return self.claim("relation", field, sentence, m, ok, sheet,
                          "" if ok else f"says {q + ' ' if q else ''}{rel} {p['name'].lower()}"), ref

    def position(self, sentence, field, m):
        things, _label, who = self.subject(sentence, m.start())
        want = [x.lower() for x in (m.group("v"), m.group("h"), m.group("s")) if x]
        halves = (self.st.get("adds") or {}).get("halves")
        if who == "this step" and not self.st["first_of_part"] and halves and not m.group("s"):
            # a pass inside its part: "most of them on the upper right" is where in the part its paint goes
            least = SOME_SIDE if re.search(r"\b(?:too|also|some|a few|a little|touch)\b", sentence, re.I) else MOST_SIDE
            have = {x: halves[{"upper": "top", "lower": "bottom"}.get(x, x)] for x in want}
            ok = all(v >= least for v in have.values())
            sheet = ", ".join(f"{v:.0%} of the paint it adds is in the {x} half of {self.st['part_name'].lower()}"
                              for x, v in have.items())
            return self.claim("position", field, sentence, m, ok, sheet,
                              "" if ok else "says " + " ".join(want) + f" (wants {least:.0%} in each)")

        def fits(t):
            return all({"upper": t["cy"] < self.ch / 2, "top": t["cy"] < self.ch / 2, "lower": t["cy"] > self.ch / 2,
                        "bottom": t["cy"] > self.ch / 2, "left": t["cx"] < self.cw / 2,
                        "right": t["cx"] > self.cw / 2}[x] for x in want)

        cand = [t for t in things if "cx" in t]
        ok = any(fits(t) for t in cand)
        sheet = f"{who}: " + "; ".join(f"{t['what']} centered {t['cx']:g} in from the left, {t['cy']:g} in from the top"
                                       for t in cand[:3])
        return self.claim("position", field, sentence, m, ok, sheet, "" if ok else "says " + " ".join(want))

    def side_of(self, sentence, field, m):
        """Where a pass adds its paint inside its own part: 'the olive goes on the left side'. None when the words
        aren't that claim (a side within a thing's own shape on its first step, another thing's side, or what's
        left showing)."""
        ref = (m.group("owner") or m.group("of") or "").lower()
        if self.st["first_of_part"] or not self.part or not self.st.get("adds"):
            return None
        if ref and ref not in ("its", "their") and not any(pid in self.family for _a, _b, pid in self.L.mentions(ref)):
            return None
        start = max([x.end() for x in re.finditer(r"[,;:]", sentence[:m.start()])], default=0)
        if LEAVE.search(sentence[start:m.end() + 30]):
            return None
        side = m.group("side").lower()
        half = {"upper": "top", "lower": "bottom"}.get(side, side)
        share = self.st["adds"].get("halves", {}).get(half)
        if share is None:
            return None
        some = re.search(r"\b(?:too|also|some|a few|a little|touch)\b", sentence, re.I)
        least = SOME_SIDE if some else MOST_SIDE
        ok = share >= least
        sheet = f"{share:.0%} of the paint it adds is in the {half} half of {self.st['part_name'].lower()}"
        return self.claim("side", field, sentence, m, ok, sheet,
                          "" if ok else f"says the paint goes on the {side} (wants {least:.0%} there)")


def _fields(t: dict) -> list[tuple[str, str]]:
    out = [("summary", t.get("summary") or ""), ("tip", t.get("tip") or "")]
    out += [(f"line {k + 1} ({x.get('kind')})", x.get("text") or "") for k, x in enumerate(t.get("lines") or [])]
    out += [(f"paint note {k + 1}", x) for k, x in enumerate(t.get("paint_notes") or [])]
    return out


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(\"'])", text.strip()) if s.strip()]


def agree(claims: list[dict]) -> list[dict]:
    """Sizes of the step's own thing that disagree within one step: every 'wide' (or 'tall') length said of it, in
    any line or the tip, must be within tolerance of the others (#159: the Where line's 3 in wide, the tip's 2 1/2)."""
    out = []
    for cue in ("wide", "tall"):
        said = [c for c in claims if c["kind"] == "length" and c.get("cue") == cue and c.get("own")]
        if len(said) < 2:
            continue
        lo, hi = min(said, key=lambda c: c["said"]), max(said, key=lambda c: c["said"])
        if hi["said"] - lo["said"] > tol(hi["said"]):
            out.append({"step": lo["step"], "id": lo["id"], "field": f"{lo['field']} and {hi['field']}", "kind": "agree",
                        "words": f"{lo['words']} / {hi['words']}", "sentence": f"{lo['sentence']} / {hi['sentence']}",
                        "ok": False, "sheet": f"one says {lo['said']:g} in {cue}, the other {hi['said']:g} in",
                        "why": "two sizes of the same thing disagree within the step", "span": (0, 0)})
    return out


def check_text(sheet: dict, text: dict, strict: bool = False, only: set[str] | None = None) -> dict:
    """Every claim in text.json's steps, checked against the lesson's sheet. `only` limits the fields read to those
    whose first word is in it ({"tip", "summary"}, or {"line"}). A claim fails when no fact on the sheet supports it;
    one whose reference isn't on the sheet is unresolved, and fails too when `strict`. Returns {"claims",
    "failures", "unresolved", "not_claims": {why: count}}."""
    lesson = Lesson(sheet)
    by_id = {t.get("stage_id"): t for t in text.get("steps") or []}
    claims, not_claims, other = [], {}, []
    for st in sheet["steps"]:
        r = Reader(lesson, st)
        mine = []
        for field, words in _fields(by_id.get(st["id"]) or {}):
            if only and field.split()[0] not in only:
                continue
            for s in sentences(words):
                got, rest = r.read(s, field)
                mine += got
                for why, w in rest:
                    not_claims[why] = not_claims.get(why, 0) + 1
                    if why == "other":
                        other.append({"step": st["n"], "field": field, "word": w, "sentence": s})
        claims += mine + agree(mine)
    for c in claims:
        c.pop("span", None)
    # not a claim in the words, but a fact on the sheet the words can't fix (#159 step 13): a pass in the paint of
    # the coat under it adds nothing the painter can see
    paint = [{"step": st["n"], "id": st["id"], "paints": st["same_paint_as_under"],
              "why": f"step {st['n']} lays {', '.join(st['same_paint_as_under'])} over the same paint from step "
                     f"{st['earlier_steps_of_part'][-1]}: its marks won't show"}
             for st in sheet["steps"] if st.get("same_paint_as_under")]
    return {"claims": claims, "paint_faults": paint,
            "failures": [c for c in claims if c["ok"] is False or (strict and c["ok"] is None)],
            "unresolved": [c for c in claims if c["ok"] is None], "not_claims": not_claims, "other_words": other}


def say(c: dict) -> str:
    """One failure as a line: where, which words, what's wrong, and what the sheet says."""
    return (f"step {c['step']} ({c['id']}), {c['field']}: \"{c['words']}\" {c['why'] or 'unresolved'}; "
            f"sheet: {c['sheet']}")


# --- Planted faults: how many the checker catches (the review of PR #182) ---
#
# Every measured Where line is right, so a Where line with one fault put in is wrong by construction (bar a thing
# that's symmetric about the canvas's middle). A tip with one put in is wrong as long as the tip was right to start.
# A mutant is caught when the sentence has more failed claims than it had before.

SWAP_LR = {"left": "right", "right": "left"}
SWAP_UD = {"top": "bottom", "bottom": "top", "upper": "lower", "lower": "upper", "above": "below", "below": "above"}
SWAP_IO = {"inside": "outside", "outside": "inside"}
SHIFTS = {"length +1 in": 1.0, "length -1 in": -1.0, "length +1/2 in": 0.5, "length -1/2 in": -0.5}


def ruler(v: float) -> str:
    """A length as a Where line says it, to the quarter inch: '1 3/4', '3'."""
    q = round(v * 4) / 4
    whole, frac = int(q), q - int(q)
    f = {0.25: "1/4", 0.5: "1/2", 0.75: "3/4"}.get(round(frac, 2), "")
    return f"{whole} {f}".strip() if whole else (f or "0")


PAIRS = re.compile(r"\b(?:top|bottom|left|right|side|up|down)\s+(?:to|and)\s+(?:top|bottom|left|right|side|up|down)\b",
                   re.I)


def _swap(text: str, table: dict[str, str], only: list[tuple[int, int]] | None = None) -> str:
    """Each word of the table swapped, except inside "top to bottom" and the like (the same reach either way)."""
    pat = re.compile(r"\b(" + "|".join(table) + r")\b", re.I)
    keep = [x.span() for x in PAIRS.finditer(text)]

    def sub(x):
        if only is not None and not any(a <= x.start() < b for a, b in only):
            return x.group(0)
        if any(a <= x.start() < b for a, b in keep):
            return x.group(0)
        w = table[x.group(1).lower()]
        return w.capitalize() if x.group(1)[0].isupper() else w
    return pat.sub(sub, text)


def mutants(sentence: str, claims: list[dict]) -> list[tuple[str, str]]:
    """(kind, sentence with one fault put in) for a sentence and its claims (Reader.read's, with their spans)."""
    out = []
    for m in LENGTH.finditer(sentence):  # every length moved
        if BRUSH.match(sentence[m.end():]) or m.group("num2"):
            continue
        said = inches(m)
        for kind, d in SHIFTS.items():
            nv = said + d
            if nv >= 0.25:
                end = m.end("and") if m.group("and") else m.end("num")
                out.append((kind, sentence[:m.start("num")] + ruler(nv) + sentence[end:]))
    kinds = {c["kind"] for c in claims}
    if any(re.search(r"\b(?:left|right)\b", c["words"], re.I) for c in claims
           if c["kind"] in ("center", "relation", "position", "side", "edge", "length")):
        out.append(("left/right swapped", _swap(sentence, SWAP_LR)))
    if any(re.search(r"\b(?:top|bottom|upper|lower|above|below)\b", c["words"], re.I) for c in claims
           if c["kind"] in ("relation", "position", "side", "edge", "fraction", "length")):
        out.append(("up/down swapped", _swap(sentence, SWAP_UD)))
    spans = [c["span"] for c in claims if c["kind"] in ("center", "relation")]
    if spans and re.search(r"\b(?:left|right|inside|outside)\b", " ".join(sentence[a:b] for a, b in spans), re.I):
        out.append(("stripe or side mirrored", _swap(_swap(sentence, SWAP_IO, spans), SWAP_LR, spans)))
    if "edge" in kinds:  # an edge reached moved off it, and a distance from an edge moved onto it
        moved = re.sub(r"\bis at the (left|right|top|bottom) edge\b", r"is about 1 1/2 in from the \1 edge", sentence,
                       count=1)
        if moved != sentence:
            out.append(("edge moved", moved))
    hit = re.search(r"\bis about (" + NUM + r") in from the (left|right|top|bottom) edge\b", sentence)
    if hit and number(hit.group(1)) >= 1:
        out.append(("edge moved", sentence[:hit.start()] + f"is at the {hit.group(2)} edge" + sentence[hit.end():]))
    return out


def mutate(sheet: dict, text: dict, misses: int = 8) -> dict:
    """The catch rate for each kind of planted fault, in the Where lines and in the other words, beside the
    false-alarm count on the words as they are: {"where"|"written": {kind: [planted, caught]}, "missed": {kind:
    [examples]}, "base": {"claims", "flags"}}."""
    lesson = Lesson(sheet)
    by_id = {t.get("stage_id"): t for t in text.get("steps") or []}
    out = {"where": {}, "written": {}, "missed": {}, "base": {"claims": 0, "flags": 0}}
    for st in sheet["steps"]:
        r = Reader(lesson, st)
        for field, words in _fields(by_id.get(st["id"]) or {}):
            group = "where" if field.endswith("(where)") else "written"
            for s in sentences(words):
                base, _rest = r.read(s, field)
                bad = sum(c["ok"] is False for c in base)
                out["base"]["claims"] += len(base)
                out["base"]["flags"] += bad
                if bad:
                    continue  # a fault is planted only in words the checker accepts as they are
                for kind, s2 in mutants(s, base):
                    if s2 == s:
                        continue
                    got, _rest = r.read(s2, field)
                    caught = sum(c["ok"] is False for c in got) > bad
                    tally = out[group].setdefault(kind, [0, 0])
                    tally[0] += 1
                    tally[1] += caught
                    if not caught and len(out["missed"].setdefault(f"{group}: {kind}", [])) < misses:
                        out["missed"][f"{group}: {kind}"].append(f"step {st['n']} ({st['id']}), {field}: {s2}")
    return out


def add_up(results: list[dict]) -> dict:
    total = {"where": {}, "written": {}, "base": {"claims": 0, "flags": 0}}
    for r in results:
        for g in ("where", "written"):
            for k, (n, c) in r[g].items():
                t = total[g].setdefault(k, [0, 0])
                t[0] += n
                t[1] += c
        for k in ("claims", "flags"):
            total["base"][k] += r["base"][k]
    return total


# the sealed POC 1.12.1 lessons the write-up ran on (L5: by name; 153316 is 1.12.0 and doesn't rebuild to its pictures)
SEALED = [ROOT / "output" / n for n in ("balloon-lavender_skill_20261116-171639", "chickadee_skill_20261116-191619",
                                        "red-sailboat_skill_20261116-191627", "sleeping-cat_skill_20261116-191623",
                                        "snow-lantern_skill_20261116-191628")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("sheet")
    a.add_argument("lesson", type=Path)
    a.add_argument("--out", type=Path)
    b = sub.add_parser("check")
    b.add_argument("lesson", type=Path)
    b.add_argument("--strict", action="store_true")
    c = sub.add_parser("sealed")
    c.add_argument("lessons", type=Path, nargs="*")
    c.add_argument("--out", type=Path, help="write every claim of every lesson here, as JSON")
    d = sub.add_parser("mutate", help="plant faults in each lesson's words and count how many the checker catches")
    d.add_argument("lessons", type=Path, nargs="*")
    args = ap.parse_args(argv)
    if args.cmd == "mutate":
        results = []
        for lesson in args.lessons or SEALED:
            sheet, _plan = lesson_sheet(lesson)
            r = mutate(sheet, json.loads((Path(lesson) / "text.json").read_text(encoding="utf-8")))
            results.append(r)
            print(Path(lesson).name, json.dumps({k: r[k] for k in ("where", "written", "base")}))
            for k, v in r["missed"].items():
                for e in v[:3]:
                    print(f"  missed {k}: {e[:200]}")
        total = add_up(results)
        for g in ("where", "written"):
            for k, (n, c) in sorted(total[g].items()):
                print(f"{g:8s} {k:24s} {c}/{n} caught ({c / max(n, 1):.0%})")
        print(f"unmutated: {total['base']['flags']} flags in {total['base']['claims']} claims")
        return 0
    if args.cmd == "sheet":
        sheet, _plan = lesson_sheet(args.lesson)
        text = json.dumps(sheet, indent=1)
        args.out.write_text(text, encoding="utf-8") if args.out else print(text)
        return 0
    lessons = [args.lesson] if args.cmd == "check" else (args.lessons or SEALED)
    everything = {}
    for lesson in lessons:
        sheet, _plan = lesson_sheet(lesson)
        text = json.loads((Path(lesson) / "text.json").read_text(encoding="utf-8"))
        r = check_text(sheet, text, strict=getattr(args, "strict", False))
        everything[Path(lesson).name] = r
        by_kind = {}
        for x in r["claims"]:
            k = by_kind.setdefault(x["kind"], [0, 0, 0])
            k[0 if x["ok"] else 1 if x["ok"] is False else 2] += 1
        print(f"{Path(lesson).name}: {len(r['claims'])} claims, {len(r['failures'])} failed, "
              f"{len(r['unresolved'])} unresolved; by kind (passed, failed, unresolved): {by_kind}; "
              f"not claims: {r['not_claims']}")
        for x in r["failures"]:
            print("  FAIL", say(x))
        for x in r["unresolved"]:
            print("  UNRESOLVED", say(x))
        for x in r["paint_faults"]:
            print("  PAINT", x["why"])
    if getattr(args, "out", None):
        args.out.write_text(json.dumps(everything, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
