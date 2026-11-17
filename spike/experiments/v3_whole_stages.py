"""Spike for #204 (pipeline v3): whole-picture stages. Erase things from the finish one at a time, and show the
erased pictures themselves as the pictures a lesson's stages end on.

Not part of the pipeline. Stage 1 of the issue: one picture (the lake cabin), one step sheet beside v2's.

    python spike/experiments/v3_whole_stages.py units lake-cabin            # the things, in the order they go; no render
    python spike/experiments/v3_whole_stages.py erase lake-cabin            # PAID: one low render a thing, chained
    python spike/experiments/v3_whole_stages.py build lake-cabin            # step pictures and the sheet beside v2's

Words:
    unit      a part of the plan with steps of its own, or several whose steps interleave (the three reflections).
              Units are in the order the lesson paints them.
    P[u]      the picture with every unit after u erased. P[last] is the finish. P[u-1] is made from P[u] by one
              render that removes unit u.
    D[u]      what unit u adds: where that render changed P[u] by a lot (`diff_mask`). No outline model, and the
              baseline run's outlines aren't read (only to measure, in `erase`'s numbers).
    behind    the render paints what's behind the unit (a mountain behind a forest).
    bare      the render leaves bare canvas (the lake: nothing is behind it but canvas). Once bare, always bare in
              every earlier picture.

The guard: P[u-1] is P[u] outside D[u], and the render inside it. Nothing else can move, so a thing can't change
shape when the next one arrives. Steps inside a unit are v2's flat coat and nearest-paint passes, cut from P[u]
inside D[u].

Pictures and numbers go in spike/experiments/bench/runs/whole/<picture>/ (git-ignored).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "spike"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_steps as bs  # noqa: E402
import from_finish as ff  # noqa: E402
import outline as ol  # noqa: E402
import v3_peel as peel  # noqa: E402

OUT = peel.BENCH / "runs" / "whole"

BLUR = 2.5  # pixels: both pictures are softened this much before they're compared, so brushwork drawn again isn't a change
STRONG = 20.0  # Lab units: a pixel that changed this much was removed
WEAK = 9.0  # ... and a pixel that changed this much, joined to one that was, went with it
REACH = 0.04  # how far past the plan's loose box for a thing its change may run, as a share of the long side
SPECK = 0.0002  # a changed patch smaller than this share of the picture is brushwork, not the thing
HOLE = 0.004  # a gap in the change smaller than this share of the picture is the thing too
BARE = 0.5  # a unit with more of its box than this outside every earlier area's cover has only canvas behind it
SMOOTH = bs.SMOOTH


# ---------------------------------------------------------------------------
# The plan's units and loose boxes
# ---------------------------------------------------------------------------


def units(plan: dict) -> list[dict]:
    """The plan's parts grouped into units, in painting order: {"parts": [ids], "steps": [step indexes]}."""
    steps = bs.flat_steps(plan)
    out: list[dict] = []
    seen: dict[str, int] = {}
    for i, s in enumerate(steps):
        if s["part"] in seen:
            u = seen[s["part"]]
            # a step of an earlier unit after other units began: they interleave, so they're one unit
            while len(out) - 1 > u:
                last = out.pop()
                out[-1]["parts"] += last["parts"]
                out[-1]["steps"] += last["steps"]
                for pid in last["parts"]:
                    seen[pid] = len(out) - 1
            out[u]["steps"].append(i)
        else:
            out.append({"parts": [s["part"]], "steps": [i]})
            seen[s["part"]] = len(out) - 1
    for u in out:
        u["steps"].sort()
    return out


def boxes_of(part: dict, covers: bool = False) -> list[list[float]]:
    got = (part.get("covers") if covers else None) or part.get("boxes") or ([part["box"]] if part.get("box") else [])
    return [list(b) for b in got]


def box_mask(boxes: list[list[float]], shape: tuple[int, int], grow: float = 0.0) -> np.ndarray:
    h, w = shape
    out = np.zeros((h, w), bool)
    g = grow * max(h, w)
    for x0, y0, x1, y1 in boxes:
        out[max(0, int(y0 * h - g)):int(np.ceil(y1 * h + g)), max(0, int(x0 * w - g)):int(np.ceil(x1 * w + g))] = True
    return out


