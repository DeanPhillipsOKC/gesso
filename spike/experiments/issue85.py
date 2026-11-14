"""Spike for #85: does a bigger or newer outline model get thin and soft parts right where SAM ViT-B doesn't?

Not part of the pipeline. Runs every local candidate on the same prompts, taken from the plans as they are, on the
three fixtures and the three gate runs, and writes the outlines, the timings, and the side-by-side sheets that
docs/spikes/outline-models.md shows.

    python spike/experiments/issue85.py fetch            # download the candidates into models/spike85/ (4.4 GB)
    python spike/experiments/issue85.py run [--only sam-b,sam2.1-l]   # outlines + numbers -> output/spike85/
    python spike/experiments/issue85.py sheets           # the pictures in docs/spikes/

The models are ONNX files from GitHub releases (rembg and X-AnyLabeling's exports), run with onnxruntime on CPU,
like the pipeline's own. Nothing here is imported by the tools.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "spike"))
import outline as ol  # noqa: E402

MODELS = ROOT / "models" / "spike85"
OUT = ROOT / "output" / "spike85"
DOCS = ROOT / "docs" / "spikes"
XA = "https://github.com/CVHub520/X-AnyLabeling/releases/download/"
REMBG = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"

# name -> (kind, encoder url, decoder url). The first is the pipeline's own model, already in models/.
CANDIDATES = {
    "sam-b": ("sam-rembg", REMBG + "vit_b-encoder-quant.onnx", REMBG + "vit_b-decoder-quant.onnx"),
    "sam-l": ("sam", XA + "v0.2.0/sam_vit_l_0b3195.encoder.quant.onnx", XA + "v0.2.0/sam_vit_l_0b3195.decoder.quant.onnx"),
    "sam-h": ("sam", XA + "v0.2.0/sam_vit_h_4b8939.encoder.quant.onnx", XA + "v0.2.0/sam_vit_h_4b8939.decoder.quant.onnx"),
    "hq-b": ("hq", XA + "v2.0.0/sam_hq_vit_b_encoder_quant.onnx", XA + "v2.0.0/sam_hq_vit_b_decoder.onnx"),
    "hq-l": ("hq", XA + "v2.0.0/sam_hq_vit_l_encoder_quant.onnx", XA + "v2.0.0/sam_hq_vit_l_decoder.onnx"),
    "hq-h": ("hq", XA + "v2.0.0/sam_hq_vit_h_encoder_quant.onnx", XA + "v2.0.0/sam_hq_vit_h_decoder.onnx"),
    "sam2.1-s": ("sam2", XA + "v2.5.0/sam2.1_hiera_small.encoder.onnx", XA + "v2.5.0/sam2.1_hiera_small.decoder.onnx"),
    "sam2.1-b+": ("sam2", XA + "v2.5.0/sam2.1_hiera_base_plus.encoder.onnx", XA + "v2.5.0/sam2.1_hiera_base_plus.decoder.onnx"),
    "sam2.1-l": ("sam2", XA + "v2.5.0/sam2.1_hiera_large.encoder.onnx", XA + "v2.5.0/sam2.1_hiera_large.decoder.onnx"),
}
MATTERS = {  # no prompts: "the thing in front" of whatever picture (or crop) they're given, as a soft matte
    "birefnet": REMBG + "BiRefNet-general-epoch_244.onnx",
    "birefnet-tiny": REMBG + "BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx",
}

PICTURES = {  # name -> (finish, plan, the pipeline's own outlines)
    "chickadee-fixture": ("spike/tests/fixtures/finishes/chickadee.jpg", "spike/tests/fixtures/plans/chickadee.json",
                          "spike/tests/fixtures/owners/chickadee.png"),
    "sailboat-fixture": ("spike/tests/fixtures/finishes/red-sailboat.jpg", "spike/tests/fixtures/plans/red-sailboat.json",
                         "spike/tests/fixtures/owners/red-sailboat.png"),
    "lavender-fixture": ("spike/tests/fixtures/finishes/lavender-balloon.jpg",
                         "spike/tests/fixtures/plans/lavender-balloon.json",
                         "spike/tests/fixtures/owners/lavender-balloon.png"),
    "chickadee-gate": ("output/chickadee_skill_20261113-041241/99_finish.png",
                       "output/chickadee_skill_20261113-041241/plan.json",
                       "output/chickadee_skill_20261113-041241/parts/owner.png"),
    "sailboat-gate": ("output/red-sailboat_skill_20261113-041240/99_finish.png",
                      "output/red-sailboat_skill_20261113-041240/plan.json",
                      "output/red-sailboat_skill_20261113-041240/parts/owner.png"),
    "lavender-gate": ("output/balloon-lavender_skill_20261113-041226/99_finish.png",
                      "output/balloon-lavender_skill_20261113-041226/plan.json",
                      "output/balloon-lavender_skill_20261113-041226/parts/owner.png"),
}
# The thin and soft parts the issue names, plus each lavender's soft parts, plus one clear-edged part per picture
# (so a swap can't quietly make the easy ones worse).
CASES = {
    "chickadee-fixture": ["branch", "trunks", "bird-feet", "bird"],
    "chickadee-gate": ["branch", "trunks", "bird-feet", "bird"],
    "sailboat-fixture": ["mast", "reflection", "sail"],
    "sailboat-gate": ["mast", "boat-reflection", "sails"],
    "lavender-fixture": ["clouds", "trunk", "tree"],
    "lavender-gate": ["clouds", "paths", "tree"],
}
MEAN, STD = np.array([123.675, 116.28, 103.53], np.float32), np.array([58.395, 57.12, 57.375], np.float32)


def file_for(url: str) -> Path:
    name = url.rsplit("/", 1)[1]
    return (ROOT / "models" / name) if name.startswith("vit_b-") else MODELS / name


def fetch() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    urls = [u for _, e, d in CANDIDATES.values() for u in (e, d)] + list(MATTERS.values())
    for url in urls:
        path = file_for(url)
        if not path.exists():
            print("downloading", url, flush=True)
            urllib.request.urlretrieve(url, path.with_suffix(".part"))
            path.with_suffix(".part").rename(path)
        print(f"{path.stat().st_size / 1e6:7.0f} MB  {hashlib.sha256(path.read_bytes()).hexdigest()[:16]}  {path.name}")


def session(path: Path):
    import onnxruntime as ort
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


class Model:
    """One promptable model. `embed` once per picture; `logits` per prompt: a float map at the picture's size
    (above 0 is the part) and the model's own confidence."""

    def __init__(self, name: str):
        self.name = name
        self.kind, enc, dec = CANDIDATES[name]
        self.paths = file_for(enc), file_for(dec)
        t = time.time()
        self.enc, self.dec = session(self.paths[0]), session(self.paths[1])
        self.load_s = time.time() - t
        self.size_mb = sum(p.stat().st_size for p in self.paths) / 1e6

    def embed(self, rgb: np.ndarray) -> float:
        t = time.time()
        h, w = rgb.shape[:2]
        self.shape = (h, w)
        if self.kind == "sam2":  # SAM 2 squashes the picture to a square; no padding
            x = cv2.resize(rgb, (1024, 1024), interpolation=cv2.INTER_LINEAR).astype(np.float32)
            x = ((x - MEAN) / STD).transpose(2, 0, 1)[None]
            out = self.enc.run(None, {self.enc.get_inputs()[0].name: x})
            self.feats = dict(zip([o.name for o in self.enc.get_outputs()], out))
            self.sx, self.sy = 1024 / w, 1024 / h
        else:
            s = 1024 / max(h, w)
            self.nh, self.nw = int(h * s + 0.5), int(w * s + 0.5)
            self.sx = self.sy = s
            x = cv2.resize(rgb, (self.nw, self.nh), interpolation=cv2.INTER_LINEAR).astype(np.float32)
            if self.kind == "sam-rembg":  # normalized and padded outside the model
                padded = np.zeros((1024, 1024, 3), np.float32)
                padded[:self.nh, :self.nw] = (x - MEAN) / STD
                self.feats = {"image_embeddings": self.enc.run(None, {"x": padded.transpose(2, 0, 1)[None]})[0]}
            else:  # X-AnyLabeling's exports normalize and pad inside
                out = self.enc.run(None, {"input_image": x})
                self.feats = {"image_embeddings": out[0]}
                if self.kind == "hq":
                    self.feats["interm_embeddings"] = np.stack(out[1:], axis=0)
        return time.time() - t

    def logits(self, box=None, points_in=(), points_out=()) -> tuple[np.ndarray, float]:
        h, w = self.shape
        pts = [[x * w, y * h] for x, y in points_in] + [[x * w, y * h] for x, y in points_out]
        labels = [1.0] * len(points_in) + [0.0] * len(points_out)
        if box:
            pts += [[box[0] * w, box[1] * h], [box[2] * w, box[3] * h]]
            labels += [2.0, 3.0]
        elif self.kind != "sam2":
            pts.append([0.0, 0.0])
            labels.append(-1.0)
        coords = (np.array(pts, np.float32) * [self.sx, self.sy]).astype(np.float32)[None]
        feed = {"point_coords": coords, "point_labels": np.array(labels, np.float32)[None],
                "mask_input": np.zeros((1, 1, 256, 256), np.float32), "has_mask_input": np.zeros(1, np.float32)}
        names = [i.name for i in self.dec.get_inputs()]
        if self.kind == "sam2":
            feed.update({k: v for k, v in self.feats.items() if k in names})
            if "orig_im_size" in names:
                kind = next(i.type for i in self.dec.get_inputs() if i.name == "orig_im_size")
                feed["orig_im_size"] = np.array([h, w], np.int64 if "int64" in kind else np.int32 if "int" in kind else np.float32)
            out = dict(zip([o.name for o in self.dec.get_outputs()], self.dec.run(None, feed)))
            masks, iou = out["masks"], out["iou_predictions"].ravel()
            best = int(iou.argmax()) if masks.shape[1] > 1 else 0
            low = masks[0, best]  # a map over the squashed square, whatever size the export gives back
            return cv2.resize(low, (w, h), interpolation=cv2.INTER_LINEAR), float(iou[best])
        feed.update(self.feats)
        feed["orig_im_size"] = np.array([h, w], np.float32)
        out = dict(zip([o.name for o in self.dec.get_outputs()], self.dec.run(None, feed)))
        # low_res_masks covers the padded square at 256 x 256 (outline.Sam.mask says why the full-size one isn't used)
        low = out["low_res_masks"][0, 0]
        up = cv2.resize(low, (1024, 1024), interpolation=cv2.INTER_LINEAR)[:self.nh, :self.nw]
        return cv2.resize(up, (w, h), interpolation=cv2.INTER_LINEAR), float(out["iou_predictions"].ravel()[0])


