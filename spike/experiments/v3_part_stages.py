"""Spike for #169 (pipeline v3, S4): stages inside a part by peeling detail, in place of a flat coat and
nearest-color passes.

Not part of the pipeline. A v2 step that isn't its part's last shows a flat coat, or the finish wherever its color is
nearest the step's paints. Here the image model paints that stage instead: the same picture with the part as it
stands after the steps done so far, as the plan describes them. Of each render only the part's own pixels are kept
(build_steps.make_background, the guard v2's background render uses), so nothing outside the part can move.

    python spike/experiments/v3_part_stages.py stages sleeping-cat                 # the requests, no render
    python spike/experiments/v3_part_stages.py render sleeping-cat --mode parallel     # PAID: one render a stage
    python spike/experiments/v3_part_stages.py build sleeping-cat --variant parallel-low   # step pictures, as a lesson
    python spike/experiments/v3_part_stages.py results                             # writes v3_part_stages.json

Words:
    stage     a part as it stands after one of its steps that isn't its last. The plan decides the stages (they are
              its steps); the image model only paints a stage the plan describes. A part's last step is the finish.
    parallel  every stage is asked for from the finished part, all renders at once.
    chained   a part's stages are made backward, each from the one after it: un-paint one step at a time.
    source    the picture a part's stages are painted on: the finish for a thing in front, and for a part behind
              v2's picture with the things in front taken out (so the part is whole where they will stand).

The pictures and numbers go in spike/experiments/bench/runs/stages/<variant>/<picture>/ (git-ignored); `results`
gathers them into v3_part_stages.json. docs/spikes/v3-part-stages.md has the results.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_steps as bs  # noqa: E402
import from_finish as ff  # noqa: E402
import outline as ol  # noqa: E402
import v3_peel as vp  # noqa: E402

BENCH = vp.BENCH
OUT = BENCH / "runs" / "stages"
RUNS = vp.RUNS
# The pictures this spike starts on (docs/decisions.md: 3 or 4, the ones most likely to show the effect): three of
# the owner's four lowest baseline scores, and the lavender balloon, whose balloon and field have the most passes.
# The birch grove is left out: its fault is the sky's fill under its own marks, in a one-step part with no stage.
ALL4 = ["sleeping-cat", "highland-cow", "lake-cabin", "balloon-lavender"]

NEAR = 12.0  # Delta E (CIEDE2000): a pixel this near a paint is that paint (paints.MAX_MERGE, the line a painter sees)
ADDS = 6  # RGB levels: a pixel a step moved by more than this was painted by it (build_steps' `changed`)
SAME = 8.0  # Lab units: where a stage is this near what's on the canvas, a step that lays only its changes leaves it
WORKERS = 8  # renders of one picture running together


# ---------------------------------------------------------------------------
# The stages the plan describes
# ---------------------------------------------------------------------------


def stages(plan: dict) -> list[dict]:
    """One entry per step that isn't its part's last: the step's place in the lesson (`i`), its part (`k`), and the
    part's steps done by then and still to come."""
    parts, steps = plan["parts"], bs.flat_steps(plan)
    index = {p["id"]: i for i, p in enumerate(parts)}
    of: dict[str, list[int]] = {}
    for i, s in enumerate(steps):
        of.setdefault(s["part"], []).append(i)
    out = []
    for i, s in enumerate(steps):
        mine = of[s["part"]]
        at = mine.index(i)
        if at < len(mine) - 1:
            out.append({"i": i, "id": s["id"], "k": index[s["part"]], "done": mine[:at + 1], "todo": mine[at + 1:]})
    return out


def _paints(plan: dict, step: dict) -> str:
    by = {p["id"]: p for p in plan["paints"]}
    return " and ".join(f"{by[c].get('name') or c} ({by[c]['hex']})" for c in step.get("paints") or [])


def _line(plan: dict, step: dict, n: int) -> str:
    how = {"flat": "a flat coat of", "pass": "a pass of", "full": "finished with", "blend": "blended from"}
    return f"({n}) {step['name']}: {how.get(step.get('show', 'full'), 'with')} {_paints(plan, step)}"


