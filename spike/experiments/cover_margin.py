"""Spike for #289 (for #287): stop a layer's step picture a little past where a later thing covers it.

A step picture shows a whole layer, the part a later thing covers too, so a painter copies detail nobody will see.
Here each step picture is the usual one outside a hidden area, and inside it shows bare canvas or a flat wash of
the layer's most-used paint. The hidden area is where a later thing covers what is on top now, shrunk by a margin.

Inputs: the v3.1 gate's three lessons as `bench/v31-gate/<picture>/` keeps them (#290): `chain/P<nn>.jpg` (the
picture at the end of unit nn), `chain/masks.npz` (`m<nn>` where each step lays paint), `data/plan.json`,
`data/canvas.json` and `data/mixes.json`. The lessons' own `output/` folders aren't used.

**The cover map.** Walk the units in order (`plan3.units`), keeping which unit is on top at each pixel: the last
unit with a step that lays paint there. A pixel's owner at the finish is found the same way, from where the steps
lay paint, not from `owner.png`, so a pixel hidden for a later thing is always shown again by that thing's own step
(`owner.png` fills pixels no step lays from the nearest owner; `report` gives how far the two differ). After unit u,
a pixel is covered later when its owner comes after u and shares no thing with the unit on top now: a later unit on
the same thing (shading, texture, a rim light) is not a cover.

**The hidden area** is the covered area shrunk by the margin, with an uneven edge (`soft`): the margin is longer and
shorter along the edge, and a short ragged ramp runs along the strokes' way (side to side, as a layer is brushed).
So a thin cover (horns, trunks, grass, cloud streaks) is never hidden: the layer is painted straight through under
it (`docs/decisions.md`, 2026-10-19).

**A step changes only where it lays paint.** Inside the pixels a step lays, the picture takes that step's unit's
cover map; everywhere else it keeps what the step before showed. So a layer already painted is never taken back or
added to by a later step, and the two checks of `build-steps` still hold (`checks`): the last picture is the finish,
and no step changes a pixel outside where its unit lays paint.

Variants (`VARIANTS`): the hidden area shows `canvas`, a `wash`, or `edge` (bare canvas where the hidden area runs
out to the canvas's edge or to canvas no step has painted yet, a wash where it is an island inside the layer), or
`open` (as `edge`, but an island isn't hidden at all: tried after stage 2, when the graders marked the islands down); the margin is 1/2, 3/4 or 1 inch; the covers that
count are `all` (every other thing), `detail` (only where the layer has detail: a layer whose covered area is
nearly one flat coat is painted through), or `staged` (`detail`, and only a thing of a later stage: what is painted
in the same stage, as the cow's clouds on its sky, is one passage with the layer). Detail is `local`, the mean Lab distance of the layer's covered pixels from
the same picture blurred by half an inch: brushwork, cloud streaks and leaves score high, one coat or a smooth blend
low. `spread` (the Lab distance from the area's middle color) is reported beside it; a blended sky scores high on it.

    .venv/bin/python spike/experiments/cover_margin.py measure        # the numbers, into cover_margin.json
    .venv/bin/python spike/experiments/cover_margin.py sheets         # stage 1's sheets, into docs/spikes/
    .venv/bin/python spike/experiments/cover_margin.py steps --variant wash-0.75-detail --out <folder>

Stage 2, the pick (`PICK`) against the baseline. The work folder (`--work`, by default `<temp>/gesso-cover-margin`)
holds a copy of the bench with the variant's pictures and words, and the blind A/B folders:

    .venv/bin/python spike/experiments/cover_margin.py bench                 # the variant's pictures
    .venv/bin/python spike/experiments/cover_margin.py words                 # the writer, on the changed steps
    .venv/bin/python spike/experiments/v4_student.py --bench <work>/bench --results spike/experiments/cover_margin/variant.json \
        --work <work>/student-variant prepare     # then carry --condition words --picture P --steps ..., grade-carry --solo words
    .venv/bin/python spike/experiments/cover_margin.py ab && .venv/bin/python spike/experiments/cover_margin.py grade
    .venv/bin/python spike/experiments/cover_margin.py bench --variant open-1-staged --tag=-open --words-from base
    .venv/bin/python spike/experiments/cover_margin.py report
    .venv/bin/python spike/experiments/cover_margin.py owner-sheet

The baseline's second carry is `v4_student.py --bench spike/experiments/bench/v31-gate --results
spike/experiments/cover_margin/base.json ... carry --rep 2`; its first is the gate's (`v31_gate/student.json`).
The write-up and verdict: `docs/spikes/cover-margin.md`.

Experiment code: it reads the bench and changes no tool.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "spike"))

import build_steps as bs  # noqa: E402
import erase3  # noqa: E402
import from_finish as ff  # noqa: E402
import plan3  # noqa: E402

BENCH = HERE / "bench" / "v31-gate"
RESULTS = HERE / "cover_margin.json"
DOCS = ROOT / "docs" / "spikes"
PICTURES = ["highland-cow", "sleeping-cat", "birch-grove"]

FILLS = ("canvas", "wash", "edge", "open", "line")
MARGINS = (0.5, 0.75, 1.0)  # inches
COVERS = ("all", "detail", "staged", "later")
VARIANTS = [f"{f}-{m:g}-{c}" for f in FILLS for m in MARGINS for c in COVERS]

DETAIL = 3.0  # Lab units of `local` detail: a layer at or above this has detail where it is covered (flat coats
#   measured 1.0 to 2.0 on the three pictures, layers with detail 4.3 and up: `cover_margin.json`)
DETAIL_BAND = (0.05, 0.5)  # inches: `local` detail is what lies between the layer blurred this little and this much
RAMP = 0.15  # inches: the hidden area's edge fades in over this
WOBBLE = 0.35  # the margin is longer and shorter along the edge by this share of itself
WOBBLE_SIZE = 0.8  # inches: how far along the edge the margin takes to change
RAG = 0.6  # the ragged ramp: this share of RAMP, along the strokes' way
SEED = 289
SHOWN = 0.002  # share of the canvas: a step whose picture differs from the baseline's by less isn't on the sheets
TILE = 240  # pixels: a picture's long side on a sheet


# ----------------------------------------------------------------------------------------------------- the inputs
def _rgb(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB"))


def load(picture: str, bench: Path = BENCH) -> dict:
    """One gate lesson: its plan, units, steps, chain pictures, step masks, paints and inches."""
    b = bench / picture
    plan = json.loads((b / "data" / "plan.json").read_text())
    canvas = json.loads((b / "data" / "canvas.json").read_text())["canvas"]
    mixes = json.loads((b / "data" / "mixes.json").read_text())
    us, steps = plan3.units(plan), plan3.steps(plan)
    z = np.load(b / "chain" / "masks.npz")
    P = [_rgb(b / "chain" / f"P{n:02d}.jpg") for n in range(len(us))]
    m = [z[f"m{i:02d}"] for i in range(len(steps))]
    owner_png = np.array(Image.open(b / "chain" / "owner.png"))
    h, w = P[0].shape[:2]
    x0, y0, x1, y1 = json.loads((b / "data" / "canvas.json").read_text())["canvas_box"]
    crop = (round(y0 * h), round(y1 * h), round(x0 * w), round(x1 * w))  # the canvas inside the frame
    hexes = {p["name"]: (mixes.get(p["name"]) or {}).get("target_hex") or p["color"] for p in plan["paints"]}
    return {"picture": picture, "plan": plan, "units": us, "steps": steps, "P": P, "m": m, "owner_png": owner_png,
            "ppi": (crop[3] - crop[2]) / float(canvas["w_in"]), "crop": crop, "canvas_in": (canvas["w_in"], canvas["h_in"]), "hexes": hexes}


def on_canvas(L: dict, img: np.ndarray) -> np.ndarray:
    """The part of a frame-sized picture that is the canvas (`canvas.json`'s canvas_box)."""
    y0, y1, x0, x1 = L["crop"]
    return img[y0:y1, x0:x1]


def unit_of(us: list[dict]) -> dict[int, int]:
    return {i: n for n, u in enumerate(us) for i in u["steps"]}


def baseline(L: dict) -> list[np.ndarray]:
    """The lesson's step pictures as `steps3.build` laid them: each step lays its unit's P where its mask is."""
    canvas = np.empty(L["P"][0].shape, np.float32)
    canvas[:] = ff.CANVAS
    out = []
    by = unit_of(L["units"])
    for i in range(len(L["steps"])):
        canvas = bs._lay(canvas, L["P"][by[i]], L["m"][i])
        out.append(np.clip(canvas, 0, 255).astype(np.uint8))
    return out


def laid_by_unit(L: dict) -> list[np.ndarray]:
    return [np.any([L["m"][i] for i in u["steps"]], axis=0) for u in L["units"]]


def last_laid(L: dict) -> np.ndarray:
    """Which unit lays the last paint on each pixel (-1: none does, the canvas stays bare)."""
    owner = np.full(L["m"][0].shape, -1, np.int32)
    for n, lay in enumerate(laid_by_unit(L)):
        owner[lay] = n
    return owner


def owner_map(L: dict) -> np.ndarray:
    """Which unit owns each pixel at the finish: `owner.png` (the last unit whose core holds it), except where that
    unit lays no paint on the pixel; there, the last unit that does. A unit that comes back to a thing is laid over
    the whole thing and moves every pixel of it a little, so where paint is last laid alone gives the rim light and
    the last lights most of the cow. And a pixel hidden for its owner must be shown again by one of its owner's
    steps, or the last picture isn't the finish."""
    if "_owner" in L:
        return L["_owner"]
    png = L["owner_png"].astype(np.int32)
    laid = np.stack(laid_by_unit(L))
    ys, xs = np.indices(png.shape)
    ok = laid[np.clip(png, 0, len(laid) - 1), ys, xs] & (png < len(laid))
    L["_owner"] = np.where(ok, png, last_laid(L))
    return L["_owner"]


def tops(L: dict) -> list[np.ndarray]:
    """After each unit, which unit is on top at each pixel (-1: bare canvas)."""
    if "_tops" in L:
        return L["_tops"]
    top = np.full(L["m"][0].shape, -1, np.int32)
    out = []
    for n, lay in enumerate(laid_by_unit(L)):
        top = top.copy()
        top[lay] = n
        out.append(top)
    L["_tops"] = out
    return out


def share_things(us: list[dict]) -> np.ndarray:
    k = len(us)
    s = np.zeros((k, k), bool)
    for a in range(k):
        for b in range(k):
            s[a, b] = bool(set(us[a]["things"]) & set(us[b]["things"]))
    return s


def later_stage(L: dict, u: int) -> np.ndarray:
    """Where the owner at the finish is a unit of a later stage than unit u."""
    stages = [x.get("id") for x in L["plan"]["stages"]]
    at = np.array([stages.index(x["stage"]) for x in L["units"]] + [-1])
    return at[owner_map(L)] > at[u]


def covered(L: dict) -> list[np.ndarray]:
    """After each unit u, where a later unit that shares no thing with the one on top covers it."""
    if "_covered" in L:
        return L["_covered"]
    us, owner = L["units"], owner_map(L)
    same = share_things(us)
    out = []
    for u, top in enumerate(tops(L)):
        ok = (top >= 0) & (owner > u)
        c = np.zeros(owner.shape, bool)
        c[ok] = ~same[top[ok], owner[ok]]
        out.append(c)
    L["_covered"] = out
    return out


# ------------------------------------------------------------------------------------------------- detail and paint
def _lab(img: np.ndarray, blur: float = 1.0) -> np.ndarray:
    return ff.lab(cv2.GaussianBlur(img, (0, 0), blur) if blur else img)


def _masked_blur(lab: np.ndarray, mask: np.ndarray, sigma: float) -> np.ndarray:
    """`lab` blurred inside `mask` only: what is around the layer doesn't bleed into it."""
    w = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), sigma)[..., None]
    return cv2.GaussianBlur(lab * mask[..., None], (0, 0), sigma) / np.maximum(w, 1e-4)


