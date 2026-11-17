"""Spike for #176 (pipeline v3, S11): one engine that rebuilds only what changed, proven byte for byte.

Not part of the pipeline. It runs the v2 tool chain the paint-lesson skill uses on the three fixture lessons
(spike/tests/fixtures/), each tool as its own process exactly as the skill calls it, and records a sha256 of every
file in the lesson folder after every tool, plus each tool's printed `seconds` and its wall time:

    python spike/experiments/v3_one_engine.py run --mode default            # today's path: one process per tool
    python spike/experiments/v3_one_engine.py run --mode engine             # the same commands through the engine
    python spike/experiments/v3_one_engine.py run --mode default --save     # write the golden hashes
    python spike/experiments/v3_one_engine.py run --mode engine --repeat 3 --times out.json   # timings
    python spike/experiments/v3_one_engine.py bench --before <main's code> --repeat 3 --out bench.json
                                                  # before and engine, fixture by fixture, taking turns
    python spike/experiments/v3_one_engine.py table bench.json          # the tables in the write-up
    python spike/experiments/v3_one_engine.py save times.json ...       # golden hashes from runs that all agree

Today's code for --code or --before: `git archive --format=tar <commit> spike techniques palettes photos docs .claude`,
unpacked into a folder with .venv and models linked into it.

`--code DIR` runs another copy of the repo's code (a `git archive` of main, say) with the same fixtures, so today's
code and the engine can be timed side by side on one machine. Every run is checked against the golden hashes
(v3_one_engine.json, next to this file) unless --save is given. docs/spikes/v3-one-engine.md has the results.

Three scenarios per fixture, one after the other in the same lesson folder, the way a run loops:

    full    outline, paints, build-steps, step-aids, mix, draft-text, card-adapt, check, publish (a draft)
    stage   the last two neighboring passes of one part swap places in plan.json; build-steps on (skill rule 9)
    part    the first object part's box grows by 0.005 on every side; outline on

Files that legitimately differ between two runs are normalized field by field, and only those (NORMALIZED below):
the publish stamp's commit, dirty flag and date (in lesson.json, embed/lesson.json and the three pages' footers), and
the lesson folder's absolute path in what the tools print. Everything else is compared byte for byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN = Path(__file__).with_suffix(".json")
NAMES = ["chickadee", "lavender-balloon", "red-sailboat"]
FOLDER = "{name}_skill_20261112-090000"  # as spike/tests/lessons.py names it
CHAIN = ["outline", "paints", "build-steps", "step-aids", "mix", "draft-text", "card-adapt", "check", "publish"]
SCENARIOS = {"full": CHAIN, "stage": CHAIN[CHAIN.index("build-steps"):], "part": CHAIN}

# What legitimately differs between two runs of the same code on the same inputs, and nothing else:
NORMALIZED = {
    "stamp": "publish's stamp (version.stamp): the git commit, whether the tree was dirty, and the date it ran. In "
             "lesson.json and embed/lesson.json as gesso.commit, gesso.dirty, gesso.published and gesso.made.commit, "
             "gesso.made.published; in the three pages as the footer line 'Gesso <version> (<commit>[+dirty]) on "
             "<date>'; in publish's printed gesso.",
    "path": "the lesson folder's absolute path, in what the tools print on stdout and stderr (a scratch folder, "
            "different each run); and each tool's printed `seconds`.",
}
STAMP = re.compile(r"\((?:[0-9a-f]{4,40}|unknown)(?:\+dirty)?\) on \d{4}-\d{2}-\d{2}")


def python() -> str:
    return str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable


# ---------------------------------------------------------------------------
# The fixture lessons and the changes the scenarios make
# ---------------------------------------------------------------------------


def setup(code: Path, name: str, into: Path) -> Path:
    """A lesson folder as spike/tests/lessons.py's "outlined" stage makes it: the fixture plan, finish, and saved
    outlines (outline then writes its own)."""
    import numpy as np
    from PIL import Image

    fix = code / "spike" / "tests" / "fixtures"
    lesson = into / FOLDER.format(name=name)
    (lesson / "parts").mkdir(parents=True)
    plan = json.loads((fix / "plans" / f"{name}.json").read_text(encoding="utf-8"))
    (lesson / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    Image.fromarray(np.array(Image.open(fix / "finishes" / f"{name}.jpg").convert("RGB"))).save(lesson / "99_finish.png")
    Image.fromarray(np.array(Image.open(fix / "owners" / f"{name}.png")).astype(np.uint8)).save(lesson / "parts" / "owner.png")
    return lesson


def change_stage(plan: dict) -> str:
    """Swap the last two neighboring `pass` steps of one part: a stages-only edit (rerun from build-steps)."""
    pairs = [(st, i) for st in plan["stages"] for i in range(len(st["steps"]) - 1)
             if st["steps"][i]["show"] == st["steps"][i + 1]["show"] == "pass"
             and st["steps"][i]["part"] == st["steps"][i + 1]["part"]]
    st, i = pairs[-1]
    st["steps"][i], st["steps"][i + 1] = st["steps"][i + 1], st["steps"][i]
    return f"swapped {st['steps'][i + 1]['id']} and {st['steps'][i]['id']}"


def change_part(plan: dict) -> str:
    """Grow the first single-box object's box by 0.005 on every side: a parts edit (rerun from outline)."""
    p = next(q for q in plan["parts"] if q["kind"] == "object" and q.get("box"))
    p["box"] = [round(max(0.0, p["box"][0] - 0.005), 4), round(max(0.0, p["box"][1] - 0.005), 4),
                round(min(1.0, p["box"][2] + 0.005), 4), round(min(1.0, p["box"][3] + 0.005), 4)]
    return f"grew {p['id']}'s box to {p['box']}"