def prompt_for(plan: dict, stage: dict) -> str:
    """What to paint, from the plan alone: the part, its steps done so far with their paints, and the steps still to
    come, which must not show."""
    parts, steps = plan["parts"], bs.flat_steps(plan)
    part = parts[stage["k"]]
    name = part.get("name") or part["id"]
    done = [_line(plan, steps[i], n + 1) for n, i in enumerate(stage["done"])]
    todo = [_line(plan, steps[i], len(done) + n + 1) for n, i in enumerate(stage["todo"])]
    kids = [p.get("name") or p["id"] for p in parts if p.get("parent") == part["id"]]
    first = steps[stage["done"][0]]
    text = ("This is a finished acrylic painting. Paint the same picture at an earlier moment, when one thing in it "
            f"was only partly painted: {name}. On it the painter has done only this so far: " + "; ".join(done) + ". "
            "These steps are NOT done yet, so nothing of them may show on it: " + "; ".join(todo) + ". ")
    if len(done) == 1 and first.get("show") == "flat":
        text += (f"So {name} is only blocked in: flat, even color in its own shape, with no shading, no texture, no "
                 "highlights and no details inside it. ")
    elif first.get("show") != "flat":
        behind = next((p.get("name") or p["id"] for p in parts if p["id"] == part.get("parent")), "what is behind it")
        text += f"Where it has no paint yet, show {behind} as it is around it. "
    else:
        text += "It shows the paint of the steps done, over its flat first coat, and nothing more. "
    text += (f"Keep its exact outline, size and place. Everything else in the picture is finished and stays exactly "
             f"as it is: change nothing outside {name}"
             + (f", and leave these, painted on it, as they are: {'; '.join(kids)}" if kids else "")
             + ". Same loose acrylic brushwork. No text, signature, or watermark.")
    return text


def chained_prompt(plan: dict, stage: dict) -> str:
    """The same stage, asked for as one step un-painted from the picture given (the stage after it)."""
    steps = bs.flat_steps(plan)
    part = plan["parts"][stage["k"]]
    name = part.get("name") or part["id"]
    undo = steps[stage["todo"][0]]
    return (f"This is an acrylic painting in progress. On {name}, un-paint the last thing the painter did: "
            f"{undo['name']} ({_paints(plan, undo)}). Show {name} as it was just before that step, with only this "
            "done on it: " + "; ".join(_line(plan, steps[i], n + 1) for n, i in enumerate(stage["done"])) + ". "
            f"Keep its exact outline, size and place, and change nothing outside {name}. Same loose acrylic "
            "brushwork. No text, signature, or watermark.")


# ---------------------------------------------------------------------------
# The picture, and what each part's stages are painted on
# ---------------------------------------------------------------------------


def load(picture: str, runs: Path = RUNS) -> dict:
    """The frozen finish, the baseline run's plan and outlines, and its background render (v3_peel.load)."""
    d = vp.load(picture, runs)
    plate = d["run"] / "98_background.png"
    d["background"] = np.array(Image.open(plate).convert("RGB")) if plate.exists() else None
    return d


def behind(d: dict) -> dict:
    """build_steps' own answer for what's behind the things in front (never changed afterwards)."""
    if "pre" not in d:
        d["pre"] = bs._behind(d["finish"], d["plan"]["parts"], d["owner"], d.get("background"))
    return d["pre"]


def source(d: dict, k: int) -> tuple[np.ndarray, np.ndarray]:
    """(picture, mine): what part k's stages are painted on, and the part's own pixels there."""
    pre = behind(d)
    if pre["is_back"][k]:
        return pre["base_back"], pre["own_back"] == k
    return pre["finish"], pre["owner"] == k


def guard(src: np.ndarray, raw: np.ndarray, mine: np.ndarray) -> np.ndarray:
    """The source with the render's pixels inside the part (and its soft rim), matched in tone to the source around
    it. Nothing else of the render is used."""
    return bs.make_background(src, mine, raw)


