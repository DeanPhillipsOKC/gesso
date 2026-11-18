"""Spike for #217 (pipeline v3): a block-in that arrives finished, and the near-empty steps after it.

Not part of the pipeline. It reads a chain `v3_combined.py` made (#214) and makes a block-in's picture again three
ways, without paying for the chain again:

    way 1  a stronger request for what is left: the "back" request that leaves the block-in also names its one paint
           and lists, from the plan, what isn't painted yet.
    way 2  a second render for the block-in alone: from the picture the "back" render left, the thing is asked for
           as one flat coat of its paint.
    way 3  no render: a flat coat of the block-in's fitted paint over the unit's change.
    way 4  way 1, and its list of what isn't painted yet on every later stage of the thing too (added by this spike
           when the first three left the later steps as they were).

    python spike/experiments/v3_block_in.py prompts sleeping-cat 7        # the two requests for unit 7; no render
    python spike/experiments/v3_block_in.py try sleeping-cat 7,10         # PAID: ways 1 and 2 (2 renders a unit), way 3
    python spike/experiments/v3_block_in.py try highland-cow 8 --ways 3   # one way only
    python spike/experiments/v3_block_in.py sheet sleeping-cat 7,10       # the thing's steps, #214's row and a row a way
    python spike/experiments/v3_block_in.py lesson sleeping-cat           # way 4's lesson folder; #214's words kept
    python spike/experiments/v3_block_in.py merge sleeping-cat [--final]  # the writers' words in, checked
    python spike/experiments/v3_block_in.py page sleeping-cat
    python spike/experiments/v3_block_in.py grade-folders sleeping-cat,highland-cow,birch-grove <outside the repo>
    python spike/experiments/v3_block_in.py results                       # writes v3_block_in.json

Words:
    block-in   a unit that is one flat first coat of a new thing (the cat's blanket is unit 7, step 10).
    P[u], D[u] as in v3_combined.py: the picture after unit u, and what unit u adds.

A way gives a new P[u] for the block-in. The pictures under it stay (P[u-1] is the thing gone, whatever the thing
looked like), and so do the pictures over it. Only D[u] and D[u+1] are measured again, so the next step now brings
everything the block-in no longer shows.

Pictures and numbers go in spike/experiments/bench/runs/block-in/ (git-ignored).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import build_steps as bs  # noqa: E402
import from_finish as ff  # noqa: E402
import v3_combined as vc  # noqa: E402
import v3_peel as peel  # noqa: E402
import v3_whole_stages as ws  # noqa: E402
import v4_forward as fw  # noqa: E402

CHAINS = vc.OUT  # #214's chains
OUT = vc.BENCH / "runs" / "block-in"
WAYS = {1: "stronger request", 2: "second render", 3: "flat coat, no render", 4: "stronger request, every stage"}
END = "Change nothing else:"


def setup(picture: str) -> tuple[dict, list[dict], list[dict]]:
    d = vc.load(picture)
    us = vc.units(d["painter"], vc.flats(d))
    return d, us, fw.flat(d["painter"])


def first_coat(d: dict, us: list[dict], steps: list[dict], n: int) -> str:
    """What a block-in is, in a request: its one paint by name and look, and what the plan paints on it later."""
    s = steps[us[n]["steps"][0]]
    looks = {p["name"]: p["looks"] for p in d["painter"]["paints"]}
    paints = " and ".join(f"{p} ({looks[p]})" for p in s["paints"])
    later = [lay["what"] for t in steps[us[n]["steps"][-1] + 1:] for lay in t["lays"] if lay["thing"] in us[n]["things"]]
    one = "one flat coat of a single paint" if len(s["paints"]) == 1 else "one flat coat of these paints"
    text = (f"is a block-in and nothing more: {one}, {paints}, the same from edge to edge, like a shape cut from "
            "colored paper. On it there is no shading, no lighter or darker part, no fold, no texture, no line and no "
            "detail. ")
    if later:
        text += "None of this is painted yet, so none of it may show: " + "; ".join(later) + ". "
    return text


def name_of(d: dict, us: list[dict], n: int) -> str:
    name = {t["id"]: t["name"] for t in d["painter"]["things"]}
    name.update(d["painter"]["called"])
    name.update(d["painter"]["early"])
    return "; ".join(name[t] for t in us[n]["things"])


def request(d: dict, us: list[dict], steps: list[dict], n: int, way: int) -> str:
    """Way 1: unit n+1's own "back" request, saying what is left. Way 2: a request made from P[n]."""
    thing = name_of(d, us, n)
    coat = first_coat(d, us, steps, n)
    if way == 1:
        text = vc.prompt_for(d["painter"], us, n + 1, d["behind"])
        at = text.rindex(END)
        say = (d["painter"].get("say") or {}).get(steps[us[n + 1]["steps"][0]]["id"])
        if say:
            at = text.index(say)
        return text[:at] + f"What is left, {thing}, {coat}" + text[at:]
    return ("This is an unfinished acrylic painting. One thing in it was painted too far for this stage: "
            f"{thing}. Paint it again as its first coat only, in exactly the same place, at the same size and with "
            f"the same outline. It {coat}Change nothing else: everything else keeps its exact place, shape, and color, "
            "and any canvas that is already bare stays bare. No text, signature, or watermark.")


