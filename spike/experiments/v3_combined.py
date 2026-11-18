"""Spike for #210 (pipeline v3): the three adopted spikes run together on one picture, the highland cow.

Not part of the pipeline. The plan is the plan-first painter's plan (#172). The finish is erased backward by that
plan's units, chained and guarded by the change with no box (#204, #207). Paints are fitted to the changes, step
pictures cut from them, and a lesson folder is made that v2's own tools (step-aids, draft-text, mix, publish) and the
fact sheet and writers of #173 can read, with a thing's shape taken from what its render changed, not from an outline.

    python spike/experiments/v3_combined.py units highland-cow --prompts   # the renders, last first; no render
    python spike/experiments/v3_combined.py probe highland-cow 9           # PAID: unit 9 alone, erased from the finish
    python spike/experiments/v3_combined.py erase highland-cow             # PAID: one low render a unit, chained
    python spike/experiments/v3_combined.py erase highland-cow --redo 8    # ask for unit 8 again (and all before it)
    python spike/experiments/v3_combined.py build highland-cow             # step pictures, the three-row sheet
    python spike/experiments/v3_combined.py lesson highland-cow            # the lesson folder, its aids and packets
    python spike/experiments/v3_combined.py merge highland-cow [--final]   # the writers' words in, checked
    python spike/experiments/v3_combined.py page highland-cow              # the lesson as a page
    python spike/experiments/v3_combined.py results highland-cow           # writes v3_combined.json
    python spike/experiments/v3_combined.py --stays erase birch-grove      # PAID: #218's requests, in runs/stays/
    python spike/experiments/v3_combined.py --stays looks birch-grove      # a picture a unit for the checker to read

Words:
    unit      a run of steps in one stage on the same thing (`units` in v4_forward.py). One render a unit.
    P[u]      the picture with every unit after u erased. P[last] is the finish.
    D[u]      what unit u adds: where the render that erased it changed P[u] by a lot (`diff_mask`, no box).
    bare      the unit's things are new and have nothing behind them: the render leaves bare canvas.
    behind    the unit's things are new and sit on things already painted: the render paints those, by name.
    back      a thing in the unit was painted in an earlier unit (the cow's coat over its shape): the render takes it
              back to how the plan says it looked before this unit. Untested before this spike.

    --stays   #218: the "behind" and "back" requests also name what stays, from the things already painted, and no
              hand-written `say` sentence is read. Its chains go in runs/stays/, so #214's stay as they were (a kept
              render is checked against its request, and v3_block_in.py reads them).

Pictures and numbers go in spike/experiments/bench/runs/combined/<picture>/ (git-ignored).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "spike"))
sys.path.insert(0, str(HERE))

import build_steps as bs  # noqa: E402
import from_finish as ff  # noqa: E402
import v3_peel as peel  # noqa: E402
import v3_whole_stages as ws  # noqa: E402
import v4_forward as fw  # noqa: E402

BENCH = peel.BENCH
OUT = BENCH / "runs" / "combined"
STAYS = False  # --stays: #218's requests (see the top of this file)
LEFT = 0.02  # share of the canvas: this much left standing beside what a render removed, and the unit is reported
LITTLE = 0.002  # a step that changes less than this share of the canvas is reported (design section 8, check 4)


def load(picture: str) -> dict:
    d = fw.load(picture)
    d["finish"] = d["v2_finish"]  # the frozen finish: every step ends on it
    extra = json.loads((HERE / "v3_combined_plan.json").read_text())[picture]
    d["behind"] = extra["behind"]
    d["extra"] = extra
    d["painter"]["early"] = extra.get("early") or {}  # a thing's name before its later stages (the meadow, plain)
    # a thing's name in every request, when the plan's own would mislead a render ("The sky and trees through the
    # window" as what is behind the trees, #214)
    d["painter"]["called"] = extra.get("called") or {}
    d["painter"]["flat"] = sorted(flats(d))  # the block-ins
    # a sentence written by hand for one unit (#214). #218's requests name what stays themselves and read none
    d["painter"]["say"] = {} if STAYS else extra.get("say") or {}
    d["painter"]["stays"] = STAYS
    return d


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


def units(painter: dict, flat: set[str] = frozenset()) -> list[dict]:
    """#207's units, cut twice more, so that no step's picture has to be cut out of another step's render:
    - a step whose paints the unit has all used already starts a unit of its own. Two steps of one render that share
      a paint can't be told apart in it (the nostrils and the mouth line, both Dark umber: the first took both and
      the second changed nothing, 2026-11-17);
    - a block-in (a step in `flat`, the ids shown as a flat coat) is a unit by itself. Cut from the next step's
      render it was a slab of one color, and its brushwork arrived on the step after (2026-11-17)."""
    steps = fw.flat(painter)
    out = []
    for u in fw.units(painter):
        cur = {"stage": u["stage"], "things": [], "steps": []}
        used: set[str] = set()
        for i in u["steps"]:
            if cur["steps"] and (set(steps[i]["paints"]) <= used or steps[cur["steps"][-1]]["id"] in flat):
                out.append(cur)
                cur, used = {"stage": u["stage"], "things": [], "steps": []}, set()
            cur["steps"].append(i)
            cur["things"] += [t for t in fw.things_of(steps[i]) if t not in cur["things"]]
            used |= set(steps[i]["paints"])
        out.append(cur)
    return out


def shows(d: dict) -> dict[str, str]:
    """How each step is shown (`shows` in v4_forward.py), with the extras' `not_flat` steps as a pass."""
    return {**fw.shows(d["fit"]), **{k: "pass" for k in d["extra"].get("not_flat") or ()}}


def flats(d: dict) -> set[str]:
    """The block-ins: the steps the fitted plan shows as a flat coat, less the ones the extras say aren't one
    (`not_flat`: the birch grove's dark leaf dabs are a flat coat to v2's cutter and no block-in, #214)."""
    return {k for k, v in shows(d).items() if v == "flat"}


