"""Spike for #171 (pipeline v3, S6): paints before the picture. Lock the finish to the lesson's mixes, so no step
picture shows a color its step doesn't name.

Not part of the pipeline. v2 measures the paints from the finish afterwards and merges them toward 10 mixes, so the
finish keeps colors no paint names (#154 for pass steps, #158 for a part's last step). Two ways to put the paints
first, on the frozen bench, each with the baseline run's plan, outlines and background render, so the A/B shows one
change:

    lock    push the finished render onto the named paints: every pixel of a part moves toward the nearest paint
            the part's steps name, until it is within `tol` of it (tol 0: onto the paint itself). With --by-step,
            toward the paints of the step that shows the pixel instead. The background render behind the objects
            is locked by part, by build_steps' owner of each pixel there. Free.
    swatch  hand the render the paints: an image-model edit of the finish with a swatch card of the lesson's paints
            as a second input, asked to repaint the same picture with only those colors. PAID, one render.

    python spike/experiments/v3_paints_first.py measure all                     # the v2 baseline's numbers, no render
    python spike/experiments/v3_paints_first.py lock sleeping-cat --tol 8       # a locked lesson, free
    python spike/experiments/v3_paints_first.py swatch sleeping-cat             # PAID: one render, then a lesson
    python spike/experiments/v3_paints_first.py results                         # writes v3_paints_first.json

Words:
    added    a step's pixels: inside what it paints (build_steps' painted area), moved by more than ADDS Lab units
             (#154's rule: a smaller move is texture under the coat, not a new color).
    off      an added pixel more than NEAR (Delta E 2000) from every paint its step names. The issue's measure, and
             check 3 of the v3 plan.
    mixes    the paints a beginner works out (paints.base_mixes: every paint that isn't a tint or shade of another).

The pictures and numbers go in spike/experiments/bench/runs/paints-first/<variant>/<picture>/ (git-ignored);
`results` gathers them into v3_paints_first.json. docs/spikes/v3-paints-first.md has the results.
"""

from __future__ import annotations

import argparse
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
import paints as pt  # noqa: E402
import v3_part_stages as vs  # noqa: E402
import v3_peel as vp  # noqa: E402

BENCH = vp.BENCH
OUT = BENCH / "runs" / "paints-first"
RUNS = vp.RUNS
ALL8 = ["chickadee", "red-sailboat", "balloon-lavender", "sleeping-cat", "snow-lantern", "highland-cow",
        "lake-cabin", "birch-grove"]

NEAR = 12.0  # Delta E 2000: an added pixel this near a paint its step names is that paint (paints.MAX_MERGE)
ADDS = 15.0  # Lab units a pixel must move by in a step to count as what the step adds (paints.ADDS, #154)
FAR = 0.25  # a step with more than this share of its added pixels off its paints is an off step (paints.MATCHED)
LEAST = 0.0005  # a step that adds less than this share of the picture isn't judged (paints.LEAST_ADDED)
SIDE = 768  # the measure runs on the pictures shrunk to this long side (build_steps.GHOST_SIDE)


# ---------------------------------------------------------------------------
# The picture and its paints
# ---------------------------------------------------------------------------


def load(picture: str, runs: Path = RUNS) -> dict:
    """The frozen finish, the baseline run's plan, outlines and background render (v3_part_stages.load)."""
    return vs.load(picture, runs)


def hexes(plan: dict) -> dict[str, str]:
    return {p["id"]: p["hex"] for p in plan["paints"] if p.get("hex")}


def part_paints(plan: dict) -> dict[str, list[str]]:
    """Every paint each part's steps name, in the order they first do (build_steps._build's paints_of)."""
    out: dict[str, list[str]] = {}
    for s in bs.flat_steps(plan):
        for c in s.get("paints") or []:
            if c not in out.setdefault(s["part"], []):
                out[s["part"]].append(c)
    return out


def mixes(plan: dict) -> int:
    return len(pt.base_mixes(plan["paints"]))


