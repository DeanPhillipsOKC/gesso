"""Every step picture cut from the one finished painting (pipeline v2, docs/design/pipeline-v2.md section 8).

    build(finish, plan, owner, background=None) -> (one picture per step, one row of numbers per step,
                                                    one mask per step: the pixels it lays paint on)

No renders. Each step paints inside one part's outline (spike/outline.py), so a step can't move, reshape, or
recolor anything else, and the last picture is the finish. That removes what v1's image reviews, redos, and
lock existed to repair (v1 was removed in #82).

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

import copy
import hashlib
import json

import cv2
import numpy as np

import from_finish as ff
import outline as ol

UNDERLAP = 0.012  # how far a part's paint runs under the next part's edge, as a share of the long side
HALO = 0.008  # how far past an object's outline its edge is cleared from the background, as a share of the long side
CLOSE = 0.03  # gaps this wide in an object (a bird's feet across a branch) are painted straight through
# objects covering more of the picture than this want a background picture, not a fill. Was 0.15; three real runs
# (2026-11-13) showed a blurred ghost of the boat, and of the balloon and tree, in every step before they were
# painted, with objects at about 8%. The render costs about 2 cents (design section 7).
NEEDS_BACKGROUND = 0.02
MATCH = 0.02  # how far around a hole a background picture is matched to the finish, as a share of the long side
MATCH_MAX = 40  # RGB levels: a bigger difference than this beside a hole isn't tone, it's something else
TEXTURE = 0.7  # how much brush texture carried-on paint borrows from beside the gap
FEATHER = 0.8  # pixels of softening at a painted edge, inward only
SMOOTH = 5  # median filter on which-paint-is-nearest, so a pass arrives as marks, not as single pixels
BACK = ("area", "marks")
RIM = 0.008  # a part's paint this near a part painted later is that part's rim (a cloud's glow, a foot's shadow)
CLEAN_MIN = 0.1  # a part with less of itself than this away from every rim keeps the old fill: there's too little to go on
ROW_BAND = 0.3  # a wide part and what's painted on it fill at least this much of a row it runs along
ROW_SOFT = 0.03  # how far a wide part's row colors are softened up and down, as a share of the height
ROW_MIN = 0.04  # a row needs this share of the picture's width in clean paint to say what color the row is
MAIN_PIECE = 0.15  # a piece of a part with less clean paint than this share of the biggest piece's is a stray: not a source
MARKS = 0.008  # the size of brush marks carried across a gap in a thing (not a wide area), as a share of the long side
NEAR = 0.03  # how far a wide part's local color (a glow by the sun) reaches into a gap before its rows take over
# The ghost check: before a part's first step, the picture mustn't already show the part's shape.
GHOST_BAND = 0.006  # the bands compared either side of a part's edge, as a share of the long side
GHOST_SEEN = 8.0  # Lab units a part must differ from what's around it in the finish for that stretch of edge to count
GHOST_PART = 0.4  # how much of that difference a step may already show there
GHOST_EDGE = 0.3  # the share of a part's countable edge that may show it that plainly
GHOST_FAINT = 0.25  # a soft ghost (a blurred cloud) shows this much of the difference
GHOST_FAINT_EDGE = 0.33  # the share of a part's edge that shows it faintly before it's worth a look
GHOST_COVER = 0.25  # the share of a part's edge that must be under paint before the step is judged
GHOST_SIDE = 768  # the check runs on the pictures shrunk to this long side


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
    """True for the parts behind every object. An area (sky, hill, field, water) is always behind, wherever it's
    listed: a lavender field listed after the tree is still ground, and the background render must not take it out
    (it did, and invented a meadow, 2026-11-13). Marks with no parent are behind until the first object or thin
    part is listed, and in front after it (a reflection). Objects and thin parts are in front. A child is wherever
    its root is."""
    roots = _roots(parts)
    first = next((i for i, p in enumerate(parts) if not p.get("parent") and p["kind"] not in BACK), len(parts))
    return np.array([parts[r]["kind"] == "area" or (parts[r]["kind"] == "marks" and r < first) for r in roots])


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
        # A render comes back a touch warmer, cooler, or lighter, and differently in the sky than in the water. So
        # it's matched to the finish locally: how far the two differ around each hole is carried into the hole and
        # taken off. (One shift for the whole picture left a tinted sail-shaped patch in the sky, 2026-11-13.)
        off = finish.astype(np.float32) - fill
        # only where the two nearly agree: a big difference beside a hole is a leftover of the object (a hull's red
        # glow on the water), not a shift in tone, and carried into the hole it tinted the whole patch
        alike = ~grown & (np.abs(off).max(2) < MATCH_MAX)
        near, support = ff._fill_from(off * alike[..., None], alike, MATCH * max(front.shape))
        fill = fill + near * np.minimum(support * 4, 1.0)[..., None]
    else:
        fill = ff.continue_paint(finish, ~grown)
    out[grown] = np.clip(fill, 0, 255).astype(np.uint8)[grown]
    return out


ROWS_REACH = 0.03  # behind an object, an area takes rows this far (share of the height) past the rows it has beside it
FAR_ROWS = 0.05  # a back part's paint this far (share of the height) above or below its own outline's rows is reported
FAR_SHARE = 0.001  # ... when it's more than this share of the picture
CHANGED = 45  # RGB levels a background picture may differ from the finish before a pixel counts as changed
CHANGED_SHARE = 0.25  # more of the scene changed than this, away from the objects, and the render didn't keep it


def background_problems(finish: np.ndarray, background: np.ndarray, front: np.ndarray) -> tuple[list[str], dict]:
    """Did the background picture keep the scene? Away from the objects it should still be the finish (brushwork
    aside). Only its pixels behind the objects are ever used, so a changed scene can't spoil a step picture, but it
    does mean what's behind the objects was painted for a different picture."""
    if background.shape[:2] != finish.shape[:2]:
        background = cv2.resize(background, (finish.shape[1], finish.shape[0]), interpolation=cv2.INTER_AREA)
    away = ~halo(halo(front))
    a = cv2.GaussianBlur(finish, (0, 0), 4).astype(np.int16)
    b = cv2.GaussianBlur(background, (0, 0), 4).astype(np.int16)
    diff = np.abs(a - b).max(2)
    share = float((diff[away] > CHANGED).mean()) if away.any() else 0.0
    shift = float(np.abs(a[away].mean(0) - b[away].mean(0)).max()) if away.any() else 0.0
    left = np.abs(b[front].astype(np.int16) - a[front]).max(1) <= CHANGED / 3 if front.any() else np.array([False])
    numbers = {"changed_share": round(share, 3), "color_shift": round(shift, 1), "objects_left": round(float(left.mean()), 3)}
    out = []
    if share > CHANGED_SHARE:
        out.append(f"the background picture changed {share:.0%} of the scene away from the objects. Render it once more "
                   "(--redo); if it still does, delete 98_background.png and keep the free fill.")
    if left.mean() > 0.5:
        out.append(f"{left.mean():.0%} of the objects' pixels look the same as in the finish: the render didn't remove "
                   "them. Render it once more (--redo), naming what to remove more plainly.")
    return out, numbers


