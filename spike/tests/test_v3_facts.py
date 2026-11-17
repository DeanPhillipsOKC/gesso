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


def scene(parts, steps, paints, pad: float = 0.0):
    """A made-up lesson: `parts` [(id, name, kind, parent, mask)], back to front; `steps` [(id, part, show, paint ids,
    where the paint goes)], each painting inside its part; `paints` {id: (name, hex)}. Returns the sheet. With `pad`,
    the pictures are in a frame `pad` inches wider on each side than the canvas, as a real finish is in the image
    model's frame, and canvas_box says where the canvas sits in it."""
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
    if not pad:
        return vf.make_sheet(plan, pictures, masks, owner, None, CANVAS)
    k = round(pad * PX)
    wide = shape[1] + 2 * k

    def framed(a, fill):
        out = np.empty((shape[0], wide) + a.shape[2:], a.dtype)
        out[:] = fill
        out[:, k:k + shape[1]] = a
        return out
    box_ = [k / wide, 0.0, (k + shape[1]) / wide, 1.0]
    return vf.make_sheet(plan, [framed(x, WHITE) for x in pictures], [framed(x, False) for x in masks],
                         framed(owner, 0), box_, CANVAS)


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


def balloon_scene(blue_right=False):
    """The run's balloon; with `blue_right`, the second blue stripe is on the center red's right (4.2 to 4.6 in)."""
    paints = {"sky-1": ("Sunset orange", "#f08a3c"), "sky-2": ("Soft periwinkle", "#7d8ee0"),
              "b-red": ("Deep balloon red", "#b72d24"), "b-blue": ("Balloon blue", "#194f8e")}
    red = BALLOON & STRIPE_ROWS & (box(2.65, 0, 2.95, 12) | box(3.85, 0, 4.2, 12))
    blue = BALLOON & STRIPE_ROWS & (box(2.45, 0, 2.65, 12) | (box(4.2, 0, 4.6, 12) if blue_right else box(3.35, 0, 3.85, 12)))
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
        # without "just" too (M2 of the PR #182 review): the left-edge stripe doesn't make it right
        loose = "Paint one stripe along the far left edge, and one left of the center."
        self.assertEqual([c["words"] for c in failed(vf.check_text(self.balloon, text(self.balloon, {
            "balloon-red": loose})))], ["left of the center"])

    def test_mirrored_blue_stripes(self):
        """Step 22: one blue 'just inside the left red stripe' (it's outside it) and one on the center red's right
        (it's on its left)."""
        r = vf.check_text(self.balloon, text(self.balloon, {"balloon-blue": TIP_22}))
        bad = failed(r, "balloon-blue")
        self.assertEqual(sorted(c["words"] for c in bad), ["just inside the left red stripe", "on its right"])
        self.assertTrue(all("step 3's red" in c["why"] for c in bad), [c["why"] for c in bad])
        fixed = TIP_22.replace("just inside", "just outside").replace("on its right", "on its left")
        self.assertEqual(failed(vf.check_text(self.balloon, text(self.balloon, {"balloon-blue": fixed}))), [])
        # the same faults worded without "just" (M2), and the center red named as a stripe (M1)
        for tip, words in [("Paint one blue stripe inside the left red stripe.", "inside the left red stripe"),
                           ("Paint one blue stripe right of the center red stripe.", "right of the center red stripe")]:
            got = [c["words"] for c in failed(vf.check_text(self.balloon, text(self.balloon, {"balloon-blue": tip})))]
            self.assertEqual(got, [words], tip)
        other = balloon_scene(blue_right=True)
        for tip, words in [("One blue stripe sits left of the center red stripe.", "left of the center red stripe"),
                           ("Paint one blue stripe inside the center red stripe.", "inside the center red stripe")]:
            got = [c["words"] for c in failed(vf.check_text(other, text(other, {"balloon-blue": tip})))]
            self.assertEqual(got, [words], tip)
        # two relations joined by "and" with no comma: each is a claim (N1 of the second review)
        for tip, words, fixed in [
                ("One goes just outside the left red stripe and one just left of the center red stripe.",
                 "just left of the center red stripe",
                 "One goes just outside the left red stripe and one just right of the center red stripe."),
                ("Paint one stripe just outside the left red stripe and the other just inside the center red stripe.",
                 "just inside the center red stripe",
                 "Paint one stripe just outside the left red stripe and the other just outside the center red stripe.")]:
            got = [c["words"] for c in failed(vf.check_text(other, text(other, {"balloon-blue": tip})))]
            self.assertEqual(got, [words], tip)
            r = vf.check_text(other, text(other, {"balloon-blue": fixed}))
            self.assertEqual(failed(r), [], fixed)
            self.assertEqual(len([c for c in r["claims"] if c["kind"] == "relation"]), 2, fixed)

    def test_far_left_edge_of_the_part_is_not_the_canvas(self):
        """'along the far left edge' on a balloon's stripe means the balloon's edge: not flagged. 'at the left edge'
        means the canvas's, and the balloon is 2.4 in from it (H1 of the PR #182 review)."""
        r = vf.check_text(self.balloon, text(self.balloon, {"balloon-red": "One stripe runs along the far left edge."}))
        self.assertEqual(r["failures"], [])
        self.assertEqual([c["kind"] for c in r["claims"] if c["field"] == "tip"], ["edge"])
        for sid, tip in [("balloon-red", "One stripe is at the left edge."),
                         ("balloon-blue", "The blue goes along the right edge of the balloon.")]:
            self.assertEqual([c["kind"] for c in failed(vf.check_text(self.balloon, text(self.balloon, {
                sid: tip})))], ["edge"], tip)
        t = text(self.balloon, {})  # a pass's Where line mirrored: no second chance at the part's own edge
        t["steps"][2]["lines"] = [{"kind": "where", "text": "Inside the outlined area. Its left side is at the left edge."}]
        self.assertEqual([c["kind"] for c in failed(vf.check_text(self.balloon, t))], ["edge"])

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

    def test_crown_said_to_reach_the_right_edge_on_a_later_step(self):
        """The same crown, said to reach the edge on a pass over it (H1 of the PR #182 review): a mark near the
        crown's own right side doesn't make the canvas's edge."""
        crown = ellipse(13.3, 4.0, 1.75, 1.5)
        lumps = crown & (np.indices(crown.shape)[1] % 16 < 6)
        sheet = scene([("sky", "Sunset sky", "area", None, SKY), ("tree", "The tree", "object", None, crown)],
                      [("sky", "sky", "flat", ["s"], SKY), ("tree-dark", "tree", "flat", ["t"], crown),
                       ("tree-mid", "tree", "pass", ["o"], lumps)],
                      {"s": ("Sunset orange", "#f08a3c"), "t": ("Deep blue-green", "#39474a"),
                       "o": ("Olive green", "#6b7a2e")})
        t = text(sheet, {"tree-mid": "Tap olive over the crown, whose right side is at the right edge."})
        t["steps"][2]["lines"] = [{"kind": "where", "text": WHERE_16}]
        bad = failed(vf.check_text(sheet, t), "tree-mid")
        self.assertEqual(sorted((c["field"], c["kind"]) for c in bad), [("line 1 (where)", "edge"), ("tip", "edge")])

    def test_frame_cropped_to_canvas(self):
        """A finish in the image model's frame, 3/4 in wider each side than the canvas: everything is measured on
        the canvas. A crown 0.26 in short of the canvas's right edge (the lavender run's step 16) is at the edge,
        as its Where line says, though it's about 1 in short of the frame's."""
        crown = ellipse(14.0, 4.0, 1.75, 1.5)  # to 15.75 in: 0.25 in short of the canvas's right edge
        sheet = scene([("sky", "Sunset sky", "area", None, SKY), ("tree", "The tree", "object", None, crown)],
                      [("sky", "sky", "flat", ["s"], SKY), ("tree-dark", "tree", "flat", ["t"], crown)],
                      {"s": ("Sunset orange", "#f08a3c"), "t": ("Deep blue-green", "#39474a")}, pad=0.75)
        st = sheet["steps"][1]
        self.assertAlmostEqual(st["area"]["right"], 0.25, delta=0.06)
        self.assertIn("right", st["area"]["edges"])
        self.assertIn("its right side is at the right edge", st["where"])
        self.assertEqual(failed(vf.check_text(sheet, text(sheet, {}))), [])
        t = text(sheet, {"tree-dark": "The crown's right side is about 1 in from the right edge."})
        self.assertEqual([c["kind"] for c in failed(vf.check_text(sheet, t))], ["length"])

    def test_paths_two_thirds_in(self):
        """Step 11: the right path 'about two-thirds in' meets the bottom edge 0.79 of the way across; the left one,
        'a third of the way in', is right."""
        field = box(0, 7, 16, 12)
        dot = (9.0, 7.4)
        paths = poly([dot, (4.6, 12), (5.95, 12)]) | poly([dot, (12.0, 12), (13.35, 12)])
        sheet = scene([("sky", "Sunset sky", "area", None, box(0, 0, 16, 7)),
                       ("lavender", "Lavender rows", "area", None, field),
                       ("soil", "Dirt paths", "marks", "lavender", paths)],
                      [("sky", "sky", "flat", ["s"], box(0, 0, 16, 7)),
                       ("lavender-base", "lavender", "flat", ["v"], field),
                       ("soil-pull", "soil", "flat", ["e"], paths)],
                      {"s": ("Sunset orange", "#f08a3c"), "v": ("Shadow violet", "#313a51"),
                       "e": ("Earth brown", "#763f37")})
        r = vf.check_text(sheet, text(sheet, {"soil-pull": TIP_11}))
        bad = failed(r, "soil-pull")
        self.assertEqual([c["words"] for c in bad], ["two-thirds in"])
        self.assertIn("right one", bad[0]["sheet"])
        ok = [c for c in r["claims"] if c["id"] == "soil-pull" and c["words"] == "a third of the way in"]
        self.assertEqual([c["ok"] for c in ok], [True])

    def test_a_pass_reaches_the_edges_its_marks_reach(self):
        """N2 of the second review: on a pass, a tip's edge claim is about the marks it adds, not the whole part."""
        field = box(0, 7, 16, 12)
        dabs = field & box(0, 7, 5, 12) & (np.indices(field.shape)[1] % 20 < 6)  # all in the left third
        sheet = scene([("sky", "Sunset sky", "area", None, box(0, 0, 16, 7)),
                       ("lavender", "Lavender rows", "area", None, field)],
                      [("sky", "sky", "flat", ["s"], box(0, 0, 16, 7)),
                       ("lavender-base", "lavender", "flat", ["v"], field),
                       ("lavender-dark", "lavender", "pass", ["d"], dabs)],
                      {"s": ("Sunset orange", "#f08a3c"), "v": ("Lavender purple", "#6250a8"),
                       "d": ("Shadow violet", "#313a51")})
        for tip, bad in [("Dab the dark marks at the right edge of the canvas.", ["edge"]),
                         ("Dab the dark marks all the way across.", ["edge"]),
                         ("Keep the dark marks short of the right edge.", []),
                         ("Start the dark marks at the left edge.", [])]:
            got = [c["kind"] for c in failed(vf.check_text(sheet, text(sheet, {"lavender-dark": tip})), "lavender-dark")]
            self.assertEqual(got, bad, tip)

    def test_many_equal_dabs_reach_the_edges_they_reach(self):
        """N3 of the third review: 13 equal dabs across the field are more than the sheet's 8 marks, and the edge
        claims read all of the paint the pass adds, not only the biggest marks."""
        field = box(0, 7, 16, 12)
        cols = np.indices(field.shape)[1]
        across = field & box(0, 9, 16, 10) & ((cols % 27 < 7) | box(15.65, 0, 16, 12))  # 13 dabs, edge to edge
        part_way = across & box(0, 0, 9, 12)  # the same dabs, stopping a little past the middle
        for dabs, ok in ((across, True), (part_way, False)):
            sheet = scene([("sky", "Sunset sky", "area", None, box(0, 0, 16, 7)),
                           ("lavender", "Lavender rows", "area", None, field)],
                          [("sky", "sky", "flat", ["s"], box(0, 0, 16, 7)),
                           ("lavender-base", "lavender", "flat", ["v"], field),
                           ("lavender-dark", "lavender", "pass", ["d"], dabs)],
                          {"s": ("Sunset orange", "#f08a3c"), "v": ("Lavender purple", "#6250a8"),
                           "d": ("Shadow violet", "#313a51")})
            if ok:
                self.assertEqual(len(sheet["steps"][2]["marks"]), vf.MAX_MARKS)
            for tip in ["Dab the dark marks all the way across.",
                        "Dab the dark marks from the left edge to the right edge."]:
                got = [c["kind"] for c in failed(vf.check_text(sheet, text(sheet, {"lavender-dark": tip})),
                                                 "lavender-dark")]
                self.assertEqual(got, [] if ok else ["edge"], (tip, ok))

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
                  "Dab two in this corner.",
                  "Paint it about 11 inches.",  # a length that names no axis, edge or size is unresolved, not a claim
                  "It should leave a soft, round edge."]:
            self.assertEqual([c for c in self.claims(s) if c["ok"] is not None], [], s)

    def test_no_claim_at_all(self):
        for s in ["Keep the brush level and the strokes long, left and right.", "Dab two in this corner."]:
            self.assertEqual(self.claims(s), [], s)

    def test_lengths_parsed(self):
        cases = {"about 2 1/2 in from the left edge": 2.5, "3/4 inch across": 0.75, "two inches wide": 2.0,
                 "half an inch": 0.5, "an inch and a half": 1.5, "about 1.5 in tall": 1.5, "a quarter inch": 0.25,
                 "one and a half inches": 1.5, "about an inch across": 1.0, "about 1-1/2 inches wide": 1.5,
                 "1½ in": 1.5, "¾ inch": 0.75, ".5 in": 0.5, "fourteen inches": 14.0, "three quarters of an inch": 0.75,
                 "2 to 3 inches": 2.5, "2-3 in": 2.5}
        for words, want in cases.items():
            m = vf.LENGTH.search(words)
            self.assertIsNotNone(m, words)
            self.assertAlmostEqual(vf.inches(m), want, msg=words)
        self.assertEqual(vf.span(vf.LENGTH.search("2 to 3 inches wide")), (2.0, 3.0))
        self.assertIsNone(vf.LENGTH.search("Paint it in the middle"))
        self.assertIsNone(vf.LENGTH.search("Dab two in this corner."))

    def test_a_length_is_checked_against_the_fact_it_names(self):
        """H2 of the PR #182 review: 'its top' against the top, not any value of any thing."""
        st = self.sheet["steps"][1]  # the balloon's coat: top 0.5 in from the top edge, left side 2.4 in
        t = text(self.sheet, {})
        for line, ok in [("Its top is about 1/2 in from the top edge.", True),
                         ("Its top is about 1 1/2 in from the top edge.", False),
                         ("Its bottom is about 1/2 in from the top edge.", False),
                         ("Its left side is about 2 1/2 in from the left edge.", True),
                         ("Its left side is about 3 1/2 in from the left edge.", False),
                         ("Its right side is about 2 1/2 in from the left edge.", False)]:
            t["steps"][1]["lines"] = [{"kind": "where", "text": "Inside the outlined area. " + line}]
            r = vf.check_text(self.sheet, t)
            got = [c["ok"] for c in r["claims"] if c["id"] == st["id"] and c["kind"] == "length"]
            self.assertEqual(got, [ok], line)

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

    def test_surrounded_and_leave(self):
        """L3: a side of a part all round the thing says nothing ('right of the sky'); 'keep' isn't 'leave'."""
        cs = [c for c in self.claims("The balloon is right of the sky.") if c["kind"] == "relation"]
        self.assertEqual([c["ok"] for c in cs], [None])
        cs = vf.Reader(vf.Lesson(self.sheet), self.sheet["steps"][1]).read(
            "Keep the dark marks at the right edge.", "tip")[0]
        self.assertEqual([c["ok"] for c in cs], [False])

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


