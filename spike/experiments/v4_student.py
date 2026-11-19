"""Spike for #174 (v4's yardstick, Y1): the student test. A reader gets a step's before picture and its words, and no
after picture, and has to get to the after picture.

Two forms, on the three v3 lessons frozen in `spike/experiments/bench/v3-words/` (the baseline):

- **pick**: a reader in a fresh context (Claude, one call through `claude -p`, no tools) gets the before picture,
  the step's words and four pictures, and says how likely each is to be the after picture. One is the real after;
  three are near misses made from the real pictures (`candidates`): the step's change put in the wrong place
  (mirrored), only half of the change, and the next step's change in its place. All four are made the same way (the
  before picture with a change laid in through a soft mask), so a seam can't give the real one away.
- **carry**: the image model carries the step's words out on the before picture (one low-quality edit), and the
  result is compared with the real after: by a measure (`measure`: how much of the way from the before to the after
  the result got, on blurred colour) and by a grader who sees the before, the real after and the step's results,
  unlabelled, and never the words.

Each form runs on the words as they are, on the step's header alone (name, paints, brush: the floor), and on three
kinds of worsened words for a subset of steps (`worsen`): the place taken out, every side swapped, the strokes'
direction taken out. A test that the header alone passes, or that doesn't fall on worsened words, is no test.

Blind graders (`graders`) grade each lesson the old way, with the after pictures in front of them, by the owner's
rubric (`bench/ab_grader.md`, one lesson instead of a pair), and add a 1 to 5 `paintable` for every step. The
student's scores are checked against their `worst_steps`.

    .venv/bin/python spike/experiments/v4_student.py prepare
    .venv/bin/python spike/experiments/v4_student.py worsen
    .venv/bin/python spike/experiments/v4_student.py pick --condition words [--rep 2] [--subset] [--picture P] [--steps 1,2]
    .venv/bin/python spike/experiments/v4_student.py carry --condition words [--subset]
    .venv/bin/python spike/experiments/v4_student.py grade-carry
    .venv/bin/python spike/experiments/v4_student.py graders
    .venv/bin/python spike/experiments/v4_student.py report

Pictures and readers' folders go in a work folder outside the repository (`--work`, by default
`<temp>/gesso-v4-student`); every answer, measure and call's tokens go in `spike/experiments/v4_student.json`.
Experiment code: it reads the frozen bench and changes no tool.

A words spike scores its own words the same way (#254): `--words-from <folder>` reads each step's lines and tip
from `<folder>/<picture>/packet.json` (the bench packet's shape; the header, pictures and near misses stay the
bench's), and `--results <file>` keeps its answers apart from v3's. Its carry results go in `<work>/carry-<file's
stem>`, and its near misses are the ones `prepare` made for v3 (read from `v4_student.json`).

    .venv/bin/python spike/experiments/v4_student.py --words-from <folder> --results <file> carry --condition words
"""
from __future__ import annotations

import argparse
import json
import random
import re
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

BENCH = HERE / "bench" / "v3-words"
PICTURES = ["highland-cow", "sleeping-cat", "birch-grove"]
RESULTS = HERE / "v4_student.json"
BASE_RESULTS = RESULTS  # v3's: where `prepare` keeps the near misses
WORDS_FROM: Path | None = None  # another lesson's words (`--words-from`): <folder>/<picture>/packet.json
WORK = Path(tempfile.gettempdir()) / "gesso-v4-student"
SEED = 174
BLANK = (246, 246, 246)  # the packet's blank canvas (packet.py's pair for step 1)
READ_SIDE = 640  # the reader's pictures, long side
GRADE_SIDE = 640
MASK_SIDE = 240  # where a step's change is found
CHANGE_DE = 5.0  # a pixel changed if its blurred colour moved this far (CIE76)
SUBSET = 8  # steps a lesson that get worsened words
CONDITIONS = ["words", "header", "no_place", "wrong_side", "no_direction"]
WORSE = ["no_place", "wrong_side", "no_direction"]
KINDS = ["real", "place", "half", "other"]  # the four pictures of pick
RENDER_QUALITY = "low"
BUDGET = 5.0  # the owner's render budget for this spike (#174, 2026-11-18); `carry` stops before going past it
LOCK = threading.Lock()


# ------------------------------------------------------------------------------------------------------- the lessons
def lesson(picture: str) -> dict:
    return json.loads((BENCH / picture / "packet.json").read_text())


def step_of(picture: str, n: int) -> dict:
    """A step as the bench packet has it, with its lines and tip from `WORDS_FROM` when that is set."""
    s = next(s for s in lesson(picture)["steps"] if s["n"] == n)
    if WORDS_FROM is None:
        return s
    other = json.loads((WORDS_FROM / picture / "packet.json").read_text())
    w = next(x for x in other["steps"] if x["n"] == n)
    return {**s, "lines": w["lines"], "tip": w.get("tip") or "", "intro": w.get("intro") or ""}


def carry_dir() -> Path:
    """Where carry's results go: `<work>/carry`, or `<work>/carry-<results stem>` for another lesson's words."""
    return WORK / ("carry" if RESULTS == BASE_RESULTS else f"carry-{RESULTS.stem}")


def load(path: Path):
    from PIL import Image
    return Image.open(path).convert("RGB")


def before_after(picture: str, n: int):
    """The canvas before step n (a blank canvas for step 1) and after it, the same size."""
    from PIL import Image
    after = load(BENCH / picture / "steps" / f"{n:02d}.jpg")
    before = load(BENCH / picture / "steps" / f"{n - 1:02d}.jpg") if n > 1 else Image.new("RGB", after.size, BLANK)
    return before, after