# ---------------------------------------------------------------------------
# What a render is asked for
# ---------------------------------------------------------------------------


def kind_of(us: list[dict], n: int, behind: dict[str, list[str]]) -> str:
    done = {t for u in us[:n] for t in u["things"]}
    if set(us[n]["things"]) & done:
        return "back"
    return "behind" if any(behind.get(t) for t in us[n]["things"]) else "bare"


def _state(after: str) -> str:
    """A step's `after` line without the sentences about what isn't there yet. It describes the whole canvas at that
    step, so "no cow yet" in the line for the meadow's lay-in would ask a later render to take the cow out."""
    keep = [s for s in after.replace("; ", ". ").split(". ") if " yet" not in s and not s.lower().startswith("no ")]
    return ". ".join(s.strip().rstrip(".") for s in keep if s.strip()) + "."


def _only(remove: str, others: str, painter: dict) -> str:
    """#218, for a "behind" request: all of the thing goes, and what stays, by name."""
    if not painter.get("stays"):
        return ""
    text = (f"All of this goes: {remove}. Every part of it and every one of them, the dark, the faint and the small "
            "ones too, so that no shape of them is left. ")
    if others:
        text += (f"Nothing else goes. These are already painted and stay exactly as they are, wherever they can be "
                 f"seen now: {others}. None of them is removed, moved or painted again in another shape, and nothing "
                 "is added to them: no new trunk, tree, branch, bush, rock or animal anywhere in the painting. ")
    return text


def prompt_for(painter: dict, us: list[dict], n: int, behind: dict[str, list[str]], again: int = 0) -> str:
    steps = fw.flat(painter)
    name = {t["id"]: t["name"] for t in painter["things"]}
    name.update(painter.get("called") or {})
    u = us[n]
    kind = kind_of(us, n, behind)
    later = {t for v in us[n + 1:] for t in v["things"]}
    if kind != "back":  # a thing with a later stage still to come is named as it looks now
        name.update({t: w for t, w in (painter.get("early") or {}).items() if t in later})
    done = [t for v in us[:n] for t in v["things"]]
    stays = list(dict.fromkeys(done))
    # #218: what a "behind" or a "back" request says must stay: every other thing already painted, by the name the
    # rest of the request uses for it. #214's renders that removed the bushes and the fallen leaves took the woods
    # behind and the rock beside them; each needed a sentence by hand that named them.
    others = "; ".join(name[t] for t in stays if t not in u["things"])
    end = ("Change nothing else: everything that stays keeps its exact place, shape, and color, and any canvas that "
           "is already bare stays bare. No text, signature, or watermark.")
    # a sentence written by hand for one unit, keyed by its first step: what a probe showed the request left open
    # (the birch grove's rock went with the fallen leaves, #214)
    end = ((painter.get("say") or {}).get(steps[u["steps"][0]]["id"], "") + " " + end).strip()
    if kind == "bare":
        remove = "; ".join(name[t] for t in u["things"])
        keep = (" (" + "; ".join(name[t] for t in stays) + ")") if stays else ""
        return ("This is an unfinished acrylic painting. Remove these things from it completely: " + remove + ". Where "
                "they were, leave bare, unpainted white canvas: plain flat white, no paint, no wash, no sketch lines. "
                f"Everything that stays{keep} keeps its exact place, shape, and color. " + end)
    if kind == "behind":
        remove = "; ".join(name[t] for t in u["things"])
        back = list(dict.fromkeys(b for t in u["things"] for b in behind.get(t) or []))
        return ("This is an unfinished acrylic painting. Remove these things from it completely: " + remove + ". "
                "Behind them there is only this: " + "; ".join(name[b] for b in back) + ". Paint that there, plain "
                "and empty, as it is in the open places of the painting, in the same colors and the same brushwork. "
                "Paint no new thing there: no trees, plants, rocks, animals, buildings or figures. Leave no trace, "
                "outline, or shadow of what you removed. " + _only(remove, others, painter) + end)
    mine = [steps[i] for i in u["steps"]]
    first = u["steps"][0]
    moves = " ".join(f"({k + 1}) " + "; ".join(lay["what"] for lay in s["lays"]) + "." for k, s in enumerate(mine))
    was = [_state(steps[first - 1]["after"])]
    for t in u["things"]:  # a thing the step before didn't touch: how its own last step left it
        last = max(i for i in range(first) if t in fw.things_of(steps[i]))
        if last != first - 1:
            was.append(f"{name[t]}: " + _state(steps[last]["after"]))
    things = "; ".join(name[t] for t in u["things"])
    text = ("This is an unfinished acrylic painting, made in stages. Take it back one stage: un-paint only the paint "
            f"that was laid last, on {things}. The paint to take off: {moves} "
            "Before that paint went on, the painting looked like this: " + " ".join(was) + " "
            "Where you take paint off, show what was under it at that earlier stage, in the colors and brushwork "
            "already there beside it. " + f"{things} stay where they are, at the same size and outline; only the "
            "last layer of paint on them goes. ")
    if painter.get("stays") and others:
        text += (f"Nothing else in the painting is touched. These stay exactly as they are now: {others}. None of them "
                 "is removed, moved or painted again in another shape. ")
    if again:
        text += ("Take all of that layer off: none of its strokes, lights or details may still show. Add no new "
                 "detail in its place. ")
    if again > 1 or steps[first - 1]["id"] in (painter.get("flat") or ()) and set(fw.things_of(steps[first - 1])) & set(u["things"]):
        text += ("What is left where the paint came off is a first coat: smooth, flat and softly blended, with no "
                 "separate strokes, blades, dabs or texture in it. ")
    return text + end


# ---------------------------------------------------------------------------
# The chain
# ---------------------------------------------------------------------------


