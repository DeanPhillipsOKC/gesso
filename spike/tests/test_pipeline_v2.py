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
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import build_steps as bs  # noqa: E402
import cards  # noqa: E402
import lessons  # noqa: E402
import mixing  # noqa: E402
import outline as ol  # noqa: E402
import paints  # noqa: E402
import plan2  # noqa: E402
import tools  # noqa: E402
from lessons import NAMES, fixture  # noqa: E402,F401

FIX = Path(__file__).resolve().parent / "fixtures"
CANVAS = {"w_in": 14.0, "h_in": 11.0, "orientation": "landscape"}  # the fixtures (1000 x 786) have the shape of 14 x 11 in


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

    def test_a_thin_part_needs_its_model_or_a_given_outline(self):
        img, parts, given = scene()
        parts.append({"id": "pole", "kind": "thin", "width": 0.04, "paths": [[[0.9, 0.1], [0.9, 0.9]]],
                      "colors_in": ["#000000"], "colors_out": ["#6e96dc"]})
        with self.assertRaises(ol.NoModel):
            ol.outline(img, parts, given=given)
        pole = np.zeros(img.shape[:2], bool)
        pole[:, 120:160] = True  # wider than the band: only the band is kept
        masks, _, stats = ol.outline(img, parts, given={**given, "pole": pole})
        self.assertEqual(stats[-1]["how"], "given")
        self.assertTrue(masks["pole"][60, 144])
        self.assertFalse(masks["pole"][60, 120:130].any())

    def test_a_thin_part_is_asked_for_whole_then_limb_by_limb_for_what_that_missed(self):
        # a trunk (dark) with a twig off to the right; the stand-in model answers the whole part with the trunk only,
        # and a limb's own prompt with the twig plus a patch of sky beside it, which the color rule keeps out
        img = np.full((100, 100, 3), (110, 150, 220), np.uint8)
        img[10:90, 20:26] = (60, 40, 20)
        img[48:52, 26:80] = (60, 40, 20)
        L = ol.lab(img)
        part = {"id": "tree", "kind": "thin", "width": 0.06, "paths": [[[0.23, 0.1], [0.23, 0.9]], [[0.26, 0.5], [0.8, 0.5]]],
                "points_in": [[0.23, 0.3]], "points_out": [[0.6, 0.2]]}
        asked = []

        class Model:
            def mask(self, box, points_in=(), points_out=()):
                asked.append(box)
                m = np.zeros((100, 100), bool)
                if len(asked) == 1:
                    m[10:90, 20:26] = True
                else:
                    m[46:54, 26:80] = True  # the twig, and sky on both sides of it
                return m, 0.9

        inside = ol.band((100, 100), part)
        claim, got = ol.thin(Model(), L, part, inside)
        self.assertEqual(got["limbs"], [1])
        self.assertEqual(len(asked), 2)
        self.assertTrue(claim[50, 60] and claim[50, 22])
        self.assertFalse(claim[46, 60] or claim[53, 60])  # the sky the limb's answer took
        self.assertAlmostEqual(ol.covered(claim, part["paths"][1], 0.06), 1.0)

        class Nothing:
            def mask(self, *a, **k):
                return np.zeros((100, 100), bool), 0.1

        self.assertFalse(ol.thin(Nothing(), L, part, inside)[0].any())

    def test_gaps_behind_an_object_follow_their_rows(self):
        owner = np.zeros((10, 12), np.int32)
        owner[5:] = 1  # a horizon at row 5
        hole = np.zeros((10, 12), bool)
        hole[2:8, 4:8] = True
        owner[hole] = 9
        out = ol.fill_along_rows(owner, hole)
        self.assertTrue((out[:5] == 0).all() and (out[5:] == 1).all())  # the horizon runs straight on

    def test_a_stray_piece_of_an_area_inside_another_part_joins_it(self):
        parts = [{"id": "sky", "kind": "area"}, {"id": "field", "kind": "area"}, {"id": "dots", "kind": "marks"}]
        owner = np.zeros((100, 100), np.int32)
        owner[50:] = 1
        owner[70:75, 20:28] = 0   # a bit of "sky" inside the field: nothing claimed it, so the backdrop got it
        parts.append({"id": "clouds", "kind": "marks", "parent": "sky"})
        owner[60:64, 70:76] = 3   # and a bit of the sky's clouds down there too, taken by color
        owner[20:24, 40:50] = 3   # a real cloud, in the sky
        owner[10:14, 10:14] = 2   # marks stay where they are, however small
        owner[80:84, 60:64] = 2
        out = ol.drop_islands(owner, parts)
        self.assertTrue((out[70:75, 20:28] == 1).all())
        self.assertTrue((out[60:64, 70:76] == 1).all())
        self.assertTrue((out[20:24, 40:50] == 3).all())
        self.assertTrue(np.isin(out[:50], (0, 2, 3)).all())  # the sky's main body is untouched
        parts.append({"id": "branch", "kind": "thin"})
        owner[30:40, 60:80] = 4
        owner[33:36, 65:70] = 0  # a gap of sky inside the branch stays sky
        self.assertTrue((ol.drop_islands(owner, parts)[33:36, 65:70] == 0).all())
        self.assertEqual(int((out == 2).sum()), 32)

    def test_a_missing_or_shattered_object_is_reported(self):
        parts = [{"id": "sky", "kind": "area", "box": [0, 0, 1, 1]}, {"id": "bird", "kind": "object", "box": [0.2, 0.2, 0.6, 0.6]}]
        stats = [{"id": "sky", "share": 0.9, "confidence": None, "pieces": 1, "box_fill": 0.9},
                 {"id": "bird", "share": 0.05, "confidence": 0.6, "pieces": 9, "box_fill": 0.1}]
        text = " ".join(ol.problems(parts, stats))
        for word in ("unsure", "fills only", "pieces"):
            self.assertIn(word, text)

    def test_a_gap_in_an_area_that_fell_to_a_part_behind_it_is_reported(self):
        # a field over the bottom half, with two earth paths running down to the bottom edge that went to the sky
        parts = [{"id": "sky", "kind": "area", "box": [0, 0, 1, 1]}, {"id": "field", "kind": "area", "box": [0, 0.5, 1, 1]},
                 {"id": "rows", "kind": "marks", "parent": "field", "box": [0, 0.5, 1, 1], "colors_in": ["#00ff00"],
                  "colors_out": ["#ff0000"]}]
        owner = np.zeros((100, 200), np.int32)
        owner[50:] = 1
        owner[60:, 40:60] = 2  # rows painted on the field count as the field
        owner[52:, 90:100] = 0
        owner[52:, 140:150] = 0
        stats = [{"confidence": None, **s} for s in ol.owner_stats(parts, owner)]
        text = " | ".join(ol.problems(parts, stats))
        self.assertIn("field: 5% of the picture inside its outline went to sky", text)
        self.assertIn("add points_in there", text)
        self.assertIn("marks part with parent field", text)
        self.assertGreater(stats[1]["hole_at"][1], 0.5)
        owner[52:, 90:100] = owner[52:, 140:150] = 2  # the paths as a marks child of the field: nothing to tell
        self.assertEqual(ol.problems(parts, [{"confidence": None, **s} for s in ol.owner_stats(parts, owner)]), [])
        owner[:, :] = 1
        owner[:50] = 0
        owner[:70, 90:110] = 0  # a notch open at the top, wider than a gap: the field's shape, not a hole
        self.assertLess(ol.owner_stats(parts, owner)[1]["hole"], 0.002)  # only the notch's rounded corners


