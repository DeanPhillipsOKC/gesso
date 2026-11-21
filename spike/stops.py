"""Where a covered layer stops (pipeline v4, docs/design/pipeline-v4.md, sections 2 and 5).

    frame(shape, canvas_box, canvas) -> the canvas inside the frame (rows, columns) and its pixels an inch
    work_out(plan, us, masks, owner, fr)    -> how hidden each unit's paint is, and the rows build.json keeps
    lay(pictures, masks, unit_of, stops)     -> the step pictures with each stopped layer ending at its line

A step picture shows a whole layer, the part a later thing covers too. Under the owner's rule (`line-1-next`,
adopted 2026-11-21, docs/decisions.md; spike #289, docs/spikes/cover-margin.md) a layer that the next stage covers
from the canvas's bottom edge up stops at a loose line about an inch past the cover's top, and the canvas below it
stays bare until the cover is painted. This is that rule, moved out of spike/experiments/cover_margin.py with the
spike's numbers unchanged; the variants that lost stay there as the record.

**The cover map.** A unit lays paint where its steps' masks are (the first laying). After unit u, a pixel is
covered later when its owner at the finish is a later unit that shares no thing with the unit on top now. Of that,
a unit stops only where the cover is from a later stage (`later_stage`), the next paint laid there from a later
stage is in the stage right after the unit's (`next_stage_paints`), and the cover runs up from the bottom edge at
least LINE_RUN inches up its column (`stop_line`).

**The line.** In each column the layer is painted down to the deepest point it is needed within LINE_REACH inches to
either side, smoothed, then MARGIN further with a small wobble and a ragged fade. Below it is bare canvas. Thin
things and islands stop nothing: a column needs a run from the bottom edge, and its neighbours' depth decides.

**A step changes only where it lays paint** (`lay`). Inside a step's mask the picture takes its unit's line;
everywhere else it keeps what the step before showed. One rule beside the spike's (the design's guess, section 5):
canvas left bare by a stopped layer is uncovered only by a unit that shares no thing with that layer, so a glow
added to the sky after the hills doesn't lay the sky's covered part back onto bare canvas.
"""

from __future__ import annotations

import cv2
import numpy as np

import from_finish as ff

RULE = "line-1-next"
MARGIN = 1.0  # inches past the cover's top (the spike's `margin`)
LINE_REACH = 2.0  # inches: a layer goes as deep as it is needed anywhere this far to each side
LINE_RUN = 1.5  # inches: a cover reaching the bottom edge must run at least this far up a column to stop a layer
RAMP = 0.15  # inches: the line's edge fades in over this
WOBBLE = 0.35  # the margin is longer and shorter along the line by this share of itself
WOBBLE_SIZE = 0.8  # inches: how far along the line the margin takes to change
RAG = 0.6  # the ragged fade: this share of RAMP, along the strokes' way
SEED = 289
NUMBERS = {"margin_in": MARGIN, "reach_in": LINE_REACH, "run_in": LINE_RUN, "ramp_in": RAMP, "wobble": WOBBLE,
           "wobble_in": WOBBLE_SIZE, "rag": RAG, "seed": SEED}
HIDDEN = 0.5  # a pixel more hidden than this is bare canvas in the picture
SHOWING = 0.5  # inches: a stopped unit's line this close below what the finish shows of it is a note (section 5)


# ---------------------------------------------------------------------------------------------------- the frame
def frame(shape: tuple, canvas_box: list | None, canvas: dict) -> dict:
    """The canvas inside a frame of `shape` (canvas.json's canvas_box, fractions of the frame; None is all of it):
    {"crop": (y0, y1, x0, x1), "ppi": pixels an inch, "canvas_in": (w, h)}."""
    h, w = shape[:2]
    x0, y0, x1, y1 = canvas_box or (0.0, 0.0, 1.0, 1.0)
    crop = (round(y0 * h), round(y1 * h), round(x0 * w), round(x1 * w))
    return {"crop": crop, "ppi": (crop[3] - crop[2]) / float(canvas["w_in"]),
            "canvas_in": (float(canvas["w_in"]), float(canvas["h_in"]))}


# ------------------------------------------------------------------------------------------------ the cover map
def laid_by_unit(us: list[dict], masks: list[np.ndarray]) -> list[np.ndarray]:
    """Where each unit lays paint: its steps' masks together."""
    return [np.any([masks[i] for i in u["steps"]], axis=0) for u in us]


