"""Tests for the version pick list on the lessons site's tiles."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import provenance  # noqa: E402
import site_lessons  # noqa: E402


def run(output: Path, name: str, version: str, made_with: str = "render", kind: str = "hands-off") -> Path:
    d = output / name
    d.mkdir(parents=True)
    data = {"gesso": {"version": version, "commit": "abc1234", "published": "2026-11-12"},
            "stages": [{"id": "a", "image": "a.png", "made_with": made_with},
                       {"id": "finish", "image": "f.png", "made_with": "render"}]}
    (d / "lesson.json").write_text(json.dumps(data), encoding="utf-8")
    (d / "lesson-standalone.html").write_text(f"<p>{name}</p>", encoding="utf-8")
    if kind == "hands-off":
        provenance.seal(d, data)
    elif kind == "recut":
        provenance.derive(d, d, "test")
    return d


class SiteVersionTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.site, self.output = tmp / "site", tmp / "output"
        run(self.output, "balloon_skill_20261111-142734", "POC 0.20.0")
        run(self.output, "balloon_skill_20261112-084806", "POC 0.24.0", "composite:from-finish")
        run(self.output, "other_skill_20261112-090000", "POC 0.24.0")
        run(self.output, "balloon_skill_20261112-100000", "POC 0.24.0", "composite:from-finish", "recut")
        run(self.output, "balloon_skill_20261112-110000", "POC 0.24.0", kind="unsealed")

    def test_every_run_of_the_picture_is_a_version_and_pages_are_never_rewritten(self):
        versions = site_lessons.add_versions(self.site, "lavender", "balloon_skill_20261111-142734", self.output)
        self.assertEqual([v["version"] for v in versions], ["POC 0.24.0", "POC 0.20.0"])  # newest first, same picture
        self.assertEqual([v["current"] for v in versions], [False, True])
        self.assertEqual(versions[1]["href"], "lessons/lavender/")
        self.assertEqual(versions[0]["kind"], "steps cut from the finish")
        page = self.site / "lessons" / "lavender" / "v" / "20261112-084806" / "index.html"
        page.write_text("kept", encoding="utf-8")
        site_lessons.add_versions(self.site, "lavender", "balloon_skill_20261111-142734", self.output)
        self.assertEqual(page.read_text(encoding="utf-8"), "kept")

    def test_tile_has_a_pick_list_with_the_current_version_selected(self):
        versions = site_lessons.add_versions(self.site, "lavender", "balloon_skill_20261111-142734", self.output)
        html = site_lessons.card({"slug": "lavender", "title": "Balloon", "steps": 2, "canvas": "", "tubes": 0,
                                  "version": "POC 0.20.0", "versions": versions})
        self.assertIn("<select>", html)
        self.assertIn('value="lessons/lavender/" data-steps="2" selected>POC 0.20.0', html)
        self.assertIn("· current", html)


if __name__ == "__main__":
    unittest.main()
