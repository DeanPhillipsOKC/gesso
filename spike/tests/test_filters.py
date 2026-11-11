"""Tests for the filters (#7) and their command line.

    python -m unittest discover spike/tests
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import filters as f  # noqa: E402
import tools  # noqa: E402


def scene() -> np.ndarray:
    """Sky gradient, a dark hill, and a red sun: enough structure for every filter."""
    h, w = 120, 180
    img = np.zeros((h, w, 3), np.uint8)
    img[:, :] = np.linspace([90, 140, 220], [230, 200, 160], h).astype(np.uint8)[:, None, :]
    yy, xx = np.mgrid[:h, :w]
    img[yy > 80 - 20 * np.sin(xx / 30)] = (40, 60, 30)
    img[(yy - 35) ** 2 + (xx - 130) ** 2 < 15 ** 2] = (220, 60, 40)
    return img


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.rgb = scene()

    def test_value_study_has_requested_tones(self):
        for tones in (2, 3, 5):
            out = f.value_study(self.rgb, tones)
            self.assertEqual(out.shape, self.rgb.shape)
            self.assertEqual(len(np.unique(out[:, :, 0])), tones)

    def test_value_study_keeps_dark_darker(self):
        out = f.value_study(self.rgb, 3)
        self.assertLess(out[110, 10, 0], out[5, 10, 0])  # hill darker than sky

    def test_notan_is_two_values(self):
        out, threshold = f.notan(self.rgb)
        self.assertLessEqual(set(np.unique(out).tolist()), {0, 255})
        self.assertTrue(0 < threshold < 255)
        _, forced = f.notan(self.rgb, 100)
        self.assertEqual(forced, 100)

    def test_palette_shares_sum_to_one(self):
        sw = f.palette(self.rgb, 4)
        self.assertEqual(len(sw), 4)
        self.assertAlmostEqual(sum(s["share"] for s in sw), 1.0, delta=0.01)
        self.assertEqual(sw, sorted(sw, key=lambda s: -s["share"]))
        self.assertTrue(all(s["hex"].startswith("#") and len(s["hex"]) == 7 for s in sw))

    def test_posterize_uses_only_palette_colors(self):
        pal = [[255, 0, 0], [0, 0, 255], [20, 20, 20]]
        out = f.posterize(self.rgb, palette_rgb=pal)
        colors = {tuple(c) for c in out.reshape(-1, 3).tolist()}
        self.assertLessEqual(len(colors), 3)

    def test_shape_preserving_filters(self):
        for out in (f.squint(self.rgb), f.simplify(self.rgb), f.simplify(self.rgb, 1, "meanshift"),
                    f.posterize(self.rgb, 4), f.edges(self.rgb), f.grid(self.rgb, 3)):
            self.assertEqual(out.shape, self.rgb.shape)
            self.assertEqual(out.dtype, np.uint8)

    def test_edges_are_dark_lines_on_white(self):
        out = f.edges(self.rgb, "high")
        self.assertGreater((out[:, :, 0] == 255).mean(), 0.8)
        self.assertTrue((out[:, :, 0] < 128).any())


class FindPictureTests(unittest.TestCase):
    def test_finds_a_picture_between_app_bars_and_text(self):
        noise = np.random.default_rng(3).integers(-14, 15, (120, 180, 3))
        pic = np.clip(scene().astype(int) + noise, 0, 255).astype(np.uint8)  # photo-like: many colors a row
        h, w = pic.shape[:2]
        shot = np.full((h * 3, w, 3), 245, np.uint8)  # a flat app page
        shot[: h // 4] = 30                             # a dark top bar
        shot[h // 8: h // 8 + 6, 20: w - 20] = 250      # a line of "text" in it
        shot[h: 2 * h] = pic
        shot[2 * h + 40: 2 * h + 50, 30: 120] = 0       # a caption below
        found = f.find_picture(shot)
        x0, y0, x1, y1 = found["box"]
        self.assertFalse(found["whole_image"])
        self.assertLessEqual(abs(y0 - h), 3)
        self.assertLessEqual(abs(y1 - 2 * h), 3)
        self.assertEqual((x0, x1), (0, w))

    def test_a_plain_photo_needs_no_crop(self):
        noise = np.random.default_rng(4).integers(-14, 15, (120, 180, 3))
        photo = np.clip(scene().astype(int) + noise, 0, 255).astype(np.uint8)
        self.assertTrue(f.find_picture(photo)["whole_image"])


class CommandLineTests(unittest.TestCase):
    def test_every_filter_writes_output_and_json(self):
        tmp = Path(tempfile.mkdtemp())
        src = tmp / "scene.png"
        Image.fromarray(scene()).save(src)
        for name in tools.FILTERS:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = tools.main([name, str(src), "--lesson", str(tmp), "--why", f"see the {name}", "--step", "sky"])
            self.assertEqual(code, 0, name)
            result = json.loads(out.getvalue().strip().splitlines()[-1])
            self.assertEqual(result["cost_usd"], 0.0)
            self.assertTrue(Path(result["out"]).exists(), name)
        self.assertTrue((tmp / "scene_palette.json").exists())
        logged = json.loads((tmp / "ledger.json").read_text(encoding="utf-8"))["calls"]
        self.assertEqual([c["filter"] for c in logged], list(tools.FILTERS))
        self.assertTrue(all(c["tool"] == "filter" and c["why"] and c["step"] == "sky" for c in logged))

    def test_lesson_filter_needs_a_why(self):
        tmp = Path(tempfile.mkdtemp())
        src = tmp / "scene.png"
        Image.fromarray(scene()).save(src)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = tools.main(["notan", str(src), "--lesson", str(tmp)])
        self.assertEqual(code, 2)
        self.assertFalse((tmp / "ledger.json").exists())

    def test_missing_input_refuses(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = tools.main(["notan", "nope.png"])
        self.assertEqual(code, 2)


class PercentGridTests(unittest.TestCase):
    def test_lines_at_every_tenth_of_each_side(self):
        import numpy as np
        import filters as fl
        img = np.full((110, 140, 3), 250, np.uint8)  # a 14x11 canvas shape
        out = fl.grid(img, percent=True)
        self.assertTrue((out[:, 14] < 100).any() and (out[:, 70] < 100).any())  # 10% and 50% across
        self.assertTrue((out[55, :] < 100).any())  # 50% down


if __name__ == "__main__":
    unittest.main()