def erase_one(src: np.ndarray, raw: np.ndarray, bare: bool, frozen: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """#204's guard with no box: (the picture with the unit erased, what was erased)."""
    canvas = np.array(ff.CANVAS, np.uint8)
    d = ws.diff_mask(src, raw, None, frozen)
    if bare:
        out = src.copy()
        out[d] = canvas
        return out, d
    if not d.any():
        return src.copy(), d
    out = bs.make_background(src, d, raw)
    grown = bs.halo(d) & ~frozen
    out[frozen] = canvas
    return out, grown


def left_standing(src: np.ndarray, raw: np.ndarray, D: np.ndarray, frozen: np.ndarray) -> float:
    """#218, check 3, with no outline: the share of the canvas, just outside what a render removed (`D`), that still
    looks like what was removed and not like what the render put in its place. Each pixel of a band around `D` is
    compared with the picture nearby inside `D`, before (the thing) and after (what is behind it). A thing removed
    whole leaves a band of background, which is like the after; a thing left standing in part (the birch grove's
    dark firs, #214) leaves more of itself beside the hole. Only for a thing that goes ("bare" and "behind"): a layer
    that comes off ("back") leaves the same thing beside it, and this reads high on good renders."""
    if not D.any():
        return 0.0
    a = bs.ol.lab(cv2.GaussianBlur(src, (0, 0), ws.BLUR)).astype(np.float32)
    b = bs.ol.lab(cv2.GaussianBlur(raw, (0, 0), ws.BLUR)).astype(np.float32)
    w = D.astype(np.float32)
    near = cv2.GaussianBlur(w, (0, 0), 41)[..., None] + 1e-6
    was, now = cv2.GaussianBlur(a * w[..., None], (0, 0), 41) / near, cv2.GaussianBlur(b * w[..., None], (0, 0), 41) / near
    band = (cv2.dilate(D.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (61, 61))) > 0) & ~D & ~frozen
    dist = lambda x, y: np.sqrt(((x - y) ** 2).sum(2))  # noqa: E731
    like = band & (dist(a, was) + 6 < dist(a, now)) & (dist(was, now) > 12)
    like = cv2.morphologyEx(like.astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    return round(float(like.mean()), 4)


def asked(d: dict, us: list[dict], n: int) -> dict:
    """What unit n's render was asked for, for a checker: what goes, and the other things already painted."""
    steps, painter = fw.flat(d["painter"]), d["painter"]
    name = {t["id"]: t["name"] for t in painter["things"]}
    name.update(painter.get("called") or {})
    kind = kind_of(us, n, d["behind"])
    mine = "; ".join(name[t] for t in us[n]["things"])
    if kind == "back":
        moves = "; ".join(lay["what"] for i in us[n]["steps"] for lay in steps[i]["lays"])
        goes = f"only the last layer of paint on: {mine}. That layer was: {moves}. The things themselves stay."
    else:
        goes = f"all of: {mine}. What is behind shows in its place."
    stays = [name[t] for t in dict.fromkeys(t for v in us[:n] for t in v["things"]) if t not in us[n]["things"]]
    return {"unit": n, "kind": kind, "goes": goes, "stays": stays}


def look(src: np.ndarray, out: np.ndarray, D: np.ndarray, width: int = 784) -> np.ndarray:
    """#218, check 2: one picture a unit for a checker's eye: before, after, and the before with the kept change
    tinted. No measure tried could tell a stray change from the thing's own (docs/spikes/v3-stays.md); a reader with
    the list of what stays can. A wide picture's three are stacked, a tall one's are side by side."""
    tint = src.copy()
    tint[D] = (0.45 * tint[D] + 0.55 * np.array([255, 0, 255])).astype(np.uint8)
    h = round(width * src.shape[0] / src.shape[1])
    cells = [cv2.resize(x, (width, h), interpolation=cv2.INTER_AREA) for x in (src, out, tint)]
    wide = src.shape[1] > src.shape[0]
    gap = np.full((8, width, 3) if wide else (h, 8, 3), 255, np.uint8)
    return (np.vstack if wide else np.hstack)([cells[0], gap, cells[1], gap, cells[2]])


def looks(picture: str) -> Path:
    """A chain's looks and what each unit was asked for (looks/U<nn>.jpg, looks/asked.json)."""
    d = load(picture)
    us = units(d["painter"], flats(d))
    folder = OUT / picture
    er = json.loads((folder / "erase.json").read_text())
    (folder / "looks").mkdir(exist_ok=True)
    rows = []
    for n in range(1, len(us)):
        name = f"U{n:02d}" + "r" * int(er["redone"].get(str(n), 0))
        src = np.array(Image.open(folder / f"{name}_in.png").convert("RGB"))
        out = np.array(Image.open(folder / f"P{n - 1:02d}.png").convert("RGB"))
        Image.fromarray(look(src, out, np.load(folder / f"D{n:02d}.npy"))).save(folder / "looks" / f"U{n:02d}.jpg", quality=88)
        rows.append(asked(d, us, n))
    (folder / "looks" / "asked.json").write_text(json.dumps(rows, indent=1))
    return folder / "looks"


def probe(picture: str, n: int, quality: str = "low", again: int = 0) -> dict:
    """One unit erased from the finish, alone: does the request work before a chain is spent on it?"""
    d = load(picture)
    us = units(d["painter"], flats(d))
    folder = OUT / picture / "probe"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"U{n:02d}" + "r" * again
    text = prompt_for(d["painter"], us, n, d["behind"], again)
    raw, info = peel.render("gpt-image", d["finish"], text, folder, name, quality)
    out, D = erase_one(d["finish"], raw, kind_of(us, n, d["behind"]) == "bare", np.zeros(raw.shape[:2], bool))
    Image.fromarray(out).save(folder / f"{name}_out.png")
    ys, xs = np.nonzero(D)
    if len(ys):
        pad = 40
        y0, y1, x0, x1 = max(0, ys.min() - pad), ys.max() + pad, max(0, xs.min() - pad), xs.max() + pad
        tint = out.copy()
        tint[D] = (0.5 * tint[D] + 0.5 * np.array([255, 0, 255])).astype(np.uint8)
        Image.fromarray(np.hstack([d["finish"][y0:y1, x0:x1], raw[y0:y1, x0:x1], out[y0:y1, x0:x1],
                                   tint[y0:y1, x0:x1]])).save(folder / f"{name}_look.jpg", quality=90)
    ws.sheet_rows(folder / f"{name}.jpg", [[d["finish"], raw, out]], width=512)
    return {"unit": n, "kind": kind_of(us, n, d["behind"]), "erased_share": round(float(D.mean()), 4),
            "raw_moved_outside": peel.moved(d["finish"], raw, ~bs.halo(D)) if D.any() else None,
            "seconds": info["seconds"], "cost_usd": info["cost_usd"]}


def erase(picture: str, quality: str = "low", redo: dict[int, int] | None = None) -> dict:
    """The chain, last unit first. `redo`: {unit: level} to ask for again (level 1: the stricter sentence, kept as
    U<n>r; level 2: and a smooth first coat, U<n>rr). Every unit before one of them was rendered from the old
    picture, so its files are thrown and it is rendered again. A render the probe already made is used."""
    d = load(picture)
    painter, finish = d["painter"], d["finish"]
    us = units(painter, flats(d))
    folder = OUT / picture
    folder.mkdir(parents=True, exist_ok=True)
    was = json.loads((folder / "erase.json").read_text()) if (folder / "erase.json").exists() else {}
    redone = {int(k): v for k, v in (was.get("redone") or {}).items()}
    thrown = was.get("thrown", [])
    if redo:
        top = max(redo)
        for n in range(top, 0, -1):
            name = f"U{n:02d}" + "r" * redone.get(n, 0)
            meta = folder / f"{name}.json"
            if not meta.exists():
                continue
            kept = json.loads(meta.read_text())
            thrown.append({"unit": n, "seconds": kept["seconds"], "cost_usd": kept["cost_usd"]})
            for f in (folder / f"{name}.json", folder / f"{name}_in.png", folder / f"{name}_raw.png"):
                f.rename(folder / f"thrown{len(thrown):02d}_{f.name}")
        redone.update(redo)
        if top == len(us) - 1:  # the last unit is erased from the finish, as the probe erased it
            name = f"U{top:02d}" + "r" * redo[top]
            for end in (".json", "_in.png", "_raw.png"):
                if (folder / "probe" / (name + end)).exists():
                    (folder / (name + end)).write_bytes((folder / "probe" / (name + end)).read_bytes())
    shape = finish.shape[:2]
    frozen = np.zeros(shape, bool)
    P = {len(us) - 1: finish}
    raws: dict[int, np.ndarray] = {}
    rows = []
    for n in range(len(us) - 1, 0, -1):
        kind = kind_of(us, n, d["behind"])
        again = redone.get(n, 0)
        name = f"U{n:02d}" + "r" * again
        raw, info = peel.render("gpt-image", P[n], prompt_for(painter, us, n, d["behind"], again), folder, name, quality)
        # check 3 (#218): a thing that was to go and was left standing in part. Reported, not asked for again here
        left = None if kind == "back" else left_standing(P[n], raw, ws.diff_mask(P[n], raw, None, frozen), frozen)
        P[n - 1], D = erase_one(P[n], raw, kind == "bare", frozen)
        if kind == "bare":
            frozen |= D
        np.save(folder / f"D{n:02d}.npy", D)
        np.save(folder / f"C{n:02d}.npy", D if kind == "bare" else ws.core_mask(P[n - 1], P[n], D))
        Image.fromarray(P[n - 1]).save(folder / f"P{n - 1:02d}.png")
        raws[n] = raw
        rows.append({"unit": n, "kind": kind, "things": us[n]["things"], "steps": [i + 1 for i in us[n]["steps"]],
                     "redo": again, "seconds": info["seconds"], "cost_usd": info["cost_usd"],
                     "erased_share": round(float(D.mean()), 4), "left_standing": left,
                     "ask_again": bool(left is not None and left >= LEFT),
                     # of the picture the guard kept as it was, the share the raw render had moved
                     "raw_moved_outside": peel.moved(P[n], raw, ~bs.halo(D) & ~frozen)})
        print(json.dumps(rows[-1]), flush=True)
    D0 = ~frozen
    np.save(folder / "D00.npy", D0)
    np.save(folder / "C00.npy", D0)
    Image.fromarray(finish).save(folder / f"P{len(us) - 1:02d}.png")
    result = {"picture": picture, "quality": quality, "units": us, "redone": redone, "thrown": thrown,
              "ask_again": sorted(r["unit"] for r in rows if r["ask_again"]),
              "renders": len(rows), "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
              "thrown_cost_usd": round(sum(t["cost_usd"] for t in thrown), 4),
              "render_seconds": round(sum(r["seconds"] for r in rows), 1), "rows": rows}
    (folder / "erase.json").write_text(json.dumps(result, indent=1))
    canvas = np.full_like(finish, np.array(ff.CANVAS, np.uint8))
    ws.sheet_rows(folder / "chain.jpg", [[canvas] + [P[n] for n in range(len(us))],
                                         [None] + [raws.get(n + 1) for n in range(len(us))]], width=256)
    return result


# ---------------------------------------------------------------------------
# Paints and step pictures
# ---------------------------------------------------------------------------


def chain(picture: str, us: list[dict]) -> list[dict]:
    folder = OUT / picture
    return [{"P": np.array(Image.open(folder / f"P{n:02d}.png").convert("RGB")),
             "D": np.load(folder / f"D{n:02d}.npy"), "core": np.load(folder / f"C{n:02d}.npy")} for n in range(len(us))]


def unit_paints(steps: list[dict], u: dict) -> list[str]:
    names: list[str] = []
    for i in u["steps"]:
        names += [p for p in steps[i]["paints"] if p not in names]
    return names


def fit(d: dict, us: list[dict], ch: list[dict]) -> tuple[dict[str, str], list[dict[str, str]], list[dict]]:
    """(each paint's one color for the lesson, each unit's own fit, a row a paint). A unit's paints are fitted to
    its change (`fit_paints`, #207). A paint several units use takes its color from the unit that lays the most of
    it. A paint no pixel of any unit came to is reported: the plan names a color the finish doesn't have."""
    steps = fw.flat(d["painter"])
    per_unit, laid = [], {}
    for n, u in enumerate(us):
        names = unit_paints(steps, u)
        where = ch[n]["D"]
        hexes = fw.fit_paints(ch[n]["P"], where, {p: d["seeds"][p] for p in names})
        near = ws.nearest(ch[n]["P"], [hexes[p] for p in names])
        per_unit.append(hexes)
        for j, p in enumerate(names):
            laid.setdefault(p, []).append((int((where & (near == j)).sum()), n))
    one, rows = {}, []
    for p in d["seeds"]:
        if p not in laid:
            continue
        px, n = max(laid[p])
        one[p] = per_unit[n][p]
        rows.append({"paint": p, "hex": one[p], "seed": d["seeds"][p], "from_unit": n,
                     "pixels_share": round(px / ch[0]["D"].size, 4), "units": [k for _, k in laid[p]],
                     "moved_from_seed": round(float(np.sqrt(((ff.hex_lab(one[p]) - ff.hex_lab(d["seeds"][p])) ** 2).sum())), 1),
                     "not_in_finish": px < 20})
    return one, per_unit, rows


def build(picture: str) -> tuple[list[np.ndarray], list[np.ndarray], dict]:
    """(step pictures, where each step lays paint, numbers). Each pixel of a unit's change D belongs to the step
    whose paint it is nearest (cut from D, not the core: thin strokes aren't in the core, #207). A pass lays its
    own pixels. A flat step lays a flat coat over the core and over its own pixels outside it. The last step lays all
    of D: its own pixels, and the brushwork under a flat coat. Before 2026-11-17 it also brought every pixel no
    earlier step had claimed (dark bush rows on the step that names the bushes' sunlit green)."""
    d = load(picture)
    painter, folder = d["painter"], OUT / picture
    us, steps, show = units(painter, flats(d)), fw.flat(painter), shows(d)
    ch = chain(picture, us)
    one, per_unit, paint_rows = fit(d, us, ch)
    canvas = np.empty(d["finish"].shape, np.float32)
    canvas[:] = ff.CANVAS
    pictures: list[np.ndarray | None] = [None] * len(steps)
    masks: list[np.ndarray | None] = [None] * len(steps)
    rows: list[dict | None] = [None] * len(steps)
    for n, u in enumerate(us):
        content, D, core = ch[n]["P"], ch[n]["D"], ch[n]["core"]
        names = unit_paints(steps, u)
        hexes = per_unit[n]
        near = ws.nearest(content, [hexes[p] for p in names])
        lab = bs.ol.lab(cv2.GaussianBlur(content, (0, 0), 1.0))
        # every pixel of the change belongs to one step: the first of the unit that names the paint nearest it
        first = {p: next(i for i in u["steps"] if p in steps[i]["paints"]) for p in names}
        own = {i: D & np.isin(near, [j for j, p in enumerate(names) if first[p] == i]) for i in u["steps"]}
        for i in u["steps"]:
            s = steps[i]
            before = canvas.copy()
            how = show.get(s["id"], "full")
            if i == u["steps"][-1]:
                # the unit's last step: P[u] exactly. The steps before it laid their own pixels, so what is left
                # is its own (and the soft rim of the change)
                how, lay, where = "all", content, D
            elif how == "flat":
                # a flat coat of its paint over the core and over its own pixels outside it. Showing its own pixels
                # as they are was tried and looked worse: a half-finished cow beside a flat slab (2026-11-17). So
                # its brushwork still arrives on the unit's last step.
                where = core | own[i]
                lay = ff.flat_paint(content, where, [hexes[p] for p in s["paints"]])
            else:
                how, lay, where = "pass", content, own[i]
            canvas = bs._lay(canvas, lay, where)
            pic = np.clip(canvas, 0, 255).astype(np.uint8)
            changed = np.abs(canvas - before).max(2) > 6
            # check 3: how far what the step lays is from the nearest paint it names (the lesson's one color for it)
            far = None
            if changed.any():
                dist = np.min([np.sqrt(((lab[changed] - ff.hex_lab(one[p])) ** 2).sum(1)) for p in s["paints"]], axis=0)
                far = {"median": round(float(np.median(dist)), 1), "over_25": round(float((dist > 25).mean()), 3)}
            rows[i] = {"n": i + 1, "id": s["id"], "unit": n, "things": fw.things_of(s), "show": how,
                       "painted": round(float(where.mean()), 4), "changed": round(float(changed.mean()), 4),
                       "outside_unit": round(float((changed & ~bs.halo(D)).mean()), 5), "from_its_paints": far}
            pictures[i], masks[i] = pic, where & changed if (where & changed).any() else where
    gap = np.abs(pictures[-1].astype(np.int16) - d["finish"].astype(np.int16)).max(2) > peel.MOVED
    info = {"picture": picture, "steps": len(steps), "units": len(us),
            "final_gap": round(float(gap.mean()), 4), "outside_unit_max": max(r["outside_unit"] for r in rows),
            "steps_that_change_little": [r["id"] for r in rows if r["changed"] < LITTLE],
            "from_its_paints_median": round(float(np.median([r["from_its_paints"]["median"] for r in rows
                                                              if r["from_its_paints"]])), 1),
            "paints": paint_rows, "rows": rows}
    out = folder / "steps"
    out.mkdir(exist_ok=True)
    for f in out.glob("*"):
        f.unlink()
    for i, (s, img) in enumerate(zip(steps, pictures)):
        Image.fromarray(img).save(out / f"{i + 1:02d}_{s['id']}.png")
        np.save(out / f"{i + 1:02d}_mask.npy", masks[i])
    (folder / "build.json").write_text(json.dumps(info, indent=1))
    fw.three_rows(folder / "steps.jpg", d, pictures, tag="combined")
    return pictures, masks, info


# ---------------------------------------------------------------------------
# A lesson folder v2's tools and #173's sheet and writers can read
# ---------------------------------------------------------------------------
#
# v2's tools cut the step pictures again from the plan and the outlines each time they run (build_steps.build).
# Here that one function is swapped for this spike's pictures, and the "outlines" (parts/owner.png) are drawn from
# the units' changes: a part is a unit, and its shape is the core of what its render changed. Nothing else in the
# tools is touched, so the Where lines, close-ups, paint maps, drafted lines, the fact sheet and the page are v2's
# and #173's own code reading shapes that no outline model made.


def lesson_folder(picture: str) -> Path:
    return OUT / "lessons" / f"{picture}-combined"


def slug(name: str) -> str:
    return "-".join("".join(ch if ch.isalnum() else " " for ch in name.lower()).split())


def owner_from(ch: list[dict]) -> np.ndarray:
    """Which unit each pixel of the finish belongs to: the last unit whose core holds it, else the last whose change
    does, else the nearest pixel that has one."""
    owner = np.full(ch[0]["D"].shape, -1, np.int32)
    for n, c in enumerate(ch):
        owner[c["core"]] = n
    loose = np.full(owner.shape, -1, np.int32)
    for n, c in enumerate(ch):
        loose[c["D"]] = n
    owner[owner < 0] = loose[owner < 0]
    if (owner < 0).any():
        _, idx = cv2.distanceTransformWithLabels((owner < 0).astype(np.uint8), cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.nonzero(owner >= 0)
        lut = np.zeros(idx.max() + 1, np.int32)
        lut[idx[ys, xs]] = owner[ys, xs]
        owner[owner < 0] = lut[idx[owner < 0]]
    return owner


def v2_plan(d: dict, us: list[dict], ch: list[dict], one: dict[str, str], owner: np.ndarray) -> dict:
    """The painter's plan in the shape v2's tools read: a part a unit, its box measured from its place in `owner`."""
    painter = d["painter"]
    steps, show = fw.flat(painter), shows(d)
    thing = {t["id"]: t for t in painter["things"]}
    named, parents = d["extra"].get("units") or {}, d["extra"].get("parents") or {}
    h, w = owner.shape
    parts, part_of = [], {}
    for n, u in enumerate(us):
        t = thing[u["things"][0]]
        over = named.get(steps[u["steps"][0]]["id"]) or {}
        pid = over.get("id") or t["id"]
        where = owner == n
        if not where.any():
            where = ch[n]["D"]
        ys, xs = np.nonzero(where)
        kind = "area" if kind_of(us, n, d["behind"]) == "bare" or n == 0 or pid in (d["extra"].get("areas") or ()) else "object"
        p = {"id": pid, "name": over.get("name") or t["name"], "kind": kind, "thing": u["things"], "unit": n,
             "element": t["element"], "element_why": t.get("why", ""),
             "box": [round(float(xs.min() / w), 3), round(float(ys.min() / h), 3),
                     round(float((xs.max() + 1) / w), 3), round(float((ys.max() + 1) / h), 3)]}
        parent = over.get("parent") or parents.get(pid)
        if parent:
            p["parent"] = parent
        # a new thing whose first of several steps is a pass (the cat's window trees, the birch grove's fallen
        # leaves, #214): marks to v2 too, which refuses an area or object that starts with a pass
        starts_pass = len(u["steps"]) > 1 and show.get(steps[u["steps"][0]]["id"], "full") == "pass"
        if (kind_of(us, n, d["behind"]) == "back" and show.get(steps[u["steps"][0]]["id"]) != "flat") or starts_pass:
            # a later layer on a thing: v2 calls that marks, and wants their colors (never read: no outline runs)
            mine = [one[q] for q in unit_paints(steps, u)]
            p.update(kind="marks", colors_in=mine, colors_out=[h for h in one.values() if h not in mine][:3])
        parts.append(p)
        for i in u["steps"]:
            part_of[i] = pid
    lab = bs.ol.lab(cv2.GaussianBlur(d["finish"], (0, 0), 1.0))
    looks = {p["name"]: p["looks"] for p in painter["paints"]}
    paints = []
    for name, hx in one.items():
        users = sorted({part_of[i] for i, s in enumerate(steps) if name in s["paints"]}, key=[p["id"] for p in parts].index)
        y, x = np.unravel_index(np.sqrt(((lab - ff.hex_lab(hx)) ** 2).sum(2)).argmin(), lab.shape[:2])
        paints.append({"id": slug(name), "name": name, "used_for": looks[name], "hex": hx,
                       "sample_x": round(float(x / w), 3), "sample_y": round(float(y / h), 3), "parts": users})
    last_of_unit = {u["steps"][-1] for u in us}
    first_alone = [u["steps"] for n, u in enumerate(us) if len(u["steps"]) == 1 and kind_of(us, n, d["behind"]) != "back"]
    stages, i = [], 0
    for st in painter["stages"]:
        out = []
        for s in st["steps"]:
            how = "blend" if s.get("blend") else show.get(s["id"], "full")
            if how == "flat" and i in last_of_unit:  # a block-in with its own render: v2 has no flat last step
                how = "full"
            if how == "full" and i not in last_of_unit:  # the fitted plan has no row for it: cut as a pass (`build`)
                how = "pass"
            if how == "pass" and [i] in first_alone:  # a new thing in one step (the birch grove's path)
                how = "full"
            out.append({k: v for k, v in {"id": s["id"], "name": s["name"], "part": part_of[i], "show": how,
                                          "paints": [slug(p) for p in s["paints"]], "stroke": s["stroke"],
                                          "brush": s["brush"], "why": s.get("why")}.items() if v})
            i += 1
        stages.append({"id": st["id"], "name": st.get("name", st["id"]), "steps": out})
    base = d["fit"]
    return {"plan_version": 2, "technique": base["technique"], "technique_why": base.get("technique_why", ""),
            "subject": painter["subject"], "focal_point": painter["focal_point"], "light": painter["light"],
            "photo": base["photo"], "parts": parts, "paints": paints, "stages": stages}


def use(lesson: Path) -> None:
    """Make v2's tools read this lesson's own step pictures: `build_steps.build` answers with them."""
    import os

    os.environ.setdefault("GESSO_HISTORY", str(BENCH / "runs" / "history"))
    plan = json.loads((lesson / "plan.json").read_text())
    steps = bs.flat_steps(plan)
    pictures = [np.array(Image.open(lesson / f"{i + 1:02d}_{s['id']}.png").convert("RGB")) for i, s in enumerate(steps)]
    masks = [np.load(lesson / "trials" / "combined" / f"{i + 1:02d}_mask.npy") for i in range(len(steps))]
    rows = [{"id": s["id"]} for s in steps]

    def built(finish, plan, owner, background=None):
        return [p.copy() for p in pictures], [dict(r) for r in rows], [m.copy() for m in masks]

    bs.build = built
    # v2's own step-picture checks read numbers its cutter makes; this spike's checks are in build.json
    bs.problems = lambda plan, rows: []
    bs.faint_ghosts = lambda plan, rows: []


def tool(cmd: str, lesson: Path, *more: str) -> dict:
    """One of v2's tools, in this process (so it sees `use`)."""
    import contextlib
    import io

    import tools

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = tools.main([cmd, "--lesson", str(lesson), *more])
    text = buf.getvalue().strip()
    if code:
        raise SystemExit(f"{cmd} failed on {lesson}:\n{text[-3000:]}")
    return json.loads(text) if text.startswith("{") else {}


def make_lesson(picture: str) -> Path:
    import shutil

    sys.path.insert(0, str(BENCH))
    import bench
    import v3_facts as fx

    d = load(picture)
    us = units(d["painter"], flats(d))
    pictures, masks, _ = build(picture)
    ch = chain(picture, us)
    one, _, _ = fit(d, us, ch)
    lesson = lesson_folder(picture)
    if lesson.exists():
        shutil.rmtree(lesson)
    bench.build(picture, lesson.parent, name=lesson.name)
    owner = owner_from(ch)
    plan = v2_plan(d, us, ch, one, owner)
    (lesson / "plan.json").write_text(json.dumps(plan, indent=1) + "\n")
    (lesson / "painter.json").write_text(json.dumps(d["painter"], indent=1) + "\n")
    (lesson / "parts").mkdir()
    Image.fromarray(owner.astype(np.uint8)).save(lesson / "parts" / "owner.png")
    (lesson / "trials" / "combined").mkdir(parents=True)
    for i, (s, img) in enumerate(zip(fw.flat(d["painter"]), pictures)):
        Image.fromarray(img).save(lesson / f"{i + 1:02d}_{s['id']}.png")
        np.save(lesson / "trials" / "combined" / f"{i + 1:02d}_mask.npy", masks[i])
    use(lesson)
    fx._tool = tool
    done = {"mix": tool("mix", lesson), "step-aids": tool("step-aids", lesson), "draft-text": tool("draft-text", lesson)}
    Image.fromarray(d["photo"]).save(lesson / "photo.png")  # the writers' packets show the photo
    after = {s["id"]: {"meant": s["after"]} for s in fw.flat(d["painter"])}
    fx.packets(lesson, extra=after, brief=HERE / "v3_combined_writer.md")
    print(json.dumps({k: {x: v[x] for x in v if x in ("steps", "lines", "closeups", "maps", "transfer")}
                      for k, v in done.items()}))
    return lesson


def merge(picture: str, final: bool = False) -> dict:
    """The stage writers' words into text.json, checked against the sheet (#173's `merge`)."""
    import v3_facts as fx

    lesson = lesson_folder(picture)
    use(lesson)
    fx._tool = tool
    r = fx.merge(lesson, final)
    (lesson / "trials" / "facts" / ("merge-final.json" if final else "merge.json")).write_text(json.dumps(r, indent=1))
    return r


def page(picture: str) -> dict:
    lesson = lesson_folder(picture)
    use(lesson)
    return tool("publish", lesson)


def results(picture: str) -> dict:
    """What's kept in git: the chain's, the build's and the words' numbers (v3_combined.json)."""
    folder, lesson = OUT / picture, lesson_folder(picture)
    er, bd = json.loads((folder / "erase.json").read_text()), json.loads((folder / "build.json").read_text())
    probes = [json.loads(f.read_text()) for f in sorted((folder / "probe").glob("U*.json"))]
    used = {f"U{n:02d}" + "r" * lvl for n, lvl in ((int(k), v) for k, v in er["redone"].items())}
    probe_cost = sum(p["cost_usd"] for f, p in zip(sorted((folder / "probe").glob("U*.json")), probes) if f.stem not in used)
    words = {}
    for name in ("merge.json", "merge-final.json"):
        f = lesson / "trials" / "facts" / name
        if f.exists():
            m = json.loads(f.read_text())
            words[name[:-5]] = {k: m[k] for k in ("claims", "failures", "after", "dropped", "unwritten", "missing")}
    out = {"picture": picture, "issue": 210 if picture == "highland-cow" else 214, "steps": bd["steps"], "units": bd["units"],
           "renders_kept": er["renders"], "renders_thrown": len(er["thrown"]), "probes": len(probes),
           "cost_usd": {"chain_kept": er["cost_usd"], "chain_thrown": er["thrown_cost_usd"],
                        "probes_not_used": round(probe_cost, 4),
                        "all": round(er["cost_usd"] + er["thrown_cost_usd"] + probe_cost, 4)},
           "render_seconds_kept": er["render_seconds"], "redone": er["redone"],
           "checks": {"final_gap": bd["final_gap"], "outside_unit_max": bd["outside_unit_max"],
                      "from_its_paints_median": bd["from_its_paints_median"],
                      "steps_that_change_little": bd["steps_that_change_little"]},
           "chain": [{k: r[k] for k in ("unit", "kind", "things", "steps", "redo", "erased_share", "raw_moved_outside",
                                         "seconds", "cost_usd")} for r in er["rows"]],
           "paints": bd["paints"], "step_rows": bd["rows"], "words": words}
    kept = json.loads((HERE / "v3_combined.json").read_text())  # one entry a picture; the others stay as they are
    kept["pictures"][picture] = out
    (HERE / "v3_combined.json").write_text(json.dumps(kept, indent=1) + "\n")
    return out


def grade_folders(pictures: list[str], out: Path, seed: int = 214) -> dict:
    """The blind A/B round for Claude's graders (bench/ab_grader.md), as #204's: two folders a picture, each with
    the v2 baseline and the combined lesson as A/ and B/, sides drawn from the seed and swapped for the second
    grader. The folders are pair-01, pair-02, ... in a seeded shuffle. The key goes beside `out` (<out>.key.json),
    never in it, and `out` must be outside the repository."""
    import random
    import shutil

    sys.path.insert(0, str(BENCH))
    import packet

    out = Path(out).resolve()
    if ROOT in out.parents or out == ROOT:
        raise SystemExit("the grading folders must be outside the repository")
    rng = random.Random(seed)
    key: dict = {"round": "s214-combined", "seed": seed, "pictures": {}, "folders": {}}
    jobs = []
    for pic in pictures:
        order = ["v2", "combined"] if rng.random() < 0.5 else ["combined", "v2"]
        jobs += [(pic, "g1", order), (pic, "g2", order[::-1])]
    names = [f"pair-{n + 1:02d}" for n in range(len(jobs))]
    rng.shuffle(names)
    out.mkdir(parents=True, exist_ok=True)
    for name, (pic, g, order) in zip(names, jobs):
        sides = {"v2": peel.baseline_run(pic), "combined": lesson_folder(pic)}
        folder = out / name
        if folder.exists():
            shutil.rmtree(folder)
        for side, which in zip("AB", order):
            packet.build_one(sides[which], folder / side)
        shutil.copy(BENCH / "ab_grader.md", folder / "ab_grader.md")
        key["pictures"].setdefault(pic, {})[g] = {"A": order[0], "B": order[1], "folder": name,
                                                  "lessons": {k: v.name for k, v in sides.items()}}
        key["folders"][name] = f"{pic}-{g}"
    out.with_name(out.name + ".key.json").write_text(json.dumps(key, indent=1))
    return key


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stays", action="store_true", help="#218's requests; the chains go in runs/stays/")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("units")
    p.add_argument("picture")
    p.add_argument("--prompts", action="store_true")
    p = sub.add_parser("probe")
    p.add_argument("picture")
    p.add_argument("unit", type=int)
    p.add_argument("--again", type=int, default=0, help="1: the stricter sentence; 2: and a smooth first coat")
    p = sub.add_parser("erase")
    p.add_argument("picture")
    p.add_argument("--redo", default="", help="units to ask for again, e.g. 8 or 10:2 (level 2); earlier units are "
                                              "rendered again too")
    p = sub.add_parser("merge")
    p.add_argument("picture")
    p.add_argument("--final", action="store_true")
    for name in ("page", "results", "looks"):
        p = sub.add_parser(name)
        p.add_argument("picture")
    p = sub.add_parser("lesson")
    p.add_argument("picture")
    p = sub.add_parser("grade-folders")
    p.add_argument("pictures", help="comma-separated")
    p.add_argument("out", type=Path, help="a folder outside the repository")
    p = sub.add_parser("build")
    p.add_argument("picture")
    args = ap.parse_args()
    if args.stays:
        global STAYS, OUT
        STAYS, OUT = True, BENCH / "runs" / "stays"
    if args.cmd == "looks":
        print(looks(args.picture))
    elif args.cmd == "units":
        d = load(args.picture)
        us = units(d["painter"], flats(d))
        for n in range(len(us) - 1, -1, -1):
            print(n, kind_of(us, n, d["behind"]) if n else "first", us[n]["things"], [s + 1 for s in us[n]["steps"]])
            if args.prompts and n:
                print("   ", prompt_for(d["painter"], us, n, d["behind"]))
    elif args.cmd == "erase":
        r = erase(args.picture, redo={int(x.split(":")[0]): int((x.split(":") + ["1"])[1])
                                      for x in args.redo.split(",") if x})
        print(json.dumps({k: r[k] for k in ("renders", "cost_usd", "thrown_cost_usd", "render_seconds", "ask_again")}))
    elif args.cmd == "build":
        _, _, info = build(args.picture)
        print(json.dumps({k: info[k] for k in ("steps", "final_gap", "outside_unit_max", "steps_that_change_little",
                                               "from_its_paints_median")}))
        for r in info["paints"]:
            print(r)
        for r in info["rows"]:
            print(r["n"], r["id"], r["unit"], r["show"], r["changed"], r["from_its_paints"])
    elif args.cmd == "merge":
        print(json.dumps(merge(args.picture, args.final), indent=1))
    elif args.cmd == "page":
        print(json.dumps(page(args.picture))[:1500])
    elif args.cmd == "results":
        r = results(args.picture)
        print(json.dumps({k: r[k] for k in ("renders_kept", "renders_thrown", "cost_usd", "checks", "words")}))
    elif args.cmd == "grade-folders":
        grade_folders(args.pictures.split(","), args.out)
        print(f"{args.out}: the key is beside it, not in it")
    elif args.cmd == "lesson":
        print(make_lesson(args.picture))
    elif args.cmd == "probe":
        print(json.dumps(probe(args.picture, args.unit, again=args.again)))


if __name__ == "__main__":
    main()
