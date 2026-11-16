"""How well the fault counter agrees with the owner (#165, S0c).

    python spike/experiments/bench/agreement.py --packets DIR [--scores spike/experiments/bench/scores/<round>.json] [--out report.json]

Reads the counter's results (DIR/<packet>/faults.json, written by a fresh reviewer from fault_counter.md), the packet
key (DIR/key.json: packet -> lesson folder) and the owner's scores from the A/B page (ab_page.py import). Lessons are
matched by lesson folder name.

Per lesson: the weighted fault count (blocker 3, major 2, minor 1) and per class, beside the owner's three 1-5
scores. Across lessons, Spearman's rank correlation, sign turned so higher means the counter agrees:
  - all faults            against the mean of the three scores
  - class A               against (a) "the step pictures look like a real half-done painting"
  - classes C, E, F       against (b) "I could paint each step from its words"
  - classes A, C, D, E    against (c) "the pictures, paints and words agree"
Per step: the owner's "worst step" taps against the counter. A step is the counter's pick when it has a blocker or
major fault. Reported as agreement over all steps (both flag it or both don't), how many of the owner's worst steps
the counter flagged (recall), how many of the counter's flagged steps the owner tapped (precision), and how many
owner worst steps are in the counter's own worst_steps. In pair mode also: does the side with fewer weighted faults
match the owner's preference.

Lessons with no owner scores are listed as "not scored yet"; with none at all, every correlation says so.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchlib import CLASSES, SEVERITY, read_json, write_json  # noqa: E402

NOT_SCORED = "not scored yet"
GROUPS = {"all": ("ABCDEFGH", "mean"), "A": ("A", "real"), "CEF": ("CEF", "paintable"), "ACDE": ("ACDE", "agree")}
FLAG = 2  # a step the counter flags: a fault of this weight or more (major, blocker)


def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman's rho with average ranks for ties; None when it can't be told (fewer than 3, or no spread)."""
    if len(xs) < 3:
        return None
    rx, ry = _rank(xs), _rank(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    if not sx or not sy:
        return None
    return round(sxy / (sx * sy), 3)


def _faults(result: dict) -> list[tuple[int | None, dict]]:
    out = [(s.get("n"), f) for s in result.get("steps") or [] for f in s.get("faults") or []]
    out += [(None, f) for f in result.get("lesson_faults") or []]
    return out


def lesson_faults(result: dict) -> dict:
    """Counts and weights of one counter result, recomputed from its faults (not taken from its own counts)."""
    by_class = {c: 0 for c in CLASSES}
    weight = {c: 0 for c in CLASSES}
    steps: dict[int, int] = {}
    for n, f in _faults(result):
        c = str(f.get("class", "")).upper()
        if c not in by_class:
            continue
        w = SEVERITY.get(str(f.get("severity", "")).lower(), 1)
        by_class[c] += 1
        weight[c] += w
        if n is not None:
            steps[n] = max(steps.get(n, 0), w)
    return {"count": by_class, "weight": weight, "total": sum(by_class.values()), "weighted": sum(weight.values()),
            "flagged_steps": sorted(n for n, w in steps.items() if w >= FLAG),
            "worst_steps": [int(n) for n in result.get("worst_steps") or []],
            "steps": len(result.get("steps") or [])}


def owner_lessons(scores: dict | None) -> dict[str, dict]:
    """{lesson folder: {real, paintable, agree, mean, worst, would_paint, side, picture, prefer}} from a scores JSON."""
    out = {}
    for p in (scores or {}).get("pictures") or []:
        for side, folder in (p.get("lessons") or {}).items():
            sc = (p.get("scores") or {}).get(side) or {}
            vals = [sc.get(k) for k in ("real", "paintable", "agree")]
            done = all(isinstance(v, int) for v in vals)
            out[folder] = {"picture": p.get("picture"), "side": side, "real": sc.get("real"),
                           "paintable": sc.get("paintable"), "agree": sc.get("agree"),
                           "mean": round(sum(vals) / 3, 2) if done else None, "scored": done,
                           "worst": sorted(int(w["n"]) for w in sc.get("worst_steps") or [] if "n" in w),
                           "would_paint": sc.get("would_paint"), "prefer": p.get("prefer")}
    return out


def agree(packets: Path, scores: dict | None) -> dict:
    key = read_json(Path(packets) / "key.json")
    if not key:
        raise FileNotFoundError(f"{packets}/key.json is missing: make the packets with packet.py")
    owner = owner_lessons(scores)
    lessons, missing = {}, []
    for pid, info in sorted(key["packets"].items()):
        result = read_json(Path(packets) / pid / "faults.json")
        if result is None:
            missing.append(pid)
            continue
        f = lesson_faults(result)
        o = owner.get(info["lesson"])
        lessons[info["lesson"]] = {"packet": pid, "picture": info["picture"], "faults": f,
                                   "owner": o if o and o["scored"] else NOT_SCORED}
    scored = {k: v for k, v in lessons.items() if v["owner"] != NOT_SCORED}
    report = {"lessons": lessons, "counter_missing": missing, "scored": len(scored), "correlations": {}}
    for name, (classes, score) in GROUPS.items():
        if not scored:
            report["correlations"][name] = NOT_SCORED
            continue
        xs = [-sum(v["faults"]["weight"][c] for c in classes) for v in scored.values()]
        ys = [v["owner"][score] for v in scored.values()]
        rho = spearman(xs, ys)
        report["correlations"][name] = {"against": score, "classes": classes, "n": len(xs),
                                        "rho": rho if rho is not None else "too few lessons or no spread"}
    report["steps"] = _steps(scored) if scored else NOT_SCORED
    report["preference"] = _preference(lessons, owner) if scored else NOT_SCORED
    return report


def _steps(scored: dict) -> dict:
    both = total = owner_n = counter_n = hit = in_worst = 0
    for v in scored.values():
        n_steps = v["faults"]["steps"]
        mine, theirs = set(v["faults"]["flagged_steps"]), set(v["owner"]["worst"])
        for n in range(1, n_steps + 1):
            total += 1
            both += (n in mine) == (n in theirs)
        owner_n += len(theirs)
        counter_n += len(mine)
        hit += len(mine & theirs)
        in_worst += len(theirs & set(v["faults"]["worst_steps"]))
    return {"steps": total, "agree": both, "agree_share": round(both / total, 3) if total else None,
            "owner_worst": owner_n, "counter_flagged": counter_n, "both": hit,
            "recall": round(hit / owner_n, 3) if owner_n else None,
            "precision": round(hit / counter_n, 3) if counter_n else None,
            "owner_worst_in_counter_worst": in_worst}


def _preference(lessons: dict, owner: dict) -> dict | str:
    by_pic: dict[str, dict] = {}
    for folder, o in owner.items():
        if folder in lessons and o.get("prefer"):
            by_pic.setdefault(o["picture"], {"prefer": o["prefer"]})[o["side"]] = lessons[folder]["faults"]["weighted"]
    rows = []
    for pic, d in sorted(by_pic.items()):
        if "A" not in d or "B" not in d:
            continue
        counter = "same" if d["A"] == d["B"] else ("A" if d["A"] < d["B"] else "B")
        rows.append({"picture": pic, "owner": d["prefer"], "counter": counter, "agree": counter == d["prefer"]})
    if not rows:
        return "single mode: no preferences to compare"
    return {"pictures": rows, "agree": sum(r["agree"] for r in rows), "of": len(rows)}


def table(report: dict) -> str:
    lines = ["lesson | packet | faults (weighted) | A B C D E F G H | owner a/b/c | worst (owner / counter)"]
    for folder, v in report["lessons"].items():
        f, o = v["faults"], v["owner"]
        own = NOT_SCORED if o == NOT_SCORED else f"{o['real']}/{o['paintable']}/{o['agree']}"
        worst = "-" if o == NOT_SCORED else f"{o['worst']} / {f['flagged_steps']}"
        lines.append(f"{folder} | {v['packet']} | {f['total']} ({f['weighted']}) | "
                     f"{' '.join(str(f['count'][c]) for c in CLASSES)} | {own} | {worst}")
    lines.append("")
    for name, c in report["correlations"].items():
        lines.append(f"rho {name}: {c if isinstance(c, str) else c['rho']}"
                     + ("" if isinstance(c, str) else f" (n {c['n']}, against {c['against']})"))
    s = report["steps"]
    lines.append("steps: " + (s if isinstance(s, str) else
                              f"{s['agree']} of {s['steps']} agree; owner worst {s['owner_worst']}, counter flagged "
                              f"{s['counter_flagged']}, both {s['both']}"))
    if report["counter_missing"]:
        lines.append(f"no faults.json yet: {', '.join(report['counter_missing'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--packets", required=True, help="the folder packet.py made, with each reviewer's faults.json")
    ap.add_argument("--scores", help="the owner's scores (spike/experiments/bench/scores/<round>.json)")
    ap.add_argument("--out", help="write the report JSON here too")
    a = ap.parse_args(argv)
    scores = read_json(Path(a.scores)) if a.scores else None
    try:
        report = agree(Path(a.packets), scores)
    except FileNotFoundError as err:
        print(json.dumps({"problems": [str(err)]}))
        return 1
    if a.out:
        write_json(Path(a.out), report)
    print(table(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
