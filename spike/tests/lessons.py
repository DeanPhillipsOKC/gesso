"""The three fixture lessons, built once per test run and shared by every test that needs one (#87).

    built(name)          -> (plan, pictures, rows, masks): build_steps.build on the fixture
    lesson(name, stage)  -> a fresh copy of the fixture's lesson folder after that stage's tools, to change freely
    results(name, stage) -> {tool: what it printed} for the tools of that stage and the ones before it
    history(name)        -> the GESSO_HISTORY folder the "published" stage recorded into

The stages, each run on the one before it, as the skill runs the tools:

    outlined   the fixture plan, finish, and saved outlines (what outline leaves)
    aided      + build-steps, step-aids, mix
    published  + publish (no step text: every step a draft)
    checked    + draft-text, check (aided, then the text tools; no publish)

Building a fixture is about 10 seconds a lesson, and publish builds on top of it; before this, test classes each built
all three from scratch. A stage is built the first time a test asks for it and kept in GESSO_TEST_CACHE, a folder the
runner (tests/suite.py) makes for one run and its workers share. A plain `python -m unittest` works too: without the
variable the cache is a temp folder for this process. A lock per fixture keeps two workers from building the same one.
"""

from __future__ import annotations

import atexit
import contextlib
import fcntl
import io
import json
import os
import pickle
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import build_steps as bs  # noqa: E402
import tools  # noqa: E402

FIX = HERE / "fixtures"
NAMES = ["chickadee", "lavender-balloon", "red-sailboat"]


def fixture(name: str):
    """(finish, plan, owner) of a fixture: a finished painting from the lessons site, its version 2 plan, and the
    outlines the model gave for it (fixtures/owners/)."""
    finish = np.array(Image.open(FIX / "finishes" / f"{name}.jpg").convert("RGB"))
    plan = json.loads((FIX / "plans" / f"{name}.json").read_text(encoding="utf-8"))
    owner = np.array(Image.open(FIX / "owners" / f"{name}.png")).astype(np.int32)
    return finish, plan, owner

FOLDER = "{name}_skill_20261112-090000"  # a run time in the name: history counts minutes from it
STAGES = {"outlined": (None, ()), "aided": ("outlined", ("build-steps", "step-aids", "mix")),
          "published": ("aided", ("publish",)), "checked": ("aided", ("draft-text", "check"))}


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
    """Marks a test class that takes seconds (builds or publishes a fixture, runs the outline model): tests/suite.py
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
        finish, plan, owner = fixture(name)
        (folder / "parts").mkdir(parents=True)
        (folder / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        Image.fromarray(finish).save(folder / "99_finish.png")
        Image.fromarray(owner.astype(np.uint8)).save(folder / "parts" / "owner.png")
        results = {}
    else:
        shutil.copytree(_stage(name, before), folder)
        results = json.loads((folder.parent.parent / before / "results.json").read_text(encoding="utf-8"))
        built(name)  # saved for the other workers, and in this process's memo for the tools below
        old = os.environ.get("GESSO_HISTORY")
        os.environ["GESSO_HISTORY"] = str(history(name))
        try:
            for tool in run:
                code, r = run_tool(tool, "--lesson", str(folder))
                assert code == 0, (name, tool, r)
                results[tool] = r
        finally:
            if old is None:
                os.environ.pop("GESSO_HISTORY", None)
            else:
                os.environ["GESSO_HISTORY"] = old
    (folder.parent / "results.json").write_text(json.dumps(results), encoding="utf-8")
    return folder


def _prime(name: str) -> None:
    """Put the fixture's saved build, if this run has one, in build_steps' memo: a tool run on the fixture in this
    process then doesn't build it again."""
    finish, plan, owner = fixture(name)
    key = bs._key(finish, plan, owner, None)
    path = _root() / name / "build.npz"
    if key not in bs._built and path.exists():
        _load(key, path)


def _load(key: str, path: Path) -> None:
    with np.load(path) as saved:
        rows = pickle.loads((path.parent / "rows.pickle").read_bytes())
        bs._built[key] = (list(saved["pictures"]), rows, list(saved["masks"]))


def built(name: str) -> tuple[dict, list[np.ndarray], list[dict], list[np.ndarray]]:
    """(plan, pictures, rows, masks) of build_steps.build on the fixture, each call a fresh copy."""
    finish, plan, owner = fixture(name)
    key = bs._key(finish, plan, owner, None)
    if key not in bs._built:
        path = _root() / name / "build.npz"
        with _locked(f"{name}-build"):
            if not path.exists():
                pictures, rows, masks = bs.build(finish, plan, owner)
                tmp = path.with_suffix(".tmp.npz")
                path.parent.mkdir(parents=True, exist_ok=True)
                np.savez(tmp, pictures=np.stack(pictures), masks=np.stack(masks))
                (path.parent / "rows.pickle").write_bytes(pickle.dumps(rows))
                tmp.rename(path)
        if key not in bs._built:
            _load(key, path)
    pictures, rows, masks = bs.build(finish, plan, owner)  # the memo's copy
    return plan, pictures, rows, masks


def lesson(name: str, stage: str, into: Path | None = None) -> Path:
    """A copy of the fixture lesson after `stage`, in its own new folder (under `into` when given)."""
    with _locked(name):
        src = _stage(name, stage)
    _prime(name)
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
