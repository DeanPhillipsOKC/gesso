"""Tests for the version stamp (#27)."""

from __future__ import annotations

import datetime as dt
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import version  # noqa: E402


class VersionTests(unittest.TestCase):
    def test_version_is_a_poc_number_with_a_changelog_entry(self):
        v = version.version()
        self.assertRegex(v, r"^POC \d+\.\d+\.\d+$")
        log = (Path(version.HERE).parent / "docs" / "changelog.md").read_text(encoding="utf-8")
        self.assertIn(f"## {v} (", log)

    def test_stamp_and_line(self):
        s = version.stamp(dt.date(2026, 11, 11))
        self.assertEqual(s["published"], "2026-11-11")
        self.assertTrue(re.fullmatch(r"[0-9a-f]{7,}|unknown", s["commit"]))
        clean = dict(s, commit="abc1234", dirty=False)
        self.assertEqual(version.line(clean), f"Gesso {s['version']} (abc1234) on 2026-11-11")
        self.assertIn("abc1234+dirty", version.line(dict(clean, dirty=True)))

    def test_dirty_tree_is_flagged(self):
        with mock.patch.object(version, "_git", side_effect=lambda *a: "abc1234" if a[0] == "rev-parse" else " M spike/x.py"):
            self.assertTrue(version.stamp()["dirty"])
        with mock.patch.object(version, "_git", side_effect=lambda *a: "abc1234" if a[0] == "rev-parse" else ""):
            self.assertFalse(version.stamp()["dirty"])


if __name__ == "__main__":
    unittest.main()


class MadeWithTests(unittest.TestCase):
    def test_republishing_keeps_the_made_with_version(self):
        first = version.with_made({"version": "POC 0.20.0", "commit": "aaa1111", "dirty": False, "published": "2026-11-10"}, None)
        self.assertEqual(first["made"]["version"], "POC 0.20.0")
        again = version.with_made({"version": "POC 0.23.0", "commit": "bbb2222", "dirty": False, "published": "2026-11-11"}, first)
        self.assertEqual(again["made"], first["made"])
        self.assertIn("republished with POC 0.23.0", version.made_line(again))
        self.assertNotIn("republished", version.made_line(first))
        old = {"version": "POC 0.17.0", "commit": "ccc3333", "dirty": False, "published": "2026-11-09"}  # no made yet
        self.assertEqual(version.with_made(first, old)["made"]["version"], "POC 0.17.0")
