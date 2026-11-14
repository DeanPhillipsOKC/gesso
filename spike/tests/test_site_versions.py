"""Tests for the version pick list on the lessons site's tiles."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import provenance  # noqa: E402
import site_lessons  # noqa: E402


def run(output: Path, name: str, version: str, made_with: str = "render", kind: str = "hands-off",
        plan_version: int | None = 2) -> Path:
    d = output / name
    d.mkdir(parents=True)
    data = {"gesso": {"version": version, "commit": "abc1234", "published": "2026-11-12"},
            **({"plan_version": plan_version} if plan_version else {}),
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
        run(self.output, "balloon_skill_20261111-142734", "POC 1.0.0")
        run(self.output, "balloon_skill_20261112-084806", "POC 1.4.0", "composite:from-finish")
        run(self.output, "other_skill_20261112-090000", "POC 1.4.0")
        run(self.output, "balloon_skill_20261112-100000", "POC 1.4.0", "composite:from-finish", "recut")
        run(self.output, "balloon_skill_20261112-110000", "POC 1.4.0", kind="unsealed")

    def test_every_run_of_the_picture_is_a_version_and_pages_are_never_rewritten(self):
        versions = site_lessons.add_versions(self.site, "lavender", "balloon_skill_20261111-142734", self.output)
        self.assertEqual([v["version"] for v in versions], ["POC 1.4.0", "POC 1.0.0"])  # newest first, same picture
        self.assertEqual([v["current"] for v in versions], [False, True])
        self.assertEqual(versions[1]["href"], "lessons/lavender/")
        self.assertEqual(versions[0]["kind"], "steps cut from the finish")
        page = self.site / "lessons" / "lavender" / "v" / "20261112-084806" / "index.html"
        page.write_text("kept", encoding="utf-8")
        site_lessons.add_versions(self.site, "lavender", "balloon_skill_20261111-142734", self.output)
        self.assertEqual(page.read_text(encoding="utf-8"), "kept")

    def test_a_run_without_its_standalone_page_is_skipped_with_a_message(self):  # #82: no page rebuilt from lesson.json
        (self.output / "balloon_skill_20261112-084806" / "lesson-standalone.html").unlink()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            versions = site_lessons.add_versions(self.site, "lavender", "balloon_skill_20261111-142734", self.output)
        self.assertEqual([v["id"] for v in versions], ["20261111-142734"])
        self.assertIn("skipped balloon_skill_20261112-084806", out.getvalue())
        self.assertIn("lesson-standalone.html", out.getvalue())

    def test_a_v1_run_left_in_output_never_goes_back_on_the_site(self):  # #82: the tiles hold 1.0.0 on
        run(self.output, "balloon_skill_20261112-120000", "POC 0.26.1", "composite:from-finish", plan_version=None)
        versions = site_lessons.add_versions(self.site, "lavender", "balloon_skill_20261111-142734", self.output)
        self.assertNotIn("20261112-120000", [v["id"] for v in versions])
        self.assertFalse((self.site / "lessons" / "lavender" / "v" / "20261112-120000").exists())
        v1 = run(self.output, "sky_skill_20261112-130000", "POC 0.26.1", plan_version=None)
        self.assertIsNone(site_lessons.newest_hands_off("sky", self.output, site=self.site))
        with self.assertRaises(ValueError):
            site_lessons.add(v1, "sky", self.site)

    def test_a_v2_run_from_before_poc_1_0_0_never_goes_back_on_the_site(self):  # #141: the 0.26.1 runs were v2 plans
        old = run(self.output, "balloon_skill_20261113-011100", "POC 0.26.1", "composite:from-finish")
        self.assertFalse(site_lessons.on_site_era(old))
        republished = run(self.output, "balloon_skill_20261113-022000", "POC 1.8.1", "composite:from-finish")
        data = json.loads((republished / "lesson.json").read_text(encoding="utf-8"))
        data["gesso"]["made"] = {"version": "POC 0.26.1", "commit": "abc1234", "published": "2026-11-13"}
        (republished / "lesson.json").write_text(json.dumps(data), encoding="utf-8")
        (republished / "sealed.json").unlink()
        provenance.seal(republished, data)
        self.assertFalse(site_lessons.on_site_era(republished))  # the version that made it counts, not the republish
        unstamped = run(self.output, "balloon_skill_20261113-031300", "")
        self.assertFalse(site_lessons.on_site_era(unstamped))
        self.assertTrue(site_lessons.on_site_era(self.output / "balloon_skill_20261111-142734"))  # POC 1.0.0 itself
        versions = site_lessons.add_versions(self.site, "lavender", "balloon_skill_20261111-142734", self.output)
        self.assertEqual([v["id"] for v in versions], ["20261112-084806", "20261111-142734"])
        self.assertIsNone(site_lessons.newest_hands_off("sky", self.output, site=self.site))
        sky = run(self.output, "sky_skill_20261113-011100", "POC 0.26.1")
        self.assertIsNone(site_lessons.newest_hands_off("sky", self.output, site=self.site))
        with self.assertRaisesRegex(ValueError, "POC 0.26.1"):
            site_lessons.add(sky, "sky", self.site)

    def test_refresh_with_no_arguments_adds_none_of_the_0_26_1_runs(self):  # #141's acceptance
        from unittest import mock
        first = self.addable(self.output / "balloon_skill_20261111-142734")
        self.addable(self.output / "balloon_skill_20261112-084806")
        for name in ("balloon_skill_20261113-011100", "balloon_skill_20261113-022700", "balloon_skill_20261113-031300"):
            self.addable(run(self.output, name, "POC 0.26.1", "composite:from-finish"))
        with mock.patch.object(site_lessons, "known_problems_for", return_value=0):
            site_lessons.add(first, "lavender", self.site)
            site_lessons.refresh(self.site, self.output)
        entry = json.loads((self.site / "lessons.json").read_text(encoding="utf-8"))[0]
        self.assertEqual(entry["source"], "balloon_skill_20261112-084806")  # the newest 1.x run, not a 0.26.1 one
        self.assertEqual([v["id"] for v in entry["versions"]], ["20261112-084806", "20261111-142734"])
        self.assertEqual(sorted(p.name for p in (self.site / "lessons" / "lavender" / "v").iterdir()),
                         ["20261111-142734"])

    def test_a_run_kept_off_stays_off_without_remove(self):  # #141: site/kept-off.json
        from unittest import mock
        first = self.addable(self.output / "balloon_skill_20261111-142734")
        later = self.addable(self.output / "balloon_skill_20261112-084806")
        with mock.patch.object(site_lessons, "known_problems_for", return_value=0):
            site_lessons.add(first, "lavender", self.site)
            site_lessons.refresh(self.site, self.output)  # 084806 goes on, as the default
            other = self.addable(run(self.output, "balloon_skill_20261113-015433", "POC 1.4.0"))
            site_lessons.refresh(self.site, self.output)
            entry = json.loads((self.site / "lessons.json").read_text(encoding="utf-8"))[0]
            self.assertEqual(entry["source"], other.name)
            # keep 084806 off for good: it leaves the tile and its page goes, and later refreshes don't bring it back
            (self.site / "kept-off.json").write_text(json.dumps({later.name: "made from another branch"}),
                                                     encoding="utf-8")
            site_lessons.refresh(self.site, self.output)
            site_lessons.refresh(self.site, self.output)
        entry = json.loads((self.site / "lessons.json").read_text(encoding="utf-8"))[0]
        self.assertEqual([v["id"] for v in entry["versions"]], ["20261113-015433", "20261111-142734"])
        self.assertFalse((self.site / "lessons" / "lavender" / "v" / "20261112-084806").exists())
        self.assertEqual(site_lessons.kept_off(self.site), {later.name: "made from another branch"})
        with self.assertRaisesRegex(ValueError, "kept off the site"):
            site_lessons.add(later, "lavender", self.site)
        (self.site / "kept-off.json").write_text(json.dumps({other.name: "x"}), encoding="utf-8")
        self.assertEqual(site_lessons.newest_hands_off("balloon", self.output, site=self.site).name, later.name)

    def test_a_kept_off_default_hands_the_tile_to_the_newest_version_left(self):  # #141, PR #145's review
        from unittest import mock
        first = self.addable(self.output / "balloon_skill_20261111-142734")
        later = self.addable(self.output / "balloon_skill_20261112-084806")
        lesson = self.site / "lessons" / "lavender"
        out = io.StringIO()
        with mock.patch.object(site_lessons, "known_problems_for", return_value=0), contextlib.redirect_stdout(out):
            site_lessons.add(first, "lavender", self.site)
            site_lessons.refresh(self.site, self.output)  # 084806 is the default
            (self.site / "kept-off.json").write_text(json.dumps({later.name: "x"}), encoding="utf-8")
            site_lessons.refresh(self.site, self.output)
        entry = json.loads((self.site / "lessons.json").read_text(encoding="utf-8"))[0]
        self.assertEqual(entry["source"], first.name)  # its run is in output/: add() takes it
        self.assertEqual([(v["id"], v["current"]) for v in entry["versions"]], [("20261111-142734", True)])
        self.assertIn(first.name, (lesson / "index.html").read_text(encoding="utf-8"))
        self.assertFalse((lesson / "v").exists() and any((lesson / "v").iterdir()))
        self.assertIn("is kept off; the tile opens balloon_skill_20261111-142734", out.getvalue())

    def test_a_kept_off_default_with_only_listed_versions_left(self):  # #141: the run folders aren't here
        lesson = self.site / "lessons" / "lavender"
        (lesson / "v" / "20261111-142734").mkdir(parents=True)
        (lesson / "index.html").write_text("kept off", encoding="utf-8")
        (lesson / "v" / "20261111-142734" / "index.html").write_text("older", encoding="utf-8")
        listed = [{"id": "20261112-084806", "version": "POC 1.4.0", "when": "x", "guessed": False, "kind": "",
                   "steps": 5, "href": "lessons/lavender/", "current": True},
                  {"id": "20261111-142734", "version": "POC 1.0.0", "when": "y", "guessed": False, "kind": "",
                   "steps": 3, "href": "lessons/lavender/v/20261111-142734/", "current": False}]
        tiles = [{"slug": "lavender", "title": "Balloon", "steps": 5, "canvas": "", "tubes": 0, "version": "POC 1.4.0",
                  "source": "balloon_skill_20261112-084806", "versions": listed, "known": 0},
                 {"slug": "gone", "title": "Gone", "steps": 2, "canvas": "", "tubes": 0,
                  "source": "gone_skill_20261113-010101", "versions": [dict(listed[0], id="20261113-010101",
                                                                           href="lessons/gone/")], "known": 0}]
        (self.site / "lessons" / "gone").mkdir(parents=True)
        (self.site / "lessons" / "gone" / "index.html").write_text("x", encoding="utf-8")
        (self.site / "lessons.json").write_text(json.dumps(tiles), encoding="utf-8")
        (self.site / "kept-off.json").write_text(json.dumps({"balloon_skill_20261112-084806": "x",
                                                             "gone_skill_20261113-010101": "y"}), encoding="utf-8")
        empty = self.site.parent / "empty-output"
        empty.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(site_lessons.refresh(self.site, empty), {"lavender": 1})
        entry = json.loads((self.site / "lessons.json").read_text(encoding="utf-8"))
        self.assertEqual(len(entry), 1)  # no version of "gone" was left, so its tile went
        self.assertFalse((self.site / "lessons" / "gone").exists())
        self.assertEqual((entry[0]["source"], entry[0]["version"], entry[0]["steps"]),
                         ("balloon_skill_20261111-142734", "POC 1.0.0", 3))
        self.assertEqual([(v["id"], v["current"], v["href"]) for v in entry[0]["versions"]],
                         [("20261111-142734", True, "lessons/lavender/")])
        self.assertEqual((lesson / "index.html").read_text(encoding="utf-8"), "older")
        self.assertFalse((lesson / "v" / "20261111-142734").exists())

    def test_site_add_deletes_a_kept_off_versions_page(self):  # #141, PR #145's review
        from unittest import mock
        first = self.addable(self.output / "balloon_skill_20261111-142734")
        later = self.addable(self.output / "balloon_skill_20261112-084806")
        with mock.patch.object(site_lessons, "known_problems_for", return_value=0):
            site_lessons.add(first, "lavender", self.site)
            self.assertTrue((self.site / "lessons" / "lavender" / "v" / "20261112-084806").is_dir())
            (self.site / "kept-off.json").write_text(json.dumps({later.name: "x"}), encoding="utf-8")
            site_lessons.add(first, "lavender", self.site)
        self.assertFalse((self.site / "lessons" / "lavender" / "v" / "20261112-084806").exists())

    def test_kept_off_json_must_be_an_object_of_run_names(self):  # PR #145's review
        path = self.site / "kept-off.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(["balloon_skill_20261112-084806"]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must be an object of run folder name to why"):
            site_lessons.kept_off(self.site)
        path.write_text(json.dumps({"20261112-084806": "a bare run time"}), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(site_lessons.kept_off_ids(self.site, "balloon"), ())
        self.assertIn("'20261112-084806' isn't a run folder name", out.getvalue())

    def test_the_repos_kept_off_list_names_the_runs_the_docs_keep_off(self):  # docs/design/pipeline-v2.md, section 6
        off = site_lessons.kept_off()
        self.assertIn("chickadee_skill_20261114-015433", off)
        self.assertTrue(all(why for why in off.values()))
        listed = {f'{x["source"].split("_skill_")[0]}_skill_{v["id"]}'
                  for x in json.loads((site_lessons.SITE / "lessons.json").read_text(encoding="utf-8"))
                  for v in x["versions"]}
        self.assertFalse(listed & set(off))

    def addable(self, d: Path) -> Path:
        """A run site_lessons.add can take: a subject and a finish picture, sealed again."""
        from PIL import Image
        data = json.loads((d / "lesson.json").read_text(encoding="utf-8"))
        data["photo_read"] = {"subject": "Balloon"}
        (d / "lesson.json").write_text(json.dumps(data), encoding="utf-8")
        Image.new("RGB", (8, 8)).save(d / "f.png")
        if (d / "sealed.json").exists():
            (d / "sealed.json").unlink()
        provenance.seal(d, data)
        return d

    def test_tile_has_a_pick_list_with_the_current_version_selected(self):
        versions = site_lessons.add_versions(self.site, "lavender", "balloon_skill_20261111-142734", self.output)
        html = site_lessons.card({"slug": "lavender", "title": "Balloon", "steps": 2, "canvas": "", "tubes": 0,
                                  "version": "POC 1.0.0", "versions": versions})
        self.assertIn("<select>", html)
        self.assertIn('value="lessons/lavender/" data-steps="2" selected>POC 1.0.0', html)
        self.assertIn("· current", html)

    def test_refresh_keeps_listed_versions_when_output_is_empty(self):  # #83: a fresh checkout has no output/
        lesson = self.site / "lessons" / "lavender"
        (lesson / "v" / "20261111-142734").mkdir(parents=True)
        (lesson / "index.html").write_text("default", encoding="utf-8")
        (lesson / "v" / "20261111-142734" / "index.html").write_text("old", encoding="utf-8")
        listed = [{"id": "20261112-084806", "version": "POC 1.4.0", "when": "x", "guessed": False, "kind": "",
                   "steps": 2, "href": "lessons/lavender/", "current": True},
                  {"id": "20261111-142734", "version": "POC 1.0.0", "when": "y", "guessed": False, "kind": "",
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
