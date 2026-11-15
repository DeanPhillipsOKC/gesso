"""Tests for the source pictures kept in photos/ (#147): store-photo, and the site tools' warning when a tile's
picture isn't stored."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pictures  # noqa: E402
import site_lessons  # noqa: E402
import tools  # noqa: E402

HAS_GIT = shutil.which("git") is not None


def picture(path: Path, color=(200, 30, 30)) -> Path:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color).save(path)
    return path


def git_init(folder: Path) -> None:
    subprocess.run(["git", "init", "-q", str(folder)], check=True)


def git_add(folder: Path, *names: str) -> None:
    subprocess.run(["git", "-C", str(folder), "add", "--", *names], check=True)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.photos = self.tmp / "repo" / "photos"
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_a_new_picture_is_copied_in_under_its_stem_and_the_owner_is_told_to_commit_it(self):
        src = picture(self.tmp / "downloads" / "red-sailboat.JPG")
        r = pictures.store(src, self.photos)
        self.assertEqual(r["problems"], [])
        self.assertTrue(r["copied"])
        self.assertEqual((self.photos / "red-sailboat.jpg").read_bytes(), src.read_bytes())
        self.assertIn("Commit", r["next"])
        self.assertIn("personal photo", r["next"])  # the skill says so when it stores a picture
        again = pictures.store(src, self.photos)
        self.assertFalse(again["copied"])
        self.assertEqual(again["problems"], [])

    def test_a_picture_already_in_photos_is_left_where_it_is(self):
        src = picture(self.photos / "chickadee.jpg")
        r = pictures.store(src, self.photos)
        self.assertFalse(r["copied"])
        self.assertEqual(r["problems"], [])
        self.assertEqual(sorted(p.name for p in self.photos.iterdir()), ["chickadee.jpg"])

    def test_a_different_picture_with_a_stored_pictures_name_is_a_problem(self):
        stored = picture(self.photos / "chickadee.jpg")
        before = stored.read_bytes()
        r = pictures.store(picture(self.tmp / "elsewhere" / "chickadee.png", (10, 200, 10)), self.photos)
        self.assertEqual(len(r["problems"]), 1)
        self.assertIn("different picture with the same name", r["problems"][0])
        self.assertFalse(r["copied"])
        self.assertEqual(stored.read_bytes(), before)
        self.assertFalse((self.photos / "chickadee.png").exists())

    def test_a_picture_in_photos_private_stays_out_of_the_repo(self):
        src = picture(self.photos / "private" / "grandma.jpg")
        r = pictures.store(src, self.photos)
        self.assertEqual(r["problems"], [])
        self.assertFalse(r["copied"])
        self.assertEqual(r["stored"], "")
        self.assertFalse((self.photos / "grandma.jpg").exists())

    def test_a_file_that_isnt_a_kept_picture_type_is_a_problem(self):
        src = self.tmp / "cat.heic"
        src.write_bytes(b"x")
        self.assertTrue(pictures.store(src, self.photos)["problems"])
        self.assertTrue(pictures.store(self.tmp / "nope.jpg", self.photos)["problems"])

    @unittest.skipUnless(HAS_GIT, "needs git")
    def test_committed_says_whether_git_tracks_it(self):
        repo = self.photos.parent
        git_init(repo)
        a, b = picture(self.photos / "a.jpg"), picture(self.photos / "b.jpg")
        git_add(repo, "photos/a.jpg")
        self.assertIs(pictures.committed(a), True)
        self.assertIs(pictures.committed(b), False)
        self.assertFalse(pictures.store(a, self.photos).get("next"))  # tracked: nothing to commit
        self.assertIn("git add", pictures.store(b, self.photos)["next"])
        outside = picture(self.tmp / "loose" / "c.jpg")
        if subprocess.run(["git", "-C", str(outside.parent), "rev-parse"], capture_output=True).returncode != 0:
            self.assertIsNone(pictures.committed(outside))

    def test_store_photo_tool_prints_the_result(self):
        src = picture(self.tmp / "snow-lantern.png")
        out = io.StringIO()
        with mock.patch.object(pictures, "PHOTOS", self.photos):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = tools.main(["store-photo", str(src)])
        self.assertEqual(code, 0)
        r = json.loads(out.getvalue())
        self.assertTrue(r["copied"])
        self.assertTrue((self.photos / "snow-lantern.png").exists())


class MissingPictureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.site, self.photos = self.tmp / "site", self.tmp / "photos"
        self.site.mkdir()
        tiles = [{"slug": "chickadee", "source": "chickadee_skill_20261114-075954"},
                 {"slug": "lavender-balloon", "source": "balloon-lavender_skill_20261114-075951"},
                 {"slug": "red-sailboat", "source": "red-sailboat_skill_20261113-212457"}]
        (self.site / "lessons.json").write_text(json.dumps(tiles), encoding="utf-8")

    def test_names_each_tile_whose_picture_isnt_stored(self):
        picture(self.photos / "chickadee.jpg")
        picture(self.photos / "red-sailboat.png")
        with mock.patch.object(pictures, "committed", return_value=None):  # not a git checkout: can't tell
            warnings = site_lessons.missing_pictures(self.site, self.photos)
        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0].startswith("lavender-balloon:"))
        self.assertIn("photos/balloon-lavender.jpg", warnings[0])  # named by the photo stem, not the slug

    @unittest.skipUnless(HAS_GIT, "needs git")
    def test_a_stored_picture_that_isnt_committed_is_named_too(self):
        git_init(self.tmp)
        for stem in ("chickadee", "balloon-lavender", "red-sailboat"):
            picture(self.photos / f"{stem}.jpg")
        git_add(self.tmp, "photos/chickadee.jpg", "photos/balloon-lavender.jpg")
        warnings = site_lessons.missing_pictures(self.site, self.photos)
        self.assertEqual(warnings, ["red-sailboat: photos/red-sailboat.jpg isn't committed; commit it so other "
                                    "sessions can rerun it"])

    def test_no_site_no_warnings(self):
        self.assertEqual(site_lessons.missing_pictures(self.tmp / "nowhere", self.photos), [])

    def test_site_add_and_site_refresh_print_the_warnings(self):
        for argv, patch in ((["site-refresh"], "refresh"), (["site-add", "--lesson", "x", "--slug", "y"], "add")):
            out = io.StringIO()
            with mock.patch.object(site_lessons, patch, return_value={}), \
                    mock.patch.object(site_lessons, "missing_pictures", return_value=["sleeping-cat: no source picture"]):
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(tools.main(argv), 0)
            self.assertEqual(json.loads(out.getvalue())["warnings"], ["sleeping-cat: no source picture"], argv)


class RepoPictureTests(unittest.TestCase):
    """The repo's own photos/ folder: tracked, and never served by the site."""

    def test_photos_are_tracked_and_photos_private_is_ignored(self):
        if not HAS_GIT:
            self.skipTest("needs git")
        root = pictures.ROOT

        def ignored(path: str) -> bool:
            return subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--no-index", path]).returncode == 0
        self.assertFalse(ignored("photos/some-picture.jpg"))
        self.assertTrue(ignored("photos/private/some-photo.jpg"))

    def test_the_chickadee_tile_has_its_picture(self):
        tiles = json.loads((site_lessons.SITE / "lessons.json").read_text(encoding="utf-8"))
        if any(x["source"].startswith("chickadee_skill_") for x in tiles):
            self.assertIsNotNone(pictures.stored("chickadee"))
            self.assertFalse(any(w.startswith("chickadee:") for w in site_lessons.missing_pictures()))

    def test_no_file_on_the_site_is_a_source_picture(self):
        digests = {hashlib.sha256(p.read_bytes()).hexdigest(): p.name
                   for p in pictures.PHOTOS.rglob("*") if p.is_file()} if pictures.PHOTOS.is_dir() else {}
        for p in site_lessons.SITE.rglob("*"):
            self.assertNotEqual(p.name, "photos", f"{p} would put the source pictures on the site")
            if p.is_file() and p.stat().st_size < 50_000_000:
                self.assertNotIn(hashlib.sha256(p.read_bytes()).hexdigest(), digests, f"{p} is a source picture")


if __name__ == "__main__":
    unittest.main()
