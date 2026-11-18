"""A version 3 lesson as the later tools read it, in version 2's shape (docs/design/pipeline-v3.md, sections 7 to 9).

    make(lesson, plan, finish) -> build-steps for a version 3 lesson: step pictures, shapes, the plan's v2 shape
    read(lesson)               -> what it kept, for step-aids, draft-text, mix, check and publish

`build-steps` on a version 3 lesson fits the paints, cuts the step pictures from the chain, and keeps beside them
what the later tools need: v3/plan.json (the plan in version 2's shape, a part a unit), parts/owner.png (which unit
each pixel belongs to), v3/masks.npz (where each step lays paint) and v3/build.json (the checks' numbers). The
later tools read those; they never cut a version 3 lesson's steps themselves. What was kept goes stale when
plan.json or the chain changes: `read` refuses it then, and says to run build-steps again.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

import erase3
import plan2
import plan3
import steps3


class Stale(Exception):
    """What build-steps kept for a version 3 lesson is missing or was made from another plan or chain."""


def digest(lesson: Path) -> str:
    """What the kept files were made from: plan.json, the chain's numbers and pictures, and the finish."""
    lesson = Path(lesson)
    h = hashlib.sha256()
    for path in [lesson / "plan.json", lesson / "99_finish.png", lesson / "chain" / "chain.json",
                 *sorted((lesson / "chain").glob("[PDC][0-9][0-9].png"))]:
        h.update(path.name.encode() + b"\0" + (path.read_bytes() if path.exists() else b"") + b"\0")
    return h.hexdigest()


def _hashes(lesson: Path, names: list[str]) -> dict[str, str]:
    """What build-steps wrote, by its bytes: a step picture or a shape changed by anything else is stale."""
    files = [lesson / n for n in names] + [lesson / "parts" / "owner.png", lesson / "v3" / "masks.npz",
                                           lesson / "v3" / "plan.json"]
    return {str(f.relative_to(lesson)): hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else "" for f in files}


def step_names(plan: dict) -> list[str]:
    return [f"{i + 1:02d}_{s['id']}.png" for i, s in enumerate(plan3.steps(plan))]


def make(lesson: Path, plan: dict, finish: np.ndarray, save=None) -> dict:
    """Write the step pictures and everything `read` returns; return the build (steps3.build) with the v2-shaped
    plan as "plan" and the shapes as "owner". `save(rgb, path)` writes a step picture (tools.save_png)."""
    lesson = Path(lesson)
    us = plan3.units(plan)
    ch = erase3.load(lesson, plan)
    if ch[-1]["P"].shape != finish.shape:
        raise erase3.Refused("the chain doesn't match 99_finish.png's size: run erase again")
    built = steps3.build(plan, finish, ch)
    owner = steps3.owner_from(ch)
    view = steps3.as_v2(plan, us, ch, built["hexes"], owner, finish)
    wrong = plan2.problems(view)
    if wrong:  # a fault in as_v2, not in the plan: the version 2 tools would misread the lesson
        raise erase3.Refused("this plan can't be put in the shape the later tools read (report it; plan-check passed "
                             "it): " + " | ".join(wrong[:3]))
    names = step_names(plan)
    for old in lesson.glob("[0-9][0-9]_*.png"):
        if not old.name.startswith(("00_", "98_", "99_")):
            old.unlink()
    for name, pic in zip(names, built["pictures"]):
        (save or (lambda rgb, path: Image.fromarray(rgb).save(path)))(pic, lesson / name)
    (lesson / "parts").mkdir(exist_ok=True)
    (lesson / "v3").mkdir(exist_ok=True)
    Image.fromarray(owner.astype(np.uint8)).save(lesson / "parts" / "owner.png")
    np.savez_compressed(lesson / "v3" / "masks.npz", **{f"m{i:02d}": m for i, m in enumerate(built["masks"])},
                        **{f"s{n:02d}": s for n, s in enumerate(steps3.shapes(ch, owner))})
    (lesson / "v3" / "plan.json").write_text(json.dumps(view, indent=1) + "\n", encoding="utf-8")
    kept = {k: built[k] for k in ("rows", "paints", "final_gap", "outside_unit_max", "from_its_paints_median", "little")}
    (lesson / "v3" / "build.json").write_text(json.dumps({"made_from": digest(lesson), "steps": names,
                                                          "files": _hashes(lesson, names), **kept}, indent=1),
                                              encoding="utf-8")
    return {**built, "plan": view, "owner": owner, "steps": names}


def read(lesson: Path, pictures: bool = True) -> dict:
    """What build-steps kept: {"plan" (version 2's shape), "owner", "pictures", "masks", "shapes" (each unit's shape,
    for the fact sheet), "rows", "build"}. Raises Stale when it is missing or older than the plan or the chain."""
    lesson = Path(lesson)
    again = f"run build-steps --lesson {lesson}"
    need = [lesson / "v3" / "plan.json", lesson / "v3" / "build.json", lesson / "v3" / "masks.npz",
            lesson / "parts" / "owner.png"]
    if not all(p.exists() for p in need):
        raise Stale(f"no step pictures yet for this version 3 lesson: {again} (after erase)")
    build = json.loads(need[1].read_text(encoding="utf-8"))
    if build.get("made_from") != digest(lesson):
        raise Stale(f"plan.json or the chain changed since the step pictures were made: {again} again")
    missing = [n for n in build["steps"] if not (lesson / n).exists()]
    if missing:
        raise Stale(f"missing step pictures {missing[:3]}: {again} again")
    changed = [n for n, h in _hashes(lesson, build["steps"]).items() if build.get("files", {}).get(n) != h]
    if changed:
        raise Stale(f"{changed[0]} isn't the file build-steps wrote: {again} again")
    kept = np.load(need[2])
    out = {"plan": json.loads(need[0].read_text(encoding="utf-8")), "build": build, "rows": build["rows"],
           "owner": np.array(Image.open(need[3])).astype("int32"),
           "masks": [kept[k] for k in sorted(k for k in kept.files if k.startswith("m"))],
           "shapes": [kept[k] for k in sorted(k for k in kept.files if k.startswith("s"))]}
    if pictures:
        out["pictures"] = [np.array(Image.open(lesson / n).convert("RGB")) for n in build["steps"]]
    return out
