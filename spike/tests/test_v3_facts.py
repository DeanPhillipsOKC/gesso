"""Tests for spike S8 (#173, spike/experiments/v3_facts.py): each step's fact sheet, and the checker that reads every
number and side in a step's words against it (docs/spikes/v3-words-from-facts.md).

The #159 faults are turned into cases on small made-up scenes built to the sealed lavender run's measured geometry
(balloon-lavender_skill_20261116-171639 is in output/, which isn't in the repo), with that run's own words. No
renders, no network, no model files."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "experiments"))
sys.path.insert(0, str(HERE))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import lessons  # noqa: E402
import v3_facts as vf  # noqa: E402

PX = 20  # pixels per inch in the made-up scenes
CANVAS = {"w_in": 16, "h_in": 12}
WHITE = (250, 249, 245)


def ellipse(cx, cy, rx, ry):
    m = np.zeros((12 * PX, 16 * PX), np.uint8)
    cv2.ellipse(m, (round(cx * PX), round(cy * PX)), (round(rx * PX), round(ry * PX)), 0, 0, 360, 1, -1)
    return m > 0


def box(x0, y0, x1, y1):
    m = np.zeros((12 * PX, 16 * PX), bool)
    m[round(y0 * PX):round(y1 * PX), round(x0 * PX):round(x1 * PX)] = True
    return m


def poly(points):
    m = np.zeros((12 * PX, 16 * PX), np.uint8)
    cv2.fillPoly(m, [np.array([[round(x * PX), round(y * PX)] for x, y in points], np.int32)], 1)
    return m > 0


def rgb(h):
    return tuple(int(h[k:k + 2], 16) for k in (1, 3, 5))


def scene(parts, steps, paints):
    """A made-up lesson: `parts` [(id, name, kind, parent, mask)], back to front; `steps` [(id, part, show, paint ids,
    where the paint goes)], each painting inside its part; `paints` {id: (name, hex)}. Returns the sheet."""
    shape = (12 * PX, 16 * PX)
    owner = np.zeros(shape, np.int32)
    for k, (_pid, _n, _kind, _parent, m) in enumerate(parts):
        owner[m] = k
    plan = {"parts": [{"id": pid, "name": n, "kind": kind, **({"parent": parent} if parent else {})}
                      for pid, n, kind, parent, _m in parts],
            "paints": [{"id": c, "name": n, "hex": h} for c, (n, h) in paints.items()],
            "stages": [{"id": "all", "name": "All", "steps": [{"id": sid, "name": sid, "part": part, "show": show,
                                                                 "paints": ps} for sid, part, show, ps, _w in steps]}]}
    masks_of = {pid: m for pid, _n, _k, _p, m in parts}
    pic = np.empty(shape + (3,), np.uint8)
    pic[:] = WHITE
    pictures, masks = [], []
    for sid, part, show, ps, where in steps:
        pic = pic.copy()
        pic[where] = rgb(paints[ps[0]][1])
        pictures.append(pic)
        masks.append(masks_of[part].copy())
    return vf.make_sheet(plan, pictures, masks, owner, None, CANVAS)


def text(sheet, tips: dict[str, str]) -> dict:
    """text.json for a scene: each step's measured Where line, and the tips given."""
    return {"steps": [{"stage_id": st["id"], "tip": tips.get(st["id"], ""),
                       "lines": [{"kind": "where", "text": st["where"]}]} for st in sheet["steps"]]}


def failed(result, step_id=None):
    return [c for c in result["failures"] if step_id is None or c["id"] == step_id]


# --- the lavender run's balloon (#159 steps 20 to 22), measured: 2.4 to 5.2 in across, its middle at 3.8 in; the
# left red stripe at 2.65 to 2.95 in with a blue one outside it, the center red at 3.85 to 4.2 in (right of the
# middle) with a blue one on its left ---

BALLOON = ellipse(3.8, 2.2, 1.4, 1.75)
SKY = box(0, 0, 16, 12)
STRIPE_ROWS = box(0, 0.6, 16, 3.8)


