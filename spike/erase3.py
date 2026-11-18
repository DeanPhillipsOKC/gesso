"""The chain of a version 3 lesson: the finish erased backward, one unit of the plan at a time
(docs/design/pipeline-v3.md, section 6).

    request(plan, us, n, why)       -> what the image model is asked for to erase unit n
    run(lesson, plan, finish, ...)  -> the chain: chain/P<nn>.png, D<nn>.png, C<nn>.png, chain.json, looks/
    load(lesson, plan)              -> the chain as the later tools read it

Words:
    unit    a run of steps on the same thing (`plan3.units`). One render a unit.
    P[n]    the picture with every unit after n erased. P[last] is the finish.
    D[n]    what unit n adds: where P[n] differs from P[n-1].
    C[n]    the core of D[n]: the thing itself, not what went with it (its shadow, its soft rim).
    kind    "bare": the unit's things are new and have canvas behind; the render leaves bare canvas.
            "behind": new, on things already painted; the render paints those, by name.
            "back": a later stage of a thing already there; the render takes only its last layer off.

The guard: of each render only the patches that changed by a lot are kept (`changed`); every other pixel stays as
it was. So nothing moves between steps, and the last picture is the finish. A "back" render on a thing that
started as a block-in is kept over the whole thing (#217): a flat coat is close in color to the brushwork it
replaces, so the guard alone keeps it in patches. The thing's shape is known only once the chain has erased the
thing, so the chain is laid twice from the same renders (`lay`): once to find each thing, once to keep those
renders whole.

The requests are the ones the spikes ended on (spike/experiments/v3_combined.py with `--stays`, #218; the block-in
and the list of what isn't painted yet from v3_block_in.py's way 4, #217). The two were never run together before
this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import build_steps as bs
import from_finish as ff
import outline as ol
import plan3

# The guard's numbers, set on three pictures (#204, #210). Lab units, and pixels of a picture 1536 on its long side.
LONG = 1536
BLUR = 2.5  # both pictures are softened this much before they're compared, so brushwork drawn again isn't a change
STRONG = 20.0  # a pixel that changed this much was removed
WEAK = 9.0  # ... and a pixel that changed this much, joined to one that was, went with it
SPECK = 0.0002  # a changed patch smaller than this share of the picture is brushwork, not the thing
HOLE = 0.004  # a gap in the change smaller than this share of the picture is the thing too
CORE = 15  # a strong change narrower than this isn't the thing itself, and a gap in it this narrow is
MOVED = 24  # RGB levels: a pixel this far from what it was has changed (build_steps' final_gap uses the same)
LEFT = 0.02  # share of the canvas: this much left standing beside what a render removed, and the unit is asked again
TRIES = 2  # times a unit may be asked for again (design section 6, step 5)
WHY = ("left", "stray")  # why a unit is asked for again: part of it was left standing; it changed something else

END = ("Change nothing else: everything that stays keeps its exact place, shape, and color, and any canvas that is "
       "already bare stays bare. No text, signature, or watermark.")
AGAIN = {
    # a second try says what the first got wrong. These two sentences are this file's own: no spike ran them.
    "left": {"go": "Every bit of what goes must go: look again at the whole painting for any piece of it still "
                   "standing, however dark, faint or small, and take that out too. ",
             # #217 wrote this by hand for the blanket's knit, which stayed when only its stitches were named
             "back": "What is left where the paint came off is smooth, softly blended paint, with no separate strokes, "
                     "dabs, marks, pattern or texture in it. "},
    "stray": {"go": "Take great care with everything that stays: each of those things is copied exactly as it is in "
                    "this picture, in the same place and the same shapes, stroke for stroke. ",
              "back": "Take great care with everything else: each of the other things is copied exactly as it is in "
                      "this picture, in the same place and the same shapes, stroke for stroke. "},
}


class Refused(Exception):
    """The chain can't be made or read as asked. Nothing was rendered."""


def _px(n: float, shape: tuple) -> int:
    """A size in pixels of a 1536-wide picture, for this picture (sizes are shares of the picture, never pixels)."""
    return max(1, int(round(n * max(shape[:2]) / LONG)))


def _odd(n: int) -> int:
    return n if n % 2 else n + 1


def _ellipse(n: float, shape: tuple) -> np.ndarray:
    k = _odd(_px(n, shape))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


