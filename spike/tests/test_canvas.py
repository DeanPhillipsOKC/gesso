"""Tests for fitting a picture to the painter's canvas."""

from __future__ import annotations

import sys
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

    def test_crop_keeps_the_subject_and_centers_the_focus(self):
        r = canvas.fit(wide(), "10x10", focus=(0.8, 0.5), keep=(0.7, 0.3, 0.9, 0.7))
        self.assertEqual(r["mode"], "crop")
        x0, _, x1, _ = r["crop_box"]
        self.assertTrue(x0 <= 0.7 * 1536 and x1 >= 0.9 * 1536)
        self.assertEqual(x1, 1536)  # pushed to the right edge, as near the focus as it can get
        self.assertFalse(r["needs_render"])  # a square canvas fits the square frame

    def test_subject_that_wont_survive_a_crop_is_extended(self):
        r = canvas.fit(wide(), "10x10", focus=(0.5, 0.5), keep=(0.05, 0.2, 0.95, 0.8))
        self.assertEqual(r["mode"], "extend")
        self.assertTrue(r["needs_render"])
        self.assertEqual(r["frame"].getpixel((512, 5)), canvas.PAD)  # gray above the picture, for the model to fill

    def test_11x14_sits_in_a_frame_with_bands(self):
        r = canvas.fit(Image.new("RGB", (1024, 1536)), "11x14", focus=(0.5, 0.5))
        self.assertEqual(r["canvas"]["orientation"], "portrait")
        self.assertEqual(r["frame_size"], [1024, 1536])
        x0, y0, x1, y1 = r["canvas_box"]
        self.assertAlmostEqual((x1 - x0) * 1024 / ((y1 - y0) * 1536), 11 / 14, places=2)
        self.assertTrue(r["needs_render"])  # the bands above and below the canvas get filled

    def test_grid_note(self):
        self.assertEqual(canvas.grid_note({"w_in": 11, "h_in": 14}), "Each 10% is 1.1 in across and 1.4 in down.")


if __name__ == "__main__":
    unittest.main()
