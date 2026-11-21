"""Pipeline v4's gate (#299; `docs/design/pipeline-v4.md`, section 12): three hands-off lessons, each run once to its
chain and built twice from it, with the rule (`build-steps --stops`) and without, each build with its own words,
finisher and seal. This puts the six lessons in the frozen bench's shape (v31_gate.bench), picks the steps the
student test runs on, makes the blind A/B folders (the rule's side against the other) and reports.

    .venv/bin/python spike/experiments/v4_gate.py bench --side on --lesson output/<cow> --lesson ... (three)
    .venv/bin/python spike/experiments/v4_gate.py bench --side off --lesson output/<cow-off> --lesson ... (three)
    .venv/bin/python spike/experiments/v4_gate.py steps
    # then, for each side and picture (the steps `steps` printed):
    .venv/bin/python spike/experiments/v4_student.py --bench spike/experiments/bench/v4-gate/<side> \\
        --results spike/experiments/v4_gate/student-<side>.json --work <tmp>/gesso-v4-gate-<side> prepare
    ... carry --condition words --picture <p> --steps <n,...> --rep 1   (and --rep 2; --rep 3 when `report` asks)
    ... grade-carry --solo words
    .venv/bin/python spike/experiments/v4_gate.py ab --out <folder outside the repo>
    .venv/bin/python spike/experiments/v4_gate.py ab-import <folder>
    .venv/bin/python spike/experiments/v4_gate.py report

`steps` reads the two sides' step pictures: a step is tested when its picture differs between the sides, and so is
the step after each run of such steps (the step after a stopped run, whose words the spike found wrong). A lesson
whose pictures are the same either way (nothing stopped) has no tested step, and `steps` says whether they are the
same byte for byte (the gate's check).

`report` gives each picture's student score on its tested steps, a side, and the three together: the gate fails
when the rule's side is lower by 0.25 or more, and at two carries a side it asks for a third when the gap is from
0.15 to 0.25, either end included; with three, the gap decides. The design says "lower by 0.25 or more" fails and
"between 0.15 and 0.25" asks for a third, which overlap at exactly 0.25. The gate's two carries came out there, the
script as first written called it a fail, and the inclusive reading was chosen after seeing it (the owner's call,
docs/spikes/v4-gate.md). Every grade is a carry graded alone (`grade-carry --solo words`).

Experiment code: it reads lessons and the bench and changes no tool.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "bench"))
sys.path.insert(0, str(ROOT / "spike"))

import v31_gate  # noqa: E402
from benchlib import read_json, write_json  # noqa: E402

BENCH = HERE / "bench" / "v4-gate"
OUT = HERE / "v4_gate"
RESULTS = HERE / "v4_gate.json"
PICTURES = ["highland-cow", "sleeping-cat", "birch-grove"]
SIDES = ("on", "off")
FAIL, THIRD = 0.25, 0.15


def bench(args):
    v31_gate.BENCH = BENCH / args.side
    v31_gate.bench(args)


def pictures(side: str, pic: str) -> list[bytes]:
    packet = read_json(BENCH / side / pic / "packet.json")
    return [(BENCH / side / pic / s["picture"]).read_bytes() for s in packet["steps"]]


def lesson_pictures(side: str, pic: str) -> list[bytes]:
    """The lesson's own step pictures (PNG), from the folder the bench was made from."""
    les = ROOT / "output" / (BENCH / side / pic / "RUN").read_text().strip()
    return [f.read_bytes() for f in sorted(les.glob("[0-9][0-9]_*.png"))]


def steps(args):
    st = read_json(RESULTS) or {}
    out = {}
    for pic in PICTURES:
        on, off = pictures("on", pic), pictures("off", pic)
        if len(on) != len(off):
            raise SystemExit(f"{pic}: {len(on)} steps with the rule, {len(off)} without")
        changed = [i + 1 for i, (a, b) in enumerate(zip(on, off)) if a != b]
        tested = set(changed)
        for n in changed:
            if n + 1 not in changed and n + 1 <= len(on):
                tested.add(n + 1)  # the step after each run of changed steps
        same_png = None
        if not changed:
            a, b = lesson_pictures("on", pic), lesson_pictures("off", pic)
            same_png = bool(a) and a == b
        on_les = ROOT / "output" / (BENCH / "on" / pic / "RUN").read_text().strip()
        build = read_json(on_les / "v3" / "build.json") or {}
        out[pic] = {"steps": len(on), "changed": changed, "tested": sorted(tested),
                    "same_pictures": not changed, "same_png": same_png,
                    "spared_canvas": build.get("spared_canvas"),
                    "stopped": [{"id": r["id"], "steps": r["steps"], "covered_by": r.get("covered_by"),
                                 "most_in": r["line"]["most"]} for r in (build.get("stops") or {}).get("stopped", [])],
                    "not_stopped": (build.get("stops") or {}).get("not_stopped", [])}
    st["steps"] = out
    write_json(RESULTS, st)
    print(json.dumps({p: {k: v[k] for k in ("changed", "tested", "same_pictures", "same_png", "spared_canvas")}
                      for p, v in out.items()}, indent=1))


