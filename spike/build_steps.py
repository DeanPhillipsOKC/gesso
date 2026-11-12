"""Every step picture cut from the one finished painting (pipeline v2, docs/design/pipeline-v2.md section 8).

    build(finish, plan, owner, background=None) -> (one picture per step, one row of numbers per step)

No renders. Each step paints inside one part's outline (spike/outline.py), so a step can't move, reshape, or
recolor anything else, and the last picture is the finish. That removes what the image reviews, the redos, and
lock-steps existed to repair.

How a step is drawn, by its `show`:
- "flat":  the part as flat color in the step's paints (a base coat or block-in), no texture;
- "pass":  the finish shows through wherever its color is nearest one of the step's paints, over the flat coat;
- "full" or "blend": the part exactly as the finish has it, in one step.
A part's last step always shows everything of the part that's left.

Painting goes back to front, so a part is painted straight through where things in front of it will go:
- behind an object (a bird, a boat, a branch) the picture comes from `background`: the finish with the objects
  taken out. Without one given, it's filled in from around each object (free, and rougher);
- a part's own paint also runs a little under the edge of the next part, or as far as its `covers` boxes say;
- under a part's own children (clouds on a sky, a cap on a bird) the parent shows its own paint carried across.
"""

from __future__ import annotations

import cv2
import numpy as np

import from_finish as ff
import outline as ol

UNDERLAP = 0.012  # how far a part's paint runs under the next part's edge, as a share of the long side
HALO = 0.008  # how far past an object's outline its edge is cleared from the background, as a share of the long side
CLOSE = 0.03  # gaps this wide in an object (a bird's feet across a branch) are painted straight through
NEEDS_BACKGROUND = 0.15  # objects covering more of the picture than this want a background picture, not a fill
ROWS = 0.9  # how much of a wide part's carried-on paint follows its rows (bands) rather than its edges
TEXTURE = 0.7  # how much brush texture carried-on paint borrows from beside the gap
FEATHER = 0.8  # pixels of softening at a painted edge, inward only
SMOOTH = 5  # median filter on which-paint-is-nearest, so a pass arrives as marks, not as single pixels
BACK = ("area", "marks")


def flat_steps(plan: dict) -> list[dict]:
    """The plan's steps in order, each with its stage's id and name."""
    return [dict(s, stage=st["id"], stage_name=st.get("name", st["id"])) for st in plan["stages"] for s in st["steps"]]


def _roots(parts: list[dict]) -> list[int]:
    index = {p["id"]: i for i, p in enumerate(parts)}
    out = []
    for i, p in enumerate(parts):
        while p.get("parent"):
            i = index[p["parent"]]
            p = parts[i]
        out.append(i)
    return out


def _family(parts: list[dict], k: int) -> list[int]:
    """Part k and everything painted on it (its children, their children)."""
    ids, out = {parts[k]["id"]}, [k]
    for i, p in enumerate(parts):
        if p.get("parent") in ids:
            ids.add(p["id"])
            out.append(i)
    return out


def back_parts(parts: list[dict]) -> np.ndarray:
    """True for the parts behind every object: those whose root comes before the first object or thin part.
    From the first object on, parts sit in front, and are cut from the finish itself."""
    roots = _roots(parts)
    first = next((i for i, p in enumerate(parts) if not p.get("parent") and p["kind"] not in BACK), len(parts))
    return np.array([r < first for r in roots])