def matte(sess, rgb: np.ndarray) -> np.ndarray:
    """BiRefNet: the picture squashed to 1024 x 1024, a soft matte (0-1) back at the picture's size."""
    h, w = rgb.shape[:2]
    x = cv2.resize(rgb, (1024, 1024), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    x = ((x - MEAN) / STD).transpose(2, 0, 1)[None]
    y = sess.run(None, {sess.get_inputs()[0].name: x})[-1]
    y = 1 / (1 + np.exp(-y[0, 0]))
    return cv2.resize(y, (w, h), interpolation=cv2.INTER_LINEAR)


def part_box(part: dict) -> list[float]:
    """A box for any part: its own, the bounds of its boxes, or for a thin part its paths' bounds plus its width."""
    if part.get("paths"):
        pts = np.array([p for path in part["paths"] for p in path])
        m = part.get("width", 0.05)
        x0, y0, x1, y1 = pts[:, 0].min() - m, pts[:, 1].min() - m, pts[:, 0].max() + m, pts[:, 1].max() + m
    else:
        b = np.array(ol.boxes_of(part))
        x0, y0, x1, y1 = b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max()
    return [float(max(0, x0)), float(max(0, y0)), float(min(1, x1)), float(min(1, y1))]


def path_points(part: dict, step: float = 0.06) -> list[list[float]]:
    """Points along a thin part's paths, about `step` of the picture apart: what a plan already knows about where
    the part is, as point prompts."""
    out = []
    for path in part.get("paths") or []:
        p = np.array(path, float)
        seg = np.sqrt((np.diff(p, axis=0) ** 2).sum(1))
        total = float(seg.sum())
        for d in np.linspace(0, total, max(2, int(total / step) + 1)):
            i = int(min(np.searchsorted(np.cumsum(seg), d), len(seg) - 1))
            t = (d - (np.cumsum(seg)[i] - seg[i])) / max(seg[i], 1e-9)
            out.append([float(v) for v in p[i] + (p[i + 1] - p[i]) * min(max(t, 0), 1)])
    return out


def recipes(part: dict) -> dict[str, list[dict]]:
    """Ways to prompt a model for one part, from what the plan already has. Each is a list of prompts whose
    outlines are joined."""
    box = part_box(part)
    pin, pout = part.get("points_in") or [], part.get("points_out") or []
    inside = lambda pts, b: [p for p in pts if b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]]  # noqa: E731
    out = {"box": [{"box": box}]}
    if pin:
        out["box+points"] = [{"box": box, "points_in": pin, "points_out": inside(pout, box)}]
        out["points"] = [{"points_in": pin, "points_out": pout}]
    if part.get("paths"):
        along = path_points(part)
        out["path-points"] = [{"points_in": along, "points_out": pout}]
        limbs = []
        for path in part["paths"]:  # one prompt per limb: its own box and the points along it
            one = {"paths": [path], "width": part.get("width", 0.05)}
            b = part_box(one)
            limbs.append({"box": b, "points_in": path_points(one), "points_out": inside(pout, b)})
        out["per-limb"] = limbs
    elif len(ol.boxes_of(part)) > 1:
        out["per-box"] = [{"box": b, "points_in": inside(pin, b), "points_out": inside(pout, b)} for b in ol.boxes_of(part)]
    return out