def layer_detail(L: dict, cov: list[np.ndarray] | None = None) -> list[dict]:
    """For each unit, as a layer: how much of what it lays is covered later, and how much detail is in that part
    of its picture P[u]. `local`: the mean Lab distance between P[u] blurred by DETAIL_BAND's two sizes, both inside
    what the unit lays only (brushwork, streaks, leaves, ridges; not the canvas's grain, and not the things around
    it), over the covered part away from its edge. `spread`: the mean Lab distance from the covered area's middle
    color (a smooth blend scores high on it too, so it isn't the rule)."""
    cov = cov or covered(L)
    laid = laid_by_unit(L)
    rows = []
    for u, unit in enumerate(L["units"]):
        mine = laid[u] & cov[u]
        tot = int(laid[u].sum())
        row = {"unit": u, "id": unit["id"], "kind": unit["kind"], "things": unit["things"],
               "laid": round(tot / laid[u].size, 4), "covered": round(float(mine.sum() / max(tot, 1)), 3)}
        inner = mine & (cv2.erode(laid[u].astype(np.uint8), np.ones((5, 5), np.uint8)) > 0)
        if inner.sum() >= 200:
            lab = ff.lab(L["P"][u]).astype(np.float32)
            lo, hi = (_masked_blur(lab, laid[u], b * L["ppi"]) for b in DETAIL_BAND)
            row["local"] = round(float(np.sqrt(((lo - hi) ** 2).sum(2))[inner].mean()), 2)
            mid = np.median(lab[inner], axis=0)
            row["spread"] = round(float(np.sqrt(((lab[inner] - mid) ** 2).sum(1)).mean()), 2)
        row["detail"] = row.get("local", 0.0) >= DETAIL
        rows.append(row)
    return rows


