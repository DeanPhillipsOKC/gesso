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


class CommandLineTests(unittest.TestCase):
    def test_every_filter_writes_output_and_json(self):
        tmp = Path(tempfile.mkdtemp())
        src = tmp / "scene.png"
        Image.fromarray(scene()).save(src)
        for name in tools.FILTERS:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = tools.main([name, str(src), "--lesson", str(tmp)])
            self.assertEqual(code, 0, name)
            result = json.loads(out.getvalue().strip().splitlines()[-1])
            self.assertEqual(result["cost_usd"], 0.0)
            self.assertTrue(Path(result["out"]).exists(), name)
        self.assertTrue((tmp / "scene_palette.json").exists())

    def test_missing_input_refuses(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = tools.main(["notan", "nope.png"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
