"""Spike for #207 (a v4 idea): build the painting forward from a bare canvas, a thing at a time, inspired by the
photo. There is no finished painting to cut from: the last picture of the chain is the finish.

Not part of the pipeline, and not part of v3. Stage 1 of the issue: one picture (the highland cow), a step sheet with
three rows (v2, whole-picture stages from #204, forward), and the photo beside the two finishes.

    python spike/experiments/v4_forward.py units highland-cow       # the renders the plan asks for, in order; no render
    python spike/experiments/v4_forward.py paint highland-cow       # PAID: one low render a unit, chained
    python spike/experiments/v4_forward.py paint highland-cow --redo 6    # ask for unit 6 again (and all after it)
    python spike/experiments/v4_forward.py build highland-cow       # step pictures, the three-row sheet, the finishes

Words:
    painter's plan   the plan-first plan (#172, bench/plan-first/<picture>/painter-a.json): things with no boxes,
                     stages, steps. Written before any outline. The image model never decides a step.
    unit             a run of steps in one stage on the same thing (or on things that share a step). One render a
                     unit. A thing painted in three stages (the cow's shape, its coat, its face) is three units, so
                     each is painted to suit its steps.
    C[n]             the canvas after unit n. C[-1] is bare. C[last] is the finish.
    D[n]             what unit n added: where its render differs from C[n-1] by a lot (`diff_mask` from #204, with no
                     box: the painter's plan has none).

The guard, #204's turned around: C[n] is C[n-1] outside D[n], and the render inside it. So what is already painted
can't move when the next thing arrives. Steps inside a unit are v2's flat coat and nearest-paint passes, cut from
C[n] inside D[n]; the unit's last step lays all of D[n], so the picture after it is C[n] exactly.

Pictures and numbers go in spike/experiments/bench/runs/forward/<picture>/ (git-ignored).
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
sys.path.insert(0, str(ROOT / "spike"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_steps as bs  # noqa: E402
import from_finish as ff  # noqa: E402
import outline as ol  # noqa: E402
import run as gesso_run  # noqa: E402
import v3_peel as peel  # noqa: E402
import v3_whole_stages as ws  # noqa: E402

BENCH = peel.BENCH
OUT = BENCH / "runs" / "forward"
HERE = Path(__file__).resolve().parent
SMALL = (48, 72)  # the size two pictures are shrunk to before they're compared: only the big shapes and colors are left
REFIT = 2  # rounds of "each pixel to its nearest paint, each paint to the middle of its pixels"


# ---------------------------------------------------------------------------
# The painter's plan and its units
# ---------------------------------------------------------------------------


def load(picture: str) -> dict:
    folder = BENCH / "pictures" / picture
    painter = json.loads((BENCH / "plan-first" / picture / "painter-a.json").read_text())
    fit = json.loads((BENCH / "plan-first" / picture / "plan.json").read_text())
    photo = np.array(Image.open(folder / "00_canvas_frame.png").convert("RGB"))  # the photo, cropped to the canvas
    finish = np.array(Image.open(folder / "99_finish.png").convert("RGB"))  # v2's finish: only to compare with
    seeds = json.loads((HERE / "v4_forward_paints.json").read_text()).get(picture, {})
    bands = json.loads((HERE / "v4_forward_bands.json").read_text()).get(picture, [])
    return {"picture": picture, "painter": painter, "fit": fit, "photo": photo, "photo_path": folder / "00_canvas_frame.png",
            "v2_finish": finish, "seeds": seeds, "bands": bands}


def flat(painter: dict) -> list[dict]:
    return [dict(s, stage=st["id"], stage_name=st.get("name", st["id"])) for st in painter["stages"] for s in st["steps"]]


def things_of(step: dict) -> list[str]:
    return [lay["thing"] for lay in step["lays"]]


def units(painter: dict) -> list[dict]:
    """One unit a run of steps in a stage that share a thing: {"stage", "things", "steps": [indexes]}. A step on a
    thing an earlier unit of the same stage painted joins that unit, and takes the units between with it."""
    out: list[dict] = []
    i = 0
    for st in painter["stages"]:
        mine: list[dict] = []
        for s in st["steps"]:
            t = things_of(s)
            hit = [k for k, u in enumerate(mine) if set(u["things"]) & set(t)]
            if hit:
                for late in mine[hit[0] + 1:]:
                    mine[hit[0]]["things"] += [x for x in late["things"] if x not in mine[hit[0]]["things"]]
                    mine[hit[0]]["steps"] += late["steps"]
                del mine[hit[0] + 1:]
                u = mine[hit[0]]
            else:
                u = {"stage": st["id"], "things": [], "steps": []}
                mine.append(u)
            u["things"] += [x for x in t if x not in u["things"]]
            u["steps"].append(i)
            i += 1
        out += mine
    return out


# ---------------------------------------------------------------------------
# The request for a unit
# ---------------------------------------------------------------------------


def prompt_for(painter: dict, us: list[dict], n: int, again: bool = False) -> str:
    steps = flat(painter)
    name = {t["id"]: t["name"] for t in painter["things"]}
    looks = {p["name"]: p["looks"] for p in painter["paints"]}
    u = us[n]
    mine = [steps[i] for i in u["steps"]]
    moves = " ".join(f"({k + 1}) {s['name']}: " + "; ".join(lay["what"] for lay in s["lays"]) + "."
                     for k, s in enumerate(mine))
    paints: list[str] = []
    for s in mine:
        paints += [p for p in s["paints"] if p not in paints]
    done = [t for v in us[:n] for t in v["things"]]
    later = [name[t["id"]] for t in painter["things"] if t["id"] not in done and t["id"] not in u["things"]]
    start = ("The first picture is a bare white canvas." if n == 0 else
             "The first picture is an unfinished acrylic painting on a white canvas.")
    text = (f"{start} The second picture is the photo it is being painted from: {painter['subject']}. "
            "Paint the next stage of the painting onto the first picture, and only that stage, the way a beginner "
            f"following a paint-along lesson would. The stage, as the lesson's steps: {moves} "
            "Paints, and only these: " + "; ".join(f"{p} ({looks[p]})" for p in paints) + ". "
            "Put each thing where it is in the photo, at the same size. Loose, simple acrylic brushwork with "
            "visible strokes; simplify the photo, do not copy its detail. "
            f"When the stage is done the canvas shows this: {mine[-1]['after']} ")
    if later:
        text += "Do not paint these yet, and leave no hint of them: " + "; ".join(later) + ". "
    text += ("Add nothing the steps above do not name. " if not again else
             "Add nothing the steps above do not name: no detail, light or texture that belongs to a later stage. ")
    if n:
        text += "Everything already painted keeps its exact place, shape and color: do not repaint or move it. "
    text += ("Canvas that is bare and not part of this stage stays bare: plain flat white, no paint, no wash, no "
             "sketch lines. No text, signature, watermark, frame or easel: the picture is the canvas itself, edge "
             "to edge.")
    return text


# ---------------------------------------------------------------------------
# The chain of renders
# ---------------------------------------------------------------------------


def render(canvas: np.ndarray, photo: Path, prompt: str, folder: Path, name: str, quality: str) -> tuple[np.ndarray, dict]:
    """The model's answer at the canvas's size. A render already in the folder is kept (delete it to render again)."""
    src, raw, meta = folder / f"{name}_in.png", folder / f"{name}_raw.png", folder / f"{name}.json"
    if not (raw.exists() and meta.exists()):
        Image.fromarray(canvas).save(src)
        ledger = gesso_run.Ledger()
        gesso_run.edit_image("forward", [src, photo], prompt, raw, gesso_run.size_for(src), quality, ledger)
        call = ledger.calls[-1]
        meta.write_text(json.dumps({"seconds": call["seconds"], "cost_usd": call["cost_usd"], "prompt": prompt,
                                    "quality": quality}, indent=1))
    kept = json.loads(meta.read_text())
    if kept["prompt"] != prompt:
        raise SystemExit(f"{raw} was rendered for a different request: delete {raw.name} and {meta.name}")
    got = np.array(Image.open(raw).convert("RGB"))
    if got.shape != canvas.shape:
        got = cv2.resize(got, (canvas.shape[1], canvas.shape[0]), interpolation=cv2.INTER_AREA)
    return got, kept


def add_one(canvas: np.ndarray, raw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(the canvas with what the render added, where it was added). Outside that the canvas is as it was."""
    d = ws.diff_mask(canvas, raw)
    if not d.any():
        return canvas.copy(), d
    return bs.make_background(canvas, d, raw), bs.halo(d)


