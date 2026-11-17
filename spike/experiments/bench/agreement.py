"""How well the fault counter agrees with the owner (#165, S0c).

    python spike/experiments/bench/agreement.py --packets DIR [--scores spike/experiments/bench/scores/<round>.json] [--out report.json]

    e.g. the baseline, on what's committed:
    python spike/experiments/bench/agreement.py --packets spike/experiments/bench/baseline \
        --scores spike/experiments/bench/scores/baseline-1.12.1.json

Reads the packet key (DIR/key.json: packet -> lesson folder and picture), each lesson's counter result (written by a
fresh reviewer from fault_counter.md: DIR/<packet>/faults.json as packet.py lays them out, or DIR/<picture>/faults.json
as the bench keeps them), and the owner's scores from the A/B page (ab_page.py import, joined to lesson folders through
the page's answer key). Lessons are matched through the packet key by lesson folder name; a key that names one folder
twice is refused.

Per lesson: the weighted fault count (blocker 3, major 2, minor 1), per class, and per step (weighted / steps, so a
lesson with more, smaller steps doesn't score worse for it), beside the owner's three 1-5 scores. Across lessons,
Spearman's rank correlation of the per-step weighted count, sign turned so higher means the counter agrees:
  - all faults            against the mean of the three scores
  - class A               against (a) "the step pictures look like a real half-done painting"
  - classes C, E, F       against (b) "I could paint each step from its words"
  - classes A, C, D, E    against (c) "the pictures, paints and words agree"
Per step: the owner's "worst step" taps against the counter. A step is the counter's pick when it has a blocker or
major fault. A lesson the owner scored without tapping any worst step is left out here (no taps means unknown, not
"no step is bad"). Reported as agreement over those lessons' steps with Cohen's kappa beside it (most steps are
flagged by neither, so raw agreement alone flatters), how many of the owner's worst steps the counter flagged
(recall), how many of the counter's flagged steps the owner tapped (precision), and how many owner worst steps are in
the counter's own worst_steps. In pair mode also: does the side with fewer weighted faults
match the owner's preference.

Lessons with no owner scores are listed as "not scored yet"; with none at all, every correlation says so.

    --name F [--name G]   which result file to read in each lesson's folder (default faults.json). With two or more,
                          each lesson's counts are the counters' mean, and a step is flagged when at least half flag it.
    --compare F G         two counters on the same packets, against each other (repeatability): per lesson, distinct
                          faults and their spread (|a-b| over the mean), weighted counts, how many of their top-3 worst
                          steps match, and the Jaccard index of the steps each flags with a major or blocker fault,
                          over every step a fault shows in and over the step it first shows in; then the rank
                          correlation of the weighted count per step across lessons.
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
    n_steps = len(result.get("steps") or [])
    return {"count": by_class, "weight": weight, "total": sum(by_class.values()), "weighted": sum(weight.values()),
            "per_step": round(sum(weight.values()) / n_steps, 3) if n_steps else None,
            "flagged_steps": sorted(n for n, w in steps.items() if w >= FLAG),
            "worst_steps": [int(n) for n in result.get("worst_steps") or []],
            "steps": len(result.get("steps") or [])}


def check_faults(result: dict, steps: int | None = None) -> list[str]:
    """Where a faults.json doesn't fit fault_counter.md's format: [] when it does. `steps` is the packet's step count."""
    out = []
    for key in ("steps", "lesson_faults", "counts", "distinct", "worst_steps", "not_visible", "summary"):
        if key not in result:
            out.append(f"no {key}")
    rows = result.get("steps") or []
    ns = [s.get("n") for s in rows]
    if steps is not None and sorted(n for n in ns if isinstance(n, int)) != list(range(1, steps + 1)):
        out.append(f"steps should be 1 to {steps}, each once; got {len(ns)}")
    faults = _faults(result)
    ids = [f.get("id") for _, f in faults]
    if len(set(ids)) != len(ids) or None in ids:
        out.append("fault ids must be present and unique")
    for n, f in faults:
        where = f"fault {f.get('id')} (step {n})" if n is not None else f"lesson fault {f.get('id')}"
        if str(f.get("class", "")).upper() not in CLASSES:
            out.append(f"{where}: class {f.get('class')!r} isn't A to H")
        if str(f.get("severity", "")).lower() not in SEVERITY:
            out.append(f"{where}: severity {f.get('severity')!r} isn't blocker, major or minor")
        for key in ("sees", "where"):
            if not f.get(key):
                out.append(f"{where}: no {key}")
        if f.get("same_as") not in (None, *ids):
            out.append(f"{where}: same_as {f.get('same_as')!r} names no fault")
    count = {c: 0 for c in CLASSES}
    distinct = {c: 0 for c in CLASSES}
    for _, f in faults:
        c = str(f.get("class", "")).upper()
        if c in count:
            count[c] += 1
            distinct[c] += not f.get("same_as")
    for key, want in (("counts", count), ("distinct", distinct)):
        got = result.get(key)
        if isinstance(got, dict) and {c: got.get(c, 0) for c in CLASSES} != want:
            out.append(f"{key} {got} doesn't match the faults listed ({want})")
    return out


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
                           "worst": sorted(int(w["n"]) for w in sc.get("worst_steps") or [] if "n" in w) or None,
                           "would_paint": sc.get("would_paint"), "prefer": p.get("prefer")}
    return out