@lessons.slow
class ModelTests(unittest.TestCase):
    @unittest.skipUnless(all((ol.MODELS / n).exists() for n in ol.FILES), "the outline model files aren't in models/")
    def test_the_model_gives_the_saved_outlines(self):
        sam, hq = ol.Sam(), ol.Sam(ol.HQ_L)
        for name in NAMES:
            finish, plan, saved = fixture(name)
            sam.emb = hq.emb = None
            _, owner, stats = ol.outline(finish, plan["parts"], sam, thin_sam=hq)
            self.assertGreater((owner == saved).mean(), 0.995, name)
            self.assertEqual(ol.problems(plan["parts"], stats), [], name)
            if name == "chickadee":  # the same finish and plan give the same outlines twice (#129)
                sam.emb = hq.emb = None
                self.assertTrue((ol.outline(finish, plan["parts"], sam, thin_sam=hq)[1] == owner).all())
                branch = next(s for s in stats if s["id"] == "branch")
                self.assertTrue(branch["how"].startswith("model"), branch)
                self.assertEqual(branch["pieces"], 1, branch)  # in one piece, twigs included


@lessons.slow
class FixtureBuildTests(unittest.TestCase):
    def test_the_fixture_lessons_build_clean(self):
        for name in NAMES:
            finish = fixture(name)[0]
            plan, pictures, rows, _ = lessons.built(name)  # built once per run and shared (tests/lessons.py)
            self.assertEqual(len(pictures), len(bs.flat_steps(plan)), name)
            self.assertTrue((pictures[-1] == finish).all(), name)
            self.assertEqual(bs.problems(plan, rows), [], name)
            self.assertLess(rows[-1]["final_gap"], 0.02, name)  # before the last picture was set to the finish
            for r in rows:
                self.assertEqual(r["outside"], 0.0, f"{name} {r['id']} changed something outside its part")

    def test_the_same_inputs_give_the_same_pictures(self):
        # the shared build (often made in another worker process) against a fresh one here, past build's memo
        finish, plan, owner = fixture("red-sailboat")
        a = lessons.built("red-sailboat")[1]
        b, _, _ = bs._build(finish, plan, owner)
        self.assertEqual(len(a), len(b))
        self.assertTrue(all((x == y).all() for x, y in zip(a, b)))