def _small(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    f = SIDE / max(h, w)
    if f >= 1:
        return img
    size = (round(w * f), round(h * f))
    if img.dtype == bool:
        return cv2.resize(img.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST).astype(bool)
    return cv2.resize(img, size, interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------------------
# The measure (the same for every side)
# ---------------------------------------------------------------------------


def measure(plan: dict, pictures: list[np.ndarray], painted: list[np.ndarray]) -> list[dict]:
    """Per step: `added` (share of the picture), `off` (share of the added pixels more than NEAR from every paint the
    step names), `off_part` (the same against every paint the part's steps name, all through the lesson) and
    `off_any` (against every paint in the lesson). A step with no paints or that adds under LEAST has None."""
    steps = bs.flat_steps(plan)
    hx = hexes(plan)
    labs = {n: ff.hex_lab(h) for n, h in hx.items()}
    of_part = part_paints(plan)
    blank = np.empty_like(pictures[0])
    blank[:] = ff.CANVAS
    rows = []
    prev = ff.lab(_small(blank))
    for i, s in enumerate(steps):
        lab_now = ff.lab(_small(pictures[i]))
        added = _small(painted[i]) & (np.sqrt(((lab_now - prev) ** 2).sum(2)) > ADDS)
        prev = lab_now
        row = {"id": s["id"], "part": s["part"], "show": s.get("show", "full"), "added": round(float(added.mean()), 4),
               "off": None, "off_part": None, "off_any": None}
        names = [n for n in s.get("paints") or [] if n in labs]
        if names and added.mean() >= LEAST:
            px = lab_now[added]

            def off(ns: list[str]) -> float:
                best = np.min([vs.ciede2000(px, labs[n]) for n in ns], axis=0)
                return round(float((best > NEAR).mean()), 3)

            row["off"] = off(names)
            row["off_part"] = off([n for n in of_part[s["part"]] if n in labs])
            row["off_any"] = off(list(labs))
            row["n"] = int(added.sum())
        rows.append(row)
    return rows


def summary(rows: list[dict]) -> dict:
    """A lesson's numbers: the share of all added pixels off their step's paints (each step weighted by what it
    adds), the worst step, and how many steps are off steps (over FAR)."""
    judged = [r for r in rows if r["off"] is not None]
    n = sum(r["n"] for r in judged) or 1

    def mean(key: str) -> float:
        return round(sum(r[key] * r["n"] for r in judged) / n, 3)

    worst = max(judged, key=lambda r: r["off"], default=None)
    return {"steps": len(rows), "judged": len(judged), "off": mean("off"), "off_part": mean("off_part"),
            "off_any": mean("off_any"),
            "off_steps": sum(r["off"] > FAR for r in judged),
            # steps with paints that add under LEAST: a step the painter does that changes almost nothing
            "empty": [r["id"] for r in rows if r["off"] is None and r["added"] < LEAST],
            "off_last": round(sum(r["off"] * r["n"] for r in judged if r.get("last")) /
                              (sum(r["n"] for r in judged if r.get("last")) or 1), 3),
            "worst": {"id": worst["id"], "off": worst["off"]} if worst else None}


def _mark_last(plan: dict, rows: list[dict]) -> list[dict]:
    last = {s["part"]: i for i, s in enumerate(bs.flat_steps(plan))}
    for i, r in enumerate(rows):
        r["last"] = last[r["part"]] == i
    return rows


def baseline(picture: str, runs: Path = RUNS) -> dict:
    """The v2 baseline's numbers: its plan, outlines and background render, built by build_steps as the run was."""
    d = load(picture, runs)
    pictures, _, painted = bs.build(d["finish"], d["plan"], d["owner"], d.get("background"))
    rows = _mark_last(d["plan"], measure(d["plan"], pictures, painted))
    out = {"picture": picture, "run": d["run"].name, "variant": "v2", "mixes": mixes(d["plan"]),
           "paints": len(d["plan"]["paints"]), "remeasured": remeasure(d, d["finish"]),
           "off_finish": off_finish(d, d["finish"]), "summary": summary(rows), "rows": rows}
    folder = OUT / "v2" / picture
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "measure.json").write_text(json.dumps(out, indent=1))
    return out


# ---------------------------------------------------------------------------
# Lock: push the finish onto the named paints
# ---------------------------------------------------------------------------


def _lab_rgb(L: np.ndarray) -> np.ndarray:
    rgb = cv2.cvtColor(L.astype(np.float32), cv2.COLOR_LAB2RGB)
    return np.clip(np.round(rgb * 255), 0, 255).astype(np.uint8)


def lock_pixels(img: np.ndarray, owner: np.ndarray, targets: dict[int, list[np.ndarray]], tol: float) -> tuple[np.ndarray, dict]:
    """img with every pixel of each part moved toward the nearest of its part's paints (Lab) until it is within
    `tol` (Delta E 2000) of it; a pixel already within stays. Parts with no paint stay. Returns the picture and how
    far it moved (mean Delta E, share moved by more than NEAR)."""
    L = ff.lab(img).astype(np.float64)
    out = L.copy()
    for k, cols in targets.items():
        mine = owner == k
        if not cols or not mine.any():
            continue
        px = L[mine]
        d = np.stack([vs.ciede2000(px, c) for c in cols])
        j = d.argmin(0)
        t = np.array(cols)[j]
        dist = d[j, np.arange(len(j))]
        far = dist > tol
        new = px.copy()
        if tol <= 0:
            new[far] = t[far]
        else:
            # along the line from the paint to the pixel, to where Delta E is tol (a few steps of a secant: Delta E
            # 2000 is close to linear along a short line)
            s = np.ones(len(px))
            s[far] = tol / dist[far]
            for _ in range(3):
                cand = t[far] + (px[far] - t[far]) * s[far, None]
                dd = vs.ciede2000(cand, t[far])
                s[far] = np.clip(s[far] * tol / np.maximum(dd, 1e-6), 0, 1)
            s[far] *= 0.98  # stay just inside: the round trip to 8-bit RGB moves a pixel a little
            new[far] = t[far] + (px[far] - t[far]) * s[far, None]
        out[mine] = new
    locked = _lab_rgb(out)
    moved = vs.ciede2000(ff.lab(locked), L)
    return locked, {"moved_mean": round(float(moved.mean()), 2), "moved_far": round(float((moved > NEAR).mean()), 4)}


def shown_by(plan: dict, pictures: list[np.ndarray], painted: list[np.ndarray]) -> np.ndarray:
    """For every pixel, the step whose paint the finished picture shows there: the last step that moved it by more
    than ADDS inside what it paints, or -1 where none did (it kept what an earlier, smaller move left)."""
    h, w = pictures[0].shape[:2]
    out = np.full((h, w), -1, np.int32)
    blank = np.empty_like(pictures[0])
    blank[:] = ff.CANVAS
    prev = ff.lab(blank)
    for i, pic in enumerate(pictures):
        now = ff.lab(pic)
        out[painted[i] & (np.sqrt(((now - prev) ** 2).sum(2)) > ADDS)] = i
        prev = now
    return out


def lock(d: dict, tol: float, by_step: bool = False, rounds: int = 2) -> tuple[np.ndarray, np.ndarray | None, dict]:
    """(locked finish, locked background render, numbers).

    By part (the default): each pixel of the finish moves toward the nearest paint its part's steps name, the part
    being the outlines' owner of the pixel; the background render the same, by build_steps' owner of what's behind
    the objects (its own_back).

    `by_step`: each pixel of the finish moves toward the nearest paint of the step that shows it (shown_by, on the
    lesson built from the finish as it stands), falling back to its part's paints where no step's move shows; then
    the steps are built again and it's done once more (`rounds`), since a moved pixel can move to another pass.
    The background render is locked by part, as above."""
    plan = d["plan"]
    parts = plan["parts"]
    hx = hexes(plan)
    of_part = part_paints(plan)
    labs = {n: ff.hex_lab(h).astype(np.float64) for n, h in hx.items()}
    targets = {k: [labs[n] for n in of_part.get(p["id"], []) if n in labs] for k, p in enumerate(parts)}
    background = None
    info: dict = {}
    if d.get("background") is not None:
        pre = vs.behind(d)
        background, binfo = lock_pixels(d["background"], pre["own_back"], targets, tol)
        info["background_moved_mean"] = binfo["moved_mean"]
    if not by_step:
        finish, info2 = lock_pixels(d["finish"], d["owner"], targets, tol)
        return finish, background, {**info2, **info}
    steps = bs.flat_steps(plan)
    n = len(parts)
    by_key = dict(targets)  # keys 0..n-1: a part; n + i: step i
    for i, s in enumerate(steps):
        by_key[n + i] = [labs[c] for c in s.get("paints") or [] if c in labs]
    finish = d["finish"]
    for _ in range(rounds):
        pictures, _, painted = bs.build(finish, plan, d["owner"], background)
        shown = shown_by(plan, pictures, painted)
        key = np.where(shown >= 0, n + shown, d["owner"])
        # a step that names no paint (none on the bench) leaves its pixels to the part
        empty = [k for k, v in by_key.items() if k >= n and not v]
        key = np.where(np.isin(key, empty), d["owner"], key)
        finish, info2 = lock_pixels(finish, key, by_key, tol)
    # what the rounds moved together, from the original finish (the last round's own numbers count only its moves)
    total = finish_loss(d["finish"], finish)
    return finish, background, {"moved_mean": total["delta_e_mean"], "moved_far": total["moved_far"], **info}


def lesson_copy(d: dict, tag: str, pictures: list[np.ndarray], finish: np.ndarray, variant: str) -> Path:
    """The baseline lesson with these step pictures and finish: same plan, paints and words, under
    runs/paints-first/<variant>/lessons/<run>-<tag>, so the A/B page shows one change."""
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
    Image.fromarray(finish).save(lesson / "99_finish.png")
    if (lesson / "canvas" / "99_finish.png").exists():
        Image.fromarray(finish[y0:y1, x0:x1]).save(lesson / "canvas" / "99_finish.png")
    return lesson


def remeasure(d: dict, finish: np.ndarray) -> dict:
    """v2's own `paints`, first measurement, on this finish with the baseline's parts and outlines: how many mixes
    the finish would give if the paints were measured from it afresh (the mix rules unchanged)."""
    import tools
    import yaml

    plan = {**d["plan"], "paints": []}
    plan["stages"] = [{**g, "steps": [{**s, "paints": []} for s in g["steps"]]} for g in plan.get("stages") or []]
    technique = yaml.safe_load((ROOT / plan["technique"]).read_text(encoding="utf-8")) if plan.get("technique") else {}
    tubes = tools.load_palette(plan["palette"])[0] if plan.get("palette") else technique.get("palette") or []
    import mixing

    white = next((mixing.tube_rgb(t) for t in tubes if "white" in t.lower()), (255, 255, 255))
    colored = [t for t in tubes if "white" not in t.lower()]
    dark = min(colored, key=lambda t: mixing._lab(mixing.tube_rgb(t))[0]) if colored else None
    r = pt.measure(finish, plan, d["owner"], technique.get("max_mixes"), white,
                   mixing.tube_rgb(dark) if dark else (20, 20, 22), dark or "black")
    return {"mixes": len(pt.base_mixes(r["paints"])), "paints": len(r["paints"]), "merges": len(r["merges"])}


def finish_loss(a: np.ndarray, b: np.ndarray) -> dict:
    """How far one finish is from another: mean Delta E 2000, the share moved by more than NEAR, and the loss of
    detail (the mean local contrast, a 5-pixel Laplacian of lightness, of b over a's)."""
    A, B = ff.lab(_small(a)), ff.lab(_small(b))
    d = vs.ciede2000(A, B)
    la = np.abs(cv2.Laplacian(A[..., 0], cv2.CV_32F, ksize=5)).mean()
    lb = np.abs(cv2.Laplacian(B[..., 0], cv2.CV_32F, ksize=5)).mean()
    return {"delta_e_mean": round(float(d.mean()), 2), "moved_far": round(float((d > NEAR).mean()), 4),
            "detail": round(float(lb / max(la, 1e-6)), 3)}


def run_lock(picture: str, tol: float, by_step: bool = False, runs: Path = RUNS) -> dict:
    d = load(picture, runs)
    started = time.time()
    finish, background, info = lock(d, tol, by_step)
    lock_s = time.time() - started
    pictures, _, painted = bs.build(finish, d["plan"], d["owner"], background)
    variant = f"lock-{'step-' if by_step else ''}{tol:g}"
    rows = _mark_last(d["plan"], measure(d["plan"], pictures, painted))
    folder = OUT / variant / picture
    folder.mkdir(parents=True, exist_ok=True)
    Image.fromarray(finish).save(folder / "99_finish.png")
    if background is not None:
        Image.fromarray(background).save(folder / "98_background.png")
    steps = bs.flat_steps(d["plan"])
    Image.fromarray(bs.contact_sheet(pictures, steps)).save(folder / "steps.jpg", quality=88)
    lesson = lesson_copy(d, variant, pictures, finish, variant)
    out = {"picture": picture, "run": d["run"].name, "variant": variant, "tol": tol, "lock_seconds": round(lock_s, 1),
           "lesson": str(lesson.relative_to(ROOT)), "mixes": mixes(d["plan"]), "remeasured": remeasure(d, finish),
           "lock": info, "loss": finish_loss(d["finish"], finish), "edges_kept": edges_kept(d["finish"], finish),
           "off_finish": off_finish(d, finish), "off_finish_v2": off_finish(d, d["finish"]),
           "summary": summary(rows), "rows": rows}
    (folder / "measure.json").write_text(json.dumps(out, indent=1))
    return out


# ---------------------------------------------------------------------------
# Swatch: hand the render the paints
# ---------------------------------------------------------------------------

SWATCH_PROMPT = (
    "The first image is a finished acrylic painting. The second image is a card of paint swatches: the only paints "
    "the painter has mixed for it. Repaint the first image so that every color in it is one of these swatches, or a "
    "swatch lightened with white or darkened slightly: where the painting has a color no swatch has, use the nearest "
    "swatch. Keep everything else exactly as it is: the same picture, the same composition, every shape, edge and "
    "brushstroke in the same place and the same size, the same light and shadow. Do not add, remove or move anything. "
    "No text, signature, or watermark.")


STRICT_PROMPT = (
    "The first image is a finished acrylic painting. The second image is a card of paint swatches. Repaint the "
    "painting using ONLY these exact swatch colors, as a painter with only these paints would: every brushstroke "
    "must be one of the swatch colors, or one of them mixed with white, and no other color may appear anywhere. "
    "Keep the same picture: every shape, edge and brushstroke in the same place and the same size. "
    "No text, signature, or watermark.")


def swatch_card(plan: dict, side: int = 1024) -> np.ndarray:
    """The lesson's paints as a card of plain squares, in the order the lesson first uses them, on white. No words:
    a name on the card would end up painted into the picture."""
    used: list[str] = []
    for s in bs.flat_steps(plan):
        used += [c for c in s.get("paints") or [] if c not in used]
    hx = hexes(plan)
    cols = [hx[c] for c in used if c in hx]
    n = len(cols)
    per = int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / per))
    cell = side // per
    card = np.full((max(rows * cell, cell), per * cell, 3), 255, np.uint8)
    pad = max(4, cell // 12)
    for i, h in enumerate(cols):
        y, x = divmod(i, per)
        rgb = [int(h.lstrip("#")[j:j + 2], 16) for j in (0, 2, 4)]
        card[y * cell + pad:(y + 1) * cell - pad, x * cell + pad:(x + 1) * cell - pad] = rgb
    return card


def edges_kept(a: np.ndarray, b: np.ndarray, reach: int = 3) -> float:
    """The share of a's edges (Canny, at SIDE) that b has an edge within `reach` pixels of: 1 when nothing moved."""
    ea = cv2.Canny(cv2.cvtColor(_small(a), cv2.COLOR_RGB2GRAY), 60, 140) > 0
    eb = cv2.Canny(cv2.cvtColor(_small(b), cv2.COLOR_RGB2GRAY), 60, 140) > 0
    near = cv2.dilate(eb.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * reach + 1,) * 2)) > 0
    return round(float((ea & near).sum() / max(1, ea.sum())), 3)