def _lab(img: np.ndarray, blur: float = BLUR) -> np.ndarray:
    return ol.lab(cv2.GaussianBlur(img, (0, 0), blur * max(img.shape[:2]) / LONG)).astype(np.float32)


# ---------------------------------------------------------------------------
# What a render is asked for
# ---------------------------------------------------------------------------


def _state(after: str) -> str:
    """A step's `after` line without the sentences about what isn't there yet. It describes the whole canvas at that
    step, so "no cow yet" in the line for the meadow's lay-in would ask a later render to take the cow out."""
    keep = [s for s in after.replace("; ", ". ").split(". ") if " yet" not in s and not s.lower().startswith("no ")]
    return ". ".join(s.strip().rstrip(".") for s in keep if s.strip()) + "."


def names(plan: dict, us: list[dict], n: int) -> dict[str, str]:
    """Each thing's name in the request for unit n: `called` when the plan gives one, else its name. A thing that has
    had only its first unit so far and has more to come is named as it looks now, by its `plain` name ("the plain
    green meadow, smooth, with no grass blades", while the cow that stands on it is erased)."""
    name = {t["id"]: t.get("called") or t["name"] for t in plan["things"]}
    for t in plan["things"]:
        so_far = sum(1 for v in us[:n + 1] if t["id"] in v["things"])
        if t.get("plain") and so_far == 1 and any(t["id"] in v["things"] for v in us[n + 1:]):
            name[t["id"]] = t["plain"]
    return name


def _block_in_of(steps: list[dict], us: list[dict], thing: str) -> int | None:
    """The unit that is `thing`'s block-in, if it started as one."""
    n = next((k for k, u in enumerate(us) if thing in u["things"]), None)
    return n if n is not None and steps[us[n]["steps"][0]].get("block_in") else None


def _not_yet(steps: list[dict], u: dict) -> str:
    """What the plan paints on the unit's things from this unit on: none of it may show once the unit is erased."""
    later = [lay["what"] for s in steps[u["steps"][0]:] for lay in s["lays"] if lay["thing"] in u["things"]]
    return "None of this is painted yet, so none of it may show: " + "; ".join(later) + ". "


def _first_coat(plan: dict, steps: list[dict], us: list[dict], n: int) -> str:
    """#217: what a render leaves when it takes the first layer off block-in n: one flat coat."""
    s = steps[us[n]["steps"][0]]
    looks = {p["name"]: p.get("looks") or p["name"] for p in plan["paints"]}
    paints = " and ".join(f"{p} ({looks.get(p, p)})" for p in s["paints"])
    one = "one flat coat of a single paint" if len(s["paints"]) == 1 else "one flat coat of these paints"
    thing = "; ".join(names(plan, us, n)[t] for t in us[n]["things"])  # as it looked when it was only blocked in
    return (f"What is left, {thing}, is a block-in and nothing more: {one}, {paints}, the same from edge to edge, "
            "like a shape cut from colored paper. On it there is no shading, no lighter or darker part, no fold, no "
            "texture, no line and no detail. ")


def kept_whole(plan: dict, us: list[dict], n: int) -> list[int]:
    """The block-in units whose things unit n takes a layer off: its render is kept over all of those things."""
    if us[n]["kind"] != "back":
        return []
    steps = plan3.steps(plan)
    found = [_block_in_of(steps, us, t) for t in us[n]["things"]]
    return sorted({k for k in found if k is not None and k < n})


