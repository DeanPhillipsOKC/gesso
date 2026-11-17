"""Spike for #166 (pipeline v3, S1): peel the finish backward with the image model to get complete layers.

Not part of the pipeline. It takes a bench picture's frozen finish and the parts and outlines of its v2 baseline run,
and asks the image model to un-paint the things in front, a level at a time, keeping only the pixels inside what was
removed (build_steps.make_background, the guard v2's one background render already uses):

    python spike/experiments/v3_peel.py levels highland-cow                       # the levels, no render
    python spike/experiments/v3_peel.py peel highland-cow --mode chained --quality low     # PAID: one render a level
    python spike/experiments/v3_peel.py peel all4 --mode parallel --quality low
    python spike/experiments/v3_peel.py build highland-cow --variant chained-low  # step pictures from the layers
    python spike/experiments/v3_peel.py table                                     # the write-up's tables

Words:
    level     the parts behind everything (areas, and marks listed before the first object) are level 0. A thing in
              front (an object or thin part with no parent, with what's painted on it) is level 1, or one more than
              the highest earlier thing in front it touches. Things of one level don't touch, so one render takes
              them all out.
    P[L]      the picture with every level above L un-painted. P[top] is the finish; P[0] has nothing in front.
    chained   P[L-1] is made from P[L]: remove level L. One render after another.
    parallel  every P[L] is made from the finish: remove every level above L. All renders at once.

The pictures and the numbers go in spike/experiments/bench/runs/peel/<variant>/<picture>/ (git-ignored); `table`
reads the peel.json files there. docs/spikes/v3-peel.md has the results.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "spike"))

import build_steps as bs  # noqa: E402
import from_finish as ff  # noqa: E402
import outline as ol  # noqa: E402
import run as gesso_run  # noqa: E402

BENCH = ROOT / "spike" / "experiments" / "bench"
OUT = BENCH / "runs" / "peel"
RUNS = Path("/home/user/gesso-baseline/output")  # the v2 baseline runs (docs/spikes/v3-yardstick.md, section 5)
ALL4 = ["highland-cow", "sleeping-cat", "lake-cabin", "birch-grove"]  # the owner's four lowest baseline scores

TOUCH = 0.008  # things in front this near each other (share of the long side, build_steps.HALO) are on different levels
MOVED = 24  # RGB levels: a pixel this far from what it was has changed (build_steps' final_gap uses the same)
SEEN = 8.0  # Lab units the two sides of an edge differ by in the finish before the edge counts (build_steps.GHOST_SEEN)
PLAIN, FAINT = 0.4, 0.25  # how much of that difference still shows: plainly, at all (GHOST_PART, GHOST_FAINT)


# ---------------------------------------------------------------------------
# The picture, its parts, and the levels
# ---------------------------------------------------------------------------


def baseline_run(picture: str, runs: Path = RUNS) -> Path:
    key = json.loads((BENCH / "baseline" / "key.json").read_text())["packets"]
    folder = next(v["lesson"] for v in key.values() if v["picture"] == picture)
    return runs / folder


def load(picture: str, runs: Path = RUNS) -> dict:
    """The frozen finish, and the baseline run's parts and outlines (the run was cut from the same finish)."""
    run = baseline_run(picture, runs)
    finish = np.array(Image.open(BENCH / "pictures" / picture / "99_finish.png").convert("RGB"))
    plan = json.loads((run / "plan.json").read_text())
    owner = np.array(Image.open(run / "parts" / "owner.png")).astype(np.int32)
    if owner.shape != finish.shape[:2]:
        raise SystemExit(f"{picture}: the baseline's outlines aren't the frozen finish's size")
    return {"picture": picture, "run": run, "finish": finish, "plan": plan, "owner": owner}


