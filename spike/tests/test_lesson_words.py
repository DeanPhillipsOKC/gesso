"""The lesson's words, pipeline v3.1 (spike/lesson_words.py, #276): the pieces that need no lesson folder. The
rounds on a lesson are test_steps3's V3ToolsTests (the made-up scene, a stand-in writer through every round and the
arc's) and the fixtures' `worded` stage (tests/lessons.py)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import facts  # noqa: E402
import lesson_words as lw  # noqa: E402

LES = {"steps": [{"n": 1, "id": "sky", "stroke": "side-to-side-blend", "paints": ["Sky blue"]},
                 {"n": 2, "id": "rug", "stroke": "build-from-pieces", "paints": ["Rug red"]},
                 {"n": 3, "id": "cat", "stroke": "build-from-pieces", "paints": ["Cat gray"]},
                 {"n": 4, "id": "eyes", "stroke": "dotting", "paints": ["Rug red"]}],
       "stages": [{"id": "back", "steps": []}, {"id": "front", "steps": []}]}


def arc(**more) -> dict:
    a = {"opening": {"welcome": "A cat.", "light": "Window light.", "road": "Back to front.",
                     "skills": [{"card": "build-from-pieces", "steps": [2, 3], "how": "Flat pieces."},
                                {"card": "dotting", "steps": [4], "how": "Small dots."}]},
         "stages": {"back": {"for": "The back.", "end": "Done."}, "front": {"for": "The front.", "end": "Done."}},
         "steps": {}}
    a.update(more)
    return a


class LeanFactsTests(unittest.TestCase):
    def test_lean_cuts_what_the_lines_dont_use(self):
        text = "\n".join(["## Step 1 (sky): Blend the sky",
                          "Where line (kept as it is, word for word): Inside the outlined area.",
                          "This step's area: its left side 1/4 in (5/16) from the left edge; 3 in (2 15/16) wide.",
                          "The sky as the finish shows it: its left side 0 in (0) from the left edge.",
                          "mark 1: middle 2 in (2 1/16) from the left edge (0.25 of the way across The sky, 0.10 down)",
                          "Next to it: above The rug, touching; beside The cat (not painted yet)."])
        self.assertEqual(facts.lean(text).splitlines(), [
            "## Step 1 (sky): Blend the sky",
            "This step's area: its left side 1/4 in from the left edge; 3 in wide.",
            "mark 1: middle 2 in from the left edge (0.25 of the way across The sky, 0.10 down)",
            "Next to it: above The rug, touching."])
        self.assertEqual(facts.lean("Next to it: beside The cat (not painted yet)."), "")


class ArcTests(unittest.TestCase):
    def test_a_good_arc_passes(self):
        a = arc(steps={"cat": {"back": {"step": 2, "text": "The same pieces as the rug."}},
                       "eyes": {"back": {"step": 2, "text": "The rug's red again."}}})  # a shared paint
        self.assertEqual(lw.check_arc(LES, a), [])

    def test_each_check(self):
        a = arc(steps={"cat": {"back": {"step": 1, "text": "Like the sky."}},
                       "rug": {"back": {"step": 3, "text": "Like the cat."}},
                       "nope": {"back": {"step": 1, "text": "x"}},
                       "eyes": {"back": "the rug"}})
        a["opening"]["skills"] = [{"card": "glazing", "steps": [1], "how": "Thin, about 2 in wide."}]
        a["opening"]["light"] = "From the upper left."
        a["stages"]["front"] = {"for": "The cat beside the rug."}
        got = {(c["where"], c["what"].split(":")[0]) for c in lw.check_arc(LES, a)}
        for want in [("opening.skills", "two or three skills, not 1"),
                     ("opening.skill 1", "`glazing` isn't a stroke card this lesson uses"),
                     ("opening.skill 1", "steps [1] don't use the card `glazing`"),
                     ("opening.skill 1", "the opening and a stage's lines say no number and no side word"),
                     ("opening.light", "the opening and a stage's lines say no number and no side word"),
                     ("stage front.for", "the opening and a stage's lines say no number and no side word"),
                     ("stage front.end", "missing"),
                     ("step cat.back", "step 1 shares neither this step's stroke card (build-from-pieces) nor a paint "
                                       "(Cat gray)"),
                     ("step rug.back", "step 3 isn't an earlier step"),
                     ("step nope.back", "there is no step nope")]:
            self.assertIn(want, got)
        self.assertTrue(any(w == "step eyes.back" for w, _ in got))  # not {step, text}

    def test_what_fails_is_taken_out_and_nothing_else(self):
        a = arc(steps={"cat": {"back": {"step": 1, "text": "Like the sky."}},
                       "eyes": {"back": {"step": 2, "text": "The rug's red."}}})
        a["opening"]["road"] = "Back to front. Finish on the left side."
        gone = lw.take_out_arc(a, lw.check_arc(LES, a))
        self.assertEqual(len(gone), 2)
        self.assertEqual(a["opening"]["road"], "Back to front.")
        self.assertNotIn("back", a["steps"]["cat"])
        self.assertEqual(a["steps"]["eyes"]["back"]["step"], 2)
        self.assertEqual(lw.check_arc(LES, a), [])

    def test_a_back_line_goes_before_the_strokes(self):
        lines = [{"kind": k, "text": k} for k in ("first", "start", "strokes", "stop")]
        got = lw.with_back(lines, {"step": 2, "text": "x"})
        self.assertEqual([x["kind"] for x in got], ["first", "start", "back", "strokes", "stop"])
        self.assertEqual(lw.with_back(got, None), lines)  # an old back line goes when the arc has none
        self.assertEqual([x["kind"] for x in lw.with_back(lines[:2], {"step": 1, "text": "x"})],
                         ["first", "start", "back"])

    def test_has_claim(self):
        for s in ("It sits under the eaves.", "About 3 in.", "Two inches across.", "The upper branches."):
            self.assertTrue(lw.has_claim(s), s)
        for s in ("The window light warms the cat.", "Paint the sky first."):
            self.assertFalse(lw.has_claim(s), s)


class WordsTests(unittest.TestCase):
    def test_a_fix_lays_its_steps_on_out_json_and_what_cant_be_used_is_said(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "out.json").write_text(json.dumps({"steps": {
                "sky": {"first": "", "start": "a", "strokes": "b", "inside": "c", "leave": "d", "stop": "e"},
                "rug": {"start": "a", "summary": "no", "stop": 3}, "nope": {}}}))
            (d / "fix-1.json").write_text(json.dumps({"steps": {"sky": {"inside": "c2"}}}))
            (d / "fix-10.json").write_text(json.dumps({"steps": {"sky": {"inside": "c10"}}}))
            (d / "fix-2.json").write_text("{bad")
            words, bad = lw.words_of(d, ["sky", "rug"])
            self.assertEqual(words["sky"]["inside"], "c10")  # in the rounds' order: 1, 2, 10
            self.assertEqual([x["kind"] for x in lw.lines_of(words["sky"])],
                             ["start", "strokes", "inside", "leave", "stop"])
            self.assertTrue(any("no step nope" in x for x in bad))
            self.assertTrue(any("`summary`, which isn't one of the lines" in x for x in bad))
            self.assertTrue(any("rug's stop must be text" in x for x in bad))
            self.assertTrue(any("fix-2.json isn't valid JSON" in x for x in bad))
            self.assertEqual(lw.unwritten({"steps": [{"n": 1, "id": "sky"}, {"n": 2, "id": "rug"}]}, words),
                             ["step 2 (rug) has no `strokes`, `inside`, `leave`, `stop` line"])


if __name__ == "__main__":
    unittest.main()
