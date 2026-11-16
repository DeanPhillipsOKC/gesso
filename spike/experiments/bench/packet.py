"""Packets for the fault counter (#165, S0c): what a painter gets from a lesson, and nothing else.

    python spike/experiments/bench/packet.py --out DIR --lesson LESSON [--lesson LESSON ...] [--seed N]

For each lesson it writes DIR/<packet id>/ with:
    photo.jpg            the photo the lesson shows, cropped to the canvas
    finish.jpg           the finished painting, cropped to the canvas
    steps/NN.jpg         each step picture as the painter sees it (canvas crop, 1200 px on the long side)
    pairs/NN.jpg         step NN-1 beside step NN (step 1 beside a blank canvas), the same pictures side by side
    lesson.md            each step's name, paints with recipes, brush, numbered words and tip, as the page shows them
    packet.json          the same, structured, with the picture paths

and DIR/key.json, which maps each packet id to its lesson folder. The key stays out of the packets: hand the
reviewer only fault_counter.md and one packet folder. Packet ids are p01, p02, ... in an order drawn from the seed,
so a packet's name says nothing about which run or experiment made it. Nothing from plan.json, notes.json,
review.json, the ledger, or the run's transcript goes in.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchlib import canvas_box, crop_canvas, lesson_steps, picture_of, read_json, write_json  # noqa: E402

SIDE = 1200
PAIR_SIDE = 800
QUALITY = 88
RESULT = "faults.json"  # what the reviewer writes in its packet folder


def _save(img, path: Path, side: int) -> None:
    from PIL import Image

    img = img.convert("RGB")
    k = side / max(img.size)
    if k < 1:
        img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=QUALITY, optimize=True)


def _pair(before, after):
    from PIL import Image, ImageDraw

    after = after.convert("RGB")
    k = PAIR_SIDE / max(after.size)
    size = (round(after.width * k), round(after.height * k))
    b = before.convert("RGB").resize(size, Image.LANCZOS) if before is not None else Image.new("RGB", size, (246,) * 3)
    a = after.resize(size, Image.LANCZOS)
    gap, label = 16, 28
    out = Image.new("RGB", (size[0] * 2 + gap, size[1] + label), (255, 255, 255))
    out.paste(b, (0, label))
    out.paste(a, (size[0] + gap, label))
    d = ImageDraw.Draw(out)
    d.text((6, 6), "BEFORE (the step before)", fill=(0, 0, 0))
    d.text((size[0] + gap + 6, 6), "AFTER (this step)", fill=(0, 0, 0))
    return out


def _md(picture: str, steps: list[dict]) -> str:
    out = [f"# Lesson: {picture.replace('-', ' ')}", "",
           "The step pictures are in steps/, and each step beside the one before it in pairs/.", ""]
    for s in steps:
        out.append(f"## Step {s['n']}: {s['name']}")
        if s["group"]:
            out.append(f"Part of: {s['group']}")
        out.append(f"Picture: {s['picture']} (beside the step before: {s['pair']})")
        if s["paints"]:
            out.append("Paints:")
            out += [f"- {p['name']} ({p['hex']}): {p['recipe']}" for p in s["paints"]]
        if s["brushes"]:
            out.append(f"Brush: {s['brushes']}")
        out.append("Words:")
        out += [f"{i + 1}. {line}" for i, line in enumerate(s["lines"])]
        if s["tip"]:
            out.append(f"Tip: {s['tip']}")
        out.append("")
    return "\n".join(out)


def build_one(lesson: Path, dest: Path) -> dict:
    from PIL import Image

    lesson = Path(lesson)
    box = canvas_box(lesson)
    picture = picture_of(lesson)
    dest.mkdir(parents=True, exist_ok=True)
    for name, out in (("photo.png", "photo.jpg"), ("99_finish.png", "finish.jpg")):
        src = lesson / name
        if src.exists():
            _save(crop_canvas(Image.open(src), box), dest / out, SIDE)
    steps, before = [], None
    for st in lesson_steps(lesson):
        img = Image.open(st["image"]).convert("RGB")
        pic, pair = f"steps/{st['n']:02d}.jpg", f"pairs/{st['n']:02d}.jpg"
        _save(img, dest / pic, SIDE)
        _save(_pair(before, img), dest / pair, PAIR_SIDE * 2 + 16)
        before = img
        steps.append({"n": st["n"], "id": st["id"], "name": st["name"], "group": st["group"], "picture": pic,
                      "pair": pair, "paints": st["paints"], "brushes": st["brushes"], "lines": st["lines"],
                      "tip": st["tip"]})
    canvas = (read_json(lesson / "canvas.json") or {}).get("canvas") or {}
    packet = {"picture": picture, "canvas_in": [canvas.get("w_in"), canvas.get("h_in")],
              "photo": "photo.jpg" if (dest / "photo.jpg").exists() else None,
              "finish": "finish.jpg" if (dest / "finish.jpg").exists() else None,
              "steps": steps, "write_to": RESULT}
    write_json(dest / "packet.json", packet)
    (dest / "lesson.md").write_text(_md(picture, steps), encoding="utf-8")
    return packet


def build(lessons: list[Path], out: Path, seed: int = 165) -> dict:
    out = Path(out)
    order = list(lessons)
    random.Random(seed).shuffle(order)
    key = {}
    for i, lesson in enumerate(order):
        pid = f"p{i + 1:02d}"
        packet = build_one(Path(lesson), out / pid)
        key[pid] = {"lesson": Path(lesson).name, "picture": packet["picture"], "steps": len(packet["steps"])}
    write_json(out / "key.json", {"seed": seed, "packets": key})
    return {"out": str(out), "packets": key}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lesson", action="append", required=True, help="a published lesson folder (repeat)")
    ap.add_argument("--seed", type=int, default=165, help="the order packets are numbered in")
    a = ap.parse_args(argv)
    try:
        r = build([Path(x) for x in a.lesson], Path(a.out), a.seed)
    except FileNotFoundError as err:
        print(json.dumps({"problems": [str(err)]}))
        return 1
    print(json.dumps({**r, "problems": []}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