def balloon_scene():
    paints = {"sky-1": ("Sunset orange", "#f08a3c"), "sky-2": ("Soft periwinkle", "#7d8ee0"),
              "b-red": ("Deep balloon red", "#b72d24"), "b-blue": ("Balloon blue", "#194f8e")}
    red = BALLOON & STRIPE_ROWS & (box(2.65, 0, 2.95, 12) | box(3.85, 0, 4.2, 12))
    blue = BALLOON & STRIPE_ROWS & (box(2.45, 0, 2.65, 12) | box(3.35, 0, 3.85, 12))
    return scene([("sky", "Sunset sky", "area", None, SKY), ("balloon", "The balloon", "object", None, BALLOON)],
                 [("sky", "sky", "flat", ["sky-2"], SKY), ("balloon-shape", "balloon", "flat", ["sky-1"], BALLOON),
                  ("balloon-red", "balloon", "pass", ["b-red"], red),
                  ("balloon-blue", "balloon", "pass", ["b-blue"], blue)], paints)


# the run's own words (text.json of balloon-lavender_skill_20261116-171639)
TIP_20 = ("The balloon is a rounded teardrop, about 2 1/2 inches wide and 3 inches tall, widest a third of the way "
          "down and tapering to the bottom.")
TIP_21 = ("Paint two red stripes from the top of the balloon down to the neck: one along the far left edge, and one "
          "just left of the center, curving like the lines on a globe.")
TIP_22 = ("Paint two blue stripes, curving top to bottom like the red ones: one just inside the left red stripe, and "
          "one right beside the center red stripe, on its right.")
TIP_16 = "The crown is about 3 1/2 inches wide, a lumpy rounded shape on the top of the big hill at the right edge."
WHERE_16 = ("Inside the outlined area. Its top is about 2 1/2 in from the top edge, and its right side is at the right "
            "edge; it's about 3 1/2 in wide and 3 in tall.")
TIP_11 = ("The left path reaches the bottom edge about a third of the way in, the right one about two-thirds in; each "
          "is about 1 1/2 inches wide at the bottom and a thread at the dot.")


