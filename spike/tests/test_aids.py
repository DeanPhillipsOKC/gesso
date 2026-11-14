"""Tests for the teaching pictures (spike/aids.py and the step-aids tool, issue #68, docs/design/pipeline-v2.md
section 10): where each step's paint goes, close-ups, paint maps, the transfer outline, and positions in words.
No renders, no network, no model files: the three fixtures' saved outlines are enough."""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import aids  # noqa: E402
import build_steps as bs  # noqa: E402
import lessons  # noqa: E402
import tools  # noqa: E402
from test_pipeline_v2 import CANVAS, NAMES, fixture  # noqa: E402

PERCENT = re.compile(r"%|percent", re.I)


def run_tool(*argv) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = tools.main(list(argv))
    return code, json.loads(out.getvalue().strip().splitlines()[-1])


@lessons.slow
class AidsTests(unittest.TestCase):
    whole = True  # tests/suite.py runs it as one job: its setUpClass makes every fixture's aids

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.built = {}
        for name in NAMES:
            owner = fixture(name)[2]
            plan, pictures, _, masks = lessons.built(name)
            names = [f"{i + 1:02d}_{s['id']}.png" for i, s in enumerate(bs.flat_steps(plan))]
            out = Path(cls.tmp.name) / name / "aids"
            data = aids.make(plan, pictures, masks, owner, None, CANVAS, out, names)
            cls.built[name] = (plan, owner, pictures, masks, data, out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_each_where_outline_covers_what_its_step_changed(self):
        for name, (plan, _, pictures, _, data, _) in self.built.items():
            h, w = pictures[0].shape[:2]
            before = np.empty_like(pictures[0])
            before[:] = bs.ff.CANVAS
            for pic, row in zip(pictures, data["steps"]):
                changed = np.abs(pic.astype(np.int16) - before.astype(np.int16)).max(2) > 6
                inside = cv2.resize(aids.path_mask(row["path"], tuple(data["view"])).astype(np.uint8), (w, h),
                                    interpolation=cv2.INTER_NEAREST) > 0
                if changed.any():
                    share = (changed & inside).sum() / changed.sum()
                    self.assertGreaterEqual(share, 0.95, f"{name} {row['id']}: the outline holds {share:.1%} of what changed")
                before = pic

    def test_an_outline_is_drawn_round_the_area_not_the_whole_picture(self):
        for name, (_, _, _, masks, data, _) in self.built.items():
            for m, row in zip(masks, data["steps"]):
                inside = aids.path_mask(row["path"], tuple(data["view"])).mean()
                if m.mean() < 0.9:
                    self.assertLess(inside, 0.95, f"{name} {row['id']}")
                if m.mean() < 0.05:  # a small thing stays small: joining marks doesn't swallow the picture
                    self.assertLess(inside, 0.25, f"{name} {row['id']}")

    def test_no_percentage_in_any_position_sentence(self):
        for name, (_, _, _, _, data, _) in self.built.items():
            for row in data["steps"]:
                self.assertNotRegex(row["where_words"], PERCENT, f"{name} {row['id']}")
                self.assertTrue(row["where_words"].startswith("Inside the outlined area"))

    def test_close_ups_are_for_small_areas_and_at_most_600_pixels(self):
        for name, (_, _, _, _, data, out) in self.built.items():
            self.assertTrue(any(r.get("closeup") for r in data["steps"]), name)
            for r in data["steps"]:
                if not r.get("closeup"):
                    continue
                self.assertLess(r["area"], aids.CLOSE_UP)
                for key in ("before", "after"):
                    with Image.open(out.parent / r["closeup"][key]) as img:
                        self.assertLessEqual(max(img.size), aids.CLOSE_PX)

    def test_paint_maps_are_small_indexed_pngs_whose_colors_match_the_legend(self):
        for name, (plan, _, _, _, data, out) in self.built.items():
            want = aids.map_steps(plan)
            got = {i for i, r in enumerate(data["steps"]) if r.get("map")}
            self.assertEqual(got, set(want), name)
            hexes = {c["id"]: c["hex"] for c in plan["paints"]}
            for i in got:
                m = data["steps"][i]["map"]
                self.assertEqual({x["paint"] for x in m["legend"]}, set(want[i][1]))
                self.assertEqual([x["n"] for x in m["legend"]], list(range(1, len(m["legend"]) + 1)))
                with Image.open(out.parent / m["image"]) as img:
                    self.assertEqual(img.mode, "P")
                    self.assertLessEqual(max(img.size), aids.MAP_PX)
                    pal = img.getpalette()
                    used = set(np.unique(np.asarray(img)).tolist())
                for x in m["legend"]:
                    k = x["n"] + 1  # 0 outside, 1 the edge, then the paints in legend order
                    self.assertEqual("#%02x%02x%02x" % tuple(pal[3 * k:3 * k + 3]), hexes[x["paint"]].lower())
                    if x["at"]:
                        self.assertIn(k, used)

    def test_the_transfer_outline_shows_the_objects_with_no_parent(self):
        for name, (plan, _, _, _, data, out) in self.built.items():
            objects = [p["id"] for p in plan["parts"] if p["kind"] == "object" and not p.get("parent")]
            self.assertEqual([x["part"] for x in data["transfer"]["parts"]], objects, name)
            self.assertTrue((out / "transfer.png").exists())

    def test_the_same_input_gives_the_same_bytes(self):
        plan, owner, pictures, masks, data, out = self.built["red-sailboat"]
        again = out.parent / "again" / "aids"
        names = [r["image"] for r in data["steps"]]
        self.assertEqual(aids.make(plan, pictures, masks, owner, None, CANVAS, again, names), data)
        for f in sorted(out.iterdir()):
            self.assertEqual(f.read_bytes(), (again / f.name).read_bytes(), f.name)


class WhereWordsTests(unittest.TestCase):
    def area(self, box, shape=(110, 140)):
        a = np.zeros(shape, bool)
        h, w = shape
        a[round(box[1] * h):round(box[3] * h), round(box[0] * w):round(box[2] * w)] = True
        return a

    def test_inches_from_the_nearer_edges_on_a_known_canvas(self):
        words = aids.where_words(self.area([0.7, 0.6, 0.9, 0.9]), {"w_in": 14, "h_in": 11})
        self.assertEqual(words, "Inside the outlined area. Its bottom is about 1 in from the bottom edge, and its right "
                                "side is about 1 1/2 in from the right edge; it's about 3 in wide and 3 1/2 in tall.")
        sky = aids.where_words(self.area([0, 0, 1, 0.56]), {"w_in": 14, "h_in": 11})
        self.assertEqual(sky, "Inside the outlined area, all the way across from the top edge. Its bottom is about "
                              "5 in from the bottom edge.")

    def test_with_a_canvas_only_inches_and_with_none_refused(self):
        # #122: the tape-mark path is gone. With a canvas size every anchor is inches; without one it's refused.
        words = aids.where_words(self.area([0.4, 0.27, 0.5, 0.4]), {"w_in": 14, "h_in": 11})
        self.assertEqual(words, "Inside the outlined area. Its top is about 3 in from the top edge, and its left side "
                                "is about 5 1/2 in from the left edge; it's about 1 1/2 in wide and 1 1/2 in tall.")
        self.assertNotIn("tape", words)
        self.assertNotIn("mark", words)
        self.assertFalse(hasattr(aids, "MARKS_ACROSS") or hasattr(aids, "MARKS_DOWN") or hasattr(aids, "_near_mark"))
        # a mast or an eye light is narrower than a quarter inch: never "0 in" (review of #122)
        thin = aids.where_words(self.area([0.4, 0.2, 0.405, 0.6], (1100, 1400)), {"w_in": 14, "h_in": 11})
        self.assertIn("it's under 1/4 in wide and about 4 1/2 in tall", thin)
        self.assertNotIn(" 0 in", thin)
        eighth = np.zeros((1024, 1024), bool)
        eighth[500:510, 500:516] = True  # exactly 1/8 in across on 8 x 8 in, which rounds to 0
        self.assertIn("it's under 1/4 in wide and under 1/4 in tall", aids.where_words(eighth, {"w_in": 8, "h_in": 8}))
        with self.assertRaisesRegex(ValueError, "canvas.json"):
            aids.where_words(self.area([0.4, 0.27, 0.5, 0.4]), None)

    def test_stray_specks_far_away_dont_move_it(self):
        # #90: two specks by the trunk put the chickadee's body at the left edge and 8 1/2 in wide
        canvas = {"w_in": 14, "h_in": 11}
        body = self.area([0.4, 0.27, 0.5, 0.4], (1100, 1400))
        alone = aids.where_words(body, canvas)
        specked = body.copy()
        specked[500:506, 0:6] = True  # at the left edge, far below
        specked[1080:1086, 1380:1386] = True  # in the bottom right corner
        self.assertEqual(aids.where_words(specked, canvas), alone)
        self.assertEqual(aids.main_area(specked).sum(), body.sum())

    def test_small_marks_near_the_part_count_and_far_specks_dont_whatever_they_add_up_to(self):
        # review of #143: a 10% rule for "many small marks" measured the far specks again at 10% and dropped the
        # marks beside the body under it. Each small piece is judged by how near it is to the rest of the part.
        canvas = {"w_in": 14, "h_in": 11}
        for n in (14, 15):  # the small pieces, specks included, are 9.6% and 10.2% of the area: either side of 10%
            body = np.zeros((1100, 1400), bool)
            body[300:440, 550:690] = True  # 140 x 140 px
            for k in range(n):  # a row of 12 x 12 dabs 48 px above it, 40 px apart: each under 1% of the area
                body[240:252, 400 + 40 * k:412 + 40 * k] = True
            marks = body.copy()
            body[500:506, 0:6] = True  # a speck at the left edge
            body[1090:1096, 1390:1396] = True  # and one in the bottom right corner
            self.assertTrue((aids.main_area(body) == marks).all(), n)
            words = aids.where_words(body, canvas)
            self.assertEqual(words, aids.where_words(marks, canvas), n)
            self.assertIn("Its top is about 2 1/2 in from the top edge", words)  # the dabs, at 240 of 1100 px

    def test_a_trail_of_specks_doesnt_carry_the_box_away(self):
        # second review of #143: 2 x 2 specks 50 px apart (3.6% of the long side) ran a body's box 7 in to the left
        # edge. Specks that small count only beside a mark; they don't carry the chain on.
        canvas = {"w_in": 14, "h_in": 11}
        body = np.zeros((1100, 1400), bool)
        body[300:440, 550:690] = True
        body[370:372, 500:502] = True  # 48 px from the body, within STRAY_NEAR (56 px): it counts
        beside = aids.where_words(body, canvas)
        for x in range(450, 0, -50):  # and the trail on from it to the left edge doesn't
            body[370:372, x:x + 2] = True
        self.assertEqual(aids.main_area(body).sum(), 140 * 140 + 4)
        self.assertEqual(aids.where_words(body, canvas), beside)
        self.assertIn("about 5 in from the left edge", beside)

    def test_a_long_chain_is_quick(self):
        # second review of #143: one distance pass per mark added took 2.1 s for 25 dabs at 2800 px
        body = np.zeros((2200, 2800), bool)
        body[600:880, 1100:1380] = True
        for k in range(12):  # 25 dabs in two rows out from the body, 2 to 3% of the long side apart
            body[700:724, 1000 - 90 * k:1024 - 90 * k] = True
        for k in range(13):
            body[700:724, 1440 + 100 * k:1464 + 100 * k] = True
        start = time.perf_counter()
        kept = aids.main_area(body)
        self.assertLess(time.perf_counter() - start, 1.0)  # about 0.2 s on 4 cores
        self.assertTrue((kept == body).all())  # every dab is on the chain

    def test_a_part_of_only_small_pieces_is_measured_whole(self):
        # sparkles: every piece is under 1% of the area, so there's nothing to call the rest of the part
        dots = np.zeros((1100, 1400), bool)
        for k in range(150):
            x, y = 20 + 9 * k, 200 + (k % 30) * 20
            dots[y:y + 4, x:x + 4] = True
        self.assertTrue((aids.main_area(dots) == dots).all())
        self.assertIn("it's about 13 1/2 in wide", aids.where_words(dots, {"w_in": 14, "h_in": 11}))

    def test_inches_are_measured_on_the_canvas_not_the_frame(self):
        frame = np.zeros((200, 300), bool)
        box = [0.2, 0.1, 0.8, 0.9]  # the canvas is a crop of the image model's frame
        frame[20:60, 60:120] = True  # touches the canvas's top and left edges, not the frame's
        words = aids.where_words(aids.to_canvas(frame, box), {"w_in": 9, "h_in": 8})
        self.assertIn("Its top is at the top edge, and its left side is at the left edge", words)
        self.assertIn("about 3 in wide and 2 in tall", words)  # 60 of 180 px across 9 in; 40 of 160 px down 8 in


@lessons.slow
class StepAidsToolTests(unittest.TestCase):
    def lesson(self, d: str, stage: str) -> Path:
        return lessons.lesson("red-sailboat", stage, Path(d))  # built once per run and shared (tests/lessons.py)

    def test_step_aids_before_build_steps_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            code, r = run_tool("step-aids", "--lesson", str(self.lesson(d, "outlined")))
            self.assertEqual(code, 2)
            self.assertIn("run build-steps", r["refused"])

    def test_a_canvas_cropped_from_the_frame_gives_canvas_pictures_and_inches(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = self.lesson(d, "aided")  # build-steps doesn't read canvas.json; step-aids does
            box = [0.1, 0.05, 0.9, 0.95]
            (lesson / "canvas.json").write_text(json.dumps({"canvas": {"w_in": 10, "h_in": 8.5, "orientation": "landscape"},
                                                            "canvas_box": box}), encoding="utf-8")
            code, r = run_tool("step-aids", "--lesson", str(lesson))
            self.assertEqual(code, 0, r)
            data = json.loads((lesson / "aids" / "aids.json").read_text(encoding="utf-8"))
            steps = bs.flat_steps(fixture("red-sailboat")[1])
            self.assertEqual([x["id"] for x in data["steps"]], [s["id"] for s in steps])
            vw, vh = data["view"]
            with Image.open(lesson / data["steps"][0]["image"]) as shown:  # the canvas crop the page shows
                self.assertTrue(data["steps"][0]["image"].startswith("canvas/"))
                self.assertAlmostEqual(vw / vh, shown.size[0] / shown.size[1], places=2)
            words = " ".join(x["where_words"] for x in data["steps"])
            self.assertIn(" in from the ", words)
            self.assertNotRegex(words, PERCENT)
            sun = next(x for x in data["steps"] if x["id"] == "sun")
            with Image.open(lesson / sun["closeup"]["after"]) as img:
                self.assertLessEqual(max(img.size), aids.CLOSE_PX)

    def test_step_pictures_that_dont_match_the_plan_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = self.lesson(d, "aided")
            first = sorted(lesson.glob("01_*.png"))[0]
            with Image.open(first) as img:
                size = img.size
            Image.new("RGB", size, (0, 0, 0)).save(first)
            code, r = run_tool("step-aids", "--lesson", str(lesson))
            self.assertEqual(code, 2)
            self.assertIn("don't match the plan", r["refused"])


if __name__ == "__main__":
    unittest.main()