def halo(mask: np.ndarray) -> np.ndarray:
    """The mask grown by HALO: an object's painted edge and soft rim."""
    r = max(2, int(HALO * max(mask.shape)))
    return cv2.dilate(mask.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0


def make_background(finish: np.ndarray, front: np.ndarray, given: np.ndarray | None) -> np.ndarray:
    """The finish with everything in `front` (objects and thin parts) taken out. `given` is a picture of that
    (a plate render): only its pixels inside `front` are used, so it can't change anything else."""
    if not front.any():
        return finish.copy()
    grown = halo(front)  # the object's painted edge and its soft rim go too
    out = finish.copy()
    if given is not None:
        if given.shape[:2] != finish.shape[:2]:
            given = cv2.resize(given, (finish.shape[1], finish.shape[0]), interpolation=cv2.INTER_AREA)
        fill = given.astype(np.float32)
        ring = (cv2.dilate(grown.astype(np.uint8), np.ones((25, 25), np.uint8)) > 0) & ~grown
        if ring.any():  # a render comes back a touch warmer or cooler: match it to the paint around the hole
            fill = fill + (finish[ring].astype(np.float32).mean(0) - fill[ring].mean(0))
    else:
        fill = ff.continue_paint(finish, ~grown)
    out[grown] = np.clip(fill, 0, 255).astype(np.uint8)[grown]
    return out


def back_owner(parts: list[dict], owner: np.ndarray, background: np.ndarray, front: np.ndarray) -> np.ndarray:
    """Who owns each pixel once the objects are taken out: the parts behind, carried across the gaps the objects
    left, and any marks (clouds, foliage) the background picture shows there."""
    if not front.any():
        return owner
    out = ol.fill_along_rows(owner, front)
    is_back = back_parts(parts)
    L = ol.lab(cv2.GaussianBlur(background, (0, 0), 1.2))
    index = {p["id"]: i for i, p in enumerate(parts)}
    for k, p in enumerate(parts):
        if p["kind"] != "marks" or not is_back[k]:
            continue
        inside = front & ol.box_mask(owner.shape, ol.boxes_of(p))
        if p.get("parent"):
            inside &= np.isin(out, _family(parts, index[p["parent"]]))
        out[ol.marks(L, p, inside)] = k
    return out


def build(finish: np.ndarray, plan: dict, owner: np.ndarray,
          background: np.ndarray | None = None) -> tuple[list[np.ndarray], list[dict]]:
    parts, steps = plan["parts"], flat_steps(plan)
    index = {p["id"]: i for i, p in enumerate(parts)}
    hexes = {p["id"]: p["hex"] for p in plan["paints"]}
    h, w = owner.shape
    long_side = max(h, w)
    roots = _roots(parts)
    is_back = back_parts(parts)
    front = ~is_back[owner]
    real_background = background is not None
    front_grown = halo(front) if front.any() else front
    base_back = make_background(finish, front, background)
    own_back = back_owner(parts, owner, base_back, front)

    last_of = {s["part"]: i for i, s in enumerate(steps)}
    paints_of: dict[str, list[str]] = {}
    for s in steps:
        for c in s.get("paints") or []:
            if c not in paints_of.setdefault(s["part"], []):
                paints_of[s["part"]].append(c)

    content: dict[int, np.ndarray] = {}
    area: dict[int, np.ndarray] = {}
    family: dict[int, list[int]] = {}
    nearest: dict[int, np.ndarray] = {}

    def prepare(k: int) -> None:
        """Part k's painted area, and what its paint looks like across all of it."""
        p = parts[k]
        base, own_map = (base_back, own_back) if is_back[k] else (finish, owner)
        fam = family[k] = _family(parts, k)
        mine = own_map == k
        if is_back[k] and not real_background:
            mine &= ~front_grown  # with no picture of what's behind the objects, carry this part's own paint across
        whole = np.isin(own_map, fam)
        in_front = own_map > k  # parts painted later; children are handled as family
        if p.get("covers"):
            reach = ol.box_mask((h, w), p["covers"])
        else:
            r = max(1, int(UNDERLAP * long_side))
            reach = cv2.dilate(whole.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0
            if not is_back[k]:  # an object is painted whole: across narrow gaps and holes where nearer things cross it
                c_ = max(1, int(CLOSE * long_side))
                reach |= cv2.morphologyEx(whole.astype(np.uint8), cv2.MORPH_CLOSE,
                                          cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * c_ + 1, 2 * c_ + 1))) > 0
        hidden = reach & in_front & ~whole
        if is_back[k]:
            hidden &= is_back[own_map]  # behind an object, base_back already holds what's there
        area[k] = whole | hidden
        c = base.copy()
        carried = area[k] & ~mine  # hidden, or under this part's own children
        if carried.any() and mine.any():
            fill = ff.continue_paint(base, mine)
            if _is_wide(mine):
                fill = (1 - ROWS) * fill + ROWS * _rows(base, mine)
            fill = fill + borrowed_texture(base, mine, carried)
            c[carried] = np.clip(fill, 0, 255).astype(np.uint8)[carried]
        content[k] = c
        names = paints_of.get(p["id"]) or []
        if names:
            L = ol.lab(cv2.GaussianBlur(c, (0, 0), 1.0))
            d = np.stack([np.sqrt(((L - ff.hex_lab(hexes[n])) ** 2).sum(2)) for n in names])
            nearest[k] = cv2.medianBlur(d.argmin(0).astype(np.uint8), SMOOTH)

    canvas = np.empty((h, w, 3), np.float32)
    canvas[:] = ff.CANVAS
    started = np.zeros(len(parts), bool)
    pictures, rows = [], []
    for i, s in enumerate(steps):
        k = index[s["part"]]
        if k not in content:
            prepare(k)
        p = parts[k]
        # never paint over something in front that's already there (a child, or a part painted out of order)
        blocked = np.zeros((h, w), bool)
        own_map = own_back if is_back[k] else owner
        for q in np.flatnonzero(started):
            if q > k:
                blocked |= (owner == q) | (own_map == q)
        target = area[k] & ~blocked
        show = s.get("show", "full")
        names = paints_of.get(p["id"]) or []
        if show == "flat":
            lay = ff.flat_paint(content[k], area[k], [hexes[n] for n in s["paints"]])
            where = target
        elif show == "pass" and last_of[s["part"]] != i:
            pick = np.isin(nearest[k], [names.index(n) for n in s["paints"]])
            lay, where = content[k], target & pick
        else:  # full, blend, or the part's last step: everything of the part that's left
            lay, where = content[k], target
        before = canvas.copy()
        rim = np.zeros((h, w), bool)
        if not is_back[k] and not started[k]:
            # the rim around an object was cleared from the background with it; it comes back with the object
            rim = halo(np.isin(owner, family[k])) & ~front & ~blocked
            canvas = _lay(canvas, finish, rim)
        canvas = _lay(canvas, lay, where)
        started[k] = True
        changed = np.abs(canvas - before).max(2) > 6
        rows.append({"id": s["id"], "part": s["part"], "show": show,
                     "area": round(float(area[k].mean()), 4), "painted": round(float(where.mean()), 4),
                     "changed": round(float(changed.mean()), 4),
                     "outside": round(float((changed & ~rim & ~cv2.dilate(area[k].astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)).mean()), 5)})
        pictures.append(np.clip(canvas, 0, 255).astype(np.uint8))
    gap = np.abs(pictures[-1].astype(np.int16) - finish.astype(np.int16)).max(2) > 24
    for r in rows:
        r["final_gap"] = round(float(gap.mean()), 4)  # how far the built last picture is from the finish (0 = the same)
    pictures[-1] = finish.copy()
    return pictures, rows


