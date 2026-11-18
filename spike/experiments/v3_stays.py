"""Spike for #218 (pipeline v3): a render changes what it wasn't asked to, and nothing catches it.

Not part of the pipeline. The requests that name what stays, the left-standing measure and the look pictures are in
`v3_combined.py` (`--stays`). This file runs the checks over every render at hand: #214's three chains
(runs/combined/, the thrown renders and the leaves' probe included) and #218's chain (runs/stays/).

    python spike/experiments/v3_stays.py measures            # every measure tried, a row a render; no render
    python spike/experiments/v3_stays.py cores               # a change inside another unit's core, a row a unit
    python spike/experiments/v3_stays.py check-folders <a folder outside the repo>   # blind looks for the checkers
    python spike/experiments/v3_stays.py results <that folder>                        # writes v3_stays.json

Words:
    stray     a change a render made to a thing it wasn't asked to change (the far woods, when the bushes went).
    left      a thing a render was asked to remove and left standing, whole or in part.
    look      one picture a render: before, after, and the before with the kept change tinted (`look` in v3_combined).

The renders known to be bad, from docs/spikes/v3-combined-round2.md, are in KNOWN. Every other render is counted as
good, which is not quite true: #214 kept renders nobody looked at this closely.
"""

from __future__ import annotations

import argparse
import json
import random
import re
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
import v3_whole_stages as ws  # noqa: E402
import v4_forward as fw  # noqa: E402

OLD, NEW = vc.BENCH / "runs" / "combined", vc.BENCH / "runs" / "stays"
KNOWN = {  # (run, picture, the render's file stem): what is wrong with it
    ("214", "birch-grove", "thrown01_U08"): "stray",  # the bushes went, and the far woods were painted again
    ("214", "birch-grove", "probe/U15"): "stray",  # the fallen leaves went, and the rock with them
    ("214", "highland-cow", "U16rr"): "stray",  # the tall grass came off, and a few bush rows were drawn again
    ("214", "birch-grove", "thrown09_U02"): "left",  # the far firs: the dark ones right of the middle stayed
}
PICTURES = ("birch-grove", "highland-cow", "sleeping-cat")