class BuildStepsTests(unittest.TestCase):
    def test_the_same_inputs_again_give_a_copy_and_anything_else_builds_anew(self):  # build's memo (#87)
        img, parts, given = scene()
        _, owner, _ = ol.outline(img, parts, given=given)
        plan = scene_plan(parts)
        a, rows, painted = bs.build(img, plan, owner)
        a[0][:] = 0  # a caller changing what it got back
        rows[0]["id"], painted[0][:] = "changed", False
        b, rows, painted = bs.build(img, plan, owner)
        self.assertFalse((b[0] == 0).all())
        self.assertEqual((rows[0]["id"], bool(painted[0].any())), ("sky", True))
        key = bs._key(img, plan, owner, None)
        moved = owner.copy()
        moved[0, 0] = 3
        other = copy.deepcopy(plan)
        other["stages"][0]["steps"][0]["show"] = "flat"
        self.assertEqual(len({key, bs._key(img, other, owner, None), bs._key(img, plan, moved, None),
                              bs._key(img, plan, owner, img)}), 4)
        old, bs.HALO = bs.HALO, bs.HALO * 2  # a tuned number is part of the key too
        try:
            self.assertNotEqual(bs._key(img, plan, owner, None), key)
        finally:
            bs.HALO = old

    def test_back_to_front_on_a_small_scene(self):
        img, parts, given = scene()
        _, owner, _ = ol.outline(img, parts, given=given)
        pictures, rows, _ = bs.build(img, scene_plan(parts), owner)
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
        with_plate, _, _ = bs.build(img, scene_plan(parts), owner, background=plate)
        without, _, _ = bs.build(img, scene_plan(parts), owner)
        near_ball = bs.halo(owner == 3)
        self.assertTrue((with_plate[2][~near_ball] == without[2][~near_ball]).all())  # nothing else moved
        self.assertFalse((with_plate[2][near_ball] == without[2][near_ball]).all())

    def test_a_rim_of_a_later_part_waits_for_that_part(self):
        # an orange cloud whose outline is 2 pixels inside its paint: the ring left over is the sky's by the outline
        img = np.zeros((120, 160, 3), np.uint8)
        img[:] = (110, 150, 220)
        img[30:60, 60:100] = (240, 150, 60)
        cloud = np.zeros((120, 160), bool)
        cloud[32:58, 62:98] = True
        parts = [{"id": "sky", "kind": "area", "box": [0, 0, 1, 1]},
                 {"id": "cloud", "kind": "area", "box": [0.3, 0.2, 0.7, 0.6]}]
        _, owner, _ = ol.outline(img, parts, given={"cloud": cloud})
        plan = {"plan_version": 2, "parts": parts,
                "paints": [{"id": "blue", "hex": "#6e96dc"}, {"id": "orange", "hex": "#f0963c"}],
                "stages": [{"id": "all", "steps": [{"id": "sky", "part": "sky", "show": "full", "paints": ["blue"]},
                                                   {"id": "cloud", "part": "cloud", "show": "full", "paints": ["orange"]}]}]}
        (sky, done), rows, _ = bs.build(img, plan, owner)
        for y, x in ((31, 80), (45, 61), (58, 80)):  # the ring: orange in the finish, the sky's by the outline
            self.assertGreater(int(sky[y, x, 2]), int(sky[y, x, 0]) + 40, f"the sky step shows the cloud at {y},{x}")
        self.assertTrue((done == img).all())
        self.assertEqual(bs.problems(plan, rows), [])
        self.assertEqual(rows[1]["outside"], 0.0)  # the ring coming back with the cloud isn't a change outside it

    def test_a_coat_does_not_stay_where_another_part_will_cross(self):
        # a light bar with a dark peg across it, the bar started as a dark flat coat: by the bar's last step the
        # peg's place is the bar's light paint, not a peg-shaped patch of the coat
        img = np.zeros((120, 160, 3), np.uint8)
        img[:] = (110, 150, 220)
        img[50:70, 10:150] = (230, 190, 150)
        bar = np.zeros((120, 160), bool)
        bar[50:70, 10:150] = True
        peg = np.zeros((120, 160), bool)
        peg[52:68, 77:83] = True
        img[peg] = (40, 40, 60)
        parts = [{"id": "sky", "kind": "area", "box": [0, 0, 1, 1]},
                 {"id": "bar", "kind": "object", "box": [0, 0.4, 1, 0.6]},
                 {"id": "peg", "kind": "object", "box": [0.45, 0.4, 0.55, 0.6]}]
        _, owner, _ = ol.outline(img, parts, given={"bar": bar & ~peg, "peg": peg})
        plan = {"plan_version": 2, "parts": parts,
                "paints": [{"id": "blue", "hex": "#6e96dc"}, {"id": "dark", "hex": "#5a3214"},
                           {"id": "light", "hex": "#e6be96"}, {"id": "peg", "hex": "#28283c"}],
                "stages": [{"id": "all", "steps": [
                    {"id": "sky", "part": "sky", "show": "full", "paints": ["blue"]},
                    {"id": "bar-coat", "part": "bar", "show": "flat", "paints": ["dark"]},
                    {"id": "bar-light", "part": "bar", "show": "pass", "paints": ["light"]},
                    {"id": "peg", "part": "peg", "show": "full", "paints": ["peg"]}]}]}
        pictures, rows, _ = bs.build(img, plan, owner)
        self.assertLess(int(pictures[1][60, 80, 0]), 120)  # the coat
        self.assertGreater(int(pictures[2][60, 80, 0]), 180)  # then the bar's own light, straight through
        self.assertTrue((pictures[3] == img).all())

    def test_a_part_that_shows_before_its_step_is_reported(self):
        img, parts, given = scene()
        _, owner, _ = ol.outline(img, parts, given=given)
        plan = scene_plan(parts)
        pictures, rows, painted = bs.build(img, plan, owner)
        self.assertEqual([r["ghosts"] for r in rows], [[], [], [], [], []])
        ghost = [p.copy() for p in pictures]
        ghost[2][given["ball"]] = (120, 40, 40)  # a dull ball in the picture before the ball's steps
        found = bs.ghosts(img, parts, owner, bs.flat_steps(plan), ghost, painted)
        self.assertEqual([g["part"] for g in found[2]], ["ball"])
        self.assertGreater(found[2][0]["edge"], 0.5)
        rows[2]["ghosts"] = found[2]
        said = bs.problems(plan, rows)
        self.assertEqual(len(said), 1)
        self.assertIn("ball", said[0])
        self.assertIn("before it's painted", said[0])
        self.assertEqual(bs.faint_ghosts(plan, rows), [])  # not said twice

    def test_a_part_painted_on_another_that_shows_early_is_a_note_not_a_failure(self):
        plan = {"parts": [{"id": "tree", "kind": "object"}, {"id": "trunk", "kind": "marks", "parent": "tree"}]}
        rows = [{"id": "tree-coat", "painted": 0.1, "changed": 0.1, "outside": 0.0, "final_gap": 0.0,
                 "ghosts": [{"part": "trunk", "edge": 0.48, "faint": 0.51}]}]
        self.assertEqual(bs.problems(plan, rows), [])
        self.assertIn("trunk", bs.faint_ghosts(plan, rows)[0])

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

    def test_one_paint_for_a_part_is_a_color_it_has_not_an_average(self):
        img = np.zeros((60, 60, 3), np.uint8)
        img[:, :34] = (240, 230, 220)  # mostly white, with some black its outline caught
        img[:, 34:] = (30, 28, 30)
        (c,) = paints.part_paints(img, np.ones((60, 60), bool), 1)
        self.assertLess(mixing.delta_e(c["hex"], "#f0e6dc"), 3)  # the white, not a gray between the two

    def test_with_no_steps_a_part_gets_the_fewest_colors_that_fit(self):
        img = np.zeros((40, 40, 3), np.uint8)
        img[:20] = (200, 60, 40)
        img[20:] = (40, 90, 200)
        self.assertEqual(len(paints.part_paints(img, np.ones((40, 40), bool))), 2)
        self.assertEqual(len(paints.part_paints(np.full((40, 40, 3), 90, np.uint8), np.ones((40, 40), bool))), 1)


def paint(pid: str, hex_: str, **shares) -> dict:
    return {"id": pid, "hex": hex_, "sample_x": 0.5, "sample_y": 0.5, "origins": [],
            "shares": {k.replace("_", "-"): v for k, v in shares.items()}}


def tint_of(main: str, tube, share: float) -> str:
    return mixing.rgb_hex(mixing._mix_rgb([(mixing.hex_rgb(main), 1 - share), (tube, share)]))