def levels(parts: list[dict], owner: np.ndarray, deep: bool = False) -> np.ndarray:
    """Each part's level (see the top of this file). `deep`: the parts behind get levels too, by the same rule (a
    sky 0, the mountain on it 1, the forest on that 2), so a render also takes a forest off its mountain."""
    roots = np.array(bs._roots(parts))
    is_back = bs.back_parts(parts)
    r = max(2, int(TOUCH * max(owner.shape)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    level = np.zeros(len(parts), int)
    grown: dict[int, np.ndarray] = {}
    for g in sorted(set(roots if deep else roots[~is_back])):
        mine = np.isin(owner, np.flatnonzero(roots == g))
        level[roots == g] = 1 + max([level[q] for q, m in grown.items() if (m & mine).any()], default=-1 if deep else 0)
        grown[g] = cv2.dilate(mine.astype(np.uint8), kernel) > 0
    return level


def names(parts: list[dict], which: np.ndarray) -> list[str]:
    return [p.get("name") or p["id"] for p, on in zip(parts, which) if on and not p.get("parent")]


# ---------------------------------------------------------------------------
# One render
# ---------------------------------------------------------------------------


def prompt_for(remove: list[str], keep: list[str]) -> str:
    """The words v2's background tool uses (tools.background_tool), with what to remove and what stays."""
    return ("This is an acrylic painting. Remove these things from it completely: " + "; ".join(remove) + ". "
            "Where they were, paint what is behind them: continue what is around them (" + "; ".join(keep) + ") exactly "
            "as it is, in the same colors and the same brushwork. Leave no trace, outline, or shadow of what you "
            "removed. Change nothing else: everything that stays keeps its exact place, shape, and color. "
            "No text, signature, or watermark.")


def render_gpt(src: Path, prompt: str, out: Path, quality: str) -> dict:
    ledger = gesso_run.Ledger()
    gesso_run.edit_image("peel", [src], prompt, out, gesso_run.size_for(src), quality, ledger)
    call = ledger.calls[-1]
    return {"seconds": call["seconds"], "cost_usd": call["cost_usd"]}


RENDERERS = {"gpt-image": render_gpt}


def render(model: str, picture: np.ndarray, prompt: str, folder: Path, name: str, quality: str) -> tuple[np.ndarray, dict]:
    """The model's answer at the picture's size, and its seconds and cost. A render already in the folder is kept
    (delete it to render again)."""
    src, raw, meta = folder / f"{name}_in.png", folder / f"{name}_raw.png", folder / f"{name}.json"
    if not (raw.exists() and meta.exists()):
        Image.fromarray(picture).save(src)
        info = RENDERERS[model](src, prompt, raw, quality)
        meta.write_text(json.dumps({**info, "prompt": prompt, "model": model, "quality": quality}, indent=1))
    got = np.array(Image.open(raw).convert("RGB"))
    if got.shape != picture.shape:
        got = cv2.resize(got, (picture.shape[1], picture.shape[0]), interpolation=cv2.INTER_AREA)
    return got, json.loads(meta.read_text())


# ---------------------------------------------------------------------------
# Measures
# ---------------------------------------------------------------------------


def edge_left(finish: np.ndarray, peeled: np.ndarray, gone: np.ndarray) -> dict:
    """How much of the removed things' edge the peeled picture still shows (build_steps.ghosts' measure, on a whole
    picture): of the stretches of edge where the finish's two sides differ by SEEN or more, the share where the
    peeled picture shows PLAIN of that difference or more (`edge`) and FAINT or more (`faint`)."""
    r = max(2, int(bs.GHOST_BAND * max(gone.shape)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    g = gone.astype(np.uint8)
    inner, outer = gone & ~(cv2.erode(g, kernel) > 0), (cv2.dilate(g, kernel) > 0) & ~gone
    line = (cv2.dilate(g, np.ones((3, 3), np.uint8)) > 0) & ~gone

    def sides(img: np.ndarray) -> np.ndarray:
        L = ol.lab(cv2.GaussianBlur(img, (0, 0), 1.2))
        a, sa = ff._fill_from(L, inner, r)
        b, sb = ff._fill_from(L, outer, r)
        return np.where((sa > 0.05) & (sb > 0.05), np.sqrt(((a - b) ** 2).sum(2)), 0)

    was, now = sides(finish)[line], sides(peeled)[line]
    counted = was >= SEEN
    if not counted.any():
        return {"edge": 0.0, "faint": 0.0}
    return {"edge": round(float((now[counted] >= PLAIN * was[counted]).mean()), 3),
            "faint": round(float((now[counted] >= FAINT * was[counted]).mean()), 3)}


def moved(a: np.ndarray, b: np.ndarray, where: np.ndarray, by: int = MOVED) -> float:
    if not where.any():
        return 0.0
    return round(float((np.abs(a.astype(np.int16) - b.astype(np.int16)).max(2)[where] > by).mean()), 4)


# ---------------------------------------------------------------------------
# Peel
# ---------------------------------------------------------------------------


def peel(picture: str, mode: str, quality: str, model: str = "gpt-image", runs: Path = RUNS, deep: bool = False) -> dict:
    d = load(picture, runs)
    finish, parts, owner = d["finish"], d["plan"]["parts"], d["owner"]
    level = levels(parts, owner, deep)
    top = int(level.max())
    variant = ("deep-" if deep else "") + f"{mode}-{quality}" + ("" if model == "gpt-image" else f"-{model}")
    folder = OUT / variant / picture
    folder.mkdir(parents=True, exist_ok=True)
    gone = {L: level[owner] > L for L in range(top)}  # what P[L] has had removed
    P = {top: finish}
    raws: dict[int, np.ndarray] = {}
    rows = []
    started = time.time()

    def one(L: int, src: np.ndarray, taken: np.ndarray) -> tuple[np.ndarray, dict]:
        """P[L] from `src`, with `taken` removed."""
        out_levels = (level == L + 1) if mode == "chained" else (level > L)
        text = prompt_for(names(parts, out_levels), names(parts, level <= L))
        raw, info = render(model, src, text, folder, f"P{L}", quality)
        # did it take them out? Judged on what this render was asked to remove and could see: in a chained peel
        # the rest of the hole was already cleared, and looks the same on purpose
        asked = taken & (level[owner] == L + 1) if mode == "chained" else taken
        fixes, numbers = bs.background_problems(src, raw, asked)
        numbers["changed_share"] = bs.background_problems(src, raw, taken)[1]["changed_share"]
        return raw, {"level": L, "removed": names(parts, out_levels), "hole_share": round(float(taken.mean()), 4),
                     **info, **numbers,
                     # what the guard throws away: the raw render against what it was given, away from the hole
                     "raw_moved": moved(src, raw, ~bs.halo(bs.halo(taken))), "render_problems": fixes}

    if mode == "chained":
        for L in range(top - 1, -1, -1):
            # The hole is everything above L, not only level L+1: what level L+1 has under the levels already
            # removed (the blanket under the cat) was painted by the last render and has no outline, so a hole of
            # level L+1's own outline left it standing (the first try, 2026-11-17).
            raws[L], row = one(L, P[L + 1], gone[L])
            P[L] = bs.make_background(P[L + 1], gone[L], raws[L])
            rows.append(row)
    else:
        with concurrent.futures.ThreadPoolExecutor(max(1, top)) as pool:
            jobs = {L: pool.submit(one, L, finish, gone[L]) for L in range(top)}
            for L in range(top - 1, -1, -1):
                raws[L], row = jobs[L].result()
                P[L] = bs.make_background(finish, gone[L], raws[L])
                rows.append(row)
    wall = time.time() - started

    for row in rows:
        L = row["level"]
        Image.fromarray(P[L]).save(folder / f"P{L}.png")
        row.update(edge_left(finish, P[L], level[owner] == L + 1))
        # Under the levels above L+1, P[L] and P[L+1] are two renders of the same place. Whatever differs there and
        # isn't level L+1's own paint is a change outside the layer (check 2), before `layers` settles it.
        under = level[owner] > L + 1
        row["under_share"] = round(float(under.mean()), 4)
        row["under_moved"] = moved(P[L], P[L + 1], under)
    result = {"picture": picture, "variant": variant, "mode": mode, "deep": deep, "quality": quality, "model": model,
              "run": d["run"].name, "levels": top,
              "level_of": {p["id"]: int(v) for p, v in zip(parts, level)},
              "renders": len(rows), "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
              "render_seconds": round(sum(r["seconds"] for r in rows), 1),
              "wall_seconds": round(wall if all("cached" not in r for r in rows) else 0.0, 1),
              # check 1: every layer on, the picture is the finish
              "stack_gap": moved(P[top], finish, np.ones(owner.shape, bool)),
              "rows": rows}
    old = folder / "peel.json"
    if old.exists():  # a second run reads the renders from the folder: keep the first run's wall time
        before = json.loads(old.read_text())
        if wall < 2:
            result["wall_seconds"] = before["wall_seconds"]
    old.write_text(json.dumps(result, indent=1))
    sheet(folder, [P[L] for L in range(top + 1)], [raws.get(L) for L in range(top + 1)])
    return result


def sheet(folder: Path, pictures: list[np.ndarray], raws: list[np.ndarray | None], width: int = 480) -> None:
    """One sheet to Read: top row the peeled pictures P[0] to the finish, bottom row each raw render."""
    def small(img):
        h = int(img.shape[0] * width / img.shape[1])
        return cv2.resize(img, (width, h), interpolation=cv2.INTER_AREA)

    blank = np.full_like(small(pictures[0]), 255)
    top = np.hstack([small(p) for p in pictures])
    bottom = np.hstack([small(r) if r is not None else blank for r in raws])
    Image.fromarray(np.vstack([top, bottom])).save(folder / "sheet.jpg", quality=88)


def probe(picture: str, remove: list[str], quality: str = "low", model: str = "gpt-image") -> dict:
    """PAID, one render: the finish with the named parts (and what's painted on them) removed, whatever their
    level. For a look at peeling the parts behind too (a forest off its mountain), which `peel` doesn't do."""
    d = load(picture)
    parts, owner = d["plan"]["parts"], d["owner"]
    roots = np.array(bs._roots(parts))
    out = np.array([parts[r]["id"] in remove for r in roots])
    taken = out[owner]
    folder = OUT / "probe" / picture
    folder.mkdir(parents=True, exist_ok=True)
    name = "-".join(remove)
    raw, info = render(model, d["finish"], prompt_for(names(parts, out), names(parts, ~out)), folder, name, quality)
    got = bs.make_background(d["finish"], taken, raw)
    Image.fromarray(got).save(folder / f"{name}.png")
    sheet(folder, [got, d["finish"]], [raw, None])
    (folder / "sheet.jpg").rename(folder / f"{name}_sheet.jpg")
    _, numbers = bs.background_problems(d["finish"], raw, taken)
    return {"picture": picture, "removed": remove, "hole_share": round(float(taken.mean()), 4),
            "seconds": info["seconds"], "cost_usd": info["cost_usd"], **numbers,
            **edge_left(d["finish"], got, taken)}


# ---------------------------------------------------------------------------
# Layers: who owns each pixel of a peeled picture
# ---------------------------------------------------------------------------


def owners(d: dict, P: dict[int, np.ndarray], level: np.ndarray, sam=None, given=None) -> dict[int, np.ndarray]:
    """For every level L, the part that owns each pixel of P[L]. Where the finish shows a part of level L or lower,
    its outline stands. Where a thing in front above L was removed, P[L] is a complete painting of what's left, so
    it's outlined the way a finish is: the same tool (outline.outline), the plan's own boxes and points, only the
    parts of level L and lower. No fill rule and no dividing by rows or colors.

    Where a part behind above L was removed (deep levels: the lake off the forest's foot), the pixel stays that
    part's. Parts behind lie side by side more than over each other, and the render there is mostly invented (a
    shore where the lake was): a part behind keeps v2's painted area, its outline and a little under the next
    edge or its `covers`, and takes only that area's pixels from its level's picture (build)."""
    parts, owner = d["plan"]["parts"], d["owner"]
    top = int(level.max())
    out = {top: owner}
    is_back = bs.back_parts(parts)
    if given is None:  # `given`: ready-made outlines by part id in place of the model (tests)
        sam = sam or ol.Sam()
    for L in range(top):
        keep = np.flatnonzero(level <= L)
        if sam is not None:
            sam.emb = None
        _, fresh, _ = ol.outline(P[L], [parts[k] for k in keep], sam, given)
        out[L] = np.where((level[owner] <= L) | is_back[owner], owner, keep[fresh]).astype(np.int32)
    return out


# ---------------------------------------------------------------------------
# Step pictures from the layers
# ---------------------------------------------------------------------------


def build(d: dict, P: dict[int, np.ndarray], level: np.ndarray, own: dict[int, np.ndarray]):
    """(pictures, rows, painted), as build_steps.build gives them, with every part cut from its own level's peeled
    picture: part k's paint is P[level of k], whole under everything above it. What a step does inside its part
    (flat, pass, full) is v2's, unchanged (stages inside a part are #169). So is what a part has under its own
    children and under the next part's edge (build_steps._prepare); only what's behind and under things in front
    is new.

    This is build_steps._build's loop with two changes: a part reads its level's picture and owner map instead of
    the finish's (or the one background's), and a step never paints over a thing of a higher level that's already
    painted (v2 let a back part listed after an object paint over it)."""
    finish, plan, owner = d["finish"], d["plan"], d["owner"]
    parts, steps = plan["parts"], bs.flat_steps(plan)
    index = {p["id"]: i for i, p in enumerate(parts)}
    hexes = {p["id"]: p["hex"] for p in plan["paints"]}
    h, w = owner.shape
    long_side = max(h, w)
    is_back = bs.back_parts(parts)
    none = np.zeros((h, w), bool)
    pre = {L: {"finish": P[L], "owner": own[L], "is_back": is_back, "base_back": P[L], "own_back": own[L],
               "real_background": True, "doubt": none, "opened": none, "front_grown": none} for L in P}
    last_of = {s["part"]: i for i, s in enumerate(steps)}
    paints_of: dict[str, list[str]] = {}
    for s in steps:
        for c in s.get("paints") or []:
            if c not in paints_of.setdefault(s["part"], []):
                paints_of[s["part"]].append(c)
    prep: dict[int, dict] = {}
    coated = np.zeros(len(parts), bool)
    detailed: dict[int, np.ndarray] = {}
    top_part = np.full((h, w), -1, np.int32)
    canvas = np.empty((h, w, 3), np.float32)
    canvas[:] = ff.CANVAS
    started = np.zeros(len(parts), bool)
    pictures, rows, painted = [], [], []
    for i, s in enumerate(steps):
        k = index[s["part"]]
        L = int(level[k])
        names_k = paints_of.get(parts[k]["id"]) or []
        if k not in prep:
            prep[k] = bs._prepare(pre[L], parts, k, names_k, hexes)
            if is_back[k] and names_k is not None:
                # under the parts behind that were removed, the part's paint is the render's, not v2's fill
                r = prep[k]
                fix = (level[owner] > L) & is_back[owner] & r["area"]
                if fix.any():
                    r["content"] = np.where(fix[..., None], P[L], r["content"])
                    if names_k:
                        lab = ol.lab(cv2.GaussianBlur(r["content"], (0, 0), 1.0))
                        dist = np.stack([np.sqrt(((lab - ff.hex_lab(hexes[n])) ** 2).sum(2)) for n in names_k])
                        r["nearest"] = cv2.medianBlur(dist.argmin(0).astype(np.uint8), bs.SMOOTH)
                r["filled"] = round(float(fix.mean()), 4)
        r = prep[k]
        blocked = np.zeros((h, w), bool)
        for q in np.flatnonzero(started):
            if q > k or level[q] > L:
                blocked |= own[int(level[q])] == q
        target = r["area"] & ~blocked
        show = s.get("show", "full")
        if show == "flat":
            lay, where = ff.flat_paint(r["content"], r["area"], [hexes[n] for n in s["paints"]]), target
            coated[k] = True
        elif show == "pass" and last_of[s["part"]] != i:
            pick = np.isin(r["nearest"], [names_k.index(n) for n in s["paints"]])
            lay, where = r["content"], target & pick
        else:
            lay, where = r["content"], target
        if show != "flat":
            g = r["rim_group"]
            back = (g >= 0) & started[np.maximum(g, 0)]
            if back.any():
                lay = np.where(back[..., None], r["base_of"], lay)
        if coated[k] and show != "flat":
            where = where & ~r["kids"]
        before = canvas.copy()
        rim = np.zeros((h, w), bool)
        if L > 0 and not started[k]:
            # the rim around a thing in front was cleared with it in every picture below its level
            rim = bs.halo(np.isin(own[L], r["family"])) & ~blocked
            canvas = bs._lay(canvas, P[L], rim)
        if not started[k]:
            for j, rj in prep.items():
                back = (rj["rim_group"] == k) & (top_part == j) & detailed.get(j, False)
                if np.any(back):
                    canvas = bs._lay(canvas, rj["base_of"], back)
                    rim = rim | back
        canvas = bs._lay(canvas, lay, where)
        top_part[where] = k
        if show != "flat":
            detailed[k] = detailed.get(k, np.zeros((h, w), bool)) | where
        started[k] = True
        changed = np.abs(canvas - before).max(2) > 6
        near = cv2.dilate(r["area"].astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        rows.append({"id": s["id"], "part": s["part"], "show": show, "level": L,
                     "painted": round(float(where.mean()), 4), "changed": round(float(changed.mean()), 4),
                     "outside": round(float((changed & ~near & ~(rim & bs._grow(r["area"], bs.RIM_REACH * long_side))).mean()), 5)})
        pictures.append(np.clip(canvas, 0, 255).astype(np.uint8))
        painted.append(where | rim)
    gap = np.abs(pictures[-1].astype(np.int16) - finish.astype(np.int16)).max(2) > MOVED
    for row, g in zip(rows, bs.ghosts(finish, parts, owner, steps, pictures, painted)):
        row["ghosts"] = g
        row["final_gap"] = round(float(gap.mean()), 4)
    pictures[-1] = finish.copy()
    return pictures, rows, painted


def baseline_rows(d: dict) -> list[dict]:
    """v2's own numbers for the same plan, outlines and finish, with the baseline run's background render."""
    plate = d["run"] / "98_background.png"
    background = np.array(Image.open(plate).convert("RGB")) if plate.exists() else None
    return bs.build(d["finish"], d["plan"], d["owner"], background)[1]


def ghost_sum(rows: list[dict]) -> dict:
    """A lesson's ghosts in three numbers: steps that show a part before its step plainly (edge over
    build_steps.GHOST_EDGE), the worst edge, and every listed part-and-step added up."""
    listed = [g for r in rows for g in r.get("ghosts") or []]
    return {"steps_with_plain_ghost": sum(any(g["edge"] >= bs.GHOST_EDGE for g in r.get("ghosts") or []) for r in rows),
            "worst_edge": max([g["edge"] for g in listed], default=0.0),
            "edge_sum": round(sum(g["edge"] for g in listed), 2), "listed": len(listed),
            "outside_max": max(r["outside"] for r in rows), "final_gap": rows[-1]["final_gap"]}


def build_lesson(picture: str, variant: str, runs: Path = RUNS, sam=None) -> dict:
    """The baseline lesson with its step pictures cut from the peeled layers: a copy of the run in
    runs/peel/<variant>/lessons/, same plan, paints and words, so the A/B page and the fault counter see one change."""
    d = load(picture, runs)
    folder = OUT / variant / picture
    info = json.loads((folder / "peel.json").read_text())
    parts = d["plan"]["parts"]
    level = np.array([info["level_of"][p["id"]] for p in parts])
    top = int(level.max())
    P = {L: np.array(Image.open(folder / f"P{L}.png").convert("RGB")) for L in range(top)}
    P[top] = d["finish"]
    started = time.time()
    own = owners(d, P, level, sam)
    outline_s = time.time() - started
    started = time.time()
    pictures, rows, _ = build(d, P, level, own)
    build_s = time.time() - started
    for L in range(top):
        Image.fromarray(ol.preview(P[L], parts, own[L])).save(folder / f"owner{L}.jpg", quality=85)
    lesson = OUT / variant / "lessons" / f"{d['run'].name}"
    if lesson.exists():
        shutil.rmtree(lesson)
    shutil.copytree(d["run"], lesson, ignore=shutil.ignore_patterns("trials", "versions", "busy", "embed", "*.html"))
    box = (json.loads((lesson / "canvas.json").read_text()).get("canvas_box") or [0, 0, 1, 1]) \
        if (lesson / "canvas.json").exists() else [0, 0, 1, 1]
    h, w = d["owner"].shape
    x0, y0, x1, y1 = round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h)
    for i, (s, img) in enumerate(zip(bs.flat_steps(d["plan"]), pictures)):
        name = f"{i + 1:02d}_{s['id']}.png"
        Image.fromarray(img).save(lesson / name)
        if (lesson / "canvas" / name).exists():
            Image.fromarray(img[y0:y1, x0:x1]).save(lesson / "canvas" / name)
    Image.fromarray(bs.contact_sheet(pictures, bs.flat_steps(d["plan"]))).save(folder / "steps.jpg", quality=88)
    result = {"picture": picture, "variant": variant, "lesson": str(lesson.relative_to(ROOT)),
              "outline_seconds": round(outline_s, 1), "build_seconds": round(build_s, 1),
              "peel": ghost_sum(rows), "v2": ghost_sum(baseline_rows(d)), "rows": rows}
    (folder / "build.json").write_text(json.dumps(result, indent=1))
    return result


# ---------------------------------------------------------------------------
# The write-up's numbers and pictures
# ---------------------------------------------------------------------------

RESULTS = Path(__file__).with_suffix(".json")


def results() -> dict:
    """Every variant's numbers, from the peel.json and build.json files under runs/peel/, one row a picture."""
    out: dict[str, list[dict]] = {}
    for path in sorted(OUT.glob("*/*/peel.json")):
        p = json.loads(path.read_text())
        rows = p["rows"]
        row = {"picture": p["picture"], "levels": p["levels"], "renders": p["renders"], "cost_usd": p["cost_usd"],
               "render_seconds": p["render_seconds"], "wall_seconds": p["wall_seconds"],
               "stack_gap": p["stack_gap"],
               "raw_moved": round(sum(r["raw_moved"] for r in rows) / len(rows), 3),
               "not_removed": max(r["objects_left"] for r in rows),
               "failed_renders": sum(bool(r["render_problems"]) for r in rows),
               "edge_left": max(r["edge"] for r in rows), "faint_left": max(r["faint"] for r in rows),
               "under_moved": max(r["under_moved"] for r in rows)}
        built = path.with_name("build.json")
        if built.exists():
            b = json.loads(built.read_text())
            row.update({"outline_seconds": b["outline_seconds"], "build_seconds": b["build_seconds"],
                        "steps": len(b["rows"]), "outside_max": b["peel"]["outside_max"],
                        "final_gap": b["peel"]["final_gap"], "ghost_steps": b["peel"]["steps_with_plain_ghost"],
                        "ghosts_listed": b["peel"]["listed"], "v2_final_gap": b["v2"]["final_gap"],
                        "v2_ghost_steps": b["v2"]["steps_with_plain_ghost"], "v2_ghosts_listed": b["v2"]["listed"]})
        out.setdefault(p["variant"], []).append(row)
    return out


def compare(picture: str, variant: str, steps: list[int], out: Path, width: int = 420) -> None:
    """A picture for the write-up: the chosen steps of the v2 baseline (top row) over the same steps built from the
    peel (bottom row)."""
    d = load(picture)
    ids = [s["id"] for s in bs.flat_steps(d["plan"])]
    lesson = OUT / variant / "lessons" / d["run"].name

    def row(folder: Path) -> np.ndarray:
        tiles = []
        for n in steps:
            img = np.array(Image.open(folder / f"{n:02d}_{ids[n - 1]}.png").convert("RGB"))
            tiles.append(cv2.resize(img, (width, int(img.shape[0] * width / img.shape[1])), interpolation=cv2.INTER_AREA))
        return np.hstack(tiles)

    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.vstack([row(d["run"]), row(lesson)])).save(out, quality=85)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def pictures_of(arg: str) -> list[str]:
    return ALL4 if arg == "all4" else arg.split(",")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("levels")
    p.add_argument("picture")
    p = sub.add_parser("peel", help="PAID: one render per level")
    p.add_argument("picture")
    p.add_argument("--mode", choices=["chained", "parallel"], required=True)
    p.add_argument("--quality", choices=["low", "medium"], default="low")
    p.add_argument("--model", choices=sorted(RENDERERS), default="gpt-image")
    p.add_argument("--deep", action="store_true", help="give the parts behind levels too")
    p = sub.add_parser("build", help="step pictures from the peeled layers, as a copy of the baseline lesson")
    p.add_argument("picture")
    p.add_argument("--variant", required=True)
    p = sub.add_parser("probe", help="PAID, one render: the finish with the named parts removed")
    p.add_argument("picture")
    p.add_argument("--remove", required=True, help="part ids, comma-separated (parts with no parent)")
    sub.add_parser("results", help="write v3_peel.json from the runs")
    p = sub.add_parser("compare", help="a picture for the write-up: v2's steps over the peel's")
    p.add_argument("picture")
    p.add_argument("--variant", required=True)
    p.add_argument("--steps", required=True)
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "levels":
        for name in pictures_of(a.picture):
            d = load(name)
            for deep in (False, True):
              level = levels(d["plan"]["parts"], d["owner"], deep)
              print(json.dumps({"picture": name, "deep": deep, "levels": int(level.max()),
                                "level_of": {p["id"]: int(v) for p, v in zip(d["plan"]["parts"], level)}}))
            continue
            print(json.dumps({"picture": name, "levels": int(level.max()),
                              "level_of": {p["id"]: int(v) for p, v in zip(d["plan"]["parts"], level)},
                              "front_share": round(float((level[d["owner"]] > 0).mean()), 3)}))
    elif a.cmd == "peel":
        for name in pictures_of(a.picture):
            r = peel(name, a.mode, a.quality, a.model, deep=a.deep)
            print(json.dumps({k: v for k, v in r.items() if k != "level_of"}))
    elif a.cmd == "results":
        RESULTS.write_text(json.dumps(results(), indent=1) + "\n")
        print(json.dumps({"out": str(RESULTS.relative_to(ROOT))}))
    elif a.cmd == "compare":
        compare(a.picture, a.variant, [int(n) for n in a.steps.split(",")], Path(a.out))
    elif a.cmd == "probe":
        print(json.dumps(probe(a.picture, a.remove.split(","))))
    elif a.cmd == "build":
        sam = ol.Sam()
        for name in pictures_of(a.picture):
            r = build_lesson(name, a.variant, sam=sam)
            print(json.dumps({k: v for k, v in r.items() if k != "rows"}))


if __name__ == "__main__":
    main()