def paint(picture: str, quality: str = "low", redo: tuple[int, ...] = ()) -> dict:
    """`redo`: units to ask for again with the stricter sentence (kept as U<n>r). Every later unit is rendered again
    too, since it was painted on the old canvas: their files are deleted here."""
    d = load(picture)
    painter = d["painter"]
    us = units(painter)
    folder = OUT / picture
    folder.mkdir(parents=True, exist_ok=True)
    was = json.loads((folder / "paint.json").read_text()) if (folder / "paint.json").exists() else {}
    redone = sorted(set(was.get("redone", [])) | set(redo))
    thrown = was.get("thrown", [])
    if redo:
        first = min(redo)
        for n in range(first, len(us)):
            for meta in (folder / f"U{n:02d}.json", folder / f"U{n:02d}r.json"):
                if not meta.exists() or (n == first and n not in was.get("redone", []) and meta.stem.endswith("r")):
                    continue
                kept = json.loads(meta.read_text())
                thrown.append({"unit": n, "seconds": kept["seconds"], "cost_usd": kept["cost_usd"]})
                for f in folder.glob(meta.stem + "*"):
                    if f.stem in (meta.stem, meta.stem + "_in", meta.stem + "_raw"):
                        f.rename(folder / f"thrown{len(thrown):02d}_{f.name}")
    canvas = np.empty(d["photo"].shape, np.uint8)
    canvas[:] = ff.CANVAS
    painted = np.zeros(canvas.shape[:2], bool)
    C, raws, rows = [canvas], [], []
    for n, u in enumerate(us):
        again = n in redone
        name = f"U{n:02d}" + ("r" if again else "")
        raw, info = render(C[-1], d["photo_path"], prompt_for(painter, us, n, again), folder, name, quality)
        nxt, D = add_one(C[-1], raw)
        np.save(folder / f"D{n:02d}.npy", D)
        np.save(folder / f"K{n:02d}.npy", ws.core_mask(C[-1], nxt, D) if n else D)
        Image.fromarray(nxt).save(folder / f"C{n:02d}.png")
        rows.append({"unit": n, "stage": u["stage"], "things": u["things"], "steps": [i + 1 for i in u["steps"]],
                     "redo": again, "seconds": info["seconds"], "cost_usd": info["cost_usd"],
                     "added_share": round(float(D.mean()), 4),
                     # of what was already painted, the share this unit painted over (the coat on the cow: meant;
                     # a sky painted again: not)
                     "over_painted": round(float((D & painted).sum() / max(1, painted.sum())), 4),
                     # of what was already painted and the guard kept, the share the raw render had moved
                     "raw_moved_kept": peel.moved(C[-1], raw, painted & ~D)})
        print(json.dumps(rows[-1]))
        painted |= D
        C.append(nxt)
        raws.append(raw)
    result = {"picture": picture, "quality": quality, "units": us, "redone": redone, "thrown": thrown,
              "renders": len(rows), "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
              "thrown_cost_usd": round(sum(t["cost_usd"] for t in thrown), 4),
              "render_seconds": round(sum(r["seconds"] for r in rows), 1),
              "bare_left": round(float((~painted).mean()), 4), "rows": rows}
    (folder / "paint.json").write_text(json.dumps(result, indent=1))
    ws.sheet_rows(folder / "chain.jpg", [C[1:], raws], width=256)
    return result