# ------------------------------------------------------------------------------------------------- where a step changed
def lab(img, side: int = MASK_SIDE, blur: float = 1.5) -> np.ndarray:
    """A picture as blurred CIE Lab, `side` pixels on the long side."""
    import cv2
    a = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    k = side / max(a.shape[:2])
    a = cv2.resize(a, (max(1, round(a.shape[1] * k)), max(1, round(a.shape[0] * k))), interpolation=cv2.INTER_AREA)
    if blur:
        a = cv2.GaussianBlur(a, (0, 0), blur)
    return cv2.cvtColor(a, cv2.COLOR_RGB2LAB)


def change_mask(before, after, side: int = MASK_SIDE) -> np.ndarray:
    """Where the step changed the canvas, as 0/1 at `side` pixels, small specks and holes cleaned up."""
    return clean(np.linalg.norm(lab(after, side) - lab(before, side), axis=2))


def clean(d: np.ndarray) -> np.ndarray:
    """Pixels whose colour moved more than CHANGE_DE, small specks and holes cleaned up."""
    import cv2
    m = (d > CHANGE_DE).astype(np.uint8)
    k = np.ones((3, 3), np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k, iterations=2)
    return m.astype(np.float32)


def soft(mask: np.ndarray, size: tuple[int, int], feather: float = 3.0) -> np.ndarray:
    """A small 0/1 mask brought up to a picture's size (w, h) with a soft edge, as h x w x 1."""
    import cv2
    m = cv2.resize(mask.astype(np.float32), size, interpolation=cv2.INTER_LINEAR)
    m = cv2.GaussianBlur(m, (0, 0), feather * size[0] / 600)
    return np.clip(m, 0, 1)[..., None]


def lay(base, top, mask: np.ndarray):
    """`top` laid over `base` through a small mask."""
    from PIL import Image
    b = np.asarray(base, dtype=np.float32)
    t = np.asarray(top.resize(base.size), dtype=np.float32)
    m = soft(mask, base.size)
    return Image.fromarray(np.clip(b * (1 - m) + t * m, 0, 255).astype(np.uint8))


def iou(a: np.ndarray, b: np.ndarray) -> float:
    u = np.logical_or(a > 0.5, b > 0.5).sum()
    return float(np.logical_and(a > 0.5, b > 0.5).sum() / u) if u else 1.0


def half_of(mask: np.ndarray, rng: random.Random) -> np.ndarray:
    """One half of a change, split across its longer side at its middle."""
    ys, xs = np.nonzero(mask > 0.5)
    out = np.zeros_like(mask)
    if len(xs) == 0:
        return out
    if xs.max() - xs.min() >= ys.max() - ys.min():
        cut = np.median(xs)
        keep = (np.arange(mask.shape[1])[None, :] < cut) if rng.random() < 0.5 else (np.arange(mask.shape[1])[None, :] >= cut)
        keep = np.broadcast_to(keep, mask.shape)
    else:
        cut = np.median(ys)
        keep = (np.arange(mask.shape[0])[:, None] < cut) if rng.random() < 0.5 else (np.arange(mask.shape[0])[:, None] >= cut)
        keep = np.broadcast_to(keep, mask.shape)
    out[keep] = mask[keep]
    return out