def last_laid(laid: list[np.ndarray]) -> np.ndarray:
    """Which unit lays the last paint on each pixel (-1: none does)."""
    owner = np.full(laid[0].shape, -1, np.int32)
    for n, lay in enumerate(laid):
        owner[lay] = n
    return owner


def owner_map(owner: np.ndarray, laid: list[np.ndarray]) -> np.ndarray:
    """Which unit owns each pixel at the finish: `owner` (steps3.owner_from: the last unit whose core holds it),
    except where that unit lays no paint on the pixel; there, the last unit that does. A pixel hidden for its owner
    must be shown again by one of its owner's steps, or the last picture isn't the finish (the spike's correction)."""
    png = owner.astype(np.int32)
    stack = np.stack(laid)
    ys, xs = np.indices(png.shape)
    ok = stack[np.clip(png, 0, len(laid) - 1), ys, xs] & (png < len(laid)) & (png >= 0)
    return np.where(ok, png, last_laid(laid))


def tops(laid: list[np.ndarray]) -> list[np.ndarray]:
    """After each unit, which unit is on top at each pixel (-1: bare canvas)."""
    top = np.full(laid[0].shape, -1, np.int32)
    out = []
    for n, lay in enumerate(laid):
        top = top.copy()
        top[lay] = n
        out.append(top)
    return out


def share_things(us: list[dict]) -> np.ndarray:
    k = len(us)
    s = np.zeros((k, k), bool)
    for a in range(k):
        for b in range(k):
            s[a, b] = bool(set(us[a]["things"]) & set(us[b]["things"]))
    return s


def stage_of(plan: dict, us: list[dict]) -> list[int]:
    stages = [x.get("id") for x in plan["stages"]]
    return [stages.index(u["stage"]) for u in us]


def later_stage(at: list[int], owner: np.ndarray, u: int) -> np.ndarray:
    """Where the owner at the finish is a unit of a later stage than unit u."""
    return np.array(at + [-1])[owner] > at[u]


def next_stage_paints(at: list[int], laid: list[np.ndarray], u: int) -> np.ndarray:
    """Where the next unit after u to lay paint from a later stage is in the stage right after u's, so bare canvas
    never waits behind finished paint (the birch grove's mist doesn't stop for undergrowth four steps away). Work of
    u's own stage is one passage with it (the cow's clouds on its sky)."""
    nxt = np.full(laid[0].shape, -1, np.int32)
    for k in range(len(laid) - 1, u, -1):
        if at[k] > at[u]:
            nxt[laid[k]] = k
    return np.array(at + [-1])[nxt] == at[u] + 1


def covered(us: list[dict], laid: list[np.ndarray], owner: np.ndarray) -> list[np.ndarray]:
    """After each unit u, where a later unit that shares no thing with the one on top covers it. `owner` is
    `owner_map`'s."""
    same = share_things(us)
    out = []
    for u, top in enumerate(tops(laid)):
        ok = (top >= 0) & (owner > u)
        c = np.zeros(owner.shape, bool)
        c[ok] = ~same[top[ok], owner[ok]]
        out.append(c)
    return out


# ------------------------------------------------------------------------------------------------------ the line
def _noise(shape: tuple, sigma: tuple[float, float], seed: int) -> np.ndarray:
    """Smooth noise in about -1..1, blurred sigma (along y, along x) pixels."""
    rng = np.random.default_rng(seed)
    n = cv2.GaussianBlur(rng.standard_normal(shape).astype(np.float32), (0, 0), sigmaX=sigma[1], sigmaY=sigma[0])
    return n / (3 * n.std() + 1e-6)


def bottom_run(cov: np.ndarray, fr: dict) -> tuple[np.ndarray, np.ndarray]:
    """(each pixel of the canvas in a column's covered run that reaches the bottom edge, the row each run starts at:
    the canvas's height where there is none, or it is shorter than LINE_RUN inches)."""
    y0, y1, x0, x1 = fr["crop"]
    c = cov[y0:y1, x0:x1]
    h, w = c.shape
    run = np.zeros((h, w), bool)
    run[-1] = c[-1]
    for y in range(h - 2, -1, -1):
        run[y] = run[y + 1] & c[y]
    top = np.where(run.any(0), run.argmax(0), h).astype(np.float32)
    top[(h - top) < LINE_RUN * fr["ppi"]] = h
    return run, top