def by_color(parts: list[dict], owner: np.ndarray, out: np.ndarray, L: np.ndarray, front: np.ndarray,
             doubt: np.ndarray | None = None, opened: np.ndarray | None = None) -> None:
    """With a real picture of what's behind the objects, each gap is divided by what that picture shows: a pixel
    goes to the area around the gap whose color there is nearest. Dividing along rows alone gave a hull sitting on
    the horizon to the sky, and the sky's first step then painted a hull-shaped patch of sea (2026-11-13).

    An area takes only pixels in the rows it has beside the gap, give or take ROWS_REACH of the height, so a color
    match far from it doesn't count (#139). A pixel whose color is nearest a part that doesn't have its rows is set
    in `doubt`: the picture there doesn't look like the part that owns it (a hill's top hidden behind the tree, or
    cloud streaks the hill's color), so the owner's own paint is carried over it instead (build's `prepare`)."""
    h, w = owner.shape
    r = max(3, int(0.02 * max(h, w)))
    reach = max(2, int(ROWS_REACH * h))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    roots = np.array(_roots(parts))
    area_root = np.array([parts[q]["kind"] == "area" for q in roots])
    n, labels = cv2.connectedComponents(front.astype(np.uint8), connectivity=8)
    for i in range(1, n):
        gap = labels == i
        ring = (cv2.dilate(gap.astype(np.uint8), kernel) > 0) & ~front
        around = roots[owner[ring]]
        cands = [int(c) for c in np.unique(around) if area_root[c] and (around == c).sum() >= 20]
        if len(cands) < 2:
            continue
        ring_root = np.full((h, w), -1)
        ring_root[ring] = around
        means = np.array([np.median(L[ring_root == c], axis=0) for c in cands])
        d = np.sqrt(((L[gap][:, None, :] - means[None]) ** 2).sum(2))
        # A part only takes the rows it has around the gap (and a little more, for an edge hidden by the object):
        # orange cloud streaks behind a tree's canopy matched the golden hill at the tree's foot, and the hill's
        # first step painted them in the sky (#139).
        # The rows are taken over the whole ring, not per side or per column: an area whose edge slopes steeply
        # behind a wide object can still reach rows it only has on the other side.
        ys = np.nonzero(gap)[0]
        spans = [(lambda rr: (rr.min(), rr.max()))(np.flatnonzero((ring_root == c).any(1))) for c in cands]
        allowed = np.zeros(d.shape, bool)
        for j, (lo, hi) in enumerate(spans):
            allowed[:, j] = (ys >= lo - reach) & (ys <= hi + reach)
        # Rows no area reaches: an object across the whole picture, taller than the reach (a bridge, a wall, a
        # canopy). Each band of them goes to the nearest area above it and the nearest below, split where the
        # render's colors meet: a color reaches past the band's middle only where it joins its own area's side
        # (water running up behind a bridge to the horizon), not as a band of its own (hill-colored streaks up in
        # the sky behind a canopy).
        none = ~allowed.any(1)
        bands = []
        for y0, y1 in _runs(np.unique(ys[none])):
            above = [j for j, (lo, hi) in enumerate(spans) if hi + reach < y0]
            below = [j for j, (lo, hi) in enumerate(spans) if lo - reach > y1]
            up = max(above, key=lambda j: spans[j][1]) if above else None
            down = min(below, key=lambda j: spans[j][0]) if below else None
            sel = none & (ys >= y0) & (ys <= y1)
            for j in (up, down):
                if j is not None:
                    allowed[sel, j] = True
            bands.append((y0, y1, up, down, sel))
        if doubt is not None:
            unsure = ~allowed[np.arange(len(ys)), d.argmin(1)]
            doubt[gap] = doubt[gap] | unsure
        d[~allowed] = np.inf
        first = d.argmin(1)
        pick = np.zeros((h, w), np.uint8)
        pick[gap] = first.astype(np.uint8)
        pick = cv2.medianBlur(pick, 2 * max(1, r // 4) + 1)
        got = pick[gap].astype(np.int64)
        got = np.where(allowed[np.arange(len(got)), got], got, first)  # smoothing mustn't carry a part out of its rows
        xs = np.nonzero(gap)[1]
        for y0, y1, up, down, sel in bands:
            if up is None or down is None:
                continue
            mid = (y0 + y1) / 2
            for j, other, far_side in ((up, down, ys > mid), (down, up, ys < mid)):
                # pixels of j's color on the other area's side of the middle stay j's only if they join j's side
                mine = np.zeros((h, w), np.uint8)
                mine[ys[sel & (got == j)], xs[sel & (got == j)]] = 1
                n_, lab_ = cv2.connectedComponents(mine, connectivity=8)
                joined = np.zeros(n_, bool)
                near_side = sel & (got == j) & ~far_side
                joined[np.unique(lab_[ys[near_side], xs[near_side]])] = True
                cut = sel & (got == j) & far_side & ~joined[lab_[ys, xs]]
                got[cut] = other
                if doubt is not None:
                    doubt[ys[cut], xs[cut]] = True
        if opened is not None:
            opened[gap] = opened[gap] | none
        out[gap] = np.array(cands)[got]


def _runs(values: np.ndarray) -> list[tuple[int, int]]:
    """Runs of consecutive integers in a sorted array, as (first, last)."""
    if not len(values):
        return []
    breaks = np.flatnonzero(np.diff(values) > 1)
    starts = np.r_[values[0], values[breaks + 1]]
    ends = np.r_[values[breaks], values[-1]]
    return [(int(a), int(b)) for a, b in zip(starts, ends)]


def back_owner(parts: list[dict], owner: np.ndarray, background: np.ndarray, front: np.ndarray,
               real: bool = False, doubt: np.ndarray | None = None,
               opened: np.ndarray | None = None) -> np.ndarray:
    """Who owns each pixel once the objects are taken out: the parts behind, carried across the gaps the objects
    left, and any marks (clouds, foliage) the background picture shows there. `real`: the background is a picture
    of what's really behind the objects (a render), not a fill. `doubt`, when given, is set where the render's
    color there belongs to no part in those rows, and `opened` where no area had the rows (see by_color)."""
    if not front.any():
        return owner
    out = ol.fill_along_rows(owner, front)
    is_back = back_parts(parts)
    L = ol.lab(cv2.GaussianBlur(background, (0, 0), 1.2))
    if real:
        by_color(parts, owner, out, L, halo(front), doubt, opened)  # the cleared rim around each object is part of its gap
    index = {p["id"]: i for i, p in enumerate(parts)}
    for k, p in enumerate(parts):
        if p["kind"] != "marks" or not is_back[k]:
            continue
        inside = front & ol.box_mask(owner.shape, ol.boxes_of(p))
        if p.get("parent"):
            inside &= np.isin(out, _family(parts, index[p["parent"]]))
        found = ol.marks(L, p, inside)
        out[found] = k
        if doubt is not None:
            doubt &= ~found  # marks the render shows there (clouds) are what's there
    return out


_built: dict[str, tuple] = {}  # the last few builds in this process, by what went in (see build)
KEEP_BUILDS = 4


def _key(finish: np.ndarray, plan: dict, owner: np.ndarray, background: np.ndarray | None) -> str:
    h = hashlib.sha1(json.dumps(plan, sort_keys=True, default=str).encode())
    for a in (finish, owner, background):
        h.update(b"-" if a is None else f"{a.shape}{a.dtype}".encode() + np.ascontiguousarray(a).tobytes())
    for module in (globals(), vars(ff), vars(ol)):  # the tuned numbers build uses, here and in what it calls
        h.update(repr(sorted((k, v) for k, v in module.items()
                             if k.isupper() and isinstance(v, (int, float, str, tuple)))).encode())
    return h.hexdigest()


def build(finish: np.ndarray, plan: dict, owner: np.ndarray,
          background: np.ndarray | None = None) -> tuple[list[np.ndarray], list[dict], list[np.ndarray]]:
    """(each step's picture, each step's numbers, each step's painted area). The painted area is the pixels the
    step lays paint on, plus an object's rim on the step that brings the object back: what the step-aids outline
    on the page.

    The same inputs in one process give back a copy of the last answer instead of building again: build-steps,
    step-aids, draft-text, check, and publish each build the steps, and the tests run them in one process (#87).
    From the command line each tool is its own process, so nothing changes there. A test that patches one of
    build's functions (not a number) should clear _built first."""
    key = _key(finish, plan, owner, background)
    if key not in _built:
        _built[key] = _build(finish, plan, owner, background)
        while len(_built) > KEEP_BUILDS:
            _built.pop(next(iter(_built)))
    pictures, rows, painted = _built[key]
    return [p.copy() for p in pictures], copy.deepcopy(rows), [m.copy() for m in painted]


def _build(finish: np.ndarray, plan: dict, owner: np.ndarray,
           background: np.ndarray | None = None) -> tuple[list[np.ndarray], list[dict], list[np.ndarray]]:
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
    doubt, opened = np.zeros((h, w), bool), np.zeros((h, w), bool)
    own_back = back_owner(parts, owner, base_back, front, real=background is not None, doubt=doubt, opened=opened)

    last_of = {s["part"]: i for i, s in enumerate(steps)}
    paints_of: dict[str, list[str]] = {}
    for s in steps:
        for c in s.get("paints") or []:
            if c not in paints_of.setdefault(s["part"], []):
                paints_of[s["part"]].append(c)

    content: dict[int, np.ndarray] = {}
    coated = np.zeros(len(parts), bool)
    area: dict[int, np.ndarray] = {}
    family: dict[int, list[int]] = {}
    nearest: dict[int, np.ndarray] = {}
    base_of: dict[int, np.ndarray] = {}
    kids: dict[int, np.ndarray] = {}
    far: dict[int, np.ndarray] = {}  # an area's paint behind the objects far above or below its own outline's rows
    rim_group: dict[int, np.ndarray] = {}  # for a part's rim pixels, the later part whose rim it is; -1 elsewhere
    detailed: dict[int, np.ndarray] = {}  # where a part has laid more than a flat coat so far
    top = np.full((h, w), -1, np.int32)  # the part whose paint is on top at each pixel

    def group_of(k: int) -> np.ndarray:
        """For every part, the part that brings its rim back on part k: itself, or for something painted on a
        later part (a wing on the bird), that later part. A child of k itself (a cloud on the sky) is its own."""
        res = np.arange(len(parts))
        for q0, p in enumerate(parts):
            q = q0
            while p.get("parent") and p["parent"] != parts[k]["id"]:
                q = index[p["parent"]]
                p = parts[q]
            res[q0] = q
        return res

    def prepare(k: int) -> None:
        """Part k's painted area, and what its paint looks like across all of it."""
        p = parts[k]
        base, own_map = (base_back, own_back) if is_back[k] else (finish, owner)
        fam = family[k] = _family(parts, k)
        mine = own_map == k
        if is_back[k] and not real_background:
            mine &= ~front_grown  # with no picture of what's behind the objects, carry this part's own paint across
        elif is_back[k]:
            mine &= ~doubt  # what the render shows there isn't this part's: carry its own paint across (#139)
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
        seen = np.flatnonzero(np.isin(owner, fam).any(1))
        far[k] = np.zeros((h, w), bool)
        if len(seen) and p["kind"] == "area":  # marks found behind an object (a cloud) aren't held to rows
            m, ys_ = int(FAR_ROWS * h), np.arange(h)
            # rows behind an object that no area had are split between the nearest areas above and below, and
            # aren't far from either
            far[k] = whole & ((ys_ < seen.min() - m) | (ys_ > seen.max() + m))[:, None] & ~opened
        c = base.copy()
        # This part's paint right beside a part painted later is that part's rim: a cloud's glow on the sky, a
        # foot's shadow on the branch. Carried into the gap it drew the cloud and the foot before their steps
        # (#84). So the fill is taken from the part's clean paint only, and the rim itself shows the fill until
        # the part it belongs to is painted.
        later = (own_map > k) & (is_back[own_map] == is_back[k])
        r = max(2, int(RIM * long_side))
        near = cv2.dilate(later.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0
        clean = main_pieces(mine, mine & ~near)
        wide = bool(is_back[k]) and _is_wide(mine)  # a long branch isn't a sky
        if wide:
            # a wide part is itself only in the rows it runs along: bits of it lower down (sky showing between a
            # ridge and a tree) aren't what its rows look like, whatever size they are
            clean = clean & (whole.sum(1) >= ROW_BAND * w)[:, None]
        group = np.full((h, w), -1, np.int32)
        if clean.sum() >= max(50, CLEAN_MIN * mine.sum()):
            # A stray piece of the part goes the same way, whole: a dab of foliage the outline left to the sky
            # is the foliage's, and comes with it.
            rim_k = mine & ~clean
            group[rim_k] = group_of(k)[ol.fill_from_nearest(own_map, ~later)[rim_k]]
        else:
            clean, rim_k = mine, np.zeros((h, w), bool)  # a thin part that is all rim: nothing cleaner to go on
        rim_group[k] = group
        carried = (area[k] & ~mine) | rim_k  # hidden, under this part's own children, or a later part's rim
        if carried.any() and clean.any():
            fill = blend_paint(base, clean) if wide else None
            if fill is None:
                # a thing's paint (bark, a hull) has bigger marks than a sky's: carry them over whole, or the gap
                # shows as a smooth patch in the shape of what will cover it
                fill = ff.continue_paint(base, clean) + borrowed_texture(base, clean, carried, MARKS * long_side, 45, 1.0)
            else:
                fill = fill + borrowed_texture(base, clean, carried)
            c[carried] = np.clip(fill, 0, 255).astype(np.uint8)[carried]
        content[k] = c
        kids[k] = whole & ~mine  # where this part's children go
        base_of[k] = base
        names = paints_of.get(p["id"]) or []
        if names:
            L = ol.lab(cv2.GaussianBlur(c, (0, 0), 1.0))
            d = np.stack([np.sqrt(((L - ff.hex_lab(hexes[n])) ** 2).sum(2)) for n in names])
            nearest[k] = cv2.medianBlur(d.argmin(0).astype(np.uint8), SMOOTH)

    canvas = np.empty((h, w, 3), np.float32)
    canvas[:] = ff.CANVAS
    started = np.zeros(len(parts), bool)
    pictures, rows, painted = [], [], []
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
            coated[k] = True
        elif show == "pass" and last_of[s["part"]] != i:
            pick = np.isin(nearest[k], [names.index(n) for n in s["paints"]])
            lay, where = content[k], target & pick
        else:  # full, blend, or the part's last step: everything of the part that's left
            lay, where = content[k], target
        if show != "flat":
            g = rim_group[k]
            back = (g >= 0) & started[np.maximum(g, 0)]  # rims of parts already painted: the real paint, not the fill
            if back.any():
                lay = np.where(back[..., None], base_of[k], lay)
        if coated[k] and show != "flat":
            # Over a flat coat, a pass paints the part's own marks. Where its children will go (streaks on water,
            # foliage on a sky) the coat stays as it is until the child's step: a painter doesn't touch it, and a
            # carried-across fill there showed as a blurred patch in every step in between (2026-11-13). Only the
            # children's places: where another part will cross it (feet on a branch) the passes go straight
            # through, or the coat stays there as a foot-shaped patch of the branch's dark until the feet (#84).
            where = where & ~kids[k]
        before = canvas.copy()
        rim = np.zeros((h, w), bool)
        if not is_back[k] and not started[k]:
            # the rim around an object was cleared from the background with it; it comes back with the object
            rim = halo(np.isin(owner, family[k])) & ~front & ~blocked
            canvas = _lay(canvas, finish, rim)
        if not started[k]:
            # this part's rim on the parts under it was held back as fill; it comes with the part
            for j, g in rim_group.items():
                back = (g == k) & (top == j) & detailed.get(j, False)
                if np.any(back):
                    canvas = _lay(canvas, base_of[j], back)
                    rim = rim | back
        canvas = _lay(canvas, lay, where)
        top[where] = k
        if show != "flat":
            detailed[k] = detailed.get(k, np.zeros((h, w), bool)) | where
        started[k] = True
        changed = np.abs(canvas - before).max(2) > 6
        rows.append({"id": s["id"], "part": s["part"], "show": show, "last": last_of[s["part"]] == i,
                     "area": round(float(area[k].mean()), 4), "painted": round(float(where.mean()), 4),
                     "changed": round(float(changed.mean()), 4),
                     "far": round(float((where & far[k]).mean()), 5),
                     "outside": round(float((changed & ~rim & ~cv2.dilate(area[k].astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)).mean()), 5)})
        pictures.append(np.clip(canvas, 0, 255).astype(np.uint8))
        painted.append(where | rim)
    for r, g in zip(rows, ghosts(finish, parts, owner, steps, pictures, painted)):
        r["ghosts"] = g
    gap = np.abs(pictures[-1].astype(np.int16) - finish.astype(np.int16)).max(2) > 24
    for r in rows:
        r["final_gap"] = round(float(gap.mean()), 4)  # how far the built last picture is from the finish (0 = the same)
    pictures[-1] = finish.copy()
    return pictures, rows, painted


def visible(plan: dict, owner: np.ndarray, painted: list[np.ndarray]) -> list[np.ndarray]:
    """Of each step's painted area (build's third value), what the finished painting still shows: the pixels its
    part, or a child of its part, owns in the outlines. Paint carried under a later part (behind the boat, under the
    next part's edge, a `covers` overrun) is left out, and so is an object's soft rim. A child's place counts until
    the child is painted: by then the painted area already leaves it out. The Where words measure this (#126); the
    outline on the page stays the painted area, since the painter does paint there. A step whose part shows
    nowhere keeps its painted area."""
    parts = plan["parts"]
    index = {p["id"]: i for i, p in enumerate(parts)}
    out = []
    for s, m in zip(flat_steps(plan), painted):
        seen = m & np.isin(owner, _family(parts, index[s["part"]]))
        out.append(seen if seen.any() else m.copy())
    return out


def main_pieces(mine: np.ndarray, clean: np.ndarray) -> np.ndarray:
    """`clean` without the part's stray pieces: a piece of the part counts when its clean paint is at least
    MAIN_PIECE of the biggest piece's. A sliver filed under the sky down between the hill and the tree gave every
    row below the horizon the hill's dark green (#84)."""
    n, labels = cv2.connectedComponents(mine.astype(np.uint8), connectivity=8)
    if n <= 2:
        return clean
    sizes = np.bincount(labels[clean], minlength=n)
    sizes[0] = 0
    return clean & (sizes >= MAIN_PIECE * max(sizes.max(), 1))[labels]


def blend_paint(img: np.ndarray, clean: np.ndarray) -> np.ndarray | None:
    """A wide part's paint (a sky, water, a field) carried on where it can't be seen: each row in that row's own
    clean color, with the part's local color (a glow beside the sun) reaching a little way in from clean paint
    nearby. Rows with too little clean paint carry on from the nearest row that has some, so a sky runs on below its
    horizon in its last color. None when no row has enough to go on.

    Filling from the gap's edge instead drew whatever sat on that edge: clouds, a ridge, and bands of hill color
    under the horizon in the lavender's first step (#84)."""
    h, w = clean.shape
    f = img.astype(np.float32)
    need = max(8, int(ROW_MIN * w))
    ok = clean.sum(1) >= need
    if not ok.any():
        return None
    rows = np.zeros((h, 3), np.float32)
    for y in np.flatnonzero(ok):
        rows[y] = np.median(f[y][clean[y]], axis=0)  # a median: one stray dab doesn't tint the row
    ys = np.arange(h)
    for c in range(3):
        rows[:, c] = np.interp(ys, ys[ok], rows[ok, c])
    rows = cv2.GaussianBlur(rows[:, None, :], (0, 0), sigmaX=1, sigmaY=max(h * ROW_SOFT, 1))
    plate = np.repeat(rows, w, axis=1)
    off, support = ff._fill_from((f - plate) * clean[..., None], clean, NEAR * max(h, w))
    return plate + off * np.minimum(support * 4, 1.0)[..., None]


def ghosts(finish: np.ndarray, parts: list[dict], owner: np.ndarray, steps: list[dict], pictures: list[np.ndarray],
           painted: list[np.ndarray]) -> list[list[dict]]:
    """For each step, the parts not painted yet whose shape the picture already shows: [{"part", "edge", "faint"}],
    where `edge` is the share of the part's edge that shows plainly and `faint` the share that shows at all. A
    part's edge counts where the finish really has one (the part differs from what's around it) and where the step
    has laid paint on both sides. There the step shows the part if the two sides already differ the way they will,
    by GHOST_PART of the final difference (plainly) or GHOST_FAINT of it (at all). Listed when `edge` reaches
    GHOST_EDGE or `faint` reaches GHOST_FAINT_EDGE.

    Set on the three gate runs of 2026-11-13, before and after the fill was fixed (#84). Plain: the bands and ridge
    under the lavender's sky 0.46 to 0.87, the sailboat's hill and far shore 0.55 to 0.91, the chickadee's feet
    0.35; nothing over 0.23 after. Faint: the lavender's clouds 0.36 and the chickadee's foliage 0.42 under their
    skies; nothing over 0.30 after."""
    h, w = owner.shape
    s = min(1.0, GHOST_SIDE / max(h, w))
    size = (max(1, int(w * s)), max(1, int(h * s)))
    small = lambda a: cv2.resize(a, size, interpolation=cv2.INTER_AREA)  # noqa: E731
    own = cv2.resize(owner.astype(np.int32), size, interpolation=cv2.INTER_NEAREST)
    r = max(2, int(GHOST_BAND * max(size)))
    k3 = np.ones((3, 3), np.uint8)
    kr = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    index = {p["id"]: i for i, p in enumerate(parts)}
    first: dict[int, int] = {}
    for i, st in enumerate(steps):
        first.setdefault(index[st["part"]], i)
    out: list[list[dict]] = [[] for _ in steps]
    Lf = ol.lab(cv2.GaussianBlur(small(finish), (0, 0), 1.0))

    def sides(L: np.ndarray, inner: np.ndarray, outer: np.ndarray) -> np.ndarray:
        a, _ = ff._fill_from(L, inner, r)
        b, _ = ff._fill_from(L, outer, r)
        return a - b

    def share_of(cover: np.ndarray, band: np.ndarray) -> np.ndarray:
        m = band.astype(np.float32)
        return cv2.GaussianBlur(cover * m, (0, 0), r) / np.maximum(cv2.GaussianBlur(m, (0, 0), r), 1e-6)

    todo = []
    for q in range(len(parts)):
        fam = _family(parts, q)
        start = min((first[j] for j in fam if j in first), default=0)
        if start == 0:
            continue
        F = np.isin(own, fam).astype(np.uint8)
        grown, shrunk = cv2.dilate(F, kr) > 0, cv2.erode(F, kr) > 0
        inner, outer = (F > 0) & ~shrunk, grown & ~(F > 0)
        edge = (cv2.dilate(F, k3) > 0) & ~(cv2.erode(F, k3) > 0)
        ys, xs = np.nonzero(edge)
        if len(ys) < 12 or not inner.any() or not outer.any():
            continue
        # a crop around the part keeps this quick
        y0, y1, x0, x1 = max(0, ys.min() - 4 * r), min(size[1], ys.max() + 4 * r + 1), max(0, xs.min() - 4 * r), min(size[0], xs.max() + 4 * r + 1)
        box = (slice(y0, y1), slice(x0, x1))
        inner, outer, edge = inner[box], outer[box], edge[box]
        df = sides(Lf[box], inner, outer)
        size_f = np.sqrt((df ** 2).sum(2))
        real = edge & (size_f >= GHOST_SEEN)
        if real.sum() >= 12:
            todo.append((q, start, box, inner, outer, real, df, size_f))
    cover = np.zeros(size[::-1], np.float32)
    for i, pic in enumerate(pictures):
        cover = np.maximum(cover, small(painted[i].astype(np.float32)))
        L = None
        for q, start, box, inner, outer, real, df, size_f in todo:
            if i >= start:
                continue
            under = real & (share_of(cover[box], inner) > 0.9) & (share_of(cover[box], outer) > 0.9)
            if under.sum() < max(12, GHOST_COVER * real.sum()):
                continue
            if L is None:
                L = ol.lab(cv2.GaussianBlur(small(pic), (0, 0), 1.0))
            ds = sides(L[box], inner, outer)
            there = (ds * df).sum(2) / np.maximum(size_f ** 2, 1e-6)
            share = float((there[under] >= GHOST_PART).mean())
            faint = float((there[under] >= GHOST_FAINT).mean())
            if share >= GHOST_EDGE or faint >= GHOST_FAINT_EDGE:
                out[i].append({"part": parts[q]["id"], "edge": round(share, 2), "faint": round(faint, 2)})
    return out


def _lay(canvas: np.ndarray, paint: np.ndarray, where: np.ndarray) -> np.ndarray:
    """Paint goes on inside `where`, with its edge softened inward only: nothing outside `where` changes."""
    if not where.any():
        return canvas
    a = np.minimum(cv2.GaussianBlur(where.astype(np.float32), (0, 0), FEATHER) * 2.0, 1.0) * where
    a = a[..., None]
    return canvas * (1 - a) + paint.astype(np.float32) * a


def borrowed_texture(img: np.ndarray, src: np.ndarray, gap: np.ndarray, scale: float = 3, most: float = 12,
                     strength: float = TEXTURE) -> np.ndarray:
    """Brush marks for paint carried across a gap, taken from the part's own paint beside it: a smooth fill gives
    the gap away as a soft patch. Each gap pixel borrows from the same row, one gap-width to the side."""
    f = img.astype(np.float32)
    detail = np.clip(f - cv2.GaussianBlur(f, (0, 0), scale), -most, most)
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
    if todo.any() and src.any():
        # too big a gap to borrow from beside it (a sky under a spread of foliage): tile the marks from the widest
        # patch of the part's own paint, so the fill still reads as brushed paint and not as a blur
        dist = cv2.distanceTransform(src.astype(np.uint8), cv2.DIST_L2, 3)
        cy, cx = np.unravel_index(int(dist.argmax()), dist.shape)
        r = int(dist[cy, cx] / 1.5)
        tile = detail[max(0, cy - r):cy + r, max(0, cx - r):cx + r]
        if min(tile.shape[:2]) >= 8:
            tile = np.concatenate([tile, tile[:, ::-1]], axis=1)  # mirrored, so the tiles meet without a seam
            tile = np.concatenate([tile, tile[::-1]], axis=0)
            th, tw = tile.shape[:2]
            out[ys[todo], xs[todo]] = tile[ys[todo] % th, xs[todo] % tw]
    return out * strength


def _is_wide(mask: np.ndarray) -> bool:
    """A part that runs most of the way across (a sky, water, a field) is painted in bands."""
    cols = mask.any(0)
    return cols.mean() > 0.6


def problems(plan: dict, rows: list[dict]) -> list[str]:
    """What's wrong with the step pictures, each with what to change. Empty when they're fine."""
    out = []
    for r in rows:
        if r["outside"] > 0.0005:
            out.append(f"{r['id']}: changed {r['outside']:.2%} of the picture outside its part. That's a bug in build-steps; report it.")
        if r.get("far", 0) > FAR_SHARE:
            out.append(f"{r['id']}: paints {r['far']:.2%} of the picture behind the objects more than {FAR_ROWS:.0%} of "
                       "the height above or below its part's own outline. That's the split of what's behind the objects "
                       "going wrong (a bug in build-steps); look at the step in trials/steps.jpg and report it.")
        # (not a part's last step: it shows whatever is left, which is rightly little when the light tips go last)
        if (r["changed"] < 0.25 * r["painted"] and not r.get("last")) or r["painted"] == 0:
            out.append(f"{r['id']}: changes almost nothing. Its paints don't match the part's colors here, or an earlier "
                       "step already showed it. Merge it into a neighbor or fix its paints.")
    names = {p["id"]: p.get("name", p["id"]) for p in plan.get("parts") or []}
    on_another = {p["id"] for p in plan.get("parts") or [] if p.get("parent")}
    for part, (first_id, worst, n) in _seen(rows, "edge", GHOST_EDGE).items():
        if part in on_another:
            continue  # a part painted on another: faint_ghosts says so
        out.append(f"{first_id}: {names.get(part, part)} ({part}) already shows, along {worst:.0%} of its edge, in {n} "
                   f"step{'s' if n > 1 else ''} before it's painted. Look at it in trials/steps.jpg and at its outline "
                   "in parts/preview.jpg. If the outline misses some of it, fix the outline: what's left outside is "
                   "painted with the part behind. If it still shows after 2 rounds, drop the part and paint it as a "
                   "pass of the part behind (design section 6), and report the step: the fill under it is at fault.")
    if rows and rows[-1]["final_gap"] > 0.02:
        out.append(f"the steps leave {rows[-1]['final_gap']:.1%} of the picture different from the finish. Some part has no "
                   "step, or its last step is 'flat'.")
    return out


def _seen(rows: list[dict], key: str, least: float) -> dict[str, tuple[str, float, int]]:
    """Each part the ghost check found: the first step it shows in, the most it shows, and in how many steps."""
    out: dict[str, tuple[str, float, int]] = {}
    for r in rows:
        for g in r.get("ghosts") or []:
            if g[key] >= least:
                first_id, worst, n = out.get(g["part"], (r["id"], 0.0, 0))
                out[g["part"]] = (first_id, max(worst, g[key]), n + 1)
    return out


def faint_ghosts(plan: dict, rows: list[dict]) -> list[str]:
    """What shows before its step but isn't a failure, to look for on the sheet: a part that shows softly (a blurred
    cloud in a sky), and a part painted on another that shows at all. That second kind is often meant (a tree's
    block-in coat in two paints already shows where the trunk goes) and sometimes an outline that misses a little
    (an eye left to the head). Those `problems` reports aren't repeated."""
    parts = plan.get("parts") or []
    names = {p["id"]: p.get("name", p["id"]) for p in parts}
    on_another = {p["id"] for p in parts if p.get("parent")}
    plain = _seen(rows, "edge", GHOST_EDGE)
    out = [f"{first_id}: {names.get(part, part)} ({part}) shows before it's painted ({worst:.0%} of its edge). It's "
           "painted on another part, so that may be the block-in, or its outline misses a little of it"
           for part, (first_id, worst, _) in plain.items() if part in on_another]
    out += [f"{first_id}: {names.get(part, part)} ({part}) shows faintly before it's painted ({worst:.0%} of its edge)"
            for part, (first_id, worst, _) in _seen(rows, "faint", GHOST_FAINT_EDGE).items() if part not in plain]
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