def main_paint(L: dict) -> list[str]:
    """Each unit's most-used paint: the one of its paints nearest the most pixels it lays. A unit that comes back to
    a thing takes the paint of the unit that started the thing (its first coat is the layer that shows)."""
    us, steps, laid = L["units"], L["steps"], laid_by_unit(L)
    out: list[str] = []
    for u, unit in enumerate(us):
        names = list(dict.fromkeys(p for i in unit["steps"] for p in steps[i]["paints"]))
        if unit["kind"] == "back":
            first = next(k for k in range(u) if set(us[k]["things"]) & set(unit["things"]))
            out.append(out[first])
            continue
        lab = _lab(L["P"][u])[laid[u]]
        d = np.stack([np.sqrt(((lab - ff.hex_lab(L["hexes"][p])) ** 2).sum(1)) for p in names])
        out.append(names[int(np.bincount(d.argmin(0), minlength=len(names)).argmax())])
    return out


# -------------------------------------------------------------------------------------------------- the hidden area
def _noise(shape: tuple, sigma: tuple[float, float], seed: int) -> np.ndarray:
    """Smooth noise in about -1..1, blurred sigma (along y, along x) pixels."""
    rng = np.random.default_rng(seed)
    n = cv2.GaussianBlur(rng.standard_normal(shape).astype(np.float32), (0, 0), sigmaX=sigma[1], sigmaY=sigma[0])
    return n / (3 * n.std() + 1e-6)


def soft(cov: np.ndarray, margin_px: float, ppi: float, seed: int = SEED) -> np.ndarray:
    """How hidden each pixel is (0 shows the layer, 1 hides it): the covered area shrunk by an uneven margin, faded
    in over RAMP inches with a ragged edge along the strokes' way. Nothing outside `cov` is hidden."""
    if not cov.any():
        return np.zeros(cov.shape, np.float32)
    dist = cv2.distanceTransform(cov.astype(np.uint8), cv2.DIST_L2, 5)
    wob = _noise(cov.shape, (WOBBLE_SIZE * ppi, WOBBLE_SIZE * ppi), seed)
    ramp = RAMP * ppi
    rag = _noise(cov.shape, (0.02 * ppi, 0.12 * ppi), seed + 1)  # streaks run side to side
    edge = margin_px * (1 + WOBBLE * np.clip(wob * 1.6, -1, 1))
    h = np.clip((dist - edge) / ramp + RAG * rag * 1.6, 0, 1)
    return (h * cov).astype(np.float32)


def reaches_edge(L: dict, region: np.ndarray) -> np.ndarray:
    """The parts of `region` joined to the canvas's edge (the canvas inside the frame)."""
    y0, y1, x0, x1 = L["crop"]
    n, lab = cv2.connectedComponents(region.astype(np.uint8), connectivity=4)
    rim = np.concatenate([lab[y0, x0:x1], lab[y1 - 1, x0:x1], lab[y0:y1, x0], lab[y0:y1, x1 - 1]])
    keep = np.zeros(n, bool)
    keep[np.unique(rim)] = True
    keep[0] = False
    return keep[lab] & region


LINE_REACH = 2.0  # inches: a layer stopped by `line` goes as deep as it is needed anywhere this far to each side
LINE_RUN = 1.5  # inches: a cover reaching the bottom edge must run at least this far up a column to stop a layer


def stop_line(L: dict, cov: np.ndarray, margin: float) -> np.ndarray:
    """How hidden each pixel is under `line` (the owner's ask on #289: "extend a bit past where they were needed for
    large areas that would be covered"). Only a cover that runs from the bottom edge of the canvas up counts. In each
    column, the layer is painted down to the deepest point it is needed within LINE_REACH inches to either side, then
    `margin` further, so its lower edge is a loose line past the valleys of what covers it, not the cover's outline.
    The line is smoothed and wobbles a little; below it is bare canvas. Everything else is painted through."""
    y0, y1, x0, x1 = L["crop"]
    c = cov[y0:y1, x0:x1]
    h, w = c.shape
    ppi = L["ppi"]
    # each column's covered run that reaches the bottom edge starts at `top` (h: none, or shorter than LINE_RUN)
    run = np.zeros((h, w), bool)
    run[-1] = c[-1]
    for y in range(h - 2, -1, -1):
        run[y] = run[y + 1] & c[y]
    top = np.where(run.any(0), run.argmax(0), h).astype(np.float32)
    top[(h - top) < LINE_RUN * ppi] = h
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
    return out


def parse(variant: str) -> tuple[str, float, str]:
    fill, margin, cov = variant.split("-")
    return fill, float(margin), cov