def request(plan: dict, us: list[dict], n: int, why: tuple[str, ...] = ()) -> str:
    """What the image model is asked for to erase unit n (n >= 1) from P[n]. `why`: the reasons it is being asked
    again (WHY), each adding a sentence."""
    steps = plan3.steps(plan)
    u = us[n]
    name = names(plan, us, n)
    done = list(dict.fromkeys(t for v in us[:n] for t in v["things"]))
    # #218: every other thing already painted, by name, as what stays. #214's renders that removed the bushes and
    # the fallen leaves took the woods behind and the rock beside them
    others = "; ".join(name[t] for t in done if t not in u["things"])
    mine = "; ".join(name[t] for t in u["things"])
    again = "".join(AGAIN[w]["back" if u["kind"] == "back" else "go"] for w in WHY if w in why)
    if u["kind"] == "bare":
        keep = f" ({others})" if others else ""
        return ("This is an unfinished acrylic painting. Remove these things from it completely: " + mine + ". Where "
                "they were, leave bare, unpainted white canvas: plain flat white, no paint, no wash, no sketch lines. "
                f"Everything that stays{keep} keeps its exact place, shape, and color. " + again + END)
    if u["kind"] == "behind":
        thing = {t["id"]: t for t in plan["things"]}
        back = list(dict.fromkeys(b for t in u["things"] for b in thing[t].get("behind") or []))
        text = ("This is an unfinished acrylic painting. Remove these things from it completely: " + mine + ". "
                "Behind them there is only this: " + "; ".join(name[b] for b in back) + ". Paint that there, plain "
                "and empty, as it is in the open places of the painting, in the same colors and the same brushwork. "
                "Paint no new thing there: no trees, plants, rocks, animals, buildings or figures. Leave no trace, "
                f"outline, or shadow of what you removed. All of this goes: {mine}. Every part of it and every one of "
                "them, the dark, the faint and the small ones too, so that no shape of them is left. ")
        if others:
            text += (f"Nothing else goes. These are already painted and stay exactly as they are, wherever they can be "
                     f"seen now: {others}. None of them is removed, moved or painted again in another shape, and "
                     "nothing is added to them: no new trunk, tree, branch, bush, rock or animal anywhere in the "
                     "painting. ")
        return text + again + END
    first = u["steps"][0]
    moves = " ".join(f"({k + 1}) " + "; ".join(lay["what"] for lay in steps[i]["lays"]) + "."
                     for k, i in enumerate(u["steps"]))
    was = [_state(steps[first - 1]["after"])]
    for t in u["things"]:  # a thing the step before didn't touch: how its own last step left it
        last = max((i for i in range(first) if t in plan3.things_of(steps[i])), default=None)
        if last is not None and last != first - 1:
            was.append(f"{name[t]}: " + _state(steps[last]["after"]))
    text = ("This is an unfinished acrylic painting, made in stages. Take it back one stage: un-paint only the paint "
            f"that was laid last, on {mine}. The paint to take off: {moves} "
            "Before that paint went on, the painting looked like this: " + " ".join(was) + " "
            "Where you take paint off, show what was under it at that earlier stage, in the colors and brushwork "
            f"already there beside it. {mine} stay where they are, at the same size and outline; only the last layer "
            "of paint on them goes. ")
    if others:
        text += (f"Nothing else in the painting is touched. These stay exactly as they are now: {others}. None of them "
                 "is removed, moved or painted again in another shape. ")
    text += ("Take all of that layer off: none of its strokes, lights or details may still show. Add no new detail in "
             "its place. ")
    for k in kept_whole(plan, us, n):
        # the first unit to come back to a block-in is the render that leaves it: it says what a block-in is (#217)
        if n == next(m for m in range(k + 1, len(us)) if set(us[m]["things"]) & set(us[k]["things"])):
            text += _first_coat(plan, steps, us, k)
    return text + _not_yet(steps, u) + again + END


def asked(plan: dict, us: list[dict], n: int) -> dict:
    """What unit n's render was asked for, for the checker: what goes, and the other things already painted."""
    steps, name = plan3.steps(plan), names(plan, us, n)
    mine = "; ".join(name[t] for t in us[n]["things"])
    if us[n]["kind"] == "back":
        moves = "; ".join(lay["what"] for i in us[n]["steps"] for lay in steps[i]["lays"])
        goes = f"only the last layer of paint on: {mine}. That layer was: {moves}. The things themselves stay."
    else:
        goes = f"all of: {mine}. What is behind shows in its place."
    stays = [name[t] for t in dict.fromkeys(t for v in us[:n] for t in v["things"]) if t not in us[n]["things"]]
    return {"look": f"U{n:02d}", "unit": n, "name": us[n]["name"], "kind": us[n]["kind"], "goes": goes, "stays": stays}


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def changed(before: np.ndarray, after: np.ndarray, never: np.ndarray | None = None) -> np.ndarray:
    """Where `after` differs from `before` by a lot: every patch that changed by WEAK or more and holds a pixel that
    changed by STRONG or more, and nothing inside `never`. Small gaps are closed and specks dropped (`diff_mask` in
    spike/experiments/v3_whole_stages.py, with no box: a version 3 plan has none)."""
    d = np.sqrt(((_lab(before) - _lab(after)) ** 2).sum(2))
    weak, strong = d >= WEAK, d >= STRONG
    if never is not None:
        weak, strong = weak & ~never, strong & ~never
    n, labels = cv2.connectedComponents(weak.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    keep[np.unique(labels[strong])] = True
    keep[0] = False
    m = keep[labels]
    area = m.size
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, _ellipse(9, m.shape)) > 0
    n, labels, stats, _ = cv2.connectedComponentsWithStats((~m).astype(np.uint8), connectivity=4)
    for i in range(1, n):  # holes: patches of no-change walled in by change
        x, y, w, h, size = stats[i]
        if size < HOLE * area and x > 0 and y > 0 and x + w < m.shape[1] and y + h < m.shape[0]:
            m[labels == i] = True
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    for i in range(1, n):
        if stats[i][4] < SPECK * area:
            m[labels == i] = False
    if never is not None:
        m &= ~never
    return m


