"""Spike for #268 (v4 cost, C2, Claude only): a cheaper Claude setting for the chain's checker.

The chain's checker is one fresh call a round: chain-check.md, asked.json and one look a unit, answered with a stray
and a left for each (`v4_loop.Run.checker`). This spike asks the same questions of cheaper settings and compares
their answers with Opus 5.5 at the loop's setting (Claude Code's default effort, medium), look by look.

No new renders. Every run of the loop keeps each render it made (`chain/U<nn>[r...]_raw.png`) and the again-list
after every erase (`v4/state.json`), so each checker round's looks can be laid again exactly as the checker saw
them: `erase3.run` with the round's again-list and a render that hands back the saved answer.

    .venv/bin/python spike/experiments/v4_checker_cost.py rebuild            # every round of every v4 loop run
    .venv/bin/python spike/experiments/v4_checker_cost.py ask opus-medium haiku-medium ...
    .venv/bin/python spike/experiments/v4_checker_cost.py report

Rounds go to output/bench/v4-checker/<run>/round-<k>/ (looks, asked.json, opus.json: the loop's own answers).
Every answer and call goes to spike/experiments/v4_checker_cost.json.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "spike"))
sys.path.insert(0, str(HERE))

import v4_loop  # noqa: E402
from v4_loop import NO_TOOLS, SKILL, Message, call_claude, cost, last_json  # noqa: E402

OUT = ROOT / "output"
BENCH = OUT / "bench" / "v4-checker"
DATA = HERE / "v4_checker_cost.json"
USED: dict[str, int] = {}  # where the replay's renders came from: the render cache, or the run's _raw.png
SYSTEM = NO_TOOLS + "You are the chain's checker for a Gesso lesson."

# name -> (Claude Code's model alias, effort). Claude Code's aliases are the 5.5 models (checked: "haiku" answers as
# claude-haiku-5-5). The loop's checker ran with no --effort: Opus 5.5's default, medium.
SETTINGS = {
    "opus-medium": ("opus", None),
    "opus-low": ("opus", "low"),
    "opus-high": ("opus", "high"),
    "sonnet-medium": ("sonnet", "medium"),
    "sonnet-low": ("sonnet", "low"),
    "haiku-medium": ("haiku", None),
    "haiku-high": ("haiku", "high"),
}


# ------------------------------------------------------------------------------------------------------ the rounds
def _calls(run: Path) -> list[str]:
    return [c["label"] for c in json.loads((run / "v4" / "calls.json").read_text())]


def rounds_of(run: Path) -> tuple[list[dict], str | None]:
    """Each checker round of a loop run: {"again": the again-list its looks were laid with, "marked": what the loop's
    checker marked}. Or why the run can't be replayed."""
    s = json.loads((run / "v4" / "state.json").read_text())
    marked = s.get("checker") or []
    if not marked:
        return [], "no checker round"
    labels = _calls(run)
    first = next(i for i, x in enumerate(labels) if x.startswith("C4 chain check"))
    merge_at = [i for i, x in enumerate(labels) if x.startswith("C3 merge")]
    if any(i > first for i in merge_at):
        return [], "a merge after the checker changed the plan, so its units aren't the ones the checker saw"
    erases = s.get("erase") or []
    before = 1 + len(merge_at)  # the chain's erase, and one more after a merge
    out = []
    for k, m in enumerate(marked):
        e = erases[before - 1 + k] if before - 1 + k < len(erases) else None
        if e is None or e.get("again") is None:
            return out, f"no again-list recorded for round {k + 1}"
        out.append({"again": e["again"], "marked": m})
    return out, None