# ---------------------------------------------------------------------------
# Paints, fitted when the chain is done
# ---------------------------------------------------------------------------


def to_hex(rgb: np.ndarray) -> str:
    return "#" + "".join(f"{int(round(float(v))):02x}" for v in rgb)


def fit_paints(content: np.ndarray, where: np.ndarray, seeds: dict[str, str]) -> dict[str, str]:
    """Each paint's color as it is in this picture: from its seed (the plan's name for it, as a rough color), each
    pixel goes to its nearest paint and each paint to the middle of its pixels. A paint with no pixels keeps its
    seed."""
    names = list(seeds)
    hexes = dict(seeds)
    if not where.any() or len(names) < 1:
        return hexes
    px = cv2.GaussianBlur(content, (0, 0), 1.0)[where]
    lab = ol.lab(px[None])[0].astype(np.float32)
    for _ in range(REFIT):
        dist = np.stack([np.sqrt(((lab - ff.hex_lab(hexes[n])) ** 2).sum(1)) for n in names])
        near = dist.argmin(0)
        for j, n in enumerate(names):
            if (near == j).sum() >= 20:
                hexes[n] = to_hex(np.median(px[near == j], axis=0))
    return hexes


# ---------------------------------------------------------------------------
# Step pictures
# ---------------------------------------------------------------------------