class Fault159Tests(unittest.TestCase):
    """Every fault #159 lists, as a case: the checker fails the run's words, and passes the same words put right."""

    @classmethod
    def setUpClass(cls):
        cls.balloon = balloon_scene()

    def test_where_lines_pass_by_construction(self):
        r = vf.check_text(self.balloon, text(self.balloon, {}))
        self.assertTrue(r["claims"])
        self.assertEqual(r["failures"], [])

    def test_mirrored_center_stripe(self):
        """Step 21: 'just left of the center', where the center red is just right of it."""
        r = vf.check_text(self.balloon, text(self.balloon, {"balloon-red": TIP_21}))
        bad = failed(r, "balloon-red")
        self.assertEqual([c["words"] for c in bad], ["just left of the center"])
        self.assertIn("middle of the balloon is 3.8", bad[0]["sheet"])
        fixed = TIP_21.replace("just left of the center", "just right of the center")
        self.assertEqual(failed(vf.check_text(self.balloon, text(self.balloon, {"balloon-red": fixed}))), [])

    def test_mirrored_blue_stripes(self):
        """Step 22: one blue 'just inside the left red stripe' (it's outside it) and one on the center red's right
        (it's on its left)."""
        r = vf.check_text(self.balloon, text(self.balloon, {"balloon-blue": TIP_22}))
        bad = failed(r, "balloon-blue")
        self.assertEqual(sorted(c["words"] for c in bad), ["just inside the left red stripe", "on its right"])
        self.assertTrue(all("step 3's red" in c["why"] for c in bad), [c["why"] for c in bad])
        fixed = TIP_22.replace("just inside", "just outside").replace("on its right", "on its left")
        self.assertEqual(failed(vf.check_text(self.balloon, text(self.balloon, {"balloon-blue": fixed}))), [])

    def test_far_left_edge_of_the_part_is_not_the_canvas(self):
        """'along the far left edge' on a balloon's stripe means the balloon's edge: not flagged."""
        r = vf.check_text(self.balloon, text(self.balloon, {"balloon-red": "One stripe runs along the far left edge."}))
        self.assertEqual(r["failures"], [])
        self.assertEqual([c["kind"] for c in r["claims"] if c["field"] == "tip"], ["edge"])

    def test_sizes_that_disagree_within_a_step(self):
        """Step 20: the Where line says about 3 in wide and 3 1/2 in tall, the tip 2 1/2 and 3."""
        r = vf.check_text(self.balloon, text(self.balloon, {"balloon-shape": TIP_20}))
        kinds = sorted((c["kind"], c.get("cue") or c["sheet"].split()[-1]) for c in failed(r, "balloon-shape"))
        self.assertIn(("agree", "in"), kinds)
        self.assertEqual(sum(1 for c in failed(r, "balloon-shape") if c["kind"] == "agree"), 2)
        self.assertTrue(any(c["kind"] == "length" and c["cue"] == "tall" for c in failed(r, "balloon-shape")))
        fixed = TIP_20.replace("about 2 1/2 inches wide and 3 inches tall", "about 3 inches wide and 3 1/2 inches tall")
        self.assertEqual(failed(vf.check_text(self.balloon, text(self.balloon, {"balloon-shape": fixed}))), [])

    def test_crown_said_to_reach_the_right_edge(self):
        """Step 16: the crown 'at the right edge' when it stops 0.9 in short. #159 measured that in the image model's
        frame; in the run's canvas the crown stops 0.26 in short, which the Where measure calls the edge. Made up
        here as #159 describes it."""
        crown = ellipse(13.3, 4.0, 1.75, 1.5)  # 11.6 to 15.1 in across: 0.9 in short of the right edge
        sheet = scene([("sky", "Sunset sky", "area", None, SKY), ("tree", "The tree", "object", None, crown)],
                      [("sky", "sky", "flat", ["s"], SKY), ("tree-dark", "tree", "flat", ["t"], crown)],
                      {"s": ("Sunset orange", "#f08a3c"), "t": ("Deep blue-green", "#39474a")})
        st = sheet["steps"][1]
        self.assertAlmostEqual(st["area"]["right"], 0.9, delta=0.06)
        self.assertNotIn("right", st["area"]["edges"])
        t = text(sheet, {})
        t["steps"][1]["lines"] = [{"kind": "where", "text": WHERE_16}]
        bad = failed(vf.check_text(sheet, t))
        self.assertEqual([(c["kind"], c["words"]) for c in bad], [("edge", "right edge")])
        self.assertIn("0.9 in from the right edge", bad[0]["why"])
        # the tool's own line for it passes
        self.assertIn("1 in from the right edge", st["where"])
        self.assertEqual(failed(vf.check_text(sheet, text(sheet, {}))), [])

    def test_paths_two_thirds_in(self):
        """Step 11: the right path 'about two-thirds in' meets the bottom edge 0.79 of the way across; the left one,
        'a third of the way in', is right. Step 13: a pass in the paint of the coat under it (#159's paint fault)."""
        field = box(0, 7, 16, 12)
        dot = (9.0, 7.4)
        paths = poly([dot, (4.5, 12), (6.0, 12)]) | poly([dot, (11.9, 12), (13.4, 12)])
        rows = field & box(0, 8, 16, 12) & ~paths & (np.indices(field.shape)[1] % 20 < 6)
        sheet = scene([("sky", "Sunset sky", "area", None, box(0, 0, 16, 7)),
                       ("lavender", "Lavender rows", "area", None, field),
                       ("soil", "Dirt paths", "marks", "lavender", paths)],
                      [("sky", "sky", "flat", ["s"], box(0, 0, 16, 7)),
                       ("lavender-base", "lavender", "flat", ["v"], field),
                       ("soil-pull", "soil", "flat", ["e"], paths),
                       ("lavender-dark", "lavender", "pass", ["v2"], rows)],
                      {"s": ("Sunset orange", "#f08a3c"), "v": ("Shadow violet", "#313a51"),
                       "v2": ("Shadow violet", "#2a2e3c"), "e": ("Earth brown", "#763f37")})
        r = vf.check_text(sheet, text(sheet, {"soil-pull": TIP_11}))
        bad = failed(r, "soil-pull")
        self.assertEqual([c["words"] for c in bad], ["two-thirds in"])
        self.assertIn("right one", bad[0]["sheet"])
        ok = [c for c in r["claims"] if c["id"] == "soil-pull" and c["words"] == "a third of the way in"]
        self.assertEqual([c["ok"] for c in ok], [True])

    def test_same_paint_as_the_coat_under(self):
        paints = {"s": ("Sunset orange", "#f08a3c"), "v": ("Shadow violet", "#313a51")}
        field = box(0, 7, 16, 12)
        dabs = field & (np.indices(field.shape)[1] % 20 < 5)
        sheet = scene([("sky", "Sunset sky", "area", None, box(0, 0, 16, 7)),
                       ("lavender", "Lavender rows", "area", None, field)],
                      [("sky", "sky", "flat", ["s"], box(0, 0, 16, 7)),
                       ("lavender-base", "lavender", "flat", ["v"], field),
                       ("lavender-dark", "lavender", "pass", ["v"], dabs)], paints)
        r = vf.check_text(sheet, text(sheet, {}))
        self.assertEqual([(p["id"], p["paints"]) for p in r["paint_faults"]], [("lavender-dark", ["Shadow violet"])])


