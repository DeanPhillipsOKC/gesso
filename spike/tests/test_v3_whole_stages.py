"""Tests for the whole-picture stages spike (#204, spike/experiments/v3_whole_stages.py): the units, the guard that
keeps only what a render changed by a lot, and bare canvas that stays bare. Made-up pictures: no renders, no
network, no model files."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "experiments"))

import numpy as np  # noqa: E402

import from_finish as ff  # noqa: E402
import v3_whole_stages as ws  # noqa: E402

H, W = 120, 160
SKY, ROCK = (120, 160, 220), (90, 90, 95)


def step(i: str, part: str) -> dict:
    return {"id": i, "part": part, "show": "full", "paints": []}


class UnitsTests(unittest.TestCase):
    def test_parts_whose_steps_interleave_are_one_unit(self):
        plan = {"stages": [{"id": "s", "steps": [step("a", "sky"), step("b", "water"), step("c", "trees"), step("d", "peak"),
                                      step("e", "trees"), step("f", "rocks")]}]}
        got = ws.units(plan)
        self.assertEqual([u["parts"] for u in got], [["sky"], ["water"], ["trees", "peak"], ["rocks"]])
        self.assertEqual([u["steps"] for u in got], [[0], [1], [2, 3, 4], [5]])

    def test_a_unit_outside_every_earlier_area_has_only_canvas_behind_it(self):
        plan = {"parts": [{"id": "sky", "kind": "area", "box": [0, 0, 1, 0.5]},
                          {"id": "hill", "kind": "area", "box": [0.2, 0.2, 0.8, 0.5]},
                          {"id": "lake", "kind": "area", "box": [0, 0.5, 1, 1]}]}
        us = [{"parts": [p["id"]], "steps": [i]} for i, p in enumerate(plan["parts"])]
        self.assertFalse(ws.is_bare(plan, us, 1, (H, W)))
        self.assertTrue(ws.is_bare(plan, us, 2, (H, W)))


class GuardTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(204)
        self.before = np.empty((H, W, 3), np.uint8)
        self.before[:] = SKY
        self.before[70:100, 30:70] = ROCK  # the thing
        self.before[20:40, 110:140] = ROCK  # another thing like it, far from the box
        # the render: the first rock gone, the second painted over too, and every pixel a little different
        after = self.before.astype(np.int16)
        after[70:100, 30:70] = SKY
        after[20:40, 110:140] = SKY
        self.after = np.clip(after + rng.integers(-6, 7, after.shape), 0, 255).astype(np.uint8)
        self.box = ws.box_mask([[0.15, 0.5, 0.5, 0.9]], (H, W))

    def test_only_the_change_that_starts_in_the_box_is_kept(self):
        m = ws.diff_mask(self.before, self.after, self.box)
        self.assertGreater(m[72:98, 32:68].mean(), 0.95)
        self.assertFalse(m[20:40, 110:140].any())  # changed as much, but not the thing asked for
        self.assertLess(m.mean(), 0.12)  # the brushwork drawn again isn't a change

    def test_a_change_may_run_past_the_box(self):
        narrow = ws.box_mask([[0.15, 0.5, 0.3, 0.9]], (H, W))
        m = ws.diff_mask(self.before, self.after, narrow)
        self.assertGreater(m[72:98, 52:68].mean(), 0.95)

    def test_nothing_outside_the_change_moves_and_bare_canvas_stays_bare(self):
        frozen = np.zeros((H, W), bool)
        frozen[100:] = True
        out, d = ws.erase_one(self.before, self.after, self.box, False, frozen)
        self.assertTrue((out[~d & ~frozen] == self.before[~d & ~frozen]).all())
        self.assertTrue((out[frozen] == np.array(ff.CANVAS, np.uint8)).all())
        self.assertFalse(d[frozen].any())
        bare, d2 = ws.erase_one(self.before, self.after, self.box, True, np.zeros((H, W), bool))
        self.assertTrue((bare[d2] == np.array(ff.CANVAS, np.uint8)).all())
        self.assertTrue((bare[~d2] == self.before[~d2]).all())


if __name__ == "__main__":
    unittest.main()
