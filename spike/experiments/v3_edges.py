"""Spike for #168 (pipeline v3, S3): outlines prompted by name, soft edges for thin and furry things, and outlining
the photo against outlining the finish.

Not part of the pipeline. It takes a bench picture's frozen finish and its v2 baseline run (plan, outlines, paints,
words), changes only how the parts are outlined, and builds the step pictures again with v2's own builder:

    python spike/experiments/v3_edges.py name highland-cow          # SAM 3 text prompts from the parts' names
    python spike/experiments/v3_edges.py photo highland-cow         # SAM-HQ, the baseline's prompts, on the photo
    python spike/experiments/v3_edges.py repeat highland-cow        # boxes read again (jittered) against other wordings
    python spike/experiments/v3_edges.py build highland-cow --variant name-soft    # step pictures, as a lesson copy
    python spike/experiments/v3_edges.py results                    # writes v3_edges.json

Variants (`build --variant`):
    v2         the baseline's own outlines (parts/owner.png), built again: the control
    soft       the baseline's outlines, with a matte at the edge of every object and thin part
    name       objects and thin parts outlined by SAM 3 from the part's name alone (no box, no points, no paths)
    name-soft  name, with the matte

Words:
    name prompt  the part's own `name` from plan.json ("The Highland cow"), lower-cased, with a leading "the" and
                 counts ("four") taken off: SAM 3 wants a short noun phrase.
    matte        how much of each pixel at a part's edge is the part (0 to 1), with the part's color and the color
                 behind it there (pymatting: closed-form alpha and multi-level foreground estimation). The finish is
                 matte * front + (1 - matte) * behind at every pixel, so a step before the part shows `behind`,
                 and the part's step lays `front` over what's there by the matte.

Models: SAM 3 (Meta, ViT-H) as X-AnyLabeling's ONNX export (CVHub520/X-AnyLabeling release v3.0.0, 3.1 GB, CPU),
with OpenAI CLIP's tokenizer from the osam package. They live in models/spike168/ (git-ignored). The pictures and
numbers go in spike/experiments/bench/runs/edges/ (git-ignored); `results` gathers them into v3_edges.json.
docs/spikes/v3-edges.md has the results.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
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
import outline as ol  # noqa: E402

BENCH = ROOT / "spike" / "experiments" / "bench"
OUT = BENCH / "runs" / "edges"
RUNS = Path("/home/user/gesso-baseline/output")  # the v2 baseline runs (docs/spikes/v3-yardstick.md, section 5)
MODELS = ROOT / "models" / "spike168"
XA3 = "https://github.com/CVHub520/X-AnyLabeling/releases/download/v3.0.0/"
SAM3_FILES = ["sam3_image_encoder.onnx", "sam3_image_encoder.onnx.data", "sam3_language_encoder.onnx",
              "sam3_language_encoder.onnx.data", "sam3_decoder.onnx", "sam3_decoder.onnx.data"]
# Fur, whiskers, thin trunks and twigs, leaves: the four pictures most likely to show an edge change
# (docs/decisions.md: spikes start on the 3 or 4 bench pictures most likely to show their effect).
ALL4 = ["highland-cow", "sleeping-cat", "chickadee", "birch-grove"]
# Second plans of the same frozen finish, written by Claude in another run: S7's plan-first runs keep the baseline's
# outlining step, so their boxes and points are a second, independent try at the same parts.
SECOND = {"highland-cow": BENCH / "runs/plan-first/highland-cow_skill_20261116-212627-plan-first",
          "sleeping-cat": BENCH / "runs/plan-first/sleeping-cat_skill_20261116-203502-plan-first",
          "birch-grove": BENCH / "runs/plan-first/birch-grove_skill_20261116-210750-plan-first"}

SAM3_CONF = 0.5  # X-AnyLabeling's default: a detection under this score is dropped
MATTE_REACH = 0.012  # the unsure band around a part's hard edge, each way, as a share of the long side
MATTE_SURE = 0.98  # matte values at or above this count as the part; at or below 1 - this, as behind
FEATHER = 3  # pixels inside a hard outline that blend with what's behind, at the part's steps
MOVED = 24  # RGB levels: a pixel this far from what it was has changed (build_steps' final_gap uses the same)


# ---------------------------------------------------------------------------
# The picture and its baseline run
# ---------------------------------------------------------------------------


def baseline_run(picture: str, runs: Path = RUNS) -> Path:
    key = json.loads((BENCH / "baseline" / "key.json").read_text())["packets"]
    folder = next(v["lesson"] for v in key.values() if v["picture"] == picture)
    return runs / folder


def load(picture: str, runs: Path = RUNS) -> dict:
    """The frozen finish and photo, and the baseline run's plan, outlines and background render."""
    run = baseline_run(picture, runs)
    pics = BENCH / "pictures" / picture
    finish = np.array(Image.open(pics / "99_finish.png").convert("RGB"))
    plan = json.loads((run / "plan.json").read_text())
    owner = np.array(Image.open(run / "parts" / "owner.png")).astype(np.int32)
    if owner.shape != finish.shape[:2]:
        raise SystemExit(f"{picture}: the baseline's outlines aren't the frozen finish's size")
    plate = run / "98_background.png"
    background = np.array(Image.open(plate).convert("RGB")) if plate.exists() else None
    return {"picture": picture, "run": run, "finish": finish, "plan": plan, "owner": owner,
            "background": background}