def off_finish(d: dict, finish: np.ndarray) -> float:
    """The share of the finish more than NEAR from every paint its part's steps name (the outlines' owner)."""
    plan = d["plan"]
    labs = {n: ff.hex_lab(h) for n, h in hexes(plan).items()}
    of_part = part_paints(plan)
    owner = cv2.resize(d["owner"].astype(np.float32), _small(finish).shape[1::-1],
                       interpolation=cv2.INTER_NEAREST).astype(np.int32)
    L = ff.lab(_small(finish))
    off = np.zeros(owner.shape, bool)
    for k, p in enumerate(plan["parts"]):
        mine = owner == k
        cols = [labs[n] for n in of_part.get(p["id"], []) if n in labs]
        if mine.any() and cols:
            off[mine] = np.min([vs.ciede2000(L[mine], c) for c in cols], axis=0) > NEAR
    return round(float(off.mean()), 4)


def swatch(picture: str, quality: str = "high", runs: Path = RUNS, strict: bool = False) -> dict:
    """PAID, one render: the finish repainted with the lesson's swatches as a second input. Kept in
    runs/paints-first/swatch/<picture>/ (a render already there is kept)."""
    d = load(picture, runs)
    folder = OUT / ("swatch-strict" if strict else "swatch") / picture
    folder.mkdir(parents=True, exist_ok=True)
    prompt = STRICT_PROMPT if strict else SWATCH_PROMPT
    card = folder / "swatches.png"
    Image.fromarray(swatch_card(d["plan"])).save(card)
    src, raw, meta = folder / "finish_in.png", folder / "finish_raw.png", folder / "render.json"
    if not (raw.exists() and meta.exists()):
        Image.fromarray(d["finish"]).save(src)
        ledger = vp.gesso_run.Ledger()
        vp.gesso_run.edit_image("paints-first", [src, card], prompt, raw, vp.gesso_run.size_for(src), quality, ledger)
        call = ledger.calls[-1]
        meta.write_text(json.dumps({"seconds": call["seconds"], "cost_usd": call["cost_usd"], "quality": quality,
                                    "prompt": prompt}, indent=1))
    info = json.loads(meta.read_text())
    got = np.array(Image.open(raw).convert("RGB"))
    if got.shape != d["finish"].shape:
        got = cv2.resize(got, (d["finish"].shape[1], d["finish"].shape[0]), interpolation=cv2.INTER_AREA)
    Image.fromarray(got).save(folder / "99_finish.png")
    return {"picture": picture, "render": info, "got": got, "d": d}