class ClaimTests(unittest.TestCase):
    """What counts as a claim, and what doesn't."""

    @classmethod
    def setUpClass(cls):
        cls.sheet = balloon_scene()
        cls.reader = vf.Reader(vf.Lesson(cls.sheet), cls.sheet["steps"][3])

    def claims(self, sentence):
        return self.reader.read(sentence, "tip")[0]

    def test_not_claims(self):
        for s in ["Keep the brush level and the strokes long, left and right.",
                  "Stroke side to side, from left to right, overlapping each stroke.",
                  "Brush: 1/2 inch flat. Load: Creamy paint.",
                  "Mix enough Balloon blue for this step and steps 4, 7 and 10; cover it between them.",
                  "The light comes from the left, so keep every highlight on that side.",
                  "Paint two blue stripes, then two coats if it looks thin.",
                  "Then add the rest in curved pieces on each side, like ( ), smaller toward the edges.",
                  "Start with the right-hand stripe, then the left one.",
                  "Pull the tail down to the lower left.",
                  "Leave the orange showing between the stripes.",
                  "It should leave a soft, round edge."]:
            self.assertEqual(self.claims(s), [], s)

    def test_lengths_parsed(self):
        cases = {"about 2 1/2 in from the left edge": 2.5, "3/4 inch across": 0.75, "two inches wide": 2.0,
                 "half an inch": 0.5, "an inch and a half": 1.5, "about 1.5 in tall": 1.5, "a quarter inch": 0.25,
                 "one and a half inches": 1.5, "about an inch across": 1.0}
        for words, want in cases.items():
            m = vf.LENGTH.search(words)
            self.assertIsNotNone(m, words)
            self.assertAlmostEqual(vf.inches(m), want, msg=words)
        self.assertIsNone(vf.LENGTH.search("Paint it in the middle"))

    def test_claim_kinds(self):
        kinds = {"Its left side is about 2 1/2 in from the left edge.": ["length"],
                 "The balloon is at the left edge.": ["edge"],
                 "Its right one sits about two-thirds in.": ["fraction"],
                 "One sits just right of the center.": ["center"],
                 "One goes just outside the left red stripe.": ["relation"],
                 "The balloon floats in the upper left of the canvas.": ["position"],
                 "The balloon floats at the upper left.": ["position"]}
        for s, want in kinds.items():
            self.assertEqual([c["kind"] for c in self.claims(s)], want, s)

    def test_a_failure_says_which_words_what_the_sheet_says_and_where(self):
        sheet = self.sheet
        r = vf.check_text(sheet, text(sheet, {"balloon-red": TIP_21}))
        line = vf.say(r["failures"][0])
        self.assertIn("step 3 (balloon-red), tip", line)
        self.assertIn('"just left of the center"', line)
        self.assertIn("sheet: the middle of the balloon is 3.8", line)

    def test_unresolved_fails_only_when_strict(self):
        t = text(self.sheet, {"balloon-blue": "Paint one stripe just inside the hedge."})
        self.assertEqual(vf.check_text(self.sheet, t)["failures"], [])
        self.assertEqual(len(vf.check_text(self.sheet, t)["unresolved"]), 1)
        self.assertEqual(len(vf.check_text(self.sheet, t, strict=True)["failures"]), 1)

    def test_sheet_is_json_and_measured(self):
        json.dumps(self.sheet)
        st = self.sheet["steps"][2]  # the red stripes, read where they cross the balloon's middle
        mids = [c["mid"] for c in st["crossings"]["across"]]
        self.assertEqual(len(mids), 2)
        self.assertAlmostEqual(mids[0], 2.8, delta=0.06)
        self.assertAlmostEqual(mids[1], 4.02, delta=0.06)
        self.assertEqual(st["earlier_steps_of_part"], [2])
        self.assertEqual(self.sheet["tolerance"], vf.TOLERANCE)