def color_rule(rgb: np.ndarray, part: dict) -> np.ndarray | None:
    """Where the plan's own colors say the part is (outline.marks with no box): used only to measure."""
    if not (part.get("points_in") or part.get("colors_in")) or not (part.get("points_out") or part.get("colors_out")):
        return None
    L = ol.lab(cv2.GaussianBlur(rgb, (0, 0), 1.2))
    return ol.marks(L, part, np.ones(rgb.shape[:2], bool))


def measure(mask: np.ndarray, own: np.ndarray, rule: np.ndarray | None) -> dict:
    """Numbers to go with the pictures; none of them is a score against a hand-drawn outline (there isn't one).
    share: of the picture. pieces: of at least 0.02% of it. vs_pipeline: overlap (IoU) with the pipeline's outline.
    off_color: how much of the outline has the colors of what's behind (the plan's points_out), by the color rule.
    kept: how much of the pipeline's outline it covers."""
    h, w = mask.shape
    n, _, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    row = {"share": round(float(mask.mean()), 4),
           "pieces": int((st[1:, cv2.CC_STAT_AREA] >= max(4, 0.0002 * h * w)).sum()) if n > 1 else 0,
           "vs_pipeline": round(float((mask & own).sum() / max((mask | own).sum(), 1)), 3),
           "kept": round(float((mask & own).sum() / max(own.sum(), 1)), 3)}
    if rule is not None and mask.any():
        row["off_color"] = round(float((mask & ~rule).sum() / mask.sum()), 3)
    return row