CHANGES = {"stage": change_stage, "part": change_part}


def edit_plan(lesson: Path, scenario: str) -> str:
    path = lesson / "plan.json"
    plan = json.loads(path.read_text(encoding="utf-8"))
    what = CHANGES[scenario](plan)
    path.write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")  # as paints writes it
    return what


# ---------------------------------------------------------------------------
# Hashes, with only the NORMALIZED fields taken out
# ---------------------------------------------------------------------------


def _unstamp(g: dict) -> dict:
    g = dict(g)
    for k in ("commit", "dirty", "published"):
        if k in g:
            g[k] = f"<{k}>"
    if isinstance(g.get("made"), dict):
        g["made"] = {k: (f"<{k}>" if k in ("commit", "published") else v) for k, v in g["made"].items()}
    return g


GESSO_FIELDS = re.compile(rb'("(?:commit|published)": )"[^"]*"|("dirty": )(?:true|false)')


def _gesso_span(data: bytes) -> tuple[int, int] | None:
    """Where the top-level "gesso" object is in a lesson.json's bytes: from its opening brace to its closing one."""
    at = data.find(b'"gesso": {')
    if at < 0:
        return None
    start = data.index(b"{", at)
    depth, i, in_str = 0, start, False
    while i < len(data):
        c = data[i:i + 1]
        if in_str:
            if c == b"\\":
                i += 1
            elif c == b'"':
                in_str = False
        elif c == b'"':
            in_str = True
        elif c == b"{":
            depth += 1
        elif c == b"}":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    return None


def normalized(rel: str, data: bytes) -> bytes:
    """A file's bytes with the NORMALIZED fields replaced by placeholders; every other byte as it is. In lesson.json
    only the stamp's values inside its "gesso" object are replaced, on the raw bytes, so a change in how the file is
    written (spacing, a trailing newline, escaping) still shows."""
    if rel in ("lesson.json", "embed/lesson.json"):
        span = _gesso_span(data)
        if span is None:
            return data
        a, b = span
        inner = GESSO_FIELDS.sub(lambda m: (m.group(1) + b'"<stamp>"') if m.group(1) else m.group(2) + b'"<stamp>"',
                                 data[a:b])
        return data[:a] + inner + data[b:]
    if rel.endswith(".html"):
        return STAMP.sub("(<commit>) on <date>", data.decode("utf-8")).encode("utf-8")
    return data


def snapshot(lesson: Path) -> dict[str, str]:
    out = {}
    for p in sorted(lesson.rglob("*")):
        if p.is_file():
            rel = p.relative_to(lesson).as_posix()
            out[rel] = hashlib.sha256(normalized(rel, p.read_bytes())).hexdigest()
    return out


