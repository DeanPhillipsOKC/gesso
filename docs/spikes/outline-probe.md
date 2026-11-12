# Probe: outlines from a local model, on finishes already on the site

2026-11-12. A one-hour check before writing `docs/design/pipeline-v2.md`, to see whether real outlines fix what the
from-finish spike (`from-finish.md`) got wrong. It is a probe, not the spike: no code landed, no step pictures were built,
and only two finishes were tried. Issue #62 does it properly.

## What was run

- Model: Segment Anything (SAM) ViT-B, quantized ONNX, on CPU with `onnxruntime` (no PyTorch).
  Weights (108 MB together), from the rembg project's releases:
  - `https://github.com/danielgatis/rembg/releases/download/v0.0.0/vit_b-encoder-quant.onnx` (100 MB)
  - `https://github.com/danielgatis/rembg/releases/download/v0.0.0/vit_b-decoder-quant.onnx` (9 MB)
- Input: the finished paintings taken from `site/lessons/lavender-balloon/index.html` and
  `site/lessons/chickadee/index.html` (the last large inline image in each page, 1000 x 786).
- Prompts: one box per part, typed by hand from looking at the picture, the way a plan's `regions` are today.
- Time: about 5 seconds once per picture (the encoder), then about 0.1 second per part.

## What it showed

**Works: things and areas with a clear edge, from one box each.**

![Lavender balloon, one colored outline per part](outline-probe-lavender.jpg)

On the lavender balloon all 7 parts came back clean from one box each, with the model's own confidence between
0.96 and 1.0: sky, sun, far mountains, gold fields (with their tree lines), tree, lavender, balloon. This is the
picture where the from-finish spike failed, because a box could not tell the sky's gold from the field's gold.

**Works: a compact subject.** On the chickadee, the bird, the sun, and 3 of the 4 leaves came back clean from one
box each (confidence 0.96 to 1.0). The fourth leaf (lower left of the pair, confidence 0.89) came back in two
pieces.

![Chickadee: bird, leaves and sun are clean; branch and trunks are not](outline-probe-chickadee.jpg)

**Does not work: thin or soft parts from point prompts.** The branch (thin, runs across the whole picture) took
most of the background with it, and the misty trunks (soft, no real edge) came back as a ragged blob. A box per
limb was no better. These need a different method, and #62 has to find and test it.

**Not tested:** the red sailboat; parts inside parts (the bird's cap); a picture with gray bands around it (what
the image model returns when the canvas shape differs from its frame); any step pictures built from these
outlines. No outline was scored against a hand-drawn one; "clean" is by eye.

**A mistake worth knowing about.** The first version of this probe used the decoder's full-size `masks` output and
every outline came back stretched downward (the sun's outline sat below the sun). That output assumes a square
picture. The code below uses `low_res_masks` and undoes the padding itself. Anyone starting from other SAM ONNX
exports should check an outline against a small round thing first.

## The probe's code

Kept here so #62 can start from it. `box` is `[x0, y0, x1, y1]` as shares of the width and height.

```python
import numpy as np, cv2, onnxruntime as ort
enc = ort.InferenceSession("vit_b-encoder-quant.onnx")
dec = ort.InferenceSession("vit_b-decoder-quant.onnx")

def embed(rgb):                                   # once per picture, about 5 s on CPU
    h, w = rgb.shape[:2]; s = 1024 / max(h, w); nh, nw = int(h * s + .5), int(w * s + .5)
    x = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    x = (x - [123.675, 116.28, 103.53]) / [58.395, 57.12, 57.375]
    p = np.zeros((1024, 1024, 3), np.float32); p[:nh, :nw] = x
    return enc.run(None, {"x": p.transpose(2, 0, 1)[None]})[0], s

def mask(emb, s, shape, box=None, pos=(), neg=()):  # about 0.1 s per part
    h, w = shape; pts, lab = [], []
    for x, y in pos: pts.append([x * w, y * h]); lab.append(1)
    for x, y in neg: pts.append([x * w, y * h]); lab.append(0)
    if box: pts += [[box[0] * w, box[1] * h], [box[2] * w, box[3] * h]]; lab += [2, 3]
    else: pts.append([0, 0]); lab.append(-1)
    m, iou, low = dec.run(None, {
        "image_embeddings": emb,
        "point_coords": (np.array(pts, np.float32) * s)[None],
        "point_labels": np.array(lab, np.float32)[None],
        "mask_input": np.zeros((1, 1, 256, 256), np.float32),
        "has_mask_input": np.zeros(1, np.float32),
        "orig_im_size": np.array([h, w], np.float32)})
    # `low` is 256 x 256 over the padded 1024 square: enlarge, cut the padding off, then back to the picture's size.
    # (The decoder's full-size `masks` output skips the padding step and comes back stretched for non-square pictures.)
    nh, nw = int(h * s + .5), int(w * s + .5)
    up = cv2.resize(low[0, 0], (1024, 1024), interpolation=cv2.INTER_LINEAR)[:nh, :nw]
    return cv2.resize(up, (w, h), interpolation=cv2.INTER_LINEAR) > 0, float(iou.ravel()[0])  # outline, confidence
```

The lavender boxes: sky `[0, 0, 1, 0.47]`, mountains `[0, 0.36, 1, 0.54]`, fields `[0, 0.44, 1, 0.64]`, lavender
`[0, 0.6, 1, 1]`, sun `[0.34, 0.37, 0.41, 0.45]`, tree `[0.73, 0.21, 1, 0.49]`, balloon `[0.1, 0.03, 0.3, 0.34]`.
The chickadee boxes: bird `[0.12, 0.08, 0.63, 0.78]`, leaves `[0.12, 0, 0.36, 0.2]`, `[0.06, 0.1, 0.25, 0.46]`,
`[0.46, 0.78, 0.69, 1]`, `[0.62, 0.84, 0.82, 1]`, sun `[0.62, 0.07, 0.73, 0.2]`.

## What it means

- Outlines from boxes are good enough to build on for objects and clear-edged areas, and they cost nothing per run.
- The same boxes give the same outlines every time, so step pictures stop varying between runs.
- Thin and soft parts are the open risk. #62 decides how they're handled before anything is removed.
