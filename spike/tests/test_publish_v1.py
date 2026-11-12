"""Version 1 lessons publish exactly as they did before pipeline v2 (docs/design/pipeline-v2.md section 13).

fixtures/v1-lesson/ is a small version 1 lesson made by hand (plan, text, review, notes, ledger, pictures).
fixtures/expected/ holds what publish made of it before any version 2 code went in: its lesson.json, its
lesson.html, and the checks publish printed. The test publishes it again and compares, leaving out only what
carries the time, the commit, and the version.

If a change to version 1 is meant (a new version of Gesso), regenerate the expected files with
    python spike/tests/test_publish_v1.py --write
and say in the commit what changed and why.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tools  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
EXPECTED = FIX / "expected"
STAMPED = ("gesso", "calls", "provenance")  # time, commit, and version: different on every publish
RESULT_KEYS = ("steps", "steps_by_source", "diagrams", "undocumented_diagrams", "unreachable_paints", "long_steps",
               "paints_not_listed", "duplicate_recipes", "texture_jumps", "long_instructions", "paid_renders",
               "cached_renders", "image_cost_usd", "previous_version")


def publish_fixture(tmp: Path, *extra: str) -> tuple[dict, str, dict]:
    """Copy the fixture lesson into tmp and publish it: (lesson.json, lesson.html, publish's printed result)."""
    lesson = tmp / "v1-lesson"
    shutil.copytree(FIX / "v1-lesson", lesson)
    out = io.StringIO()
    old = os.environ.get("GESSO_HISTORY")
    os.environ["GESSO_HISTORY"] = str(tmp / "history")
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            tools.main(["publish", "--lesson", str(lesson), *extra])
    finally:
        if old is None:
            os.environ.pop("GESSO_HISTORY", None)
        else:
            os.environ["GESSO_HISTORY"] = old
    result = json.loads(out.getvalue().strip().splitlines()[-1])
    data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
    return data, (lesson / "lesson.html").read_text(encoding="utf-8"), result


def unstamped(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in STAMPED}


def unstamped_html(html: str) -> str:
    return re.sub(r"Gesso POC [^<]*", "Gesso", html)


def checks(result: dict) -> dict:
    return {k: result.get(k) for k in RESULT_KEYS}


class PublishV1Tests(unittest.TestCase):
    def test_a_version_1_lesson_publishes_as_it_did_before(self):
        with tempfile.TemporaryDirectory() as d:
            data, html, result = publish_fixture(Path(d))
        want = json.loads((EXPECTED / "v1-lesson.json").read_text(encoding="utf-8"))
        self.assertEqual(unstamped(data), want)
        self.assertEqual(unstamped_html(html), (EXPECTED / "v1-lesson.html").read_text(encoding="utf-8"))
        self.assertEqual(checks(result), json.loads((EXPECTED / "v1-lesson-checks.json").read_text(encoding="utf-8")))

    def test_a_version_1_lesson_still_seals_by_the_old_rules(self):
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            publish_fixture(Path(d))
            os.environ["GESSO_HISTORY"] = str(Path(d) / "history")
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    tools.main(["publish", "--lesson", str(Path(d) / "v1-lesson"), "--final"])
            finally:
                os.environ.pop("GESSO_HISTORY", None)
        refused = json.loads(out.getvalue().strip().splitlines()[-1])["refused"]
        self.assertEqual(refused, (EXPECTED / "v1-lesson-seal.txt").read_text(encoding="utf-8").strip())


def write_expected() -> None:
    EXPECTED.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        data, html, result = publish_fixture(Path(d))
        os.environ["GESSO_HISTORY"] = str(Path(d) / "history")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            tools.main(["publish", "--lesson", str(Path(d) / "v1-lesson"), "--final"])
        os.environ.pop("GESSO_HISTORY", None)
    (EXPECTED / "v1-lesson.json").write_text(json.dumps(unstamped(data), indent=1) + "\n", encoding="utf-8")
    (EXPECTED / "v1-lesson.html").write_text(unstamped_html(html), encoding="utf-8")
    (EXPECTED / "v1-lesson-checks.json").write_text(json.dumps(checks(result), indent=1) + "\n", encoding="utf-8")
    seal = json.loads(out.getvalue().strip().splitlines()[-1]).get("refused", "")
    (EXPECTED / "v1-lesson-seal.txt").write_text(seal + "\n", encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1:] == ["--write"]:
        write_expected()
    else:
        unittest.main()