def prompted(part: dict) -> bool:
    """The parts v2 asks the outline model for: objects and thin parts, and areas that aren't the backdrop.
    Marks stay on the color rule in every variant (docs/spikes/outline-models.md: the marks are what's painted)."""
    return part["kind"] in ("object", "thin")


# ---------------------------------------------------------------------------
# SAM 3, prompted by name
# ---------------------------------------------------------------------------


def name_prompt(part: dict) -> str:
    """The part's own name as a short noun phrase: "The Highland cow" -> "highland cow", "The four leaves" ->
    "leaves", "Legs and feet" -> "legs and feet"."""
    text = (part.get("name") or part["id"].replace("-", " ")).lower().strip()
    text = re.sub(r"^(the|a|an)\s+", "", text)
    text = re.sub(r"^(two|three|four|five|six|seven|eight|nine|ten|\d+)\s+", "", text)
    return text


class Sam3:
    """SAM 3 (ViT-H) from X-AnyLabeling's ONNX export, CPU. `embed` once per picture, `mask` per text prompt. The
    export takes text only: no boxes or points with a text prompt in this form (its README)."""

    def __init__(self, folder: Path = MODELS):
        import onnxruntime as ort

        missing = [f for f in SAM3_FILES if not (folder / f).exists()]
        if missing:
            raise ol.NoModel(f"SAM 3 files missing in {folder}: {missing} (from {XA3})")
        so = ort.SessionOptions()
        so.log_severity_level = 3
        so.enable_cpu_mem_arena = False  # 15 GB machine: the arena kept the encoder's peak, and SAM-HQ beside it ran out
        cpu = ["CPUExecutionProvider"]
        self.enc = ort.InferenceSession(str(folder / "sam3_image_encoder.onnx"), so, providers=cpu)
        self.lang = ort.InferenceSession(str(folder / "sam3_language_encoder.onnx"), so, providers=cpu)
        self.dec = ort.InferenceSession(str(folder / "sam3_decoder.onnx"), so, providers=cpu)
        i = self.enc.get_inputs()[0]
        self.size = (int(i.shape[-2]) or 1008, int(i.shape[-1]) or 1008)
        self.float_input = i.type == "tensor(float)"
        self.dec_inputs = [x.name for x in self.dec.get_inputs()]
        spec = importlib.util.spec_from_file_location("sam3_clip_tokenizer", folder / "clip" / "simple_tokenizer.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.tok = mod.SimpleTokenizer(str(folder / "clip" / "bpe_simple_vocab_16e6.txt.gz"))
        self.emb = None
        self.shape = None

    def tokens(self, text: str, context: int = 32) -> np.ndarray:
        ids = [self.tok.encoder["<|startoftext|>"]] + self.tok.encode(text) + [self.tok.encoder["<|endoftext|>"]]
        out = np.zeros((1, context), np.int64)
        out[0, :min(len(ids), context)] = ids[:context]
        if len(ids) > context:
            out[0, -1] = self.tok.encoder["<|endoftext|>"]
        return out

    def embed(self, rgb: np.ndarray) -> None:
        self.shape = rgb.shape[:2]
        x = cv2.resize(rgb, (self.size[1], self.size[0]), interpolation=cv2.INTER_LINEAR).transpose(2, 0, 1)
        x = (((x / 255.0) - 0.5) / 0.5).astype(np.float32) if self.float_input else x.astype(np.uint8)
        self.emb = self.enc.run(None, {self.enc.get_inputs()[0].name: x})

    def mask(self, text: str, conf: float = SAM3_CONF) -> tuple[np.ndarray, list[float]]:
        """Every instance of `text` above `conf`, joined into one outline, and each instance's score."""
        lm, lf, le = self.lang.run(None, {"tokens": self.tokens(text)})[:3]
        h, w = self.shape
        e = self.emb
        inputs = {"original_height": np.array(h, np.int64), "original_width": np.array(w, np.int64),
                  "vision_pos_enc_0": e[0], "vision_pos_enc_1": e[1], "vision_pos_enc_2": e[2],
                  "backbone_fpn_0": e[3], "backbone_fpn_1": e[4], "backbone_fpn_2": e[5],
                  "language_mask": lm, "language_features": lf, "language_embeds": le,
                  "box_coords": np.zeros((1, 1, 4), np.float32), "box_labels": np.ones((1, 1), np.int64),
                  "box_masks": np.ones((1, 1), np.bool_)}
        out = self.dec.run(None, {k: v for k, v in inputs.items() if k in self.dec_inputs})
        masks, scores = out[2], np.asarray(out[1]).ravel()
        keep = np.flatnonzero(scores > conf)
        joined = np.zeros((h, w), bool)
        for j in keep:
            m = masks[j]
            m = m[0] if m.ndim == 3 else m
            if m.shape != (h, w):
                m = cv2.resize(m.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
            joined |= m > 0
        return joined, [round(float(s), 3) for s in scores[keep]]


# ---------------------------------------------------------------------------
# Outlines: by name, from the photo, and the baseline's again
# ---------------------------------------------------------------------------


def outline_by_name(picture: np.ndarray, parts: list[dict], sam3: Sam3, sam=None) -> tuple[np.ndarray, list[dict]]:
    """Every object and thin part from SAM 3 and its name alone. The rest (areas, marks) as v2 does it, by the
    same tool (outline.outline), so only the prompt changes. A part SAM 3 finds nothing for falls back to v2's
    box-and-points prompt (counted: `fallback`)."""
    given, rows, use = {}, [], []
    if sam3.emb is None or sam3.shape != picture.shape[:2]:
        sam3.embed(picture)
    for p in parts:
        q = dict(p)
        if prompted(p):
            started = time.time()
            m, scores = sam3.mask(name_prompt(p))
            row = {"id": p["id"], "prompt": name_prompt(p), "scores": scores, "seconds": round(time.time() - started, 2)}
            if m.any():
                given[p["id"]] = m
                if p["kind"] == "thin":  # no paths and no band: the name is the whole prompt
                    q = {k: v for k, v in p.items() if k not in ("paths", "path", "width", "points_in", "points_out")}
                    q.update(kind="object", box=[0, 0, 1, 1])
            else:
                row["fallback"] = True
            rows.append(row)
        use.append(q)
    sam = sam or ol.Sam()  # areas that aren't the backdrop, and any fallback, still use v2's model
    sam.emb = None
    _, owner, _ = ol.outline(picture, use, sam, given)
    return owner, rows


def outline_v2(picture: np.ndarray, parts: list[dict], sam=None) -> np.ndarray:
    """v2's own outline tool with the plan's own boxes, points and paths, on any picture."""
    sam = sam or ol.Sam()
    sam.emb = None
    return ol.outline(picture, parts, sam)[1]


def photo_frame(picture: str) -> np.ndarray:
    """The photo in the finish's frame: the canvas fit when the run extended the canvas, else the framed photo."""
    pics = BENCH / "pictures" / picture
    path = pics / "00_canvas_fit.png" if (pics / "00_canvas_fit.png").exists() else pics / "00_canvas_frame.png"
    return np.array(Image.open(path).convert("RGB"))


def iou(a: np.ndarray, b: np.ndarray) -> float:
    u = (a | b).sum()
    return round(float((a & b).sum() / u), 3) if u else 1.0


def roots_prompted(parts: list[dict]) -> list[int]:
    """The things in front that get a matte: objects and thin parts with no parent (with what's painted on them)."""
    return [k for k, p in enumerate(parts) if prompted(p) and not p.get("parent")]


def edge_fit(finish: np.ndarray, mask: np.ndarray) -> float | None:
    """How much of an outline's edge lies on an edge the finish really has: the share of the outline's border
    pixels within 2 pixels of a Canny edge of the (lightly blurred) finish. 1 = the outline follows the paint."""
    k3 = np.ones((3, 3), np.uint8)
    border = (cv2.dilate(mask.astype(np.uint8), k3) > 0) & ~(cv2.erode(mask.astype(np.uint8), k3) > 0)
    if border.sum() < 20:
        return None
    gray = cv2.cvtColor(cv2.GaussianBlur(finish, (0, 0), 1.0), cv2.COLOR_RGB2GRAY)
    edges = cv2.dilate(cv2.Canny(gray, 40, 100), np.ones((5, 5), np.uint8)) > 0
    return round(float(edges[border].mean()), 3)


def compare_outlines(finish: np.ndarray, parts: list[dict], base: np.ndarray, other: np.ndarray) -> list[dict]:
    """For every thing in front (with its children): how far `other` is from the baseline, and how well each
    follows the finish's own edges."""
    out = []
    for k in roots_prompted(parts):
        fam = bs._family(parts, k)
        a, b = np.isin(base, fam), np.isin(other, fam)
        out.append({"id": parts[k]["id"], "iou_v2": iou(a, b), "share_v2": round(float(a.mean()), 4),
                    "share": round(float(b.mean()), 4), "edge_fit_v2": edge_fit(finish, a), "edge_fit": edge_fit(finish, b)})
    return out


# ---------------------------------------------------------------------------
# Mattes: soft edges for the things in front
# ---------------------------------------------------------------------------


def matte(finish: np.ndarray, mask: np.ndarray, reach: float = MATTE_REACH) -> dict:
    """A soft edge for one thing in front, from its hard outline: a trimap (sure inside, unsure band, sure
    outside), closed-form alpha in the band, and the front and behind colors there (pymatting). Arrays are the
    picture's size; outside the band alpha is 0 or 1 and front = behind = the finish."""
    from pymatting import estimate_alpha_cf, estimate_foreground_ml

    h, w = mask.shape
    r = max(2, int(reach * max(h, w)))
    kr = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    m8 = mask.astype(np.uint8)
    sure, maybe = cv2.erode(m8, kr) > 0, cv2.dilate(m8, kr) > 0
    alpha = mask.astype(np.float32)
    front = finish.astype(np.float32) / 255
    behind = front.copy()
    ys, xs = np.nonzero(maybe)
    if not len(ys) or not sure.any():  # nothing, or a part thinner than the band everywhere: no matte, its hard edge
        return {"alpha": alpha, "front": front * 255, "behind": behind * 255, "band": maybe & ~sure}
    y0, y1, x0, x1 = max(0, ys.min() - r), min(h, ys.max() + r + 1), max(0, xs.min() - r), min(w, xs.max() + r + 1)
    img = front[y0:y1, x0:x1].astype(np.float64)
    tri = np.where(sure[y0:y1, x0:x1], 1.0, np.where(maybe[y0:y1, x0:x1], 0.5, 0.0))
    a = np.clip(estimate_alpha_cf(img, tri), 0, 1)
    F, B = estimate_foreground_ml(img, a, return_background=True)
    alpha[y0:y1, x0:x1] = a
    front[y0:y1, x0:x1], behind[y0:y1, x0:x1] = F, B
    # inside the outline only a thin feather blends with what's behind: deeper in, a color unlike the rest of the
    # part (a cat's pink ear) reads to the matte as background, and blending there brought the ear in early
    feather = mask & ~(cv2.erode(m8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * FEATHER + 1,) * 2)) > 0)
    return {"alpha": alpha, "front": np.clip(front, 0, 1) * 255, "behind": np.clip(behind, 0, 1) * 255,
            "band": (maybe & ~mask) | feather}


