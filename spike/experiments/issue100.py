"""Spike for #100: the cheapest way to a clean outline for a thin, soft-edged part (the chickadee's branch).

Not part of the pipeline. Four ways to get the branch block-in of `chickadee_skill_20261113-130614` clean, on the
pictures its published lesson page holds (site/lessons/chickadee/v/20261113-130614/), then the fixtures' mast and
tree:

    python spike/experiments/issue100.py free     # no cost: cleanups and today's tool -> output/spike100/
    python spike/experiments/issue100.py paid     # about $0.15: image-model mask edits and step re-renders
    python spike/experiments/issue100.py sheets   # the pictures and numbers docs/spikes/thin-outlines.md shows

That run's plan and full-size finish weren't kept (output/ is local), so the branch's paths and points below were
written for this spike, by eye from the finish, the way a plan would give them. The published branch outline is
read back from the page's own step 4 and step 5 pictures: the flat brown step 5 added.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "spike"))
import outline as ol  # noqa: E402

OUT = ROOT / "output" / "spike100"
DOCS = ROOT / "docs" / "spikes"
PAGE = ROOT / "site/lessons/chickadee/v/20261113-130614/index.html"
W, H = 900, 707  # the page's step pictures


def px(points):  # pixels on the page's pictures -> 0-1
    return [[round(x / W, 4), round(y / H, 4)] for x, y in points]


BRANCH = {  # written for this spike from the 130614 finish (see the docstring)
    "id": "branch", "kind": "thin", "width": 0.07,
    "paths": [px(p) for p in [
        [(25, 5), (15, 100), (25, 180), (45, 260), (62, 330), (82, 400), (95, 450), (70, 520), (30, 600), (5, 695)],
        [(40, 580), (110, 500), (200, 465), (300, 437), (400, 420), (500, 425), (580, 445), (650, 480), (720, 520),
         (770, 560), (810, 600), (850, 640), (898, 675)],
        [(740, 518), (800, 502), (850, 487), (898, 466)],
        [(790, 577), (850, 593), (898, 600)],
        [(40, 62), (80, 32), (140, 4)],
        [(76, 36), (88, 65), (100, 96)],
        [(597, 468), (578, 490), (560, 505)],
        [(592, 472), (598, 520), (608, 556)]]],
    "points_in": px([(300, 442), (450, 422), (55, 300), (30, 620), (680, 495), (130, 498), (22, 120), (760, 550)]),
    "points_out": px([(250, 350), (300, 560), (700, 400), (600, 620), (820, 545), (130, 250), (450, 560)]),
}

# ---------------------------------------------------------------------------------------------------------------
# The cases
# ---------------------------------------------------------------------------------------------------------------


def page_pictures() -> dict[str, np.ndarray]:
    """Step 4, step 5 and the last step (the finish, canvas view) from the published lesson page, RGB."""
    html = PAGE.read_text()
    out = {}
    for name, n in (("step4", 4), ("step5", 5), ("finish", 19)):
        m = re.search(rf'<image id="pic-{n}"[^>]*href="data:image/jpeg;base64,([A-Za-z0-9+/=]+)"', html)
        out[name] = np.array(Image.open(io.BytesIO(base64.b64decode(m.group(1)))).convert("RGB"))
    return out


def published_branch(step4: np.ndarray, step5: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The branch outline the run used: where step 5 laid its flat brown. Returns it and the brown."""
    d = np.abs(step5.astype(int) - step4.astype(int)).sum(2)
    brown = np.median(step5[d > 120], axis=0)
    m = (d > 45) & (np.abs(step5.astype(int) - brown).sum(2) < 40)
    return cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0, brown


def fixture(name: str, part_id: str):
    finish = np.array(Image.open(ROOT / f"spike/tests/fixtures/finishes/{name}.jpg").convert("RGB"))
    plan = json.loads((ROOT / f"spike/tests/fixtures/plans/{name}.json").read_text())
    return finish, plan, next(p for p in plan["parts"] if p["id"] == part_id)


def color_rule(finish: np.ndarray, part: dict) -> np.ndarray:
    """A thin part the way it was found before #129: by color alone, inside its band."""
    L = ol.lab(cv2.GaussianBlur(finish, (0, 0), 1.2))
    return ol.keep_pieces(ol.marks(L, part, ol.band(finish.shape[:2], part)))


def todays_tool(sam: ol.Sam, finish: np.ndarray, part: dict) -> np.ndarray:
    sam.embed(finish)
    L = ol.lab(cv2.GaussianBlur(finish, (0, 0), 1.2))
    return thin_now(sam, L, part, finish.shape[:2])