def P_of(picture: str, n: int) -> np.ndarray:
    return np.array(Image.open(CHAINS / picture / f"P{n:02d}.png").convert("RGB"))


def D_of(picture: str, n: int) -> np.ndarray:
    return np.load(CHAINS / picture / f"D{n:02d}.npy")


def solid(mask: np.ndarray) -> np.ndarray:
    """A mask with its narrow gaps closed and its holes filled: a block-in is one solid shape."""
    m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    flood = np.pad(m, 1)
    cv2.floodFill(flood, None, (0, 0), 2)
    return flood[1:-1, 1:-1] != 2


def keep(picture: str, n: int, src: np.ndarray, raw: np.ndarray) -> np.ndarray:
    """A block-in's render, kept over the whole thing: where it changed the picture by a lot, and all of the solid
    part of what the unit adds. The chain's own guard keeps only the change, and a flat coat is close to some of the
    brushwork it replaces, so patches of stitches and fur stayed (the first try of this spike)."""
    d = ws.diff_mask(src, raw, None, None)
    return bs.make_background(src, solid(d | np.load(CHAINS / picture / f"C{n:02d}.npy")), raw)


def block_in(picture: str, n: int, way: int, d: dict, us: list[dict], steps: list[dict]) -> tuple[np.ndarray, dict]:
    """The block-in's new picture (P[n]) one way, and what it cost."""
    folder = OUT / picture / "renders"
    folder.mkdir(parents=True, exist_ok=True)
    if way == 1:  # unit n+1 erased again from P[n+1]
        src = P_of(picture, n + 1)
        raw, info = peel.render("gpt-image", src, request(d, us, steps, n, 1), folder, f"w1_U{n + 1:02d}", "low")
        return keep(picture, n, src, raw), info
    if way == 2:  # the block-in asked for again from P[n]
        src = P_of(picture, n)
        raw, info = peel.render("gpt-image", src, request(d, us, steps, n, 2), folder, f"w2_U{n:02d}", "low")
        return keep(picture, n, src, raw), info
    # way 3: the fitted paint, flat, over the solid part of what the unit adds
    src, under = P_of(picture, n), P_of(picture, n - 1)
    where = solid(np.load(CHAINS / picture / f"C{n:02d}.npy"))
    names = steps[us[n]["steps"][0]]["paints"]
    hexes = fw.fit_paints(src, where, {p: d["seeds"][p] for p in names})
    lay = ff.flat_paint(src, where, [hexes[p] for p in names])
    out = np.clip(bs._lay(under.astype(np.float32), lay, where), 0, 255).astype(np.uint8)
    return out, {"seconds": 0.0, "cost_usd": 0.0, "paints": hexes}


def not_yet(us: list[dict], steps: list[dict], m: int) -> str:
    """What the plan paints on unit m's things from unit m on: none of it may show once unit m is erased."""
    later = [lay["what"] for t in steps[us[m]["steps"][0]:] for lay in t["lays"] if lay["thing"] in us[m]["things"]]
    return "None of this is painted yet, so none of it may show: " + "; ".join(later) + ". "