class LimitTests(unittest.TestCase):
    """The rules of design section 9, each on a few made-up paints."""
    WHITE, DARK = (255, 255, 255), mixing.tube_rgb("Ultramarine blue")

    def limit(self, ps, n, order, fixed=frozenset(), held=frozenset()):
        return paints.limit(ps, n, order, self.WHITE, self.DARK, "Ultramarine blue", fixed, held)

    def test_a_lighter_or_darker_version_of_the_main_paint_is_a_tint_or_shade(self):
        main = "#1d677a"
        ps = [paint("water-1", main, water=0.5), paint("water-2", tint_of(main, self.WHITE, 0.4), water=0.2),
              paint("water-3", tint_of(main, self.DARK, 0.3), water=0.1), paint("water-4", "#e2a259", water=0.1)]
        paints.mark_tints(ps, ["water"], self.WHITE, self.DARK, "Ultramarine blue")
        got = {p["id"]: (p.get("of"), p.get("plus")) for p in ps}
        self.assertEqual(got, {"water-1": (None, None), "water-2": ("water-1", "white"),
                               "water-3": ("water-1", "Ultramarine blue"), "water-4": (None, None)})
        self.assertEqual(paints.base_mixes(ps), ["water-1", "water-4"])  # tints and shades aren't mixes

    def test_paints_in_different_parts_merge_first_into_one_shared_paint(self):
        ps = [paint("sky-1", "#4a6fb0", sky=0.5), paint("sky-2", "#e08a40", sky=0.2),
              paint("sky-3", "#2a7a3a", sky=0.1), paint("sky-4", "#2c7244", sky=0.1),  # the closest pair: one part
              paint("hill-1", "#d88a48", hill=0.1), paint("sun-1", "#fbe9b0", sun=0.01)]
        merges = self.limit(ps, 5, ["sky", "hill", "sun"])
        self.assertEqual(len(merges), 1)
        self.assertFalse(merges[0]["same_part"])
        shared = next(p for p in ps if "hill" in p["shares"])
        self.assertEqual(shared["id"], "sky-2")  # the paint covering more keeps its id
        self.assertEqual(set(shared["shares"]), {"sky", "hill"})  # one paint for both parts
        self.assertEqual((merges[0]["id"], merges[0]["into"]), ("hill-1", "sky-2"))

    def test_a_paint_a_step_uses_is_never_merged_away_but_can_take_one_in(self):
        ps = [paint("bark-1", "#5e3928", bark=0.5), paint("bark-2", "#2a7a3a", bark=0.2),
              paint("bark-3", "#2c7244", bark=0.1), paint("sun-1", "#fbe9b0", sun=0.01)]
        self.assertEqual(self.limit(copy.deepcopy(ps), 3, ["bark", "sun"], fixed={"bark-2", "bark-3"}), [])  # both used
        merges = self.limit(ps, 3, ["bark", "sun"], fixed={"bark-3"})  # bark-2 covers more, but a step uses bark-3
        self.assertEqual((merges[0]["id"], merges[0]["into"]), ("bark-2", "bark-3"))
        self.assertTrue(merges[0]["same_part"])

    def test_a_paint_paints_add_made_never_merges(self):
        ps = [paint("leaf-1", "#2a7a3a", leaf=0.2), paint("leaf-2", "#4a6a18", leaf=0.2),  # 10 apart, not a shade
              paint("sky-1", "#4a6fb0", sky=0.5), paint("sun-1", "#fbe9b0", sun=0.01)]
        self.assertEqual(self.limit(copy.deepcopy(ps), 3, ["sky", "sun", "leaf"], held={"leaf-2"}), [])
        self.assertEqual(len(self.limit(ps, 3, ["sky", "sun", "leaf"])), 1)
        self.assertEqual(paints.mergeable([p for p in ps if p["id"] != "sun-1"], set(), held={"leaf-1"}), [])

    def test_an_accent_is_never_merged_away(self):
        ps = [paint("sky-1", "#f08a50", sky=0.4), paint("sky-2", "#e07c86", sky=0.3),
              paint("sun-1", "#fbe9b0", sun=0.003),  # the lightest paint
              paint("hull-1", "#2c7f3a", hull=0.003),  # the only green
              paint("sea-1", "#1d4f8a", sea=0.3), paint("sea-2", "#28609a", sea=0.1)]
        self.assertEqual(paints.accents(ps) & {"sun-1", "hull-1"}, {"sun-1", "hull-1"})
        self.limit(ps, 3, ["sky", "sun", "hull", "sea"])
        self.assertEqual({p["id"] for p in ps} & {"sun-1", "hull-1"}, {"sun-1", "hull-1"})
        self.assertEqual(next(p for p in ps if p["id"] == "sun-1")["hex"], "#fbe9b0")  # and its color didn't move

    def test_paints_further_apart_than_the_ceiling_are_never_merged(self):
        ps = [paint("hull-1", "#952821", hull=0.01), paint("refl-1", "#765353", refl=0.01),  # 16 apart
              paint("sea-1", "#1d677a", sea=0.3), paint("sea-2", "#2a7088", sea=0.1),
              paint("sun-1", "#fbe9b0", sun=0.003)]
        self.assertGreater(mixing.delta_e("#952821", "#765353"), paints.MAX_MERGE)
        merges = self.limit(ps, 2, ["hull", "refl", "sea", "sun"])
        self.assertEqual({p["id"] for p in ps} & {"hull-1", "refl-1"}, {"hull-1", "refl-1"})  # the red stays
        self.assertTrue(all(m["delta_e"] <= paints.MAX_MERGE for m in merges))
        self.assertEqual(paints.mergeable([p for p in ps if not p.get("of")], paints.accents(ps)), [])
        why = {o["id"]: o for o in paints.over_target(ps)}  # what kept it over the target, for the tool to say
        self.assertEqual((why["hull-1"]["nearest"], why["hull-1"]["delta_e"]),
                         ("refl-1", round(mixing.delta_e("#952821", "#765353"), 1)))

    def test_merging_stops_when_only_accents_are_left(self):
        ps = [paint("a-1", "#fbe9b0", a=0.1), paint("b-1", "#2c7f3a", b=0.1), paint("c-1", "#c03030", c=0.1)]
        merges = self.limit(ps, 1, ["a", "b", "c"])
        self.assertEqual(merges, [])
        self.assertEqual(len(ps), 3)