# ---------------------------------------------------------------------------
# Renders
# ---------------------------------------------------------------------------


def render_stages(picture: str, mode: str = "parallel", quality: str = "low", model: str = "gpt-image",
                  runs: Path = RUNS, only: list[str] | None = None) -> dict:
    """PAID: one render a stage. Writes <step id>_raw.png (the model's answer), <step id>.png (guarded), and
    stages.json. A render already in the folder is kept."""
    d = load(picture, runs)
    plan = d["plan"]
    todo = [s for s in stages(plan) if not only or plan["parts"][s["k"]]["id"] in only]
    variant = f"{mode}-{quality}" + ("" if model == "gpt-image" else f"-{model}")
    folder = OUT / variant / picture
    folder.mkdir(parents=True, exist_ok=True)
    fresh = [s for s in todo if not (folder / f"{s['id']}_raw.png").exists()]
    started = time.time()
    rows: dict[str, dict] = {}

    def one(stage: dict, src: np.ndarray, text: str) -> np.ndarray:
        _, mine = source(d, stage["k"])
        raw, info = vp.render(model, src, text, folder, stage["id"], quality)
        got = guard(src, raw, mine)
        Image.fromarray(got).save(folder / f"{stage['id']}.png")
        away = ~bs.halo(bs.halo(mine))
        rows[stage["id"]] = {"id": stage["id"], "part": plan["parts"][stage["k"]]["id"],
                             "part_share": round(float(mine.mean()), 4), "seconds": info["seconds"],
                             "cost_usd": info["cost_usd"],
                             # what the guard throws away: the raw render against its source, away from the part
                             "raw_moved": vp.moved(src, raw, away),
                             # how much of the part the render changed at all
                             "part_moved": vp.moved(src, raw, mine)}
        return got

    behind(d)  # once, before the threads
    if mode == "chained":
        by_part: dict[int, list[dict]] = {}
        for s in todo:
            by_part.setdefault(s["k"], []).append(s)

        def chain(k: int) -> None:
            cur = source(d, k)[0]
            for s in reversed(by_part[k]):
                cur = one(s, cur, chained_prompt(plan, s))

        with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
            list(pool.map(chain, by_part))
    else:
        with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
            list(pool.map(lambda s: one(s, source(d, s["k"])[0], prompt_for(plan, s)), todo))
    wall = time.time() - started
    listed = [rows[s["id"]] for s in todo]
    old = folder / "stages.json"
    result = {"picture": picture, "variant": variant, "mode": mode, "quality": quality, "model": model,
              "run": d["run"].name, "renders": len(listed), "steps": len(bs.flat_steps(plan)),
              "cost_usd": round(sum(r["cost_usd"] for r in listed), 4),
              "render_seconds": round(sum(r["seconds"] for r in listed), 1),
              # the clock for this picture's renders, when every one was made in this run
              "wall_seconds": round(wall, 1) if len(fresh) == len(todo) else
              (json.loads(old.read_text()).get("wall_seconds") if old.exists() else None),
              "rows": listed}
    old.write_text(json.dumps(result, indent=1))
    return result


# ---------------------------------------------------------------------------
# Step pictures
# ---------------------------------------------------------------------------