def stages(us: list[dict], d: dict, n: int, far: bool = False) -> list[int]:
    """The units right after block-in n that come back to its thing, in a row (the cat: 11 to 14). `far`: every
    unit up to the last one that comes back to it, other things' units between them too (the cow: 9 to 15, with the
    horns' 10 and 11), since a chain can only be made again as a row of units."""
    mine = [m for m in range(n + 1, len(us)) if set(us[m]["things"]) & set(us[n]["things"])]
    if far:
        return list(range(n + 1, max(mine) + 1)) if mine else []
    out = []
    for m in range(n + 1, len(us)):
        if m not in mine or vc.kind_of(us, m, d["behind"]) != "back":
            break
        out.append(m)
    return out


SMOOTH = ("What is left where the paint came off is smooth, softly blended paint, with no separate strokes, dabs, "
          "marks, pattern or texture in it. ")


def every_stage(picture: str, n: int, d: dict, us: list[dict], steps: list[dict],
                smooth: tuple[int, ...] = (), far: bool = False) -> tuple[dict[int, np.ndarray], dict]:
    """Way 4: way 1, and the same list of what isn't painted yet on every later stage of the thing. The thing's
    units are erased again from the top one down, each from the last; the block-in is the last of them. A unit in
    `smooth` (picked by hand, as #214's `say`) is also told that what is left has no texture: the blanket's knit
    stayed when only its stitches were named."""
    folder = OUT / picture / "renders"
    folder.mkdir(parents=True, exist_ok=True)
    ms = stages(us, d, n, far)
    P, new, cost = P_of(picture, ms[-1]), {}, 0.0
    none = np.zeros(P.shape[:2], bool)
    for m in ms[::-1]:
        if not set(us[m]["things"]) & set(us[n]["things"]):  # another thing's unit in the row: as #214 asked for it
            kind = vc.kind_of(us, m, d["behind"])
            raw, info = peel.render("gpt-image", P, vc.prompt_for(d["painter"], us, m, d["behind"]), folder,
                                    f"w4_U{m:02d}", "low")
            cost += info["cost_usd"]
            P = new[m - 1] = vc.erase_one(P, raw, kind == "bare", none)[0]
            continue
        if m == n + 1:  # the request that leaves the block-in: way 1's
            text = request(d, us, steps, n, 1)
        else:
            text = vc.prompt_for(d["painter"], us, m, d["behind"], again=1)
            at = text.rindex(END)
            text = text[:at] + (SMOOTH if m in smooth else "") + not_yet(us, steps, m) + text[at:]
        # way 1's own render of the block-in was made from #214's picture; this one is made from the new one
        name = f"w4_U{m:02d}" if len(ms) > 1 else f"w1_U{m:02d}"
        if any(k in smooth for k in ms if k >= m):  # made from a picture a smooth request left
            name = name.replace("w4_", "w4s_")
        raw, info = peel.render("gpt-image", P, text, folder, name, "low")
        cost += info["cost_usd"] if len(ms) > 1 else 0.0
        # every stage's render is kept over the whole thing, as the block-in's is: the chain's guard keeps only what
        # changed by a lot, and threw away a render that took the blanket's knit off (smooth yellow for knitted yellow)
        P = keep(picture, n, P, raw)
        new[m - 1] = P
    return new, {"cost_usd": cost}


def assemble(picture: str, name: str, new: dict[int, np.ndarray]) -> Path:
    """#214's chain with the pictures in `new` in place of its own, in runs/block-in/<name>/<picture>/. The changes
    of the units from the lowest new picture to the one over the highest are measured again; every other file is
    #214's, so the last picture is still the finish."""
    d, us, _ = setup(picture)
    assert not any(vc.kind_of(us, m, d["behind"]) == "bare" for m in range(min(new), len(us))), "bare canvas over it"
    src, folder = CHAINS / picture, OUT / name / picture
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for f in src.glob("[PDC][0-9][0-9].*"):
        shutil.copy(f, folder / f.name)
    low, top = min(new), max(new) + 1
    assert set(new) == set(range(low, top)), "the new pictures must be units in a row"
    P = {top: P_of(picture, top), low - 1: P_of(picture, low - 1), **new}
    # a unit's change is every pixel that differs, not only the ones that differ by a lot (`diff_mask`): a flat coat
    # is close in color to some of the brushwork over it, and those patches would stay in the block-in's picture.
    # A new picture is #214's own outside what was rendered or laid again, so this is never wider than the thing.
    D = {m: bs.halo((P[m] != P[m - 1]).any(2)) for m in range(low, top + 1)}
    for m in range(low, top + 1):
        np.save(folder / f"D{m:02d}.npy", D[m])
        np.save(folder / f"C{m:02d}.npy", ws.core_mask(P[m - 1], P[m], D[m]))
        Image.fromarray(P[m]).save(folder / f"P{m:02d}.png")
    return folder