def moved(before, after, mask: np.ndarray):
    """The step's change somewhere else: mirrored side to side, or top to bottom when the side-to-side mirror
    looks too much like the real thing (a change that is nearly symmetric, or covers the canvas), or rolled half the
    canvas when both do. Returns the moved picture, its mask and how it was moved."""
    from PIL import Image, ImageOps
    real = lab(lay(before, after, mask))
    d_real = float(np.linalg.norm(real - lab(before), axis=2).mean())

    def far(top, mm):  # the moved change differs from the real one by at least half of what the step changed
        return float(np.linalg.norm(lab(lay(before, top, mm)) - real, axis=2).mean()) >= 0.5 * d_real

    tries = [(ImageOps.mirror(after), mask[:, ::-1].copy(), "mirrored side to side"),
             (ImageOps.flip(after), mask[::-1, :].copy(), "mirrored top to bottom")]
    for top, mm, how in tries:
        if far(top, mm):
            return top, mm, how
    a = np.asarray(after)
    return (Image.fromarray(np.roll(a, a.shape[1] // 2, axis=1)), np.roll(mask, mask.shape[1] // 2, axis=1),
            "rolled half the canvas sideways")


def candidates(picture: str, n: int, count: int) -> tuple[dict, dict]:
    """The four pictures of pick for step n: the real after and three near misses, each the before picture with a
    change laid in through the same soft mask. Returns {kind: picture} and what was made."""
    rng = random.Random(f"{picture}-{n}-{SEED}")
    before, after = before_after(picture, n)
    m = change_mask(before, after)
    out = {"real": lay(before, after, m)}
    top, mm, how = moved(before, after, m)
    out["place"] = lay(before, top, mm)
    out["half"] = lay(before, after, half_of(m, rng))
    o = n + 1 if n < count else n - 1  # the next step's change instead (the step before's, for the last)
    ob, oa = before_after(picture, o)
    om = change_mask(ob, oa)
    out["other"] = lay(before, oa, om)
    info = {"area": round(float(m.mean()), 4), "place": how, "other_step": o,
            "place_iou": round(iou(m, mm), 3), "other_iou": round(iou(m, om), 3)}
    return out, info


# ------------------------------------------------------------------------------------------------------- the words
SIDES = {"left": "right", "right": "left", "top": "bottom", "bottom": "top", "upper": "lower", "lower": "upper",
         "above": "below", "below": "above", "leftmost": "rightmost", "rightmost": "leftmost",
         "topmost": "bottommost", "bottommost": "topmost"}
SIDE_RE = re.compile(r"\b(" + "|".join(sorted(SIDES, key=len, reverse=True)) + r")\b", re.I)


def swap_sides(text: str) -> str:
    """Every side named the other way round: left for right, top for bottom, upper for lower, above for below."""
    def one(m):
        w = m.group(0)
        s = SIDES[w.lower()]
        return s.capitalize() if w[0].isupper() else s
    return SIDE_RE.sub(one, text)


def has_sides(s: dict) -> bool:
    return bool(SIDE_RE.search(" ".join(s["lines"]) + " " + (s.get("tip") or "")))


def step_text(s: dict, canvas_in, count: int, words: dict | None = None, header_only: bool = False) -> str:
    """A step as the lesson page gives it, less its picture. `words` replaces its lines and tip. A step's `intro`
    (a words spike's stage opener, #255) is said above the step, as the page shows it at the top of the stage."""
    w = words or {"lines": s["lines"], "tip": s.get("tip") or ""}
    out = [f"The canvas is {canvas_in[0]:g} in wide and {canvas_in[1]:g} in tall. This is step {s['n']} of {count}.",
           ""]
    if s.get("intro"):
        out += [s["intro"], ""]
    out.append(f"Step {s['n']}: {s['name']}")
    if s.get("group"):
        out.append(f"Part of: {s['group']}")
    if s.get("paints"):
        out.append("Paints:")
        out += [f"- {p['name']} ({p['hex']}): {p['recipe']}" for p in s["paints"]]
    if s.get("brushes"):
        out.append(f"Brush: {s['brushes']}")
    if not header_only:
        out.append("Words:")
        out += [f"{i}. {line}" for i, line in enumerate(w["lines"], 1)]
        if w.get("tip"):
            out.append(f"Tip: {w['tip']}")
    return "\n".join(out)


def subset(picture: str) -> list[int]:
    """The steps a lesson's words are worsened on: up to SUBSET steps that name a side and change a visible part of
    the canvas, spread evenly through the lesson."""
    les = lesson(picture)
    ok = [s["n"] for s in les["steps"] if has_sides(s)]
    area = state()["prepared"].get(picture, {})
    ok = [n for n in ok if area.get(str(n), {}).get("area", 1) >= 0.005] or ok
    if len(ok) <= SUBSET:
        return ok
    idx = np.linspace(0, len(ok) - 1, SUBSET).round().astype(int)
    return [ok[i] for i in sorted(set(idx))]


def words_for(picture: str, n: int, condition: str) -> tuple[dict | None, bool]:
    """(the words to use, header only) for a condition."""
    s = step_of(picture, n)
    if condition == "words":
        return None, False
    if condition == "header":
        return None, True
    if condition == "wrong_side":
        return {"lines": [swap_sides(x) for x in s["lines"]], "tip": swap_sides(s.get("tip") or "")}, False
    w = state()["worsened"].get(picture, {}).get(condition, {}).get(str(n))
    if not w:
        raise SystemExit(f"no {condition} words for {picture} step {n}: run `worsen` first")
    return w, False


WORSEN_BRIEF = {
    "no_place": (
        "Take out WHERE on the canvas the paint goes, and nothing else. Delete every measurement of place (inches "
        "from an edge, the size of the area), every 'inside the outlined area', and every word or phrase that says "
        "which part of the canvas or of the subject the paint lands on or stays off (the left side, under the belly, "
        "along the top of the back, between the trunks, near the window). Keep what to paint, the paints, the "
        "brush, the load, how to make the stroke and which way it runs, drying, what it should look like and the "
        "watch-outs. Where a sentence was only about place, drop it. Where it mixed place with something else, keep "
        "the something else in plain words."),
    "no_direction": (
        "Take out WHICH WAY the strokes run, and nothing else. Delete every direction or path of a stroke (side to "
        "side, top to bottom, downward, in the direction the fur grows, along the curve, bend with the shape, from "
        "the top of each bump down, outward from the centre, back and forth, pull toward, diagonal). Keep where on "
        "the canvas the paint goes, the paints, the brush, the load, what kind of mark it is (tap, dab, stroke, "
        "glaze), drying, what it should look like and the watch-outs. Where a sentence was only about direction, "
        "drop it. Where it mixed direction with something else, keep the something else in plain words."),
}


# ---------------------------------------------------------------------------------------------------- the results file
_STATE: dict | None = None


def state() -> dict:
    global _STATE
    if _STATE is None:
        _STATE = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
        for k in ("prepared", "worsened"):
            _STATE.setdefault(k, {})
        for k in ("pick", "carry", "carry_grades", "graders", "calls"):
            _STATE.setdefault(k, [])
        if not _STATE["prepared"] and RESULTS != BASE_RESULTS and BASE_RESULTS.exists():
            _STATE["prepared"] = json.loads(BASE_RESULTS.read_text())["prepared"]  # the same near misses as v3's
    return _STATE


_NEW: dict = {}  # records this process added and hasn't written yet


def save():
    """Write the results file, merged with what is on disk under a file lock, so several commands (pick, carry,
    graders) can run at once: lists get this process's new records appended, `prepared` and `worsened` are merged."""
    import fcntl
    global _STATE
    with LOCK:
        st = state()
        WORK.mkdir(parents=True, exist_ok=True)
        with open(WORK / "results.lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            disk = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
            for k, v in st.items():
                if isinstance(v, list):
                    disk[k] = disk.get(k, []) + _NEW.get(k, [])
                elif isinstance(v, dict) and k in ("prepared", "worsened"):
                    merged = disk.setdefault(k, {})
                    for pic, d in v.items():
                        for kk, vv in d.items():
                            if isinstance(vv, dict) and isinstance(merged.setdefault(pic, {}).get(kk), dict):
                                merged[pic][kk].update(vv)
                            else:
                                merged[pic][kk] = vv
                else:
                    disk[k] = v
            tmp = RESULTS.with_suffix(".json.tmp")  # written whole, then moved: a full disk can't cut the file short
            tmp.write_text(json.dumps(disk, indent=1) + "\n")
            tmp.replace(RESULTS)
        _NEW.clear()
        _STATE = disk


def add(key: str, rec: dict):
    with LOCK:
        state()[key].append(rec)
        _NEW.setdefault(key, []).append(rec)
    save()


# ------------------------------------------------------------------------------------------------------- Claude
def ask(blocks: list[dict], system: str, label: str, cwd: Path) -> dict:
    """One fresh call to Claude (`v4_loop.call_claude`: `claude -p`, Opus, no tools); its tokens go in `calls`."""
    from v4_loop import call_claude, cost, last_json
    r = call_claude(blocks, system, cwd=cwd)
    u = r["usage"]
    rec = {"label": label, "seconds": r["seconds"], "input_tokens": u.get("input_tokens", 0),
           "cache_write_tokens": u.get("cache_creation_input_tokens", 0),
           "cache_read_tokens": u.get("cache_read_input_tokens", 0), "output_tokens": u.get("output_tokens", 0),
           "cost_usd": round(cost(u), 5)}
    add("calls", rec)
    try:
        answer = last_json(r["text"])
    except ValueError:
        answer = None
    return {"answer": answer, "text": r["text"], "cost_usd": rec["cost_usd"], "seconds": r["seconds"]}


def picture_block(img, side: int) -> list[dict]:
    import base64
    import io
    im = img.copy()
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(buf.getvalue()).decode()}}]


