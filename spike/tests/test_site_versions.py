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

    def test_refresh_keeps_listed_versions_when_output_is_empty(self):  # #83: a fresh checkout has no output/
        lesson = self.site / "lessons" / "lavender"
        (lesson / "v" / "20261111-142734").mkdir(parents=True)
        (lesson / "index.html").write_text("default", encoding="utf-8")
        (lesson / "v" / "20261111-142734" / "index.html").write_text("old", encoding="utf-8")
        listed = [{"id": "20261112-084806", "version": "POC 0.24.0", "when": "x", "guessed": False, "kind": "",
                   "steps": 2, "href": "lessons/lavender/", "current": True},
                  {"id": "20261111-142734", "version": "POC 0.20.0", "when": "y", "guessed": False, "kind": "",
                   "steps": 2, "href": "lessons/lavender/v/20261111-142734/", "current": False}]
        (self.site / "lessons.json").write_text(json.dumps([{"slug": "lavender", "title": "Balloon", "steps": 2,
                                                             "canvas": "", "tubes": 0, "source": "balloon_skill_20261112-084806",
                                                             "versions": listed, "known": 3}]), encoding="utf-8")
        empty = self.site.parent / "empty-output"
        empty.mkdir()
        self.assertEqual(site_lessons.refresh(self.site, empty), {"lavender": 2})
        entry = json.loads((self.site / "lessons.json").read_text(encoding="utf-8"))[0]
        self.assertEqual([v["id"] for v in entry["versions"]], ["20261112-084806", "20261111-142734"])
        self.assertEqual((lesson / "v" / "20261111-142734" / "index.html").read_text(encoding="utf-8"), "old")
        self.assertEqual((lesson / "index.html").read_text(encoding="utf-8"), "default")
        site_lessons.refresh(self.site, empty, remove=("20261111-142734",))  # only taken off when named
        entry = json.loads((self.site / "lessons.json").read_text(encoding="utf-8"))[0]
        self.assertEqual([v["id"] for v in entry["versions"]], ["20261112-084806"])
        self.assertFalse((lesson / "v" / "20261111-142734").exists())
        self.assertEqual(entry["known"], 3)  # the run isn't here to count them again, so the tile keeps its count

    def test_site_add_over_a_default_keeps_the_old_default_as_a_version(self):  # #83
        from unittest import mock
        from PIL import Image
        first = self.output / "balloon_skill_20261111-142734"
        later = self.output / "balloon_skill_20261112-084806"
        for d in (first, later):
            data = json.loads((d / "lesson.json").read_text(encoding="utf-8"))
            data["photo_read"] = {"subject": "Balloon"}
            (d / "lesson.json").write_text(json.dumps(data), encoding="utf-8")
            Image.new("RGB", (8, 8)).save(d / "f.png")
            (d / "sealed.json").unlink()
            provenance.seal(d, data)
        with mock.patch.object(site_lessons, "known_problems_for", return_value=0):
            site_lessons.add(first, "lavender", self.site)
            elsewhere = self.site.parent / "only-new"  # the old default's run folder isn't on this machine
            elsewhere.mkdir()
            later = later.rename(elsewhere / later.name)
            site_lessons.add(later, "lavender", self.site)
        entry = json.loads((self.site / "lessons.json").read_text(encoding="utf-8"))[0]
        self.assertEqual([(v["id"], v["current"]) for v in entry["versions"]],
                         [("20261112-084806", True), ("20261111-142734", False)])
        lesson = self.site / "lessons" / "lavender"
        self.assertIn(first.name, (lesson / "v" / "20261111-142734" / "index.html").read_text(encoding="utf-8"))
        self.assertIn(later.name, (lesson / "index.html").read_text(encoding="utf-8"))

    def test_refresh_makes_the_newest_hands_off_run_the_default(self):  # owner, 2026-11-13
        from unittest import mock
        from PIL import Image
        runs = [self.output / "balloon_skill_20261111-142734", self.output / "balloon_skill_20261112-084806"]
        for d in runs:
            data = json.loads((d / "lesson.json").read_text(encoding="utf-8"))
            data["photo_read"] = {"subject": "Balloon"}
            (d / "lesson.json").write_text(json.dumps(data), encoding="utf-8")
            Image.new("RGB", (8, 8)).save(d / "f.png")
            (d / "sealed.json").unlink()
            provenance.seal(d, data)
        with mock.patch.object(site_lessons, "known_problems_for", return_value=0):
            site_lessons.add(runs[0], "lavender", self.site)
            site_lessons.refresh(self.site, self.output)
        entry = json.loads((self.site / "lessons.json").read_text(encoding="utf-8"))[0]
        # the newer hands-off run is the default; the recut and the unsealed runs after it are passed over
        self.assertEqual(entry["source"], "balloon_skill_20261112-084806")
        self.assertEqual([(v["id"], v["current"]) for v in entry["versions"]],
                         [("20261112-084806", True), ("20261111-142734", False)])
        lesson = self.site / "lessons" / "lavender"
        self.assertIn(runs[1].name, (lesson / "index.html").read_text(encoding="utf-8"))
        self.assertIn(runs[0].name, (lesson / "v" / "20261111-142734" / "index.html").read_text(encoding="utf-8"))
        self.assertFalse((lesson / "v" / "20261112-084806").exists())  # no copy of the tile's own page
        with mock.patch.object(site_lessons, "known_problems_for", return_value=0):
            site_lessons.refresh(self.site, self.output)  # again: nothing changes
        self.assertEqual(json.loads((self.site / "lessons.json").read_text(encoding="utf-8"))[0]["source"],
                         "balloon_skill_20261112-084806")


if __name__ == "__main__":
    unittest.main()
