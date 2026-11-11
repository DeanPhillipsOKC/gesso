"""Tests for locking finished areas between step pictures (#30)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lock  # noqa: E402

W, H = 120, 80


def blank(color=(246, 245, 240)):
    return np.full((H, W, 3), color, np.uint8)


class LockTests(unittest.TestCase):
    def test_change_outside_the_region_goes_back(self):
        prev = blank()
        render = prev.copy()
        render[10:30, 10:40] = (30, 90, 200)  # the step's sky, inside its region
        render[60:75, 90:110] = (40, 140, 40)  # grass arriving early, outside it
        region = lock.region_mask((H, W), [[0.0, 0.0, 0.5, 0.5]], margin=0)
        out, share = lock.lock_one(prev, render, render, region)
        self.assertTrue((out[20, 25] == render[20, 25]).all())  # kept
        self.assertTrue(np.abs(out[67, 100].astype(int) - prev[67, 100]).max() < 5)  # put back
        self.assertGreater(share, 0)

    def test_finished_area_stays_put_even_inside_the_region(self):
        finish = blank((30, 90, 200))
        prev = finish.copy()  # the sky is already finished
        render = prev.copy()
        render[20:60, 20:100] = (200, 120, 60)  # the render repaints it orange
        out, _ = lock.lock_one(prev, render, finish, None)
        self.assertTrue(np.abs(out[40, 60].astype(int) - prev[40, 60]).max() < 5)

    def test_bare_canvas_is_never_finished(self):
        prev = blank()
        finish = blank((244, 243, 236))  # a cream vine in the finish, nearly the canvas color
        render = blank((20, 30, 90))  # the night sky goes on
        out, share = lock.lock_one(prev, render, finish, None, blank())
        self.assertTrue((out == render).all())

    def test_inside_its_region_the_step_is_trusted(self):
        finish = blank((240, 160, 60))
        prev = finish.copy()  # the glow is "finished"
        render = prev.copy()
        render[30:50, 50:70] = (255, 240, 200)  # the sun, painted inside the step's region
        region = lock.region_mask((H, W), [[0.3, 0.2, 0.7, 0.8]], margin=0)
        out, _ = lock.lock_one(prev, render, finish, region)
        self.assertTrue((out[40, 60] == render[40, 60]).all())

    def test_protect_keeps_the_steps_paint_and_puts_back_the_rest(self):
        prev = blank((230, 120, 30))  # an orange pumpkin, finished
        render = prev.copy()
        render[10:70, 55:62] = (240, 238, 225)  # a cream vine painted over it: the step's own paint
        render[50:75, 10:40] = (170, 70, 20)  # the pumpkin repainted darker under it: drift
        region = lock.region_mask((H, W), [[0, 0, 1, 1]], margin=0)
        protect = lock.region_mask((H, W), [[0, 0, 1, 1]], margin=0)
        out, _ = lock.lock_one(prev, render, render, region, None, protect, [(240, 238, 225)])
        self.assertTrue(np.abs(out[40, 58].astype(int) - render[40, 58]).max() < 5)  # vine kept
        self.assertTrue(np.abs(out[62, 25].astype(int) - prev[62, 25]).max() < 5)  # repaint put back

    def test_new_paint_toward_the_finish_is_kept(self):
        finish = blank((30, 90, 200))
        prev = blank()  # white canvas, not finished yet
        render = finish.copy()
        out, share = lock.lock_one(prev, render, finish, None)
        self.assertTrue((out == render).all())
        self.assertEqual(share, 0.0)

    def test_lock_keeps_raw_renders_and_can_rerun(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = Path(d)
            Image.fromarray(blank((30, 90, 200))).save(lesson / "99_finish.png")
            step = blank()
            step[0:40] = (30, 90, 200)
            Image.fromarray(step).save(lesson / "01_sky.png")
            lock.lock(lesson, [lesson / "01_sky.png"], lesson / "99_finish.png", None, [[[0, 0, 1, 0.5]]])
            self.assertTrue((lesson / "trials" / "raw" / "01_sky.png").exists())
            first = np.asarray(Image.open(lesson / "01_sky.png"))
            lock.lock(lesson, [lesson / "01_sky.png"], lesson / "99_finish.png", None, [[[0, 0, 1, 0.5]]])
            self.assertTrue((np.asarray(Image.open(lesson / "01_sky.png")) == first).all())  # from raw, same result


if __name__ == "__main__":
    unittest.main()