def text_block(s: str) -> list[dict]:
    return [{"type": "text", "text": s}]


def cwd() -> Path:
    d = WORK / "cwd"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------------------------------------- prepare
def prepare(args):
    st = state()
    for pic in PICTURES:
        les = lesson(pic)
        count = len(les["steps"])
        st["prepared"].setdefault(pic, {})
        for s in les["steps"]:
            n = s["n"]
            cands, info = candidates(pic, n, count)
            order = KINDS[:]
            random.Random(f"order-{pic}-{n}-{SEED}").shuffle(order)
            info["order"] = order  # picture 1 is order[0], and so on; the same for every condition
            d = WORK / "pick" / pic / f"{n:02d}"
            d.mkdir(parents=True, exist_ok=True)
            for i, kind in enumerate(order, 1):
                cands[kind].save(d / f"{i}.jpg", quality=90)
            before_after(pic, n)[0].save(d / "before.jpg", quality=90)
            st["prepared"][pic][str(n)] = info
            print(f"{pic} {n:2d}: area {info['area']:.3f}, {info['place']}, other step {info['other_step']}")
    save()


def sheet(args):
    """A contact sheet of one step's four pictures, for the write-up."""
    from PIL import Image, ImageDraw
    d = WORK / "pick" / args.picture / f"{args.step:02d}"
    info = state()["prepared"][args.picture][str(args.step)]
    ims = [load(d / "before.jpg")] + [load(d / f"{i}.jpg") for i in range(1, 5)]
    labels = ["before"] + [{"real": "real after", "place": "moved", "half": "half", "other": "next step's"}[k]
                           for k in info["order"]]
    w = 360
    h = round(ims[0].height * w / ims[0].width)
    out = Image.new("RGB", (5 * w + 4 * 8, h + 26), "white")
    dr = ImageDraw.Draw(out)
    for i, (im, lb) in enumerate(zip(ims, labels)):
        out.paste(im.resize((w, h)), (i * (w + 8), 26))
        dr.text((i * (w + 8) + 4, 6), lb, fill=(0, 0, 0))
    out.save(args.out, quality=85)
    print(args.out)


# ----------------------------------------------------------------------------------------------------------- worsen
def worsen(args):
    st = state()
    for pic in PICTURES:
        les = lesson(pic)
        steps = {s["n"]: s for s in les["steps"]}
        for kind, brief in WORSEN_BRIEF.items():
            have = st["worsened"].setdefault(pic, {}).setdefault(kind, {})
            todo = [n for n in subset(pic) if str(n) not in have]
            if not todo:
                continue
            payload = [{"n": n, "lines": steps[n]["lines"], "tip": steps[n].get("tip") or ""} for n in todo]
            system = ("You edit painting-lesson steps for an experiment that checks whether a test notices worse "
                      "instructions. Do exactly the one edit asked, and change no other word.")
            msg = (brief + "\n\nThe steps, as JSON:\n```json\n" + json.dumps(payload, indent=1) + "\n```\n\nReply with "
                   "the same JSON, every step and key kept (`n`, `lines`, `tip`), one ```json block and nothing else. A "
                   "line left empty is dropped.")
            r = ask(text_block(msg), system, f"worsen {kind} {pic}", cwd())
            ans = r["answer"] or []
            for a in ans:
                if a.get("n") in todo:
                    have[str(a["n"])] = {"lines": [x for x in a.get("lines") or [] if str(x).strip()],
                                         "tip": a.get("tip") or ""}
            print(f"{pic} {kind}: {len(ans)} steps, ${r['cost_usd']:.3f}")
            save()


