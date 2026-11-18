"""What the step tools share about a lesson's steps and pictures (docs/design/pipeline-v3.md, sections 6 to 9).

    flat_steps(plan)                     -> the plan's steps in order, each with its stage
    make_background(finish, front, raw)  -> a render's pixels inside `front` put into the picture (the chain's keep)
    halo(mask)                           -> an object's edge and soft rim
    visible(plan, owner, painted)        -> what the finish still shows of each step's painted area
    contact_sheet(pictures, steps)       -> every step picture on one sheet

The plan these read is in version 2's shape (steps3.as_v2): a part a unit. Pipeline v2 cut every step from the
finish inside measured outlines here, with about 34 tuned numbers; that went in #238 with the rest of v2.
"""

from __future__ import annotations

import cv2
import numpy as np

import from_finish as ff

HALO = 0.008  # how far past an object's outline its edge is cleared, as a share of the long side
MATCH = 0.02  # how far around a hole a render is matched to the picture, as a share of the long side
MATCH_MAX = 40  # RGB levels: a bigger difference than this beside a hole isn't tone, it's something else
FEATHER = 0.8  # pixels of softening at a painted edge, inward only
SMOOTH = 5  # median filter on which-paint-is-nearest, so a pass arrives as marks, not as single pixels


def flat_steps(plan: dict) -> list[dict]:
    """The plan's steps in order, each with its stage's id and name."""
    return [dict(s, stage=st["id"], stage_name=st.get("name", st["id"])) for st in plan["stages"] for s in st["steps"]]


def _family(parts: list[dict], k: int) -> list[int]:
    """Part k and everything painted on it (its children, their children)."""
    ids, out = {parts[k]["id"]}, [k]
    for i, p in enumerate(parts):
        if p.get("parent") in ids:
            ids.add(p["id"])
            out.append(i)
    return out


def halo(mask: np.ndarray) -> np.ndarray:
    """The mask grown by HALO: an object's painted edge and soft rim."""
    r = max(2, int(HALO * max(mask.shape)))
    return cv2.dilate(mask.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0


def make_background(finish: np.ndarray, front: np.ndarray, given: np.ndarray) -> np.ndarray:
    """`finish` with what is in `front` taken out: `given` is a render of that, and only its pixels inside `front`
    (grown by HALO) are used, so it can't change anything else. The chain keeps each render this way (erase3)."""
    if not front.any():
        return finish.copy()
    grown = halo(front)  # the object's painted edge and its soft rim go too
    out = finish.copy()
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
    out[grown] = np.clip(fill, 0, 255).astype(np.uint8)[grown]
    return out


ROWS_REACH = 0.03  # behind an object, an area takes rows this far (share of the height) past the rows it has beside it
FAR_ROWS = 0.05  # a back part's paint this far (share of the height) above or below its own outline's rows is reported
FAR_SHARE = 0.001  # ... when it's more than this share of the picture
RIM_REACH = 0.03  # a step's changes this far (share of the long side) past its painted area can only be rims it brings back
CHANGED = 45  # RGB levels a background picture may differ from the finish before a pixel counts as changed
CHANGED_SHARE = 0.25  # more of the scene changed than this, away from the objects, and the render didn't keep it


def visible(plan: dict, owner: np.ndarray, painted: list[np.ndarray]) -> list[np.ndarray]:
    """Of each step's painted area, what the finished painting still shows: the pixels its part (a unit, in the
    plan's version 2 shape), or a child of its part, owns in `owner`. Paint carried under a later part is left out.
    The Where words measure this (#126); the outline on the page stays the painted area, since the painter does
    paint there. A step whose part shows nowhere keeps its painted area."""
    parts = plan["parts"]
    index = {p["id"]: i for i, p in enumerate(parts)}
    out = []
    for s, m in zip(flat_steps(plan), painted):
        seen = m & np.isin(owner, _family(parts, index[s["part"]]))
        out.append(seen if seen.any() else m.copy())
    return out


def _lay(canvas: np.ndarray, paint: np.ndarray, where: np.ndarray) -> np.ndarray:
    """Paint goes on inside `where`, with its edge softened inward only: nothing outside `where` changes."""
    if not where.any():
        return canvas
    a = np.minimum(cv2.GaussianBlur(where.astype(np.float32), (0, 0), FEATHER) * 2.0, 1.0) * where
    a = a[..., None]
    return canvas * (1 - a) + paint.astype(np.float32) * a


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
