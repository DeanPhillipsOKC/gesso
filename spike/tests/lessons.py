"""The three fixture lessons, built once per test run and shared by every test that needs one (#87).

    built(name)          -> (plan, pictures, rows, masks): what build-steps kept for the fixture (lesson3.read)
    lesson(name, stage)  -> a fresh copy of the fixture's lesson folder after that stage's tools, to change freely
    results(name, stage) -> {tool: what it printed} for the tools of that stage and the ones before it
    history(name)        -> the GESSO_HISTORY folder the "published" stage recorded into

Each fixture is a sealed version 3 run made small (fixtures/lessons/<name>/, tests/make_fixtures.py): its plan, its
canvas, its chain, the chain checker's answers and the stage writers' words. The stages, each run on the one before
it, as the skill runs the tools:

    chained    the plan, canvas, finish and chain (what erase leaves)
    built      + build-steps, step-aids, mix
    published  + publish (no step text: every step a draft)
    checked    + draft-text, check (built, then the text tools; no publish)
    worded     + packets, the writers' words, check-text --final (checked, then the words)

A stage is built the first time a test asks for it and kept in GESSO_TEST_CACHE, a folder the runner
(tests/suite.py) makes for one run and its workers share. A plain `python -m unittest` works too: without the
variable the cache is a temp folder for this process. A lock per fixture keeps two workers from building the same one.
"""

from __future__ import annotations

import atexit
import contextlib
import fcntl
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import erase3  # noqa: E402
import lesson3  # noqa: E402
import plan3  # noqa: E402
import tools  # noqa: E402

FIX = HERE / "fixtures" / "lessons"
NAMES = ["chickadee", "lavender-balloon", "red-sailboat"]
CANVAS = {"w_in": 16.0, "h_in": 12.0, "orientation": "landscape"}  # every fixture's canvas (canvas.json)


def chain_into(name: str, folder: Path) -> None:
    """The fixture as erase leaves it: plan.json, canvas.json, 99_finish.png (the last picture of the chain) and
    chain/, with its made_for worked out for this finish."""
    src = FIX / name
    (folder / "chain" / "looks").mkdir(parents=True)
    plan = json.loads((src / "plan.json").read_text(encoding="utf-8"))
    for f in ("plan.json", "canvas.json"):
        shutil.copyfile(src / f, folder / f)
    ps = sorted((src / "chain").glob("P[0-9][0-9].jpg"))
    for p in ps:
        Image.open(p).convert("RGB").save(folder / "chain" / f"{p.stem}.png")
        for kind in "DC":
            shutil.copyfile(src / "chain" / f"{kind}{p.stem[1:]}.png", folder / "chain" / f"{kind}{p.stem[1:]}.png")
    shutil.copyfile(folder / "chain" / f"{ps[-1].stem}.png", folder / "99_finish.png")
    kept = json.loads((src / "chain" / "chain.json").read_text(encoding="utf-8"))
    again = {int(k): v for k, v in (kept.get("again") or {}).items()}
    finish = np.array(Image.open(folder / "99_finish.png").convert("RGB"))
    kept["made_for"] = erase3.made_for(plan, plan3.units(plan), finish, again)
    (folder / "chain" / "chain.json").write_text(json.dumps(kept, indent=1), encoding="utf-8")
    if (src / "answers.json").exists():
        shutil.copyfile(src / "answers.json", folder / "chain" / "looks" / "answers.json")
    for n in range(1, len(ps)):  # a look a unit, as erase leaves them, so the seal's "every unit" rule has units
        Image.open(folder / "chain" / f"P{n:02d}.png").convert("RGB").resize((64, 43)).save(
            folder / "chain" / "looks" / f"U{n:02d}.jpg")


def words_into(name: str, folder: Path) -> None:
    """The stage writers' out.json from the run the fixture was made from, into the packets' folders."""
    for stage, out in json.loads((FIX / name / "words.json").read_text(encoding="utf-8")).items():
        if (folder / "words" / stage).is_dir():
            (folder / "words" / stage / "out.json").write_text(json.dumps(out), encoding="utf-8")