def _saved_render(lesson: Path, chain: Path):
    """A renderer that hands back the run's saved answer for a try, brought to the picture's size as `erase` does."""
    import numpy as np
    from PIL import Image
    from run import size_for
    from tools import CACHE_DIR, _to_frame, cache_key

    def render(name: str, src: Path, prompt: str, fresh: bool):
        picture = np.array(Image.open(src).convert("RGB"))
        size = size_for(src)
        frame, box = _to_frame(picture, size)
        # The render cache first, keyed as `erase` keys it (the picture as sent, with its gray bands, and the
        # request). A run whose later redo was stopped by the cost cap rendered some units again under the same
        # names, so their _raw.png is not what the checker saw; the cache still holds the earlier answer.
        padded = box != (0, 0) + frame.size
        if padded:
            frame.save(src)
            prompt = prompt.replace("No text, signature", "Keep the plain gray bands at the edges exactly as they are. "
                                                          "No text, signature")
        key = cache_key([src], prompt, size, "low")
        if padded:
            Image.fromarray(picture).save(src)
        raw = CACHE_DIR / f"{key}.png"
        if not raw.exists():
            raw = chain / f"{name}_raw.png"
        USED[raw.parent.name] = USED.get(raw.parent.name, 0) + 1
        if not raw.exists():
            raise RuntimeError(f"{lesson.name}: no saved render {raw.name}")
        got = Image.open(raw).convert("RGB")
        if got.size != frame.size:
            got = got.resize(frame.size, Image.LANCZOS)
        if box != (0, 0) + frame.size:
            got = got.crop(box)
        if got.size != (picture.shape[1], picture.shape[0]):
            got = got.resize((picture.shape[1], picture.shape[0]), Image.LANCZOS)
        return np.array(got), {"seconds": 0, "cost_usd": 0, "cached": True}

    return render


def rebuild_run(run: Path) -> dict:
    import erase3
    import numpy as np
    from PIL import Image
    from tools import _v3_ready

    rounds, why = rounds_of(run)
    if why and not rounds:
        return {"run": run.name, "skipped": why}
    plan, _, finish = _v3_ready(run)
    tries = json.loads((run / "chain" / "tries.json").read_text())
    import plan3
    if tries["units"] != [[u["things"], u["steps"]] for u in plan3.units(plan)]:
        return {"run": run.name, "skipped": "tries.json is for other units than plan.json"}
    made = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "chain").mkdir()
        render = _saved_render(run, run / "chain")
        for k, r in enumerate(rounds, 1):
            (t / "chain" / "tries.json").write_text(json.dumps({"units": tries["units"], "again": r["again"],
                                                                 "rendered": tries["rendered"]}))
            erase3.run(t, plan, finish, render, None, auto=False)
            dest = BENCH / run.name / f"round-{k}"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(t / "chain" / "looks", dest)
            looks = json.loads((dest / "asked.json").read_text())
            hit = {m["look"]: m for m in r["marked"]}
            (dest / "opus.json").write_text(json.dumps(
                [{"look": a["look"], "stray": bool(hit.get(a["look"], {}).get("stray")),
                  "left": bool(hit.get(a["look"], {}).get("left")), "why": hit.get(a["look"], {}).get("why") or ""}
                 for a in looks], indent=1))
            made.append(dest)
    # the last round, laid again, is the run's own looks: the check that the replay is exact
    last, own = made[-1], run / "chain" / "looks"
    same = None
    if (own / "answers.json").exists():
        diffs = []
        for p in sorted(own.glob("U*.jpg")):
            a = np.asarray(Image.open(p)).astype(int)
            b = np.asarray(Image.open(last / p.name)).astype(int)
            diffs.append(float(np.abs(a - b).mean()) if a.shape == b.shape else 999.0)
        same = round(max(diffs), 3)
    return {"run": run.name, "rounds": len(made), "looks": sum(len(list(m.glob("U*.jpg"))) for m in made),
            "last_round_vs_own_looks_mean_abs": same, "note": why}


def cmd_rebuild(a):
    runs = sorted(p for p in OUT.glob("*_v4loop_*") if (p / "v4" / "state.json").exists())
    if a.only:
        runs = [r for r in runs if re.search(a.only, r.name)]
    rows = []
    for r in runs:
        USED.clear()
        rows.append(rebuild_run(r) | {"renders_from": dict(USED)})
    for r in rows:
        print(json.dumps(r))
    d = load()
    keep = {r["run"]: r for r in d.get("rounds", [])}
    keep.update({r["run"]: r for r in rows})
    d["rounds"] = [keep[k] for k in sorted(keep)]
    save(d)


# -------------------------------------------------------------------------------------------------------- asking
def load() -> dict:
    return json.loads(DATA.read_text()) if DATA.exists() else {}


def save(d: dict):
    DATA.write_text(json.dumps(d, indent=1))


def all_rounds() -> list[Path]:
    return sorted(p for p in BENCH.glob("*/round-*") if (p / "opus.json").exists())


