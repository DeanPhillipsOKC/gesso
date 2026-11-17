"""Tests for the forward-build spike (#207, spike/experiments/v4_forward.py): the units a painter's plan asks for, the
request for one, the guard that keeps what is already painted, and the paints fitted at the end. Made-up pictures:
no renders, no network, no model files."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "experiments"))

import numpy as np  # noqa: E402

import from_finish as ff  # noqa: E402
import v4_forward as fw  # noqa: E402

H, W = 120, 160


def step(i: str, *things: str, paints: tuple[str, ...] = ("Blue",)) -> dict:
    return {"id": i, "name": i.title(), "lays": [{"thing": t, "what": f"the {t}"} for t in things],
            "paints": list(paints), "after": f"after {i}"}


PAINTER = {
    "subject": "a cow",
    "things": [{"id": t, "name": f"The {t}"} for t in ("sky", "cow", "horns", "grass")],
    "paints": [{"name": "Blue", "looks": "a soft blue"}, {"name": "Rust", "looks": "a red-brown"}],
    "stages": [
        {"id": "back", "steps": [step("a", "sky"), step("b", "grass")]},
        {"id": "shape", "steps": [step("c", "cow", paints=("Rust",)), step("d", "horns"), step("e", "cow", "horns")]},
        {"id": "coat", "steps": [step("f", "cow"), step("g", "cow")]},
        {"id": "front", "steps": [step("h", "grass")]},
    ],
}


class UnitsTests(unittest.TestCase):
    def test_a_unit_is_a_run_in_one_stage_and_a_shared_step_joins_things(self):
        got = fw.units(PAINTER)
        self.assertEqual([u["steps"] for u in got], [[0], [1], [2, 3, 4], [5, 6], [7]])
        self.assertEqual(got[2]["things"], ["cow", "horns"])

    def test_a_thing_painted_again_in_a_later_stage_is_a_new_unit(self):
        got = fw.units(PAINTER)
        self.assertEqual([u["stage"] for u in got if "grass" in u["things"]], ["back", "front"])

    def test_the_request_names_the_steps_the_paints_and_what_waits(self):
        us = fw.units(PAINTER)
        first, later = fw.prompt_for(PAINTER, us, 0), fw.prompt_for(PAINTER, us, 2)
        self.assertIn("bare white canvas", first)
        self.assertNotIn("already painted", first)
        self.assertIn("The cow; The horns", first)
        self.assertIn("Rust (a red-brown)", later)
        self.assertIn("after e", later)
        self.assertIn("already painted keeps its exact place", later)
        self.assertNotIn("Do not paint these yet", later)  # nothing is left that hasn't been started


class GuardTests(unittest.TestCase):
    def test_only_what_changed_by_a_lot_goes_on_the_canvas(self):
        rng = np.random.default_rng(207)
        canvas = np.empty((H, W, 3), np.uint8)
        canvas[:] = ff.CANVAS
        canvas[:50] = (120, 160, 220)
        raw = np.clip(canvas.astype(np.int16) + rng.integers(-4, 5, canvas.shape), 0, 255).astype(np.uint8)
        raw[:50] = (128, 166, 214)  # the sky drawn again, a little off
        raw[60:100, 40:90] = (140, 70, 30)  # the new thing
        out, d = fw.add_one(canvas, raw)
        self.assertTrue(d[70:90, 50:80].all())
        self.assertFalse(d[:45].any())
        self.assertTrue((out[:45] == canvas[:45]).all())
        self.assertLess(np.abs(out[70:90, 50:80].astype(int) - (140, 70, 30)).max(), 30)

    def test_a_render_that_adds_nothing_leaves_the_canvas(self):
        canvas = np.full((H, W, 3), 200, np.uint8)
        out, d = fw.add_one(canvas, canvas.copy())
        self.assertFalse(d.any())
        self.assertTrue((out == canvas).all())


class PaintsTests(unittest.TestCase):
    def test_a_paint_moves_to_the_color_it_has_in_the_picture(self):
        img = np.zeros((H, W, 3), np.uint8)
        img[:, :80] = (150, 60, 30)
        img[:, 80:] = (230, 200, 120)
        got = fw.fit_paints(img, np.ones((H, W), bool), {"Rust": "#8a4a26", "Gold": "#f3dc9c", "Blue": "#3050c0"})
        self.assertEqual(got["Rust"], "#963c1e")
        self.assertEqual(got["Gold"], "#e6c878")
        self.assertEqual(got["Blue"], "#3050c0")  # no pixel is nearest it: it keeps its seed

    def test_a_picture_is_closest_to_itself(self):
        rng = np.random.default_rng(1)
        a = rng.integers(0, 255, (H, W, 3)).astype(np.uint8)
        same = fw.closeness(a, a)
        self.assertEqual(same["color_distance"], 0.0)
        self.assertGreater(same["light_and_dark"], 0.999)
        self.assertGreater(fw.closeness(a, 255 - a)["color_distance"], 10)


if __name__ == "__main__":
    unittest.main()