def thin_now(sam, L, part, shape):
    return ol.thin(sam, L, part, ol.band(shape, part))[0]


# ---------------------------------------------------------------------------------------------------------------
# Option 1: free cleanup of an outline
# ---------------------------------------------------------------------------------------------------------------

GAP = 0.004  # gaps narrower than about twice this share of the long side are closed
TWIG = 3.5  # a thin piece at least this many times longer than wide is a twig, and stays
SIDE = 1.25  # a path-led cleanup keeps this many times the part's usual half-width on each side of its path
STEP = 4  # pixels between the cross-sections measured along a path


def disc(r: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def main_body(mask: np.ndarray) -> np.ndarray:
    """Small gaps closed, then only the pieces joined to the biggest one."""
    r = max(1, int(GAP * max(mask.shape)))
    closed = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, disc(r))
    n, lab_, st, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    if n < 2:
        return mask
    return (lab_ == 1 + int(st[1:, cv2.CC_STAT_AREA].argmax())) & (closed > 0)


def by_shape(mask: np.ndarray) -> np.ndarray:
    """Cleanup with no plan (option 1, first way). Keep the main body; open away what's thinner than half the
    part's usual thickness, then give back the pieces that are long and thin (twigs); smooth the edge."""
    body = main_body(mask).astype(np.uint8)
    dist = cv2.distanceTransform(body, cv2.DIST_L2, 5)
    ridge = dist[(dist > 0) & (dist >= cv2.dilate(dist, np.ones((3, 3), np.uint8)) - 1e-6)]  # the middle line
    r = max(2, int(np.median(ridge) * 0.5))
    thick = cv2.morphologyEx(body, cv2.MORPH_OPEN, disc(r))
    rest = body & ~thick
    n, lab_, st, _ = cv2.connectedComponentsWithStats(rest, connectivity=8)
    keep = thick.copy()
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] < 30:
            continue
        pts = np.argwhere(lab_ == i)[:, ::-1].astype(np.float32)
        (_, _), (a, b), _ = cv2.minAreaRect(pts)
        long_, short = max(a, b), max(min(a, b), 1.0)
        if long_ / short >= TWIG and st[i, cv2.CC_STAT_AREA] / (long_ * short) > 0.35:
            keep[lab_ == i] = 1
    keep = main_body(keep > 0).astype(np.uint8)
    return cv2.medianBlur(keep * 255, 7) > 127


