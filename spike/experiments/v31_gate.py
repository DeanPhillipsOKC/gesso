"""v3.1's gate (#279; `docs/design/pipeline-v3.1.md`, section 13): the three bench lessons made by `/paint-lesson` on
the branch, put in the frozen bench's shape so v3's yardstick reads them, and the blind A/B folders against v3's.

    .venv/bin/python spike/experiments/v31_gate.py bench --lesson output/<cow> --lesson output/<cat> --lesson output/<birch>
    .venv/bin/python spike/experiments/v31_gate.py ab --out <folder outside the repo>
    .venv/bin/python spike/experiments/v31_gate.py ab-import <folder>
    .venv/bin/python spike/experiments/v31_gate.py report

`bench` writes `spike/experiments/bench/v31-gate/<picture>/` as `bench/v3-words/` is laid out (packet.py's packet,
`RUN`, `data/`), with each step's lines as the page shows them: the six lines with their labels, the "As in step N"
line after Start, every step of a stage under its stage's line and the stage's end above its last step (as #267's
packets had it), and the lesson's opening. The student test then reads it:

    .venv/bin/python spike/experiments/v4_student.py --bench spike/experiments/bench/v31-gate \
        --results spike/experiments/v31_gate/student.json --work <tmp>/gesso-v31-gate prepare
    ... carry --condition words; grade-carry --solo words; pick --condition words; pick --condition header

`ab` makes two blind folders a picture (`bench/ab_grader.md`'s A/ and B/), the new lesson on side A in one and side
B in the other, and the key beside them, never in them. Each lesson keeps its own pictures: v3's and v3.1's lessons
were made from scratch, so a grader sees both the words and the pictures differ (two lessons from scratch differ
enough to decide a grader, `docs/spikes/v4-cost-cuts.md`). A grader is a fresh Opus context given one folder and
the brief. `ab-import` reads each folder's `grade.json` into `v31_gate.json` through the key.

Experiment code: it reads lessons and the bench and changes no tool.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / "bench"))
sys.path.insert(0, str(ROOT / "spike"))

import packet as pk  # noqa: E402
from benchlib import read_json, write_json  # noqa: E402

BENCH = HERE / "bench" / "v31-gate"
V3 = HERE / "bench" / "v3-words"
RESULTS = HERE / "v31_gate.json"
PICTURES = ["highland-cow", "sleeping-cat", "birch-grove"]
LABELS = {"first": "First", "start": "Start", "strokes": "Strokes", "inside": "Where the paint sits",
          "leave": "Leave", "stop": "Stop when"}


def page_lines(lines: list[dict]) -> list[str]:
    """A step's lines as the page shows them, each with its label (page2.six_lines)."""
    out = []
    for x in lines:
        t = (x.get("text") or "").strip()
        if not t:
            continue
        out.append(f"As in step {x.get('step')}: {t}" if x.get("kind") == "back" else f"{LABELS.get(x.get('kind'), x.get('kind'))}: {t}")
    return out


def opening_text(op: dict, cards: dict[str, str]) -> str:
    out = []
    if op.get("welcome"):
        out += [op["welcome"], ""]
    if op.get("light"):
        out += [f"The light: {op['light']}", ""]
    if op.get("skills"):
        out.append("What this painting teaches:")
        for sk in op["skills"]:
            steps = ", ".join(str(n) for n in sk.get("steps") or [])
            out.append(f"- {cards.get(sk.get('card'), sk.get('card'))} (steps {steps}): {sk.get('how', '')}")
    if op.get("road"):
        out += ["", f"The way there: {op['road']}"]
    return "\n".join(out).strip()


def card_names() -> dict[str, str]:
    import yaml_files
    out = {}
    for p in sorted((ROOT / "techniques" / "strokes").glob("*.yaml")):
        d = yaml_files.read(p) or {}
        out[p.stem] = d.get("name") or p.stem.replace("-", " ")
    return out


def md(picture: str, steps: list[dict], opening: str) -> str:
    out = [f"# Lesson: {picture.replace('-', ' ')}", "",
           "The step pictures are in steps/, and each step beside the one before it in pairs/.", ""]
    if opening:
        out += ["## Before you start", "", opening, ""]
    for s in steps:
        if s.get("intro"):
            out += [s["intro"], ""]
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
        if s.get("tip"):
            out.append(f"Tip: {s['tip']}")
        out.append("")
    return "\n".join(out)