# ------------------------------------------------------------------------------------------------------------- pick
PICK_SYSTEM = (
    "You are a student painter taking a test. You get a painting in progress, the next step of a painting lesson "
    "as its page gives it (the step's own picture is left out), and four pictures of the canvas after that step. One "
    "is what a painter who followed the step got. The other three are near misses. Judge only from what the step's "
    "words tell you to do. You have no tools.")


def pick_one(pic: str, n: int, condition: str, rep: int):
    st = state()
    les = lesson(pic)
    s = step_of(pic, n)
    words, header = words_for(pic, n, condition)
    info = st["prepared"][pic][str(n)]
    d = WORK / "pick" / pic / f"{n:02d}"
    blocks = text_block("The canvas before this step:") + picture_block(load(d / "before.jpg"), READ_SIDE)
    blocks += text_block("The step:\n\n" + step_text(s, les["canvas_in"], len(les["steps"]), words, header))
    for i in range(1, 5):
        blocks += text_block(f"Picture {i}:") + picture_block(load(d / f"{i}.jpg"), READ_SIDE)
    blocks += text_block(
        "Which picture is the canvas after a painter did this step? Give each of the four a chance in percent, adding "
        "to 100, and say in one sentence what in the step's words decided it. Reply with one ```json block: "
        '{"chances": {"1": 0, "2": 0, "3": 0, "4": 0}, "why": "..."}')
    r = ask(blocks, PICK_SYSTEM, f"pick {condition} {pic} {n} r{rep}", cwd())
    a = r["answer"] or {}
    ch = {str(k): float(v) for k, v in (a.get("chances") or {}).items() if str(k) in "1234"}
    total = sum(ch.values()) or 1.0
    probs = {info["order"][int(k) - 1]: round(v / total, 3) for k, v in ch.items()}
    top = max(probs, key=probs.get) if probs else None
    add("pick", {"picture": pic, "n": n, "condition": condition, "rep": rep, "p_real": probs.get("real", 0.0),
                 "probs": probs, "pick": top, "hit": top == "real", "why": a.get("why", r["text"][-300:]),
                 "cost_usd": r["cost_usd"], "seconds": r["seconds"]})
    print(f"pick {condition} {pic} {n:2d} r{rep}: p(real) {probs.get('real', 0):.2f}, picked {top}")


def targets(args) -> list[tuple[str, int]]:
    out = []
    for pic in ([args.picture] if args.picture else PICTURES):
        ns = [s["n"] for s in lesson(pic)["steps"]]
        if args.subset or args.condition in WORSE:
            ns = subset(pic)
        if args.steps:
            want = {int(x) for x in args.steps.split(",")}
            ns = [n for n in ns if n in want]
        out += [(pic, n) for n in ns]
    return out


def run_pool(fn, jobs: list, workers: int):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in [ex.submit(fn, *j) for j in jobs]:
            try:
                f.result()
            except Exception as e:  # one failed call doesn't stop the batch; it is run again next time
                print(f"  failed: {e}", file=sys.stderr)


def pick(args):
    done = {(r["picture"], r["n"], r["condition"], r["rep"]) for r in state()["pick"]}
    jobs = [(p, n, args.condition, args.rep) for p, n in targets(args) if (p, n, args.condition, args.rep) not in done]
    print(f"{len(jobs)} readers")
    run_pool(pick_one, jobs, args.workers)


# ------------------------------------------------------------------------------------------------------------ carry
def carry_prompt(s: dict, canvas_in, count: int, words, header) -> str:
    return ("This is a photo of an acrylic painting in progress on a canvas. A beginner now does the next step of a "
            "painting lesson, exactly as its words say and nothing more. Paint onto this same canvas what the step "
            "asks for, in the paints it names, where it says, with the strokes it describes. Keep everything else "
            "exactly as it is: the same framing, the same painted areas, the same bare canvas. Don't finish the "
            "painting or add anything the step doesn't ask for.\n\n"
            + step_text(s, canvas_in, count, words, header))


MEASURE_SIDE = 96


