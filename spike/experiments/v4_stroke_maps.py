"""Spike for #256 (v4, P1): stroke maps, a few arrows on a step's picture showing where the strokes go.

On the frozen bench (`spike/experiments/bench/v3-words/`), on v3's pictures and the adopted words (lesson-slots with
the long arc, `arc-add-long`, `v4_arc.py`), so only the map differs. A map is the step's before picture with at most
four arrows drawn on it by a tool (never the image model): a numbered dot where to start, and an arrow along the way
the strokes run, bent where the strokes bend. It shows this step only.

Three ways to get the arrows (`VARIANTS`):

- `change`: from what the step changed alone. The change is the student test's own mask (`v4_student.change_mask`).
  Inside it, the grain of the new paint (a structure tensor of the after picture, and of the change itself for thin
  marks) gives the strokes' direction at every point, and each arrow is a line traced along that grain from the
  deepest point of one of the change's biggest pieces. Where to start comes from the biggest piece, top end first.
- `writer`: one fresh Claude call a step reads the step's words, its before and after pictures and the change, on a
  grid in inches, and names the start and up to four arrows as points in inches. The tool draws them.
- `both`: the same call, also shown the `change` arrows and asked to keep, move or replace them. Where the words'
  stroke direction and the picture's grain disagree it follows the picture and says so (`disagrees`).

How the map reaches the tests:

- **The student (carry)** gets two pictures: the canvas as it is, and the map (the same canvas with the arrows).
  Its prompt says the second picture is the step's stroke map and the arrows are not to be painted. The grader still
  sees only the before, the real after and the result.
- **The grain measure** (`grain`, no Claude): how well the result's strokes run the way the real after's do, tile by
  tile inside the change, as the mean of cos(2 x the angle between them), weighted by how clearly each has a grain.
  1 is the same direction everywhere, 0 no relation, -1 crossways. It runs on the baseline's results too.
- **The blind graders** (`bench/ab_grader.md`, two a picture, sides swapped) see the words with the map against the
  same words without it.

    .venv/bin/python spike/experiments/v4_stroke_maps.py maps [--variant change] [--picture P]
    .venv/bin/python spike/experiments/v4_stroke_maps.py sheet --variant change,writer,both --picture P --out sheet.jpg
    .venv/bin/python spike/experiments/v4_stroke_maps.py carry --variant change [--steps 1,2] [--budget 2]
    .venv/bin/python spike/experiments/v4_stroke_maps.py grade --variant change
    .venv/bin/python spike/experiments/v4_stroke_maps.py ab --variant change
    .venv/bin/python spike/experiments/v4_stroke_maps.py report

The words are read from `<temp>/gesso-v4-arc/words/arc-add-long` (`v4_arc.py packets` remakes them); the near
misses carry's measure reads from `<temp>/gesso-v4-student/pick` (`v4_student.py prepare`). Maps go in
`<temp>/gesso-v4-maps`. The arrows, the writers' answers and every call's tokens go in
`spike/experiments/v4_stroke_maps.json`; the student test's answers in `spike/experiments/v4_stroke_maps/<variant>.json`.
Experiment code: it reads the frozen bench and the arc spike's words, and changes no tool.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "spike"))

import v4_student as student  # noqa: E402

BENCH = student.BENCH
PICTURES = student.PICTURES
RESULTS = HERE / "v4_stroke_maps.json"
STUDENT_DIR = HERE / "v4_stroke_maps"
BASE = "arc-add-long"  # the adopted words (#255): the baseline
BASE_STUDENT = HERE / "v4_arc" / f"{BASE}.json"
TMP = Path(tempfile.gettempdir())
WORDS = TMP / "gesso-v4-arc" / "words" / BASE
WORK = TMP / "gesso-v4-maps"
VARIANTS = ["change", "writer", "both"]
SEED = 256
LOCK = threading.Lock()

FIELD_SIDE = 360  # where the grain is found, long side
MAP_SIDE = 1024  # the map picture, long side
MAX_ARROWS = 4
MIN_PIECE = 0.12  # a piece of the change gets an arrow if it holds this share of the change
MIN_AREA = 0.002  # ... and this share of the canvas


# ------------------------------------------------------------------------------------------------------- the grain
def grain_field(before, after, side: int = FIELD_SIDE):
    """The strokes' direction at every point of the step's change, at `side` pixels.

    Returns (mask, angle, coherence): angle in radians (0 runs side to side, pi/2 top to bottom, mod pi), coherence 0
    to 1 (how clearly the paint there has a grain). The grain is the structure tensor of the after picture's
    lightness inside the change, plus that of the change's own strength, so a thin mark (a whisker, a branch) gets its
    own length as its grain. The change's outer edge is left out of the first, or every fill would run along its
    outline."""
    import cv2
    m = student.change_mask(before, after, side)
    la, lb = student.lab(after, side, 1.0), student.lab(before, side, 1.0)
    d = np.linalg.norm(la - lb, axis=2)
    L = la[..., 0]
    inner = cv2.erode(m.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32)

    def tensor(img, w):
        gx = cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(img, cv2.CV_32F, 0, 1, ksize=3)
        return gx * gx * w, gy * gy * w, gx * gy * w

    a1, b1, c1 = tensor(L, inner)
    a2, b2, c2 = tensor(np.minimum(d, 30.0), m)  # the change's own shape, capped so its edge doesn't swamp
    sig = side / 60
    jxx, jyy, jxy = (cv2.GaussianBlur(x, (0, 0), sig) for x in (a1 + 0.5 * a2, b1 + 0.5 * b2, c1 + 0.5 * c2))
    grad = 0.5 * np.arctan2(2 * jxy, jxx - jyy)  # the direction the colour changes fastest
    angle = np.mod(grad + np.pi / 2, np.pi)  # strokes run across it
    tr = jxx + jyy
    coh = np.where(tr > 1e-6, np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / np.maximum(tr, 1e-6), 0.0)
    return m, angle.astype(np.float32), np.clip(coh, 0, 1).astype(np.float32)


def grain_tiles(mask, angle, coh, tiles: int = 12):
    """The field summed tile by tile: {(i, j): (angle, strength)} for tiles with enough change in them."""
    h, w = mask.shape
    out = {}
    for i in range(tiles):
        for j in range(tiles):
            sl = (slice(i * h // tiles, (i + 1) * h // tiles), slice(j * w // tiles, (j + 1) * w // tiles))
            mm = mask[sl]
            if mm.mean() < 0.3:
                continue
            c, a = coh[sl] * mm, angle[sl]
            x, y = float((c * np.cos(2 * a)).sum()), float((c * np.sin(2 * a)).sum())
            n = float(mm.sum())
            out[(i, j)] = (0.5 * math.atan2(y, x), math.hypot(x, y) / n)
    return out


def grain(before, after, result) -> dict:
    """How well the result's strokes run the way the real after's do, inside the real change (see the module doc).
    `agree`: the weighted mean of cos(2 x the angle between them) over the tiles where both changed; `tiles`: how
    many; `real_coherence`: how clearly the real step has a grain at all (a flat fill has little)."""
    res = result.resize(after.size)
    m, a, c = grain_field(before, after)
    mr, ar, cr = grain_field(before, res)
    tr, tg = grain_tiles(m, a, c), grain_tiles(np.minimum(m, mr), ar, cr)
    num = den = 0.0
    for k, (ang, s) in tr.items():
        if k in tg:
            ang2, s2 = tg[k]
            wgt = s * s2
            num += wgt * math.cos(2 * (ang - ang2))
            den += wgt
    return {"agree": round(num / den, 3) if den > 1e-9 else None, "tiles": sum(1 for k in tr if k in tg),
            "real_coherence": round(float(np.mean([s for _, s in tr.values()])), 3) if tr else 0.0}


# ------------------------------------------------------------------------------------ arrows from the change alone
def trace(seed, angle, coh, inside, max_len: float, step: float = 1.5):
    """A line from `seed` along the grain both ways, until it leaves `inside` or runs `max_len` pixels: [(x, y)]."""
    h, w = inside.shape

    def one(sign):
        pts, (x, y) = [], seed
        prev = None
        n = 0
        while n * step < max_len / 2:
            xi, yi = int(round(x)), int(round(y))
            if not (0 <= xi < w and 0 <= yi < h) or not inside[yi, xi]:
                break
            t = float(angle[yi, xi])
            v = np.array([math.cos(t), math.sin(t)])
            if prev is None:
                v = v * sign
            elif float(v @ prev) < 0:
                v = -v
            if prev is not None and float(v @ prev) < 0.7:  # turned more than about 45 degrees in one step
                break
            pts.append((x, y))
            prev = v
            x, y = x + step * v[0], y + step * v[1]
            n += 1
        return pts

    fwd, back = one(1), one(-1)
    return list(reversed(back[1:])) + fwd


def change_arrows(before, after) -> dict:
    """The `change` variant: up to MAX_ARROWS lines along the change's grain, in canvas fractions (0 to 1 from the
    left and from the top), the first one's first point where to start.

    The arrows are shared out among the change's biggest pieces by area (at least one each, up to three pieces).
    Inside a piece, each arrow starts from a point deep inside it, as far as possible from the others (the canvas
    edge counts as the piece's edge), and is traced along the grain, smoothed so it bends only where the strokes do,
    for about a third of the canvas at most."""
    import cv2
    m, angle, coh = grain_field(before, after)
    h, w = m.shape
    total = m.sum()
    if total < 20:
        return {"arrows": [], "note": "the step changed almost nothing"}
    # a smoother field to trace along: the doubled angle blurred, so a line can't zigzag on brush texture
    c2, s2 = (cv2.GaussianBlur((coh * f(2 * angle)).astype(np.float32), (0, 0), max(h, w) / 30) for f in (np.cos, np.sin))
    smooth = np.mod(0.5 * np.arctan2(s2, c2), np.pi)
    n, lab_, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    pieces = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])
    pieces = [i for i in pieces if stats[i, cv2.CC_STAT_AREA] >= max(MIN_PIECE * total, MIN_AREA * h * w)][:3]
    if not pieces:
        pieces = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])[:1]
    areas = np.array([stats[i, cv2.CC_STAT_AREA] for i in pieces], dtype=float)
    share = np.ones(len(pieces), int)
    while share.sum() < MAX_ARROWS and (areas / share).max() > 0.04 * h * w:
        share[int(np.argmax(areas / share))] += 1
    arrows = []
    for i, k in zip(pieces, share):
        piece = (lab_ == i).astype(np.uint8)
        dist = cv2.distanceTransform(np.pad(piece, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
        ok = dist >= max(2.0, 0.35 * dist.max())
        ys, xs = np.nonzero(ok)
        if len(xs) == 0:
            continue
        seeds = [int(np.argmax(dist[ys, xs]))]
        while len(seeds) < k:  # farthest-point sampling among the deep points
            d = np.min([np.hypot(xs - xs[j], ys - ys[j]) for j in seeds], axis=0)
            j = int(np.argmax(d))
            if d[j] < 0.12 * max(h, w):
                break
            seeds.append(j)
        extent = math.hypot(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT])
        for j in seeds:
            pts = trace((float(xs[j]), float(ys[j])), smooth, coh, piece.astype(bool),
                        max_len=min(0.85 * extent, 0.33 * max(h, w)))
            if len(pts) < 4:  # too small to trace: a short arrow along the grain at the seed
                t = float(smooth[ys[j], xs[j]])
                r = max(4.0, 0.04 * max(h, w))
                pts = [(xs[j] - r * math.cos(t), ys[j] - r * math.sin(t)), (xs[j] + r * math.cos(t), ys[j] + r * math.sin(t))]
            a, b = pts[0], pts[-1]
            # a stroke starts at its top end, or its left end when it runs nearly side to side
            steep = abs(b[1] - a[1]) > 0.35 * abs(b[0] - a[0])
            if (steep and b[1] < a[1]) or (not steep and b[0] < a[0]):
                pts = pts[::-1]
            pts = simplify(pts, 1.0)
            arrows.append([[round(min(max(px / w, 0.02), 0.98), 4), round(min(max(py / h, 0.02), 0.98), 4)]
                           for px, py in pts])
    c = float((coh * m).sum() / total)
    return {"arrows": arrows[:MAX_ARROWS], "coherence": round(c, 3)}


def simplify(pts, eps: float):
    """Douglas-Peucker, so an arrow is a few points."""
    if len(pts) < 3:
        return pts
    a, b = np.array(pts[0]), np.array(pts[-1])
    ab = b - a
    nrm = np.linalg.norm(ab) or 1.0
    d = [abs(ab[0] * (p[1] - a[1]) - ab[1] * (p[0] - a[0])) / nrm for p in pts]
    i = int(np.argmax(d))
    if d[i] > eps:
        return simplify(pts[:i + 1], eps)[:-1] + simplify(pts[i:], eps)
    return [pts[0], pts[-1]]


# ---------------------------------------------------------------------------------------------------------- drawing
def smooth_path(pts, n: int = 24):
    """A polyline smoothed into a gentle curve (Chaikin), so a bent arrow reads as a bent stroke."""
    p = [tuple(x) for x in pts]
    for _ in range(3):
        if len(p) < 3:
            break
        q = [p[0]]
        for a, b in zip(p, p[1:]):
            q += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]),
                  (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        q.append(p[-1])
        p = q
    return p


def draw_map(before, arrows: list, start: int = 0):
    """The map: the before picture, a little paler, with each arrow drawn as a bent line and a head, and a numbered
    dot at each arrow's start (1 where to start). `arrows` are in canvas fractions."""
    from PIL import Image, ImageDraw, ImageFont
    img = before.convert("RGB").copy()
    k = MAP_SIDE / max(img.size)
    img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
    w, h = img.size
    base = np.asarray(img, dtype=np.float32)
    img = Image.fromarray((base * 0.8 + 255 * 0.2).astype(np.uint8))
    dr = ImageDraw.Draw(img)
    lw = max(4, round(w / 170))
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", round(lw * 3.2))
    except OSError:
        font = ImageFont.load_default()
    for num, arr in enumerate(arrows, 1):
        pts = smooth_path([(x * w, y * h) for x, y in arr])
        if len(pts) < 2:
            continue
        for width, col in ((lw + 6, (20, 20, 20)), (lw, (255, 214, 0))):
            dr.line(pts, fill=col, width=width, joint="curve")
        (x1, y1), (x2, y2) = pts[-1], pts[max(0, len(pts) - 4)]
        t = math.atan2(y1 - y2, x1 - x2)
        L = lw * 4.5
        head = [(x1 + math.cos(t) * lw, y1 + math.sin(t) * lw),
                (x1 - L * math.cos(t - 0.5), y1 - L * math.sin(t - 0.5)),
                (x1 - L * math.cos(t + 0.5), y1 - L * math.sin(t + 0.5))]
        dr.polygon(head, fill=(255, 214, 0), outline=(20, 20, 20), width=3)
        x0, y0 = pts[0]
        r = lw * 2.6
        dr.ellipse((x0 - r, y0 - r, x0 + r, y0 + r), fill=(20, 20, 20), outline=(255, 214, 0), width=3)
        dr.text((x0, y0), str(num + start), fill=(255, 255, 255), font=font, anchor="mm")
    return img


def grid_picture(img, canvas_in, side: int = 768):
    """A picture with a light grid every inch, labelled in inches from the left and from the top, for the writer."""
    from PIL import Image, ImageDraw, ImageFont
    im = img.convert("RGB").copy()
    k = side / max(im.size)
    im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    w, h = im.size
    pad = 26
    out = Image.new("RGB", (w + pad, h + pad), "white")
    out.paste(im, (pad, pad))
    dr = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
    cw, ch = canvas_in
    for i in range(int(cw) + 1):
        x = pad + i * w / cw
        dr.line([(x, pad), (x, pad + h)], fill=(90, 90, 90) if i % 2 == 0 else (170, 170, 170), width=1)
        if i % 2 == 0:
            dr.text((x, pad / 2), str(i), fill="black", font=font, anchor="mm")
    for j in range(int(ch) + 1):
        y = pad + j * h / ch
        dr.line([(pad, y), (pad + w, y)], fill=(90, 90, 90) if j % 2 == 0 else (170, 170, 170), width=1)
        if j % 2 == 0:
            dr.text((pad / 2, y), str(j), fill="black", font=font, anchor="mm")
    return out


# ------------------------------------------------------------------------------------------------------- the state
_STATE: dict | None = None


def state() -> dict:
    global _STATE
    if _STATE is None:
        _STATE = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
        _STATE.setdefault("maps", {})
        _STATE.setdefault("calls", [])
        _STATE.setdefault("ab", [])
    return _STATE


def update(fn):
    """Change the results file under a lock, merged with what is on disk (several commands can run at once)."""
    import fcntl
    global _STATE
    with LOCK:
        WORK.mkdir(parents=True, exist_ok=True)
        with open(WORK / "results.lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            _STATE = None
            st = state()
            fn(st)
            tmp = RESULTS.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(st, indent=1) + "\n")
            tmp.replace(RESULTS)


def packet(picture: str) -> dict:
    return json.loads((WORDS / picture / "packet.json").read_text())


def map_path(variant: str, pic: str, n: int) -> Path:
    return WORK / "maps" / variant / pic / f"{n:02d}.png"


def save_map(variant: str, pic: str, n: int, rec: dict):
    before, _ = student.before_after(pic, n)
    p = map_path(variant, pic, n)
    p.parent.mkdir(parents=True, exist_ok=True)
    draw_map(before, rec["arrows"]).save(p)
    update(lambda st: st["maps"].setdefault(variant, {}).setdefault(pic, {}).__setitem__(str(n), rec))


# ------------------------------------------------------------------------------------------------- the map's writer
WRITER_SYSTEM = (
    "You draw a stroke map for one step of a beginner's acrylic painting lesson. You have no tools. A program draws "
    "your arrows on the canvas exactly where you put them, so place every point with care.")

WRITER_BRIEF = """A stroke map is the canvas before the step with a few arrows on it, so a beginner can see where the
first strokes go and which way they run before they start. Each arrow is one stroke's path, or the path a row of
strokes follows: a numbered dot where it starts and an arrowhead where it ends. Arrow 1 is where the painter starts.

You get the step as the lesson gives it (its words, paints and brush), and three pictures of the canvas, each with a
grid in inches (numbers every 2 in, from the left edge and from the top edge; lines every inch):

- the canvas before the step (the map is drawn on this one);
- the canvas after the step;
- only what the step changed (the rest washed pale).

Draw 1 to 4 arrows:

- Put each arrow on paint this step lays down, inside the changed area, never on paint that was already there.
- Run each arrow the way the strokes in the after picture run there, and bend it where they bend (give it more
  points). Point it the way the brush moves.
- Arrow 1 starts where the step's words say to start; if they don't say, where a painter would begin this step.
- Cover the step's main areas: a big area may get two or three arrows, a small detail one short arrow.
- Show this step only: nothing the step doesn't paint, and nothing from later steps.
- An arrow is about as long as the strokes or the row of strokes it stands for, never longer than the area it's in.

{extra}Give every point in inches, [x from the left edge, y from the top edge], inside the {w:g} x {h:g} in canvas.
Reply with one ```json block:

{{"arrows": [{{"points": [[x, y], [x, y], ...], "says": "what this arrow shows, a few words"}}, ...],
  "disagrees": "" or one sentence: where the step's words and its after picture disagree about the strokes' direction}}
"""

BOTH_EXTRA = """A program has also drawn arrows from the grain of the paint the step laid down (a fourth picture, with
their points below). It reads the after picture only, not the words, and it guesses where to start (the biggest
area's top end). Keep its arrows where they are right, move or bend them where they aren't, drop the ones on the
wrong thing and add any it missed. Where the words and the after picture disagree about which way the strokes run,
follow the after picture, since that is what the painter has to reach, and say so in `disagrees`.

The program's arrows, in inches:
{arrows}

"""


def to_inches(arrows: list, canvas_in) -> list:
    return [[[round(x * canvas_in[0], 2), round(y * canvas_in[1], 2)] for x, y in a] for a in arrows]


def from_inches(arrows: list, canvas_in) -> list:
    out = []
    for a in arrows:
        pts = [[min(max(float(x) / canvas_in[0], 0.0), 1.0), min(max(float(y) / canvas_in[1], 0.0), 1.0)]
               for x, y in (a.get("points") or [])]
        if len(pts) >= 2:
            out.append([[round(x, 4), round(y, 4)] for x, y in pts])
    return out[:MAX_ARROWS]


def write_one(variant: str, pic: str, n: int):
    from v4_loop import Message, call_claude, cost, last_json
    les = packet(pic)
    s = next(x for x in les["steps"] if x["n"] == n)
    canvas = les["canvas_in"]
    before, after = student.before_after(pic, n)
    d = WORK / "writer" / pic
    d.mkdir(parents=True, exist_ok=True)
    import v4_teacher as teacher
    files = {"before": grid_picture(before, canvas), "after": grid_picture(after, canvas),
             "change": grid_picture(teacher.change_picture(before, after), canvas)}
    extra = ""
    if variant == "both":
        ch = state()["maps"]["change"][pic][str(n)]
        files["program"] = grid_picture(draw_map(before, ch["arrows"]), canvas)
        extra = BOTH_EXTRA.format(arrows=json.dumps(to_inches(ch["arrows"], canvas)))
    m = Message().text(WRITER_BRIEF.format(extra=extra, w=canvas[0], h=canvas[1]))
    m.text("The step:\n\n" + student.step_text(s, canvas, len(les["steps"])))
    for k, im in files.items():
        p = d / f"{n:02d}-{k}.jpg"
        im.save(p, quality=88)
        m.picture(p, {"before": "before.jpg", "after": "after.jpg", "change": "change.jpg",
                      "program": "program-arrows.jpg"}[k])
    m.text("Now the stroke map's arrows, as one ```json block.")
    cwd = WORK / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    r = call_claude(m.blocks, WRITER_SYSTEM, cwd=cwd)
    c = round(cost(r["usage"]), 5)
    call = {"label": f"map-writer {variant} {pic} {n}", "seconds": r["seconds"], "cost_usd": c,
            "input_tokens": r["usage"].get("input_tokens", 0),
            "cache_write_tokens": r["usage"].get("cache_creation_input_tokens", 0),
            "cache_read_tokens": r["usage"].get("cache_read_input_tokens", 0),
            "output_tokens": r["usage"].get("output_tokens", 0)}
    update(lambda st: st["calls"].append(call))
    try:
        a = last_json(r["text"]) or {}
    except ValueError:
        a = {}
    rec = {"arrows": from_inches(a.get("arrows") or [], canvas), "says": [x.get("says", "") for x in a.get("arrows") or []],
           "disagrees": a.get("disagrees") or "", "cost_usd": c, "seconds": r["seconds"]}
    save_map(variant, pic, n, rec)
    print(f"{variant} {pic} {n:2d}: {len(rec['arrows'])} arrows, ${c:.3f}" + (f"  disagrees: {rec['disagrees']}" if rec["disagrees"] else ""))


def steps_of(args) -> list[tuple[str, int]]:
    out = []
    for pic in ([args.picture] if getattr(args, "picture", None) else PICTURES):
        ns = [s["n"] for s in packet(pic)["steps"]]
        if getattr(args, "steps", None):
            want = {int(x) for x in args.steps.split(",")}
            ns = [n for n in ns if n in want]
        out += [(pic, n) for n in ns]
    return out


def pool(fn, jobs, workers: int):
    with ThreadPoolExecutor(workers) as ex:
        for f in [ex.submit(fn, *j) for j in jobs]:
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                print(f"  failed: {e}", file=sys.stderr)


def maps(args):
    """Make the maps: `change` from the change alone (no Claude), `writer` and `both` by the writer's call."""
    variants = [args.variant] if args.variant else VARIANTS
    for v in variants:
        jobs = steps_of(args)
        if not args.again:
            have = state()["maps"].get(v, {})
            jobs = [(p, n) for p, n in jobs if str(n) not in have.get(p, {})]
        if v == "change":
            for pic, n in jobs:
                before, after = student.before_after(pic, n)
                save_map(v, pic, n, change_arrows(before, after))
            print(f"change: {len(jobs)} maps")
        else:
            print(f"{v}: {len(jobs)} writers")
            pool(lambda p, n, v=v: write_one(v, p, n), jobs, args.workers)


def sheet(args):
    """Every step of a lesson: the map beside the after picture, for looking at (and the write-up)."""
    from PIL import Image
    rows = []
    for pic, n in steps_of(args):
        before, after = student.before_after(pic, n)
        ims = [load_map(v, pic, n) or before for v in args.variant.split(",")] + [after]
        side = 420
        ims = [im.resize((side, round(side * im.height / im.width))) for im in ims]
        row = Image.new("RGB", (sum(i.width for i in ims) + 8 * (len(ims) - 1), ims[0].height), "white")
        x = 0
        for im in ims:
            row.paste(im, (x, 0))
            x += im.width + 8
        rows.append(row)
    out = Image.new("RGB", (rows[0].width, sum(r.height for r in rows) + 8 * (len(rows) - 1)), "white")
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height + 8
    out.save(args.out, quality=85)
    print(args.out)


def load_map(variant: str, pic: str, n: int):
    p = map_path(variant, pic, n)
    return student.load(p) if p.exists() else None


# ------------------------------------------------------------------------------------------------------ the student
MAP_NOTE = (
    "\n\nThe second picture is this step's stroke map: the same canvas, a little paler, with yellow arrows drawn on "
    "it. Each arrow shows which way the strokes run there, and a numbered dot where they start (1 first). Paint on "
    "the first picture, the canvas itself. The map is only a guide: never paint the arrows, the dots or the numbers, "
    "and keep the canvas's own colours, not the map's paler ones.")


def use_student(variant: str):
    """Point the student test at the adopted words and this variant's own results file and carry folder."""
    student.WORK = TMP / "gesso-v4-student"
    student.WORDS_FROM = WORDS
    student.RESULTS = (STUDENT_DIR / f"map-{variant}.json").resolve()
    student._STATE = None
    STUDENT_DIR.mkdir(exist_ok=True)


def carry_one(variant: str, pic: str, n: int):
    from run import Ledger, edit_image
    les = student.lesson(pic)
    s = student.step_of(pic, n)
    before, after = student.before_after(pic, n)
    d = student.carry_dir() / pic
    d.mkdir(parents=True, exist_ok=True)
    src = d / f"{n:02d}-before.png"
    before.save(src)
    mp = map_path(variant, pic, n)
    out = d / f"{n:02d}-words-r1.png"
    w, h = les["canvas_in"]
    size = "1536x1024" if w > h else "1024x1536" if h > w else "1024x1024"
    with LOCK:
        spent = sum(r["render_usd"] for r in student.state()["carry"])
    if spent > student.BUDGET:
        raise RuntimeError(f"render spend ${spent:.2f} is past ${student.BUDGET:.2f}: ask the owner first")
    ledger = Ledger()
    t0 = time.time()
    prompt = student.carry_prompt(s, les["canvas_in"], len(les["steps"]), None, False) + MAP_NOTE
    edit_image(f"{pic}-{n}-map-{variant}", [src, mp], prompt, out, size, student.RENDER_QUALITY, ledger)
    pd = student.WORK / "pick" / pic / f"{n:02d}"
    order = student.state()["prepared"][pic][str(n)]["order"]
    cands = {k: student.load(pd / f"{i}.jpg") for i, k in enumerate(order, 1)}
    real = cands.pop("real")
    res = student.load(out)
    mm = student.measure(before, real, res, cands)
    g = grain(before, after, res)
    student.add("carry", {"picture": pic, "n": n, "condition": "words", "rep": 1, "file": out.name, **mm,
                          "grain": g["agree"], "map": variant, "render_usd": ledger.total_cost,
                          "seconds": round(time.time() - t0, 1)})
    print(f"carry map-{variant} {pic} {n:2d}: beats {mm['beats']:.2f}, grain {g['agree']}, ${ledger.total_cost:.3f}")


def carry(args):
    use_student(args.variant)
    student.BUDGET = args.budget
    done = {(r["picture"], r["n"]) for r in student.state()["carry"]}
    jobs = [(args.variant, p, n) for p, n in steps_of(args) if (p, n) not in done]
    spent = sum(r["render_usd"] for r in student.state()["carry"])
    print(f"{len(jobs)} renders; ${spent:.2f} spent so far on map-{args.variant}")
    pool(carry_one, jobs, args.workers)


def grade(args):
    """carry's grader, each result alone (`v4_student.py grade-carry --solo words`), on this variant's results."""
    use_student(args.variant)
    student.grade_carry(argparse.Namespace(solo="words", picture=args.picture, workers=args.workers))


# ------------------------------------------------------------------------------------------------- the blind graders
def ab_one(variant: str, pic: str, g: int):
    """One blind grader (`bench/ab_grader.md`): the adopted words with this variant's maps against the same words
    without, the sides set by `g`. The words are the same on both sides; only the maps differ."""
    from v4_loop import Message, call_claude, cost, last_json
    les = packet(pic)
    sides = ["map", "none"] if (g + random.Random(f"{variant}-{pic}-{SEED}").randrange(2)) % 2 else ["none", "map"]
    brief_text = (HERE / "bench" / "ab_grader.md").read_text().replace(
        "You were given a folder.", "You were given everything in this message, in place of a folder.")
    m = Message().text(f'<file name="ab_grader.md">\n{brief_text}\n</file>')
    m.text("The two lessons, A and B, have the same photo, finish, step pictures and words. One of them also gives "
           "some steps a stroke map: the canvas before the step with yellow arrows on it, showing where the strokes "
           "start (numbered dots, 1 first) and which way they run. Each step's picture is shown once, with its words "
           "and each lesson's map, if it has one, below.")
    m.picture(BENCH / pic / "photo.jpg", "photo.jpg", max_side=1024)
    m.picture(BENCH / pic / "finish.jpg", "finish.jpg", max_side=1024)
    m.text(f"The lessons' opening (the same in both):\n{les.get('opening', '')}")
    for s in les["steps"]:
        m.text(f"Step {s['n']}. Its picture (the canvas after the step):")
        m.picture(BENCH / pic / "steps" / f"{s['n']:02d}.jpg", f"steps/{s['n']:02d}.jpg", max_side=640)
        m.text("The words (the same in A and B):\n" + student.step_text(s, les["canvas_in"], len(les["steps"])))
        for side, who in zip("AB", sides):
            if who == "map" and map_path(variant, pic, s["n"]).exists():
                m.text(f"Lesson {side}'s stroke map for step {s['n']}:")
                m.picture(map_path(variant, pic, s["n"]), f"{side}-map-{s['n']:02d}.jpg", max_side=640)
            else:
                m.text(f"Lesson {side}: no stroke map.")
    m.text('Reply with grade.json as one ```json block (the brief\'s shape, `"picture": "' + pic + '"`), then the '
           "scores, the preference and how sure you are. Say in `note` whether the maps helped, misled or made no "
           "difference, and name any step whose map points the wrong way or sits on the wrong thing.")
    cwd = WORK / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    r = call_claude(m.blocks, "You have no tools. You grade one blind A/B pair, in the owner's place.", cwd=cwd)
    try:
        a = last_json(r["text"])
    except ValueError:
        a = {}
    a = a if isinstance(a, dict) else {}
    prefer = a.get("prefer")
    out = {"variant": variant, "picture": pic, "grader": g, "A": sides[0], "B": sides[1], "prefer": prefer,
           "preferred": sides["AB".index(prefer)] if prefer in ("A", "B") else "none",
           "scores": {sides["AB".index(k)]: v for k, v in (a.get("scores") or {}).items() if k in ("A", "B")},
           "worst_steps": a.get("worst_steps"), "note": a.get("note", ""), "text": r["text"][-3000:],
           "cost_usd": round(cost(r["usage"]), 5), "seconds": r["seconds"]}
    update(lambda st: st["ab"].append(out))
    print(f"ab {variant} {pic} g{g}: prefers {out['preferred']} ({prefer}), ${out['cost_usd']:.3f}")


def ab(args):
    done = {(r["variant"], r["picture"], r["grader"]) for r in state()["ab"]}
    jobs = [(args.variant, p, g) for p in PICTURES for g in (1, 2) if (args.variant, p, g) not in done]
    pool(ab_one, jobs, args.workers)


# ------------------------------------------------------------------------------------------------------------ report
def solo(path: Path) -> dict:
    ss = json.loads(path.read_text()) if path.exists() else {}
    return {(r["picture"], r["n"]): r["grade"] for r in ss.get("carry_grades", []) if r.get("solo")
            and r["condition"] == "words"}


def base_grain() -> dict:
    """The grain measure on the baseline's own results (arc-add-long, no map), worked out once and kept."""
    st = state()
    if "base_grain" not in st:
        out = {}
        for r in json.loads(BASE_STUDENT.read_text())["carry"]:
            if r["condition"] != "words":
                continue
            before, after = student.before_after(r["picture"], r["n"])
            res = student.load(TMP / "gesso-v4-student" / f"carry-{BASE}" / r["picture"] / r["file"])
            out[f"{r['picture']} {r['n']}"] = grain(before, after, res)["agree"]
        update(lambda s: s.__setitem__("base_grain", out))
    return state()["base_grain"]


def paired(a: dict, b: dict) -> dict:
    ks = sorted(set(a) & set(b))
    if not ks:
        return {}
    d = np.array([b[k] - a[k] for k in ks], dtype=float)
    return {"n": len(ks), "mean_diff": round(float(d.mean()), 3),
            "se": round(float(d.std(ddof=1) / math.sqrt(len(d))), 3) if len(d) > 1 else None,
            "rose": int((d > 0).sum()), "fell": int((d < 0).sum())}


def report(args) -> dict:
    base = solo(BASE_STUDENT)
    bg = {tuple([k.rsplit(" ", 1)[0], int(k.rsplit(" ", 1)[1])]): v for k, v in base_grain().items() if v is not None}
    out = {"baseline": {p: round(float(np.mean([g for (pp, _), g in base.items() if pp == p])), 2) for p in PICTURES},
           "baseline_grain": round(float(np.mean(list(bg.values()))), 3), "variants": {}}
    for v in VARIANTS:
        path = STUDENT_DIR / f"map-{v}.json"
        if not path.exists():
            continue
        ss = json.loads(path.read_text())
        gr = solo(path)
        vg = {(r["picture"], r["n"]): r["grain"] for r in ss["carry"] if r.get("grain") is not None}
        rec = {"grade": {p: round(float(np.mean([g for (pp, _), g in gr.items() if pp == p])), 2)
                         for p in PICTURES if any(pp == p for pp, _ in gr)},
               "against_baseline": paired(base, gr), "grain_against_baseline": paired(bg, vg),
               "grain": round(float(np.mean([vg[k] for k in vg if k in bg])), 3) if vg else None,  # on the baseline's steps
               "renders_usd": round(sum(r["render_usd"] for r in ss["carry"]), 3),
               "grader_usd": round(sum(r["cost_usd"] for r in ss.get("carry_grades", [])), 3)}
        for p in PICTURES:
            rec[f"against_baseline {p}"] = paired({k: x for k, x in base.items() if k[0] == p},
                                                  {k: x for k, x in gr.items() if k[0] == p})
        maps_ = state()["maps"].get(v, {})
        rec["map_usd_a_lesson"] = round(sum(m.get("cost_usd", 0) for pm in maps_.values() for m in pm.values()) / 3, 3)
        rec["disagrees"] = {f"{p} {n}": m["disagrees"] for p, pm in maps_.items() for n, m in pm.items()
                            if m.get("disagrees")}
        ab_ = [r for r in state()["ab"] if r["variant"] == v]
        rec["ab"] = {p: [("map" if r["preferred"] == "map" else "no map") if r["prefer"] in ("A", "B") else "no difference"
                     for r in ab_ if r["picture"] == p] for p in PICTURES}
        out["variants"][v] = rec
    update(lambda st: st.__setitem__("report", out))
    print(json.dumps(out, indent=1))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    mp = sub.add_parser("maps")
    mp.add_argument("--variant", choices=VARIANTS)
    mp.add_argument("--again", action="store_true", help="make maps that already exist again")
    sh = sub.add_parser("sheet")
    sh.add_argument("--variant", default="change", help="one or more, comma-separated")
    sh.add_argument("--out", required=True)
    for p in (mp, sh):
        p.add_argument("--picture", choices=PICTURES)
        p.add_argument("--steps", help="comma-separated step numbers")
        p.add_argument("--workers", type=int, default=6)
    ca = sub.add_parser("carry")
    ca.add_argument("--variant", choices=VARIANTS, required=True)
    ca.add_argument("--picture", choices=PICTURES)
    ca.add_argument("--steps")
    ca.add_argument("--budget", type=float, default=2.0, help="stop before rendering past this spend on the variant")
    ca.add_argument("--workers", type=int, default=6)
    gr = sub.add_parser("grade")
    gr.add_argument("--variant", choices=VARIANTS, required=True)
    gr.add_argument("--picture", choices=PICTURES)
    gr.add_argument("--workers", type=int, default=6)
    a = sub.add_parser("ab")
    a.add_argument("--variant", choices=VARIANTS, required=True)
    a.add_argument("--workers", type=int, default=6)
    sub.add_parser("report")
    args = ap.parse_args(argv)
    {"maps": maps, "sheet": sheet, "carry": carry, "grade": grade, "ab": ab, "report": report}[args.cmd](args)


if __name__ == "__main__":
    main()