def along_paths(mask: np.ndarray, part: dict) -> np.ndarray:
    """Cleanup led by the plan's paths (option 1, second way). Along each path, measure how far the outline reaches
    on each side; the part's real edge is the usual reach near there (a running low-middle value), so a lump is a
    stretch that reaches further and is cut back to SIDE times the usual. Twigs are safe: each has its own path."""
    h, w = mask.shape
    body = main_body(mask)
    keep = np.zeros((h, w), np.uint8)
    most = part.get("width", 0.05) * w * ol.BAND
    for path in part["paths"]:
        p = np.array([[x * w, y * h] for x, y in path], np.float32)
        seg = np.sqrt((np.diff(p, axis=0) ** 2).sum(1))
        n = max(2, int(seg.sum() / STEP))
        d = np.linspace(0, seg.sum(), n)
        ends = np.cumsum(seg)
        i = np.minimum(np.searchsorted(ends, d), len(seg) - 1)
        t = ((d - (ends[i] - seg[i])) / np.maximum(seg[i], 1e-6))[:, None]
        c = p[i] + (p[i + 1] - p[i]) * np.clip(t, 0, 1)
        tan = cv2.GaussianBlur((p[i + 1] - p[i]) / np.maximum(seg[i], 1e-6)[:, None], (1, 0), 6)
        tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-6)
        nor = np.stack([-tan[:, 1], tan[:, 0]], 1)
        reach = np.zeros((n, 2), np.float32)
        for side, sign in enumerate((1, -1)):
            for k in range(n):
                # the outline's far edge on this side, allowing the path itself to sit a little off the part
                last, miss = 0.0, 0
                for s in np.arange(0, most, 1.0):
                    x, y = c[k] + sign * s * nor[k]
                    inside = 0 <= int(y) < h and 0 <= int(x) < w and body[int(y), int(x)]
                    if inside:
                        last, miss = s, 0
                    else:
                        miss += 1
                        if miss > 4 and last > 0:
                            break
                reach[k, side] = last
        win = max(5, int(0.12 * w / STEP)) | 1  # the "usual" reach is taken over about an eighth of the width
        pad = np.pad(reach, ((win // 2, win // 2), (0, 0)), mode="edge")
        usual = np.stack([np.percentile(pad[k:k + win], 40, axis=0) for k in range(n)])
        allow = np.minimum(reach, usual * SIDE + 2)
        allow = cv2.GaussianBlur(allow, (1, 0), 2)
        left, right = c + allow[:, :1] * nor, c - allow[:, 1:] * nor
        for k in range(n - 1):
            quad = np.array([left[k], left[k + 1], right[k + 1], right[k]], np.int32)
            cv2.fillConvexPoly(keep, quad, 1)
    keep = (keep > 0) & body
    return cv2.medianBlur(main_body(keep).astype(np.uint8) * 255, 5) > 127


# ---------------------------------------------------------------------------------------------------------------
# Measures, and step 5 rebuilt
# ---------------------------------------------------------------------------------------------------------------


def pieces(mask: np.ndarray) -> int:
    return cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)[0] - 1


def against(mask: np.ndarray, ref: np.ndarray) -> dict:
    """Against the reference outline: what's stuck on (not the part) and what's lost (the part, missing), each as
    a share of the reference's size, and the pieces."""
    return {"stuck": round(float((mask & ~ref).sum() / ref.sum()), 3),
            "lost": round(float((ref & ~mask).sum() / ref.sum()), 3),
            "pieces": pieces(mask)}


def block_in(before: np.ndarray, mask: np.ndarray, paint: np.ndarray) -> np.ndarray:
    out = before.copy()
    out[mask] = paint
    return out


def save_mask(mask: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask.astype(np.uint8) * 255).save(path)


def load_mask(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("L")) > 127


def free(_a) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sam = ol.Sam()
    times = {}
    pics = page_pictures()
    for k, v in pics.items():
        Image.fromarray(v).save(OUT / f"chickadee-{k}.png")
    published, brown = published_branch(pics["step4"], pics["step5"])
    (OUT / "brown.json").write_text(json.dumps([int(v) for v in brown]))
    cases = {"chickadee": (pics["finish"], BRANCH, published)}
    for name, fx, pid in (("mast", "red-sailboat", "mast"), ("trunk", "lavender-balloon", "trunk")):
        finish, plan, part = fixture(fx, pid)
        if part["kind"] == "thin":
            cases[name] = (finish, part, color_rule(finish, part))
        else:  # the lavender's trunk is marks on the tree (an object): as the pipeline outlines it today
            owner = np.array(Image.open(ROOT / f"spike/tests/fixtures/owners/{fx}.png"))
            index = [p["id"] for p in plan["parts"]]
            tree = (owner == index.index("tree")) | (owner == index.index(pid))
            save_mask(tree, OUT / "tree-today.png")
            Image.fromarray(finish).save(OUT / "tree-finish.png")
            save_mask(by_shape(tree), OUT / "tree-by-shape.png")
            continue
    for name, (finish, part, rough) in cases.items():
        Image.fromarray(finish).save(OUT / f"{name}-finish.png")
        save_mask(rough, OUT / f"{name}-color-rule.png")
        for label, fn in (("by-shape", lambda m: by_shape(m)), ("along-paths", lambda m: along_paths(m, part))):
            t = time.time()
            save_mask(fn(rough), OUT / f"{name}-{label}.png")
            times[f"{name} {label}"] = round(time.time() - t, 2)
        t = time.time()
        tool = todays_tool(sam, finish, part)
        times[f"{name} tool"] = round(time.time() - t, 2)
        save_mask(tool, OUT / f"{name}-tool.png")
        save_mask(along_paths(tool, part), OUT / f"{name}-tool-along-paths.png")
    (OUT / "times.json").write_text(json.dumps(times, indent=1))
    print(json.dumps(times, indent=1))


# ---------------------------------------------------------------------------------------------------------------
# Options 3 and 4: the image model
# ---------------------------------------------------------------------------------------------------------------

MASK_PROMPT = (
    "The first image is a painting{bars}. The second image is a rough black-and-white mask of the {thing} in it: "
    "white where the {thing} is, black elsewhere. The rough mask is wrong in places: {wrong}. "
    "Make the corrected mask: pure white exactly on the {thing} ({what}), pure black everywhere else. "
    "Keep the exact position, size and framing of the first image so the mask lines up with it pixel for pixel. "
    "Flat white and flat black only: no gray, no texture, no outlines, no other objects.")
STEP_PROMPT = (
    "The first image is one step of a painting lesson{bars}: the misty background is painted, and the tree branch "
    "has just been blocked in as one flat dark brown shape. The block-in is wrong: ragged brown blobs and loose "
    "brown specks are stuck around the branch that aren't branch. The second image is the finished painting. "
    "Repaint the first image so the flat dark brown covers exactly the trunk, branch and twigs of the second image "
    "and nothing else, with the misty background showing where the blobs were. Keep the brown flat, with no bark "
    "texture or highlights. Don't add the bird or the leaves. Change nothing else: same background, same "
    "position, size and framing.")
BARS = ", with a gray bar down each side that isn't part of it (keep the bars)"


def to_api(img: np.ndarray, path: Path) -> tuple[Path, tuple[int, int, int, int]]:
    """Fit a picture onto the image model's 1536 x 1024 with gray bars, and say where it sits."""
    h, w = img.shape[:2]
    s = min(1536 / w, 1024 / h)
    nw, nh = int(round(w * s)), int(round(h * s))
    x0, y0 = (1536 - nw) // 2, (1024 - nh) // 2
    page = np.full((1024, 1536, 3), 128, np.uint8)
    page[y0:y0 + nh, x0:x0 + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_CUBIC)
    Image.fromarray(page).save(path)
    return path, (x0, y0, nw, nh)


def from_api(path: Path, where: tuple[int, int, int, int], shape: tuple[int, int]) -> np.ndarray:
    x0, y0, nw, nh = where
    img = np.array(Image.open(path).convert("RGB").resize((1536, 1024)))
    return cv2.resize(img[y0:y0 + nh, x0:x0 + nw], (shape[1], shape[0]), interpolation=cv2.INTER_AREA)


def paid(a) -> None:
    import run

    led_path = OUT / "ledger.json"
    done = json.loads(led_path.read_text()) if led_path.exists() else {}
    client = run.openai_client()

    def call(key: str, inputs: list[Path], prompt: str) -> Path:
        out = OUT / f"{key}.api.png"
        if key in done and out.exists() and not a.fresh:
            return out
        led = run.Ledger()
        run.edit_image(key, inputs, prompt, out, "1536x1024", "low", led, client=client)
        done[key] = led.calls[-1]
        led_path.write_text(json.dumps(done, indent=1))
        return out

    jobs = [("chickadee", "tree branch", "the trunk at the left, the long curved branch, and its thin twigs and leaf "
             "stems", "blobs and specks of misty background are stuck to the branch", 2),
            ("mast", "sailboat's mast", "one thin straight pole", "its edge is ragged and lumpy", 1)]
    for name, thing, what, wrong, runs in jobs:
        finish = np.array(Image.open(OUT / f"{name}-finish.png"))
        rough = load_mask(OUT / f"{name}-color-rule.png")
        f, where = to_api(finish, OUT / f"{name}-finish.in.png")
        r, _ = to_api(np.repeat(rough[..., None].astype(np.uint8) * 255, 3, 2), OUT / f"{name}-rough.in.png")
        # the bars of the mask picture are gray too, so the model can see where the picture ends
        for i in range(1, runs + 1):
            got = call(f"{name}-mask-edit-{i}", [f, r], MASK_PROMPT.format(bars=BARS, thing=thing, what=what, wrong=wrong))
            back = from_api(got, where, finish.shape[:2])
            Image.fromarray(back).save(OUT / f"{name}-mask-edit-{i}.raw.png")
            save_mask(ol.keep_pieces(back.mean(2) > 127), OUT / f"{name}-mask-edit-{i}.png")
    step5 = np.array(Image.open(OUT / "chickadee-step5.png"))
    finish = np.array(Image.open(OUT / "chickadee-finish.png"))
    s, where = to_api(step5, OUT / "chickadee-step5.in.png")
    f, _ = to_api(finish, OUT / "chickadee-finish.in.png")
    for i in (1, 2):
        got = call(f"chickadee-rerender-{i}", [s, f], STEP_PROMPT.format(bars=BARS))
        Image.fromarray(from_api(got, where, step5.shape[:2])).save(OUT / f"chickadee-rerender-{i}.png")
    print(json.dumps({k: (v["seconds"], v["cost_usd"]) for k, v in done.items()}, indent=1))


# ---------------------------------------------------------------------------------------------------------------
# The sheets and the numbers
# ---------------------------------------------------------------------------------------------------------------


def label(img: np.ndarray, text: str) -> np.ndarray:
    out = np.ascontiguousarray(img.copy())
    s = max(0.8, img.shape[1] / 900)
    cv2.rectangle(out, (0, 0), (img.shape[1], int(44 * s)), (255, 255, 255), -1)
    cv2.putText(out, text, (int(10 * s), int(31 * s)), cv2.FONT_HERSHEY_SIMPLEX, 0.85 * s, (20, 20, 20),
                max(1, int(2 * s)), cv2.LINE_AA)
    return out


def grid(tiles: list[np.ndarray], per_row: int, gap: int = 8) -> np.ndarray:
    h, w = tiles[0].shape[:2]
    rows = -(-len(tiles) // per_row)
    page = np.full((rows * h + (rows - 1) * gap, per_row * w + (per_row - 1) * gap, 3), 255, np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, per_row)
        page[r * (h + gap):r * (h + gap) + h, c * (w + gap):c * (w + gap) + w] = t
    return page


def brown_of(img: np.ndarray, brown: np.ndarray) -> np.ndarray:
    """Where a re-rendered step is block-in brown (the model's brown isn't exactly the step's)."""
    L, b = ol.lab(img), ol.lab(np.array([[brown]], np.uint8))[0, 0]
    return ol.keep_pieces(np.sqrt(((L - b) ** 2).sum(2)) < 18)


def shift(a: np.ndarray, b: np.ndarray, where: np.ndarray) -> float:
    """How far (pixels) picture b's background sits from picture a's."""
    ga, gb = (cv2.cvtColor(x, cv2.COLOR_RGB2GRAY).astype(np.float32) * where for x in (a, b))
    (dx, dy), _ = cv2.phaseCorrelate(ga, gb)
    return round(float(np.hypot(dx, dy)), 2)


def best_shift(mask: np.ndarray, ref: np.ndarray, most: int = 20) -> dict:
    """The whole-picture shift (pixels) that lines a mask up best with the reference, and the overlap (shared over
    either) before and after it: how much of a mask's error is only that it sits in the wrong place."""
    def overlap(m):
        return float((m & ref).sum() / max((m | ref).sum(), 1))
    best = (overlap(mask), 0, 0)
    for dy in range(-most, most + 1):
        for dx in range(-most, most + 1):
            m = np.roll(np.roll(mask, dy, 0), dx, 1)
            best = max(best, (overlap(m), dx, dy))
    return {"overlap": round(overlap(mask), 2), "overlap_shifted": round(best[0], 2), "shift_px": [best[1], best[2]]}


def sheets(_a) -> None:
    brown = np.array(json.loads((OUT / "brown.json").read_text()), np.uint8)
    step4 = np.array(Image.open(OUT / "chickadee-step4.png"))
    step5 = np.array(Image.open(OUT / "chickadee-step5.png"))
    ref = load_mask(OUT / "chickadee-tool.png")  # the reference: today's tool, checked by eye against the finish
    numbers, tiles = {}, []
    names = [("color-rule", "As published (color rule)"), ("by-shape", "1a Cleanup by shape, free"),
             ("along-paths", "1b Cleanup along paths, free"), ("tool", "2 Today's tool (SAM-HQ), free"),
             ("mask-edit-1", "3 Image-model mask, run 1"), ("mask-edit-2", "3 Image-model mask, run 2")]
    for key, text in names:
        m = load_mask(OUT / f"chickadee-{key}.png")
        numbers[f"chickadee {key}"] = against(m, ref)
        numbers[f"chickadee {key}"].update(best_shift(m, ref))
        tiles.append(label(block_in(step4, m, brown), text))
    far = ~cv2.dilate((ref | load_mask(OUT / "chickadee-color-rule.png")).astype(np.uint8), disc(12)).astype(bool)
    for i in (1, 2):
        img = np.array(Image.open(OUT / f"chickadee-rerender-{i}.png"))
        row = against(brown_of(img, brown), ref)
        row["background_change"] = round(float(np.abs(img.astype(int) - step4.astype(int)).mean(2)[far].mean()), 1)
        row["background_shift_px"] = shift(step4, img, far)
        numbers[f"chickadee rerender-{i}"] = row
        tiles.append(label(img, f"4 Step re-rendered, run {i}"))
    a, b = (load_mask(OUT / f"chickadee-mask-edit-{i}.png") for i in (1, 2))
    numbers["chickadee mask-edit run 1 vs run 2"] = {"overlap": round(float((a & b).sum() / (a | b).sum()), 3)}
    a, b = (brown_of(np.array(Image.open(OUT / f"chickadee-rerender-{i}.png")), brown) for i in (1, 2))
    numbers["chickadee rerender run 1 vs run 2"] = {"overlap": round(float((a & b).sum() / (a | b).sum()), 3)}
    numbers["chickadee published step 5, read back"] = {
        "mean_difference": round(float(np.abs(block_in(step4, load_mask(OUT / "chickadee-color-rule.png"), brown).astype(int)
                                      - step5.astype(int)).mean()), 2)}
    Image.fromarray(grid(tiles, 2)).save(DOCS / "thin-outlines-step5.jpg", quality=86)

    # the edit and re-render over the finish, to see what lines up: the model's outline in white
    finish = np.array(Image.open(OUT / "chickadee-finish.png"))
    over = []
    for key, text in (("tool", "2 Today's tool"), ("mask-edit-1", "3 Image-model mask, run 1"),
                      ("mask-edit-2", "3 Image-model mask, run 2")):
        m = load_mask(OUT / f"chickadee-{key}.png").astype(np.uint8)
        t = finish.copy()
        cv2.drawContours(t, cv2.findContours(m, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)[0], -1, (255, 255, 255), 2)
        over.append(label(t, text))
    m = brown_of(np.array(Image.open(OUT / "chickadee-rerender-1.png")), brown).astype(np.uint8)
    t = finish.copy()
    cv2.drawContours(t, cv2.findContours(m, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)[0], -1, (255, 255, 255), 2)
    over.append(label(t, "4 Step re-rendered, run 1"))
    Image.fromarray(grid(over, 2)).save(DOCS / "thin-outlines-lined-up.jpg", quality=86)

    # the mast
    finish = np.array(Image.open(OUT / "mast-finish.png"))
    ref = load_mask(OUT / "mast-tool.png")
    ys, xs = np.nonzero(load_mask(OUT / "mast-color-rule.png"))
    x0, x1, y0, y1 = xs.min() - 70, xs.max() + 70, ys.min() - 25, ys.max() + 25
    tiles = [label(cv2.resize(finish[y0:y1, x0:x1], None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC), "Finish")]
    for key, text in (("color-rule", "Color rule"), ("by-shape", "1a By shape"), ("along-paths", "1b Along paths"),
                      ("tool", "2 Today's tool"), ("mask-edit-1", "3 Image model")):
        m = load_mask(OUT / f"mast-{key}.png")
        numbers[f"mast {key}"] = against(m, ref)
        numbers[f"mast {key}"].update(best_shift(m, ref))
        t = finish.copy()
        t[m] = (40, 230, 60)
        tiles.append(label(cv2.resize(t[y0:y1, x0:x1], None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST), text))
    Image.fromarray(grid(tiles, 6)).save(DOCS / "thin-outlines-mast.jpg", quality=86)

    # the lavender's tree
    finish = np.array(Image.open(OUT / "tree-finish.png"))
    today, shaped = load_mask(OUT / "tree-today.png"), load_mask(OUT / "tree-by-shape.png")
    numbers["tree by-shape"] = against(shaped, today)
    ys, xs = np.nonzero(today)
    x0, x1, y0, y1 = max(0, xs.min() - 30), xs.max() + 30, max(0, ys.min() - 30), ys.max() + 30
    tiles = [label(cv2.resize(finish[y0:y1, x0:x1], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC), "Finish")]
    for m, text in ((today, "Today's outline"), (shaped, "1a By shape")):
        t = finish.copy()
        t[m] = (40, 230, 60)
        tiles.append(label(cv2.resize(t[y0:y1, x0:x1], None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST), text))
    Image.fromarray(grid(tiles, 3)).save(DOCS / "thin-outlines-tree.jpg", quality=86)

    numbers["times_s"] = json.loads((OUT / "times.json").read_text())
    numbers["paid"] = {k: {"seconds": v["seconds"], "cost_usd": v["cost_usd"]}
                       for k, v in json.loads((OUT / "ledger.json").read_text()).items()}
    (OUT / "numbers.json").write_text(json.dumps(numbers, indent=1))
    print(json.dumps(numbers, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("free").set_defaults(fn=free)
    p = sub.add_parser("paid")
    p.add_argument("--fresh", action="store_true", help="call again even where a result is saved")
    p.set_defaults(fn=paid)
    sub.add_parser("sheets").set_defaults(fn=sheets)
    a = ap.parse_args()
    a.fn(a)
