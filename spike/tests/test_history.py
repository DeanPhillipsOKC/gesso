"""Tests for the lesson history (site/history/): nothing is overwritten, and the page says what changed."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

import history  # noqa: E402


def lesson(root: Path, name: str, version: str, color=(90, 140, 220)) -> tuple[Path, dict]:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    for i in (1, 2):
        Image.new("RGB", (30, 40), color).save(folder / f"0{i}_s{i}.png")
    data = {"gesso": {"version": version, "commit": "abc1234", "dirty": False, "published": "2026-11-12"},
            "photo": "balloon-lavender.png", "technique": "t", "tubes": ["white"],
            "stages": [{"id": f"s{i}", "name": f"Step {i}", "image": f"0{i}_s{i}.png", "steps": ["Paint it"],
                        "made_with": "render"} for i in (1, 2)],
            "calls": [{"tool": "render", "cached": False}], "total_cost_usd": 0.1, "total_seconds": 120,
            "review_issues": [{"action": "redone"}], "text_issues": []}
    return folder, data


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "history"

    def test_keeps_every_publish_that_changed_and_skips_one_that_did_not(self):
        folder, data = lesson(self.tmp, "balloon-lavender_skill_20261111-142734", "POC 0.20.0")
        self.assertTrue(history.record(folder, data, {"long_steps": [1]}, self.home)["recorded"])
        self.assertFalse(history.record(folder, data, None, self.home)["recorded"])  # same pictures and text
        data["stages"][0]["steps"] = ["Paint it lighter"]
        self.assertEqual(history.record(folder, data, None, self.home)["publish"], 2)
        rec = json.loads((self.home / "balloon-lavender" / folder.name / "record.json").read_text(encoding="utf-8"))
        self.assertEqual([p["n"] for p in rec["publishes"]], [1, 2])
        self.assertEqual(rec["publishes"][0]["metrics"]["checks"]["long_steps"], 1)
        self.assertEqual(rec["publishes"][0]["metrics"]["redos"], 1)
        self.assertTrue((self.home / "balloon-lavender" / folder.name / "strip-2.jpg").exists())

    def test_page_lists_what_changed_between_runs(self):
        a, da = lesson(self.tmp, "balloon-lavender_skill_20261111-083555", "POC 0.13.0")
        b, db = lesson(self.tmp, "balloon-lavender_skill_20261111-142734", "POC 0.20.0", (200, 100, 50))
        history.record(a, da, None, self.home)
        history.record(b, db, None, self.home)
        page = (self.home / "index.html").read_text(encoding="utf-8")
        self.assertIn("since the run before", page)
        self.assertIn("POC 0.20.0", page)
        self.assertLess(page.index("20261111-142734#1"), page.index("20261111-083555#1"))  # newest first

    def test_between_and_changelog(self):
        log = {"POC 0.9.0": ["a"], "POC 0.10.0": ["b"], "POC 0.20.0": ["c"], "POC 0.21.0": ["d"]}
        self.assertEqual([v for v, _ in history.between(log, "POC 0.9.0", "POC 0.20.0")], ["POC 0.10.0", "POC 0.20.0"])
        real = history.changelog()
        self.assertIn("POC 0.23.1", real)
        self.assertTrue(all(isinstance(b, str) for bs in real.values() for b in bs))

    def test_rating_shows_on_the_page(self):
        folder, data = lesson(self.tmp, "balloon-lavender_skill_20261111-142734", "POC 0.20.0")
        history.record(folder, data, None, self.home)
        history.rate(folder.name, 2, "lavender went blocky", self.home)
        self.assertIn("Rated 2/5", (self.home / "index.html").read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            history.rate(folder.name, 9, "", self.home)


if __name__ == "__main__":
    unittest.main()