def _lay(canvas: np.ndarray, paint: np.ndarray, where: np.ndarray) -> np.ndarray:
    """Paint goes on inside `where`, with its edge softened inward only: nothing outside `where` changes."""
    if not where.any():
        return canvas
    a = np.minimum(cv2.GaussianBlur(where.astype(np.float32), (0, 0), FEATHER) * 2.0, 1.0) * where
    a = a[..., None]
    return canvas * (1 - a) + paint.astype(np.float32) * a


def borrowed_texture(img: np.ndarray, src: np.ndarray, gap: np.ndarray) -> np.ndarray:
    """Brush marks for paint carried across a gap, taken from the part's own paint beside it: a smooth fill gives
    the gap away as a soft patch. Each gap pixel borrows from the same row, one gap-width to the side."""
    f = img.astype(np.float32)
    detail = np.clip(f - cv2.GaussianBlur(f, (0, 0), 3), -12, 12)
    out = np.zeros_like(f)
    _, labels, stats, _ = cv2.connectedComponentsWithStats(gap.astype(np.uint8), connectivity=8)
    ys, xs = np.nonzero(gap)
    wide = stats[labels[ys, xs], cv2.CC_STAT_WIDTH] + 4  # each gap pixel's own gap width
    w = img.shape[1]
    todo = np.ones(len(xs), bool)
    for times in (1, -1, 2, -2, 3, -3):  # nearest side first
        sx = xs + times * wide
        ok = todo & (sx >= 0) & (sx < w)
        ok[ok] = src[ys[ok], sx[ok]]
        out[ys[ok], xs[ok]] = detail[ys[ok], sx[ok]]
        todo &= ~ok
    return out * TEXTURE