class MutationTests(unittest.TestCase):
    """Planted faults: the share the checker catches is a number of its own (the PR #182 review)."""

    def test_balloon_where_lines(self):
        sheet = balloon_scene()
        r = vf.mutate(sheet, text(sheet, {}))
        self.assertEqual(r["base"]["flags"], 0)
        for kind in ("length +1 in", "length -1 in", "length +1/2 in", "length -1/2 in"):
            n, caught = r["where"][kind]
            self.assertGreaterEqual(n, 4, kind)
            self.assertGreaterEqual(caught / n, 0.9, (kind, r["missed"]))

    def test_mutants(self):
        s = "Its left side is about 2 1/2 in from the left edge, and its top is at the top edge."
        reader = vf.Reader(vf.Lesson(balloon_scene()), balloon_scene()["steps"][1])
        got = dict(vf.mutants(s, reader.read(s, "line 1 (where)")[0]))
        self.assertIn("Its right side is about 2 1/2 in from the right edge", got["left/right swapped"])
        self.assertIn("about 3 1/2 in from the left edge", got["length +1 in"])
        self.assertIn("Its left side is about 2 1/2 in from the left edge, and its bottom is at the bottom edge",
                      got["up/down swapped"])
        self.assertEqual(vf._swap("top to bottom, at the top", vf.SWAP_UD), "top to bottom, at the bottom")


