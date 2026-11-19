"""The arc spike (#255, v4's W2): the arc's checks, where a back line sits, taking out what fails, and the student
reading a stage opener above a step. On the bench's sleeping cat. No network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "experiments"))
sys.path.insert(0, str(HERE.parent))

import v4_arc as va  # noqa: E402
import v4_student as vs  # noqa: E402

CAT = "sleeping-cat"


def arc(**over):
    """A whole, passing arc for the cat, with `over` replacing its parts."""
    a = {"opening": {"skills": [{"card": "press-and-lift", "steps": [11, 12, 17], "how": "Press, then lift off."},
                                {"card": "curved-strokes", "steps": [14, 15], "how": "Bend every stroke round."}],
                     "road": "Far things first, then the cat."},
         "stages": {st["id"]: {"for": "This stage sets the scene.", "end": "It reads as a shape."}
                    for st in va.stages_of(CAT)},
         "steps": {}}
    a.update(over)
    return a


class Checks(unittest.TestCase):
    def test_a_whole_arc_passes(self):
        self.assertEqual(va.check_arc(CAT, arc()), [])

    def test_a_skill_must_be_a_card_the_lesson_uses_on_its_steps(self):
        a = arc()
        a["opening"]["skills"][0] = {"card": "liner", "steps": [20, 3], "how": "Thin lines."}
        a["opening"]["skills"][1]["card"] = "no-such-card"
        got = {c["where"]: c["what"] for c in va.check_arc(CAT, a)}
        self.assertIn("[3]", got["opening.skill 1"])
        self.assertIn("isn't a stroke card", [c["what"] for c in va.check_arc(CAT, a)
                                               if c["where"] == "opening.skill 2"][0])

    def test_one_skill_is_too_few(self):
        a = arc()
        a["opening"]["skills"] = a["opening"]["skills"][:1]
        self.assertEqual([c["where"] for c in va.check_arc(CAT, a)], ["opening.skills"])

    def test_an_opener_says_no_number_and_no_side(self):
        a = arc()
        a["opening"]["road"] = "Far things first. The window is on the left side."
        a["stages"]["the-sill"]["end"] = "The sill is about 2 in tall."
        got = [(c["where"], c["sentence"]) for c in va.check_arc(CAT, a)]
        self.assertEqual(got, [("opening.road", "The window is on the left side."),
                               ("stage the-sill.end", "The sill is about 2 in tall.")])

    def test_a_back_line_must_share_a_card_or_a_paint_with_an_earlier_step(self):
        ok = arc(steps={"dab-sunlit-leaves": {"back": {"step": 2, "text": "The same tap as the dark leaves."}},
                        "light-sill": {"back": {"step": 7, "text": "The same brown."}}})
        self.assertEqual(va.check_arc(CAT, ok), [])
        bad = arc(steps={"dab-sunlit-leaves": {"back": {"step": 1, "text": "Like the sky."}},
                         "dab-dark-leaves": {"back": {"step": 3, "text": "Like the next one."}}})
        got = {c["where"]: c["what"] for c in va.check_arc(CAT, bad)}
        self.assertIn("shares neither", got["step dab-sunlit-leaves.back"])
        self.assertIn("isn't an earlier step", got["step dab-dark-leaves.back"])


class Lines(unittest.TestCase):
    def test_a_back_line_sits_after_first_and_start(self):
        slots = [{"kind": "first", "text": "Let it dry."}, {"kind": "start", "text": "Start at the top."},
                 {"kind": "strokes", "text": "Tap."}]
        got = va.step_lines(slots, {"step": 2, "text": "The same tap."})
        self.assertEqual([x["kind"] for x in got], ["first", "start", "back", "strokes"])
        self.assertEqual(va.page_lines(got)[2], "As in step 2: The same tap.")
        self.assertEqual(va.page_lines(got)[3], "Strokes: Tap.")

    def test_arc_add_keeps_the_teachers_lines(self):
        a = arc(steps={"dab-sunlit-leaves": {"back": {"step": 2, "text": "The same tap."}}})
        got = va.compose(CAT, "arc-add", a)
        base = va.base_words(CAT)
        self.assertEqual([x for x in got["dab-sunlit-leaves"] if x["kind"] != "back"], base["dab-sunlit-leaves"])
        self.assertEqual(got["blend-window-sky"], base["blend-window-sky"])

    def test_the_back_line_is_checked_by_check_text(self):
        a = arc(steps={"dab-sunlit-leaves": {"back": {"step": 2, "text": "Its top is about 1/4 in from the bottom "
                                                                         "edge."}}})
        r = va.teacher.check(CAT, va.text_for_check(CAT, va.compose(CAT, "arc-add", a)))
        self.assertTrue(any("(back)" in c["field"] for c in r["failures"]))


class TakingOut(unittest.TestCase):
    def test_what_still_fails_goes_and_the_rest_stays(self):
        a = arc(steps={"dab-sunlit-leaves": {"back": {"step": 1, "text": "Like the sky."}}})
        a["opening"]["road"] = "Far things first. The window is on the left side."
        a["opening"]["skills"].append({"card": "no-such-card", "steps": [1], "how": "x"})
        gone = va.take_out_arc(a, va.check_arc(CAT, a))
        self.assertEqual(a["opening"]["road"], "Far things first.")
        self.assertEqual([s["card"] for s in a["opening"]["skills"]], ["press-and-lift", "curved-strokes"])
        self.assertNotIn("back", a["steps"]["dab-sunlit-leaves"])
        self.assertEqual(va.check_arc(CAT, a), [])
        self.assertEqual(len(gone), 4)


class Long(unittest.TestCase):
    """arc-add-long (the owner's ask, 2026-11-19): a welcome and a light line, held to the opening's rules."""

    def test_the_welcome_and_the_light_say_no_number_and_no_side(self):
        a = arc()
        a["opening"]["welcome"] = "A sleeping cat in soft light. It is about 7 in wide."
        a["opening"]["light"] = "The window light falls on the left side of the head."
        got = [(c["where"], c["sentence"]) for c in va.check_arc(CAT, a)]
        self.assertEqual(got, [("opening.welcome", "It is about 7 in wide."),
                               ("opening.light", "The window light falls on the left side of the head.")])
        va.take_out_arc(a, va.check_arc(CAT, a))
        self.assertEqual(a["opening"]["welcome"], "A sleeping cat in soft light.")
        self.assertEqual(a["opening"]["light"], "")

    def test_the_opening_shows_the_welcome_and_the_light_first(self):
        a = arc()
        a["opening"]["welcome"] = "A sleeping cat."
        a["opening"]["light"] = "The window light."
        text = va.opening_text(a)
        self.assertTrue(text.startswith("A sleeping cat."))
        self.assertLess(text.index("The light: The window light."), text.index("What this painting teaches:"))

    def test_the_long_brief_carries_the_ask(self):
        self.assertIn("More steps point back", va.add_brief(True))
        self.assertNotIn("More steps point back", va.add_brief())


class Student(unittest.TestCase):
    def test_a_stage_opener_is_said_above_the_step(self):
        s = {"n": 4, "name": "Blend the wall", "lines": ["Start: at the top."], "intro": "This stage, the wall: ..."}
        text = vs.step_text(s, (10, 8), 21)
        self.assertLess(text.index("This stage, the wall"), text.index("Step 4: Blend the wall"))
        self.assertNotIn("This stage", vs.step_text({**s, "intro": ""}, (10, 8), 21))


if __name__ == "__main__":
    unittest.main()
