"""Tests for spike S4 (#169, spike/experiments/v3_part_stages.py): the stages the plan describes, their requests,
the guard, step pictures built from stage pictures, and the measures (docs/spikes/v3-part-stages.md). A made-up
scene and a stand-in for the image model: no renders, no network, no model files."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "experiments"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import build_steps as bs  # noqa: E402
import from_finish as ff  # noqa: E402
import mixing  # noqa: E402
import v3_part_stages as st  # noqa: E402

H, W = 120, 160
SKY, RUG, RUG_DARK, CAT, STRIPE, WHITE = ((120, 160, 220), (230, 170, 30), (170, 110, 20), (130, 116, 120),
                                          (70, 62, 66), (228, 214, 210))


def hexed(c) -> str:
    return "#%02x%02x%02x" % c


def scene() -> dict:
    """A sky, a rug with dark bands, and a cat on the rug with dark stripes and a white chest."""
    finish = np.zeros((H, W, 3), np.uint8)
    owner = np.zeros((H, W), np.int32)
    finish[:] = SKY
    finish[70:110, 20:140], owner[70:110, 20:140] = RUG, 1
    finish[70:110:8, 20:140] = RUG_DARK
    finish[40:90, 50:110], owner[40:90, 50:110] = CAT, 2
    finish[40:90, 60:100:10] = STRIPE
    finish[70:90, 50:60] = WHITE
    parts = [{"id": "sky", "name": "The sky", "kind": "area", "box": [0, 0, 1, 1]},
             {"id": "rug", "name": "The rug", "kind": "object", "box": [0.12, 0.58, 0.88, 0.92]},
             {"id": "cat", "name": "The cat", "kind": "object", "box": [0.31, 0.33, 0.69, 0.75]}]
    paints = [{"id": i, "name": n, "hex": hexed(c), "parts": [p]} for i, n, c, p in [
        ("sky-1", "Sky blue", SKY, "sky"), ("rug-1", "Mustard", RUG, "rug"), ("rug-2", "Deep gold", RUG_DARK, "rug"),
        ("cat-1", "Cat gray", CAT, "cat"), ("cat-2", "Stripe gray", STRIPE, "cat"), ("cat-3", "Cat white", WHITE, "cat")]]

    def step(i, name, part, show, *colors):
        return {"id": i, "name": name, "part": part, "show": show, "paints": list(colors)}

    stages = [{"id": "sky", "name": "Sky", "steps": [step("sky-all", "Blend the sky", "sky", "blend", "sky-1")]},
              {"id": "rug", "name": "Rug", "steps": [step("rug-block", "Block in the rug", "rug", "flat", "rug-1"),
                                                     step("rug-bands", "Shade the bands", "rug", "pass", "rug-2")]},
              {"id": "cat", "name": "Cat", "steps": [step("cat-block", "Block in the cat", "cat", "flat", "cat-1"),
                                                     step("cat-white", "Paint the chest", "cat", "pass", "cat-3"),
                                                     step("cat-stripes", "Paint the stripes", "cat", "pass", "cat-2")]}]
    plan = {"plan_version": 2, "parts": parts, "paints": paints, "stages": stages}
    return {"picture": "made-up", "run": Path("made-up_skill_1"), "finish": finish, "plan": plan, "owner": owner,
            "background": None}


def stage_picture(d: dict, step_id: str, everywhere=None) -> np.ndarray:
    """What a good render of a stage would be: the finish with the part as it stands after that step. `everywhere`:
    a color the render also (wrongly) paints over the rest of the picture."""
    out = d["finish"].copy()
    if everywhere is not None:
        out[:] = everywhere
    if step_id == "rug-block":
        out[70:110, 20:140] = RUG
    else:
        out[40:90, 50:110] = CAT
        if step_id == "cat-white":
            out[70:90, 50:60] = WHITE
    return np.where((d["owner"] == (1 if step_id == "rug-block" else 2))[..., None], out,
                    out if everywhere is not None else d["finish"])


class StagesTests(unittest.TestCase):
    def test_a_stage_for_every_step_that_is_not_its_parts_last(self):
        d = scene()
        got = st.stages(d["plan"])
        self.assertEqual([s["id"] for s in got], ["rug-block", "cat-block", "cat-white"])
        white = got[2]
        self.assertEqual((white["k"], white["done"], white["todo"]), (2, [3, 4], [5]))

    def test_the_request_comes_from_the_plan(self):
        d = scene()
        block, white = (st.prompt_for(d["plan"], s) for s in st.stages(d["plan"])[1:])
        self.assertIn("only partly painted: The cat", block)
        self.assertIn("(1) Block in the cat: a flat coat of Cat gray", block)
        self.assertIn("only blocked in", block)
        self.assertIn("(3) Paint the stripes: a pass of Stripe gray", block.split("NOT done yet")[1])
        self.assertIn("(2) Paint the chest: a pass of Cat white", white.split("NOT done yet")[0])
        self.assertNotIn("only blocked in", white)
        self.assertIn("change nothing outside The cat", white)
        undo = st.chained_prompt(d["plan"], st.stages(d["plan"])[2])
        self.assertIn("un-paint the last thing the painter did: Paint the stripes", undo)

    def test_a_part_that_starts_with_a_pass_is_told_to_show_what_is_behind(self):
        d = scene()
        d["plan"]["stages"][1]["steps"][0]["show"] = "pass"
        d["plan"]["parts"][1]["kind"] = "marks"
        self.assertIn("Where it has no paint yet, show what is behind it", st.prompt_for(d["plan"], st.stages(d["plan"])[0]))

    def test_the_guard_keeps_only_the_parts_pixels(self):
        d = scene()
        src, mine = st.source(d, 2)
        got = st.guard(src, stage_picture(d, "cat-block", everywhere=(255, 0, 255)), mine)
        away = ~bs.halo(mine)
        self.assertTrue((got[away] == d["finish"][away]).all())
        self.assertTrue((got[45:85, 55:105] == CAT).all())


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.d = scene()
        self.staged = {}
        for s in st.stages(self.d["plan"]):
            src, mine = st.source(self.d, s["k"])
            self.staged[s["id"]] = st.guard(src, stage_picture(self.d, s["id"]), mine)
        self.ids = [s["id"] for s in bs.flat_steps(self.d["plan"])]

    def test_a_staged_step_shows_its_stage_and_the_last_step_the_finish(self):
        pictures, rows, _, _ = st.build(self.d, self.staged)
        white = pictures[self.ids.index("cat-white")]
        self.assertTrue((np.abs(white[72:88, 52:58].astype(int) - WHITE).max() <= 2))
        # the stripes aren't painted yet, where v2's pass would leave them out too
        self.assertTrue((np.abs(white[45:65, 60].astype(int) - CAT).max() <= 2))
        self.assertTrue((pictures[-1] == self.d["finish"]).all())
        self.assertEqual([r["staged"] for r in rows], [False, True, False, True, True, False])

    def test_no_step_changes_anything_outside_its_part(self):
        pictures, rows, _, areas = st.build(self.d, self.staged)
        self.assertEqual(max(r["outside"] for r in rows), 0.0)
        before = pictures[self.ids.index("rug-bands")]
        after = pictures[self.ids.index("cat-block")]
        grown = bs.halo(areas[self.ids.index("cat-block")])
        self.assertTrue((before[~grown] == after[~grown]).all())

    def test_a_block_in_stage_has_none_of_the_later_paint(self):
        pictures, _, _, _ = st.build(self.d, self.staged)
        block = pictures[self.ids.index("rug-block")]
        # the rug's dark bands come with the next step; and its paint runs a little under the cat's edge, as v2's
        self.assertTrue((np.abs(block[72:108, 22:48].astype(int) - RUG).max() <= 2))
        self.assertTrue((np.abs(block[72:88, 50].astype(int) - RUG).max() <= 8))

    def test_only_passes_keeps_v2s_flat_coat(self):
        pictures, rows, _, _ = st.build(self.d, self.staged, only_passes=True)
        v2, _, _ = bs.build(self.d["finish"], self.d["plan"], self.d["owner"], None)
        i = self.ids.index("cat-block")
        self.assertFalse(rows[i]["staged"])
        self.assertTrue((pictures[i] == v2[i]).all())
        self.assertTrue(rows[self.ids.index("cat-white")]["staged"])

    def test_laying_only_changes_leaves_the_rest_of_the_coat_alone(self):
        pictures, _, _, _ = st.build(self.d, self.staged, lay_all=False)
        block, white = pictures[self.ids.index("cat-block")], pictures[self.ids.index("cat-white")]
        self.assertTrue((block[45:65, 65:105] == white[45:65, 65:105]).all())
        self.assertTrue((np.abs(white[72:88, 52:58].astype(int) - WHITE).max() <= 2))

    def test_with_no_stage_pictures_it_builds_what_v2_builds(self):
        pictures, _, _, _ = st.build(self.d, {})
        v2, _, _ = bs.build(self.d["finish"], self.d["plan"], self.d["owner"], None)
        for a, b in zip(pictures, v2):
            self.assertTrue((a == b).all())


class MeasureTests(unittest.TestCase):
    def test_ciede2000_is_mixings(self):
        for a, b in [("#827478", "#e1d3d0"), ("#f1a012", "#da7f05"), ("#39473b", "#5d6333"), ("#808080", "#808080")]:
            self.assertAlmostEqual(float(st.ciede2000(ff.hex_lab(a), ff.hex_lab(b))), mixing.delta_e(a, b), delta=0.15)

    def test_measures_read_the_paints_from_the_pictures(self):
        d = scene()
        staged = {}
        for s in st.stages(d["plan"]):
            src, mine = st.source(d, s["k"])
            staged[s["id"]] = st.guard(src, stage_picture(d, s["id"]), mine)
        pictures, rows, _, areas = st.build(d, staged)
        marks = st.measure(d, pictures, areas)
        by = {m["id"]: m for m in marks}
        self.assertGreaterEqual(by["cat-block"]["named"], 0.95)
        self.assertGreater(by["cat-block"]["to_finish"], by["cat-white"]["to_finish"])
        self.assertEqual(by["cat-stripes"]["to_finish"], 0.0)
        # a stage in a color no step names is counted
        off = dict(staged)
        off["cat-block"] = np.where((d["owner"] == 2)[..., None], np.uint8((200, 40, 200)), d["finish"]).astype(np.uint8)
        pictures, rows, _, areas = st.build(d, off)
        self.assertLessEqual({m["id"]: m for m in st.measure(d, pictures, areas)}["cat-block"]["named"], 0.05)
        total = st.summary(rows, marks, {"cat-block", "cat-white"})
        self.assertEqual(total["steps"], 2)


class RenderTests(unittest.TestCase):
    def test_render_stages_guards_each_answer_and_keeps_the_numbers(self):
        d = scene()

        def fake(model, picture, prompt, folder, name, quality):
            return stage_picture(d, name, everywhere=(255, 0, 255)), {"seconds": 1.0, "cost_usd": 0.01}

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(st, "OUT", Path(tmp)), \
                mock.patch.object(st, "load", lambda picture, runs=None: d), mock.patch.object(st.vp, "render", fake):
            got = st.render_stages("made-up")
            folder = Path(tmp) / "parallel-low" / "made-up"
            self.assertEqual((got["renders"], got["cost_usd"]), (3, 0.03))
            self.assertEqual(json.loads((folder / "stages.json").read_text())["rows"][0]["id"], "rug-block")
            kept = np.array(Image.open(folder / "cat-block.png").convert("RGB"))
            away = ~bs.halo(d["owner"] == 2)
            self.assertTrue((kept[away] == d["finish"][away]).all())
            self.assertGreater(got["rows"][1]["raw_moved"], 0.9)  # the stand-in repainted everything; the guard dropped it


if __name__ == "__main__":
    unittest.main()
