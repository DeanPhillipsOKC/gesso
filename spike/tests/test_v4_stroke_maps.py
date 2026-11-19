"""The stroke maps spike (#256, v4's P1): the grain measure, arrows traced from a change, the writer's inches, and the
map picture. On small made-up canvases. No network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "experiments"))
sys.path.insert(0, str(HERE.parent))

import v4_stroke_maps as sm  # noqa: E402


def canvas(w=480, h=360):
    from PIL import Image
    return Image.new("RGB", (w, h), (246, 246, 246))


def striped(base, box, across: bool, period: int = 6):
    """`base` with a striped patch in `box` (x0, y0, x1, y1): stripes running side to side if `across`, else top to
    bottom, like strokes laid that way."""
    from PIL import Image
    a = np.asarray(base, dtype=np.uint8).copy()
    x0, y0, x1, y1 = box
    yy, xx = np.mgrid[y0:y1, x0:x1]
    band = ((yy if across else xx) // period) % 2 == 0
    a[y0:y1, x0:x1] = np.where(band[..., None], (40, 70, 160), (90, 130, 210))
    return Image.fromarray(a)


class Grain(unittest.TestCase):
    def test_strokes_the_same_way_agree_and_crossways_disagree(self):
        before = canvas()
        after = striped(before, (60, 60, 420, 300), across=True)
        same = striped(before, (60, 60, 420, 300), across=True, period=8)
        cross = striped(before, (60, 60, 420, 300), across=False)
        self.assertGreater(sm.grain(before, after, same)["agree"], 0.8)
        self.assertLess(sm.grain(before, after, cross)["agree"], -0.5)

    def test_a_step_that_changes_nothing_has_no_grain(self):
        before = canvas()
        self.assertIsNone(sm.grain(before, before, before)["agree"])


class ChangeArrows(unittest.TestCase):
    def test_arrows_run_along_the_strokes_inside_the_change(self):
        before = canvas()
        after = striped(before, (60, 120, 420, 240), across=True)
        r = sm.change_arrows(before, after)
        self.assertTrue(1 <= len(r["arrows"]) <= sm.MAX_ARROWS)
        for a in r["arrows"]:
            (x0, y0), (x1, y1) = a[0], a[-1]
            self.assertGreater(abs(x1 - x0), 2 * abs(y1 - y0))  # side to side
            self.assertLess(x0, x1)  # a side-to-side stroke starts at its left end
            for x, y in a:
                self.assertTrue(60 / 480 - 0.03 <= x <= 420 / 480 + 0.03 and 120 / 360 - 0.03 <= y <= 240 / 360 + 0.03)

    def test_a_tall_stroke_starts_at_its_top(self):
        before = canvas()
        after = striped(before, (200, 30, 280, 330), across=False)
        a = sm.change_arrows(before, after)["arrows"][0]
        self.assertLess(a[0][1], a[-1][1])

    def test_no_change_no_arrows(self):
        self.assertEqual(sm.change_arrows(canvas(), canvas())["arrows"], [])


class Inches(unittest.TestCase):
    def test_the_writers_inches_come_back_as_fractions_kept_on_the_canvas(self):
        got = sm.from_inches([{"points": [[0, 0], [8, 6], [20, -1]]}, {"points": [[1, 1]]}], [16, 12])
        self.assertEqual(got, [[[0.0, 0.0], [0.5, 0.5], [1.0, 0.0]]])  # one point isn't an arrow
        self.assertEqual(sm.to_inches([[[0.5, 0.25]]], [16, 12]), [[[8.0, 3.0]]])

    def test_at_most_four_arrows(self):
        got = sm.from_inches([{"points": [[1, 1], [2, 2]]}] * 6, [16, 12])
        self.assertEqual(len(got), sm.MAX_ARROWS)


class Drawing(unittest.TestCase):
    def test_the_map_is_the_before_picture_with_yellow_arrows(self):
        before = canvas(1200, 900)
        m = sm.draw_map(before, [[[0.2, 0.5], [0.5, 0.45], [0.8, 0.5]]])
        self.assertEqual(max(m.size), sm.MAP_SIDE)
        a = np.asarray(m)
        yellow = (a[..., 0] > 230) & (a[..., 1] > 190) & (a[..., 2] < 60)
        self.assertGreater(yellow.sum(), 500)
        self.assertEqual(sm.draw_map(before, []).size, m.size)

    def test_the_writers_grid_is_labelled_in_inches(self):
        g = sm.grid_picture(canvas(1200, 900), [16, 12], side=768)
        self.assertEqual(g.size, (768 + 26, 576 + 26))


if __name__ == "__main__":
    unittest.main()