def variant_steps(L: dict, variant: str, base: list[np.ndarray] | None = None,
                  detail: list[dict] | None = None) -> dict:
    """The step pictures of a variant, and how hidden each pixel is after each step. Each step takes its unit's
    hidden area inside the pixels it lays and keeps the step before's everywhere else."""
    fill_kind, margin, which = parse(variant)
    base = base or baseline(L)
    cov = covered(L)
    if which in ("detail", "staged"):
        detail = detail or layer_detail(L, cov)
        rich = np.array([r["detail"] for r in detail] + [False])  # index -1: bare canvas
        cov = [c & rich[t] for c, t in zip(cov, tops(L))]
    if which in ("staged", "later"):  # a thing painted in the same stage is one passage with the layer (the clouds)
        cov = [c & later_stage(L, u) for u, c in enumerate(cov)]
    if fill_kind == "line":
        want = [stop_line(L, c, margin) for c in cov]
    else:
        want = [soft(c, margin * L["ppi"], L["ppi"]) for c in cov]
    paint = main_paint(L)
    wash = np.array([ff.hex_lab(L["hexes"][p]) for p in paint])  # Lab, a unit's row
    wash_rgb = np.array([np.array(Image.new("RGB", (1, 1), L["hexes"][p]))[0, 0] for p in paint], np.float32)
    top_after = tops(L)
    by = unit_of(L["units"])
    hide = np.zeros(L["m"][0].shape, np.float32)
    fill = np.empty(L["P"][0].shape, np.float32)
    fill[:] = ff.CANVAS
    pictures, hidden = [], []
    bare = np.ones(L["m"][0].shape, bool)
    for i, b in enumerate(base):
        u = by[i]
        where = L["m"][i]
        bare &= ~where
        hide = hide.copy()
        hide[where] = want[u][where]
        if fill_kind in ("wash", "edge", "open"):  # ("line" leaves bare canvas: the fill stays the canvas)
            fill = fill.copy()
            t = top_after[u][where]
            fill[where] = wash_rgb[np.maximum(t, 0)]
        if fill_kind in ("edge", "open"):  # bare canvas where the hidden area runs out to the edge or bare canvas
            out = reaches_edge(L, (hide > 0.5) | bare)
            fill[where & out] = ff.CANVAS
            if fill_kind == "open":  # an island isn't hidden: the layer is painted through it
                hide[where & ~out] = 0.0
        a = hide[..., None]
        pictures.append(np.clip(b.astype(np.float32) * (1 - a) + fill * a, 0, 255).astype(np.uint8))
        hidden.append(hide)
    del wash
    return {"pictures": pictures, "hidden": hidden, "paint": paint}


# ---------------------------------------------------------------------------------------------------- the numbers
def checks(L: dict, base: list[np.ndarray], var: list[np.ndarray]) -> dict:
    """build-steps' two checks on a variant: the share of the last picture that isn't the finish (by erase3.MOVED),
    and the most of the canvas any step changed outside where its unit lays paint (by steps3.LAID)."""
    gap = float((np.abs(var[-1].astype(np.int16) - L["P"][-1].astype(np.int16)).max(2) > erase3.MOVED).mean())
    by, laid = unit_of(L["units"]), laid_by_unit(L)
    worst = 0.0
    prev = np.full(var[0].shape, ff.CANVAS, np.float32)
    for i, pic in enumerate(var):
        moved = np.abs(pic.astype(np.float32) - prev).max(2) > 6
        worst = max(worst, float((moved & ~laid[by[i]]).mean()))
        prev = pic.astype(np.float32)
    return {"final_gap": round(gap, 5), "outside_unit_max": round(worst, 5)}


def spared(L: dict, base: list[np.ndarray], hidden: list[np.ndarray]) -> list[dict]:
    """For each step: the share of the paint it lays that the baseline shows and the variant hides (more than half
    hidden), and that share of the canvas."""
    out = []
    for i, s in enumerate(L["steps"]):
        lay = L["m"][i]
        h = hidden[i] > 0.5
        n = int(lay.sum())
        out.append({"n": i + 1, "id": s["id"], "laid": round(n / lay.size, 4),
                    "spared": round(float((lay & h).sum() / max(n, 1)), 3),
                    "spared_canvas": round(float((lay & h).mean()), 4)})
    return out


def changed_steps(base: list[np.ndarray], var: list[np.ndarray]) -> list[int]:
    return [i for i, (b, v) in enumerate(zip(base, var))
            if (np.abs(b.astype(np.int16) - v.astype(np.int16)).max(2) > erase3.MOVED).mean() >= SHOWN]


def measure(args) -> dict:
    out = {"variants": VARIANTS, "constants": {"DETAIL": DETAIL, "DETAIL_BAND": DETAIL_BAND, "RAMP": RAMP,
                                               "WOBBLE": WOBBLE, "RAG": RAG, "SHOWN": SHOWN}, "pictures": {}}
    for pic in args.picture or PICTURES:
        L = load(pic)
        base = baseline(L)
        cov = covered(L)
        detail = layer_detail(L, cov)
        steps_dir = BENCH / pic / "steps"
        drift = []  # the rebuilt baseline against the bench's own step pictures (900 px JPEGs)
        for i, b in enumerate(base):
            f = steps_dir / f"{i + 1:02d}.jpg"
            if f.exists():
                ref = _rgb(f)
                small = cv2.resize(on_canvas(L, b), (ref.shape[1], ref.shape[0]), interpolation=cv2.INTER_AREA)
                drift.append(round(float((np.abs(small.astype(np.int16) - ref).max(2) > erase3.MOVED).mean()), 4))
        own, png = owner_map(L), L["owner_png"].astype(np.int32)
        row = {"ppi": round(L["ppi"], 1), "units": [u["id"] for u in L["units"]],
               "baseline_vs_bench_max": max(drift) if drift else None,
               "owner_is_png": round(float((own == png).mean()), 4),
               "png_alone_agrees": round(float((last_laid(L) == png).mean()), 3),
               "layers": detail, "main_paint": main_paint(L), "variants": {}}
        for v in VARIANTS:
            r = variant_steps(L, v, base, detail)
            ch = changed_steps(base, r["pictures"])
            sp = spared(L, base, r["hidden"])
            row["variants"][v] = {"checks": checks(L, base, r["pictures"]), "changed": [i + 1 for i in ch],
                                  "spared": [sp[i] for i in ch],
                                  "spared_canvas_total": round(sum(sp[i]["spared_canvas"] for i in ch), 3)}
        out["pictures"][pic] = row
        print(pic, "layers:", [(r["id"], r["covered"], r.get("local"), r.get("spread")) for r in detail])
    if args.picture:  # one picture measured again: the others' numbers stay
        out["pictures"] = {**(state().get("pictures") or {}), **out["pictures"]}
    save({**state(), **out})
    return out


# ------------------------------------------------------------------------------------------------------- the sheets
def _font(size: int):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf"):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def _tile(img: np.ndarray, label: str, long: int = TILE) -> Image.Image:
    h, w = img.shape[:2]
    s = long / max(h, w)
    t = Image.fromarray(cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA))
    out = Image.new("RGB", (t.width, t.height + 22), "white")
    out.paste(t, (0, 22))
    ImageDraw.Draw(out).text((4, 3), label, fill=(30, 30, 30), font=_font(14))
    return out