def put_photo(les: Path, dest: Path) -> bool:
    """The photo the lesson was painted from, cropped to the canvas. packet.py looks for photo.png, which a v3.1 run
    doesn't write; the fitted photo (or the canvas frame) is in the image model's frame, as the steps are."""
    from PIL import Image
    for name in ("00_canvas_fit.png", "00_canvas_frame.png"):
        if (les / name).exists():
            pk._save(pk.crop_canvas(Image.open(les / name), pk.canvas_box(les)), dest / "photo.jpg", pk.SIDE)
            return True
    return False


def bench(args):
    cards = card_names()
    for les in [Path(x).resolve() for x in args.lesson]:
        data = read_json(les / "lesson.json") or {}
        if not data.get("opening"):
            raise SystemExit(f"{les.name}: no opening in lesson.json; is it a sealed v3.1 lesson?")
        pic = pk.picture_of(les)
        dest = BENCH / pic
        if dest.exists():
            shutil.rmtree(dest)
        packet = pk.build_one(les, dest)
        shutil.rmtree(dest / "pairs", ignore_errors=True)  # as bench/v3-words: the pairs are the steps side by side
        if not (dest / "photo.jpg").exists() and put_photo(les, dest):
            packet["photo"] = "photo.jpg"
        text = read_json(les / "text.json") or {}
        back_step = {}  # lesson.json's back line may not carry its step; text.json's does
        for t in text.get("steps") or []:
            for x in t.get("lines") or []:
                if x.get("kind") == "back":
                    back_step[t.get("stage_id")] = x.get("step")
        by_id = {s["id"]: s for s in data.get("stages") or []}
        stage_of, last_of = {}, {}
        for g in data.get("groups") or []:
            for sid in g.get("steps") or []:
                stage_of[sid] = g
            if g.get("steps"):
                last_of[g["steps"][-1]] = g
        sl = data.get("stage_lines") or {}
        for s in packet["steps"]:
            lines = [dict(x) for x in by_id[s["id"]].get("lines") or []]
            for x in lines:
                if x.get("kind") == "back" and x.get("step") is None:
                    x["step"] = back_step.get(s["id"])
            s["lines"] = page_lines(lines)
            s["tip"] = ""
            g = stage_of.get(s["id"])
            o = sl.get(g["id"], {}) if g else {}
            intro = f"This stage, {g['name']}: {o.get('for', '')}".strip() if g and o.get("for") else ""
            if s["id"] in last_of and o.get("end"):
                intro = (intro + f" By its end: {o['end']}").strip()
            s["intro"] = intro
        packet["opening"] = opening_text(data["opening"], cards)
        write_json(dest / "packet.json", packet)
        (dest / "lesson.md").write_bytes(md(pic, packet["steps"], packet["opening"]).encode("utf-8"))
        (dest / "RUN").write_text(les.name + "\n")
        d = dest / "data"
        (d / "words").mkdir(parents=True)
        for f in ("plan.json", "text.json", "lesson.json", "mixes.json", "canvas.json", "review.json"):
            if (les / f).exists():
                shutil.copy(les / f, d / f)
        for f in ("sheet.json", "dropped.json"):
            if (les / "words" / f).exists():
                shutil.copy(les / "words" / f, d / "words" / f)
        if (les / "words" / "lesson" / "rounds.json").exists():
            shutil.copy(les / "words" / "lesson" / "rounds.json", d / "words" / "rounds.json")
        print(f"{pic}: {len(packet['steps'])} steps, {dest.relative_to(ROOT)}")