FOLDER = "{name}_skill_20261112-090000"  # a run time in the name: history counts minutes from it
STAGES = {"chained": (None, ()), "built": ("chained", ("build-steps", "step-aids", "mix")),
          "published": ("built", ("publish",)), "checked": ("built", ("draft-text", "check")),
          "worded": ("checked", ("packets", words_into, "check-text --final"))}


def _root() -> Path:
    root = os.environ.get("GESSO_TEST_CACHE")
    if not root:
        root = tempfile.mkdtemp(prefix="gesso-tests-")
        atexit.register(shutil.rmtree, root, True)
        os.environ["GESSO_TEST_CACHE"] = root  # this process only; the runner sets it for all its workers
    return Path(root)


@contextlib.contextmanager
def _locked(name: str):
    path = _root() / f"{name}.lock"
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def slow(cls):
    """Marks a test class that takes seconds (builds or publishes a fixture): tests/suite.py
    --quick leaves it out."""
    cls.slow = True
    return cls


def run_tool(*argv) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = tools.main(list(argv))
    return code, json.loads(out.getvalue().strip().splitlines()[-1])


def history(name: str) -> Path:
    return _root() / name / "history"


def _stage(name: str, stage: str) -> Path:
    """The cached folder for a stage, built (with the stages before it) if this run hasn't yet. Call under the lock."""
    folder = _root() / name / stage / FOLDER.format(name=name)
    if (folder.parent / "results.json").exists():
        return folder
    before, run = STAGES[stage]
    shutil.rmtree(folder.parent, ignore_errors=True)  # what a build that failed part way left
    if before is None:
        chain_into(name, folder)
        results = {}
    else:
        shutil.copytree(_stage(name, before), folder)
        results = json.loads((folder.parent.parent / before / "results.json").read_text(encoding="utf-8"))
        old = os.environ.get("GESSO_HISTORY")
        os.environ["GESSO_HISTORY"] = str(history(name))
        try:
            for tool in run:
                if callable(tool):
                    tool(name, folder)
                    continue
                code, r = run_tool(*tool.split()[:1], "--lesson", str(folder), *tool.split()[1:])
                assert code == 0, (name, tool, r)
                results[tool.split()[0]] = r
        finally:
            if old is None:
                os.environ.pop("GESSO_HISTORY", None)
            else:
                os.environ["GESSO_HISTORY"] = old
    (folder.parent / "results.json").write_text(json.dumps(results), encoding="utf-8")
    return folder


def built(name: str) -> tuple[dict, list[np.ndarray], list[dict], list[np.ndarray]]:
    """(plan, pictures, rows, masks): what build-steps kept for the fixture, the plan in version 2's shape (the
    shape step-aids, draft-text, check and publish read). Each call a fresh copy."""
    with _locked(name):
        src = _stage(name, "built")
    kept = lesson3.read(src)
    return kept["plan"], kept["pictures"], kept["rows"], kept["masks"]


def owner(name: str) -> np.ndarray:
    """Which unit (the plan's part, in version 2's shape) each pixel of the fixture's finish belongs to."""
    with _locked(name):
        src = _stage(name, "built")
    return lesson3.read(src, pictures=False)["owner"]


def lesson(name: str, stage: str, into: Path | None = None) -> Path:
    """A copy of the fixture lesson after `stage`, in its own new folder (under `into` when given)."""
    with _locked(name):
        src = _stage(name, stage)
    if into is not None:
        Path(into).mkdir(parents=True, exist_ok=True)
    dst = Path(tempfile.mkdtemp(dir=into)) / src.name
    shutil.copytree(src, dst)
    return dst


def results(name: str, stage: str) -> dict:
    with _locked(name):
        src = _stage(name, stage)
    return json.loads((src.parent / "results.json").read_text(encoding="utf-8"))


def warm(name: str) -> None:
    """Build every stage of one fixture (the runner does this first, one fixture per worker)."""
    for stage in STAGES:
        results(name, stage)