def sheet(rows: list[list[tuple[np.ndarray, str]]], title: str, path: Path) -> None:
    tiles = [[_tile(img, lab) for img, lab in r] for r in rows]
    tw, th = tiles[0][0].width, tiles[0][0].height
    cols = max(len(r) for r in tiles)
    pad = 8
    out = Image.new("RGB", (cols * (tw + pad) + pad, len(tiles) * (th + pad) + pad + 30), (235, 235, 235))
    ImageDraw.Draw(out).text((pad, 6), title, fill=(0, 0, 0), font=_font(18))
    for r, row in enumerate(tiles):
        for c, t in enumerate(row):
            out.paste(t, (pad + c * (tw + pad), 30 + pad + r * (th + pad)))
    out.save(path, quality=86)


def sheets(args) -> list[str]:
    """Stage 1's sheets: for each picture and each question, a row a step that changes, baseline first."""
    made = []
    groups = {
        "fill": [f"{f}-{args.margin:g}-{args.cover}" for f in FILLS],
        "pick": [f"{f}-{args.margin:g}-{c}" for f in ("wash", "edge") for c in ("detail", "staged")],
        "margin": [f"{args.fill}-{m:g}-{args.cover}" for m in MARGINS],
        "covers": [f"{args.fill}-{args.margin:g}-{c}" for c in COVERS],
    }
    for pic in args.picture or PICTURES:
        L = load(pic)
        base = baseline(L)
        detail = layer_detail(L)
        for g in args.group or list(groups):
            vs = groups[g]
            res = {v: variant_steps(L, v, base, detail)["pictures"] for v in vs}
            ch = sorted({i for v in vs for i in changed_steps(base, res[v])})
            rows = [[(on_canvas(L, base[i]), f"{i + 1}. {L['steps'][i]['id']}: baseline")]
                    + [(on_canvas(L, res[v][i]), v) for v in vs] for i in ch]
            for k in range(0, len(rows), args.per):
                part = "" if len(rows) <= args.per else f"-{k // args.per + 1}"
                path = Path(args.out) / f"cover-margin-{pic}-{g}{part}.jpg"
                sheet(rows[k:k + args.per], f"{pic}: {g} ({', '.join(vs)})", path)
                made.append(str(path))
    print("\n".join(made))
    return made


def steps_out(args) -> None:
    """One variant's step pictures as JPEGs, `NN.jpg` as the bench keeps them (900 pixels on the long side)."""
    out = Path(args.out)
    for pic in args.picture or PICTURES:
        L = load(pic)
        base = baseline(L)
        res = variant_steps(L, args.variant, base)["pictures"]
        d = out / pic
        d.mkdir(parents=True, exist_ok=True)
        for i, img in enumerate(base if args.variant == "baseline" else res):
            img = on_canvas(L, img)
            h, w = img.shape[:2]
            s = 900 / max(h, w)
            Image.fromarray(cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)).save(
                d / f"{i + 1:02d}.jpg", quality=92)


# --------------------------------------------------------------------------------------------- stage 2: the words
PICK = "edge-1-staged"  # stage 1's pick (docs/spikes/cover-margin.md)
WORK = Path(tempfile.gettempdir()) / "gesso-cover-margin"
STUDENT = HERE / "cover_margin"  # the student test's answers: variant.json, and base.json for the baseline's second carry
BRIEF = ROOT / ".claude" / "skills" / "paint-lesson" / "v3" / "lesson-brief.md"
ADDED = ("In the steps you write here, a layer stops a little past where a later thing will cover it, and the "
         "picture leaves the rest bare or as one flat coat: say how far the layer goes, in inches from an edge or "
         "from a thing already painted.")
LINE_KEYS = [("first", "First"), ("start", "Start"), ("strokes", "Strokes"), ("inside", "Where the paint sits"),
             ("leave", "Leave"), ("stop", "Stop when")]


def state() -> dict:
    return json.loads(RESULTS.read_text()) if RESULTS.exists() else {}


def save(st: dict) -> None:
    RESULTS.write_text(json.dumps(st, indent=1) + "\n")


def stopped_short(L: dict, hidden: np.ndarray, i: int, fill: np.ndarray) -> dict | None:
    """What step i leaves out, measured on its picture: the box of the part of its paint the variant hides, in
    inches from the canvas's edges, and whether that part shows bare canvas or a flat coat."""
    y0, y1, x0, x1 = L["crop"]
    h = (hidden[i] > 0.5)[y0:y1, x0:x1]
    if h.mean() < SHOWN:
        return None
    ys, xs = np.nonzero(h)
    ppi = L["ppi"]
    hh, ww = h.shape
    bare = float((np.abs(fill[y0:y1, x0:x1][h] - np.array(ff.CANVAS, np.float32)).max(1) < 6).mean())
    return {"left": xs.min() / ppi, "right": (ww - 1 - xs.max()) / ppi, "top": ys.min() / ppi,
            "bottom": (hh - 1 - ys.max()) / ppi, "bare": round(bare, 2), "share": round(float(h.mean()), 3)}


def bench(args) -> None:
    """A copy of the gate's bench with the variant's step pictures, in the work folder (`<work>/bench/<picture>`),
    for the student test and the A/B folders. The words of the steps that changed are put in by `words`."""
    import shutil
    st = state()
    for pic in args.picture or PICTURES:
        L = load(pic)
        base = baseline(L)
        r = variant_steps(L, args.variant, base)
        ch = changed_steps(base, r["pictures"])
        dest = Path(args.work) / f"bench{args.tag}" / pic
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(BENCH / pic, dest, ignore=shutil.ignore_patterns("chain"), copy_function=shutil.copyfile)
        for i, img in enumerate(r["pictures"]):
            img = on_canvas(L, img)
            h, w = img.shape[:2]
            k = 900 / max(h, w)
            Image.fromarray(cv2.resize(img, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA)).save(
                dest / "steps" / f"{i + 1:02d}.jpg", quality=92)
        rows = []
        for i in ch:
            # what shows where the variant hides paint: the picture itself there (bare canvas or a flat coat)
            ss = stopped_short(L, r["hidden"], i, r["pictures"][i].astype(np.float32))
            rows.append({"n": i + 1, "id": L["steps"][i]["id"], "hidden": ss})
        st.setdefault(f"bench{args.tag}", {})[pic] = {"variant": args.variant, "changed": rows}
        if args.words_from:  # the changed steps' words, from a run whose pictures of those steps are the same
            src_tag = "" if args.words_from == "base" else args.words_from
            same = {c["id"] for c in st[f"bench{src_tag}"][pic]["changed"]}
            src = json.loads((Path(args.work) / f"bench{src_tag}" / pic / "packet.json").read_text())
            packet = json.loads((dest / "packet.json").read_text())
            new = {x["id"]: x for x in src["steps"]}
            for x in packet["steps"]:
                if x["id"] in {r["id"] for r in rows}:
                    if x["id"] not in same:
                        raise SystemExit(f"{pic} {x['id']}: no words written for this picture")
                    x["lines"] = new[x["id"]]["lines"]
            (dest / "packet.json").write_text(json.dumps(packet, indent=1) + "\n")
            sys.path.insert(0, str(HERE))
            import v31_gate
            (dest / "lesson.md").write_bytes(v31_gate.md(pic, packet["steps"], packet["opening"]).encode("utf-8"))
        print(pic, "changed steps:", [x["n"] for x in rows])
    save(st)