def build(d: dict, staged: dict[str, np.ndarray], lay_all: bool = True, only_passes: bool = False):
    """(pictures, rows, painted, areas), as build_steps.build gives them, with every step in `staged` (step id ->
    its guarded stage picture) showing its part as the stage has it.

    This is build_steps._build's loop with one change. A staged step lays the stage's paint over the part's whole
    area, where v2 lays a flat coat or the finish's pixels nearest the step's paints. Under the things that will
    cover the part, and where its children go, the stage's own paint is carried across by v2's fill
    (build_steps._prepare, given the stage picture in place of the finish). What's behind things, rims, the order
    of parts and each part's last step are v2's, unchanged.

    `lay_all` False: after a part's first step, a staged step lays only the pixels where its stage differs from the
    canvas by SAME or more. A part that starts with a pass (clouds, a reflection) always works that way, so the
    paint under it stays where the stage shows none. `only_passes`: flat steps stay v2's flat coat."""
    finish, plan, owner = d["finish"], d["plan"], d["owner"]
    parts, steps = plan["parts"], bs.flat_steps(plan)
    index = {p["id"]: i for i, p in enumerate(parts)}
    hexes = {p["id"]: p["hex"] for p in plan["paints"]}
    h, w = owner.shape
    long_side = max(h, w)
    pre = behind(d)
    is_back, front, own_back = pre["is_back"], pre["front"], pre["own_back"]
    last_of = {s["part"]: i for i, s in enumerate(steps)}
    paints_of: dict[str, list[str]] = {}
    for s in steps:
        for c in s.get("paints") or []:
            if c not in paints_of.setdefault(s["part"], []):
                paints_of[s["part"]].append(c)
    prep: dict[int, dict] = {}
    coated = np.zeros(len(parts), bool)
    detailed: dict[int, np.ndarray] = {}
    top = np.full((h, w), -1, np.int32)
    canvas = np.empty((h, w, 3), np.float32)
    canvas[:] = ff.CANVAS
    started = np.zeros(len(parts), bool)
    pictures, rows, painted, areas = [], [], [], []
    for i, s in enumerate(steps):
        k = index[s["part"]]
        names = paints_of.get(parts[k]["id"]) or []
        if k not in prep:
            prep[k] = bs._prepare(pre, parts, k, names, hexes)
        r = prep[k]
        blocked = np.zeros((h, w), bool)
        own_map = own_back if is_back[k] else owner
        for q in np.flatnonzero(started):
            if q > k:
                blocked |= (owner == q) | (own_map == q)
        target = r["area"] & ~blocked
        show = s.get("show", "full")
        stage = staged.get(s["id"]) if last_of[s["part"]] != i and not (only_passes and show == "flat") else None
        before = canvas.copy()
        if stage is not None:
            # the part as the stage has it, carried under what will cover it the way v2 carries the finish's paint
            key = "base_back" if is_back[k] else "finish"
            lay = bs._prepare({**pre, key: stage}, parts, k, [], hexes)["content"]
            where = target
            if started[k] and (not lay_all or not coated[k]) or (not started[k] and show != "flat"):
                gap = np.sqrt(((ol.lab(lay) - ol.lab(np.clip(canvas, 0, 255).astype(np.uint8))) ** 2).sum(2))
                where = where & (cv2.medianBlur((gap >= SAME).astype(np.uint8), bs.SMOOTH) > 0)
            if show == "flat":
                coated[k] = True
        elif show == "flat":
            lay, where = ff.flat_paint(r["content"], r["area"], [hexes[n] for n in s["paints"]]), target
            coated[k] = True
        elif show == "pass" and last_of[s["part"]] != i:
            pick = np.isin(r["nearest"], [names.index(n) for n in s["paints"]])
            lay, where = r["content"], target & pick
        else:
            lay, where = r["content"], target
        if show != "flat":
            g = r["rim_group"]
            back = (g >= 0) & started[np.maximum(g, 0)]
            if back.any():
                lay = np.where(back[..., None], r["base_of"], lay)
        if (coated[k] or (stage is not None and started[k])) and show != "flat":
            where = where & ~r["kids"]
        rim = np.zeros((h, w), bool)
        if not is_back[k] and not started[k]:
            rim = bs.halo(np.isin(owner, r["family"])) & ~front & ~blocked
            canvas = bs._lay(canvas, finish, rim)
        if not started[k]:
            for j, rj in prep.items():
                back = (rj["rim_group"] == k) & (top == j) & detailed.get(j, False)
                if np.any(back):
                    canvas = bs._lay(canvas, rj["base_of"], back)
                    rim = rim | back
        canvas = bs._lay(canvas, lay, where)
        top[where] = k
        if show != "flat":
            detailed[k] = detailed.get(k, np.zeros((h, w), bool)) | where
        started[k] = True
        changed = np.abs(canvas - before).max(2) > ADDS
        near = cv2.dilate(r["area"].astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        rows.append({"id": s["id"], "part": s["part"], "show": show, "staged": stage is not None,
                     "last": last_of[s["part"]] == i,
                     "painted": round(float(where.mean()), 4), "changed": round(float(changed.mean()), 4),
                     "outside": round(float((changed & ~near & ~(rim & bs._grow(r["area"], bs.RIM_REACH * long_side))).mean()), 5)})
        pictures.append(np.clip(canvas, 0, 255).astype(np.uint8))
        painted.append(where | rim)
        areas.append(r["area"])
    gap = np.abs(pictures[-1].astype(np.int16) - finish.astype(np.int16)).max(2) > vp.MOVED
    for row in rows:
        row["final_gap"] = round(float(gap.mean()), 4)
    pictures[-1] = finish.copy()
    return pictures, rows, painted, areas


# ---------------------------------------------------------------------------
# Measures (the same for v2's pictures and the staged ones)
# ---------------------------------------------------------------------------


def ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIEDE2000 between Lab arrays (..., 3) that broadcast against each other; mixing.delta_e's formula, on arrays."""
    L1, a1, b1 = (lab1[..., i].astype(np.float64) for i in range(3))
    L2, a2, b2 = (lab2[..., i].astype(np.float64) for i in range(3))
    Cb = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    G = 0.5 * (1 - np.sqrt(Cb ** 7 / (Cb ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p, h2p = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(C1p * C2p == 0, 0.0, dh)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh) / 2)
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    hs = h1p + h2p
    hbp = np.where(np.abs(h1p - h2p) > 180, np.where(hs < 360, hs + 360, hs - 360), hs) / 2
    hbp = np.where(C1p * C2p == 0, hs, hbp)
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    SL = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    SC, SH = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    RC = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    RT = -RC * np.sin(np.radians(60 * np.exp(-((hbp - 275) / 25) ** 2)))
    return np.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2 + RT * (dCp / SC) * (dHp / SH))


def measure(d: dict, pictures: list[np.ndarray], areas: list[np.ndarray]) -> list[dict]:
    """Per step, read from the pictures alone:
    `added`        the share of the picture the step changed inside its part;
    `named`        of that, the share within NEAR of a paint the step names (check 3 of the v3 plan);
    `named_so_far` the same against every paint the part's steps have named by then;
    `to_finish`    how far the part is from the finish after the step (mean Delta E over its area);
    `undone`       the share of the part that was within NEAR of the finish before the step and isn't after."""
    plan = d["plan"]
    steps = bs.flat_steps(plan)
    hexes = {p["id"]: p["hex"] for p in plan["paints"]}
    fin = ol.lab(d["finish"])
    blank = np.empty_like(d["finish"])
    blank[:] = ff.CANVAS
    so_far: dict[str, list[str]] = {}
    rows = []
    for i, s in enumerate(steps):
        prev = pictures[i - 1] if i else blank
        area = areas[i]
        added = area & (np.abs(pictures[i].astype(np.int16) - prev.astype(np.int16)).max(2) > ADDS)
        mine = so_far.setdefault(s["part"], [])
        mine += [c for c in s.get("paints") or [] if c not in mine]
        now = ol.lab(pictures[i])

        def share(names: list[str]) -> float | None:
            if not added.any() or not names:
                return None
            px = now[added]
            best = np.min([ciede2000(px, ff.hex_lab(hexes[n])) for n in names], axis=0)
            return round(float((best <= NEAR).mean()), 3)

        d_now = ciede2000(now[area], fin[area])
        d_was = ciede2000(ol.lab(prev)[area], fin[area])
        rows.append({"id": s["id"], "added": round(float(added.mean()), 4),
                     "named": share(s.get("paints") or []), "named_so_far": share(mine),
                     "to_finish": round(float(d_now.mean()), 2),
                     "undone": round(float(((d_was <= NEAR) & (d_now > NEAR)).mean()), 4)})
    return rows


def summary(rows: list[dict], marks: list[dict], which: set[str]) -> dict:
    """A lesson's numbers over the steps in `which` (the steps that have a stage), weighted by what each added."""
    pick = [(r, m) for r, m in zip(rows, marks) if r["id"] in which and m["named"] is not None]
    weight = sum(m["added"] for _, m in pick) or 1.0
    return {"steps": len(pick),
            "named": round(sum(m["named"] * m["added"] for _, m in pick) / weight, 3),
            "named_so_far": round(sum(m["named_so_far"] * m["added"] for _, m in pick) / weight, 3),
            "named_worst": min([m["named"] for _, m in pick], default=None),
            "undone_max": max([m["undone"] for r, m in zip(rows, marks) if r["id"] in which], default=0.0),
            "outside_max": max(r["outside"] for r in rows), "final_gap": rows[-1]["final_gap"]}


# ---------------------------------------------------------------------------
# The lesson, for the A/B page
# ---------------------------------------------------------------------------


def build_lesson(picture: str, variant: str, runs: Path = RUNS, lay_all: bool = True,
                 only_passes: bool = False, name: str = "") -> dict:
    """The baseline lesson with its step pictures built from the stages: a copy of the run under
    runs/stages/<variant>/lessons/, same plan, paints and words, so the A/B page shows one change. The copy's
    folder gets its own name (the peel round's two sides shared one, docs/spikes/v3-peel.md section 8)."""
    d = load(picture, runs)
    folder = OUT / variant / picture
    staged = {s["id"]: np.array(Image.open(folder / f"{s['id']}.png").convert("RGB"))
              for s in stages(d["plan"]) if (folder / f"{s['id']}.png").exists()}
    started = time.time()
    pictures, rows, _, areas = build(d, staged, lay_all, only_passes)
    seconds = time.time() - started
    v2_pictures, v2_rows, _ = bs.build(d["finish"], d["plan"], d["owner"], d.get("background"))
    which = {r["id"] for r in rows if r["staged"]}
    marks, v2_marks = measure(d, pictures, areas), measure(d, v2_pictures, areas)
    tag = name or ("stages" + ("" if lay_all else "-changes") + ("-passes" if only_passes else ""))
    lesson = OUT / variant / "lessons" / f"{d['run'].name}-{tag}"
    if lesson.exists():
        shutil.rmtree(lesson)
    shutil.copytree(d["run"], lesson, ignore=shutil.ignore_patterns("trials", "versions", "busy", "embed", "*.html"))
    box = (json.loads((lesson / "canvas.json").read_text()).get("canvas_box") or [0, 0, 1, 1]) \
        if (lesson / "canvas.json").exists() else [0, 0, 1, 1]
    h, w = d["owner"].shape
    x0, y0, x1, y1 = round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h)
    steps = bs.flat_steps(d["plan"])
    for i, (s, img) in enumerate(zip(steps, pictures)):
        file = f"{i + 1:02d}_{s['id']}.png"
        Image.fromarray(img).save(lesson / file)
        if (lesson / "canvas" / file).exists():
            Image.fromarray(img[y0:y1, x0:x1]).save(lesson / "canvas" / file)
    Image.fromarray(bs.contact_sheet(pictures, steps)).save(folder / f"steps-{tag}.jpg", quality=88)
    result = {"picture": picture, "variant": variant, "tag": tag, "lesson": str(lesson.relative_to(ROOT)),
              "staged_steps": len(which), "build_seconds": round(seconds, 1),
              "stages": summary(rows, marks, which), "v2": summary(v2_rows, v2_marks, which),
              "rows": [{**r, **m, "v2": v} for r, m, v in zip(rows, marks, v2_marks)]}
    (folder / f"build-{tag}.json").write_text(json.dumps(result, indent=1))
    return result