# the catch rate on the three fixtures' Where lines, from this spike's run (docs/spikes/v3-words-from-facts.md):
# every +-1 in shift and every swap caught, 93% of +1/2 in (rounding: a value 0.25 in from the ruler step still
# rounds to the planted one). A drop below these floors means a check got looser.
FLOORS = {"length +1 in": 1.0, "length -1 in": 1.0, "length +1/2 in": 0.9, "length -1/2 in": 0.95,
          "left/right swapped": 1.0, "up/down swapped": 0.95, "edge moved": 1.0}


@lessons.slow
class FixtureTests(unittest.TestCase):
    """The three fixture lessons after draft-text: every claim in their Where lines passes (they're measured with
    the same measure as the sheet), and nothing in the drafted lines is flagged."""

    def test_fixtures(self):
        results = []
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
                results.append(vf.mutate(sheet, t))
        total = vf.add_up(results)
        for kind, floor in FLOORS.items():
            n, caught = total["where"][kind]
            self.assertGreaterEqual(caught / n, floor, f"{kind}: {caught}/{n}")


LAVENDER = Path(os.environ.get("GESSO_OUTPUT", vf.ROOT / "output")) / "balloon-lavender_skill_20261116-171639"


@lessons.slow
@unittest.skipUnless((LAVENDER / "text.json").exists(), "the sealed lavender run of #159 isn't in output/ here")
class SealedLavenderTests(unittest.TestCase):
    """The run #159 was found in, when it's on this machine (output/ isn't in the repo)."""

    def test_flags(self):
        """Exactly these flags: a new one is a new false alarm (or a new fault) and fails the test."""
        sheet, _plan = vf.lesson_sheet(LAVENDER)
        r = vf.check_text(sheet, json.loads((LAVENDER / "text.json").read_text(encoding="utf-8")))
        got = sorted((c["step"], c["kind"], c["words"]) for c in r["failures"])
        self.assertEqual(got, [
            (11, "fraction", "two-thirds in"),
            (20, "agree", "3 inches tall / 3 1/2 in tall"),
            (20, "agree", "about 2 1/2 inches wide / about 3 in wide"),
            (20, "length", "3 inches tall"),
            (20, "length", "about 2 1/2 inches wide"),
            (21, "center", "just left of the center"),
            (22, "relation", "just inside the left red stripe"),
            (22, "relation", "on its right")])
        self.assertEqual([p["step"] for p in r["paint_faults"]], [13])


if __name__ == "__main__":
    unittest.main()
