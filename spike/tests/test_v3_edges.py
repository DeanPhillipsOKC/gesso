"""Tests for spike S3 (#168, spike/experiments/v3_edges.py): name prompts, mattes, soft step pictures, the
re-reading jitter, and the grading folders (docs/spikes/v3-edges.md). A made-up scene: no model files, no network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "experiments"))

import numpy as np  # noqa: E402

import build_steps as bs  # noqa: E402
import v3_edges as ve  # noqa: E402

H, W = 120, 160
WALL, RUG, CAT, POST = (150, 180, 220), (230, 170, 30), (90, 90, 95), (200, 60, 50)


def scene() -> dict:
    """A wall, a rug on it, a cat on the rug with soft fur at its edge (a ring half cat, half what's behind), and a
    post the cat's fur ring reaches, listed after the cat."""
    owner = np.zeros((H, W), np.int32)
    owner[60:100, 20:120] = 1
    owner[40:85, 50:90] = 2
    owner[20:110, 92:100] = 3
    fur = np.zeros((H, W), np.float32)
    fur[36:89, 46:94] = 0.5
    fur[40:85, 50:90] = 1.0
    behind = np.zeros((H, W, 3), np.float32)
    behind[:] = WALL
    behind[60:100, 20:120] = RUG
    finish = fur[..., None] * np.array(CAT, np.float32) + (1 - fur[..., None]) * behind
    finish[20:110, 92:100] = POST
    parts = [{"id": "wall", "name": "The wall", "kind": "area", "box": [0, 0, 1, 1]},
             {"id": "rug", "name": "The rug", "kind": "object", "box": [0.12, 0.5, 0.75, 0.83]},
             {"id": "cat", "name": "The sleeping cat", "kind": "object", "box": [0.31, 0.33, 0.56, 0.71]},
             {"id": "post", "name": "The post", "kind": "object", "box": [0.57, 0.16, 0.63, 0.92]}]
    colors = [WALL, RUG, CAT, POST]
    paints = [{"id": f"{p['id']}-1", "name": p["name"], "hex": "#%02x%02x%02x" % c, "parts": [p["id"]]}
              for p, c in zip(parts, colors)]
    stages = [{"id": p["id"], "name": p["name"], "steps": [
        {"id": f"{p['id']}-all", "name": p["name"], "part": p["id"], "show": "full", "paints": [f"{p['id']}-1"]}]}
        for p in parts]
    return {"finish": np.clip(finish + 0.5, 0, 255).astype(np.uint8), "owner": owner,
            "plan": {"plan_version": 2, "parts": parts, "paints": paints, "stages": stages}}


class NamePromptTests(unittest.TestCase):
    def test_the_name_as_a_short_noun_phrase(self):
        self.assertEqual(ve.name_prompt({"id": "cow", "name": "The Highland cow"}), "highland cow")
        self.assertEqual(ve.name_prompt({"id": "leaves", "name": "The four leaves"}), "leaves")
        self.assertEqual(ve.name_prompt({"id": "bird-feet", "name": "Legs and feet"}), "legs and feet")
        self.assertEqual(ve.name_prompt({"id": "far-hills"}), "far hills")

    def test_only_objects_and_thin_parts_are_prompted(self):
        kinds = {k: ve.prompted({"kind": k}) for k in ("area", "marks", "object", "thin")}
        self.assertEqual(kinds, {"area": False, "marks": False, "object": True, "thin": True})


class JitterTests(unittest.TestCase):
    def test_every_position_moves_a_little_and_the_same_seed_gives_the_same_reading(self):
        parts = [{"id": "a", "kind": "object", "box": [0.2, 0.2, 0.6, 0.6], "points_in": [[0.4, 0.4]]},
                 {"id": "b", "kind": "thin", "paths": [[[0.1, 0.1], [0.9, 0.9]]], "width": 0.02},
                 {"id": "c", "kind": "object", "boxes": [[0.0, 0.0, 0.1, 0.1]]}]
        one = ve.jitter(parts, np.random.default_rng(1))
        two = ve.jitter(parts, np.random.default_rng(1))
        self.assertEqual(one, two)
        self.assertNotEqual(one[0]["box"], parts[0]["box"])
        for a, b in zip(one[0]["box"] + one[0]["points_in"][0], parts[0]["box"] + parts[0]["points_in"][0]):
            self.assertLessEqual(abs(a - b), ve.JITTER + 1e-9)
        x0, y0, x1, y1 = one[2]["boxes"][0]
        self.assertTrue(0 <= x0 <= x1 <= 1 and 0 <= y0 <= y1 <= 1)
        self.assertEqual(one[1]["width"], 0.02)
        self.assertEqual(parts[0]["box"], [0.2, 0.2, 0.6, 0.6])  # the plan itself isn't touched


def hand_matte(d: dict) -> dict:
    """The cat's matte as the scene was made: half cat on the fur ring, with the cat's and the true behind colors."""
    alpha = np.zeros((H, W), np.float32)
    alpha[36:89, 46:94] = 0.5
    alpha[40:85, 50:90] = 1.0
    behind = np.zeros((H, W, 3), np.float32)
    behind[:] = WALL
    behind[60:100, 20:120] = RUG
    mine = d["owner"] == 2
    band = (alpha > 0) & (alpha < 1) | (mine & ~np.pad(mine[1:-1, 1:-1] & mine[:-2, 1:-1] & mine[2:, 1:-1]
                                                      & mine[1:-1, :-2] & mine[1:-1, 2:], 1))
    return {2: {"alpha": alpha, "front": np.broadcast_to(np.array(CAT, np.float32), (H, W, 3)).copy(),
                "behind": behind, "band": band}}


class MatteTests(unittest.TestCase):
    def test_the_finish_is_front_over_behind_by_the_matte(self):
        d = scene()
        m = ve.matte(d["finish"], d["owner"] == 2, reach=0.04)
        self.assertTrue(((m["alpha"] >= 0) & (m["alpha"] <= 1)).all())
        a = m["alpha"][..., None]
        rebuilt = a * m["front"] + (1 - a) * m["behind"]
        self.assertLess(float(np.abs(rebuilt - d["finish"]).mean()), 2)  # regularized: close on average, not exact
        self.assertTrue(m["band"][37, 70])  # the fur ring is in the unsure band
        self.assertFalse(m["band"][60, 70])  # deep inside: no blending there

    def test_a_part_thinner_than_the_band_keeps_its_hard_edge(self):
        d = scene()
        thin = np.zeros((H, W), bool)
        thin[50, 10:150] = True
        m = ve.matte(d["finish"], thin, reach=0.04)
        self.assertTrue(np.array_equal(m["alpha"], thin.astype(np.float32)))


class SoftenTests(unittest.TestCase):
    def setUp(self):
        self.d = scene()
        d = self.d
        self.hard, _, self.painted = bs.build(d["finish"], d["plan"], d["owner"])
        self.soft = hand_matte(d)
        self.pictures = ve.soften(d["finish"], d["plan"], d["owner"], self.hard, self.soft)

    def test_the_last_picture_is_the_finish_and_nothing_outside_a_band_changes(self):
        self.assertTrue(np.array_equal(self.pictures[-1], self.d["finish"]))
        bands = np.zeros((H, W), bool)
        for m in self.soft.values():
            bands |= m["band"]
        for hard, soft in zip(self.hard, self.pictures):
            moved = np.abs(hard.astype(int) - soft.astype(int)).max(2) > 0
            self.assertFalse((moved & ~bands).any())

    def test_the_fur_waits_for_the_cat(self):
        """Before the cat's step the rug and wall under its fur show what's behind, not the cat's fur."""
        before = self.pictures[1]  # after the rug, before the cat
        self.assertLess(np.abs(before[37, 70].astype(int) - np.array(WALL)).max(), 30)
        self.assertGreater(np.abs(self.hard[1][37, 70].astype(int) - np.array(WALL)).max(), 30)

    def test_a_fringe_never_covers_a_part_listed_after_it(self):
        """The cat's fur ring reaches the post, which is in front of it: the cat's step leaves the post's pixels."""
        cat_step, post = 2, self.d["owner"] == 3
        self.assertTrue(np.array_equal(self.pictures[cat_step][post], self.hard[cat_step][post]))


class GradeFolderTests(unittest.TestCase):
    def test_refuses_a_folder_inside_the_repository(self):
        with self.assertRaises(SystemExit):
            ve.grade_folders([("chickadee", "soft")], ve.ROOT / "output" / "grades")

    def test_iou(self):
        a = np.zeros((4, 4), bool)
        a[:2] = True
        self.assertEqual(ve.iou(a, a), 1.0)
        self.assertEqual(ve.iou(a, ~a), 0.0)
        self.assertEqual(ve.iou(np.zeros((2, 2), bool), np.zeros((2, 2), bool)), 1.0)


if __name__ == "__main__":
    unittest.main()