def unit_box(plan: dict, unit: dict, shape: tuple[int, int], grow: float = REACH) -> np.ndarray:
    """Where the plan says the unit's parts are, loosely. A part with no box may be anywhere."""
    by_id = {p["id"]: p for p in plan["parts"]}
    out = np.zeros(shape, bool)
    for pid in unit["parts"]:
        b = boxes_of(by_id[pid])
        if not b:
            return np.ones(shape, bool)
        out |= box_mask(b, shape, grow)
    return out


def is_bare(plan: dict, us: list[dict], n: int, shape: tuple[int, int]) -> bool:
    """Has unit n only canvas behind it? Yes when most of its box is outside what the earlier wide areas cover."""
    by_id = {p["id"]: p for p in plan["parts"]}
    covered = np.zeros(shape, bool)
    for u in us[:n]:
        for pid in u["parts"]:
            if by_id[pid].get("kind") == "area":
                covered |= box_mask(boxes_of(by_id[pid], covers=True), shape)
    mine = unit_box(plan, us[n], shape, 0.0)
    return bool(mine.any() and (mine & ~covered).sum() > BARE * mine.sum())


# ---------------------------------------------------------------------------
# The guard: what a render changed by a lot
# ---------------------------------------------------------------------------


def diff_mask(before: np.ndarray, after: np.ndarray, where: np.ndarray | None = None,
              never: np.ndarray | None = None) -> np.ndarray:
    """Where `after` differs from `before` by a lot: every patch that changed by WEAK or more and holds a pixel that
    changed by STRONG or more inside `where` (the plan's loose box), and nothing inside `never`. Small gaps are
    closed and specks dropped."""
    a = ol.lab(cv2.GaussianBlur(before, (0, 0), BLUR)).astype(np.float32)
    b = ol.lab(cv2.GaussianBlur(after, (0, 0), BLUR)).astype(np.float32)
    d = np.sqrt(((a - b) ** 2).sum(2))
    weak, strong = d >= WEAK, d >= STRONG
    if where is not None:
        # the box says where the thing starts, not where it ends: a patch must have removed paint inside the box,
        # and may run past it (the plan's box for the mountain stopped short of its left end, 2026-11-17)
        strong = strong & where
    if never is not None:
        weak, strong = weak & ~never, strong & ~never
    n, labels = cv2.connectedComponents(weak.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    keep[np.unique(labels[strong])] = True
    keep[0] = False
    m = keep[labels]
    area = m.size
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 0
    # holes: patches of no-change walled in by change
    n, labels, stats, _ = cv2.connectedComponentsWithStats((~m).astype(np.uint8), connectivity=4)
    for i in range(1, n):
        x, y, w, h, size = stats[i]
        if size < HOLE * area and x > 0 and y > 0 and x + w < m.shape[1] and y + h < m.shape[0]:
            m[labels == i] = True
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    for i in range(1, n):
        if stats[i][4] < SPECK * area:
            m[labels == i] = False
    if never is not None:
        m &= ~never
    return m


def erase_one(src: np.ndarray, raw: np.ndarray, where: np.ndarray, bare: bool, frozen: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(the picture with the thing erased, what was erased). `frozen` is canvas already bare: it never changes."""
    canvas = np.array(ff.CANVAS, np.uint8)
    d = diff_mask(src, raw, where, frozen)
    if bare:
        out = src.copy()
        out[d] = canvas
        return out, d
    out = bs.make_background(src, d, raw)  # the render inside the change (and its rim), matched in tone around it
    grown = bs.halo(d) & ~frozen
    out[frozen] = canvas
    return out, grown


# ---------------------------------------------------------------------------
# The chain of renders
# ---------------------------------------------------------------------------


def prompt_for(remove: list[str], keep: list[str], bare: bool) -> str:
    if bare:
        return ("This is an unfinished acrylic painting. Remove these things from it completely: " + "; ".join(remove)
                + ". Where they were, leave bare, unpainted white canvas: plain flat white, no paint, no wash, no "
                "sketch lines. Change nothing else: everything that stays (" + "; ".join(keep) + ") keeps its exact "
                "place, shape, and color, and any canvas that is already bare stays bare. No text, signature, or "
                "watermark.")
    return ("This is an unfinished acrylic painting. Remove these things from it completely: " + "; ".join(remove) + ". "
            "Where they were, paint what is behind them: continue what is around them (" + "; ".join(keep) + ") "
            "exactly as it is, in the same colors and the same brushwork. Leave no trace, outline, or shadow of what "
            "you removed. Change nothing else: everything that stays keeps its exact place, shape, and color, and "
            "any bare white canvas stays bare. No text, signature, or watermark.")


def part_names(plan: dict, ids: list[str]) -> list[str]:
    by_id = {p["id"]: p for p in plan["parts"]}
    return [by_id[i].get("name") or i for i in ids]


def erase(picture: str, quality: str = "low", model: str = "gpt-image") -> dict:
    d = peel.load(picture)
    finish, plan, owner = d["finish"], d["plan"], d["owner"]
    us = units(plan)
    index = {p["id"]: i for i, p in enumerate(plan["parts"])}
    shape = finish.shape[:2]
    folder = OUT / picture
    folder.mkdir(parents=True, exist_ok=True)
    canvas = np.array(ff.CANVAS, np.uint8)
    frozen = np.zeros(shape, bool)
    P = {len(us) - 1: finish}
    rows = []
    for n in range(len(us) - 1, 0, -1):
        bare = is_bare(plan, us, n, shape)
        remove = part_names(plan, us[n]["parts"])
        keep = part_names(plan, [pid for u in us[:n] for pid in u["parts"]])
        raw, info = peel.render(model, P[n], prompt_for(remove, keep, bare), folder, f"U{n:02d}", quality)
        P[n - 1], D = erase_one(P[n], raw, unit_box(plan, us[n], shape), bare, frozen)
        if bare:
            frozen |= D
        np.save(folder / f"D{n:02d}.npy", D)
        Image.fromarray(P[n - 1]).save(folder / f"P{n - 1:02d}.png")
        # numbers only: against the baseline run's outline of the same parts (never used to make a picture)
        theirs = np.isin(owner, [index[pid] for pid in us[n]["parts"]])
        both, either = (D & theirs).sum(), (D | theirs).sum()
        rows.append({"unit": n, "parts": us[n]["parts"], "bare": bare, "seconds": info["seconds"],
                     "cost_usd": info["cost_usd"], "erased_share": round(float(D.mean()), 4),
                     "v2_outline_share": round(float(theirs.mean()), 4),
                     "iou_with_v2_outline": round(float(both / max(1, either)), 3),
                     # of v2's outline of the thing, the share the guard left as it was
                     "v2_outline_kept": round(float((theirs & ~D).sum() / max(1, theirs.sum())), 3),
                     "raw_moved_outside": peel.moved(P[n], raw, ~bs.halo(D) & ~frozen)})
        print(json.dumps(rows[-1]))
    D0 = ~frozen  # the first unit: everything that isn't bare canvas when only it is left
    np.save(folder / "D00.npy", D0)
    result = {"picture": picture, "run": d["run"].name, "quality": quality, "model": model,
              "units": us, "renders": len(rows), "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
              "render_seconds": round(sum(r["seconds"] for r in rows), 1), "rows": rows}
    (folder / "erase.json").write_text(json.dumps(result, indent=1))
    chain = [np.full_like(finish, canvas)] + [P[n] for n in range(len(us))]
    raws = [None, None] + [np.array(Image.open(folder / f"U{n:02d}_raw.png").convert("RGB")) for n in range(1, len(us))]
    sheet_rows(folder / "chain.jpg", [chain, raws[1:] + [None]], width=384)
    return result


# ---------------------------------------------------------------------------
# Step pictures
# ---------------------------------------------------------------------------


def nearest(content: np.ndarray, hexes: list[str]) -> np.ndarray:
    lab = ol.lab(cv2.GaussianBlur(content, (0, 0), 1.0))
    dist = np.stack([np.sqrt(((lab - ff.hex_lab(h)) ** 2).sum(2)) for h in hexes])
    return cv2.medianBlur(dist.argmin(0).astype(np.uint8), SMOOTH)


def split(plan: dict, unit: dict, content: np.ndarray, D: np.ndarray, paints_of: dict[str, list[str]],
          hexes: dict[str, str]) -> dict[str, np.ndarray]:
    """Which of a unit's parts each pixel of D is. One part: all of it. Several (the reflections): the part that
    names the paint nearest the pixel; a paint two parts name goes to the one whose loose box holds the pixel."""
    ids = unit["parts"]
    if len(ids) == 1:
        return {ids[0]: D}
    by_id = {p["id"]: p for p in plan["parts"]}
    names = sorted({n for pid in ids for n in paints_of.get(pid, [])})
    near = nearest(content, [hexes[n] for n in names])
    inside = {pid: box_mask(boxes_of(by_id[pid]), D.shape) if boxes_of(by_id[pid]) else np.ones(D.shape, bool) for pid in ids}
    size = {pid: inside[pid].sum() for pid in ids}
    out = {pid: np.zeros(D.shape, bool) for pid in ids}
    left = D.copy()
    for j, name in enumerate(names):
        mine = left & (near == j)
        users = sorted([pid for pid in ids if name in paints_of.get(pid, [])], key=lambda pid: size[pid])
        for pid in users[:-1]:  # smallest box first
            got = mine & inside[pid]
            out[pid] |= got
            mine &= ~got
        out[users[-1]] |= mine
    return out


def build(picture: str) -> tuple[list[np.ndarray], list[dict], dict]:
    d = peel.load(picture)
    finish, plan = d["finish"], d["plan"]
    folder = OUT / picture
    us = units(plan)
    steps = bs.flat_steps(plan)
    hexes = {p["id"]: p["hex"] for p in plan["paints"]}
    paints_of: dict[str, list[str]] = {}
    for s in steps:
        for c in s.get("paints") or []:
            if c not in paints_of.setdefault(s["part"], []):
                paints_of[s["part"]].append(c)
    last_of = {s["part"]: i for i, s in enumerate(steps)}
    canvas = np.empty(finish.shape, np.float32)
    canvas[:] = ff.CANVAS
    pictures: list[np.ndarray | None] = [None] * len(steps)
    rows: list[dict | None] = [None] * len(steps)
    for n, u in enumerate(us):
        content = finish if n == len(us) - 1 else np.array(Image.open(folder / f"P{n:02d}.png").convert("RGB"))
        D = np.load(folder / f"D{n:02d}.npy")
        masks = split(plan, u, content, D, paints_of, hexes)
        near = {pid: nearest(content, [hexes[c] for c in paints_of[pid]]) for pid in u["parts"] if paints_of.get(pid)}
        for i in u["steps"]:
            s = steps[i]
            pid, show, m = s["part"], s.get("show", "full"), masks[s["part"]]
            before = canvas.copy()
            if i == u["steps"][-1]:
                lay, where = content, D  # the unit's last step: the whole erased picture, exactly
            elif show == "flat":
                lay, where = ff.flat_paint(content, m, [hexes[c] for c in s["paints"]]), m
            elif show == "pass" and last_of[pid] != i:
                lay, where = content, m & np.isin(near[pid], [paints_of[pid].index(c) for c in s["paints"]])
            else:
                lay, where = content, m
            canvas = bs._lay(canvas, lay, where)
            changed = np.abs(canvas - before).max(2) > 6
            rows[i] = {"id": s["id"], "part": pid, "unit": n, "show": show, "painted": round(float(where.mean()), 4),
                       "outside_unit": round(float((changed & ~bs.halo(D)).mean()), 5)}
            pictures[i] = np.clip(canvas, 0, 255).astype(np.uint8)
    gap = np.abs(pictures[-1].astype(np.int16) - finish.astype(np.int16)).max(2) > peel.MOVED
    info = {"picture": picture, "steps": len(steps), "final_gap": round(float(gap.mean()), 4),
            "outside_unit_max": max(r["outside_unit"] for r in rows), "rows": rows}
    out = folder / "steps"
    out.mkdir(exist_ok=True)
    for i, (s, img) in enumerate(zip(steps, pictures)):
        Image.fromarray(img).save(out / f"{i + 1:02d}_{s['id']}.png")
    (folder / "build.json").write_text(json.dumps(info, indent=1))
    theirs = [np.array(Image.open(d["run"] / f"{i + 1:02d}_{s['id']}.png").convert("RGB")) for i, s in enumerate(steps)]
    labels = [f"{i + 1} {s['id']}" for i, s in enumerate(steps)]
    compare_sheet(folder / "steps.jpg", theirs, pictures, labels)
    return pictures, rows, info


# ---------------------------------------------------------------------------
# Sheets to look at
# ---------------------------------------------------------------------------


def _small(img: np.ndarray | None, width: int, like: np.ndarray) -> np.ndarray:
    h = int(like.shape[0] * width / like.shape[1])
    if img is None:
        return np.full((h, width, 3), 255, np.uint8)
    return cv2.resize(img, (width, h), interpolation=cv2.INTER_AREA)


def sheet_rows(path: Path, rows: list[list[np.ndarray | None]], width: int = 384) -> None:
    like = next(x for x in rows[0] if x is not None)
    n = max(len(r) for r in rows)
    grid = [np.hstack([_small(r[i] if i < len(r) else None, width, like) for i in range(n)]) for r in rows]
    Image.fromarray(np.vstack(grid)).save(path, quality=88)


def compare_sheet(path: Path, theirs: list[np.ndarray], ours: list[np.ndarray], labels: list[str],
                  per_row: int = 6, width: int = 420) -> None:
    """v2's step pictures above, this spike's below, the same steps, a label over each pair."""
    like = theirs[0]
    gap = 6
    bands = []
    for start in range(0, len(theirs), per_row):
        cells = []
        for i in range(start, start + per_row):
            a = _small(theirs[i] if i < len(theirs) else None, width, like)
            b = _small(ours[i] if i < len(ours) else None, width, like)
            bar = np.full((34, width, 3), 40, np.uint8)
            if i < len(labels):
                cv2.putText(bar, labels[i], (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 1, cv2.LINE_AA)
            tag_a, tag_b = a.copy(), b.copy()
            if i < len(theirs):
                for img, tag in ((tag_a, "v2"), (tag_b, "whole stages")):
                    cv2.rectangle(img, (0, 0), (12 + 11 * len(tag), 24), (40, 40, 40), -1)
                    cv2.putText(img, tag, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            cell = np.vstack([bar, tag_a, np.full((gap, width, 3), 40, np.uint8), tag_b])
            cells.append(np.hstack([cell, np.full((cell.shape[0], gap, 3), 40, np.uint8)]))
        bands.append(np.hstack(cells))
        bands.append(np.full((gap * 3, bands[-1].shape[1], 3), 40, np.uint8))
    Image.fromarray(np.vstack(bands[:-1])).save(path, quality=88)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("units", "erase", "build"):
        p = sub.add_parser(name)
        p.add_argument("picture")
        if name == "erase":
            p.add_argument("--quality", default="low")
    args = ap.parse_args()
    if args.cmd == "units":
        d = peel.load(args.picture)
        us = units(d["plan"])
        for n, u in enumerate(us):
            how = "first" if n == 0 else ("bare" if is_bare(d["plan"], us, n, d["finish"].shape[:2]) else "behind")
            print(n, how, u["parts"], [s + 1 for s in u["steps"]])
    elif args.cmd == "erase":
        r = erase(args.picture, args.quality)
        print(json.dumps({k: r[k] for k in ("renders", "cost_usd", "render_seconds")}))
    else:
        _, _, info = build(args.picture)
        print(json.dumps({k: info[k] for k in ("steps", "final_gap", "outside_unit_max")}))


if __name__ == "__main__":
    main()