def writer_blocks(pic: str, work: Path, tag: str = "", only: list[int] | None = None) -> list[dict]:
    """What the lesson's writer is sent for the changed steps of one picture: lesson-brief.md with one added
    sentence, the changed steps' headers, facts and cards, the plan, the photo and finish, and each changed step's
    pair and change pictures (made from the variant's pictures, as `packets` makes them)."""
    sys.path.insert(0, str(HERE))
    import facts
    import lesson_words as lw
    import v4_student as student
    st = dict(state()[f"bench{tag}"][pic])
    if only:  # the steps after a changed one: their own picture is the same, the one before it isn't
        st["changed"] = [{"n": n, "id": None, "hidden": None} for n in only]
    b = work / f"bench{tag}" / pic
    packet = json.loads((b / "packet.json").read_text())
    sheet = json.loads((b / "data" / "words" / "sheet.json").read_text())
    plan = json.loads((b / "data" / "plan.json").read_text())
    stroke = {x["id"]: x.get("stroke") for x in plan3.steps(plan)}
    rows = {x["id"]: x for x in sheet["steps"]}
    by_n = {x["n"]: x for x in packet["steps"]}
    brief = BRIEF.read_text()
    brief = brief[:brief.index("## What you are sent")] + ADDED + "\n\n" + brief[brief.index("## What a step says"):]
    brief = brief[:brief.index("## What to write")]
    head, fact_rows, cards = ["# The steps you write (their headers, as the page shows them)", ""], [], []
    for c in st["changed"]:
        s = by_n[c["n"]]
        paints = "; ".join(f"{p['name']} ({p['recipe']})" for p in s["paints"])
        head.append(f"- step {s['n']} `{s['id']}`: {s['name']}. Part: {rows[s['id']]['part_name']}. Paints: {paints}. "
                    f"Brush: {s['brushes']}. Stroke card: {stroke.get(s['id'])}.")
        f = facts.facts_text(sheet, {}, rows[s["id"]])
        h = c["hidden"]
        if h:
            look = "bare canvas" if h["bare"] > 0.5 else "one flat coat"
            f += ("\nWhat this step's picture leaves out (a later step covers it): that part shows " + look + "; "
                  f"its top {facts.q(h['top'])} from the top edge, its bottom {facts.q(h['bottom'])} from the bottom "
                  f"edge, its left side {facts.q(h['left'])} from the left edge, its right side {facts.q(h['right'])} "
                  "from the right edge.")
        fact_rows += [f, ""]
        if stroke.get(s["id"]):
            cards.append(stroke[s["id"]])
    canvas = packet["canvas_in"]
    head += ["", f"The canvas is {canvas[0]:g} in wide and {canvas[1]:g} in tall, and the lesson has "
                 f"{len(packet['steps'])} steps. You write only the steps above; the others keep their words."]
    blocks = student.text_block(
        brief + "## What you are sent\n\nEverything is in this message: the steps you write, their facts and stroke "
        "cards, the plan, the photo and the finished painting, and for each step its pair (before on the left, after "
        "on the right) and its change (only what the step changed, at full colour).\n\n## What to write\n\nReply "
        "with one ```json block, `{\"steps\": {\"<step id>\": {\"first\": \"\", \"start\": \"...\", \"strokes\": \"...\", "
        "\"inside\": \"...\", \"leave\": \"...\", \"stop\": \"...\"}}}`, with an entry for every step you write, then one "
        "line: anything in the pictures your words couldn't square.")
    blocks += student.text_block("\n".join(head))
    blocks += student.text_block("# Facts\n\n" + facts.lean("\n".join(fact_rows)))
    blocks += student.text_block(lw.card_text(list(dict.fromkeys(cards))))
    blocks += student.text_block("# plan.json\n\n" + json.dumps(plan, indent=1))
    blocks += student.text_block("photo.jpg:") + student.picture_block(Image.open(b / "photo.jpg").convert("RGB"), 768)
    blocks += student.text_block("finish.jpg:") + student.picture_block(Image.open(b / "finish.jpg").convert("RGB"), 768)
    for c in st["changed"]:
        n = c["n"]
        after = Image.open(b / "steps" / f"{n:02d}.jpg").convert("RGB")
        before = Image.open(b / "steps" / f"{n - 1:02d}.jpg").convert("RGB") if n > 1 else Image.new(
            "RGB", after.size, lw.BLANK)
        blocks += student.text_block(f"pair-{n:02d}.jpg (step {n}):") + student.picture_block(lw.pair_picture(before, after), 1600)
        ch = lw.change_picture(before, after)
        blocks += student.text_block(f"change-{n:02d}.jpg (step {n}):") + student.picture_block(ch, lw.CHANGE_SIDE)
    return blocks