def run_swatch(picture: str, quality: str = "high", runs: Path = RUNS, strict: bool = False) -> dict:
    """The swatch render as the lesson's finish, cut by the baseline's outlines and plan, and measured. The
    background render behind the objects stays the baseline's (it was made from the old finish)."""
    r = swatch(picture, quality, runs, strict)
    d, finish = r["d"], r["got"]
    variant = "swatch-strict" if strict else "swatch"
    pictures, _, painted = bs.build(finish, d["plan"], d["owner"], d.get("background"))
    rows = _mark_last(d["plan"], measure(d["plan"], pictures, painted))
    folder = OUT / variant / picture
    steps = bs.flat_steps(d["plan"])
    Image.fromarray(bs.contact_sheet(pictures, steps)).save(folder / "steps.jpg", quality=88)
    lesson = lesson_copy(d, variant, pictures, finish, variant)
    out = {"picture": picture, "run": d["run"].name, "variant": variant, "render": r["render"],
           "lesson": str(lesson.relative_to(ROOT)), "mixes": mixes(d["plan"]), "remeasured": remeasure(d, finish),
           "loss": finish_loss(d["finish"], finish), "edges_kept": edges_kept(d["finish"], finish),
           "off_finish": off_finish(d, finish), "off_finish_v2": off_finish(d, d["finish"]),
           "summary": summary(rows), "rows": rows}
    (folder / "measure.json").write_text(json.dumps(out, indent=1))
    return out


