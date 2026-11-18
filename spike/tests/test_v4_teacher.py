"""The teacher spike (#254, v4's W1): the writer's words into checked lines, taking out what fails, the packets, and
the student test reading another lesson's words. No network."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "experiments"))
sys.path.insert(0, str(HERE.parent))

import v4_student as vs  # noqa: E402
import v4_teacher as vt  # noqa: E402


class Lines(unittest.TestCase):
    def test_free_prose_is_one_line_a_paragraph(self):
        got = vt.lines_of("free", {"words": ["Start at the top.", "  ", "Pull down."]})
        self.assertEqual([x["text"] for x in got], ["Start at the top.", "Pull down."])
        self.assertEqual(vt.page_lines("free", got), ["Start at the top.", "Pull down."])

    def test_slots_keep_their_order_and_labels_and_drop_an_empty_one(self):
        w = {"stop": "Stop when it's round.", "first": "", "start": "Start at the back.", "strokes": "Curve them.",
             "inside": "Under the belly.", "leave": "Leave the paws."}
        got = vt.lines_of("slots", w)
        self.assertEqual([x["kind"] for x in got], ["start", "strokes", "inside", "leave", "stop"])
        self.assertEqual(vt.page_lines("slots", got)[0], "Start: Start at the back.")
        self.assertEqual(vt.page_lines("slots", got)[-1], "Stop when: Stop when it's round.")

    def test_a_step_with_no_entry_has_no_lines(self):
        self.assertEqual(vt.lines_of("free", None), [])


class Checking(unittest.TestCase):
    """On the bench's sleeping cat, with its own sheet."""

    def words(self, sentence):
        text = vt.text_of("sleeping-cat", "free", {"shade-cat": {"words": ["Start at the fold.", sentence]}})
        return text, vt.check("sleeping-cat", text)

    def test_a_true_number_passes_and_a_false_one_fails(self):
        _, ok = self.words("Its bottom is about 3 3/4 in from the bottom edge.")
        _, bad = self.words("Its bottom is about 1/4 in from the bottom edge.")
        self.assertFalse(ok["failures"])
        self.assertTrue(bad["failures"])

    def test_take_out_removes_only_the_failing_sentence(self):
        text, r = self.words("Its bottom is about 1/4 in from the bottom edge. Keep it soft.")
        gone = vt.take_out(text, r["failures"])
        step = next(t for t in text["steps"] if t["stage_id"] == "shade-cat")
        self.assertEqual([x["text"] for x in step["lines"]], ["Start at the fold.", "Keep it soft."])
        self.assertEqual(len(gone), 1)
        self.assertFalse(vt.check("sleeping-cat", text)["failures"])

    def test_a_line_left_empty_goes(self):
        text, r = self.words("Its bottom is about 1/4 in from the bottom edge.")
        vt.take_out(text, r["failures"])
        step = next(t for t in text["steps"] if t["stage_id"] == "shade-cat")
        self.assertEqual(len(step["lines"]), 1)

    def test_kinds_sorts_unfound_from_wrong(self):
        self.assertEqual(vt.kinds([{"ok": None, "kind": "relation"}, {"ok": False, "kind": "length"},
                                   {"ok": False, "kind": "length"}]),
                         {"no such thing on the sheet": 1, "wrong length": 2})


class Message(unittest.TestCase):
    def test_a_stage_writer_gets_its_steps_pictures_and_cards(self):
        old = vt.WORK
        with tempfile.TemporaryDirectory() as d:
            vt.WORK = Path(d)
            try:
                from PIL import Image
                folder = vt.stages("sleeping-cat")[4]
                ns = [s["n"] for s in vt.stage_steps(folder)]
                pd = Path(d) / "pictures" / "sleeping-cat"
                pd.mkdir(parents=True)
                for n in ns:
                    for k in ("pair", "change"):
                        Image.new("RGB", (40, 30), "white").save(pd / f"{k}-{n:02d}.jpg")
                m = vt.writer_message("sleeping-cat", "slots", [folder])
            finally:
                vt.WORK = old
        text = "\n".join(b.get("text", "") for b in m.blocks)
        self.assertEqual(m.pictures, 2 * len(ns) + 2)
        self.assertIn("The form: a fixed set of lines", text)
        self.assertIn("## curved-strokes", text)
        self.assertIn("`shade-cat`", text)
        self.assertIn("Step 14 (shade-cat)", text)  # the stage's facts
        self.assertNotIn("`block-in-blanket`", text)  # another stage's step


class StudentReadsOtherWords(unittest.TestCase):
    def test_words_from_replaces_lines_and_tip_and_keeps_the_header(self):
        with tempfile.TemporaryDirectory() as d:
            les = vs.lesson("sleeping-cat")
            for s in les["steps"]:
                s["lines"], s["tip"] = [f"New words {s['n']}."], ""
            (Path(d) / "sleeping-cat").mkdir()
            (Path(d) / "sleeping-cat" / "packet.json").write_text(json.dumps(les))
            old = vs.WORDS_FROM
            vs.WORDS_FROM = Path(d)
            try:
                s = vs.step_of("sleeping-cat", 14)
            finally:
                vs.WORDS_FROM = old
        self.assertEqual(s["lines"], ["New words 14."])
        self.assertEqual(s["tip"], "")
        self.assertEqual(s["name"], "Shade the cat's shadow side")
        self.assertEqual(vs.step_of("sleeping-cat", 14)["lines"][0][:9], "Let the s")

    def test_other_results_keep_their_own_carry_folder_and_v3s_near_misses(self):
        old = (vs.RESULTS, vs._STATE)
        with tempfile.TemporaryDirectory() as d:
            try:
                vs.RESULTS, vs._STATE = Path(d) / "other.json", None
                self.assertEqual(vs.carry_dir().name, "carry-other")
                if vs.BASE_RESULTS.exists():
                    self.assertTrue(vs.state()["prepared"])
            finally:
                vs.RESULTS, vs._STATE = old
        self.assertEqual(vs.carry_dir().name, "carry")


if __name__ == "__main__":
    unittest.main()