def stop_line(cov: np.ndarray, fr: dict, margin: float = MARGIN) -> tuple[np.ndarray, dict | None]:
    """(how hidden each pixel is: 0 shows the layer, 1 is bare canvas; the line, or None when nothing stops). Only a
    cover that runs from the bottom edge of the canvas up counts. In each column, the layer is painted down to the
    deepest point it is needed within LINE_REACH inches to either side, then `margin` further, so its lower edge is a
    loose line past the valleys of what covers it, not the cover's outline (the owner's ask on #289: "extend a bit
    past where they were needed for large areas that would be covered").

    The line, a row a column of the canvas: `first`, where the bare canvas starts (as the picture shows it, past the
    fade); `top`, where the cover's run starts (the canvas's height where nothing covers it from the bottom edge);
    and `columns`, where it stops."""
    y0, y1, x0, x1 = fr["crop"]
    ppi = fr["ppi"]
    run, top = bottom_run(cov, fr)
    h, w = run.shape
    reach = max(1, int(LINE_REACH * ppi))
    pad = np.pad(top, reach, mode="edge")
    deep = np.array([pad[i:i + 2 * reach + 1].max() for i in range(w)], np.float32)  # needed this deep nearby
    smooth = cv2.GaussianBlur(deep[None], (0, 0), sigmaX=reach / 2)[0]
    smooth = np.maximum(smooth, top)  # smoothing never cuts into where the layer itself is needed
    wob = _noise((1, w), (1, WOBBLE_SIZE * ppi), SEED)[0] * 3  # about -1..1 along the edge
    stop = smooth + margin * ppi * (1 + WOBBLE * np.clip(wob, -1, 1))
    rag = _noise((h, w), (0.02 * ppi, 0.12 * ppi), SEED + 1)
    ys = np.arange(h, dtype=np.float32)[:, None]
    hid = np.clip((ys - stop[None]) / (RAMP * ppi) + RAG * rag * 1.6, 0, 1) * run
    out = np.zeros(cov.shape, np.float32)
    out[y0:y1, x0:x1] = hid
    bare = hid > HIDDEN
    cols = bare.any(0)
    return out, ({"first": np.where(cols, bare.argmax(0), h), "top": top, "columns": cols} if cols.any() else None)


def _in(px: float, ppi: float) -> float:
    return round(float(px) / ppi, 3)


def line_row(line: dict, fr: dict) -> dict:
    """A stopped unit's line in inches from the canvas's top edge, where the bare canvas starts: its highest point,
    most of it (the median), its lowest point, at the left edge and at the right edge (None where it doesn't reach
    that edge), and how far past the cover's top it is (most of it, the least and the most)."""
    ppi, cols = fr["ppi"], line["columns"]
    s = line["first"][cols]
    past = (line["first"] - line["top"])[cols]
    return {"highest": _in(s.min(), ppi), "most": _in(np.median(s), ppi), "lowest": _in(s.max(), ppi),
            "left": _in(line["first"][0], ppi) if cols[0] else None,
            "right": _in(line["first"][-1], ppi) if cols[-1] else None,
            "past_cover": {"most": _in(np.median(past), ppi), "least": _in(past.min(), ppi),
                           "greatest": _in(past.max(), ppi)}}


def _runs_up(cov: np.ndarray, fr: dict) -> bool:
    return bool((bottom_run(cov, fr)[1] < cov[fr["crop"][0]:fr["crop"][1]].shape[0]).any())


def work_out(plan: dict, us: list[dict], masks: list[np.ndarray], owner: np.ndarray, fr: dict) -> dict:
    """How hidden each unit's paint is (`want`, a map a unit), and what build.json keeps of it: a row a stopped unit
    (`stopped`) and a row a unit covered from the bottom edge that doesn't stop, with why (`not_stopped`). `masks`
    are the first laying's (where each step lays paint); `owner` is steps3.owner_from's."""
    laid = laid_by_unit(us, masks)
    own = owner_map(owner, laid)
    at = stage_of(plan, us)
    cov_all = covered(us, laid, own)
    want, not_stopped, lines = [], [], []
    for u, c in enumerate(cov_all):
        later = c & later_stage(at, own, u)
        cov = later & next_stage_paints(at, laid, u)
        hid, line = stop_line(cov, fr)
        want.append(hid)
        lines.append(line)
        if line is None:
            if _runs_up(c, fr):
                why = ("the cover is in its own stage" if not _runs_up(later, fr) else
                       "the cover is more than one stage on")
                not_stopped.append({"unit": u, "id": us[u]["id"], "steps": [i + 1 for i in us[u]["steps"]],
                                    "why": why})
    return {"want": want, "lines": lines, "owner": own, "laid": laid, "not_stopped": not_stopped}


