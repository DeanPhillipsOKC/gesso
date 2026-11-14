"""Tests for fitting a picture to the painter's canvas."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import canvas  # noqa: E402


def wide(w=1536, h=1024):
    return Image.new("RGB", (w, h), (120, 160, 200))


class CanvasTests(unittest.TestCase):
    def test_parse_and_orientation(self):
        self.assertEqual(canvas.parse("11x14"), (11.0, 14.0))
        self.assertEqual(canvas.parse("24 x 30 in"), (24.0, 30.0))
        with self.assertRaises(ValueError):
            canvas.parse("big")
        self.assertEqual(canvas.orient(11, 14, 1.5), (14, 11))  # a wide picture hangs the canvas sideways
        self.assertEqual(canvas.orient(11, 14, 0.7), (11, 14))
        self.assertEqual(canvas.orient(14, 11, 1.5, "portrait"), (11, 14))

    def test_same_shape_needs_nothing(self):
        r = canvas.fit(wide(), "15x10")
        self.assertEqual(r["mode"], "none")
        self.assertFalse(r["needs_render"])
        self.assertEqual(r["canvas_box"], [0.0, 0.0, 1.0, 1.0])

    def test_crop_splits_evenly_when_the_subject_allows(self):
        # 14x11 from a 3:2 picture: the boat at 68-87% across fits a centered crop, so cut both sides equally
        r = canvas.fit(wide(), "11x14", focus=(0.78, 0.5), keep=(0.68, 0.25, 0.87, 0.65))
        self.assertEqual(r["mode"], "crop")
        x0, _, x1, _ = r["crop_box"]
        self.assertAlmostEqual(x0, 1536 - x1, delta=1)

    def test_crop_shifts_only_as_far_as_the_subject_needs(self):
        r = canvas.fit(wide(), "10x10", focus=(0.8, 0.5), keep=(0.7, 0.3, 0.9, 0.7))
        self.assertEqual(r["mode"], "crop")
        x0, _, x1, _ = r["crop_box"]
        self.assertEqual(x1, round(0.9 * 1536))  # its right edge just holds the subject
        self.assertFalse(r["needs_render"])  # a square canvas fits the square frame

    def test_frame_shaped_photo_needs_no_render_after_a_crop(self):
        r = canvas.fit(wide(), "11x14", focus=(0.78, 0.5), keep=(0.68, 0.25, 0.87, 0.65))
        self.assertFalse(r["needs_render"])  # the cut-off edges are the bands
        self.assertEqual(r["frame_size"], [1536, 1024])
        self.assertAlmostEqual(r["canvas_box"][0], r["crop_box"][0] / 1536, places=3)

    def test_subject_that_wont_survive_a_crop_is_extended(self):
        r = canvas.fit(wide(), "10x10", focus=(0.5, 0.5), keep=(0.05, 0.2, 0.95, 0.8))
        self.assertEqual(r["mode"], "extend")
        self.assertTrue(r["needs_render"])
        self.assertEqual(r["frame"].getpixel((512, 5)), canvas.PAD)  # gray above the picture, for the model to fill

    def test_11x14_sits_in_a_frame_with_bands(self):
        # the whole picture must stay (keep is everything), so it's extended, and the frame has bands to fill
        r = canvas.fit(Image.new("RGB", (1024, 1536)), "11x14", focus=(0.5, 0.5), keep=(0, 0, 1, 1))
        self.assertEqual(r["mode"], "extend")
        self.assertEqual(r["canvas"]["orientation"], "portrait")
        self.assertEqual(r["frame_size"], [1024, 1536])
        x0, y0, x1, y1 = r["canvas_box"]
        self.assertAlmostEqual((x1 - x0) * 1024 / ((y1 - y0) * 1536), 11 / 14, places=2)
        self.assertTrue(r["needs_render"])  # the bands above and below the canvas get filled

    def test_grid_note(self):
        self.assertEqual(canvas.grid_note({"w_in": 11, "h_in": 14}), "Each 10% is 1.1 in across and 1.4 in down.")


class DefaultCanvasTests(unittest.TestCase):
    """#122: every version 2 lesson has a canvas size, so its steps can say where in inches."""

    def test_the_standard_size_closest_to_the_shape(self):
        self.assertEqual(canvas.default_size(1000 / 786), "11x14")  # the fixtures: exactly 14 x 11
        self.assertEqual(canvas.default_size(11 / 14), "11x14")
        self.assertEqual(canvas.default_size(0.8), "11x14")  # 8x10 is the shape, but 11x14 is within 3%: equally good
        self.assertEqual(canvas.default_size(1.0), "11x14")  # square: 8x10 and 11x14 fit as well
        self.assertEqual(canvas.default_size(4 / 3), "12x16")  # 9x12 and 12x16 tie: 12x16 is nearer 11x14 in area
        self.assertEqual(canvas.default_size(1.5), "12x16")
        self.assertEqual(canvas.default_size(1.5, "portrait"), "11x14")  # hung upright: 8x10 is nearest, 11x14 as good
        self.assertIn(canvas.default_size(1.5), canvas.STANDARD)

    def test_a_lesson_with_no_canvas_json_gets_the_default_when_its_finish_has_a_standard_shape(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = Path(d)
            wide(1000, 786).save(lesson / "99_finish.png")
            info = canvas.lesson_canvas(lesson)
            self.assertEqual(info["chosen"], "default")
            self.assertEqual(info["canvas"], {"w_in": 14.0, "h_in": 11.0, "orientation": "landscape"})
            self.assertEqual(info["canvas_box"], [0.0, 0.0, 1.0, 1.0])
            self.assertEqual(json.loads((lesson / "canvas.json").read_text(encoding="utf-8")), info)  # recorded
            self.assertEqual(canvas.lesson_canvas(lesson), info)  # and read back, not picked again

    def test_a_lesson_with_no_canvas_json_and_an_odd_shaped_finish_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = Path(d)
            with self.assertRaisesRegex(canvas.NoCanvas, "canvas.json"):
                canvas.lesson_canvas(lesson)  # no finish at all
            wide(1536, 1024).save(lesson / "99_finish.png")  # 3:2; the nearest standard canvas is 16 x 12
            with self.assertRaisesRegex(canvas.NoCanvas, r"canvas\.json is missing.*fit-canvas"):
                canvas.lesson_canvas(lesson)
            self.assertFalse((lesson / "canvas.json").exists())

    def test_fit_canvas_without_a_size_picks_and_records_the_default(self):
        import tools
        with tempfile.TemporaryDirectory() as d:
            photo, lesson = Path(d) / "photo.png", Path(d) / "lesson"
            wide().save(photo)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = tools.main(["fit-canvas", str(photo), "--lesson", str(lesson), "--why", "a test"])
            self.assertEqual(code, 0, out.getvalue())
            info = json.loads((lesson / "canvas.json").read_text(encoding="utf-8"))
            self.assertEqual(info["chosen"], "default")
            self.assertEqual(info["canvas"], {"w_in": 16.0, "h_in": 12.0, "orientation": "landscape"})
            self.assertEqual(info["mode"], "crop")  # 3:2 to 4:3 is a small, free crop
            with contextlib.redirect_stdout(io.StringIO()):
                tools.main(["fit-canvas", str(photo), "--lesson", str(lesson), "--canvas", "11x14", "--why", "a test"])
            self.assertEqual(json.loads((lesson / "canvas.json").read_text(encoding="utf-8"))["chosen"], "given")


if __name__ == "__main__":
    unittest.main()