def words(args) -> None:
    """The lesson writer (Opus, one fresh call a picture) rewrites the changed steps; their lines go into the work
    bench's packet.json and lesson.md, in the page's form."""
    sys.path.insert(0, str(HERE))
    import v31_gate
    from v4_loop import call_claude, cost, last_json
    st = state()
    work = Path(args.work)
    cwd = work / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    for pic in args.picture or PICTURES:
        if not st[f"bench{args.tag}"][pic]["changed"]:
            continue
        if pic in st.get(f"words{args.tag}", {}) and not args.again:
            out = st[f"words{args.tag}"][pic]
        else:
            r = call_claude(writer_blocks(pic, work, args.tag), "You are a painting teacher writing a beginner's lesson.", cwd=cwd)
            ans = last_json(r["text"])
            out = {"steps": ans["steps"], "note": r["text"].strip().splitlines()[-1][:400],
                   "cost_usd": round(cost(r["usage"]), 4), "seconds": r["seconds"],
                   "usage": {k: r["usage"].get(k) for k in ("input_tokens", "output_tokens",
                                                             "cache_creation_input_tokens", "cache_read_input_tokens")}}
            st.setdefault(f"words{args.tag}", {})[pic] = out
            save(st)
        if args.after and not out.get("after"):  # #289's stage 2 left these out: their old words describe the old canvas
            changed = {c["n"] for c in st[f"bench{args.tag}"][pic]["changed"]}
            count = len(json.loads((work / f"bench{args.tag}" / pic / "packet.json").read_text())["steps"])
            nxt = sorted({n + 1 for n in changed if n + 1 not in changed and n + 1 <= count})
            r = call_claude(writer_blocks(pic, work, args.tag, nxt), "You are a painting teacher writing a beginner's lesson.",
                            cwd=cwd)
            out["steps"].update(last_json(r["text"])["steps"])
            out["after"] = {"steps": nxt, "cost_usd": round(cost(r["usage"]), 4)}
            save(st)
        b = work / f"bench{args.tag}" / pic
        packet = json.loads((b / "packet.json").read_text())
        for s in packet["steps"]:
            w = out["steps"].get(s["id"])
            if not w:
                continue
            back = [x for x in s["lines"] if x.startswith("As in step ")]
            lines = [f"{label}: {w[k].strip()}" for k, label in LINE_KEYS if (w.get(k) or "").strip()]
            s["lines"] = lines[:1] + back + lines[1:] if lines and lines[0].startswith("First") else back + lines
        (b / "packet.json").write_text(json.dumps(packet, indent=1) + "\n")
        (b / "lesson.md").write_bytes(v31_gate.md(pic, packet["steps"], packet["opening"]).encode("utf-8"))
        print(pic, f"${out['cost_usd']:.2f}", out["note"][:200])


def ab(args) -> None:
    """Two blind folders a picture (`bench/ab_grader.md`), the variant on side A in one and side B in the other, the
    key beside them in the results. The baseline side is the gate's own lesson."""
    import shutil
    sys.path.insert(0, str(HERE))
    import v31_gate
    st = state()
    out = Path(args.work) / f"ab{args.tag}"
    key = {}
    for pic in PICTURES:
        if not st[f"bench{args.tag}"][pic]["changed"]:  # the same lesson on both sides: "none" without a grader
            continue
        for g, new_side in ((1, "A"), (2, "B")):
            f = out / f"{pic}-g{g}"
            if f.exists():
                shutil.rmtree(f)
            f.mkdir(parents=True)
            old_side = "B" if new_side == "A" else "A"
            v31_gate.side_folder(Path(args.work) / f"bench{args.tag}" / pic, f / new_side)
            v31_gate.side_folder(BENCH / pic, f / old_side)
            key[f.name] = {"picture": pic, "grader": g, new_side: "variant", old_side: "baseline"}
    st[f"ab_key{args.tag}"] = key
    save(st)
    print(sorted(key))


def grade_blocks(folder: Path) -> list[dict]:
    import v4_student as student
    brief = (HERE / "bench" / "ab_grader.md").read_text()
    blocks = student.text_block(brief.replace("Read only that folder.", "Everything in it is in this message.")
                                .replace("`grade.json` in the folder you were given:", "Reply with one ```json block:"))
    for side in ("A", "B"):
        d = folder / side
        blocks += student.text_block(f"# Lesson {side}\n\n{side}/photo.jpg:")
        blocks += student.picture_block(Image.open(d / "photo.jpg").convert("RGB"), 768)
        blocks += student.text_block(f"{side}/finish.jpg:")
        blocks += student.picture_block(Image.open(d / "finish.jpg").convert("RGB"), 768)
        blocks += student.text_block(f"{side}/lesson.md:\n\n" + (d / "lesson.md").read_text())
        packet = json.loads((d / "packet.json").read_text())
        for s in packet["steps"]:
            blocks += student.text_block(f"{side}/{s['pair']} (step {s['n']}, before and after):")
            blocks += student.picture_block(Image.open(d / s["pair"]).convert("RGB"), 1100)
    return blocks


def grade(args) -> None:
    """Each A/B folder read by a grader in a fresh context (Opus, one call, no tools)."""
    from concurrent.futures import ThreadPoolExecutor
    from v4_loop import call_claude, cost, last_json
    st = state()
    out = Path(args.work) / f"ab{args.tag}"
    cwd = Path(args.work) / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    done = {r["folder"] for r in st.get(f"ab{args.tag}", [])}
    todo = [n for n in sorted(st[f"ab_key{args.tag}"]) if n not in done]

    def one(name):
        import re
        usd = 0.0
        for _ in range(3):  # a reply whose JSON doesn't parse is asked for again, and its cost still counts
            r = call_claude(grade_blocks(out / name), "You grade painting lessons in the owner's place.", cwd=cwd)
            usd += cost(r["usage"])
            for text in (r["text"], re.sub(r",(\s*[}\]])", r"\1", r["text"])):
                try:
                    return name, last_json(text), round(usd, 4)
                except ValueError:
                    pass
        raise RuntimeError(f"{name}: three replies with no readable JSON")

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for name, g, usd in ex.map(one, todo):
            k = st[f"ab_key{args.tag}"][name]
            prefer = g.get("prefer")
            st.setdefault(f"ab{args.tag}", []).append({
                "folder": name, "picture": k["picture"], "grader": k["grader"],
                "preferred": k[prefer] if prefer in ("A", "B") else "none",
                "scores": {k[s]: v for s, v in (g.get("scores") or {}).items() if s in ("A", "B")},
                "note": g.get("note", ""), "cost_usd": usd})
            save(st)
            print(f"{name}: prefers {st[f'ab{args.tag}'][-1]['preferred']} (${usd:.2f}): {g.get('note', '')[:160]}")


def solo_grades(path: Path, rep: int | None = None) -> dict:
    ss = json.loads(path.read_text()) if path.exists() else {}
    g: dict = {}
    for r in ss.get("carry_grades", []):
        if r.get("solo") and r["condition"] == "words" and (rep is None or r["rep"] == rep):
            g.setdefault((r["picture"], r["n"]), []).append(r["grade"])
    return g


