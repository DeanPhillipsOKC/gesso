"""Spike for #253 (v4's Y3 and C1): the cost baseline on three bench pictures, then the cuts that don't touch the words.

The lessons are made by `v4_loop.py run <photo> [--cuts ...]`. This file sums their logs and runs the blind graders.

    .venv/bin/python spike/experiments/v4_cost_cuts.py summary <lesson> [<lesson> ...]   # writes v4_cost_cuts.json
    .venv/bin/python spike/experiments/v4_cost_cuts.py ab --round <name> --pair <baseline lesson> <cut lesson> [...]

`ab` is the owner's rubric (`bench/ab_grader.md`), two graders a picture with the sides swapped between them, on two
whole lessons of one photo: each has its own finish, step pictures and words, since a cut to the plan's writer can
change the plan. Which lesson is A is drawn from the round's name and the picture, then swapped for the second
grader, and the grader is told nothing of how either was made. Experiment code: it writes only
`spike/experiments/v4_cost_cuts.json` and changes no tool.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "bench"))

import v4_loop  # noqa: E402
from benchlib import lesson_steps  # noqa: E402

OUT = HERE / "v4_cost_cuts.json"
PICTURES = ["highland-cow", "sleeping-cat", "birch-grove"]


def load() -> dict:
    return json.loads(OUT.read_text()) if OUT.exists() else {"runs": {}, "ab": []}


def save(st: dict):
    OUT.write_text(json.dumps(st, indent=1) + "\n")


def picture_of(lesson: Path) -> str:
    return lesson.name.split("_v4loop_")[0]


# --------------------------------------------------------------------------------------------------------- summary
def summary(lessons: list[str]):
    st = load()
    for l in lessons:
        lesson = Path(l).resolve()
        r = v4_loop.report(lesson)
        state = json.loads((lesson / "v4" / "state.json").read_text())
        plan = json.loads((lesson / "plan.json").read_text())
        st["runs"][lesson.name] = {
            "picture": picture_of(lesson), "cuts": r["cuts"], "sealed": bool(state.get("sealed")),
            "calls": r["calls"], "charged_usd": r["claude_cost_usd"], "api_usd": r["api_usd"],
            "api_usd_no_cc": r["api_usd_no_cc"], "renders_usd": r["image_cost_usd"], "tokens": r["tokens"],
            "claude_seconds": r["claude_seconds"], "minutes": round(sum((state.get("phases") or {}).values()) / 60, 1),
            "steps": sum(len(s["steps"]) for s in plan["stages"]), "stages": len(plan["stages"]),
            "renders": (state.get("plan_check") or {}).get("renders"), "merged": len(state.get("merged") or []),
            "checker_marks": [len(x) for x in state.get("checker") or []], "picks": state.get("picks"),
            "by_helper": {k: {f: v[f] for f in ("calls", "cost_usd", "api_usd", "api_usd_no_cc", "output")}
                          for k, v in r["by_helper"].items()},
            "plan_calls": [{"label": c["label"], "sent": c["input_tokens"] + c["cache_write_tokens"],
                            "read": c["cache_read_tokens"], "output": c["output_tokens"],
                            "cost_usd": c["cost_usd"], "api_usd": round(c["api_usd"], 4)}
                           for c in json.loads((lesson / "v4" / "calls.json").read_text())
                           if c["helper"] == "plan-writer"]}
    save(st)
    for name, r in sorted(st["runs"].items(), key=lambda x: (",".join(x[1]["cuts"]), x[1]["picture"])):
        print(f"{name:44} {','.join(r['cuts']) or 'baseline':34} charged ${r['charged_usd']:.2f}  api "
              f"${r['api_usd']:.2f}  plan ${r['by_helper'].get('plan-writer', {}).get('api_usd', 0):.2f}  "
              f"renders ${r['renders_usd'] or 0:.2f}  {r['steps']} steps")


# --------------------------------------------------------------------------------------------- the blind graders
def lesson_words(s: dict) -> str:
    paints = "; ".join(f"{p['name']}" + (f" ({p['recipe']})" if p.get("recipe") else "") for p in s["paints"])
    out = [f"Step {s['n']}: {s['name']}", f"Paints: {paints}", f"Brush: {s['brushes']}"]
    out += [f"{i}. {x}" for i, x in enumerate(s["lines"], 1)]
    if s["tip"]:
        out.append(f"Tip: {s['tip']}")
    return "\n".join(out)


def ab_one(rnd: str, base: Path, cut: Path, g: int) -> dict:
    from v4_loop import Message, call_claude, cost, last_json
    pic = picture_of(base)
    first = random.Random(f"{rnd}-{pic}").randrange(2)
    sides = [base, cut] if (first + g) % 2 else [cut, base]
    brief = (HERE / "bench" / "ab_grader.md").read_text()
    brief = brief.replace("You were given a folder.", "You were given everything in this message, in place of a "
                          "folder.").replace("Read only that folder.", "Read only this message.")
    m = Message().text(f'<file name="ab_grader.md">\n{brief}\n</file>')
    m.text("Each lesson below has its own finish and step pictures: the two were made separately, so they may differ "
           "in their pictures as well as their words. Under each step's words is its picture (the canvas after the "
           "step). Write grade.json's contents in your reply; the program saves it.")
    photo = next(p for p in (base / "photo.png", base / "photo.jpg") if p.exists())
    m.picture(photo, "photo.jpg", max_side=1024)
    for side, lesson in zip("AB", sides):
        steps = lesson_steps(lesson)
        m.text(f"===== Lesson {side}: {len(steps)} steps. Its finish:")
        m.picture(lesson / "99_finish.png", f"{side}/finish.jpg", max_side=768)
        for s in steps:
            m.text(lesson_words(s))
            m.picture(s["image"], f"{side}/steps/{s['n']:02d}.jpg", max_side=640)
    m.text('Reply with grade.json as one ```json block (the brief\'s shape, `"picture": "' + pic + '"`), then the '
           "scores, the preference and how sure you are.")
    cwd = Path(tempfile.gettempdir()) / "gesso-v4-cost-cuts"
    cwd.mkdir(exist_ok=True)
    r = call_claude(m.blocks, "You have no tools. You grade one blind A/B pair, in the owner's place.", cwd=cwd,
                    cache="none")
    try:
        a = last_json(r["text"])
    except ValueError:
        a = {}
    who = {"A": sides[0].name, "B": sides[1].name}
    prefer = a.get("prefer")
    return {"round": rnd, "picture": pic, "grader": g, "A": who["A"], "B": who["B"], "prefer": prefer,
            "preferred": ("cut" if who[prefer] == cut.name else "baseline") if prefer in ("A", "B") else "none",
            "scores": {("cut" if who[k] == cut.name else "baseline"): v for k, v in (a.get("scores") or {}).items()
                       if k in who},
            "note": a.get("note", ""), "cost_usd": round(cost(r["usage"]), 4), "seconds": r["seconds"],
            "pictures": m.pictures}


def ab(rnd: str, pairs: list[tuple[str, str]]):
    st = load()
    done = {(x["round"], x["picture"], x["grader"]) for x in st["ab"]}
    jobs = [(rnd, Path(b).resolve(), Path(c).resolve(), g) for b, c in pairs for g in (1, 2)
            if (rnd, picture_of(Path(b)), g) not in done]
    with ThreadPoolExecutor(6) as ex:
        for f in [ex.submit(ab_one, *j) for j in jobs]:
            try:
                out = f.result()
            except Exception as e:  # noqa: BLE001
                print(f"  failed: {e}", file=sys.stderr)
                continue
            st = load()
            st["ab"].append(out)
            save(st)
            print(f"{out['round']} {out['picture']} g{out['grader']}: prefers {out['preferred']} "
                  f"(${out['cost_usd']:.2f})")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summary")
    s.add_argument("lessons", nargs="+")
    a = sub.add_parser("ab")
    a.add_argument("--round", required=True)
    a.add_argument("--pair", nargs=2, action="append", required=True, metavar=("BASELINE", "CUT"))
    args = ap.parse_args(argv)
    if args.cmd == "summary":
        summary(args.lessons)
    else:
        ab(args.round, [tuple(p) for p in args.pair])


if __name__ == "__main__":
    main()