# ---------------------------------------------------------------------------
# The write-up's numbers and pictures
# ---------------------------------------------------------------------------

RESULTS = Path(__file__).with_suffix(".json")


def results() -> dict:
    """Every variant's numbers, one row a picture, from the stages.json and build-*.json files under runs/stages/."""
    out: dict[str, list[dict]] = {}
    for path in sorted(OUT.glob("*/*/stages.json")):
        p = json.loads(path.read_text())
        rows = p["rows"]
        row = {"picture": p["picture"], "steps": p["steps"], "renders": p["renders"], "cost_usd": p["cost_usd"],
               "render_seconds": p["render_seconds"], "wall_seconds": p["wall_seconds"],
               "raw_moved": round(sum(r["raw_moved"] for r in rows) / max(1, len(rows)), 3),
               "raw_moved_worst": max([r["raw_moved"] for r in rows], default=0.0)}
        for built in sorted(path.parent.glob("build-*.json")):
            b = json.loads(built.read_text())
            row[b["tag"]] = {"staged_steps": b["staged_steps"], "build_seconds": b["build_seconds"],
                             "stages": b["stages"], "v2": b["v2"],
                             "steps": [{k: r.get(k) for k in ("id", "show", "staged", "added", "named", "named_so_far",
                                                              "to_finish", "undone")}
                                       | {"v2_named": r["v2"]["named"], "v2_named_so_far": r["v2"]["named_so_far"],
                                          "v2_to_finish": r["v2"]["to_finish"]}
                                       for r in b["rows"] if not r["last"]]}
        out.setdefault(p["variant"], []).append(row)
    return out