# ---------------------------------------------------------------------------
# The write-up's numbers
# ---------------------------------------------------------------------------

RESULTS = Path(__file__).with_suffix(".json")


def results() -> dict:
    out: dict[str, list[dict]] = {}
    for path in sorted(OUT.glob("*/*/measure.json")):
        m = json.loads(path.read_text())
        out.setdefault(m["variant"], []).append({k: v for k, v in m.items() if k != "rows"} | {
            "steps": [{k: r.get(k) for k in ("id", "show", "last", "added", "off", "off_part", "off_any")}
                      for r in m["rows"]]})
    RESULTS.write_text(json.dumps(out, indent=1) + "\n")
    return out


def grade_folders(pictures: list[str], variant: str, out: Path, seed: int = 171) -> dict:
    """The blind A/B round for Claude's graders (spike/experiments/bench/ab_grader.md): per picture two folders,
    <out>/<picture>-g1/ and -g2/, each with the two lessons as A/ and B/ (packet.build_one) and the brief; the
    second grader has the sides swapped. Which side is which is drawn from the seed and kept only in the key,
    <out>/key.json, never in a grader's folder. `out` must be outside the repository."""
    import random

    sys.path.insert(0, str(BENCH))
    import packet

    out = Path(out).resolve()
    if ROOT in out.parents or out == ROOT:
        raise SystemExit("the grading folders must be outside the repository")
    rng = random.Random(seed)
    key = {"round": f"s6-{variant}", "seed": seed, "variant": variant, "pictures": {}}
    for pic in pictures:
        m = json.loads((OUT / variant / pic / "measure.json").read_text())
        sides = {"v2": RUNS / m["run"], variant: ROOT / m["lesson"]}
        first = rng.random() < 0.5
        order = ["v2", variant] if first else [variant, "v2"]
        key["pictures"][pic] = {}
        for g, names in (("g1", order), ("g2", order[::-1])):
            folder = out / f"{pic}-{g}"
            if folder.exists():
                shutil.rmtree(folder)
            for side, name in zip("AB", names):
                packet.build_one(sides[name], folder / side)
            shutil.copy(BENCH / "ab_grader.md", folder / "ab_grader.md")
            key["pictures"][pic][g] = {"A": names[0], "B": names[1],
                                       "lessons": {n: str(sides[n].relative_to(sides[n].parents[1])) for n in names}}
    (out / "key.json").write_text(json.dumps(key, indent=1))
    return key