class MeasureTests(unittest.TestCase):
    def scene_lesson(self):
        img, parts, given = scene()
        _, owner, _ = ol.outline(img, parts, given=given)
        plan = scene_plan(parts)
        for c, name in zip(plan["paints"], ("Sky blue", "Dab orange", "Grass green", "Ball red")):
            c["name"], c["used_for"] = name, name.lower()
        plan["paints"][2]["hex"] = "#2a6a8a"  # the grass paint was given a color far from the grass
        return img, plan, owner

    def test_names_are_kept_only_where_the_color_barely_moved(self):
        img, plan, owner = self.scene_lesson()
        before = copy.deepcopy(plan)
        r = paints.measure(img, plan, owner, None)
        self.assertFalse(r["first"])
        names = {p["id"]: p.get("name") for p in r["paints"]}
        # the grass moved a long way and the dabs (small, with soft edges) 3.1: Claude names them again
        self.assertEqual(names, {"blue": "Sky blue", "orange": None, "green": None, "red": "Ball red"})
        self.assertEqual({(c["id"], c["name_kept"]) for c in r["changed"]},
                         {("orange", False), ("green", False), ("red", True)})
        self.assertEqual(r["kept"], ["blue"])
        self.assertEqual(plan, before)  # the plan, and its steps, aren't changed
        for p in r["paints"]:
            self.assertTrue({"sample_x", "sample_y", "parts", "hex"} <= set(p))
        self.assertEqual(next(p for p in r["paints"] if p["id"] == "green")["parts"], ["ground"])  # from its step

    def test_a_first_measurement_needs_no_steps_and_running_again_changes_nothing(self):
        img, parts, given = scene()
        _, owner, _ = ol.outline(img, parts, given=given)
        plan = {"plan_version": 2, "parts": parts}
        r = paints.measure(img, plan, owner, 10)
        self.assertTrue(r["first"])
        self.assertEqual([(p["id"], p["parts"]) for p in r["paints"]],
                         [("sky-1", ["sky"]), ("dabs-1", ["dabs"]), ("ground-1", ["ground"]), ("ball-1", ["ball"])])
        plan["paints"] = r["paints"]
        self.assertEqual(plan2.problems(plan, {"max_mixes": 10}), [plan2.NO_STAGES])  # the only thing left: stages
        for p in plan["paints"]:
            p["name"], p["used_for"] = p["id"].title(), "x"
        again = paints.measure(img, plan, owner, 10)
        self.assertEqual((again["first"], again["paints"], again["changed"], again["merges"]),
                         (False, plan["paints"], [], []))

    def test_running_again_keeps_every_id_and_drops_a_paint_whose_part_is_gone(self):
        img, parts, given = scene()
        _, owner, _ = ol.outline(img, parts, given=given)
        plan = scene_plan(parts)
        plan["paints"] = paints.measure(img, {"plan_version": 2, "parts": parts}, owner, 10)["paints"]
        for st in plan["stages"]:
            for s in st["steps"]:
                s["paints"] = [f"{s['part']}-1"]
        # the dabs are dropped (their pixels go back to the sky) and a hill is added in front of the ground
        parts2 = [p for p in parts if p["id"] != "dabs"] + [{"id": "hill", "kind": "area", "box": [0, 0.6, 0.3, 1]}]
        owner2 = np.where(owner == 1, 0, np.where(owner > 1, owner - 1, owner))
        owner2[90:, :40] = 3
        img2 = img.copy()
        img2[90:, :40] = (150, 120, 60)
        plan2_ = dict(plan, parts=parts2)
        r = paints.measure(img2, plan2_, owner2, 10)
        self.assertEqual([x["id"] for x in r["removed"]], ["dabs-1"])
        self.assertEqual(r["removed"][0]["steps"], ["dabs"])  # the step that still names it is listed
        self.assertEqual(r["new"], ["hill-1"])
        self.assertEqual([p["id"] for p in r["paints"]], ["sky-1", "ground-1", "ball-1", "hill-1"])
        self.assertEqual(r["kept"], ["ground-1", "ball-1"])  # the sky, with the dabs' pixels, moved a little
        self.assertEqual([c["id"] for c in r["changed"]], ["sky-1"])

    def test_the_fixtures_are_the_tools_own_result_and_nothing_a_step_uses_is_merged(self):
        dark = mixing.tube_rgb("Ultramarine blue")
        for name in NAMES:
            finish, plan, owner = fixture(name)
            a = paints.measure(finish, plan, owner, 10, dark=dark, dark_name="Ultramarine blue")
            bases = [p for p in a["paints"] if not p.get("of")]
            if len(bases) > 10:
                self.assertEqual(paints.mergeable(bases, set(a["accents"])), [], name)
                self.assertEqual(len(a["over_target"]), len(bases), name)
            self.assertEqual(a, paints.measure(finish, plan, owner, 10, dark=dark, dark_name="Ultramarine blue"), name)
            # running paints on the fixture plans (its own result) changes no paint, not even a spot
            self.assertEqual((a["paints"], a["changed"], a["merges"]), (plan["paints"], [], []), name)
            self.assertIn("sun-1", a["accents"], name)  # the sun is never merged away
            # far over the target, still nothing a step uses is merged away or moved to another step
            b = paints.measure(finish, plan, owner, 3, dark=dark, dark_name="Ultramarine blue")
            self.assertEqual((b["paints"], b["merges"]), (plan["paints"], []), name)
            self.assertTrue(all(o["used"] for o in b["over_target"]), name)

    def test_a_first_measurement_of_the_fixtures_reaches_the_target_or_stops_at_the_ceiling(self):
        dark = mixing.tube_rgb("Ultramarine blue")
        for name in NAMES:
            finish, plan, owner = fixture(name)
            fresh = {k: v for k, v in plan.items() if k not in ("paints", "stages")}
            a = paints.measure(finish, fresh, owner, 10, dark=dark, dark_name="Ultramarine blue")
            self.assertTrue(a["first"], name)
            bases = paints.base_mixes(a["paints"])
            if len(bases) > 10:
                self.assertEqual(paints.mergeable([p for p in a["paints"] if not p.get("of")], set(a["accents"])), [])
            self.assertEqual(plan2.problems(dict(fresh, paints=a["paints"]), {"max_mixes": 10}), [plan2.NO_STAGES])
            again = paints.measure(finish, dict(fresh, paints=a["paints"]), owner, 10, dark=dark,
                                   dark_name="Ultramarine blue")
            self.assertEqual((again["paints"], again["merges"]), (a["paints"], []), name)