@lessons.slow
class FixtureTests(unittest.TestCase):
    """The three fixture lessons after draft-text: every claim in their Where lines passes (they're measured with
    the same measure as the sheet), and nothing in the drafted lines is flagged."""

    def test_fixtures(self):
        for name in lessons.NAMES:
            with self.subTest(name):
                lesson = lessons.lesson(name, "checked")
                sheet, plan = vf.lesson_sheet(lesson)
                t = json.loads((lesson / "text.json").read_text(encoding="utf-8"))
                r = vf.check_text(sheet, t)
                where = [c for c in r["claims"] if c["field"].endswith("(where)")]
                self.assertGreater(len(where), 40)
                self.assertTrue(all(c["ok"] for c in where), [vf.say(c) for c in where if not c["ok"]])
                self.assertEqual(r["failures"], [], [vf.say(c) for c in r["failures"]])
                for st, entry in zip(sheet["steps"], t["steps"]):
                    first = next(x["text"] for x in entry["lines"] if x["kind"] == "where")
                    self.assertTrue(first.startswith(st["where"]), (name, st["id"]))


LAVENDER = Path(os.environ.get("GESSO_OUTPUT", vf.ROOT / "output")) / "balloon-lavender_skill_20261116-171639"


@lessons.slow
@unittest.skipUnless((LAVENDER / "text.json").exists(), "the sealed lavender run of #159 isn't in output/ here")
class SealedLavenderTests(unittest.TestCase):
    """The run #159 was found in, when it's on this machine (output/ isn't in the repo)."""

    def test_flags(self):
        sheet, _plan = vf.lesson_sheet(LAVENDER)
        r = vf.check_text(sheet, json.loads((LAVENDER / "text.json").read_text(encoding="utf-8")))
        got = {(c["step"], c["words"]) for c in r["failures"]}
        for want in [(11, "two-thirds in"), (21, "just left of the center"), (22, "just inside the left red stripe"),
                     (22, "on its right")]:
            self.assertIn(want, got)
        self.assertEqual(sum(1 for c in r["failures"] if c["step"] == 20 and c["kind"] == "agree"), 2)
        self.assertEqual([p["step"] for p in r["paint_faults"]], [13])


if __name__ == "__main__":
    unittest.main()
