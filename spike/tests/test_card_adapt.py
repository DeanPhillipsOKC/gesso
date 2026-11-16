"""Stroke cards adapted for one painting (#96): `card-adapt`, the drift checks, the page, and generic general cards.

A general card is shown on whatever is being painted, so it says only the technique; a lesson's own copy, in
text.json's card_text, swaps in the subject's words, paints, and shape, and `check` keeps it to the card's technique.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cards  # noqa: E402
import lessons  # noqa: E402
import page2  # noqa: E402
from lessons import fixture, run_tool  # noqa: E402

PAINTS = {"Sun yellow": "#f2c14e", "Sky blue": "#7fa7d9"}


def sun_copy() -> dict:
    """The small-circles card adapted for a plain round sun: only the words, the paints, and the shape changed."""
    a = cards.adapt(cards.strokes()["small-circles"])
    a["motion"] = ("Small circles with the tip of the brush make the round edge of the sun. Keep the circles moving "
                   "outward from it, into the sky.")
    a["result"] = "A soft, round edge on the sun."
    a["then"] = "Smooth with the same circular motion, and put the lighter yellow only on the side facing the light."
    a["mistakes"][0]["fix"] = "Soften the sun's edge with lighter passes. Smudging with a finger works too."
    d = a["diagram"]
    d["title"] = "Little circles around the sun"
    d["stages"][0]["add"] = [{"rect": [4, 4, 92, 92], "paint": "Sky blue", "done": True, "round": 4},
                             {"circle": [50, 50, 22], "paint": "Sun yellow"}]
    d["stages"][1]["add"] = [{"circle": [50, 50, 26], "paint": "Sun yellow", "behind": True}]
    d["stages"][1]["caption"] = "Soften the edge into the sky"
    return a


class GeneralCardTests(unittest.TestCase):
    def test_a_general_card_naming_a_subject_is_a_problem_and_the_set_is_clean(self):
        self.assertEqual([p for p in cards.problems() if "names a subject" in p], [])
        card = copy.deepcopy(cards.strokes()["small-circles"])
        card["motion"] = "Small circles with the tip of the brush make a cloud's bumpy top edge."
        wrong = cards.problems({"small-circles": card}, {}, [card["stroke_result"]])
        self.assertTrue(any("small-circles" in p and "motion names a subject (cloud)" in p for p in wrong), wrong)
        card = copy.deepcopy(cards.strokes()["liner"])  # "Add water." is the material, not a subject
        self.assertEqual(cards.problems({"liner": card}, {}, [card["stroke_result"]]), [])
        card["mistakes"][0]["fix"] = "Thin it, then paint the grass."
        self.assertIn("mistake 1 names a subject (grass)", " | ".join(cards.problems({"liner": card}, {},
                                                                                     [card["stroke_result"]])))

    def test_a_basics_card_naming_a_subject_is_a_problem_but_rinse_water_isnt(self):
        good = {"id": "x", "name": "X", "when": "start", "lines": ["Two water jars, and keep the water clean."],
                "sources": ["s"], "checked": False}
        self.assertEqual(cards.problems({}, {"x": good}, []), [])
        self.assertIn("names a subject (sky)", " | ".join(cards.problems({}, {"x": {**good, "lines": ["Paint the sky."]}}, [])))

    def test_every_card_keeps_its_sources_and_the_subjects_are_in_uses(self):
        known = cards.strokes()
        self.assertEqual(len(known), 28)
        self.assertTrue(all(c.get("sources") for c in known.values()))
        self.assertIn("cloud tops", known["small-circles"]["uses"])


class CardAdaptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lesson = Path(self.tmp.name) / "chickadee"
        self.lesson.mkdir()
        (self.lesson / "plan.json").write_text(json.dumps(fixture("chickadee")[1]), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def text(self) -> dict:
        return json.loads((self.lesson / "text.json").read_text(encoding="utf-8"))

    def test_card_adapt_copies_each_opened_card_and_keeps_edits_on_a_second_run(self):
        code, r = run_tool("card-adapt", "--lesson", str(self.lesson))
        self.assertEqual(code, 0, r)
        ct = self.text()["card_text"]
        plan = fixture("chickadee")[1]
        steps = [s for st in plan["stages"] for s in st["steps"]]
        want = cards.opened(steps)
        self.assertEqual(sorted(f"{s}.{c}" for s, c in want), sorted(r["added"]))
        self.assertEqual({(s, c) for s in ct for c in ct[s]}, set(want))
        card = cards.strokes()["small-circles"]
        sun = ct["sun"]["small-circles"]  # the chickadee's sun step opens the small-circles card
        self.assertEqual(sun["from"], "small-circles")
        for k in ("motion", "result", "then", "mistakes", "diagram"):
            self.assertEqual(sun[k], card[k], k)
        self.assertEqual(set(sun), {"motion", "result", "then", "mistakes", "diagram", "from"})
        # a later step with the same stroke links back to the first: no copy of its own
        self.assertNotIn("branch-mid", ct)
        # the run edits the copy; card-adapt again keeps it
        text = self.text()
        text["card_text"]["sun"]["small-circles"] = sun_copy()
        text["steps"] = [{"stage_id": "sun", "summary": "kept"}]
        (self.lesson / "text.json").write_text(json.dumps(text), encoding="utf-8")
        code, r = run_tool("card-adapt", "--lesson", str(self.lesson))
        self.assertEqual((code, r["added"]), (0, []))
        self.assertIn("sun.small-circles", r["kept"])
        again = self.text()
        self.assertEqual(again["card_text"]["sun"]["small-circles"], sun_copy())
        self.assertEqual(again["steps"], [{"stage_id": "sun", "summary": "kept"}])


class DriftTests(unittest.TestCase):
    def steps(self):
        return [{"id": "sun", "stroke": "small-circles"}, {"id": "sun-2", "stroke": "small-circles"},
                {"id": "chest", "stroke": "curved-strokes"}]

    def check(self, mine: dict | None):
        ct = {"sun": {"small-circles": mine}} if mine is not None else {}
        return cards.adapted_problems(ct, self.steps(), cards.strokes(), PAINTS)

    def test_one_that_changed_only_wording_and_paints_passes(self):
        fails, notes = self.check(sun_copy())
        self.assertEqual(fails, [])
        self.assertEqual(len(notes), 1)  # curved-strokes, opened by chest, shows the general card
        self.assertIn("chest opens the curved-strokes card", notes[0])

    def test_a_card_opened_with_no_copy_is_a_note_not_a_failure(self):
        fails, notes = self.check(None)
        self.assertEqual(fails, [])
        self.assertEqual(len(notes), 2)
        self.assertIn("card-adapt", notes[0])

    def test_drift_from_the_card_is_a_failure_saying_what_to_put_back(self):
        extra = sun_copy()
        extra["mistakes"].append({"mistake": "The sun looks flat.", "fix": "Add a glow."})
        missing = sun_copy()
        missing.pop("then")
        added = {**sun_copy(), "practice": "Try it on scrap paper."}
        brush = sun_copy()
        brush["motion"] = "Tap small circles with a fan brush around the sun."
        stages = sun_copy()
        stages["diagram"]["stages"].append({"caption": "More", "add": [{"circle": [50, 50, 5], "paint": "Sun yellow"}]})
        arrows = sun_copy()
        arrows["diagram"]["stages"][0]["arrows"] = []
        other = {**sun_copy(), "from": "dabbing"}
        for mine, expect in ((extra, "has 2 mistakes; the small-circles card has 1"),
                             (missing, "has no then. Put back"), (added, "has a practice the small-circles card hasn't"),
                             (brush, "names a brush the small-circles card doesn't use (fan)"),
                             (stages, "its diagram has 3 stages; the card's has 2"),
                             (arrows, "panel 1 has 0 arrows; the card's has 1"), (other, "its from is 'dabbing'")):
            fails, _ = self.check(mine)
            self.assertTrue(any(expect in f for f in fails), (expect, fails))
            self.assertTrue(all(f.startswith("card_text.sun.small-circles: ") for f in fails), fails)

    def test_a_dropped_mistake_passes_and_a_copy_for_a_step_that_doesnt_open_the_card_fails(self):
        dropped = sun_copy()
        dropped["mistakes"] = []
        self.assertEqual(self.check(dropped)[0], [])
        fails, _ = cards.adapted_problems({"sun-2": {"small-circles": sun_copy()}}, self.steps(), cards.strokes(), PAINTS)
        self.assertIn("step sun-2 doesn't open the small-circles card", " | ".join(fails))

    def test_a_diagram_paint_that_isnt_the_lessons_is_reported(self):
        bad = sun_copy()
        bad["diagram"]["stages"][0]["add"][1]["paint"] = "Moon white"
        self.assertIn("draws gray", " | ".join(self.check(bad)[0]))


def lesson_with(card_text: dict | None = None, closeup: bool = False, construct: bool = False) -> dict:
    steps = [{"id": "sun", "name": "Paint the sun", "part": "sun", "stroke_cards": ["small-circles"], "aids": {}},
             {"id": "sun-2", "name": "Glow", "part": "sun", "stroke_cards": ["small-circles"], "aids": {}}]
    if card_text:
        steps[0]["card_text"] = card_text
    if closeup:
        steps[0]["aids"] = {"closeup": {"box": [100, 50, 300, 250], "before": "aids/01_sun_before.jpg",
                                        "after": "aids/01_sun_after.jpg"}, "area": 0.02}
    if construct:
        steps[1]["construct"] = {"stages": [{"caption": "A circle", "add": [{"circle": [50, 50, 20]}]}]}
    return {"stages": steps}


class PageTests(unittest.TestCase):
    def fold(self, lesson: dict, i: int = 0) -> str:
        return page2.stroke_folds(lesson, i, cards.strokes(), Path("."), False, PAINTS)

    def test_a_step_with_an_adapted_card_shows_it_with_the_adapted_line_and_a_link_to_the_general_card(self):
        html = self.fold(lesson_with({"small-circles": sun_copy()}))
        self.assertIn("Adapted for this painting from the Small circles card, not checked yet", html)
        self.assertIn("the round edge of the sun", html)
        self.assertIn("href='#general-small-circles'", html)
        self.assertIn('id="general-small-circles"', html)  # the general card, folded under it
        self.assertIn("make a bumpy edge", html)
        self.assertIn("techniques/strokes/small-circles.yaml", html)
        self.assertEqual(html.count("id='stroke-small-circles'"), 1)
        self.assertIn("#f2c14e", html)  # the adapted diagram in the lesson's own paints, by name

    def test_an_unedited_copy_shows_as_the_general_card_and_check_notes_it(self):
        copy_ = cards.adapt(cards.strokes()["small-circles"])
        self.assertNotIn("Adapted for this painting", self.fold(lesson_with({"small-circles": copy_})))
        fails, notes = cards.adapted_problems({"sun": {"small-circles": copy_}}, [{"id": "sun", "stroke": "small-circles"}],
                                              cards.strokes(), PAINTS)
        self.assertEqual(fails, [])
        self.assertIn("still the general card word for word", " | ".join(notes))

    def test_a_step_without_one_shows_the_general_card(self):
        html = self.fold(lesson_with())
        self.assertNotIn("Adapted for this painting", html)
        self.assertIn("make a bumpy edge", html)
        self.assertIn("id='stroke-small-circles'", html)
        later = self.fold(lesson_with({"small-circles": sun_copy()}), 1)  # a later use links back
        self.assertIn('href="#stroke-small-circles"', later)
        self.assertNotIn("Adapted", later)

    def test_the_card_fold_shows_the_steps_close_up_as_here_and_points_at_its_diagram(self):
        html = self.fold(lesson_with({"small-circles": sun_copy()}, closeup=True, construct=True))
        self.assertIn("<figcaption><b>Here</b>", html)
        self.assertIn('href="aids/01_sun_after.jpg"', html)
        self.assertIn('viewBox="100 50 200 200"', html)
        self.assertLess(html.index("<b>Here</b>"), html.index("class=\"build\""))  # beside the card's diagram
        self.assertIn('the Diagram in <a href="#step-2">step 2</a>', html)
        plain = self.fold(lesson_with(closeup=True))
        self.assertIn("<b>Here</b>", plain)  # the general card gets the close-up too
        self.assertNotIn("<b>Here</b>", self.fold(lesson_with()))


@lessons.slow
class LessonTests(unittest.TestCase):
    """card-adapt, check, and publish on a fixture lesson."""

    def test_check_and_the_page_on_a_fixture_with_one_adapted_card(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"GESSO_HISTORY": str(Path(tmp) / "h")}):
            lesson = lessons.lesson("chickadee", "checked", Path(tmp))
            code, r = run_tool("check", "--lesson", str(lesson))
            self.assertTrue(any("opens the small-circles card with no copy" in n for n in r["notes"]), r["notes"])
            self.assertEqual(run_tool("card-adapt", "--lesson", str(lesson))[0], 0)
            text = json.loads((lesson / "text.json").read_text(encoding="utf-8"))
            mine = sun_copy()
            plan = json.loads((lesson / "plan.json").read_text(encoding="utf-8"))
            sun = next(s for st in plan["stages"] for s in st["steps"] if s["id"] == "sun")
            name = {p["id"]: p.get("name") or p["id"] for p in plan["paints"]}[sun["paints"][0]]
            for st in mine["diagram"]["stages"]:
                for sh in st["add"]:
                    sh["paint"] = name
            text["card_text"]["sun"]["small-circles"] = mine
            extra = copy.deepcopy(text["card_text"]["sun"]["small-circles"])
            (lesson / "text.json").write_text(json.dumps(text), encoding="utf-8")
            _, r = run_tool("check", "--lesson", str(lesson))
            self.assertFalse([f for f in r["problems"] if "card_text" in f], r["problems"])
            self.assertFalse(any("small-circles card with no copy" in n for n in r["notes"]))
            extra["mistakes"].append({"mistake": "x", "fix": "y"})
            text["card_text"]["sun"]["small-circles"] = extra
            (lesson / "text.json").write_text(json.dumps(text), encoding="utf-8")
            _, r = run_tool("check", "--lesson", str(lesson))
            self.assertTrue(any("card_text.sun.small-circles: has 2 mistakes" in f for f in r["problems"]))
            text["card_text"]["sun"]["small-circles"] = mine
            (lesson / "text.json").write_text(json.dumps(text), encoding="utf-8")
            code, r = run_tool("publish", "--lesson", str(lesson))
            self.assertEqual(code, 0, r)
            data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
            sun_stage = next(s for s in data["stages"] if s["id"] == "sun")
            self.assertEqual(sun_stage["card_text"]["small-circles"]["result"], "A soft, round edge on the sun.")
            html = (lesson / "lesson-standalone.html").read_text(encoding="utf-8")
            self.assertIn("Adapted for this painting from the Small circles card", html)


if __name__ == "__main__":
    unittest.main()
