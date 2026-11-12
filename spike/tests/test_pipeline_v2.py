"""Tests for pipeline v2: outlines (outline.py), step pictures cut from the finish (build_steps.py), the version 2
plan (plan2.py), and their tools. docs/design/pipeline-v2.md.

The three fixtures are finished paintings from the lessons site with a version 2 plan each and the outlines the
model gave for it (fixtures/owners/), so everything but the model itself is tested without the model files.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import build_steps as bs  # noqa: E402
import outline as ol  # noqa: E402
import paints  # noqa: E402
import plan2  # noqa: E402
import tools  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
NAMES = ["chickadee", "lavender-balloon", "red-sailboat"]


def fixture(name: str):
    finish = np.array(Image.open(FIX / "finishes" / f"{name}.jpg").convert("RGB"))
    plan = json.loads((FIX / "plans" / f"{name}.json").read_text(encoding="utf-8"))
    owner = np.array(Image.open(FIX / "owners" / f"{name}.png")).astype(np.int32)
    return finish, plan, owner


def scene():
    """Blue sky over green ground, orange dabs on the sky, and a red ball in front of both."""
    img = np.zeros((120, 160, 3), np.uint8)
    img[:70] = (110, 150, 220)
    img[70:] = (60, 140, 70)
    for x in (20, 100, 130):
        img[15:27, x:x + 14] = (240, 150, 60)
    yy, xx = np.mgrid[:120, :160]
    ball = ((yy - 68) ** 2 + (xx - 60) ** 2) < 16 ** 2
    img[ball] = (210, 40, 40)
    parts = [
        {"id": "sky", "kind": "area", "box": [0, 0, 1, 1]},
        {"id": "dabs", "kind": "marks", "parent": "sky", "box": [0, 0, 1, 0.5],
         "colors_in": ["#f0963c"], "colors_out": ["#6e96dc"]},
        {"id": "ground", "kind": "area", "box": [0, 0.55, 1, 1]},
        {"id": "ball", "kind": "object", "box": [0.25, 0.4, 0.5, 0.75]},
    ]
    ground = np.zeros((120, 160), bool)
    ground[70:] = True
    return img, parts, {"ground": ground, "ball": ball}


def scene_plan(parts):
    return {"plan_version": 2, "parts": parts,
            "paints": [{"id": "blue", "hex": "#6e96dc"}, {"id": "orange", "hex": "#f0963c"},
                       {"id": "green", "hex": "#3c8c46"}, {"id": "red", "hex": "#d22828"}],
            "stages": [{"id": "back", "steps": [
                {"id": "sky", "part": "sky", "show": "full", "paints": ["blue"]},
                {"id": "dabs", "part": "dabs", "show": "full", "paints": ["orange"]},
                {"id": "ground", "part": "ground", "show": "full", "paints": ["green"]}]},
                {"id": "ball", "steps": [
                    {"id": "ball-flat", "part": "ball", "show": "flat", "paints": ["red"]},
                    {"id": "ball-done", "part": "ball", "show": "pass", "paints": ["red"]}]}]}


class OutlineTests(unittest.TestCase):
    def test_every_pixel_has_one_owner_and_later_parts_win(self):
        img, parts, given = scene()
        masks, owner, stats = ol.outline(img, parts, given=given)
        self.assertEqual(owner.min(), 0)
        self.assertEqual(int(sum(m.sum() for m in masks.values())), owner.size)
        self.assertTrue(masks["ball"][68, 60])  # the ball is in front of sky and ground
        self.assertFalse(masks["ground"][68, 60])
        self.assertEqual(ol.problems(parts, stats), [])

    def test_marks_are_found_by_color_inside_their_box(self):
        img, parts, given = scene()
        masks, _, _ = ol.outline(img, parts, given=given)
        self.assertTrue(masks["dabs"][20, 25] and masks["dabs"][20, 105])
        self.assertFalse(masks["dabs"][5, 5])
        self.assertGreater(masks["dabs"].sum(), 3 * 12 * 14 * 0.7)

    def test_a_part_without_a_model_or_given_outline_is_refused(self):
        img, parts, _ = scene()
        with self.assertRaises(ol.NoModel):
            ol.outline(img, parts)

    def test_gaps_behind_an_object_follow_their_rows(self):
        owner = np.zeros((10, 12), np.int32)
        owner[5:] = 1  # a horizon at row 5
        hole = np.zeros((10, 12), bool)
        hole[2:8, 4:8] = True
        owner[hole] = 9
        out = ol.fill_along_rows(owner, hole)
        self.assertTrue((out[:5] == 0).all() and (out[5:] == 1).all())  # the horizon runs straight on

    def test_a_missing_or_shattered_object_is_reported(self):
        parts = [{"id": "sky", "kind": "area", "box": [0, 0, 1, 1]}, {"id": "bird", "kind": "object", "box": [0.2, 0.2, 0.6, 0.6]}]
        stats = [{"id": "sky", "share": 0.9, "confidence": None, "pieces": 1, "box_fill": 0.9},
                 {"id": "bird", "share": 0.05, "confidence": 0.6, "pieces": 9, "box_fill": 0.1}]
        text = " ".join(ol.problems(parts, stats))
        for word in ("unsure", "fills only", "pieces"):
            self.assertIn(word, text)

    @unittest.skipUnless(all((ol.MODELS / n).exists() for n in ol.FILES), "the outline model files aren't in models/")
    def test_the_model_gives_the_saved_outlines(self):
        sam = ol.Sam()
        for name in NAMES:
            finish, plan, saved = fixture(name)
            sam.emb = None
            _, owner, stats = ol.outline(finish, plan["parts"], sam)
            self.assertGreater((owner == saved).mean(), 0.995, name)
            self.assertEqual(ol.problems(plan["parts"], stats), [], name)


class BuildStepsTests(unittest.TestCase):
    def test_the_fixture_lessons_build_clean(self):
        for name in NAMES:
            finish, plan, owner = fixture(name)
            pictures, rows = bs.build(finish, plan, owner)
            self.assertEqual(len(pictures), len(bs.flat_steps(plan)), name)
            self.assertTrue((pictures[-1] == finish).all(), name)
            self.assertEqual(bs.problems(plan, rows), [], name)
            self.assertLess(rows[-1]["final_gap"], 0.02, name)  # before the last picture was set to the finish
            for r in rows:
                self.assertEqual(r["outside"], 0.0, f"{name} {r['id']} changed something outside its part")

    def test_the_same_inputs_give_the_same_pictures(self):
        finish, plan, owner = fixture("red-sailboat")
        a, _ = bs.build(finish, plan, owner)
        b, _ = bs.build(finish, plan, owner)
        self.assertTrue(all((x == y).all() for x, y in zip(a, b)))

    def test_back_to_front_on_a_small_scene(self):
        img, parts, given = scene()
        _, owner, _ = ol.outline(img, parts, given=given)
        pictures, rows = bs.build(img, scene_plan(parts), owner)
        sky, dabs, ground, ball_flat, done = pictures
        canvas = np.array(bs.ff.CANVAS)
        self.assertTrue(np.abs(sky[100, 20].astype(int) - canvas).max() < 3)  # the ground is still bare canvas
        self.assertGreater(sky[20, 25, 2], sky[20, 25, 0])  # sky runs straight through where a dab will go: still blue
        self.assertGreater(dabs[20, 25, 0], dabs[20, 25, 2])  # then the dab is orange
        self.assertLess(ground[68, 60, 0], 160)  # behind the ball: sky or ground, not the ball's red, until its step
        self.assertGreater(ball_flat[68, 60, 0], 180)
        self.assertTrue((done == img).all())

    def test_a_background_picture_is_used_only_behind_objects(self):
        img, parts, given = scene()
        _, owner, _ = ol.outline(img, parts, given=given)
        plate = np.full_like(img, 255)  # a "render" that got everything wrong
        with_plate, _ = bs.build(img, scene_plan(parts), owner, background=plate)
        without, _ = bs.build(img, scene_plan(parts), owner)
        near_ball = bs.halo(owner == 3)
        self.assertTrue((with_plate[2][~near_ball] == without[2][~near_ball]).all())  # nothing else moved
        self.assertFalse((with_plate[2][near_ball] == without[2][near_ball]).all())

    def test_a_step_that_adds_nothing_is_reported(self):
        rows = [{"id": "x", "painted": 0.1, "changed": 0.001, "outside": 0.0, "final_gap": 0.0}]
        self.assertIn("changes almost nothing", bs.problems({}, rows)[0])

    def test_objects_are_in_front_from_the_first_object_on(self):
        parts = [{"id": "sky", "kind": "area"}, {"id": "cloud", "kind": "marks", "parent": "sky"},
                 {"id": "boat", "kind": "object"}, {"id": "reflection", "kind": "marks"},
                 {"id": "glint", "kind": "marks", "parent": "sky"}]
        self.assertEqual(bs.back_parts(parts).tolist(), [True, True, False, False, True])


class PaintsTests(unittest.TestCase):
    def test_a_parts_colors_come_out_darkest_first_and_the_same_each_time(self):
        img, parts, given = scene()
        mask = np.ones(img.shape[:2], bool)
        a = paints.part_colors(img, mask, 3)
        self.assertEqual(a, paints.part_colors(img, mask, 3))
        self.assertEqual(len(a), 3)
        self.assertAlmostEqual(sum(c["share"] for c in a), 1.0, places=2)
        light = [int(c["hex"][1:3], 16) * 0.3 + int(c["hex"][3:5], 16) * 0.6 + int(c["hex"][5:], 16) * 0.1 for c in a]
        self.assertEqual(light, sorted(light))


class PlanTests(unittest.TestCase):
    def test_the_fixture_plans_are_clean(self):
        for name in NAMES:
            self.assertEqual(plan2.problems(fixture(name)[1]), [], name)

    def breaks(self, change, expect: str):
        plan = copy.deepcopy(fixture("red-sailboat")[1])
        change(plan)
        self.assertIn(expect, " | ".join(plan2.problems(plan)))

    def test_what_a_broken_plan_is_told(self):
        self.breaks(lambda p: p["parts"][1].update(parent="water"), "must be an earlier part")
        self.breaks(lambda p: p["parts"][4].pop("points_in"), "needs points_in or colors_in")
        self.breaks(lambda p: p["stages"][0]["steps"][0].update(part="moon"), "isn't in parts")
        self.breaks(lambda p: p["stages"][2]["steps"].pop(1), "its last step")
        self.breaks(lambda p: p["stages"][2]["steps"].pop(0), "starts with a pass")
        self.breaks(lambda p: p["stages"][1]["steps"].clear(), "no step paints this part")
        self.breaks(lambda p: p["stages"][0]["steps"][0].update(show="full", paints=["sky-1"] * 4), "paints in one step")
        self.breaks(lambda p: p["stages"][0]["steps"][1].update(paints=["mauve"]), "isn't in paints")

    def test_a_version_1_plan_is_not_mistaken_for_version_2(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "plan.json").write_text(json.dumps({"steps": []}), encoding="utf-8")
            self.assertFalse(plan2.is_v2(Path(d)))
            with self.assertRaises(ValueError):
                plan2.load(Path(d))


class ToolTests(unittest.TestCase):
    def lesson(self, d: str, name: str = "red-sailboat") -> Path:
        finish, plan, owner = fixture(name)
        lesson = Path(d)
        (lesson / "parts").mkdir()
        (lesson / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        Image.fromarray(finish).save(lesson / "99_finish.png")
        Image.fromarray(owner.astype(np.uint8)).save(lesson / "parts" / "owner.png")
        return lesson

    def run_tool(self, *argv) -> dict:
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            tools.main(list(argv))
        return json.loads(out.getvalue().strip().splitlines()[-1])

    def test_build_steps_writes_a_picture_per_step_and_a_sheet(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = self.lesson(d)
            r = self.run_tool("build-steps", "--lesson", str(lesson))
            self.assertEqual(r["problems"], [])
            self.assertEqual(len(r["steps"]), 14)
            self.assertTrue(all((lesson / n).exists() for n in r["steps"]))
            self.assertTrue((lesson / "trials" / "steps.jpg").exists())
            self.assertEqual(r["cost_usd"], 0.0)

    def test_build_steps_says_when_a_background_picture_is_wanted(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_tool("build-steps", "--lesson", str(self.lesson(d, "chickadee")))
            self.assertGreater(r["objects_share"], bs.NEEDS_BACKGROUND)
            self.assertIn("background render", r["advice"])

    def test_part_colors_lists_every_part(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_tool("part-colors", "--lesson", str(self.lesson(d)), "--colors", "2")
            self.assertEqual(set(r["colors"]), {p["id"] for p in fixture("red-sailboat")[1]["parts"]})

    def test_a_version_1_lesson_is_refused_with_a_reason(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "plan.json").write_text(json.dumps({"steps": []}), encoding="utf-8")
            self.assertIn("version 2", self.run_tool("build-steps", "--lesson", d)["refused"])

    def test_build_steps_before_outline_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = self.lesson(d)
            (lesson / "parts" / "owner.png").unlink()
            self.assertIn("run outline", self.run_tool("build-steps", "--lesson", str(lesson))["refused"])


if __name__ == "__main__":
    unittest.main()