class AddTests(unittest.TestCase):
    def test_add_gives_one_part_one_more_color_and_touches_nothing_else(self):
        finish, plan, owner = fixture("red-sailboat")
        r = paints.add(finish, plan, owner, "hill", 10, dark=mixing.tube_rgb("Ultramarine blue"),
                       dark_name="Ultramarine blue")  # the fixture's darkest tube, which its shades are marked with
        self.assertEqual(r["problems"], [])
        new = next(p for p in r["paints"] if p["id"] == r["added"])
        self.assertEqual((r["added"], new["parts"], new["added"]), ("hill-2", ["hill"], True))  # the next free id
        others = {c["id"]: c for c in plan["paints"] if "hill" not in c["parts"]}
        self.assertEqual([p for p in r["paints"] if p["id"] in others], list(others.values()))  # nothing else moved
        self.assertEqual(r["merges"], [])
        self.assertEqual(len(r["paints"]), len(plan["paints"]) + 1)
        self.assertEqual([(c["id"], c["name_kept"]) for c in r["changed"]], [("hill-1", True)])  # its nearest color
        added = dict(plan, paints=r["paints"])
        self.assertEqual(plan2.problems(added, {"max_mixes": 10}), [])  # over the target through --add is allowed
        again = paints.measure(finish, added, owner, 10)  # and a later run keeps it
        self.assertEqual((again["merges"], [p["id"] for p in again["paints"]]), ([], [p["id"] for p in r["paints"]]))

    def test_add_says_so_when_a_part_has_no_other_distinct_color(self):
        rng = np.random.default_rng(3)
        img = np.clip(np.array([40, 90, 200]) + rng.normal(0, 6, (60, 80, 3)), 0, 255).astype(np.uint8)  # one blue
        owner = np.zeros((60, 80), np.int32)
        plan = {"plan_version": 2, "parts": [{"id": "sky", "kind": "area", "box": [0, 0, 1, 1]}]}
        plan["paints"] = paints.measure(img, plan, owner, 10)["paints"]
        r = paints.add(img, plan, owner, "sky", 10)
        self.assertIsNone(r["added"])
        self.assertIn("sky: its pixels don't hold another distinct color: the next one measured", r["problems"][0])
        self.assertIn("from sky-1", r["problems"][0])
        self.assertEqual(r["paints"], plan["paints"])
        with self.assertRaises(ValueError):
            paints.add(img, plan, owner, "moon", 10)


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
        self.breaks(lambda p: p["stages"][0]["steps"][1].update(paints=["sky-1"]), "sky-1's parts don't list sun")
        self.breaks(lambda p: p["paints"][0].pop("sample_x"), "no sample_x/sample_y")
        self.breaks(lambda p: p["paints"][1].update(of="sky-9", plus="white"), "which isn't in paints")

    def test_the_parts_are_checked_alone_before_there_are_paints_or_stages(self):
        plan = {k: v for k, v in fixture("red-sailboat")[1].items() if k not in ("paints", "stages")}
        self.assertEqual(plan2.parts_problems(plan), [])
        self.assertIn("no stages with steps", " | ".join(plan2.problems(plan)))
        broken = copy.deepcopy(plan)
        broken["parts"][4].pop("points_in")
        self.assertIn("needs points_in", " | ".join(plan2.parts_problems(broken)))

    def test_a_marks_or_thin_part_on_a_marks_part_is_refused_with_what_to_do(self):
        plan = copy.deepcopy(fixture("red-sailboat")[1])
        self.assertEqual(plan["parts"][4]["parent"], "water")
        plan["parts"].append({"id": "glints", "kind": "marks", "parent": "sun-path", "box": [0.2, 0.6, 0.5, 0.9],
                              "points_in": [[0.4, 0.7]], "points_out": [[0.3, 0.8]]})
        text = " | ".join(plan2.parts_problems(plan))
        self.assertIn("glints: a marks part can't have the marks part sun-path as its parent: it would outline nothing. "
                      "List it after sun-path and give it 'water' as its parent", text)
        plan["parts"][-1]["parent"] = "water"
        self.assertEqual(plan2.parts_problems(plan), [])
        self.assertIsNone(plan["parts"][8].get("parent"))  # the reflection has none: its child is told to have none
        plan["parts"].append({"id": "mast-reflection", "kind": "thin", "parent": "reflection", "width": 0.01,
                              "paths": [[[0.8, 0.65], [0.8, 0.9]]], "points_in": [[0.8, 0.7]], "points_out": [[0.7, 0.8]]})
        self.assertIn("mast-reflection: a thin part can't have the marks part reflection as its parent: it would outline "
                      "nothing. List it after reflection and give it no parent.", " | ".join(plan2.parts_problems(plan)))

    def test_over_the_target_is_told_only_when_paints_could_still_merge(self):
        plan = copy.deepcopy(fixture("red-sailboat")[1])
        bases = [c for c in plan["paints"] if not c.get("of")]
        self.assertGreater(len(bases), 10)
        self.assertEqual(plan2.problems(plan, {"max_mixes": 10}), [])  # over, but nothing close enough is left
        a, b = bases[1], bases[2]
        a["hex"] = mixing.rgb_hex(np.clip(np.array(mixing.hex_rgb(b["hex"])) + 4, 0, 255))
        self.assertEqual(plan2.problems(plan, {"max_mixes": 10}), [])  # both used by steps: paints won't merge them
        spare = dict(a, id="spare")  # the same color, but no step uses it: paints would merge it away
        plan["paints"].append(spare)
        text = " | ".join(plan2.problems(plan, {"max_mixes": 10}))
        self.assertIn("spare", text)
        self.assertIn("Run paints again", text)
        spare["added"] = True  # one paints --add made (a pass split in two) never merges
        self.assertEqual(plan2.problems(plan, {"max_mixes": 10}), [])
        spare.pop("added")
        self.assertEqual(plan2.problems(plan, {"max_mixes": 20}), [])  # under the target: fine either way

    def test_a_version_1_plan_is_not_mistaken_for_version_2(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "plan.json").write_text(json.dumps({"steps": []}), encoding="utf-8")
            self.assertFalse(plan2.is_v2(Path(d)))
            with self.assertRaises(ValueError):
                plan2.load(Path(d))