def im(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB"))


def renders() -> list[dict]:
    """Every render at hand: #214's kept and thrown ones, the leaves' probe, and #218's chain."""
    out = []
    for run, root, pictures in (("214", OLD, PICTURES), ("218", NEW, ("birch-grove",))):
        for pic in pictures:
            files = sorted((root / pic).glob("*U[0-9][0-9]*.json"))
            if run == "214" and pic == "birch-grove":
                files.append(root / pic / "probe" / "U15.json")
            for f in files:
                stem = ("probe/" if f.parent.name == "probe" else "") + f.stem
                out.append({"run": run, "picture": pic, "stem": stem, "path": f.with_suffix(""),
                            "unit": int(re.search(r"U(\d\d)", f.stem).group(1)),
                            "known": KNOWN.get((run, pic, stem), "")})
    return out


def setup(picture: str, stays: bool) -> tuple[dict, list[dict], list[dict]]:
    vc.STAYS = stays
    d = vc.load(picture)
    return d, vc.units(d["painter"], vc.flats(d)), fw.flat(d["painter"])


def pair(r: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(the picture the render was made from, the render at its size, canvas that was already bare)."""
    src, raw = im(Path(str(r["path"]) + "_in.png")), im(Path(str(r["path"]) + "_raw.png"))
    if raw.shape != src.shape:
        raw = cv2.resize(raw, (src.shape[1], src.shape[0]), interpolation=cv2.INTER_AREA)
    return src, raw, np.abs(src.astype(int) - np.array(ff.CANVAS)).max(2) <= 2


# ---------------------------------------------------------------------------
# The measures tried
# ---------------------------------------------------------------------------


def lab(a: np.ndarray) -> np.ndarray:
    return bs.ol.lab(cv2.GaussianBlur(a, (0, 0), ws.BLUR)).astype(np.float32)


def measure(d: dict, us: list[dict], steps: list[dict], r: dict) -> dict:
    """One render's numbers. Three ways to see a stray change with no outline, and the left-standing measure:
    apart        the share of the canvas in pieces of the change not joined to its biggest piece;
    weak_pieces  of those, the ones where under a quarter of the pixels changed by STRONG (a restyle, not a removal);
    off_color    the share of the canvas, in solid patches of the change, where the paint that was there is far from
                 every paint the unit lays (the unit's paints fitted to the change from the plan's rough colors);
    left         `left_standing` in v3_combined.py."""
    n = r["unit"]
    src, raw, frozen = pair(r)
    D = ws.diff_mask(src, raw, None, frozen)
    kind = vc.kind_of(us, n, d["behind"])
    out = {"run": r["run"], "picture": r["picture"], "render": r["stem"], "unit": n, "kind": kind,
           "things": us[n]["things"], "known": r["known"], "changed": round(float(D.mean()), 4)}
    if not D.any():
        return {**out, "apart": 0.0, "weak_pieces": 0.0, "off_color": 0.0, "left": 0.0}
    a, b = lab(src), lab(raw)
    moved = np.sqrt(((a - b) ** 2).sum(2))
    k, labels, stats, _ = cv2.connectedComponentsWithStats(D.astype(np.uint8), connectivity=8)
    pieces = sorted(((stats[i][4] / D.size, float((moved[labels == i] >= ws.STRONG).mean())) for i in range(1, k)), reverse=True)
    names = vc.unit_paints(steps, us[n])
    hexes = fw.fit_paints(src, D, {p: d["seeds"][p] for p in names})
    far = np.min([np.sqrt(((a - ff.hex_lab(hexes[p])) ** 2).sum(2)) for p in names], axis=0) > 22
    off = cv2.morphologyEx((D & far).astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    return {**out, "apart": round(float(sum(s for s, _ in pieces[1:])), 4),
            "weak_pieces": round(float(sum(s for s, f in pieces[1:] if f < 0.25 and s >= 0.001)), 4),
            "off_color": round(float(off.mean()), 4),
            "left": vc.left_standing(src, raw, D, frozen) if kind != "back" else None}


def measures() -> list[dict]:
    rows, cache = [], {}
    for r in renders():
        key = (r["picture"], r["run"] == "218")
        if key not in cache:
            cache[key] = setup(*key)
        d, us, steps = cache[key]
        if r["unit"] < len(us):
            rows.append(measure(d, us, steps, r))
            print(json.dumps(rows[-1]), flush=True)
    return rows


def chains() -> dict[str, tuple[str, dict[int, Path]]]:
    """The chains that can be put together from the files: #214's kept three, and the birch grove's first (A: the
    bushes' first render and the seven made from it) and second (B: the firs left standing)."""
    b = OLD / "birch-grove"
    kept = {n: b / (f"U{n:02d}" + ("r" if n in (2, 8) else "")) for n in range(1, 19)}
    out = {"birch-grove, kept": ("birch-grove", kept),
           "birch-grove, first (the bushes' stray)": ("birch-grove", {**kept, **{8 - i: b / f"thrown{i + 1:02d}_U{8 - i:02d}" for i in range(8)}}),
           "birch-grove, second (firs left)": ("birch-grove", {**kept, 2: b / "thrown09_U02", 1: b / "thrown10_U01"}),
           "highland-cow": ("highland-cow", {n: OLD / "highland-cow" / (f"U{n:02d}" + ("rr" if n == 16 else "")) for n in range(1, 17)}),
           "sleeping-cat": ("sleeping-cat", {n: OLD / "sleeping-cat" / f"U{n:02d}" for n in range(1, 15)})}
    return out


def cores() -> list[dict]:
    """The issue's first idea, which needs the whole chain: of each unit's change, the share of the canvas that lands,
    in solid patches, where another thing's unit was on top before it (`on_other`); and the most of any earlier
    unit's core the change covers (`most_of_a_core`). A unit that comes back to a thing should score near nothing on
    the first; it doesn't tell the bad renders from the good ones."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    rows = []
    for name, (pic, files) in chains().items():
        d, us, _ = setup(pic, False)
        frozen = np.zeros(d["finish"].shape[:2], bool)
        D, C = {}, {}
        for n in range(len(us) - 1, 0, -1):
            src, raw, _ = pair({"path": files[n]})
            kind = vc.kind_of(us, n, d["behind"])
            D[n] = ws.diff_mask(src, raw, None, frozen)
            out, grown = vc.erase_one(src, raw, kind == "bare", frozen)
            if kind == "bare":
                frozen |= grown
            C[n] = grown if kind == "bare" else ws.core_mask(out, src, grown)
        C[0] = ~frozen
        for n in range(1, len(us)):
            top = np.zeros(frozen.shape, np.int32)
            for m in range(n):
                top[C[m]] = m
            other = [m for m in range(n) if not set(us[m]["things"]) & set(us[n]["things"])]
            on = cv2.morphologyEx((D[n] & np.isin(top, other)).astype(np.uint8), cv2.MORPH_OPEN, k) > 0
            most = max((float((D[n] & C[m]).sum() / C[m].sum()) for m in other if m and C[m].mean() > 0.001), default=0.0)
            rows.append({"chain": name, "unit": n, "kind": vc.kind_of(us, n, d["behind"]), "things": us[n]["things"],
                         "render": files[n].name, "changed": round(float(D[n].mean()), 4),
                         "on_other": round(float(on.mean()), 4), "most_of_a_core": round(most, 3)})
            print(json.dumps(rows[-1]), flush=True)
    return rows


# ---------------------------------------------------------------------------
# The looks, read blind
# ---------------------------------------------------------------------------


def check_folders(out: Path, seed: int = 218, per: int = 20) -> dict:
    """Every render's look, for checkers who don't know which are bad: folders set-01, set-02, ... of about `per`
    looks each, one picture's renders together, their order and names (r01.jpg, ...) drawn from the seed. Each has
    asked.json (what went and what was to stay, a row a look) and the brief. The key goes beside `out`, never in it,
    and `out` must be outside the repository."""
    import shutil

    out = Path(out).resolve()
    if vc.ROOT in out.parents or out == vc.ROOT:
        raise SystemExit("the looks must be outside the repository")
    rng = random.Random(seed)
    key: dict = {"round": "s218-stays", "seed": seed, "sets": {}}
    by_pic: dict[str, list[dict]] = {}
    for r in renders():
        by_pic.setdefault(r["picture"], []).append(r)
    sets = []
    for pic, rs in by_pic.items():
        rng.shuffle(rs)
        parts = max(1, round(len(rs) / per))
        sets += [rs[i::parts] for i in range(parts)]
    cache = {}
    if out.exists():
        shutil.rmtree(out)
    for s, rs in enumerate(sets):
        folder = out / f"set-{s + 1:02d}"
        folder.mkdir(parents=True)
        rows = []
        for i, r in enumerate(rs):
            k = (r["picture"], r["run"] == "218")
            if k not in cache:
                cache[k] = setup(*k)
            d, us, _ = cache[k]
            src, raw, frozen = pair(r)
            kind = vc.kind_of(us, r["unit"], d["behind"])
            after, D = vc.erase_one(src, raw, kind == "bare", frozen)
            name = f"r{i + 1:02d}"
            Image.fromarray(vc.look(src, after, D)).save(folder / f"{name}.jpg", quality=88)
            what = vc.asked(d, us, r["unit"])
            rows.append({"look": name, "goes": what["goes"], "stays": what["stays"]})
            key["sets"].setdefault(folder.name, {})[name] = {k2: r[k2] for k2 in ("run", "picture", "stem", "unit", "known")}
        (folder / "asked.json").write_text(json.dumps(rows, indent=1))
        shutil.copy(HERE / "v3_stays_checker.md", folder / "checker.md")
    out.with_name(out.name + ".key.json").write_text(json.dumps(key, indent=1))
    return key


def results(out: Path) -> dict:
    """What's kept in git (v3_stays.json): the measures, the cores, #218's chain, and the checkers' answers (each
    set's answers.json, written by its checker) against the key."""
    out = Path(out).resolve()
    key = json.loads(out.with_name(out.name + ".key.json").read_text())
    read = []
    for folder, looks in sorted(key["sets"].items()):
        answers = {a["look"]: a for a in json.loads((out / folder / "answers.json").read_text())}
        for name, r in sorted(looks.items()):
            a = answers[name]
            read.append({**r, "set": folder, "look": name, "stray": a["stray"], "left": a["left"], "why": a.get("why", "")})
    er = json.loads((NEW / "birch-grove" / "erase.json").read_text())
    kept = {"issue": 218, "known": [{"run": k[0], "picture": k[1], "render": k[2], "what": v} for k, v in KNOWN.items()],
            "left_line": vc.LEFT, "measures": measures(), "cores": cores(), "checkers": read,
            "chain_218": {"picture": "birch-grove", "renders": er["renders"], "cost_usd": er["cost_usd"],
                          "thrown": er["thrown"], "thrown_cost_usd": er["thrown_cost_usd"], "redone": er["redone"],
                          "render_seconds": er["render_seconds"], "ask_again": er["ask_again"],
                          "rows": [{**{k: r[k] for k in ("unit", "kind", "things", "steps", "redo", "erased_share",
                                                          "left_standing", "ask_again", "seconds", "cost_usd")},
                                    "request": json.loads((NEW / "birch-grove" / (f"U{r['unit']:02d}" + "r" * r["redo"] + ".json")).read_text())["prompt"]}
                                   for r in er["rows"]]}}
    (HERE / "v3_stays.json").write_text(json.dumps(kept, indent=1) + "\n")
    return kept


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("measures")
    sub.add_parser("cores")
    for cmd in ("check-folders", "results"):
        p = sub.add_parser(cmd)
        p.add_argument("out", type=Path, help="a folder outside the repository")
    args = ap.parse_args()
    if args.cmd == "measures":
        measures()
    elif args.cmd == "cores":
        cores()
    elif args.cmd == "check-folders":
        key = check_folders(args.out)
        print({k: len(v) for k, v in key["sets"].items()}, "the key is beside the folder, not in it")
    elif args.cmd == "results":
        r = results(args.out)
        print(len(r["measures"]), "renders measured;", len(r["checkers"]), "looks read")


if __name__ == "__main__":
    main()