def side_folder(src: Path, dest: Path):
    """One side of an A/B folder: the packet's files, with the pairs made from the steps (bench/v3-words leaves
    them out)."""
    from PIL import Image
    dest.mkdir(parents=True)
    for f in ("photo.jpg", "finish.jpg", "lesson.md", "packet.json"):
        shutil.copy(src / f, dest / f)
    shutil.copytree(src / "steps", dest / "steps", copy_function=shutil.copyfile)  # no file dates: they tell the sides apart
    packet = read_json(src / "packet.json")
    before = None
    for s in packet["steps"]:
        img = Image.open(src / s["picture"]).convert("RGB")
        pk._save(pk._pair(before, img), dest / s.get("pair", f"pairs/{s['n']:02d}.jpg"), pk.PAIR_SIDE * 2 + 16)
        before = img
    for f in ("packet.json",):
        p = read_json(dest / f)
        p.pop("write_to", None)
        write_json(dest / f, p)


def ab(args):
    out = Path(args.out).resolve()
    if out == ROOT or ROOT in out.parents:
        raise SystemExit("make the A/B folders outside the repository")
    out.mkdir(parents=True, exist_ok=True)
    key = {}
    for pic in PICTURES:
        for g, new_side in ((1, "A"), (2, "B")):
            f = out / f"{pic}-g{g}"
            if f.exists():
                shutil.rmtree(f)
            f.mkdir()
            old_side = "B" if new_side == "A" else "A"
            side_folder(BENCH / pic, f / new_side)
            side_folder(V3 / pic, f / old_side)
            shutil.copy(HERE / "bench" / "ab_grader.md", f / "ab_grader.md")
            key[f.name] = {"picture": pic, "grader": g, new_side: "v3.1", old_side: "v3"}
    write_json(out.parent / f"{out.name}.key.json", key)
    print(json.dumps({"folders": sorted(key), "key": str(out.parent / f"{out.name}.key.json")}, indent=1))


def ab_import(args):
    out = Path(args.folder).resolve()
    key = read_json(out.parent / f"{out.name}.key.json")
    st = read_json(RESULTS) or {}
    st["ab"] = []
    for name, k in sorted(key.items()):
        g = read_json(out / name / "grade.json")
        if not g:
            print(f"{name}: no grade.json", file=sys.stderr)
            continue
        prefer = g.get("prefer")
        st["ab"].append({"picture": k["picture"], "grader": k["grader"], "A": k["A"], "B": k["B"],
                         "preferred": k[prefer] if prefer in ("A", "B") else "none",
                         "scores": {k[s]: v for s, v in (g.get("scores") or {}).items() if s in ("A", "B")},
                         "note": g.get("note", "")})
    write_json(RESULTS, st)
    for r in st["ab"]:
        print(f"{r['picture']} g{r['grader']}: prefers {r['preferred']}  ({r['note'][:120]})")


def solo(path: Path) -> dict:
    ss = read_json(path) or {}
    g = {}
    for r in ss.get("carry_grades", []):
        if r.get("solo") and r["condition"] == "words":
            g.setdefault((r["picture"], r["n"]), []).append(r["grade"])
    return {k: sum(v) / len(v) for k, v in g.items()}


def report(args):
    import numpy as np
    new = solo(HERE / "v31_gate" / "student.json")
    old = solo(HERE / "v4_student.json")
    st = read_json(RESULTS) or {}
    rows = {}
    for pic in PICTURES:
        a = [v for (p, _n), v in new.items() if p == pic]
        b = [v for (p, _n), v in old.items() if p == pic]
        rows[pic] = {"v3.1": round(float(np.mean(a)), 2) if a else None, "steps": len(a),
                     "v3": round(float(np.mean(b)), 2) if b else None}
    allnew = [v for v in new.values()]
    allold = [v for v in old.values() if v is not None]
    rows["all"] = {"v3.1": round(float(np.mean(allnew)), 2) if allnew else None,
                   "v3": round(float(np.mean(allold)), 2) if allold else None}
    st["student"] = rows
    write_json(RESULTS, st)
    print(json.dumps({"student": rows, "ab": [(r["picture"], r["grader"], r["preferred"]) for r in st.get("ab", [])]},
                     indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bench")
    b.add_argument("--lesson", action="append", required=True)
    a = sub.add_parser("ab")
    a.add_argument("--out", required=True)
    i = sub.add_parser("ab-import")
    i.add_argument("folder")
    sub.add_parser("report")
    args = ap.parse_args(argv)
    {"bench": bench, "ab": ab, "ab-import": ab_import, "report": report}[args.cmd](args)


if __name__ == "__main__":
    main()