def _is_wide(mask: np.ndarray) -> bool:
    """A part that runs most of the way across (a sky, water, a field) is painted in bands."""
    cols = mask.any(0)
    return cols.mean() > 0.6


def _rows(img: np.ndarray, src: np.ndarray) -> np.ndarray:
    """from_finish.row_paint, plus the rows it can't do (no paint of this part in them at all): those carry on
    from the nearest row that has some, so a sky that should run past the horizon does."""
    out = ff.row_paint(img, src)
    has = src.any(1)
    if has.any() and not has.all():
        ys = np.arange(len(has))
        nearest_row = ys[has][np.abs(ys[:, None] - ys[has][None]).argmin(1)]
        smooth = cv2.GaussianBlur(out, (0, 0), sigmaX=max(img.shape[1] * 0.05, 1), sigmaY=1)
        out[~has] = smooth[nearest_row[~has]]
    return out


def problems(plan: dict, rows: list[dict]) -> list[str]:
    """What's wrong with the step pictures, each with what to change. Empty when they're fine."""
    out = []
    for r in rows:
        if r["outside"] > 0.0005:
            out.append(f"{r['id']}: changed {r['outside']:.2%} of the picture outside its part. That's a bug in build-steps; report it.")
        if r["changed"] < 0.25 * r["painted"] or r["painted"] == 0:
            out.append(f"{r['id']}: changes almost nothing. Its paints don't match the part's colors here, or an earlier "
                       "step already showed it. Merge it into a neighbor or fix its paints.")
    if rows and rows[-1]["final_gap"] > 0.02:
        out.append(f"the steps leave {rows[-1]['final_gap']:.1%} of the picture different from the finish. Some part has no "
                   "step, or its last step is 'flat'.")
    return out


def contact_sheet(pictures: list[np.ndarray], steps: list[dict], per_row: int = 6, width: int = 360) -> np.ndarray:
    """Every step picture, numbered, on one sheet."""
    h, w = pictures[0].shape[:2]
    th = int(width * h / w)
    tiles = []
    for i, (pic, s) in enumerate(zip(pictures, steps)):
        t = np.ascontiguousarray(cv2.resize(pic, (width, th), interpolation=cv2.INTER_AREA))
        text = f"{i + 1} {s['id']}"
        cv2.rectangle(t, (0, 0), (min(width, 12 + 8 * len(text)), 20), (255, 255, 255), -1)
        cv2.putText(t, text, (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1, cv2.LINE_AA)
        tiles.append(t)
    while len(tiles) % per_row:
        tiles.append(np.full_like(tiles[0], 255))
    gap = np.full((th, 6, 3), 255, np.uint8)
    rows_ = []
    for r in range(0, len(tiles), per_row):
        row = tiles[r]
        for t in tiles[r + 1:r + per_row]:
            row = np.hstack([row, gap, t])
        rows_.append(row)
    line = np.full((6, rows_[0].shape[1], 3), 255, np.uint8)
    sheet = rows_[0]
    for r in rows_[1:]:
        sheet = np.vstack([sheet, line, r])
    return sheet