def lay(pictures: list[np.ndarray], masks: list[np.ndarray], us: list[dict], want: list[np.ndarray]) -> dict:
    """The second laying: {"pictures", "hidden" (how hidden each pixel is after each step), "by" (after each step,
    the unit whose line left each pixel bare, -1 none)}. Inside a step's mask the picture takes its unit's line,
    bare canvas below it; everywhere else it keeps what the step before showed. Canvas a stopped layer left bare is
    uncovered only by a unit that shares no thing with that layer."""
    unit_of = {i: n for n, u in enumerate(us) for i in u["steps"]}
    same = share_things(us)
    hide = np.zeros(masks[0].shape, np.float32)
    by = np.full(masks[0].shape, -1, np.int32)
    fill = np.empty(pictures[0].shape, np.float32)
    fill[:] = ff.CANVAS
    out, hidden, bys = [], [], []
    for i, b in enumerate(pictures):
        u = unit_of[i]
        where = masks[i]
        hide, by = hide.copy(), by.copy()
        new, old, was = want[u][where], hide[where], by[where]
        keep = (was >= 0) & same[u, np.maximum(was, 0)] & (old > new)  # the stopped layer's own thing comes back
        hide[where] = np.where(keep, old, new)
        by[where] = np.where(keep, was, np.where(new > 0, u, -1))
        a = hide[..., None]
        out.append(np.clip(b.astype(np.float32) * (1 - a) + fill * a, 0, 255).astype(np.uint8))
        hidden.append(hide)
        bys.append(by)
    return {"pictures": out, "hidden": hidden, "by": bys}


def report(plan: dict, us: list[dict], masks: list[np.ndarray], worked: dict, laid2: dict, fr: dict) -> dict:
    """What build.json keeps (design section 5): the rule's name and numbers, a row a stopped unit (its steps, the
    unit and first step that covers it, its line), the units covered from the bottom edge that don't stop and why,
    each step's `spared` (the share of its paint not shown) and the lesson's `spared_canvas`, and the notes."""
    steps_of = {n: [i + 1 for i in u["steps"]] for n, u in enumerate(us)}
    hidden = laid2["hidden"]
    spared = []
    for i, m in enumerate(masks):
        n = int(m.sum())
        h = m & (hidden[i] > HIDDEN)
        spared.append({"spared": round(float(h.sum() / max(n, 1)), 3), "spared_canvas": round(float(h.mean()), 4)})
    rows, notes = [], []
    at = stage_of(plan, us)
    own = worked["owner"]
    y0, y1, x0, x1 = fr["crop"]
    for u, line in enumerate(worked["lines"]):
        if line is None:
            continue
        if not any(spared[i]["spared"] > 0 for i in us[u]["steps"]):
            continue  # its line runs where it lays no paint
        nxt = [k for k in range(u + 1, len(us)) if at[k] == at[u] + 1
               and (worked["laid"][k] & (worked["want"][u] > HIDDEN)).any()]
        by = nxt[0] if nxt else None
        rows.append({"unit": u, "id": us[u]["id"], "steps": steps_of[u],
                     "covered_by": None if by is None else {"unit": by, "id": us[by]["id"],
                                                            "step": us[by]["steps"][0] + 1},
                     "line": line_row(line, fr)})
        # the finish shows the unit above its line: the line must leave SHOWING inches below the lowest of it
        last = us[u]["steps"][-1]
        shown = (own == u)[y0:y1, x0:x1] & ~(hidden[last] > HIDDEN)[y0:y1, x0:x1]
        hid = (hidden[last] > HIDDEN)[y0:y1, x0:x1] & worked["laid"][u][y0:y1, x0:x1]
        hh = shown.shape[0]
        low = np.where(shown.any(0), hh - 1 - shown[::-1].argmax(0), -1)
        first_hid = np.where(hid.any(0), hid.argmax(0), hh)
        both = (low >= 0) & (first_hid < hh)
        if both.any():
            gap = float((first_hid[both] - low[both]).min()) / fr["ppi"]
            if gap < SHOWING:
                notes.append(f"{us[u]['id']}: its line comes {gap:.2f} in below the lowest of it the finish shows, "
                             f"under {SHOWING:g} in. The rule's arithmetic can't do that: check the chain's masks.")
    total = round(sum(s["spared_canvas"] for s in spared), 3)
    return {"stops": {"rule": RULE, "numbers": NUMBERS, "stopped": rows, "not_stopped": worked["not_stopped"]},
            "spared": spared, "spared_canvas": total, "notes": notes}