def build(picture: str, name: str) -> dict:
    """v3_combined's own `build`, on the chain in runs/block-in/<name>/."""
    was = vc.OUT
    vc.OUT = OUT / name
    try:
        _, _, info = vc.build(picture)
    finally:
        vc.OUT = was
    return info


def thing_steps(us: list[dict], steps: list[dict], n: int) -> list[int]:
    """The block-in's step and every later step on its thing."""
    return [i for i in range(us[n]["steps"][0], len(steps)) if set(fw.things_of(steps[i])) & set(us[n]["things"])]


def seen(folder: Path, steps: list[dict]) -> dict[str, float]:
    """The share of the canvas each step changes by enough to see: 9 Lab units or more (the guard's WEAK) after the
    guard's blur, from one step picture to the next. `changed` in build.json counts any pixel 6 levels off, so a
    thing rendered again reads as all changed."""
    out, last = {}, None
    for i, s in enumerate(steps):
        img = np.array(Image.open(folder / "steps" / f"{i + 1:02d}_{s['id']}.png").convert("RGB"))
        lab = bs.ol.lab(cv2.GaussianBlur(img, (0, 0), ws.BLUR)).astype(np.float32)
        if last is not None:
            out[str(i + 1)] = round(float((np.sqrt(((lab - last) ** 2).sum(2)) >= ws.WEAK).mean()), 4)
        last = lab
    return out


def run(picture: str, ns: list[int], ways: list[int], smooth: tuple[int, ...] = (), far: bool = False) -> dict:
    """Each way on each block-in of the picture, one chain a way with all of them in it."""
    d, us, steps = setup(picture)
    kept = json.loads((CHAINS / picture / "build.json").read_text())
    out = {"picture": picture, "units": ns, "steps": {str(n): [i + 1 for i in thing_steps(us, steps, n)] for n in ns},
           "ids": {str(i + 1): steps[i]["id"] for n in ns for i in thing_steps(us, steps, n)},
           "changed": {"214": {str(r["n"]): r["changed"] for r in kept["rows"]}},
           "seen": {"214": seen(CHAINS / picture, steps)}, "cost_usd": {}, "checks": {}}
    for way in ways:
        new, cost = {}, 0.0
        for n in ns:
            if way == 4:
                new[n], info = every_stage(picture, n, d, us, steps, smooth, far)
            else:
                one, info = block_in(picture, n, way, d, us, steps)
                new[n] = {n: one}
            cost += info["cost_usd"]
        folder = None
        for n in ns:  # one `assemble` a block-in, on the same folder
            folder = assemble_more(picture, f"way{way}", new[n], first=(n == ns[0]))
        info = build(picture, f"way{way}")
        out["changed"][f"way{way}"] = {str(r["n"]): r["changed"] for r in info["rows"]}
        out["seen"][f"way{way}"] = seen(OUT / f"way{way}" / picture, steps)
        out["cost_usd"][f"way{way}"] = round(cost, 4)
        out["checks"][f"way{way}"] = {k: info[k] for k in ("final_gap", "outside_unit_max", "steps_that_change_little")}
        print(way, WAYS[way], folder, out["cost_usd"][f"way{way}"], flush=True)
    (OUT / picture).mkdir(parents=True, exist_ok=True)
    f = OUT / picture / "try.json"
    was = json.loads(f.read_text()) if f.exists() else {}
    for k in ("changed", "seen", "cost_usd", "checks"):
        out[k] = {**(was.get(k) or {}), **out[k]}
    f.write_text(json.dumps(out, indent=1))
    return out