def compare(picture: str, variant: str, steps: list[int], out: Path, tag: str = "stages", width: int = 420) -> None:
    """A picture for the write-up: the chosen steps of the v2 baseline (top row) over the same steps from the
    stages (bottom row)."""
    d = load(picture)
    ids = [s["id"] for s in bs.flat_steps(d["plan"])]
    lesson = OUT / variant / "lessons" / f"{d['run'].name}-{tag}"

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
    p = sub.add_parser("stages", help="the stages and their requests; no render")
    p.add_argument("picture")
    p.add_argument("--prompts", action="store_true")
    p = sub.add_parser("render", help="PAID: one render a stage")
    p.add_argument("picture")
    p.add_argument("--mode", choices=["parallel", "chained"], default="parallel")
    p.add_argument("--quality", choices=["low", "medium"], default="low")
    p.add_argument("--parts", help="only these parts' stages (ids, comma-separated)")
    p = sub.add_parser("build", help="step pictures from the stages, as a copy of the baseline lesson")
    p.add_argument("picture")
    p.add_argument("--variant", required=True)
    p.add_argument("--changes", action="store_true", help="after a part's first step, lay only what the stage changes")
    p.add_argument("--passes", action="store_true", help="flat steps stay v2's flat coat")
    sub.add_parser("results", help="write v3_part_stages.json from the runs")
    p = sub.add_parser("compare", help="a picture for the write-up: v2's steps over the stages'")
    p.add_argument("picture")
    p.add_argument("--variant", required=True)
    p.add_argument("--steps", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--tag", default="stages")
    a = ap.parse_args()
    if a.cmd == "stages":
        for name in pictures_of(a.picture):
            d = load(name)
            todo = stages(d["plan"])
            print(json.dumps({"picture": name, "steps": len(bs.flat_steps(d["plan"])), "renders": len(todo),
                              "stages": [s["id"] for s in todo]}))
            if a.prompts:
                for s in todo:
                    print(f"\n[{s['id']}]\n{prompt_for(d['plan'], s)}")
    elif a.cmd == "render":
        for name in pictures_of(a.picture):
            r = render_stages(name, a.mode, a.quality, only=a.parts.split(",") if a.parts else None)
            print(json.dumps({k: v for k, v in r.items() if k != "rows"}))
    elif a.cmd == "build":
        for name in pictures_of(a.picture):
            r = build_lesson(name, a.variant, lay_all=not a.changes, only_passes=a.passes)
            print(json.dumps({k: v for k, v in r.items() if k != "rows"}))
    elif a.cmd == "results":
        RESULTS.write_text(json.dumps(results(), indent=1) + "\n")
        print(json.dumps({"out": str(RESULTS.relative_to(ROOT))}))
    elif a.cmd == "compare":
        compare(a.picture, a.variant, [int(n) for n in a.steps.split(",")], Path(a.out), a.tag)


if __name__ == "__main__":
    main()