def _key(packets: Path) -> dict:
    key = read_json(Path(packets) / "key.json")
    if not key:
        raise FileNotFoundError(f"{packets}/key.json is missing: make the packets with packet.py")
    folders = [v["lesson"] for v in key["packets"].values()]
    if len(set(folders)) != len(folders):
        raise ValueError(f"the packet key names a lesson folder twice: {sorted({f for f in folders if folders.count(f) > 1})}")
    return key


def _result(packets: Path, pid: str, info: dict, name: str) -> dict | None:
    """One counter's result for a lesson: <packet>/<name> as packet.py lays them out, or <picture>/<name>."""
    found = read_json(Path(packets) / pid / name)
    return found if found is not None else read_json(Path(packets) / info["picture"] / name)


def _one(result: dict, steps: int | None) -> dict:
    f = lesson_faults(result)
    f["distinct_count"] = {c: sum(1 for _, x in _faults(result)
                                  if str(x.get("class", "")).upper() == c and not x.get("same_as"))
                           for c in CLASSES}
    f["distinct"] = sum(f["distinct_count"].values())
    f["format_problems"] = check_faults(result, steps)
    return f


def _mean(fs: list[dict]) -> dict:
    """Several counters' results for one lesson as one: every count is their mean, and a step is flagged when at
    least half of them flag it."""
    if len(fs) == 1:
        return fs[0]
    n = len(fs)

    def avg(xs):
        return round(sum(xs) / n, 3)

    flagged = sorted({s for f in fs for s in f["flagged_steps"]
                      if sum(s in g["flagged_steps"] for g in fs) * 2 >= n})
    worst = []
    for f in fs:
        worst += [w for w in f["worst_steps"] if w not in worst]
    return {"count": {c: avg([f["count"][c] for f in fs]) for c in CLASSES},
            "weight": {c: avg([f["weight"][c] for f in fs]) for c in CLASSES},
            "distinct_count": {c: avg([f["distinct_count"][c] for f in fs]) for c in CLASSES},
            "total": avg([f["total"] for f in fs]), "weighted": avg([f["weighted"] for f in fs]),
            "distinct": avg([f["distinct"] for f in fs]),
            "per_step": avg([f["per_step"] or 0 for f in fs]), "flagged_steps": flagged, "worst_steps": worst,
            "steps": fs[0]["steps"], "counters": n,
            "format_problems": [p for f in fs for p in f["format_problems"]]}


def agree(packets: Path, scores: dict | None, names: list[str] | tuple[str, ...] = ("faults.json",)) -> dict:
    """The counter against the owner. With several result files per lesson (names), each lesson's counts are the
    counters' mean."""
    key = _key(packets)
    owner = owner_lessons(scores)
    lessons, missing = {}, []
    for pid, info in sorted(key["packets"].items()):
        results = [(name, _result(packets, pid, info, name)) for name in names]
        if any(r is None for _, r in results):
            missing += [f"{pid} {name}" for name, r in results if r is None]
            continue
        fs = []
        for name, r in results:
            f = _one(r, info.get("steps"))
            if len(names) > 1:
                f["format_problems"] = [f"{name}: {x}" for x in f["format_problems"]]
            fs.append(f)
        o = owner.get(info["lesson"])
        lessons[info["lesson"]] = {"packet": pid, "picture": info["picture"], "faults": _mean(fs),
                                   "owner": o if o and o["scored"] else NOT_SCORED}
    scored = {k: v for k, v in lessons.items() if v["owner"] != NOT_SCORED}
    report = {"lessons": lessons, "counter_missing": missing, "scored": len(scored), "counters": list(names),
              "correlations": {}}
    for name, (classes, score) in GROUPS.items():
        if not scored:
            report["correlations"][name] = NOT_SCORED
            continue
        xs = [-sum(v["faults"]["weight"][c] for c in classes) / max(1, v["faults"]["steps"]) for v in scored.values()]
        ys = [v["owner"][score] for v in scored.values()]
        rho = spearman(xs, ys)
        report["correlations"][name] = {"against": score, "classes": classes, "n": len(xs), "per_step": True,
                                        "rho": rho if rho is not None else "too few lessons or no spread"}
    report["steps"] = _steps(scored) if scored else NOT_SCORED
    report["preference"] = _preference(lessons, owner) if scored else NOT_SCORED
    return report


def kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    """Cohen's kappa of two yes/no raters; None when it can't be told."""
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def _steps(scored: dict) -> dict | str:
    tapped = {k: v for k, v in scored.items() if v["owner"]["worst"]}
    if not tapped:
        return "the owner tapped no worst step: unknown"
    both = total = owner_n = counter_n = hit = in_worst = 0
    pairs = []
    for v in tapped.values():
        n_steps = v["faults"]["steps"]
        mine, theirs = set(v["faults"]["flagged_steps"]), set(v["owner"]["worst"])
        for n in range(1, n_steps + 1):
            total += 1
            both += (n in mine) == (n in theirs)
            pairs.append((n in theirs, n in mine))
        owner_n += len(theirs)
        counter_n += len(mine)
        hit += len(mine & theirs)
        in_worst += len(theirs & set(v["faults"]["worst_steps"]))
    return {"lessons": len(tapped), "lessons_without_taps": len(scored) - len(tapped), "steps": total,
            "agree": both, "agree_share": round(both / total, 3) if total else None, "kappa": kappa(pairs),
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


def jaccard(a: set, b: set) -> float | None:
    return round(len(a & b) / len(a | b), 3) if a | b else None


def first_flagged(result: dict) -> set[int]:
    """Steps where a major or blocker fault first shows (repeats, with same_as, left out)."""
    return {s.get("n") for s in result.get("steps") or [] for f in s.get("faults") or []
            if not f.get("same_as") and SEVERITY.get(str(f.get("severity", "")).lower(), 1) >= FLAG}


def compare(packets: Path, a: str, b: str) -> dict:
    """Two counters on the same packets: how much they agree with each other (the counter's repeatability)."""
    key = _key(packets)
    rows, missing = [], []
    for pid, info in sorted(key["packets"].items(), key=lambda kv: kv[1]["picture"]):
        ra, rb = _result(packets, pid, info, a), _result(packets, pid, info, b)
        if ra is None or rb is None:
            missing.append(pid)
            continue
        fa, fb = _one(ra, info.get("steps")), _one(rb, info.get("steps"))
        da, db = fa["distinct"], fb["distinct"]
        rows.append({
            "picture": info["picture"], "packet": pid, "steps": fa["steps"],
            "distinct": [da, db], "all": [fa["total"], fb["total"]], "weighted": [fa["weighted"], fb["weighted"]],
            "distinct_by_class": {c: [fa["distinct_count"][c], fb["distinct_count"][c]] for c in CLASSES},
            "distinct_spread": round(abs(da - db) / ((da + db) / 2), 3) if da + db else 0.0,
            "weighted_spread": round(abs(fa["weighted"] - fb["weighted"]) / ((fa["weighted"] + fb["weighted"]) / 2), 3)
            if fa["weighted"] + fb["weighted"] else 0.0,
            "worst3_overlap": len(set(fa["worst_steps"][:3]) & set(fb["worst_steps"][:3])),
            "worst3_of": min(3, len(fa["worst_steps"][:3]), len(fb["worst_steps"][:3])),
            "flagged_jaccard": jaccard(set(fa["flagged_steps"]), set(fb["flagged_steps"])),
            "first_flagged_jaccard": jaccard(first_flagged(ra), first_flagged(rb)),
            "flagged": [len(fa["flagged_steps"]), len(fb["flagged_steps"])],
            "format_problems": {a: fa["format_problems"], b: fb["format_problems"]},
        })
    js = [r["flagged_jaccard"] for r in rows if r["flagged_jaccard"] is not None]
    fj = [r["first_flagged_jaccard"] for r in rows if r["first_flagged_jaccard"] is not None]
    spreads = [r["distinct_spread"] for r in rows]
    wsp = [r["weighted_spread"] for r in rows]
    summary = {
        "lessons": len(rows),
        "distinct_spread": {"mean": round(sum(spreads) / len(spreads), 3) if spreads else None,
                            "min": min(spreads, default=None), "max": max(spreads, default=None)},
        "weighted_spread": {"mean": round(sum(wsp) / len(wsp), 3) if wsp else None,
                            "min": min(wsp, default=None), "max": max(wsp, default=None)},
        "worst3_overlap": [sum(r["worst3_overlap"] for r in rows), sum(r["worst3_of"] for r in rows)],
        "flagged_jaccard": {"mean": round(sum(js) / len(js), 3) if js else None,
                            "min": min(js, default=None), "max": max(js, default=None)},
        "first_flagged_jaccard": {"mean": round(sum(fj) / len(fj), 3) if fj else None,
                                  "min": min(fj, default=None), "max": max(fj, default=None)},
        "rank_rho_weighted_per_step": spearman([r["weighted"][0] / r["steps"] for r in rows],
                                               [r["weighted"][1] / r["steps"] for r in rows]),
        "distinct_by_class_total": {c: [sum(r["distinct_by_class"][c][0] for r in rows),
                                        sum(r["distinct_by_class"][c][1] for r in rows)] for c in CLASSES},
    }
    return {"counters": [a, b], "lessons": rows, "missing": missing, "summary": summary}


def compare_table(report: dict) -> str:
    a, b = report["counters"]
    lines = [f"picture | distinct {a} / {b} | spread | weighted | worst-3 overlap | flagged-step Jaccard (all / first)"]
    for r in report["lessons"]:
        lines.append(f"{r['picture']} | {r['distinct'][0]} / {r['distinct'][1]} | {r['distinct_spread']:.0%} | "
                     f"{r['weighted'][0]} / {r['weighted'][1]} | {r['worst3_overlap']} of {r['worst3_of']} | "
                     f"{r['flagged_jaccard']} / {r['first_flagged_jaccard']}")
    s = report["summary"]
    lines += ["", f"distinct spread: mean {s['distinct_spread']['mean']:.0%}, {s['distinct_spread']['min']:.0%} to "
              f"{s['distinct_spread']['max']:.0%}",
              f"weighted spread: mean {s['weighted_spread']['mean']:.0%}, {s['weighted_spread']['min']:.0%} to "
              f"{s['weighted_spread']['max']:.0%}",
              f"worst-3 overlap: {s['worst3_overlap'][0]} of {s['worst3_overlap'][1]}",
              f"flagged-step Jaccard: mean {s['flagged_jaccard']['mean']}, {s['flagged_jaccard']['min']} to "
              f"{s['flagged_jaccard']['max']} (every step a major fault shows in)",
              f"first-flagged-step Jaccard: mean {s['first_flagged_jaccard']['mean']}, "
              f"{s['first_flagged_jaccard']['min']} to {s['first_flagged_jaccard']['max']} (the step it first shows in)",
              f"rank rho of weighted per step, {a} against {b}: {s['rank_rho_weighted_per_step']}"]
    lines += [f"format, {r['packet']} {n}: {p}" for r in report["lessons"] for n, ps in r["format_problems"].items()
              for p in ps]
    if report["missing"]:
        lines.append(f"missing: {', '.join(report['missing'])}")
    return "\n".join(lines)


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
                              f"{s['agree']} of {s['steps']} agree (kappa {s['kappa']}); owner worst {s['owner_worst']}, "
                              f"counter flagged {s['counter_flagged']}, both {s['both']}; {s['lessons_without_taps']} "
                              "scored lessons without worst-step taps left out"))
    for folder, v in report["lessons"].items():
        for p in v["faults"].get("format_problems") or []:
            lines.append(f"format, {v['packet']}: {p}")
    if report["counter_missing"]:
        lines.append(f"no faults.json yet: {', '.join(report['counter_missing'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--packets", required=True, help="the folder with key.json and each lesson's counter results")
    ap.add_argument("--scores", help="the owner's scores (spike/experiments/bench/scores/<round>.json)")
    ap.add_argument("--name", action="append", help="a counter's result file name in each lesson's folder (default "
                    "faults.json); give it twice or more to use the counters' mean")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"), help="two counters' result file names: report how well "
                    "they agree with each other instead")
    ap.add_argument("--out", help="write the report JSON here too")
    a = ap.parse_args(argv)
    scores = read_json(Path(a.scores)) if a.scores else None
    try:
        if a.compare:
            report = compare(Path(a.packets), *a.compare)
            text = compare_table(report)
        else:
            report = agree(Path(a.packets), scores, a.name or ["faults.json"])
            text = table(report)
    except (FileNotFoundError, ValueError) as err:
        print(json.dumps({"problems": [str(err)]}))
        return 1
    if a.out:
        write_json(Path(a.out), report)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
