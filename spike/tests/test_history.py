"""Tests for the lesson history (site/history/): nothing is overwritten, and the page says what changed."""

from __future__ import annotations

import datetime as dt
import json
import os
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

    def test_a_seal_with_the_drafts_pictures_takes_the_seals_numbers(self):
        """#135: the draft's entry kept its text_problems and minutes_total when the seal changed only the text."""
        folder, data = lesson(self.tmp, "chickadee_skill_20261114-022601", "POC 1.6.0")
        started = dt.datetime(2026, 11, 14, 2, 26, 1)

        def publish(at_minutes: float) -> dict:
            (folder / "lesson.json").write_text(json.dumps(data), encoding="utf-8")
            t = (started + dt.timedelta(minutes=at_minutes)).timestamp()
            os.utime(folder / "lesson.json", (t, t))
            return history.record(folder, data, {"long_instructions": []}, self.home)

        data["provenance"] = {"kind": "unsealed", "note": "not finished by the skill, or from before seals"}
        data["stages"][0]["summary"] = "Draft summary"
        self.assertTrue(publish(12.6)["recorded"])
        # the text review and a summary change; the step pictures, lines, and paints don't
        data["text_issues"] = [{"step": "s1", "kind": "wording"}] * 6
        data["stages"][0]["summary"] = "Sealed summary"
        data["provenance"] = {"kind": "hands-off", "sealed": "2026-11-14T02:43:55"}
        sealed = publish(17.9)
        self.assertFalse(sealed["recorded"])
        self.assertTrue(sealed["refreshed"])
        path = self.home / "chickadee" / folder.name / "record.json"
        rec = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(rec["publishes"]), 1)
        entry = rec["publishes"][0]
        self.assertEqual(entry["metrics"]["text_problems"], 6)
        self.assertEqual(entry["metrics"]["minutes_total"], 17.9)
        self.assertEqual(entry["provenance"]["kind"], "hands-off")
        self.assertTrue((path.parent / entry["strip"]).exists())
        kept = json.loads((folder / "versions" / "1" / "lesson.json").read_text(encoding="utf-8"))
        self.assertEqual(kept["stages"][0]["summary"], "Sealed summary")  # the kept lesson is the sealed one
        self.assertIn("7 review fixes", (self.home / "index.html").read_text(encoding="utf-8"))  # 1 step + 6 text
        # the same sealed lesson published again records nothing, and doesn't move its time
        before = path.read_text(encoding="utf-8")
        again = publish(30)
        self.assertFalse(again["recorded"])
        self.assertNotIn("refreshed", again)
        self.assertEqual(path.read_text(encoding="utf-8"), before)
        self.assertNotIn("refreshed", history.record(folder, data, None, self.home))  # a backfill keeps the checks
        self.assertEqual(path.read_text(encoding="utf-8"), before)

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