@lessons.slow
class ToolTests(unittest.TestCase):
    def lesson(self, d: str, name: str = "red-sailboat") -> Path:
        """A fixture lesson as outline leaves it (tests/lessons.py; its build is already in build_steps' memo)."""
        return lessons.lesson(name, "outlined", Path(d))

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
        r = lessons.results("chickadee", "aided")["build-steps"]  # what build-steps printed on the shared build
        self.assertGreater(r["objects_share"], bs.NEEDS_BACKGROUND)
        self.assertTrue(r["needs_background"])
        self.assertIn("Run background (one render", r["advice"])
        r = lessons.results("red-sailboat", "aided")["build-steps"]  # objects at about 8% show a ghost too (three real runs, 2026-11-13)
        self.assertLess(r["objects_share"], 0.15)
        self.assertTrue(r["needs_background"])
        self.assertEqual(bs.NEEDS_BACKGROUND, 0.02)

    def test_outline_and_part_colors_run_on_a_plan_with_parts_only(self):
        from unittest import mock

        img, parts, _ = scene()
        with tempfile.TemporaryDirectory() as d:
            lesson = Path(d)
            plan = {"plan_version": 2, "parts": parts[:2]}  # the backdrop and marks on it: no model needed
            (lesson / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
            Image.fromarray(img).save(lesson / "99_finish.png")
            with mock.patch.object(ol, "Sam", lambda *a: None):
                r = self.run_tool("outline", "--lesson", str(lesson))
            self.assertEqual(r["problems"], [])
            self.assertTrue((lesson / "parts" / "owner.png").exists())
            self.assertEqual(set(self.run_tool("part-colors", "--lesson", str(lesson))["colors"]), {"sky", "dabs"})
            plan["parts"][1].pop("colors_in")
            (lesson / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
            self.assertIn("needs points_in or colors_in", self.run_tool("outline", "--lesson", str(lesson))["refused"])

    def test_part_colors_lists_every_part(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_tool("part-colors", "--lesson", str(self.lesson(d)), "--colors", "2")
            self.assertEqual(set(r["colors"]), {p["id"] for p in fixture("red-sailboat")[1]["parts"]})

    def test_paints_writes_the_measured_paints_and_a_swatch_sheet(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = self.lesson(d, "lavender-balloon")
            plan = json.loads((lesson / "plan.json").read_text(encoding="utf-8"))
            plan["paints"] = [{k: v for k, v in c.items() if k not in ("name", "used_for")} for c in plan["paints"]]
            (lesson / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
            r = self.run_tool("paints", "--lesson", str(lesson))
            self.assertEqual(r["problems"], [])
            self.assertEqual(r["max_mixes"], 10)
            self.assertGreater(r["base_mixes"], 10)  # the lavender stops above the target rather than lose a color
            self.assertIn("above the target of 10", r["over_target"][0])
            self.assertTrue(all(" stays" in line and "away" in line for line in r["over_target"][1:]))
            self.assertTrue((lesson / "trials" / "paints.jpg").exists())
            written = plan2.load(lesson)
            self.assertEqual(written["paints"], plan["paints"])  # the same paints the fixture holds, still unnamed
            self.assertEqual(written["stages"], plan["stages"])
            self.assertEqual(plan2.problems(written), [])
            self.assertFalse(r["first"])
            self.assertEqual((r["merged"], r["changed"], r["removed"]), ([], [], []))

    def test_paints_first_needs_no_stages_and_add_splits_a_part(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = self.lesson(d)
            plan = json.loads((lesson / "plan.json").read_text(encoding="utf-8"))
            parts_only = {k: v for k, v in plan.items() if k not in ("paints", "stages")}
            (lesson / "plan.json").write_text(json.dumps(parts_only), encoding="utf-8")
            r = self.run_tool("paints", "--lesson", str(lesson))
            self.assertTrue(r["first"])
            self.assertEqual(r["problems"], [])  # no stages yet is not a problem here
            self.assertIn("First measurement", r["advice"])
            (lesson / "plan.json").write_text(json.dumps(plan), encoding="utf-8")  # the fixture, with its steps
            r = self.run_tool("paints", "--lesson", str(lesson), "--add", "hill")
            self.assertEqual((r["added"], r["problems"], r["merged"]), ("hill-2", [], []))
            written = plan2.load(lesson)
            self.assertEqual(written["stages"], plan["stages"])  # the step is Claude's to point at it
            self.assertTrue(next(c for c in written["paints"] if c["id"] == "hill-2")["added"])
            r = self.run_tool("paints", "--lesson", str(lesson), "--add", "moon")
            self.assertIn("isn't one of the plan's parts", r["refused"])

    def test_a_version_1_lesson_is_refused_with_a_reason(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "plan.json").write_text(json.dumps({"steps": []}), encoding="utf-8")
            self.assertIn("version 2", self.run_tool("build-steps", "--lesson", d)["refused"])

    def test_build_steps_before_outline_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = self.lesson(d)
            (lesson / "parts" / "owner.png").unlink()
            self.assertIn("run outline", self.run_tool("build-steps", "--lesson", str(lesson))["refused"])


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_render import FakeClient

        self.tmp = tempfile.TemporaryDirectory()
        self.cache, tools.CACHE_DIR = tools.CACHE_DIR, Path(self.tmp.name) / "cache"
        self.client = FakeClient()
        finish, plan, owner = fixture("red-sailboat")
        self.lesson = Path(self.tmp.name) / "lesson"
        (self.lesson / "parts").mkdir(parents=True)
        (self.lesson / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        Image.fromarray(finish).save(self.lesson / "99_finish.png")
        Image.fromarray(owner.astype(np.uint8)).save(self.lesson / "parts" / "owner.png")

    def tearDown(self):
        tools.CACHE_DIR = self.cache
        self.tmp.cleanup()

    def run_tool(self, *argv) -> dict:
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            tools.main(list(argv), client=self.client)
        return json.loads(out.getvalue().strip().splitlines()[-1])

    def test_one_render_names_what_to_remove_and_is_counted(self):
        r = self.run_tool("background", "--lesson", str(self.lesson))
        self.assertEqual(self.client.images.calls, 1)
        self.assertGreater(r["cost_usd"], 0)
        self.assertEqual(r["removed"], ["The sail", "The hull", "The mast", "The reflection"])
        with Image.open(self.lesson / "98_background.png") as got, Image.open(self.lesson / "99_finish.png") as finish:
            self.assertEqual(got.size, finish.size)  # back at the finish's own size

    def test_a_second_render_needs_redo_and_only_one_redo_is_allowed(self):
        self.run_tool("background", "--lesson", str(self.lesson))
        self.assertIn("--redo", self.run_tool("background", "--lesson", str(self.lesson))["refused"])
        self.run_tool("background", "--lesson", str(self.lesson), "--redo")
        self.assertEqual(self.client.images.calls, 2)
        self.assertIn("refused", self.run_tool("background", "--lesson", str(self.lesson), "--redo"))
        self.assertEqual(self.client.images.calls, 2)

    def test_a_render_that_changed_the_scene_or_left_the_objects_is_reported(self):
        img, parts, given = scene()
        _, owner, _ = ol.outline(img, parts, given=given)
        front = owner == 3
        same, numbers = bs.background_problems(img, img.copy(), front)
        self.assertIn("didn't remove", " ".join(same))  # the ball is still there
        cleared = img.copy()
        cleared[front] = (110, 150, 220)
        self.assertEqual(bs.background_problems(img, cleared, front)[0], [])
        other = np.full_like(img, 30)
        self.assertIn("changed", " ".join(bs.background_problems(img, other, front)[0]))


class CardTests(unittest.TestCase):
    def test_the_cards_in_the_repo_are_complete(self):
        self.assertEqual(cards.problems(), [])
        self.assertEqual(len(cards.strokes()), len(cards.stroke_results()))  # one card per stroke result

    def test_every_stroke_the_fixture_plans_use_has_a_card(self):
        have = set(cards.strokes())
        for name in NAMES:
            used = {s["stroke"] for s in bs.flat_steps(fixture(name)[1])}
            self.assertEqual(used - have, set(), name)

    def test_what_a_broken_card_is_told(self):
        results = ["Dry brush (x)"]
        good = {"id": "dry-brush", "stroke_result": "Dry brush (x)", "name": "Dry brush", "result": "Broken marks.",
                "sources": ["research, section 2"], "checked": False, "brushes": ["flat"],
                "diagram": {"stages": [{"caption": "a", "add": [{"circle": [50, 50, 10], "paint": "#2f3b2a"}]}]}}
        self.assertEqual(cards.problems({"dry-brush": good}, {}, results), [])  # #127: a shape needs its paint
        for change, expect in (({"sources": []}, "no sources"), ({"result": ""}, "no result"),
                               ({"stroke_result": "Made up"}, "isn't an entry"), ({"brushes": ["spoon"]}, "can draw"),
                               ({"diagram": {"stages": [{"add": [{"blob": 1}]}]}}, "doesn't draw"),
                               ({"mistakes": [{"mistake": "Blobs."}]}, "'mistake' and 'fix'")):
            self.assertIn(expect, " | ".join(cards.problems({"dry-brush": {**good, **change}}, {}, results)))
        self.assertIn("no stroke card for", " | ".join(cards.problems({}, {}, results)))
        self.assertIn("no lines", " | ".join(cards.problems({}, {"x": {"id": "x", "name": "X", "sources": ["s"], "checked": False}}, [])))

    def test_every_basics_card_has_a_valid_when_and_a_missing_one_is_a_problem(self):
        for cid, c in cards.basics().items():
            self.assertIn(c.get("when"), cards.WHEN, cid)
        good = {"id": "x", "name": "X", "when": "start", "lines": ["a"], "sources": ["s"], "checked": False}
        self.assertEqual(cards.problems({}, {"x": good}, []), [])
        self.assertIn("x: no when", " | ".join(cards.problems({}, {"x": {**good, "when": None}}, [])))
        self.assertIn("isn't one of", " | ".join(cards.problems({}, {"x": {**good, "when": "someday"}}, [])))
        self.assertIn("only a start card", " | ".join(cards.problems({}, {"x": {**good, "when": "midway",
                                                                                 "fold": "F"}}, [])))

    def test_where_each_basics_card_goes_in_a_made_up_lesson(self):
        def st(part, show, group, hexes, kinds=(), area=None, of=False):
            return {"part": part, "show": show, "group": group, "lines": [{"kind": k, "text": "t"} for k in kinds],
                    "colors": [{"hex": h, **({"of": "p"} if of else {})} for h in hexes],
                    "aids": {} if area is None else {"area": area}}
        stages = [st("sun", "full", "sky", ["#f0e080"], area=0.02),                       # 1: small
                  st("sky", "blend", "sky", ["#5070c0", "#a0b0e0"], area=0.6),           # 2: the first big coat
                  st("hill", "flat", "land", ["#204020"], ["dry"], area=0.2),             # 3: over the sky; the stage start nearest halfway
                  st("hill", "pass", "land", ["#103010"], ["dry"]),                       # 4: darker, not a light value
                  st("hill", "pass", "land", ["#60a060"], ["dry"], of=True),              # 5: lighter, and a tint
                  st("tree", "flat", "tree", ["#302010"], ["dry"]),                       # 6: a later stage start
                  st("tree", "pass", "tree", ["#c0c0a0"], ["dry", "coats"])]              # 7: a coats line
        got = cards.places(stages)
        self.assertEqual({c: at for c, at in got.items() if at != "start"},
                         {"dries-darker": 1, "let-it-dry": 2, "one-light": 4, "lighter-darker": 4, "ugly-stage": 2,
                          "light-over-dark": 6})
        self.assertEqual(cards.unplaced(stages), [])
        # no coats line, no tint, no lighter pass: those cards don't show at all
        plain = [{**s, "lines": [x for x in s["lines"] if x["kind"] != "coats"],
                  "colors": [{"hex": "#101010"}]} for s in stages]
        got = cards.places(plain)
        self.assertFalse({"light-over-dark", "lighter-darker", "one-light"} & set(got))
        # with no step aids, the first coat stands in for the first big one
        self.assertEqual(cards.places([{**s, "aids": {}} for s in stages])["dries-darker"], 0)
        # nothing painted over anything: check notes the card that has nowhere to go
        bare = [st("a", "full", "g1", ["#ffffff"]), st("b", "full", "g2", ["#000000"])]
        self.assertEqual(len(cards.unplaced(bare)), 1)
        self.assertIn("let-it-dry", cards.unplaced(bare)[0])
        self.assertEqual(cards.unplaced(bare[:1]), [])  # one step: nothing is expected

    def test_the_ugly_stage_is_the_stage_start_nearest_halfway_never_the_last_step(self):
        def lesson(starts, n):
            group = 0
            out = []
            for i in range(n):
                group += i in starts and i > 0
                out.append({"group": f"g{group}", "show": "full", "colors": []})
            return out
        self.assertEqual(cards.moment("midway", lesson({0, 2, 9}, 10)), 2)    # not step 10 of 10
        self.assertEqual(cards.moment("midway", lesson({0, 9}, 10)), 5)       # only a last-step start: halfway
        self.assertEqual(cards.moment("midway", lesson({0}, 10)), 5)          # one stage: halfway
        self.assertEqual(cards.moment("midway", lesson({0, 4, 6}, 10)), 4)    # a tie goes to the earlier one
        self.assertIsNone(cards.moment("midway", lesson({0}, 1)))

    def test_a_when_that_isnt_a_word_is_a_problem_not_a_crash(self):
        good = {"id": "x", "name": "X", "lines": ["a"], "sources": ["s"], "checked": False}
        for when in (["start"], {"step": 3}):
            self.assertIn("isn't one of", " | ".join(cards.problems({}, {"x": {**good, "when": when}}, [])))
            self.assertEqual(cards.places([], {"x": {**good, "when": when}}), {})

    def test_an_unchecked_card_says_so_and_the_page_holds_every_card(self):
        page = cards.page()
        for cid in cards.strokes():
            self.assertIn(f"id='stroke-{cid}'", page)
        self.assertIn("Not checked yet", cards.stroke_html({**cards.strokes()["dabbing"], "checked": False}))
        self.assertNotIn("Not checked yet", cards.stroke_html({**cards.strokes()["dabbing"], "checked": True}))


if __name__ == "__main__":
    unittest.main()