def shows(fit: dict) -> dict[str, str]:
    """How the fitted plan (#172) shows each of the painter's steps: "flat" if any of its v2 steps is a flat coat."""
    out: dict[str, str] = {}
    for s in bs.flat_steps(fit):
        of = s.get("of") or s["id"]
        if s.get("show") == "flat" or of not in out:
            out[of] = s.get("show", "full")
    return out


def build(picture: str) -> tuple[list[np.ndarray], dict]:
    d = load(picture)
    painter, folder = d["painter"], OUT / picture
    us, steps, show = units(painter), flat(painter), shows(d["fit"])
    canvas = np.empty(d["photo"].shape, np.float32)
    canvas[:] = ff.CANVAS
    pictures: list[np.ndarray | None] = [None] * len(steps)
    rows: list[dict | None] = [None] * len(steps)
    fitted: dict[str, dict[str, str]] = {}
    for n, u in enumerate(us):
        content = np.array(Image.open(folder / f"C{n:02d}.png").convert("RGB"))
        D, core = np.load(folder / f"D{n:02d}.npy"), np.load(folder / f"K{n:02d}.npy")
        names: list[str] = []
        for i in u["steps"]:
            names += [p for p in steps[i]["paints"] if p not in names]
        hexes = fit_paints(content, core if core.any() else D, {p: d["seeds"][p] for p in names})
        fitted[f"U{n:02d}"] = hexes
        near = ws.nearest(content, [hexes[p] for p in names])
        for i in u["steps"]:
            s = steps[i]
            before = canvas.copy()
            how = show.get(s["id"], "full")
            if i == u["steps"][-1]:
                how, lay, where = "all", content, D  # the unit's last step: the canvas after the unit, exactly
            elif how == "flat":
                lay, where = ff.flat_paint(content, core, [hexes[p] for p in s["paints"]]), core
            else:
                how, lay, where = "pass", content, D & np.isin(near, [names.index(p) for p in s["paints"]])
            canvas = bs._lay(canvas, lay, where)
            changed = np.abs(canvas - before).max(2) > 6
            rows[i] = {"id": s["id"], "unit": n, "things": things_of(s), "show": how,
                       "painted": round(float(where.mean()), 4), "changed": round(float(changed.mean()), 4),
                       "outside_unit": round(float((changed & ~bs.halo(D)).mean()), 5)}
            pictures[i] = np.clip(canvas, 0, 255).astype(np.uint8)
    finish = np.array(Image.open(folder / f"C{len(us) - 1:02d}.png").convert("RGB"))
    gap = np.abs(pictures[-1].astype(np.int16) - finish.astype(np.int16)).max(2) > peel.MOVED
    info = {"picture": picture, "steps": len(steps), "final_gap": round(float(gap.mean()), 4),
            "outside_unit_max": max(r["outside_unit"] for r in rows),
            "steps_that_change_little": [r["id"] for r in rows if r["changed"] < 0.002],
            "close_to_photo": {"forward": closeness(finish, d["photo"]), "v2": closeness(d["v2_finish"], d["photo"]),
                               "forward_to_v2": closeness(finish, d["v2_finish"])},
            "paints": fitted, "rows": rows}
    out = folder / "steps"
    out.mkdir(exist_ok=True)
    for f in out.glob("*.png"):
        f.unlink()
    for i, (s, img) in enumerate(zip(steps, pictures)):
        Image.fromarray(img).save(out / f"{i + 1:02d}_{s['id']}.png")
    Image.fromarray(finish).save(folder / "99_finish.png")
    (folder / "build.json").write_text(json.dumps(info, indent=1))
    three_rows(folder / "steps.jpg", d, pictures)
    finishes(folder / "finishes.jpg", d, finish)
    return pictures, info