def core(before: np.ndarray, after: np.ndarray, d: np.ndarray) -> np.ndarray:
    """The thing itself inside its change `d`: where the change is STRONG in a solid patch. The rest of `d` is what
    went with the thing (its reflection, its shadow, ground the render painted again under fallen leaves)."""
    m = (np.sqrt(((_lab(before) - _lab(after)) ** 2).sum(2)) >= STRONG).astype(np.uint8)
    k = _ellipse(CORE, m.shape)
    return (cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_CLOSE, k), cv2.MORPH_OPEN, k) > 0) & d


def solid(mask: np.ndarray) -> np.ndarray:
    """A mask with its narrow gaps closed and its holes filled: a thing that was blocked in is one solid shape."""
    m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, _ellipse(15, mask.shape))
    flood = np.pad(m, 1)
    cv2.floodFill(flood, None, (0, 0), 2)
    return flood[1:-1, 1:-1] != 2


def erase_one(src: np.ndarray, raw: np.ndarray, bare: bool, frozen: np.ndarray,
              whole: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(the picture with the unit erased, what was erased). `bare`: what changed becomes bare canvas. `whole`: a
    shape the render is kept over as well as where it changed by a lot (a thing that started as a block-in, #217).
    Canvas already bare (`frozen`) stays bare."""
    canvas = np.array(ff.CANVAS, np.uint8)
    d = changed(src, raw, frozen)
    if bare:
        out = src.copy()
        out[d] = canvas
        return out, d
    if whole is not None and whole.any():
        d = solid(d | whole) & ~frozen
    if not d.any():
        return src.copy(), d
    out = bs.make_background(src, d, raw)
    out[frozen] = canvas
    if whole is not None and whole.any():
        # every pixel that differs, not only the ones that differ by a lot: the next step brings all of it
        return out, bs.halo((out != src).any(2)) & ~frozen
    return out, bs.halo(d) & ~frozen


def left_standing(src: np.ndarray, raw: np.ndarray, D: np.ndarray, frozen: np.ndarray) -> float:
    """#218: the share of the canvas, just outside what a render removed (`D`), that still looks like what was
    removed and not like what the render put in its place. Each pixel of a band around `D` is compared with the
    picture nearby inside `D`, before (the thing) and after (what is behind it). A thing removed whole leaves a band
    of background, which is like the after; a thing left standing in part (the birch grove's dark firs, #214)
    leaves more of itself beside the hole. Only for a thing that goes ("bare" and "behind"): a layer that comes off
    leaves the same thing beside it. It sees a whole thing left, not a faint one in part."""
    if not D.any():
        return 0.0
    a, b = _lab(src), _lab(raw)
    w = D.astype(np.float32)
    sigma = 41 * max(D.shape) / LONG
    near = cv2.GaussianBlur(w, (0, 0), sigma)[..., None] + 1e-6
    was = cv2.GaussianBlur(a * w[..., None], (0, 0), sigma) / near
    now = cv2.GaussianBlur(b * w[..., None], (0, 0), sigma) / near
    band = (cv2.dilate(D.astype(np.uint8), _ellipse(61, D.shape)) > 0) & ~D & ~frozen
    dist = lambda x, y: np.sqrt(((x - y) ** 2).sum(2))  # noqa: E731
    like = band & (dist(a, was) + 6 < dist(a, now)) & (dist(was, now) > 12)
    like = cv2.morphologyEx(like.astype(np.uint8), cv2.MORPH_OPEN, _ellipse(9, D.shape))
    return round(float(like.mean()), 4)


def moved(a: np.ndarray, b: np.ndarray, where: np.ndarray) -> float:
    """The share of `where` in which the two pictures differ by enough to see."""
    if not where.any():
        return 0.0
    return round(float((np.abs(a.astype(np.int16) - b.astype(np.int16)).max(2)[where] > MOVED).mean()), 4)


# ---------------------------------------------------------------------------
# The chain
# ---------------------------------------------------------------------------


def _unit(plan: dict, us: list[dict], n: int, src: np.ndarray, raw: np.ndarray, frozen: np.ndarray,
          cores: dict[int, np.ndarray] | None) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Unit n erased from `src` by its render: (P[n-1], D[n], C[n], the canvas that is bare from here back)."""
    shapes = [cores[k] for k in kept_whole(plan, us, n) if k in cores] if cores else []
    bare = us[n]["kind"] == "bare"
    out, d = erase_one(src, raw, bare, frozen, np.logical_or.reduce(shapes) if shapes else None)
    return out, d, (d if bare else core(out, src, d)), (frozen | d if bare else frozen)


def lay(plan: dict, us: list[dict], finish: np.ndarray, raws: dict[int, np.ndarray],
        cores: dict[int, np.ndarray] | None = None) -> dict:
    """The chain laid from its renders, last unit first: {"P", "D", "C"} by unit. `cores`: each block-in unit's
    shape from an earlier laying; a "back" render on its thing is then kept over all of it (`kept_whole`)."""
    last = len(us) - 1
    frozen = np.zeros(finish.shape[:2], bool)
    P, D, C = {last: finish}, {}, {}
    for n in range(last, 0, -1):
        P[n - 1], D[n], C[n], frozen = _unit(plan, us, n, P[n], raws[n], frozen, cores)
    D[0] = C[0] = ~frozen
    return {"P": P, "D": D, "C": C}


def look(src: np.ndarray, out: np.ndarray, D: np.ndarray, width: int = 784) -> np.ndarray:
    """One picture a unit for the checker's eye: before, after, and the before with the kept change tinted (#218).
    A wide picture's three are stacked, a tall one's are side by side."""
    tint = src.copy()
    tint[D] = (0.45 * tint[D] + 0.55 * np.array([255, 0, 255])).astype(np.uint8)
    h = round(width * src.shape[0] / src.shape[1])
    cells = [cv2.resize(x, (width, h), interpolation=cv2.INTER_AREA) for x in (src, out, tint)]
    wide = src.shape[1] > src.shape[0]
    gap = np.full((8, width, 3) if wide else (h, 8, 3), 255, np.uint8)
    return (np.vstack if wide else np.hstack)([cells[0], gap, cells[1], gap, cells[2]])


def sheet(pictures: list[np.ndarray | None], like: np.ndarray, width: int = 256, per_row: int = 6) -> np.ndarray:
    h = int(like.shape[0] * width / like.shape[1])
    cells = [np.full((h, width, 3), 255, np.uint8) if p is None else
             cv2.resize(p, (width, h), interpolation=cv2.INTER_AREA) for p in pictures]
    cells += [np.full((h, width, 3), 255, np.uint8)] * (-len(cells) % per_row)
    return np.vstack([np.hstack(cells[i:i + per_row]) for i in range(0, len(cells), per_row)])


def _png(path: Path, img: np.ndarray) -> None:
    Image.fromarray(img.astype(np.uint8) * 255 if img.dtype == bool else img).save(path)


def _read(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB"))


def run(lesson: Path, plan: dict, finish: np.ndarray, render, redo: dict[int, str] | None = None,
        auto: bool = True) -> dict:
    """Make the chain in <lesson>/chain/ and return its numbers (also chain.json).

    `render(name, src, prompt, fresh) -> (the model's answer at src's size, {"seconds", "cost_usd", "cached"})`.
    The same picture and request come back from the render cache for nothing, so running this again pays only for
    what changed. `redo`: {unit: why} to ask for again (WHY). Every unit before one of them is then rendered from a
    new picture. `auto`: a unit whose thing was left standing (LEFT) is asked for again on the spot, before the
    units before it are rendered from its picture."""
    us = plan3.units(plan)
    folder = Path(lesson) / "chain"
    folder.mkdir(parents=True, exist_ok=True)
    # Every try is written down before its render and ticked off after it (chain/tries.json), so a run that stops
    # partway (the cost cap, the network) neither forgets a try nor pays for it twice: the next run asks for the
    # same tries, and one already rendered comes from the cache.
    shape = [[u["things"], u["steps"]] for u in us]
    tries = folder / "tries.json"
    was = json.loads(tries.read_text(encoding="utf-8")) if tries.exists() else {}
    same = was.get("units") == shape
    again: dict[int, list[str]] = {int(k): list(v) for k, v in (was.get("again") or {}).items()} if same else {}
    rendered: set[str] = set(was.get("rendered") or []) if same else set()

    def keep() -> None:
        tmp = tries.with_suffix(".tmp")
        tmp.write_text(json.dumps({"units": shape, "again": {str(k): v for k, v in sorted(again.items())},
                                   "rendered": sorted(rendered)}, indent=1), encoding="utf-8")
        tmp.replace(tries)

    for n, why in (redo or {}).items():
        if not 1 <= n < len(us):
            raise Refused(f"there is no unit {n} to ask for again: the chain renders units 1 to {len(us) - 1}")
        if why not in WHY:
            raise Refused(f"say why unit {n} is asked for again: {' or '.join(WHY)}")
        pending = bool(again.get(n)) and again[n][-1] == why and f"U{n:02d}" + "r" * len(again[n]) not in rendered
        if len(again.get(n, [])) >= TRIES and not pending:
            raise Refused(f"unit {n} ({us[n]['name']}) has been asked for again {TRIES} times already. Go on with it "
                          "as it is, and record it in notes.json as a known problem.")
    for n, why in (redo or {}).items():
        newest = f"U{n:02d}" + "r" * len(again.get(n, []))
        if again.get(n) and again[n][-1] == why and newest not in rendered:
            continue  # the same try, asked for by a run that stopped before rendering it: not a new one
        again.setdefault(n, []).append(why)
    keep()
    last = len(us) - 1
    frozen = np.zeros(finish.shape[:2], bool)
    P, D, C = {last: finish}, {}, {}
    raws: dict[int, np.ndarray] = {}
    rows: dict[int, dict] = {}
    for n in range(last, 0, -1):
        made = []  # every render made for this unit in this run: the one kept and the tries before it
        while True:
            name = f"U{n:02d}" + "r" * len(again.get(n, []))
            src = folder / f"{name}_in.png"
            _png(src, P[n])
            # a try that was never rendered is a fresh render: a second try's request can be word for word the first's
            raw, info = render(name, src, request(plan, us, n, tuple(again.get(n, []))),
                               bool(again.get(n)) and name not in rendered)
            rendered.add(name)
            keep()
            made.append({"render": name, "seconds": info["seconds"], "cost_usd": info["cost_usd"],
                         "cached": bool(info.get("cached"))})
            left = None if us[n]["kind"] == "back" else left_standing(P[n], raw, changed(P[n], raw, frozen), frozen)
            if not (auto and left is not None and left >= LEFT and len(again.get(n, [])) < TRIES):
                break
            again.setdefault(n, []).append("left")
            keep()
        raws[n] = raw
        before = frozen
        P[n - 1], D[n], C[n], frozen = _unit(plan, us, n, P[n], raw, frozen, None)
        rows[n] = {"unit": n, "id": us[n]["id"], "name": us[n]["name"], "kind": us[n]["kind"],
                   "things": us[n]["things"], "steps": [i + 1 for i in us[n]["steps"]], "render": name,
                   "again": again.get(n, []), "tries": made,
                   "seconds": round(sum(t["seconds"] for t in made), 1),
                   "cost_usd": round(sum(t["cost_usd"] for t in made), 4),
                   "cached": all(t["cached"] for t in made), "left_standing": left,
                   "ask_again": bool(left is not None and left >= LEFT),
                   # of the picture the guard kept as it was, the share the raw render had moved
                   "raw_moved_outside": moved(P[n], raw, ~bs.halo(D[n]) & ~before)}
    D[0] = C[0] = ~frozen
    # the renders laid a second time, each thing that started as a block-in now known by its shape (#217)
    cores = {k: C[k] for n in range(1, len(us)) for k in kept_whole(plan, us, n)}
    ch = lay(plan, us, finish, raws, cores) if cores else {"P": P, "D": D, "C": C}
    (folder / "looks").mkdir(exist_ok=True)
    # the old chain's pictures go, and with them the checker's answers.json: it read other pictures
    for old in list(folder.glob("[PDC][0-9][0-9].png")) + [f for f in (folder / "looks").iterdir() if f.is_file()]:
        old.unlink()
    for n in range(len(us)):
        _png(folder / f"P{n:02d}.png", ch["P"][n])
        _png(folder / f"D{n:02d}.png", ch["D"][n])
        _png(folder / f"C{n:02d}.png", ch["C"][n])
        if n:
            rows[n]["erased_share"] = round(float(ch["D"][n].mean()), 4)
            rows[n]["kept_whole"] = bool(kept_whole(plan, us, n))
            Image.fromarray(look(ch["P"][n], ch["P"][n - 1], ch["D"][n])).save(folder / "looks" / f"U{n:02d}.jpg", quality=88)
    (folder / "looks" / "asked.json").write_text(json.dumps([asked(plan, us, n) for n in range(1, len(us))], indent=1),
                                                 encoding="utf-8")
    canvas = np.full_like(finish, np.array(ff.CANVAS, np.uint8))
    Image.fromarray(sheet([canvas] + [ch["P"][n] for n in range(len(us))], finish)).save(folder / "chain.jpg", quality=88)
    ordered = [rows[n] for n in range(1, len(us))]
    result = {"units": [{"id": u["id"], "name": u["name"], "kind": u["kind"], "things": u["things"],
                         "steps": u["steps"]} for u in us],
              "again": {str(k): v for k, v in sorted(again.items())},
              "made_for": made_for(plan, us, finish, again),
              "renders": len(ordered), "paid": sum(1 for r in ordered for t in r["tries"] if not t["cached"]),
              "cost_usd": round(sum(r["cost_usd"] for r in ordered), 4),
              "render_seconds": round(sum(r["seconds"] for r in ordered), 1), "rows": ordered}
    (folder / "chain.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def made_for(plan: dict, us: list[dict], finish: np.ndarray, again: dict[int, list[str]]) -> str:
    """What a chain was made for: the finish and every request. A chain made for another finish, or for a plan
    whose words changed, is stale even when its units are the same."""
    import hashlib

    h = hashlib.sha256(np.ascontiguousarray(finish).tobytes())
    for n in range(1, len(us)):
        h.update(request(plan, us, n, tuple(again.get(n, []))).encode("utf-8") + b"\0")
    return h.hexdigest()


def problems(result: dict) -> tuple[list[str], list[str]]:
    """(what to do about the chain, what is left as it is). A unit whose thing was left standing is asked for
    again while it has tries left; after that it stays, to be recorded as a known problem."""
    todo, kept = [], []
    for r in result["rows"]:
        if not r["ask_again"]:
            continue
        said = (f"unit {r['unit']} ({r['name']}): {r['left_standing']:.1%} of the canvas beside what the render "
                "removed still looks like what was to go")
        if len(r["again"]) < TRIES:
            todo.append(f"{said}. Ask for it again: erase --redo {r['unit']}:left")
        else:
            kept.append(f"{said}, after {TRIES} more tries. It stays: record it in notes.json as a known problem.")
    return todo, kept


def load(lesson: Path, plan: dict) -> list[dict]:
    """The chain as the later tools read it: [{"P", "D", "core"}] by unit. Refuses a chain made for another plan."""
    folder = Path(lesson) / "chain"
    us = plan3.units(plan)
    if not (folder / "chain.json").exists():
        raise Refused(f"no chain yet: run erase --lesson {lesson} first")
    kept = json.loads((folder / "chain.json").read_text(encoding="utf-8"))
    if [(u["things"], u["steps"]) for u in kept["units"]] != [(u["things"], u["steps"]) for u in us]:
        raise Refused("the chain was made for a plan with other units: run erase again")
    finish = Path(lesson) / "99_finish.png"
    again = {int(k): v for k, v in (kept.get("again") or {}).items()}
    from filters import load as read_finish  # as the tools read it (the camera's rotation flag honored)

    if not finish.exists() or kept.get("made_for") != made_for(plan, us, read_finish(finish, max_side=100_000), again):
        raise Refused("the finish or the plan's words changed since the chain was made: run erase again (a request "
                      "that didn't change costs nothing)")
    return [{"P": _read(folder / f"P{n:02d}.png"), "D": np.array(Image.open(folder / f"D{n:02d}.png")) > 0,
             "core": np.array(Image.open(folder / f"C{n:02d}.png")) > 0} for n in range(len(us))]
