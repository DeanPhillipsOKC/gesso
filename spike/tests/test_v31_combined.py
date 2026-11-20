"""The combined v3.1 lesson's experiment (`pipeline-v3.1.md`, section 12): the three changes to the writer's brief,
and the count of lines over 40 words. No network, no Claude."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "experiments"))

import v31_combined as v  # noqa: E402
import v4_arc as arc  # noqa: E402
import v4_student as student  # noqa: E402
import v4_teacher as teacher  # noqa: E402
import v4_writer_cost as wc  # noqa: E402


class BriefTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        for target, attr, value in [(v, "RESULTS", Path(self.dir.name) / "r.json"), (wc, "RESULTS", wc.RESULTS),
                                    (wc, "WORK", Path(self.dir.name)), (teacher, "BRIEF", teacher.BRIEF),
                                    (teacher, "BENCH", teacher.BENCH), (teacher, "WORK", teacher.WORK),
                                    (arc, "BENCH", arc.BENCH), (student, "BENCH", student.BENCH)]:
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)
        for d in (teacher.FORM, wc.WORD_VARIANTS, wc.SETS):  # setup() adds to these, and wc.point moves the benches
            p = mock.patch.dict(d, dict(d))
            p.start()
            self.addCleanup(p.stop)

    def test_the_brief_gets_the_three_changes_once(self):
        v.setup()
        v.setup()  # a second command in one process changes nothing more
        b = teacher.brief("slots")
        self.assertEqual(b.count("**Where picture**"), 1)
        self.assertEqual(b.count("by their look and their step"), 1)
        self.assertNotIn("an earlier step's marks by their\n  paint", b)
        self.assertEqual(b.count("No line is over 40 words"), 1)
        self.assertIn("Name only the paints the step lists", b)

    def test_it_runs_the_lean_words_with_the_paint_check_on_its_own_results(self):
        v.setup()
        self.assertEqual(wc.WORD_VARIANTS[v.WORDS], wc.WORD_VARIANTS["lean-paints"])
        self.assertEqual(wc.RESULTS, v.RESULTS)
        self.assertEqual(wc.lessons("new"), {"sleeping-cat": v.LESSONS["sleeping-cat"][1]})
        self.assertEqual(set(wc.lessons("site")), {"chickadee", "balloon-lavender"})


class LongLinesTests(unittest.TestCase):
    def test_a_line_over_40_words_is_listed(self):
        rec = {"final": {"a": [{"kind": "start", "text": "word " * 40}, {"kind": "stop", "text": "word " * 41}]}}
        self.assertEqual(v.long_lines(rec), [("a", "stop", 41)])


if __name__ == "__main__":
    unittest.main()