def run(only: list[str] | None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results_path = OUT / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else {"models": {}, "rows": []}
    pictures = {}
    for pic, (finish, plan, owner) in PICTURES.items():
        rgb = cv2.cvtColor(cv2.imread(str(ROOT / finish)), cv2.COLOR_BGR2RGB)
        parts = json.loads((ROOT / plan).read_text())["parts"]
        own = cv2.imread(str(ROOT / owner), cv2.IMREAD_UNCHANGED)
        pictures[pic] = (rgb, {p["id"]: (k, p) for k, p in enumerate(parts)}, own if own.ndim == 2 else own[..., 0])
        for pid in CASES[pic]:  # the pipeline's own outline, for the sheets
            k, part = pictures[pic][1][pid]
            (OUT / pic).mkdir(exist_ok=True)
            cv2.imwrite(str(OUT / pic / f"{pid}__pipeline.png"), (pictures[pic][2] == k).astype(np.uint8) * 255)
    for name in CANDIDATES:
        if only and name not in only:
            continue
        model = Model(name)
        embeds, per_prompt = [], []
        results["rows"] = [r for r in results["rows"] if r["model"] != name]
        for pic, (rgb, parts, own) in pictures.items():
            embeds.append(model.embed(rgb))
            for pid in CASES[pic]:
                k, part = parts[pid]
                rule = color_rule(rgb, part)
                for recipe, prompts in recipes(part).items():
                    t = time.time()
                    soft, conf = np.full(rgb.shape[:2], -1e9, np.float32), []
                    for pr in prompts:
                        lg, c = model.logits(pr.get("box"), pr.get("points_in", ()), pr.get("points_out", ()))
                        soft = np.maximum(soft, lg)
                        conf.append(c)
                    per_prompt.append((time.time() - t) / len(prompts))
                    mask = soft > 0
                    stem = OUT / pic / f"{pid}__{name}__{recipe}"
                    cv2.imwrite(f"{stem}.png", mask.astype(np.uint8) * 255)
                    np.save(f"{stem}.npy", np.clip(soft, -20, 20).astype(np.float16))
                    results["rows"].append({"picture": pic, "part": pid, "kind": part["kind"], "model": name,
                                            "recipe": recipe, "confidence": round(min(conf), 3),
                                            **measure(mask, own == k, rule)})
        again = model.embed(pictures["chickadee-gate"][0])  # warm, on the biggest picture
        lg1, _ = model.logits(part_box(pictures["chickadee-gate"][1]["bird"][1]))
        lg2, _ = model.logits(part_box(pictures["chickadee-gate"][1]["bird"][1]))
        results["models"][name] = {"size_mb": round(model.size_mb), "load_s": round(model.load_s, 1),
                                   "embed_s": round(float(np.median(embeds)), 1), "embed_s_gate": round(again, 1),
                                   "prompt_s": round(float(np.median(per_prompt)), 3),
                                   "same_twice": bool(np.array_equal(lg1, lg2))}
        print(name, results["models"][name], flush=True)
        results_path.write_text(json.dumps(results, indent=1))
        del model
    if not only or any(m in only for m in MATTERS):
        for name, url in MATTERS.items():
            if only and name not in only:
                continue
            path = file_for(url)
            t = time.time()
            sess = session(path)
            load, times = time.time() - t, []
            for pic, (rgb, parts, own) in pictures.items():
                h, w = rgb.shape[:2]
                for pid in CASES[pic]:
                    k, part = parts[pid]
                    x0, y0, x1, y1 = ol.grow(part_box(part), 0.03)
                    crop = rgb[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
                    t = time.time()
                    a = matte(sess, crop)
                    times.append(time.time() - t)
                    full = np.zeros((h, w), np.float32)
                    full[int(y0 * h):int(y0 * h) + a.shape[0], int(x0 * w):int(x0 * w) + a.shape[1]] = a
                    stem = OUT / pic / f"{pid}__{name}__crop"
                    cv2.imwrite(f"{stem}.png", (full * 255).astype(np.uint8))
                    results["rows"] = [r for r in results["rows"] if not (r["model"] == name and r["picture"] == pic and r["part"] == pid)]
                    results["rows"].append({"picture": pic, "part": pid, "kind": part["kind"], "model": name,
                                            "recipe": "crop", "confidence": None,
                                            **measure(full > 0.5, own == k, color_rule(rgb, part))})
            results["models"][name] = {"size_mb": round(path.stat().st_size / 1e6), "load_s": round(load, 1),
                                       "embed_s": round(float(np.median(times)), 1), "prompt_s": None}
            print(name, results["models"][name], flush=True)
            results_path.write_text(json.dumps(results, indent=1))


def tint(rgb: np.ndarray, mask: np.ndarray, color=(255, 0, 200)) -> np.ndarray:
    """The picture dimmed, with the outline's inside tinted and its edge drawn."""
    out = rgb.astype(np.float32) * 0.55  # dim what's outside
    soft = mask.astype(np.float32)
    inside = soft[..., None]
    out = out * (1 - inside) + (rgb.astype(np.float32) * 0.45 + np.array(color, np.float32) * 0.55) * inside
    edge = cv2.morphologyEx((soft > 0.5).astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    out[edge] = 255
    return out.astype(np.uint8)


def label(img: np.ndarray, text: str) -> np.ndarray:
    bar = np.full((34, img.shape[1], 3), 255, np.uint8)
    cv2.putText(bar, text, (6, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    return np.vstack([bar, img])


def load(pic: str, pid: str, stem: str) -> np.ndarray:
    """A saved outline (0-1). "<model>__<recipe>@band" keeps it inside the thin part's band (or a marks part's
    boxes) and drops pieces under 0.05% of the picture, as `outline` would."""
    name, _, clip = stem.partition("@")
    m = cv2.imread(str(OUT / pic / f"{pid}__{name}.png"), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
    if clip:
        part = next(p for p in json.loads((ROOT / PICTURES[pic][1]).read_text())["parts"] if p["id"] == pid)
        inside = ol.band(m.shape, part) if part.get("paths") else ol.box_mask(m.shape, ol.boxes_of(part))
        m = ((m > 0.5) & inside).astype(np.uint8)
        n, lab_, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= ol.SPECK * m.size]
        m = np.isin(lab_, keep).astype(np.float32)
    return m


def sheet(pic: str, pid: str, cells: list[tuple[str, str]], crop: list[float] | None, cols: int, width: int,
          out: str | None = None) -> np.ndarray:
    """One part, one cell per (label, outline file stem under output/spike85/<pic>/)."""
    finish = PICTURES[pic][0]
    rgb = cv2.cvtColor(cv2.imread(str(ROOT / finish)), cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = crop or [0, 0, 1, 1]
    sl = (slice(int(y0 * h), int(y1 * h)), slice(int(x0 * w), int(x1 * w)))
    tiles = []
    for text, stem in cells:
        if stem == "finish":
            img = rgb[sl]
        else:
            m = load(pic, pid, stem).astype(np.float32)
            img = tint(rgb, m)[sl]
        img = cv2.resize(img, (width, int(img.shape[0] * width / img.shape[1])), interpolation=cv2.INTER_AREA)
        tiles.append(label(img, text))
    while len(tiles) % cols:
        tiles.append(np.full_like(tiles[0], 255))
    rows = [np.hstack([np.pad(t, ((0, 0), (0, 6), (0, 0)), constant_values=255) for t in tiles[i:i + cols]])
            for i in range(0, len(tiles), cols)]
    return save(np.vstack(rows), out)


def save(img: np.ndarray, out: str | None) -> np.ndarray:
    if out:
        cv2.imwrite(str(DOCS / out), cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 80])
    return img


def stack(images: list[np.ndarray], out: str) -> None:
    w = max(i.shape[1] for i in images)
    save(np.vstack([np.pad(i, ((0, 8), (0, w - i.shape[1]), (0, 0)), constant_values=255) for i in images]), out)


# The two prompts that worked for a thin part, both kept inside its band:
ONE = "box+points@band"  # one box around all its paths, with the plan's points_in and points_out
THIN = "per-limb@band"  # per limb: a box around that path and points along it


def sheets() -> None:
    """The pictures docs/spikes/outline-models.md shows. Top row of each: the gate run; bottom: the fixture."""
    names = [("SAM ViT-B (today's model)", "sam-b"), ("SAM ViT-L", "sam-l"), ("SAM-HQ ViT-L", "hq-l"),
             ("SAM 2.1 Large", "sam2.1-l")]
    three = names[:3]
    both = [(f"{n.split(' (')[0]}, {text}", f"{m}__{rec}") for n, m in three
            for text, rec in (("one box + points", ONE), ("per limb", THIN))]
    branch = [("the pipeline today (color rule)", "pipeline"), ("ViT-B, one box, no points (the probe)", "sam-b__box")] + both
    stack([sheet(pic, "branch", branch, None, 4, 420) for pic in ("chickadee-gate", "chickadee-fixture")],
          "outline-models-branch.jpg")
    mast = [("finish", "finish"), ("pipeline today", "pipeline")] \
        + [(t.replace("SAM-HQ ViT-L", "HQ-L").replace("SAM ", "").replace("one box + points", "box + points"), f) for t, f in both]
    stack([sheet("sailboat-gate", "mast", mast, [0.66, 0.2, 0.9, 0.66], 8, 230),
           sheet("sailboat-fixture", "mast", mast, [0.7, 0.2, 0.94, 0.66], 8, 230)], "outline-models-mast.jpg")
    trunks = [("finish", "finish"), ("pipeline today", "pipeline")] \
        + [(n.split(" (")[0], f"{m}__box+points") for n, m in names] \
        + [("SAM-HQ ViT-B", "hq-b__box+points"), ("SAM-HQ ViT-H", "hq-h__box+points")]
    stack([sheet("chickadee-gate", "trunks", trunks, [0.72, 0, 1, 1], 8, 230),
           sheet("chickadee-fixture", "trunks", trunks, [0.76, 0, 1, 1], 8, 230)], "outline-models-trunks.jpg")
    feet = [("finish", "finish"), ("pipeline today (color rule)", "pipeline")] + [(n + ", one box", f"{m}__box") for n, m in names]
    stack([sheet("chickadee-gate", "bird-feet", feet, [0.38, 0.5, 0.58, 0.67], 6, 310),
           sheet("chickadee-fixture", "bird-feet", feet, [0.36, 0.5, 0.6, 0.68], 6, 310)], "outline-models-feet.jpg")
    soft = lambda rec: [("finish", "finish"), ("pipeline today (color rule)", "pipeline")] \
        + [(n.split(" (")[0], f"{m}__{rec}") for n, m in names]  # noqa: E731
    stack([sheet("lavender-gate", "clouds", soft("per-box"), [0, 0, 1, 0.45], 6, 310),
           sheet("sailboat-gate", "boat-reflection", soft("box+points"), [0.6, 0.55, 0.95, 1], 6, 310)],
          "outline-models-soft.jpg")
    m = [("BiRefNet (small), no prompt", "birefnet-tiny__crop")]
    tiles = [sheet("chickadee-gate", "branch", [("asked for: the branch", m[0][1])], None, 1, 470),
             sheet("chickadee-gate", "trunks", [("the trunks", m[0][1])], [0.72, 0, 1, 1], 1, 150),
             sheet("sailboat-gate", "mast", [("the mast", m[0][1])], [0.66, 0.2, 0.9, 0.66], 1, 180),
             sheet("chickadee-gate", "bird-feet", [("the feet", m[0][1])], [0.38, 0.5, 0.58, 0.67], 1, 330)]
    h = max(t.shape[0] for t in tiles)
    save(np.hstack([np.pad(t, ((0, h - t.shape[0]), (0, 0), (0, 0)), constant_values=255) for t in tiles]),
         "outline-models-matte.jpg")
    steps = []
    for text, model, rec in [("step 5 today", None, None)] + [(f"{n.split(' (')[0]}, {t}", m, r) for n, m in three
                                                              for t, r in (("one box + points", ONE), ("per limb", THIN))]:
        swaps = {"branch": f"{model}__{rec}", "bird-feet": f"{model}__box"} if model else {}
        pic = rebuilt_step("chickadee-gate", swaps, "branch-dark")
        steps.append(label(cv2.resize(pic, (600, 400), interpolation=cv2.INTER_AREA), text))
    steps.insert(1, np.full_like(steps[0], 255))
    save(np.vstack([np.hstack(steps[i:i + 2]) for i in range(0, 8, 2)]), "outline-models-step5.jpg")


def rebuilt_step(pic: str, swaps: dict[str, str], step_id: str) -> np.ndarray:
    """One step picture of a gate run, built by the real tools (outline.outline, build_steps.build) with some
    parts' outlines swapped for saved ones (`swaps`: part id -> "<model>__<recipe>[@band]"). A swapped part is
    handed to `outline` as a ready-made outline, which it takes only for an object, so its kind is changed for
    this build; nothing else in the plan is."""
    import build_steps as bs
    from filters import load as load_picture

    finish, plan_path, _ = PICTURES[pic]
    lesson = (ROOT / plan_path).parent
    rgb = cv2.cvtColor(cv2.imread(str(ROOT / finish)), cv2.COLOR_BGR2RGB)
    plan = json.loads((ROOT / plan_path).read_text())
    given = {}
    for p in plan["parts"]:
        if p["id"] in swaps:
            given[p["id"]] = load(pic, p["id"], swaps[p["id"]]) > 0.5
            p["kind"] = "object"
    _, owner, _ = ol.outline(rgb, plan["parts"], ol.Sam(), given)
    plate = lesson / "98_background.png"
    pictures, _, _ = bs.build(rgb, plan, owner, load_picture(plate, max_side=100_000) if plate.exists() else None)
    ids = [s["id"] for s in bs.flat_steps(plan)]
    return pictures[ids.index(step_id)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["fetch", "run", "sheets"])
    ap.add_argument("--only")
    a = ap.parse_args()
    if a.what == "fetch":
        fetch()
    elif a.what == "sheets":
        sheets()
    else:
        run(a.only.split(",") if a.only else None)