# ---------------------------------------------------------------------------
# Is it still the photo?
# ---------------------------------------------------------------------------


def closeness(picture: np.ndarray, photo: np.ndarray) -> dict:
    """How close a painting is to the photo once both are shrunk to SMALL, so only the big shapes and colors count:
    the mean color distance (Lab units; lower is closer) and how well light and dark fall in the same places
    (correlation of lightness, 1 is the same)."""
    a = ol.lab(cv2.resize(picture, SMALL, interpolation=cv2.INTER_AREA)).astype(np.float32)
    b = ol.lab(cv2.resize(photo, SMALL, interpolation=cv2.INTER_AREA)).astype(np.float32)
    la, lb = a[..., 0].ravel(), b[..., 0].ravel()
    return {"color_distance": round(float(np.sqrt(((a - b) ** 2).sum(2)).mean()), 1),
            "light_and_dark": round(float(np.corrcoef(la, lb)[0, 1]), 3)}


# ---------------------------------------------------------------------------
# Sheets to look at
# ---------------------------------------------------------------------------


def _cell(img: np.ndarray | None, label: str, width: int, like: np.ndarray) -> np.ndarray:
    pic = ws._small(img, width, like)
    bar = np.full((26, width, 3), 40 if img is not None else 255, np.uint8)
    if img is not None:
        cv2.putText(bar, label[:int(width / 8.6)], (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    return np.vstack([bar, pic])


def band_of(step_things: list[str], bands: list[dict]) -> int:
    for k, b in enumerate(bands):
        if step_things[0] in b["things"]:
            return k
    raise SystemExit(f"no band holds {step_things[0]}")


def three_rows(path: Path, d: dict, forward: list[np.ndarray], width: int = 240, per_line: int = 9) -> None:
    """Three rows a thing: v2, whole-picture stages (#204), forward. The plans differ (v2's 16 steps, the painter's
    24), so the rows are lined up by the thing being painted (v4_forward_bands.json), each picture under its own
    step number. Things are in the forward lesson's order."""
    v2 = peel.load(d["picture"])
    v2_steps = bs.flat_steps(v2["plan"])
    whole = ws.OUT / d["picture"] / "steps"
    steps = flat(d["painter"])
    like = forward[0]
    bands = d["bands"]
    cells: list[list[list[np.ndarray]]] = []  # band -> row -> cells
    for b in bands:
        rows: list[list[np.ndarray]] = [[], [], []]
        for i, s in enumerate(v2_steps):
            if s["part"] in b["v2"]:
                name = f"{i + 1:02d}_{s['id']}.png"
                rows[0].append(_cell(np.array(Image.open(v2["run"] / name).convert("RGB")), f"{i + 1} {s['id']}", width, like))
                rows[1].append(_cell(np.array(Image.open(whole / name).convert("RGB")), f"{i + 1} {s['id']}", width, like))
        for i, s in enumerate(steps):
            if bands[band_of(things_of(s), bands)] is b:
                rows[2].append(_cell(forward[i], f"{i + 1} {s['id']}", width, like))
        cells.append(rows)
    blank = _cell(None, "", width, like)
    tags = ["v2", "whole stages", "forward"]
    lines: list[list[int]] = [[]]
    for k, rows in enumerate(cells):  # bands side by side while they fit
        wide = max(len(r) for r in rows)
        if lines[-1] and sum(max(len(r) for r in cells[j]) for j in lines[-1]) + wide > per_line:
            lines.append([])
        lines[-1].append(k)
    gap = 8
    total = per_line * (width + gap)
    out = []
    for line in lines:
        head, body = [], [[], [], []]
        for k in line:
            wide = max(len(r) for r in cells[k])
            bar = np.full((34, wide * (width + gap), 3), 20, np.uint8)
            cv2.putText(bar, bands[k]["name"], (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            head.append(bar)
            for r in range(3):
                for c in range(wide):
                    cell = cells[k][r][c] if c < len(cells[k][r]) else blank
                    body[r].append(np.hstack([cell, np.full((cell.shape[0], gap, 3), 20 if c == wide - 1 else 255, np.uint8)]))
        def pad(img: np.ndarray, fill: int) -> np.ndarray:
            return np.hstack([img, np.full((img.shape[0], total - img.shape[1], 3), fill, np.uint8)]) if img.shape[1] < total else img
        out.append(pad(np.hstack(head), 20))
        for r in range(3):
            row = pad(np.hstack(body[r]), 255)
            tag = np.full((row.shape[0], 30, 3), (40, 40, 40) if r < 2 else (150, 60, 20), np.uint8)
            label = np.full((30, row.shape[0], 3), tag[0, 0], np.uint8)
            cv2.putText(label, tags[r], (10, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
            out.append(np.hstack([cv2.rotate(label, cv2.ROTATE_90_COUNTERCLOCKWISE), row]))
            out.append(np.full((gap, total + 30, 3), 20, np.uint8))
    full = max(o.shape[1] for o in out)
    out = [np.hstack([np.full((o.shape[0], full - o.shape[1], 3), 20, np.uint8), o]) if o.shape[1] < full else o for o in out]
    Image.fromarray(np.vstack(out)).save(path, quality=86)


def finishes(path: Path, d: dict, finish: np.ndarray, width: int = 512) -> None:
    """The photo, v2's finish and the forward finish, side by side: is it still the painter's photo?"""
    cells = [_cell(img, label, width, finish) for img, label in
             ((d["photo"], "the photo"), (d["v2_finish"], "v2's finish (whole stages ends on it too)"),
              (finish, "the forward finish"))]
    gap = np.full((cells[0].shape[0], 8, 3), 20, np.uint8)
    Image.fromarray(np.hstack([cells[0], gap, cells[1], gap, cells[2]])).save(path, quality=90)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("units", "paint", "build"):
        p = sub.add_parser(name)
        p.add_argument("picture")
        if name == "paint":
            p.add_argument("--quality", default="low")
            p.add_argument("--redo", default="", help="units to ask for again, e.g. 6; later units are rendered again too")
        if name == "units":
            p.add_argument("--prompts", action="store_true")
    args = ap.parse_args()
    if args.cmd == "units":
        d = load(args.picture)
        us = units(d["painter"])
        for n, u in enumerate(us):
            print(n, u["stage"], u["things"], [s + 1 for s in u["steps"]])
            if args.prompts:
                print("   ", prompt_for(d["painter"], us, n))
    elif args.cmd == "paint":
        r = paint(args.picture, args.quality, tuple(int(x) for x in args.redo.split(",") if x))
        print(json.dumps({k: r[k] for k in ("renders", "cost_usd", "thrown_cost_usd", "render_seconds", "bare_left")}))
    else:
        _, info = build(args.picture)
        print(json.dumps({k: info[k] for k in ("steps", "final_gap", "outside_unit_max", "steps_that_change_little",
                                               "close_to_photo")}))


if __name__ == "__main__":
    main()