def printed(stdout: str, lesson: Path) -> str:
    """All a tool printed on stdout, without its `seconds`, the lesson's path, or publish's stamp."""
    lines = []
    for line in stdout.splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            lines.append(_unpath(line, lesson))
            continue
        if isinstance(r, dict):
            r = {k: v for k, v in r.items() if k != "seconds"}
            if isinstance(r.get("gesso"), dict):
                r["gesso"] = _unstamp(r["gesso"])
        lines.append(_unpath(json.dumps(r, sort_keys=True), lesson))
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _unpath(text: str, lesson: Path) -> str:
    return text.replace(str(lesson.resolve()), "<lesson>").replace(str(lesson), "<lesson>")


def errors(stderr: str, lesson: Path) -> str:
    """What a tool printed on stderr, without the lesson's path."""
    return hashlib.sha256(_unpath(stderr, lesson).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Running the chain
# ---------------------------------------------------------------------------


class Engine:
    """The engine started for one fixture's scenarios, as a caller would: `tools.py engine serve` in the
    background, then every tool through `tools.py engine call`."""

    def __init__(self, code: Path, folder: Path, env: dict, readings: Path):
        self.code, self.env = code, env
        self.state = folder / "engine.json"
        self.state.unlink(missing_ok=True)  # left by an engine that died
        self.log = open(folder / "engine.log", "a")
        self.proc = subprocess.Popen([python(), str(code / "spike" / "tools.py"), "engine", "serve", "--state",
                                      str(self.state), "--readings", str(readings)], cwd=code, env=env,
                                     stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.time() + 120
        while not self.state.exists():
            if self.proc.poll() is not None or time.time() > deadline:
                raise RuntimeError(f"the engine didn't start; see {folder / 'engine.log'}")
            time.sleep(0.05)

    def argv(self, tool: str, lesson: Path) -> list[str]:
        return [python(), str(self.code / "spike" / "tools.py"), "engine", "call", "--state", str(self.state), tool,
                "--lesson", str(lesson)]

    def status(self) -> dict:
        p = subprocess.run([python(), str(self.code / "spike" / "tools.py"), "engine", "status", "--state",
                            str(self.state)], cwd=self.code, env=self.env, capture_output=True, text=True, timeout=60)
        return json.loads(p.stdout.strip().splitlines()[-1])

    def close(self) -> None:
        subprocess.run([python(), str(self.code / "spike" / "tools.py"), "engine", "stop", "--state",
                        str(self.state)], cwd=self.code, env=self.env, capture_output=True, timeout=60)
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()


def run_fixture(code: Path, name: str, mode: str, work: Path, env: dict, readings: Path | None = None) -> dict:
    """Every scenario on one fixture: per tool, its exit code, the hash of what it printed, its `seconds`, its wall
    time, and the files it changed (relative path -> sha256, or null for a file it removed)."""
    lesson = setup(code, name, work)
    engine = Engine(code, work, env, readings or work / "readings") if mode == "engine" else None
    out, restarts = {}, 0
    try:
        before = snapshot(lesson)
        for scenario, tools in SCENARIOS.items():
            rows = []
            change = edit_plan(lesson, scenario) if scenario in CHANGES else None
            if change:
                now = snapshot(lesson)
                rows.append({"tool": "edit plan.json", "change": change,
                             "files": {k: v for k, v in now.items() if before.get(k) != v}})
                before = now
            for tool in tools:
                argv = (engine.argv(tool, lesson) if engine else
                        [python(), str(code / "spike" / "tools.py"), tool, "--lesson", str(lesson)])
                for attempt in range(3):
                    start = time.perf_counter()
                    p = subprocess.run(argv, cwd=code, env=env, capture_output=True, text=True, timeout=1800)
                    wall = time.perf_counter() - start
                    # killed from outside (the machine ran out of memory, with other work on it): the tool rewrites
                    # everything it makes, so it's run again; a dead engine is started again (its memos start empty)
                    if engine and engine.proc.poll() is not None:
                        print(f"  {name} {scenario} {tool}: the engine died ({engine.proc.returncode}), starting it "
                              "again", file=sys.stderr, flush=True)
                        engine.close()
                        engine = Engine(code, work, env, readings or work / "readings")
                        argv = engine.argv(tool, lesson)
                        restarts += 1
                        continue
                    if p.returncode >= 0:
                        break
                    print(f"  {name} {scenario} {tool}: killed by signal {-p.returncode}, running it again",
                          file=sys.stderr, flush=True)
                lines = p.stdout.strip().splitlines()
                if not lines:
                    raise RuntimeError(f"{name} {scenario} {tool} printed nothing (exit code {p.returncode}): "
                                       f"{p.stderr[-2000:]}")
                result = json.loads(lines[-1])
                now = snapshot(lesson)
                changed = {k: v for k, v in now.items() if before.get(k) != v}
                changed.update({k: None for k in before if k not in now})
                rows.append({"tool": tool, "code": p.returncode, "printed": printed(p.stdout, lesson),
                             "stderr": errors(p.stderr, lesson),
                             "refused": result.get("refused"), "seconds": result.get("seconds"),
                             "wall": round(wall, 2), "files": changed})
                before = now
                print(f"  {name} {scenario:5} {tool:11} code {p.returncode} seconds {result.get('seconds')} "
                      f"wall {wall:.2f} files {len(changed)}", file=sys.stderr, flush=True)
            out[scenario] = rows
        if engine:
            out["engine"] = {**engine.status(), "restarts": restarts}
    finally:
        if engine:
            engine.close()
    return out


def run_all(code: Path, mode: str, names: list[str], keep: Path | None = None, readings: Path | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "GESSO_HISTORY"}  # publish records nothing: not under output/
    work = Path(tempfile.mkdtemp(prefix="v3-one-engine-", dir=keep))
    try:
        return {name: run_fixture(code, name, mode, work / name, env, readings) for name in names}
    finally:
        if keep is None:
            shutil.rmtree(work, ignore_errors=True)


def hashes(run: dict) -> dict:
    """A run without its timings: what must come out the same."""
    return {name: {sc: [{k: v for k, v in r.items() if k not in ("seconds", "wall")} for r in rows]
                   for sc, rows in scs.items() if sc in SCENARIOS} for name, scs in run.items()}


def differences(a: dict, b: dict) -> list[str]:
    out = []
    for name in a:
        for sc in a[name]:
            ra, rb = a[name][sc], b.get(name, {}).get(sc, [])
            if len(ra) != len(rb):
                out.append(f"{name} {sc}: {len(ra)} tools against {len(rb)}")
                continue
            for x, y in zip(ra, rb):
                if x == y:
                    continue
                files = sorted(k for k in set(x.get("files", {})) | set(y.get("files", {}))
                               if x.get("files", {}).get(k) != y.get("files", {}).get(k))
                other = [k for k in set(x) | set(y) if k != "files" and x.get(k) != y.get(k)]
                out.append(f"{name} {sc} {x['tool']}: differs in {other + files}")
    return out


def timing_table(runs: list[dict]) -> dict:
    """Per fixture, scenario and tool: the median and the range of `seconds` and of wall time over the runs, and
    the same for each scenario's whole chain."""
    out: dict = {}
    for name in runs[0]:
        for sc in SCENARIOS:
            tools = [r["tool"] for r in runs[0][name][sc] if "wall" in r]
            per = {}
            for i, tool in enumerate(tools):
                rows = [[r for r in run[name][sc] if "wall" in r][i] for run in runs]
                per[tool] = {k: _spread([r[k] for r in rows if r.get(k) is not None]) for k in ("seconds", "wall")}
            chain = {k: _spread([sum(r[k] or 0 for r in run[name][sc] if "wall" in r) for run in runs])
                     for k in ("seconds", "wall")}
            out.setdefault(name, {})[sc] = {"tools": per, "chain": chain}
    return out


def _spread(xs: list[float]) -> dict:
    return {"median": round(statistics.median(xs), 2), "min": round(min(xs), 2), "max": round(max(xs), 2),
            "runs": [round(x, 2) for x in xs]} if xs else {}


def bench(a) -> int:
    """Before and after, fixture by fixture, taking turns (the machine is shared, so each pair runs under about the
    same load), each run checked against the golden hashes."""
    env = {k: v for k, v in os.environ.items() if k != "GESSO_HISTORY"}
    gold = json.loads(a.golden.read_text(encoding="utf-8"))["fixtures"]
    arms = [("before", "default", a.before.resolve()), ("engine", "engine", a.after.resolve())]
    if a.with_default_after:
        arms.append(("after-default", "default", a.after.resolve()))
    runs: dict[str, list[dict]] = {label: [] for label, _, _ in arms}
    diffs: dict[str, list[str]] = {label: [] for label, _, _ in arms}
    for i in range(a.repeat):
        order = arms if (i + a.flip) % 2 == 0 else arms[::-1]
        for label, _, _ in arms:
            runs[label].append({})
        for name in a.fixtures:
            for label, mode, code in order:
                print(f"repeat {i + 1} of {a.repeat}: {name}, {label}", file=sys.stderr, flush=True)
                work = Path(tempfile.mkdtemp(prefix="v3-one-engine-"))
                try:
                    got = run_fixture(code, name, mode, work, env, a.readings)
                finally:
                    shutil.rmtree(work, ignore_errors=True)
                runs[label][-1][name] = got
                diffs[label] += differences({name: gold[name]}, hashes({name: got}))
                a.out.write_text(json.dumps({"arms": {lb: [m, str(c)] for lb, m, c in arms}, "diffs": diffs,
                                             "table": {lb: timing_table([r for r in rs if set(r) == set(a.fixtures)])
                                                       for lb, rs in runs.items() if any(set(r) == set(a.fixtures)
                                                                                         for r in rs)},
                                             "runs": runs}, indent=1), encoding="utf-8")
    report = {"same_as_golden": {label: not d for label, d in diffs.items()}, "out": str(a.out)}
    print(json.dumps(report, indent=1))
    return 0 if not any(diffs.values()) else 1


def tables(paths: list[Path]) -> str:
    """Markdown: each fixture's chains, then each tool summed over the fixtures, before and with the engine, as the
    median of every run and the lowest to highest."""
    runs: dict[str, list[dict]] = {}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        for label, rs in (data["bench"] if "bench" in data else data)["runs"].items():
            runs.setdefault(label, []).extend(r for r in rs if r)
    before, after = runs["before"], runs["engine"]
    names = [n for n in NAMES if all(n in r for r in before + after)]

    def chain(run, name, sc, key):
        return sum(r[key] or 0 for r in run[name][sc] if "wall" in r)

    def cell(xs):
        return f"{statistics.median(xs):.1f} ({min(xs):.1f} to {max(xs):.1f})"

    out = [f"Runs: {len(before)} before, {len(after)} with the engine.", "",
           "| Fixture | Scenario | Before, tool seconds | Engine, tool seconds | Before, wall | Engine, wall | Wall saved |",
           "|---|---|---|---|---|---|---|"]
    for name in names:
        for sc in SCENARIOS:
            b = [chain(r, name, sc, "seconds") for r in before]
            e = [chain(r, name, sc, "seconds") for r in after]
            bw = [chain(r, name, sc, "wall") for r in before]
            ew = [chain(r, name, sc, "wall") for r in after]
            out.append(f"| {name} | {sc} | {cell(b)} | {cell(e)} | {cell(bw)} | {cell(ew)} | "
                       f"{1 - statistics.median(ew) / statistics.median(bw):.0%} |")
    for sc in SCENARIOS:
        out += ["", f"Each tool in `{sc}`, wall seconds summed over the {len(names)} fixtures:", "",
                "| Tool | Before | Engine | Saved |", "|---|---|---|---|"]
        for tool in SCENARIOS[sc]:
            b = [sum(r["wall"] for n in names for r in run[n][sc] if r["tool"] == tool) for run in before]
            e = [sum(r["wall"] for n in names for r in run[n][sc] if r["tool"] == tool) for run in after]
            out.append(f"| {tool} | {cell(b)} | {cell(e)} | {1 - statistics.median(e) / statistics.median(b):.0%} |")
    restarts = [r[n].get("engine", {}).get("restarts", 0) for r in after for n in names]
    out += ["", f"Engine restarts (killed when the machine ran out of memory): {sum(restarts)}."]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("bench", help="before (one process per tool) and after (the engine), taking turns")
    p.add_argument("--before", type=Path, default=ROOT, help="the code for the before runs (a git archive of main)")
    p.add_argument("--after", type=Path, default=ROOT, help="the code for the engine runs (default: this one)")
    p.add_argument("--with-default-after", action="store_true", help="also the after code without the engine")
    p.add_argument("--fixtures", nargs="+", default=NAMES, choices=NAMES)
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--golden", type=Path, default=GOLDEN)
    p.add_argument("--readings", type=Path, help="the engine's readings folder for every run (warm after the first); "
                                                 "default a new one per run (cold)")
    p.add_argument("--flip", type=int, default=0, choices=[0, 1], help="1: the engine first in the first repeat")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("run")
    p.add_argument("--mode", choices=["default", "engine"], required=True)
    p.add_argument("--code", type=Path, default=ROOT, help="the repo copy whose spike/tools.py runs (default: this one)")
    p.add_argument("--fixtures", nargs="+", default=NAMES, choices=NAMES)
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--save", action="store_true", help="write the golden hashes from this run (today's code)")
    p.add_argument("--golden", type=Path, default=GOLDEN)
    p.add_argument("--times", type=Path, help="write every run's timings and their medians here")
    p.add_argument("--keep", type=Path, help="keep the lesson folders under this folder")
    p.add_argument("--readings", type=Path, help="engine: keep the outline model's readings here across runs (a warm "
                                                 "disk); default a new folder per fixture and run (cold)")
    p = sub.add_parser("save", help="the golden hashes from runs already made (their --times files), once every one "
                                    "of them agrees")
    p.add_argument("times", type=Path, nargs="+")
    p.add_argument("--golden", type=Path, default=GOLDEN)
    p = sub.add_parser("table", help="the before and after tables in docs/spikes/v3-one-engine.md, from bench files")
    p.add_argument("bench", type=Path, nargs="+")
    a = ap.parse_args()
    if a.cmd == "bench":
        return bench(a)
    if a.cmd == "table":
        print(tables(a.bench))
        return 0
    if a.cmd == "save":
        runs = [r for t in a.times for r in json.loads(t.read_text(encoding="utf-8"))["runs"]]
        diffs = [differences(hashes(runs[0]), hashes(r)) for r in runs[1:]]
        if any(diffs):
            print(json.dumps({"same_every_run": False, "run_differences": diffs}, indent=1))
            return 1
        a.golden.write_text(json.dumps({"made_with": "default path (one process per tool), the same in every one of "
                                                     f"{len(runs)} runs", "normalized": NORMALIZED,
                                        "fixtures": hashes(runs[0])}, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({"same_every_run": True, "runs": len(runs), "saved": str(a.golden)}))
        return 0
    code = a.code.resolve()
    runs = []
    for i in range(a.repeat):
        print(f"run {i + 1} of {a.repeat}, {a.mode}, code {code}", file=sys.stderr, flush=True)
        runs.append(run_all(code, a.mode, a.fixtures, a.keep, a.readings))
        if a.times:  # after every run, so a run that dies later doesn't take the earlier ones with it
            a.times.write_text(json.dumps({"mode": a.mode, "code": str(code), "table": timing_table(runs),
                                           "runs": runs}, indent=1), encoding="utf-8")
    report: dict = {"mode": a.mode, "code": str(code), "runs": len(runs)}
    same = [differences(hashes(runs[0]), hashes(r)) for r in runs[1:]]
    report["same_every_run"] = not any(same)
    if any(same):
        report["run_differences"] = same
    if a.save:
        a.golden.write_text(json.dumps({"made_with": "default path (one process per tool)", "normalized": NORMALIZED,
                                        "fixtures": hashes(runs[0])}, indent=1) + "\n", encoding="utf-8")
        report["saved"] = str(a.golden)
    else:
        gold = json.loads(a.golden.read_text(encoding="utf-8"))["fixtures"]
        gold = {n: gold[n] for n in a.fixtures}
        diffs = [differences(gold, hashes(r)) for r in runs]
        report["same_as_golden"] = not any(diffs)
        if any(diffs):
            report["golden_differences"] = diffs
    if a.times:
        a.times.write_text(json.dumps({"mode": a.mode, "code": str(code), "table": timing_table(runs), "runs": runs},
                                      indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0 if report["same_every_run"] and report.get("same_as_golden", True) else 1


if __name__ == "__main__":
    sys.exit(main())
