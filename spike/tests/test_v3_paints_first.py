"""Tests for spike S6 (#171, spike/experiments/v3_paints_first.py): the off-paint measure, the lock (by part and by
step), the swatch card, and the blind grading folders (docs/spikes/v3-paints-first.md). A made-up scene: no renders,
no network, no model files."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "experiments"))

import numpy as np  # noqa: E402

import build_steps as bs  # noqa: E402
import from_finish as ff  # noqa: E402
import v3_paints_first as pf  # noqa: E402
import v3_part_stages as vs  # noqa: E402

H, W = 120, 160
SKY, RUG, RUG_DARK, CAT, STRIPE, NOSE = ((120, 160, 220), (230, 170, 30), (170, 110, 20), (130, 116, 120),
                                         (70, 62, 66), (230, 120, 150))


def hexed(c) -> str:
    return "#%02x%02x%02x" % c


def scene() -> dict:
    """A sky, a rug with dark bands, and a cat with stripes and a pink nose that no step names."""
    finish = np.zeros((H, W, 3), np.uint8)
    owner = np.zeros((H, W), np.int32)
    finish[:] = SKY
    finish[70:110, 20:140], owner[70:110, 20:140] = RUG, 1
    finish[70:110:8, 20:140] = RUG_DARK
    finish[40:90, 50:110], owner[40:90, 50:110] = CAT, 2
    finish[40:90, 60:100:10] = STRIPE
    finish[55:65, 75:85] = NOSE
    parts = [{"id": "sky", "name": "The sky", "kind": "area", "box": [0, 0, 1, 1]},
             {"id": "rug", "name": "The rug", "kind": "object", "box": [0.12, 0.58, 0.88, 0.92]},
             {"id": "cat", "name": "The cat", "kind": "object", "box": [0.31, 0.33, 0.69, 0.75]}]
    paints = [{"id": i, "name": n, "hex": hexed(c), "parts": [p]} for i, n, c, p in [
        ("sky-1", "Sky blue", SKY, "sky"), ("rug-1", "Mustard", RUG, "rug"), ("rug-2", "Deep gold", RUG_DARK, "rug"),
        ("cat-1", "Cat gray", CAT, "cat"), ("cat-2", "Stripe gray", STRIPE, "cat")]]

    def step(i, part, show, *colors):
        return {"id": i, "name": i, "part": part, "show": show, "paints": list(colors)}

    stages = [{"id": "sky", "name": "Sky", "steps": [step("sky-all", "sky", "blend", "sky-1")]},
              {"id": "rug", "name": "Rug", "steps": [step("rug-block", "rug", "flat", "rug-1"),
                                                     step("rug-bands", "rug", "pass", "rug-2")]},
              {"id": "cat", "name": "Cat", "steps": [step("cat-block", "cat", "flat", "cat-1"),
                                                     step("cat-stripes", "cat", "pass", "cat-2")]}]
    plan = {"version": 2, "parts": parts, "paints": paints, "stages": stages}
    return {"picture": "test", "run": Path("test_run"), "finish": finish, "owner": owner, "plan": plan,
            "background": None}


def lesson_numbers(d: dict, finish: np.ndarray) -> dict:
    pictures, _, painted = bs.build(finish, d["plan"], d["owner"], None)
    rows = pf._mark_last(d["plan"], pf.measure(d["plan"], pictures, painted))
    return {"rows": {r["id"]: r for r in rows}, "summary": pf.summary(rows)}


class MeasureTests(unittest.TestCase):
    def setUp(self):
        bs._built.clear()

    def test_a_color_no_step_names_is_off(self):
        d = scene()
        got = lesson_numbers(d, d["finish"])
        # the cat's last step shows the nose, a pink no cat paint comes near
        self.assertGreater(got["rows"]["cat-stripes"]["off"], 0.0)
        self.assertGreater(got["rows"]["cat-stripes"]["off_part"], 0.0)
        # the rug and the sky show only their own paints (but for a few pixels where the measure's shrink blends edges)
        self.assertLess(got["rows"]["rug-bands"]["off"], 0.05)
        self.assertLess(got["rows"]["sky-all"]["off"], 0.05)
        self.assertGreater(got["summary"]["off"], 0.0)

    def test_summary_weights_by_what_a_step_adds(self):
        rows = [{"id": "a", "off": 1.0, "off_part": 1.0, "off_any": 0.0, "n": 10, "added": 0.1, "last": False},
                {"id": "b", "off": 0.0, "off_part": 0.0, "off_any": 0.0, "n": 30, "added": 0.3, "last": True},
                {"id": "c", "off": None, "off_part": None, "off_any": None, "added": 0.0, "last": False}]
        s = pf.summary(rows)
        self.assertEqual(s["off"], 0.25)
        self.assertEqual(s["off_steps"], 1)
        self.assertEqual(s["off_last"], 0.0)
        self.assertEqual(s["empty"], ["c"])
        self.assertEqual(s["worst"], {"id": "a", "off": 1.0})


class LockTests(unittest.TestCase):
    def setUp(self):
        bs._built.clear()

    def test_lock_pixels_moves_only_what_is_too_far(self):
        img = np.zeros((2, 2, 3), np.uint8)
        img[0, 0] = CAT
        img[0, 1] = (135, 118, 122)  # within a few Delta E of the cat's gray: stays
        img[1, 0] = NOSE  # far: moves to within tol
        img[1, 1] = NOSE
        owner = np.array([[0, 0], [0, 1]])
        targets = {0: [ff.hex_lab(hexed(CAT)).astype(np.float64)], 1: []}  # part 1 names no paint: stays
        out, info = pf.lock_pixels(img, owner, targets, 8.0)
        self.assertTrue((out[0, 0] == img[0, 0]).all() or np.abs(out[0, 0].astype(int) - img[0, 0]).max() <= 1)
        self.assertLessEqual(np.abs(out[0, 1].astype(int) - img[0, 1]).max(), 1)
        d = vs.ciede2000(ff.lab(out[1:, :1]), ff.hex_lab(hexed(CAT)))[0, 0]
        self.assertLessEqual(d, 8.5)
        self.assertGreater(d, 5.0)  # pulled to the line, not onto the paint
        self.assertTrue((out[1, 1] == NOSE).all())
        self.assertGreater(info["moved_mean"], 0)

    def test_tol_zero_snaps_onto_the_paint(self):
        img = np.zeros((1, 2, 3), np.uint8)
        img[0, :] = NOSE
        out, _ = pf.lock_pixels(img, np.zeros((1, 2), int), {0: [ff.hex_lab(hexed(CAT)).astype(np.float64)]}, 0)
        self.assertLessEqual(np.abs(out[0, 0].astype(int) - CAT).max(), 1)

    def test_lock_by_part_takes_the_nose_to_a_cat_paint(self):
        d = scene()
        finish, background, info = pf.lock(d, 8.0)
        self.assertIsNone(background)
        nose = vs.ciede2000(ff.lab(finish[55:65, 75:85]), ff.hex_lab(hexed(CAT))).max()
        self.assertLessEqual(nose, 8.5)
        # what was already a paint doesn't move
        self.assertLessEqual(np.abs(finish[10, 10].astype(int) - SKY).max(), 1)
        self.assertLess(lesson_numbers(d, finish)["summary"]["off"], lesson_numbers(d, d["finish"])["summary"]["off"])

    def test_lock_by_step_leaves_no_step_off(self):
        d = scene()
        finish, _, _ = pf.lock(d, 8.0, by_step=True)
        got = lesson_numbers(d, finish)
        self.assertEqual(got["summary"]["off_steps"], 0)
        self.assertLessEqual(got["summary"]["off"], 0.02)

    def test_shown_by_names_the_last_step_that_moved_a_pixel(self):
        d = scene()
        pictures, _, painted = bs.build(d["finish"], d["plan"], d["owner"], None)
        shown = pf.shown_by(d["plan"], pictures, painted)
        ids = [s["id"] for s in bs.flat_steps(d["plan"])]
        self.assertEqual(ids[shown[10, 10]], "sky-all")
        self.assertEqual(ids[shown[60, 80]], "cat-stripes")  # the nose: the cat's last step
        self.assertIn(ids[shown[45, 70]], ("cat-block", "cat-stripes"))


class SwatchAndGradeTests(unittest.TestCase):
    def test_swatch_card_has_each_used_paint_once(self):
        d = scene()
        card = pf.swatch_card(d["plan"], side=300)
        colors = {tuple(c) for c in card.reshape(-1, 3)}
        for c in (SKY, RUG, RUG_DARK, CAT, STRIPE):
            self.assertIn(c, colors)
        self.assertNotIn(NOSE, colors)

    def test_edges_kept_is_one_for_the_same_picture(self):
        d = scene()
        self.assertEqual(pf.edges_kept(d["finish"], d["finish"]), 1.0)

    def test_off_finish_counts_the_nose(self):
        d = scene()
        self.assertAlmostEqual(pf.off_finish(d, d["finish"]), 100 / (H * W), places=3)

    def test_grade_folders_refuse_the_repository(self):
        with self.assertRaises(SystemExit):
            pf.grade_folders(["chickadee"], "lock-step-8", pf.ROOT / "output" / "grade")

    def test_grade_folders_outside_are_allowed_to_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            # no measured variant for a made-up picture: it fails reading, not on where it writes
            with self.assertRaises(FileNotFoundError):
                pf.grade_folders(["no-such-picture"], "lock-step-8", Path(tmp))


if __name__ == "__main__":
    unittest.main()