def mattes(finish: np.ndarray, parts: list[dict], owner: np.ndarray) -> tuple[dict[int, dict], float]:
    started = time.time()
    out = {k: matte(finish, np.isin(owner, bs._family(parts, k))) for k in roots_prompted(parts)}
    return out, round(time.time() - started, 1)


def nearest_inside(mine: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For every pixel, the row and column of the nearest pixel of `mine`."""
    _, lab = cv2.distanceTransformWithLabels((~mine).astype(np.uint8), cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(mine)
    ry, rx = np.zeros(lab.max() + 1, np.int64), np.zeros(lab.max() + 1, np.int64)
    ry[lab[ys, xs]], rx[lab[ys, xs]] = ys, xs
    return ry[lab], rx[lab]


def soften(finish: np.ndarray, plan: dict, owner: np.ndarray, pictures: list[np.ndarray],
           soft: dict[int, dict]) -> list[np.ndarray]:
    """v2's step pictures with each thing in front laid as a layer with a soft edge. In its unsure band:

    - before its first step, where the picture already shows the finish outside its outline (the fur or whiskers
      painted with the wall), show what's behind instead;
    - from its first step, outside its outline: by the matte over what's behind, the part's paint as it is now at
      the nearest pixel inside (a flat coat gives a flat fringe), and its front color from its last step on;
    - from its first step, inside its outline: its paint by the matte over what's behind.

    The last picture stays the finish. Nothing outside a band changes."""
    parts, steps = plan["parts"], bs.flat_steps(plan)
    index = {p["id"]: i for i, p in enumerate(parts)}
    first: dict[int, int] = {}
    last: dict[int, int] = {}
    for i, s in enumerate(steps):
        for k in soft:
            if index[s["part"]] in bs._family(parts, k):
                first.setdefault(k, i)
                last[k] = i
    started_at: dict[int, int] = {}
    for i, s in enumerate(steps):
        started_at.setdefault(index[s["part"]], i)

    def seen_by(i: int) -> set[int]:
        return {q for q, f in started_at.items() if f <= i}

    fin = finish.astype(np.float32)
    prep = {}
    for k, m in soft.items():
        mine = np.isin(owner, bs._family(parts, k))
        prep[k] = (mine, nearest_inside(mine) if mine.any() else None)
    out = []
    for i, pic in enumerate(pictures):
        if i == len(pictures) - 1:
            out.append(pic.copy())
            continue
        img = pic.astype(np.float32)
        for k, m in soft.items():
            band, a = m["band"], m["alpha"]
            mine, near = prep[k]
            if k not in first or i < first[k]:
                shown = band & ~mine & (np.abs(img - fin).max(2) <= 6) & (a > 0.02)
                img[shown] = m["behind"][shown]
                continue
            if near is None:
                continue
            ny, nx = near
            # only over what's behind it: never over a part listed after it (the horns beside the cow, the cat
            # in front of the window), painted yet or not; nor over a part not started
            fam = set(bs._family(parts, k))
            later = np.isin(owner, [q for q in range(len(parts)) if (q > k and q not in fam) or q not in seen_by(i)])
            outer, inner = band & ~mine & ~later, band & mine
            aa = a[..., None]
            # until the part's last step, its fringe is the part's paint as it is now at the nearest pixel inside
            # (a flat coat gives a flat fringe; an ear's pink can't come early); from then, the front color
            paint = m["front"] if i >= last[k] else img[ny, nx]
            fringe = aa * paint + (1 - aa) * m["behind"]
            edge = aa * img + (1 - aa) * m["behind"]
            img[outer] = fringe[outer]
            img[inner] = edge[inner]
        out.append(np.clip(img + 0.5, 0, 255).astype(np.uint8))
    return out


# ---------------------------------------------------------------------------
# The runs: outlines, step pictures, lessons
# ---------------------------------------------------------------------------

VARIANTS = {"v2": ("v2", False), "soft": ("v2", True), "name": ("name", False), "name-soft": ("name", True),
            "photo": ("photo", False)}


def save_mask(path: Path, owner: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(owner.astype(np.uint8)).save(path)


def read_mask(path: Path) -> np.ndarray:
    return np.array(Image.open(path)).astype(np.int32)


def outlines(picture: str, sam3: Sam3 | None = None, sam=None) -> dict:
    """Outline the picture every way, save each owner map in runs/edges/outlines/<picture>/, and the numbers."""
    d = load(picture)
    parts, finish = d["plan"]["parts"], d["finish"]
    folder = OUT / "outlines" / picture
    sam = sam or ol.Sam()
    info: dict = {"picture": picture, "run": d["run"].name}
    t = time.time()
    again = outline_v2(finish, parts, sam)
    info["v2_seconds"] = round(time.time() - t, 1)
    info["v2_again_differs"] = round(float((again != d["owner"]).mean()), 5)  # the baseline's tool, run again
    save_mask(folder / "v2.png", d["owner"])
    sam3 = sam3 or Sam3()
    sam3.emb = None
    t = time.time()
    sam3.embed(finish)
    info["sam3_read_seconds"] = round(time.time() - t, 1)
    t = time.time()
    by_name, rows = outline_by_name(finish, parts, sam3, sam)
    info["name_seconds"] = round(time.time() - t + info["sam3_read_seconds"], 1)
    info["name_prompts"] = rows
    save_mask(folder / "name.png", by_name)
    info["name"] = compare_outlines(finish, parts, d["owner"], by_name)
    t = time.time()
    photo = photo_frame(picture)
    by_photo = outline_v2(photo, parts, sam)
    info["photo_seconds"] = round(time.time() - t, 1)
    save_mask(folder / "photo.png", by_photo)
    info["photo"] = compare_outlines(finish, parts, d["owner"], by_photo)
    info["photo_on_photo"] = [r | {"edge_fit_photo": edge_fit(photo, np.isin(by_photo, bs._family(parts, k)))}
                              for r, k in zip(info["photo"], roots_prompted(parts))]
    for name, own in (("v2", d["owner"]), ("name", by_name), ("photo", by_photo)):
        Image.fromarray(ol.preview(finish, parts, own)).save(folder / f"{name}.jpg", quality=85)
    (folder / "outline.json").write_text(json.dumps(info, indent=1))
    return info


# Other wordings a plan could give the same thing: the second plans' names where they differ, and plain paraphrases.
WORDINGS = {"highland-cow": {"cow": ["cow", "shaggy cow"], "horns": ["cow horns", "the horns"], "loch": ["lake", "water"]},
            "sleeping-cat": {"cat": ["cat", "tabby cat"], "blanket": ["blanket", "knitted blanket"],
                             "window": ["window", "window frame"], "sill": ["window sill", "sill"]},
            "chickadee": {"branch": ["tree branch", "branch and trunk"], "leaves": ["four leaves", "autumn leaves"],
                          "bird": ["bird", "small bird"], "bird-feet": ["bird feet", "feet"], "sun": ["the sun", "sun disk"]},
            "birch-grove": {"birches": ["birch trees", "white birch trunks"]}}
JITTER = 0.03  # how far a box edge or point can land from where it was meant, as a share of the picture: a third of
# a 10% grid cell, the grid Claude reads positions off
DRAWS = 5


def jitter(parts: list[dict], rng: np.random.Generator, by: float = JITTER) -> list[dict]:
    """The same plan with every box edge, point and path point moved by up to `by`, as a second reading might."""
    def move(v):
        return float(np.clip(v + rng.uniform(-by, by), 0, 1))

    out = []
    for p in parts:
        q = json.loads(json.dumps(p))
        for key in ("box",):
            if q.get(key):
                x0, y0, x1, y1 = (move(v) for v in q[key])
                q[key] = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
        if q.get("boxes"):
            q["boxes"] = [[min(a, c), min(b, d), max(a, c), max(b, d)] for a, b, c, d in
                          ([move(v) for v in bx] for bx in q["boxes"])]
        for key in ("points_in", "points_out"):
            if q.get(key):
                q[key] = [[move(x), move(y)] for x, y in q[key]]
        if q.get("paths"):
            q["paths"] = [[[move(x), move(y)] for x, y in path] for path in q["paths"]]
        out.append(q)
    return out


def repeat(picture: str, sam3: Sam3 | None = None, sam=None) -> dict:
    """How much two runs of one picture differ, by how they were prompted, for each thing in front (with its
    children), as the IoU of the two outlines (1 = the same).

    - boxes: the baseline's own boxes, points and paths, then DRAWS readings of them each moved by up to JITTER.
    - names: the baseline's names, then each other wording in WORDINGS (one change at a time).
    - plans: where S7's plan-first run gave a part different prompts (it started from the baseline's), the two."""
    d = load(picture)
    parts, finish = d["plan"]["parts"], d["finish"]
    sam3, sam = sam3 or Sam3(), sam or ol.Sam()
    sam3.emb = None
    rng = np.random.default_rng(168)
    fronts = roots_prompted(parts)
    by_box = {parts[k]["id"]: [] for k in fronts}
    for _ in range(DRAWS):
        other = outline_v2(finish, jitter(parts, rng), sam)
        for k in fronts:
            fam = bs._family(parts, k)
            by_box[parts[k]["id"]].append(iou(np.isin(d["owner"], fam), np.isin(other, fam)))
    base_name, _ = outline_by_name(finish, parts, sam3, sam)
    by_name = {parts[k]["id"]: [] for k in fronts}
    for k in fronts:
        for words in WORDINGS.get(picture, {}).get(parts[k]["id"], []):
            q = [dict(p) for p in parts]
            q[k]["name"] = words
            other, _ = outline_by_name(finish, q, sam3, sam)
            fam = bs._family(parts, k)
            by_name[parts[k]["id"]].append({"words": name_prompt(q[k]), "iou": iou(np.isin(base_name, fam), np.isin(other, fam))})
    plans = []
    if picture in SECOND:
        second = SECOND[picture]
        pb = json.loads((second / "plan.json").read_text())["parts"]
        owner_b = read_mask(second / "parts" / "owner.png")
        ids_b = {p["id"]: i for i, p in enumerate(pb)}
        for k in fronts:
            j = ids_b.get(parts[k]["id"])
            if j is None:
                continue
            keys = ("box", "boxes", "points_in", "points_out", "paths", "width")
            if all(parts[k].get(x) == pb[j].get(x) for x in keys):
                continue
            plans.append({"id": parts[k]["id"], "iou": iou(np.isin(d["owner"], bs._family(parts, k)),
                                                          np.isin(owner_b, bs._family(pb, j)))})
    info = {"picture": picture, "jitter": JITTER, "draws": DRAWS,
            "parts": [{"id": parts[k]["id"], "share": round(float(np.isin(d["owner"], bs._family(parts, k)).mean()), 4),
                       "boxes_iou": by_box[parts[k]["id"]], "names": by_name[parts[k]["id"]]} for k in fronts],
            "plans": plans}
    folder = OUT / "outlines" / picture
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "repeat.json").write_text(json.dumps(info, indent=1))
    return info


def outside(pictures: list[np.ndarray], painted: list[np.ndarray], bands: list[np.ndarray]) -> float:
    """Check 2: the most any step changes outside what it paints (its painted area and rim, and the soft band of
    the thing it belongs to), as a share of the picture."""
    worst = 0.0
    k3 = np.ones((3, 3), np.uint8)
    for i in range(1, len(pictures) - 1):
        changed = np.abs(pictures[i].astype(np.int16) - pictures[i - 1].astype(np.int16)).max(2) > 6
        allowed = (cv2.dilate(painted[i].astype(np.uint8), k3) > 0) | bands[i]
        worst = max(worst, float((changed & ~allowed).mean()))
    return round(worst, 5)


def build_lesson(picture: str, variant: str) -> dict:
    """The baseline lesson with its outlines and step pictures replaced: a copy of the run in
    runs/edges/<variant>/lessons/, same plan, paints and words, so the A/B page and the fault counter see one
    change."""
    d = load(picture)
    source, is_soft = VARIANTS[variant]
    parts, plan, finish = d["plan"]["parts"], d["plan"], d["finish"]
    owner = d["owner"] if source == "v2" else read_mask(OUT / "outlines" / picture / f"{source}.png")
    t = time.time()
    pictures, rows, painted = bs.build(finish, plan, owner, d["background"])
    build_s = time.time() - t
    steps = bs.flat_steps(plan)
    index = {p["id"]: i for i, p in enumerate(parts)}
    no_band = np.zeros(owner.shape, bool)
    bands = [no_band] * len(steps)
    matte_s = soft_s = 0.0
    if is_soft:
        soft, matte_s = mattes(finish, parts, owner)
        t = time.time()
        pictures = soften(finish, plan, owner, pictures, soft)
        soft_s = round(time.time() - t, 1)
        root_of = {q: k for k in soft for q in bs._family(parts, k)}
        bands = [soft[root_of[index[s["part"]]]]["band"] if index[s["part"]] in root_of else no_band for s in steps]
    ghosts = bs.ghosts(finish, parts, owner, steps, pictures, painted)
    for r, g in zip(rows, ghosts):
        r["ghosts"] = g
    folder = OUT / variant / picture
    folder.mkdir(parents=True, exist_ok=True)
    lesson = OUT / variant / "lessons" / f"{d['run'].name}-{variant}"
    if lesson.exists():
        shutil.rmtree(lesson)
    shutil.copytree(d["run"], lesson, ignore=shutil.ignore_patterns("trials", "versions", "busy", "embed", "*.html"))
    save_mask(lesson / "parts" / "owner.png", owner)
    Image.fromarray(ol.preview(finish, parts, owner)).save(lesson / "parts" / "preview.jpg", quality=85)
    box = (json.loads((lesson / "canvas.json").read_text()).get("canvas_box") or [0, 0, 1, 1]) \
        if (lesson / "canvas.json").exists() else [0, 0, 1, 1]
    h, w = owner.shape
    x0, y0, x1, y1 = round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h)
    for i, (s, img) in enumerate(zip(steps, pictures)):
        name = f"{i + 1:02d}_{s['id']}.png"
        Image.fromarray(img).save(lesson / name)
        if (lesson / "canvas" / name).exists():
            Image.fromarray(img[y0:y1, x0:x1]).save(lesson / "canvas" / name)
    Image.fromarray(bs.contact_sheet(pictures, steps)).save(folder / "steps.jpg", quality=88)
    listed = [g for r in rows for g in r["ghosts"]]
    result = {"picture": picture, "variant": variant, "lesson": str(lesson.relative_to(ROOT)),
              "build_seconds": round(build_s, 1), "matte_seconds": matte_s, "soften_seconds": soft_s,
              "steps": len(steps), "outside_max": outside(pictures, painted, bands),
              "ghost_steps": sum(any(g["edge"] >= bs.GHOST_EDGE for g in r["ghosts"]) for r in rows),
              "ghosts_listed": len(listed), "worst_ghost": max([g["edge"] for g in listed], default=0.0),
              "final_gap": rows[-1]["final_gap"], "rows": rows}
    (folder / "build.json").write_text(json.dumps(result, indent=1))
    return result


# ---------------------------------------------------------------------------
# The write-up's numbers and pictures
# ---------------------------------------------------------------------------

RESULTS = Path(__file__).with_suffix(".json")


def results() -> dict:
    out: dict = {"outlines": {}, "repeat": {}, "builds": {}}
    for path in sorted((OUT / "outlines").glob("*/outline.json")):
        out["outlines"][path.parent.name] = json.loads(path.read_text())
    for path in sorted((OUT / "outlines").glob("*/repeat.json")):
        out["repeat"][path.parent.name] = json.loads(path.read_text())
    for path in sorted(OUT.glob("*/*/build.json")):
        b = json.loads(path.read_text())
        out["builds"].setdefault(b["variant"], {})[b["picture"]] = {k: v for k, v in b.items() if k != "rows"}
    return out


def crops(picture: str, variants: list[str], steps: list[int], box: list[float], out: Path, width: int = 360) -> None:
    """A picture for the write-up: a crop (box, 0-1) of the chosen steps, one row per variant."""
    d = load(picture)
    ids = [s["id"] for s in bs.flat_steps(d["plan"])]
    rows = []
    for v in variants:
        lesson = OUT / v / "lessons" / f"{d['run'].name}-{v}"
        tiles = []
        for n in steps:
            img = np.array(Image.open(lesson / f"{n:02d}_{ids[n - 1]}.png").convert("RGB"))
            h, w = img.shape[:2]
            c = img[int(box[1] * h):int(box[3] * h), int(box[0] * w):int(box[2] * w)]
            c = cv2.resize(c, (width, int(c.shape[0] * width / c.shape[1])), interpolation=cv2.INTER_AREA)
            cv2.putText(c, f"{v} {n}", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(c, f"{v} {n}", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
            tiles.append(c)
        rows.append(np.hstack(tiles))
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.vstack(rows)).save(out, quality=85)


def variant_lesson(picture: str, variant: str) -> Path:
    return OUT / variant / "lessons" / f"{baseline_run(picture).name}-{variant}"


def grade_folders(pairs: list[tuple[str, str]], out: Path, seed: int = 168) -> dict:
    """The blind A/B round for Claude's graders (bench/ab_grader.md): per (picture, variant) <out>/<picture>-<variant>-g1/
    and -g2/, the v2 baseline and the variant's lesson as A/ and B/, sides drawn from the seed and swapped for the
    second grader. The key is only in <out>/key.json. `out` must be outside the repository."""
    import random

    sys.path.insert(0, str(BENCH))
    import packet

    out = Path(out).resolve()
    if ROOT in out.parents or out == ROOT:
        raise SystemExit("the grading folders must be outside the repository")
    rng = random.Random(seed)
    key: dict = {"round": "s3-edges", "seed": seed, "pictures": {}}
    for pic, variant in pairs:
        sides = {"v2": baseline_run(pic), variant: variant_lesson(pic, variant)}
        order = ["v2", variant] if rng.random() < 0.5 else [variant, "v2"]
        entry = key["pictures"].setdefault(f"{pic}/{variant}", {})
        for g, names in (("g1", order), ("g2", order[::-1])):
            folder = out / f"{pic}-{variant}-{g}"
            if folder.exists():
                shutil.rmtree(folder)
            for side, name in zip("AB", names):
                packet.build_one(sides[name], folder / side)
            shutil.copy(BENCH / "ab_grader.md", folder / "ab_grader.md")
            entry[g] = {"A": names[0], "B": names[1], "lessons": {n: sides[n].name for n in names}}
    (out / "key.json").write_text(json.dumps(key, indent=1))
    return key


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def pictures_of(arg: str) -> list[str]:
    return ALL4 if arg == "all4" else arg.split(",")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("outline", help="outline every way (v2 again, by name, the photo); free, local")
    p.add_argument("picture")
    p = sub.add_parser("repeat", help="two Claude plans of one finish: boxes against names")
    p.add_argument("picture")
    p = sub.add_parser("build", help="step pictures from a variant's outlines, as a copy of the baseline lesson")
    p.add_argument("picture")
    p.add_argument("--variant", choices=sorted(VARIANTS), required=True)
    sub.add_parser("results", help="write v3_edges.json from the runs")
    p = sub.add_parser("grade", help="the blind A/B folders for Claude's graders, outside the repository")
    p.add_argument("pairs", help="picture/variant, comma-separated (chickadee/name,birch-grove/soft)")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("crops", help="a picture for the write-up: a crop of chosen steps, a row per variant")
    p.add_argument("picture")
    p.add_argument("--variants", required=True)
    p.add_argument("--steps", required=True)
    p.add_argument("--box", required=True, help="x0,y0,x1,y1 as shares of the picture")
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd in ("outline", "repeat"):
        sam3, sam = Sam3(), ol.Sam()
        for name in pictures_of(a.picture):
            r = outlines(name, sam3, sam) if a.cmd == "outline" else repeat(name, sam3, sam)
            print(json.dumps(r))
    elif a.cmd == "build":
        for name in pictures_of(a.picture):
            r = build_lesson(name, a.variant)
            print(json.dumps({k: v for k, v in r.items() if k != "rows"}))
    elif a.cmd == "results":
        RESULTS.write_text(json.dumps(results(), indent=1, sort_keys=True) + "\n")
        print(json.dumps({"out": str(RESULTS.relative_to(ROOT))}))
    elif a.cmd == "grade":
        pairs = [tuple(x.split("/")) for x in a.pairs.split(",")]
        print(json.dumps(grade_folders(pairs, a.out), indent=1))
    elif a.cmd == "crops":
        crops(a.picture, a.variants.split(","), [int(n) for n in a.steps.split(",")],
              [float(x) for x in a.box.split(",")], Path(a.out))


if __name__ == "__main__":
    main()