def ab(args):
    out = Path(args.out).resolve()
    if out == ROOT or ROOT in out.parents:
        raise SystemExit("make the A/B folders outside the repository")
    out.mkdir(parents=True, exist_ok=True)
    key = {}
    for pic in PICTURES:
        for g, on_side in ((1, "A"), (2, "B")):
            f = out / f"{pic}-g{g}"
            if f.exists():
                shutil.rmtree(f)
            f.mkdir()
            off_side = "B" if on_side == "A" else "A"
            v31_gate.side_folder(BENCH / "on" / pic, f / on_side)
            v31_gate.side_folder(BENCH / "off" / pic, f / off_side)
            shutil.copy(HERE / "bench" / "ab_grader.md", f / "ab_grader.md")
            key[f.name] = {"picture": pic, "grader": g, on_side: "rule", off_side: "no rule"}
    write_json(out.parent / f"{out.name}.key.json", key)
    print(json.dumps({"folders": sorted(key), "key": str(out.parent / f"{out.name}.key.json")}, indent=1))


def ab_import(args):
    v31_gate.RESULTS = RESULTS
    v31_gate.ab_import(args)


def grades(side: str) -> dict:
    """Each (picture, step)'s carries graded alone, a list a step."""
    ss = read_json(OUT / f"student-{side}.json") or {}
    g = {}
    for r in ss.get("carry_grades", []):
        if r.get("solo") and r["condition"] == "words":
            g.setdefault((r["picture"], r["n"]), []).append(r["grade"])
    return g


def report(args):
    st = read_json(RESULTS) or {}
    if "steps" not in st:
        raise SystemExit("run `steps` first")
    g = {s: grades(s) for s in SIDES}
    rows, all_on, all_off = {}, [], []
    for pic in PICTURES:
        tested = st["steps"][pic]["tested"]
        per = {}
        for n in tested:
            a, b = g["on"].get((pic, n), []), g["off"].get((pic, n), [])
            per[str(n)] = {"rule": a, "no rule": b}
        mean = lambda xs: round(float(np.mean(xs)), 2) if xs else None  # noqa: E731
        on = [np.mean(g["on"][(pic, n)]) for n in tested if g["on"].get((pic, n))]
        off = [np.mean(g["off"][(pic, n)]) for n in tested if g["off"].get((pic, n))]
        all_on += on
        all_off += off
        rows[pic] = {"tested": tested, "rule": mean(on), "no rule": mean(off), "by_step": per}
    raw = float(np.mean(all_on) - np.mean(all_off)) if all_on and all_off else None  # compared unrounded
    gap = round(raw, 2) if raw is not None else None
    diffs = [np.mean(g["on"][(p, n)]) - np.mean(g["off"][(p, n)]) for p in PICTURES for n in st["steps"][p]["tested"]
             if g["on"].get((p, n)) and g["off"].get((p, n))]
    se = round(float(np.std(diffs, ddof=1) / np.sqrt(len(diffs))), 2) if len(diffs) > 1 else None
    carries = min((len(g[s][(p, n)]) for s in SIDES for p in PICTURES for n in st["steps"][p]["tested"]
                   if g[s].get((p, n))), default=0)
    if gap is None:
        verdict = None
    elif raw <= -FAIL + 1e-9 and carries >= 3:
        verdict = "fail"
    elif raw < -THIRD and carries < 3:
        verdict = "third carry"  # at two carries a side, a gap from 0.15 to 0.25 (either end) asks for a third
    else:
        verdict = "fail" if raw <= -FAIL + 1e-9 else "pass"
    rows["all"] = {"rule": round(float(np.mean(all_on)), 2) if all_on else None,
                   "no rule": round(float(np.mean(all_off)), 2) if all_off else None,
                   "gap": gap, "se": se, "steps": len(diffs), "carries": carries, "student": verdict}
    st["student"] = rows
    write_json(RESULTS, st)
    print(json.dumps({"student": {p: {k: v for k, v in r.items() if k != "by_step"} for p, r in rows.items()},
                      "ab": [(r["picture"], r["grader"], r["preferred"]) for r in st.get("ab", [])]}, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bench")
    b.add_argument("--side", choices=SIDES, required=True)
    b.add_argument("--lesson", action="append", required=True)
    sub.add_parser("steps")
    a = sub.add_parser("ab")
    a.add_argument("--out", required=True)
    i = sub.add_parser("ab-import")
    i.add_argument("folder")
    sub.add_parser("report")
    args = ap.parse_args(argv)
    {"bench": bench, "steps": steps, "ab": ab, "ab-import": ab_import, "report": report}[args.cmd](args)


if __name__ == "__main__":
    main()