def message(folder: Path) -> Message:
    """Word for word what the loop's checker is sent (`v4_loop.Run.checker`)."""
    looks = folder
    m = Message().file(SKILL / "v3" / "chain-check.md", "chain-check.md")
    rel = "output/" + "/".join(folder.relative_to(OUT).parts[:2]) + "/chain/looks"
    m.text(f"Folder: {rel}").file(looks / "asked.json", "asked.json")
    for p in sorted(looks.glob("U*.jpg")):
        m.picture(p, p.name)
    m.text("Reply with answers.json as one ```json block, then your one line. The program writes the file.")
    return m


def ask_one(setting: str, folder: Path, rep: int) -> dict:
    model, effort = SETTINGS[setting]
    m = message(folder)
    with tempfile.TemporaryDirectory() as cwd:
        r = call_claude(m.blocks, SYSTEM, cwd=Path(cwd), cache="none", model=model, effort=effort)
        calls = [r]
        try:
            answers = last_json(r["text"])
        except ValueError as e:
            again = Message().text(f"Your reply had no JSON I could read ({e}). Send the same answer again as one "
                                   "```json block, and nothing else.")
            r2 = call_claude(again.blocks, SYSTEM, session=r["session"], cwd=Path(cwd), cache="5m", model=model,
                             effort=effort)
            calls.append(r2)
            answers = last_json(r2["text"])
    return {"setting": setting, "round": str(folder.relative_to(BENCH)), "rep": rep,
            "answers": [{"look": x.get("look"), "stray": bool(x.get("stray")), "left": bool(x.get("left")),
                         "why": x.get("why") or ""} for x in answers],
            "cost_usd": round(sum(cost(c["usage"], c["model"]) for c in calls), 5),
            "seconds": round(sum(c["seconds"] for c in calls), 1),
            "output_tokens": sum(c["usage"].get("output_tokens", 0) for c in calls),
            "input_tokens": sum(c["usage"].get("input_tokens", 0) + c["usage"].get("cache_creation_input_tokens", 0)
                                + c["usage"].get("cache_read_input_tokens", 0) for c in calls),
            "model": calls[0]["model"], "json_again": len(calls) > 1}


def cmd_ask(a):
    d = load()
    d.setdefault("answers", [])
    have = {(x["setting"], x["round"], x["rep"]) for x in d["answers"]}
    jobs = [(s, f, rep) for s in a.settings for f in all_rounds() for rep in range(1, a.reps + 1)
            if (s, str(f.relative_to(BENCH)), rep) not in have]
    if a.only:
        jobs = [j for j in jobs if re.search(a.only, str(j[1]))]
    print(f"{len(jobs)} calls", file=sys.stderr)

    def go(j):
        try:
            return ask_one(*j)
        except Exception as e:  # noqa: BLE001 - one failed call is reported and left for the next run
            print(f"  {j[0]} {j[1].relative_to(BENCH)}: {e}", file=sys.stderr)
            return None

    with ThreadPoolExecutor(a.jobs) as ex:
        for r in ex.map(go, jobs):
            if r:
                d = load()
                d.setdefault("answers", []).append(r)
                save(d)
                print(f"  {r['setting']} {r['round']} rep {r['rep']}: ${r['cost_usd']:.3f} {r['seconds']} s, "
                      f"marked {[x['look'] for x in r['answers'] if x['stray'] or x['left']]}", file=sys.stderr)


# -------------------------------------------------------------------------------------------------------- report
def _marks(answers: list[dict]) -> dict[str, set]:
    return {x["look"]: {k for k in ("stray", "left") if x.get(k)} for x in answers}


def compare(ref: list[dict], got: list[dict]) -> dict:
    """Look by look, against the reference: the marks it made that `got` missed, the ones `got` added, and the looks
    where both said nothing or both marked the same."""
    r, g = _marks(ref), _marks(got)
    looks = sorted(set(r) | set(g))
    out = {"looks": len(looks), "ref_marks": 0, "caught": 0, "missed": [], "added": [], "agree_looks": 0}
    for lk in looks:
        a, b = r.get(lk, set()), g.get(lk, set())
        out["ref_marks"] += len(a)
        out["caught"] += len(a & b)
        out["missed"] += [f"{lk}:{k}" for k in sorted(a - b)]
        out["added"] += [f"{lk}:{k}" for k in sorted(b - a)]
        out["agree_looks"] += a == b
    return out