def pictures_of(arg: str) -> list[str]:
    return ALL8 if arg == "all" else arg.split(",")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("measure", help="the v2 baseline's numbers; no render")
    p.add_argument("pictures")
    p = sub.add_parser("lock", help="a lesson from the finish locked to its paints; free")
    p.add_argument("pictures")
    p.add_argument("--tol", type=float, default=8.0)
    p.add_argument("--by-step", action="store_true", help="toward the paints of the step that shows each pixel")
    p = sub.add_parser("swatch", help="PAID: one render a picture, the finish repainted with the swatches; then a lesson")
    p.add_argument("pictures")
    p.add_argument("--quality", default="high", help="the finish's own quality on the bench")
    p.add_argument("--strict", action="store_true", help="the stricter request (STRICT_PROMPT)")
    p = sub.add_parser("grade", help="the blind A/B folders for Claude's graders, outside the repository")
    p.add_argument("pictures")
    p.add_argument("--variant", default="lock-step-8")
    p.add_argument("--out", required=True)
    sub.add_parser("results", help="write v3_paints_first.json from the runs")
    a = ap.parse_args()
    if a.cmd == "measure":
        for pic in pictures_of(a.pictures):
            r = baseline(pic)
            print(json.dumps({"picture": pic, "mixes": r["mixes"], **r["summary"]}))
    elif a.cmd == "lock":
        for pic in pictures_of(a.pictures):
            r = run_lock(pic, a.tol, a.by_step)
            print(json.dumps({"picture": pic, "mixes": r["mixes"], "remeasured": r["remeasured"], **r["lock"],
                              **r["loss"], **r["summary"]}))
    elif a.cmd == "swatch":
        for pic in pictures_of(a.pictures):
            r = run_swatch(pic, a.quality, strict=a.strict)
            print(json.dumps({"picture": pic, "cost_usd": r["render"]["cost_usd"], "edges_kept": r["edges_kept"],
                              "off_finish": r["off_finish"], "off_finish_v2": r["off_finish_v2"], **r["loss"],
                              **r["summary"]}))
    elif a.cmd == "grade":
        print(json.dumps(grade_folders(pictures_of(a.pictures), a.variant, Path(a.out)), indent=1))
    elif a.cmd == "results":
        print(json.dumps({k: len(v) for k, v in results().items()}))


if __name__ == "__main__":
    main()