def fit_colour(r: np.ndarray, b: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """The result's colours mapped onto the before picture's where nothing was meant to change: a scale and an
    offset for each Lab channel (least squares, the scale held to 0.8 to 1.25). The image model shifts the whole
    picture's colour a little, and that shift would swamp a small step."""
    if keep.sum() < 50:
        return r
    out = r.copy()
    for c in range(3):
        x, y = r[..., c][keep], b[..., c][keep]
        vx = float(x.var())
        k = float(np.clip(((x - x.mean()) * (y - y.mean())).mean() / vx, 0.8, 1.25)) if vx > 1e-6 else 1.0
        out[..., c] = (r[..., c] - x.mean()) * k + y.mean()
    return out


def measure(before, after, result, misses: dict | None = None) -> dict:
    """The result against the real after, on blurred colour, after `fit_colour`.

    `beats`: of the before picture and pick's three near misses, the share the result is nearer to the real after
    than to (1: nearer the real after than to any of them; the same yardstick as pick, and blind to the shift
    every render has). `toward`: how far it got from the before picture to the after (1 is the after, 0 no nearer
    than not painting, floored at -1). `where`: the overlap of where the result changed the canvas with where the
    real step did."""
    s = MEASURE_SIDE
    b, a = lab(before, s, 2.0), lab(after, s, 2.0)
    res = result.resize(after.size)
    m = change_mask(before, after, s)
    others = {"before": before, **(misses or {})}
    keep = m < 0.5
    for o in others.values():
        keep &= change_mask(before, o, s) < 0.5
    r = fit_colour(lab(res, s, 2.0), b, keep)
    d = lambda x, y: float(np.linalg.norm(x - y, axis=2).mean())  # noqa: E731
    d_ba, d_ra = d(b, a), d(r, a)
    nearer = [d_ra < d(r, lab(o, s, 2.0)) for o in others.values()]
    return {"beats": round(sum(nearer) / len(nearer), 3),
            "toward": round(max(-1.0, 1 - d_ra / d_ba), 3) if d_ba > 0 else 0.0,
            "where": round(iou(m, clean(np.linalg.norm(r - b, axis=2))), 3),
            "d_before_after": round(d_ba, 2), "d_result_after": round(d_ra, 2)}


def carry_one(pic: str, n: int, condition: str, rep: int):
    from run import Ledger, edit_image
    les = lesson(pic)
    s = step_of(pic, n)
    words, header = words_for(pic, n, condition)
    before, after = before_after(pic, n)
    d = carry_dir() / pic
    d.mkdir(parents=True, exist_ok=True)
    src = d / f"{n:02d}-before.png"
    before.save(src)
    out = d / f"{n:02d}-{condition}-r{rep}.png"
    w, h = les["canvas_in"]
    size = "1536x1024" if w > h else "1024x1536" if h > w else "1024x1024"
    with LOCK:
        spent = sum(r["render_usd"] for r in state()["carry"])
    if spent > BUDGET:
        raise RuntimeError(f"render spend ${spent:.2f} is past ${BUDGET:.2f}: ask the owner first")
    ledger = Ledger()
    t0 = time.time()
    edit_image(f"{pic}-{n}-{condition}", [src], carry_prompt(s, les["canvas_in"], len(les["steps"]), words, header),
               out, size, RENDER_QUALITY, ledger)
    pd = WORK / "pick" / pic / f"{n:02d}"
    order = state()["prepared"][pic][str(n)]["order"]
    cands = {k: load(pd / f"{i}.jpg") for i, k in enumerate(order, 1)}
    real = cands.pop("real")
    m = measure(before, real, load(out), cands)
    add("carry", {"picture": pic, "n": n, "condition": condition, "rep": rep, "file": out.name, **m,
                  "render_usd": ledger.total_cost, "seconds": round(time.time() - t0, 1)})
    print(f"carry {condition} {pic} {n:2d}: beats {m['beats']:.2f}, toward {m['toward']:.2f}, where {m['where']:.2f}, "
          f"${ledger.total_cost:.3f}")


def carry(args):
    done = {(r["picture"], r["n"], r["condition"], r["rep"]) for r in state()["carry"]}
    jobs = [(p, n, args.condition, args.rep) for p, n in targets(args) if (p, n, args.condition, args.rep) not in done]
    global BUDGET
    BUDGET = args.budget
    spent = sum(r["render_usd"] for r in state()["carry"])
    print(f"{len(jobs)} renders; ${spent:.2f} spent so far")
    run_pool(carry_one, jobs, args.workers)


CARRY_GRADE_SYSTEM = (
    "You grade an experiment. A painter did one step of a painting lesson several times. You see the canvas before "
    "the step, the canvas after the step as the lesson's own picture shows it, and the painters' results, in no "
    "order. You don't see the lesson's words. You have no tools.")


def grade_carry_one(pic: str, n: int, solo: tuple | None = None):
    """Grade a step's results in one call, or with `solo` (condition, rep) that one result alone (`grade-carry
    --solo`: a result graded beside worse ones scores higher than graded alone, so a baseline is graded alone)."""
    rows = [r for r in state()["carry"] if r["picture"] == pic and r["n"] == n
            and (solo is None or (r["condition"], r["rep"]) == tuple(solo))]
    rng = random.Random(f"grade-{pic}-{n}-{SEED}")
    rng.shuffle(rows)
    before, after = before_after(pic, n)
    blocks = (text_block("Before the step:") + picture_block(before, GRADE_SIDE)
              + text_block("After the step, the lesson's own picture:") + picture_block(after, GRADE_SIDE))
    for i, r in enumerate(rows, 1):
        blocks += text_block(f"Result {i}:") + picture_block(load(carry_dir() / pic / r["file"]), GRADE_SIDE)
    blocks += text_block(
        "For each result, score 1 to 5 how close it comes to doing this step the way the lesson's picture shows it: "
        "the same things painted, in the same places, about the same colours and amount, with the step's kind of "
        "marks. 5: a painter would say it's the same step done well. 3: the right thing, but clearly off in place, "
        "amount or colour. 1: a different step, or nothing like it. Don't mark a result down for the photo's light, "
        "a slightly different crop or brushwork that differs only in detail; do mark it down for anything painted "
        "that the lesson's picture doesn't have. Reply with one ```json block: "
        '{"scores": {"1": 3, ...}, "note": "one sentence"}')
    r = ask(blocks, CARRY_GRADE_SYSTEM, f"grade-carry {pic} {n}", cwd())
    sc = (r["answer"] or {}).get("scores") or {}
    for i, row in enumerate(rows, 1):
        if str(i) in sc:
            add("carry_grades", {"picture": pic, "n": n, "condition": row["condition"], "rep": row["rep"],
                                 "grade": int(sc[str(i)]), "batch": len(rows), "solo": solo is not None,
                                 "cost_usd": round(r["cost_usd"] / len(rows), 5)})
    print(f"grade-carry {pic} {n:2d}: {len(rows)} results, ${r['cost_usd']:.3f}")


def grade_carry(args):
    if args.solo:
        done = {(r["picture"], r["n"], r["condition"], r["rep"]) for r in state()["carry_grades"] if r.get("solo")}
        jobs = sorted((r["picture"], r["n"], (r["condition"], r["rep"])) for r in state()["carry"]
                      if r["condition"] == args.solo and (r["picture"], r["n"], r["condition"], r["rep"]) not in done)
    else:
        done = {(r["picture"], r["n"]) for r in state()["carry_grades"] if not r.get("solo")}
        jobs = sorted({(r["picture"], r["n"]) for r in state()["carry"]} - done)
    if args.picture:
        jobs = [j for j in jobs if j[0] == args.picture]
    print(f"{len(jobs)} steps to grade")
    run_pool(grade_carry_one, jobs, args.workers)


# ---------------------------------------------------------------------------------------------- the blind graders
def grader_brief() -> str:
    """The owner's rubric from bench/ab_grader.md, for one lesson, with a score for every step added."""
    brief = (HERE / "bench" / "ab_grader.md").read_text()
    rubric = brief[brief.index("## Who you are grading for"):brief.index("## What to write")]
    return ("You grade one lesson for a painting app, in the owner's place, with the owner's rubric. You get the photo, "
            "the finished painting, and every step: its picture (the canvas after the step) and its words, as the "
            "lesson page shows them. You have no tools.\n\n" + rubric.replace("For the pair, `prefer`", "(No pair here.) `prefer`"))


def grader_one(pic: str, g: int):
    les = lesson(pic)
    root = BENCH / pic
    blocks = (text_block("The photo:") + picture_block(load(root / "photo.jpg"), GRADE_SIDE)
              + text_block("The finished painting:") + picture_block(load(root / "finish.jpg"), GRADE_SIDE))
    for s in les["steps"]:
        blocks += text_block(step_text(s, les["canvas_in"], len(les["steps"])) + "\n\nIts picture (after the step):")
        blocks += picture_block(load(root / s["picture"]), GRADE_SIDE)
    blocks += text_block(
        "Grade this lesson by the rubric. Also score every step's own `paintable`, 1 to 5: could a beginner paint "
        "this step from its words and get its picture. Reply with one ```json block: "
        '{"real": 3, "paintable": 3, "agree": 3, "worst_steps": [4, 11], "steps": {"1": 4, "2": 3, ...}, '
        '"note": "two or three plain sentences"}')
    r = ask(blocks, grader_brief(), f"grader {pic} g{g}", cwd())
    a = r["answer"] or {}
    add("graders", {"picture": pic, "grader": g, "real": a.get("real"), "paintable": a.get("paintable"),
                    "agree": a.get("agree"), "worst_steps": a.get("worst_steps") or [],
                    "steps": {str(k): v for k, v in (a.get("steps") or {}).items()}, "note": a.get("note", ""),
                    "cost_usd": r["cost_usd"], "seconds": r["seconds"]})
    print(f"grader {pic} g{g}: worst {a.get('worst_steps')}, paintable {a.get('paintable')}")


def graders(args):
    done = {(r["picture"], r["grader"]) for r in state()["graders"]}
    jobs = [(p, g) for p in PICTURES for g in (1, 2) if (p, g) not in done]
    run_pool(grader_one, jobs, args.workers)


# ------------------------------------------------------------------------------------------------------------ report
def rank(x: list[float]) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    order = a.argsort(kind="stable")
    r = np.empty(len(a))
    r[order] = np.arange(len(a))
    for v in np.unique(a):  # ties share their mean rank
        r[a == v] = r[a == v].mean()
    return r


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    rx, ry = rank(x), rank(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return round(float(np.corrcoef(rx, ry)[0, 1]), 2)


def per_step(rows: list[dict], key: str, condition: str = "words") -> dict:
    """{(picture, n): mean of `key`} over a condition's reps."""
    acc: dict = {}
    for r in rows:
        if r["condition"] == condition and r.get(key) is not None:
            acc.setdefault((r["picture"], r["n"]), []).append(float(r[key]))
    return {k: sum(v) / len(v) for k, v in acc.items()}


def finds_worst(scores: dict, worst: dict) -> dict:
    """How many of the graders' worst steps fall in the student's lowest third of each lesson."""
    hit = total = 0
    for pic in PICTURES:
        mine = sorted((v, n) for (p, n), v in scores.items() if p == pic)
        if not mine:
            continue
        low = {n for _, n in mine[:max(1, round(len(mine) / 3))]}
        w = worst.get(pic, set()) & {n for _, n in mine}
        hit += len(w & low)
        total += len(w)
    return {"in_lowest_third": hit, "of": total, "chance": "a third"}


def paired(rows: list[dict], key: str, a: str, b: str) -> dict:
    """The mean of `key` on condition b less on condition a, over the steps both have (rep 1), and how many fell."""
    x = per_step(rows, key, a)
    y = per_step(rows, key, b)
    both = sorted(set(x) & set(y))
    if not both:
        return {}
    diff = [y[k] - x[k] for k in both]
    return {"steps": len(both), "mean_a": round(sum(x[k] for k in both) / len(both), 3),
            "mean_b": round(sum(y[k] for k in both) / len(both), 3), "change": round(sum(diff) / len(diff), 3),
            "fell": sum(d < 0 for d in diff), "rose": sum(d > 0 for d in diff)}


def report(args) -> dict:
    st = state()
    worst = {}
    gstep: dict = {}
    for g in st["graders"]:
        worst.setdefault(g["picture"], set()).update(int(x) for x in g["worst_steps"])
        for k, v in g["steps"].items():
            gstep.setdefault((g["picture"], int(k)), []).append(float(v))
    gmean = {k: sum(v) / len(v) for k, v in gstep.items()}
    out = {"graders": {p: {"worst_steps": sorted(worst.get(p, ())),
                           "lesson": [{k: g[k] for k in ("grader", "real", "paintable", "agree")}
                                      for g in st["graders"] if g["picture"] == p]} for p in PICTURES}}

    def form(rows, key, extra=None):
        f = {}
        for c in CONDITIONS:
            v = [r[key] for r in rows if r["condition"] == c and r.get(key) is not None]
            if v:
                f[c] = {"n": len(v), "mean": round(sum(v) / len(v), 3)}
                if extra:
                    f[c].update(extra(c))
        f["vs_words"] = {c: paired(rows, key, "words", c) for c in CONDITIONS[1:] if any(r["condition"] == c for r in rows)}
        s = per_step(rows, key)
        common = sorted(set(s) & set(gmean))
        f["agree_with_graders"] = {"spearman": spearman([s[k] for k in common], [gmean[k] for k in common]),
                                   "steps": len(common), **finds_worst(s, worst)}
        h = per_step(rows, key, "header")
        lift = {k: s[k] - h[k] for k in s if k in h}  # what the words add over the header alone
        if lift:
            c2 = sorted(set(lift) & set(gmean))
            f["lift_agree_with_graders"] = {"spearman": spearman([lift[k] for k in c2], [gmean[k] for k in c2]),
                                            "steps": len(c2), **finds_worst(lift, worst),
                                            "words_hurt": sorted(f"{p} {n}" for (p, n), v in lift.items() if v <= -0.25)}
        f["by_picture"] = {p: round(float(np.mean([v for (q, _), v in s.items() if q == p])), 3)
                           for p in PICTURES if any(q == p for q, _ in s)}
        reps = {}
        for r in rows:
            if r["condition"] == "words":
                reps.setdefault((r["picture"], r["n"]), {})[r["rep"]] = r[key]
        two = [v for v in reps.values() if 1 in v and 2 in v]
        if two:
            f["repeat"] = {"steps": len(two), "spearman": spearman([v[1] for v in two], [v[2] for v in two]),
                           "mean_abs_diff": round(float(np.mean([abs(v[1] - v[2]) for v in two])), 3)}
        return f

    pk = st["pick"]
    out["pick"] = form(pk, "p_real", lambda c: {"hits": sum(r["hit"] for r in pk if r["condition"] == c)})
    out["pick"]["picked_when_wrong"] = {k: sum(1 for r in pk if r["condition"] == "words" and r["pick"] == k)
                                        for k in KINDS[1:]}
    out["carry_measure"] = form(st["carry"], "beats")
    out["carry_toward"] = form(st["carry"], "toward")
    out["carry_where"] = form(st["carry"], "where")
    out["carry_grade"] = form([r for r in st["carry_grades"] if not r.get("solo")], "grade")
    out["carry_grade_solo"] = form([r for r in st["carry_grades"] if r.get("solo")], "grade")
    calls = st["calls"]

    def claude(prefix):
        c = [x for x in calls if x["label"].startswith(prefix)]
        return {"calls": len(c), "usd": round(sum(x["cost_usd"] for x in c), 3),
                "usd_a_call": round(sum(x["cost_usd"] for x in c) / len(c), 4) if c else None,
                "seconds_a_call": round(sum(x["seconds"] for x in c) / len(c), 1) if c else None}
    cr = st["carry"]
    out["cost"] = {"pick": claude("pick "), "carry_grade": claude("grade-carry "), "graders": claude("grader "),
                   "worsen": claude("worsen "),
                   "carry_renders": {"renders": len(cr), "usd": round(sum(r["render_usd"] for r in cr), 3),
                                     "usd_a_render": round(sum(r["render_usd"] for r in cr) / len(cr), 4) if cr else None,
                                     "seconds_a_render": round(sum(r["seconds"] for r in cr) / len(cr), 1) if cr else None}}
    st["report"] = out
    save()
    print(json.dumps(out, indent=1))
    return out


def main(argv=None):
    global WORK, RESULTS, WORDS_FROM, _STATE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=WORK)
    ap.add_argument("--words-from", type=Path, help="read each step's lines and tip from <folder>/<picture>/packet.json")
    ap.add_argument("--results", type=Path, help="the results file (default: v4_student.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    sub.add_parser("worsen")
    sh = sub.add_parser("sheet")
    sh.add_argument("picture")
    sh.add_argument("step", type=int)
    sh.add_argument("out")
    for name in ("pick", "carry"):
        p = sub.add_parser(name)
        p.add_argument("--condition", choices=CONDITIONS, default="words")
        p.add_argument("--rep", type=int, default=1)
        p.add_argument("--subset", action="store_true", help="only the steps whose words get worsened")
        p.add_argument("--picture", choices=PICTURES)
        p.add_argument("--steps", help="comma-separated step numbers")
        p.add_argument("--workers", type=int, default=6)
        if name == "carry":
            p.add_argument("--budget", type=float, default=5.0, help="stop before rendering past this spend")
    gc = sub.add_parser("grade-carry")
    gc.add_argument("--picture", choices=PICTURES)
    gc.add_argument("--solo", choices=CONDITIONS, help="grade each of this condition's results alone")
    gc.add_argument("--workers", type=int, default=6)
    gr = sub.add_parser("graders")
    gr.add_argument("--workers", type=int, default=6)
    sub.add_parser("report")
    args = ap.parse_args(argv)
    WORK = args.work
    if args.words_from and not args.results:
        ap.error("--words-from needs --results, so v3's answers stay apart")
    WORDS_FROM = args.words_from.resolve() if args.words_from else None
    if args.results:
        RESULTS = args.results.resolve()
        _STATE = None
    {"prepare": prepare, "worsen": worsen, "sheet": sheet, "pick": pick, "carry": carry,
     "grade-carry": grade_carry, "graders": graders, "report": report}[args.cmd](args)


if __name__ == "__main__":
    main()