def reference(d: dict) -> dict[str, list[dict]]:
    """Each round's marks that most of Opus's reads made: the loop's own answer and every opus-medium read here.
    A mark is in when more than half the reads made it. Opus doesn't always agree with itself, so this, not the
    loop's one read, is what a cheaper setting has to catch."""
    out = {}
    for f in all_rounds():
        rnd = str(f.relative_to(BENCH))
        reads = [json.loads((f / "opus.json").read_text())] + [x["answers"] for x in d.get("answers", [])
                                                                if x["setting"] == "opus-medium" and x["round"] == rnd]
        votes: dict[tuple, int] = {}
        looks = sorted({a["look"] for r in reads for a in r})
        for r in reads:
            for lk, ks in _marks(r).items():
                for k in ks:
                    votes[(lk, k)] = votes.get((lk, k), 0) + 1
        out[rnd] = {"reads": len(reads), "answers": [
            {"look": lk, **{k: votes.get((lk, k), 0) * 2 > len(reads) for k in ("stray", "left")},
             "votes": {k: votes.get((lk, k), 0) for k in ("stray", "left")}} for lk in looks]}
    return out


def summary(d: dict) -> dict:
    ref = reference(d)
    loop = {str(f.relative_to(BENCH)): json.loads((f / "opus.json").read_text()) for f in all_rounds()}
    by: dict[str, list] = {"opus-loop": [{"setting": "opus-loop", "round": k, "answers": v, "cost_usd": 0,
                                          "seconds": 0, "json_again": False} for k, v in loop.items()]}
    for x in d.get("answers", []):
        by.setdefault(x["setting"], []).append(x)
    res = {}
    for s, xs in by.items():
        tot = {"calls": len(xs), "looks": 0, "ref_marks": 0, "caught": 0, "missed": [], "added": [],
               "agree_looks": 0, "cost_usd": 0.0, "seconds": 0.0, "json_again": 0}
        for x in xs:
            c = compare(ref[x["round"]]["answers"], x["answers"])
            for k in ("looks", "ref_marks", "caught", "agree_looks"):
                tot[k] += c[k]
            tot["missed"] += [f"{x['round']}/{m}" for m in c["missed"]]
            tot["added"] += [f"{x['round']}/{m}" for m in c["added"]]
            tot["cost_usd"] += x["cost_usd"]
            tot["seconds"] += x["seconds"]
            tot["json_again"] += x["json_again"]
        n = len(xs)
        tot["cost_per_call"] = round(tot["cost_usd"] / n, 4)
        tot["seconds_per_call"] = round(tot["seconds"] / n, 1)
        tot["recall"] = round(tot["caught"] / tot["ref_marks"], 3) if tot["ref_marks"] else None
        tot["agree_share"] = round(tot["agree_looks"] / tot["looks"], 3) if tot["looks"] else None
        tot["cost_usd"] = round(tot["cost_usd"], 3)
        res[s] = tot
    return {"reference": ref, "settings": res}


def cmd_report(a):
    d = load()
    d["summary"] = summary(d)
    save(d)
    ref = d["summary"]["reference"]
    print(f"{len(ref)} rounds, {sum(len(r['answers']) for r in ref.values())} looks, "
          f"{sum(a['stray'] + a['left'] for r in ref.values() for a in r['answers'])} marks most Opus reads made")
    for s, t in d["summary"]["settings"].items():
        print(f"{s:14} calls {t['calls']:3}  caught {t['caught']}/{t['ref_marks']} ({t['recall']})  "
              f"looks agreeing {t['agree_share']}  added {len(t['added'])}  ${t['cost_per_call']}/call  "
              f"{t['seconds_per_call']} s/call")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("rebuild")
    b.add_argument("--only", help="a regex on the run's folder name")
    b.set_defaults(fn=cmd_rebuild)
    q = sub.add_parser("ask")
    q.add_argument("settings", nargs="+", choices=list(SETTINGS))
    q.add_argument("--reps", type=int, default=1)
    q.add_argument("--jobs", type=int, default=4)
    q.add_argument("--only", help="a regex on the round's folder")
    q.set_defaults(fn=cmd_ask)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