def report(args) -> dict:
    """The student test on the changed steps (the gate's carries and a second baseline carry against the variant's
    two), the blind graders and the painted area spared, into cover_margin.json's `report`."""
    st = state()
    base = solo_grades(HERE / "v31_gate" / "student.json")
    for k, v in solo_grades(STUDENT / "base.json").items():
        base.setdefault(k, []).extend(v)
    var = solo_grades(STUDENT / "variant.json")
    out: dict = {"student": {}, "ab": {}, "spared": {}}
    allb, allv = [], []
    for pic in PICTURES:
        ch = [c["n"] for c in st.get("bench", {}).get(pic, {}).get("changed", [])]
        b = [float(np.mean(base[(pic, n)])) for n in ch if (pic, n) in base and (pic, n) in var]
        v = [float(np.mean(var[(pic, n)])) for n in ch if (pic, n) in base and (pic, n) in var]
        allb += b
        allv += v
        out["student"][pic] = {"steps": len(b), "baseline": round(float(np.mean(b)), 2) if b else None,
                               "variant": round(float(np.mean(v)), 2) if v else None,
                               "per_step": {n: [base.get((pic, n)), var.get((pic, n))] for n in ch}}
        out["ab"][pic] = {(tag and "open-1-staged") or PICK: [r["preferred"] for r in st.get(f"ab{tag}", []) if r["picture"] == pic]
                          for tag in ("", "-open")}
        sp = st["pictures"][pic]["variants"].get(st.get("bench", {}).get(pic, {}).get("variant", PICK), {})
        out["spared"][pic] = {"canvas_total": sp.get("spared_canvas_total"),
                              "steps": {r["n"]: r["spared"] for r in sp.get("spared", [])}}
    d = np.array(allv) - np.array(allb)
    out["student"]["all"] = {"steps": len(d), "baseline": round(float(np.mean(allb)), 2) if allb else None,
                             "variant": round(float(np.mean(allv)), 2) if allv else None,
                             "gain": round(float(d.mean()), 2) if len(d) else None,
                             "se": round(float(d.std(ddof=1) / np.sqrt(len(d))), 2) if len(d) > 1 else None}
    costs = {"words": round(sum(w["cost_usd"] + (w.get("after") or {}).get("cost_usd", 0)
                                for t in ("", "-line") for w in st.get(f"words{t}", {}).values()), 2),
             "graders": round(sum(r.get("cost_usd", 0) for t in ("ab", "ab-open") for r in st.get(t, [])), 2)}
    for f in ("variant", "base"):
        p = STUDENT / f"{f}.json"
        if p.exists():
            ss = json.loads(p.read_text())
            costs[f"renders_{f}"] = round(sum(r["render_usd"] for r in ss.get("carry", [])), 3)
            costs[f"carry_grades_{f}"] = round(sum(r.get("cost_usd", 0) for r in ss.get("calls", [])), 2)
    out["cost"] = costs
    st["report"] = out
    save(st)
    print(json.dumps(out, indent=1))
    return out


def owner_sheet(args) -> None:
    """The sheet for the owner: the cow's sky, hills and hillside steps, the baseline above the pick, each picture
    with its words as the page gives them."""
    import textwrap
    steps = [int(x) for x in args.steps.split(",")]
    sides = [("As it is", BENCH / args.picture), ("Stopped short", Path(args.work) / "bench" / args.picture)]
    col, pad, font, small = 440, 14, _font(15), _font(13)
    cells = []
    for title, b in sides:
        packet = json.loads((b / "packet.json").read_text())
        row = []
        for n in steps:
            s = packet["steps"][n - 1]
            img = Image.open(b / "steps" / f"{n:02d}.jpg").convert("RGB")
            img.thumbnail((col, col))
            lines = []
            for x in s["lines"]:
                lines += textwrap.wrap(x, 62) + [""]
            row.append((f"{title}: step {n}, {s['name']}", img, lines))
        cells.append(row)
    pic_h = max(c[1].height for r in cells for c in r)
    txt_h = max(len(c[2]) for r in cells for c in r) * 17
    cell_h = 26 + pic_h + 8 + txt_h
    out = Image.new("RGB", (len(steps) * (col + pad) + pad, 2 * (cell_h + pad) + pad + 34), "white")
    d = ImageDraw.Draw(out)
    d.text((pad, 8), f"{args.picture}: the lesson as it is (top) and with each layer stopped short (bottom)", fill=(0, 0, 0),
           font=_font(19))
    for r, row in enumerate(cells):
        y0 = 34 + pad + r * (cell_h + pad)
        for c, (title, img, lines) in enumerate(row):
            x0 = pad + c * (col + pad)
            d.text((x0, y0), title, fill=(20, 20, 20), font=font)
            out.paste(img, (x0, y0 + 26))
            for k, line in enumerate(lines):
                d.text((x0, y0 + 26 + pic_h + 8 + k * 17), line, fill=(40, 40, 40), font=small)
        if r == 0:
            d.line((pad, y0 + cell_h + pad // 2, out.width - pad, y0 + cell_h + pad // 2), fill=(150, 150, 150), width=2)
    out.save(args.out, quality=88)
    print(args.out)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--picture", action="append")
    s = sub.add_parser("sheets")
    s.add_argument("--picture", action="append")
    s.add_argument("--group", action="append", choices=["fill", "margin", "covers", "pick"])
    s.add_argument("--fill", default="wash", choices=FILLS)
    s.add_argument("--margin", type=float, default=0.75)
    s.add_argument("--cover", default="all", choices=COVERS)
    s.add_argument("--per", type=int, default=8)
    s.add_argument("--out", default=str(DOCS))
    o = sub.add_parser("steps")
    o.add_argument("--picture", action="append")
    o.add_argument("--variant", required=True, choices=VARIANTS + ["baseline"])
    o.add_argument("--out", required=True)
    for name in ("bench", "words", "ab", "grade"):
        x = sub.add_parser(name)
        x.add_argument("--work", default=str(WORK))
        x.add_argument("--tag", default="", help="keeps a second variant's bench and graders apart (`-open`)")
        if name == "bench":
            x.add_argument("--variant", default=PICK, choices=VARIANTS)
        if name in ("bench", "words"):
            x.add_argument("--picture", action="append")
        if name == "bench":
            x.add_argument("--words-from", help="take the changed steps' words from the bench of this tag (`base`: the first run)")
        if name == "words":
            x.add_argument("--again", action="store_true")
            x.add_argument("--after", action="store_true", help="also the step after each changed run (its canvas before changed)")
        if name == "grade":
            x.add_argument("--workers", type=int, default=3)
    sub.add_parser("report")
    ow = sub.add_parser("owner-sheet")
    ow.add_argument("--work", default=str(WORK))
    ow.add_argument("--picture", default="highland-cow")
    ow.add_argument("--steps", default="1,4,7")
    ow.add_argument("--out", default=str(DOCS / "cover-margin-owner-cow.jpg"))
    a = ap.parse_args(argv)
    {"measure": measure, "sheets": sheets, "steps": steps_out, "bench": bench, "words": words, "ab": ab,
     "grade": grade, "report": report, "owner-sheet": owner_sheet}[a.cmd](a)


if __name__ == "__main__":
    main()
