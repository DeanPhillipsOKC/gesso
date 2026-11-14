"""Tests for the busy measure (#109): how much of a picture is fine texture, and where."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import busy  # noqa: E402
import filters  # noqa: E402
import lesson_notes  # noqa: E402
import tools  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def run_tool(*args: str) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = tools.main(list(args))
    return code, json.loads(out.getvalue().strip().splitlines()[-1])


def calm(w=1200, h=800) -> np.ndarray:
    """A sky fading to a field, with one soft sun: big shapes, no texture."""
    y = np.linspace(0, 1, h)[:, None, None]
    sky = np.array([250, 190, 150]) * (1 - y) + np.array([150, 120, 200]) * y
    img = np.broadcast_to(sky, (h, w, 3)).astype(np.uint8).copy()
    img[h // 2:] = (120, 90, 160)
    cv2.circle(img, (w // 2, h // 3), h // 12, (255, 230, 170), -1)
    return cv2.GaussianBlur(img, (0, 0), 2)


def stalks(w=1200, h=800, top=0.5) -> np.ndarray:
    """The calm picture with a field of hundreds of thin stalks below `top` (a lavender field's texture)."""
    img = calm(w, h)
    rng = np.random.default_rng(7)
    for _ in range(round(2500 * (1 - top) / 0.5)):  # the same density however much of the picture it covers
        x, y = int(rng.integers(0, w)), int(rng.integers(int(h * top), h))
        tone = (60, 30, 90) if rng.random() < 0.5 else (200, 170, 235)  # dark and light stalks
        cv2.line(img, (x, y), (x + int(rng.integers(-3, 4)), y - int(rng.integers(8, 22))), tone, 2)
    return img


class MeasureTests(unittest.TestCase):
    def test_a_field_of_stalks_is_fine_texture_and_a_calm_picture_is_not(self):
        busy_pic = busy.measure(busy.to_work(stalks()))
        calm_pic = busy.measure(busy.to_work(calm()))
        self.assertGreater(busy_pic["fine_texture"], 0.25)  # most of the bottom half
        self.assertLess(busy_pic["fine_texture"], 0.55)  # nothing above the field
        self.assertEqual(calm_pic["fine_texture"], 0.0)
        self.assertGreater(busy_pic["edges"], calm_pic["edges"])
        self.assertEqual(busy_pic["tiles"], round(busy_pic["fine_texture"] * (800 * 1000 // 1200 // 40) * 25))

    def test_the_three_fixture_finishes_are_calm(self):
        # Painted finishes: brush marks only, under 2% (the spike's 15 finishes: 0.0 to 1.7%)
        for name in ("chickadee", "lavender-balloon", "red-sailboat"):
            r = busy.measure(busy.to_work(filters.load(FIXTURES / "finishes" / f"{name}.jpg")))
            self.assertLess(r["fine_texture"], 0.02, name)
            self.assertLess(r["edges"], 0.04, name)

    def test_size_doesnt_change_the_answer(self):
        small = busy.measure(busy.to_work(stalks(1200, 800)))
        big = busy.measure(busy.to_work(cv2.resize(stalks(1200, 800), (2400, 1600), interpolation=cv2.INTER_CUBIC)))
        self.assertAlmostEqual(small["fine_texture"], big["fine_texture"], delta=0.05)

    def test_the_picture_fades_all_but_the_texture_and_outlines_it(self):
        rgb = busy.to_work(stalks())
        out = busy.picture(rgb)
        self.assertEqual(out.shape, rgb.shape)
        sky = (slice(20, 60), slice(20, 60))  # far from the stalks: faded toward white
        self.assertGreater(out[sky].mean(), rgb[sky].mean())
        dense = busy.tiles(busy.edges(rgb))
        r, c = (int(v[0]) for v in np.nonzero(dense))
        t = busy.TILE
        inside = (slice(r * t + 4, r * t + t - 4), slice(c * t + 4, c * t + t - 4))
        np.testing.assert_array_equal(out[inside], rgb[inside])  # a texture tile at full color
        self.assertTrue((out[r * t, c * t + t // 2] == busy.MARK).all())  # with its outline


class LessonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.lesson = self.tmp / "lesson"
        self.lesson.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def frame(self, name: str, rgb: np.ndarray, band: int = 200) -> Path:
        """The picture in a frame with gray bands left and right, and canvas.json saying where the canvas is."""
        h, w = rgb.shape[:2]
        framed = np.full((h, w + 2 * band, 3), 128, np.uint8)
        framed[:, band:band + w] = rgb
        W = w + 2 * band
        (self.lesson / "canvas.json").write_text(json.dumps({
            "canvas": {"w_in": 12, "h_in": 8}, "frame_size": [W, h],
            "canvas_box": [round(band / W, 4), 0.0, round((band + w) / W, 4), 1.0]}), encoding="utf-8")
        return filters.save(framed, self.lesson / name)

    def notes(self) -> dict:
        return json.loads((self.lesson / "notes.json").read_text(encoding="utf-8"))

    def test_the_photo_is_measured_on_the_canvas_and_recorded_in_the_notes(self):
        photo = self.frame("00_canvas_frame.png", stalks())
        (self.lesson / "notes.json").write_text(json.dumps({"read": "a field", "beginner_version": "stalks"}))
        code, r = run_tool("busy", str(photo), "--lesson", str(self.lesson))
        self.assertEqual(code, 0, r)
        self.assertEqual((r["role"], r["measured"], r["problems"], r["cost_usd"]), ("photo", "the canvas", [], 0.0))
        self.assertGreater(r["fine_texture"], 0.25)
        self.assertNotIn("came_down", r)
        self.assertTrue((self.lesson / "busy" / "00_canvas_frame.jpg").exists())
        notes = self.notes()
        self.assertEqual(notes["read"], "a field")  # the rest of the notes kept
        self.assertEqual(notes["beginner_version"]["list"], "stalks")  # a sentence stands for the list, as the page reads it
        rec = notes["beginner_version"]["busy"]["photo"]
        self.assertEqual(rec, {"picture": "00_canvas_frame.png", "fine_texture": r["fine_texture"], "edges": r["edges"],
                               "tiles": r["tiles"], "where": "busy/00_canvas_frame.jpg"})
        # The same picture, measured again: the same numbers
        self.assertEqual(run_tool("busy", "00_canvas_frame.png", "--lesson", str(self.lesson))[1]["fine_texture"],
                         r["fine_texture"])

    def test_the_gray_bands_arent_measured(self):
        # Stalks in the bands only: the canvas inside is calm
        framed = np.full((800, 1600, 3), 128, np.uint8)
        framed[:, 200:1400] = calm()
        framed[:, :200] = stalks(200, 800, top=0.0)
        path = filters.save(framed, self.lesson / "00_canvas_frame.png")
        (self.lesson / "canvas.json").write_text(json.dumps({"frame_size": [1600, 800], "canvas_box": [0.125, 0, 0.875, 1]}))
        self.assertEqual(busy.run(path, self.lesson)["fine_texture"], 0.0)
        # A picture not in the frame's shape (a photo before fit-canvas) is measured whole
        whole = filters.save(stalks(), self.lesson / "photo.png")
        r = busy.run(whole, self.lesson, "photo")
        self.assertIn("the whole picture", r["measured"])

    def test_a_beginner_version_and_finish_must_bring_fine_texture_down(self):
        self.frame("00_canvas_frame.png", stalks())
        self.frame("00_beginner.png", calm())
        self.frame("99_finish.png", stalks(top=0.7))  # a finish that brought the stalks back, less of them
        busy.run(self.lesson / "00_canvas_frame.png", self.lesson)
        b = busy.run(self.lesson / "00_beginner.png", self.lesson)
        self.assertEqual((b["role"], b["came_down"]), ("beginner", True))
        f = busy.run(self.lesson / "99_finish.png", self.lesson)
        self.assertEqual(f["role"], "finish")
        self.assertTrue(f["came_down"])
        self.assertLess(f["fine_texture"], f["photo_fine_texture"])
        self.assertEqual(list(self.notes()["beginner_version"]["busy"]), ["photo", "beginner", "finish"])
        # One that didn't come down says so, and points at the redo
        filters.save(filters.load(self.lesson / "00_canvas_frame.png"), self.lesson / "00_beginner.png")
        b = busy.run(self.lesson / "00_beginner.png", self.lesson)
        self.assertFalse(b["came_down"])
        self.assertIn("one redo", b["advice"])

    def test_with_no_beginner_version_nothing_is_compared(self):
        # A calm picture's finish measures a little more than its photo from brush marks: out of scope (#109)
        self.frame("00_canvas_frame.png", calm())
        self.frame("99_finish.png", stalks(top=0.9))
        busy.run(self.lesson / "00_canvas_frame.png", self.lesson)
        r = busy.run(self.lesson / "99_finish.png", self.lesson)
        self.assertNotIn("came_down", r)
        self.assertIn("No beginner version", r["advice"])

    def test_the_seal_needs_the_numbers_and_the_page_shows_them(self):
        self.frame("00_canvas_frame.png", stalks())
        self.assertEqual(len(tools.busy_problems(self.lesson, {})), 1)
        busy.run(self.lesson / "00_canvas_frame.png", self.lesson)
        self.assertEqual(tools.busy_problems(self.lesson, self.notes()), [])
        self.frame("00_beginner.png", calm())
        said = tools.busy_problems(self.lesson, self.notes())
        self.assertEqual(len(said), 2)
        self.assertIn("run busy 00_beginner.png", said[0])
        self.assertIn("run busy 99_finish.png", said[1])
        self.frame("99_finish.png", calm())
        busy.run(self.lesson / "00_beginner.png", self.lesson)
        busy.run(self.lesson / "99_finish.png", self.lesson)
        notes = self.notes()
        self.assertEqual(tools.busy_problems(self.lesson, notes), [])
        line = lesson_notes.busy_line(notes["beginner_version"]["busy"])
        self.assertRegex(line, r"^the photo \d+\.\d%, the beginner version 0\.0%, the finish 0\.0% of the canvas$")
        self.assertEqual(lesson_notes.busy_line("not measured"), "")

    def test_a_picture_with_another_name_needs_as_and_never_replaces_the_photo_silently(self):
        self.frame("00_canvas_frame.png", stalks())
        busy.run(self.lesson / "00_canvas_frame.png", self.lesson)
        photo = self.notes()["beginner_version"]["busy"]["photo"]
        redo = self.frame("00_beginner_redo.png", calm())
        code, r = run_tool("busy", str(redo), "--lesson", str(self.lesson))
        self.assertEqual(code, 2)
        self.assertIn("--as photo|beginner|finish", r["refused"])
        self.assertEqual(self.notes()["beginner_version"]["busy"], {"photo": photo})  # nothing recorded
        code, r = run_tool("busy", str(redo), "--lesson", str(self.lesson), "--as", "beginner")
        self.assertEqual((code, r["role"], r["came_down"]), (0, "beginner", True))
        self.assertEqual(self.notes()["beginner_version"]["busy"]["photo"], photo)

    def test_a_beginner_number_with_no_photo_number_asks_for_the_photo(self):
        self.frame("00_beginner.png", calm())
        r = busy.run(self.lesson / "00_beginner.png", self.lesson)
        self.assertNotIn("came_down", r)
        self.assertIn("no photo number", r["advice"])

    def test_nothing_left_to_remove_counts_as_came_down(self):
        self.frame("00_canvas_frame.png", calm())
        self.frame("00_beginner.png", calm())
        busy.run(self.lesson / "00_canvas_frame.png", self.lesson)
        r = busy.run(self.lesson / "00_beginner.png", self.lesson)
        self.assertEqual((r["fine_texture"], r["photo_fine_texture"], r["came_down"]), (0.0, 0.0, True))

    def test_a_turned_down_beginner_render_left_on_disk_doesnt_hold_up_the_seal(self):
        self.frame("00_canvas_frame.png", calm())
        self.frame("00_beginner.png", calm())
        busy.run(self.lesson / "00_canvas_frame.png", self.lesson)
        notes = self.notes()
        self.assertEqual(len(tools.busy_problems(self.lesson, notes)), 2)  # the notes don't say: the file decides
        notes["beginner_version"]["made"] = False
        self.assertEqual(tools.busy_problems(self.lesson, notes), [])
        (self.lesson / "00_beginner.png").unlink()
        notes["beginner_version"]["made"] = True  # the notes say one was made: it was
        self.assertEqual(len(tools.busy_problems(self.lesson, notes)), 2)

    def test_refusals(self):
        code, r = run_tool("busy", "nope.png", "--lesson", str(self.lesson))
        self.assertEqual(code, 2)
        self.assertIn("no picture", r["refused"])
        filters.save(calm(), self.lesson / "photo.png")
        (self.lesson / "notes.json").write_text("{not json")
        code, r = run_tool("busy", "photo.png", "--lesson", str(self.lesson), "--as", "photo")
        self.assertEqual(code, 2)
        self.assertIn("notes.json isn't valid JSON", r["refused"])
        (self.lesson / "notes.json").write_text("[1, 2]")
        code, r = run_tool("busy", "photo.png", "--lesson", str(self.lesson), "--as", "photo")
        self.assertEqual(code, 2)
        self.assertIn("isn't a JSON object", r["refused"])
        self.assertEqual((self.lesson / "notes.json").read_text(), "[1, 2]")  # left as it was


if __name__ == "__main__":
    unittest.main()