def assemble_more(picture: str, name: str, new: dict[int, np.ndarray], first: bool) -> Path:
    """`assemble`, kept when a second block-in of the same picture goes into the same chain."""
    global CHAINS
    folder = OUT / name / picture
    if first:
        return assemble(picture, name, new)
    was, hold = CHAINS, OUT / name / "_hold"
    if hold.exists():
        shutil.rmtree(hold)
    (hold / picture).parent.mkdir(parents=True, exist_ok=True)
    folder.rename(hold / picture)
    CHAINS = hold
    try:
        return assemble(picture, name, new)
    finally:
        CHAINS = was
        shutil.rmtree(hold)


def sheet(picture: str, ns: list[int], ways: list[int], width: int = 300, per_line: int = 5) -> Path:
    """The steps of each block-in's thing: #214's row, then a row a way, the share of the canvas each step changes
    written on it."""
    d, us, steps = setup(picture)
    t = json.loads((OUT / picture / "try.json").read_text())
    idx = sorted({i for n in ns for i in thing_steps(us, steps, n)})
    rows = []
    for at in range(0, len(idx), per_line):
        for tag, folder in [("214", CHAINS / picture)] + [(f"way{w}", OUT / f"way{w}" / picture) for w in ways]:
            cells = []
            for i in idx[at:at + per_line]:
                img = np.array(Image.open(folder / "steps" / f"{i + 1:02d}_{steps[i]['id']}.png").convert("RGB"))
                img = cv2.resize(img, (width, round(width * img.shape[0] / img.shape[1])), interpolation=cv2.INTER_AREA)
                bar = np.full((26, width, 3), 40, np.uint8)
                label = f"{'#214' if tag == '214' else tag} step {i + 1}: {100 * t['seen'][tag][str(i + 1)]:.1f}%"
                cv2.putText(bar, label, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
                cells.append(np.vstack([bar, img]))
            row = np.hstack(cells)
            rows.append(np.pad(row, ((0, 0), (0, per_line * width - row.shape[1]), (0, 0)), constant_values=255))
    path = OUT / picture / f"sheet-{'-'.join(map(str, ns))}.jpg"
    Image.fromarray(np.vstack(rows)).save(path, quality=88)
    return path


def lesson(cmd: str, picture: str, final: bool = False):
    """v3_combined's `lesson`, `merge` and `page` on way 4's chain: the lesson goes in runs/block-in/way4/lessons/.
    `lesson` also copies #214's words for every stage whose pictures are the same, so only the changed stages go to
    a writer."""
    was = vc.OUT
    vc.OUT = OUT / "way4"
    try:
        if cmd == "merge":
            return vc.merge(picture, final)
        if cmd == "page":
            return vc.page(picture)
        new = vc.make_lesson(picture)
    finally:
        vc.OUT = was
    old = was / "lessons" / new.name
    todo = []
    for stage in sorted((new / "trials" / "facts").glob("stage-*")):
        ids = [s["id"] for s in json.loads((stage / "steps.json").read_text())["steps"]]
        names = [f.name for f in new.glob("[0-9][0-9]_*.png") if f.name[3:-4] in ids]
        px = [np.array(Image.open(side / f).convert("RGB")).astype(np.int16) for f in names for side in (new, old)]
        # the same to the eye: a picture after a changed unit differs from #214's by a rim of soft pixels
        same = all((np.abs(a - b).max(2) > peel.MOVED).mean() < 0.0005 for a, b in zip(px[::2], px[1::2]))
        if same and (old / "trials" / "facts" / stage.name / "out.json").exists():
            shutil.copy(old / "trials" / "facts" / stage.name / "out.json", stage / "out.json")
        else:
            todo.append(stage.name)
    return {"lesson": str(new), "stages_to_write": todo}


def grade_folders(pictures: list[str], out: Path, seed: int = 217) -> dict:
    """The blind A/B round (v3_combined's `grade_folders`), #214's lesson against way 4's: two folders a picture,
    sides drawn from the seed and swapped for the second grader, the key beside `out`, never in it."""
    import random

    sys.path.insert(0, str(vc.BENCH))
    import packet

    out = Path(out).resolve()
    if vc.ROOT in out.parents or out == vc.ROOT:
        raise SystemExit("the grading folders must be outside the repository")
    rng = random.Random(seed)
    key: dict = {"round": "s217-block-in", "seed": seed, "pictures": {}, "folders": {}}
    jobs = []
    for pic in pictures:
        order = ["214", "way4"] if rng.random() < 0.5 else ["way4", "214"]
        jobs += [(pic, "g1", order), (pic, "g2", order[::-1])]
    names = [f"pair-{k + 1:02d}" for k in range(len(jobs))]
    rng.shuffle(names)
    out.mkdir(parents=True, exist_ok=True)
    for name, (pic, g, order) in zip(names, jobs):
        sides = {"214": vc.OUT / "lessons" / f"{pic}-combined", "way4": OUT / "way4" / "lessons" / f"{pic}-combined"}
        folder = out / name
        if folder.exists():
            shutil.rmtree(folder)
        for side, which in zip("AB", order):
            packet.build_one(sides[which], folder / side)
        shutil.copy(vc.BENCH / "ab_grader.md", folder / "ab_grader.md")
        key["pictures"].setdefault(pic, {})[g] = {"A": order[0], "B": order[1], "folder": name}
        key["folders"][name] = f"{pic}-{g}"
    out.with_name(out.name + ".key.json").write_text(json.dumps(key, indent=1))
    return key


def results() -> dict:
    """What's kept in git: each picture's try.json and its renders' requests and costs."""
    out = {"issue": 217, "pictures": {}}
    spent = 0.0
    for f in sorted(OUT.glob("*/try.json")):
        t = json.loads(f.read_text())
        renders = []
        for r in sorted((f.parent / "renders").glob("*.json")):
            m = json.loads(r.read_text())
            renders.append({"name": r.stem, "cost_usd": m["cost_usd"], "seconds": m["seconds"], "prompt": m["prompt"]})
            spent += m["cost_usd"]
        out["pictures"][t["picture"]] = {**t, "renders": renders}
    out["render_cost_usd"] = round(spent, 4)
    (HERE / "v3_block_in.json").write_text(json.dumps(out, indent=1) + "\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("prompts", "try", "sheet"):
        p = sub.add_parser(cmd)
        p.add_argument("picture")
        p.add_argument("units", help="the block-ins' units, comma-separated")
        p.add_argument("--ways", default="1,2,3")
        p.add_argument("--far", action="store_true", help="way 4: later stages of the thing that aren't in a row too")
        p.add_argument("--smooth", default="", help="way 4: units whose request also says what is left has no texture")
    sub.add_parser("results")
    for cmd in ("lesson", "merge", "page"):
        p = sub.add_parser(cmd)
        p.add_argument("picture")
        p.add_argument("--final", action="store_true")
    p = sub.add_parser("grade-folders")
    p.add_argument("pictures", help="comma-separated")
    p.add_argument("out", type=Path, help="a folder outside the repository")
    args = ap.parse_args()
    if args.cmd == "results":
        print(results()["render_cost_usd"])
        return
    if args.cmd in ("lesson", "merge", "page"):
        print(json.dumps(lesson(args.cmd, args.picture, args.final), indent=1)[:3000])
        return
    if args.cmd == "grade-folders":
        grade_folders(args.pictures.split(","), args.out)
        print(f"{args.out}: the key is beside it, not in it")
        return
    ns, ways = [int(x) for x in args.units.split(",")], [int(x) for x in args.ways.split(",")]
    if args.cmd == "prompts":
        d, us, steps = setup(args.picture)
        for n in ns:
            for way in (1, 2):
                print(f"unit {n}, way {way}:\n   ", request(d, us, steps, n, way))
    elif args.cmd == "try":
        t = run(args.picture, ns, ways, tuple(int(x) for x in args.smooth.split(",") if x), args.far)
        for n in ns:
            for i in t["steps"][str(n)]:
                print(i, t["ids"][str(i)], {k: v[str(i)] for k, v in t["seen"].items()})
    elif args.cmd == "sheet":
        print(sheet(args.picture, ns, ways))


if __name__ == "__main__":
    main()
