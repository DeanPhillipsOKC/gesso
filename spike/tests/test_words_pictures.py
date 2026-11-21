"""Words belong to their pictures (pipeline v4, section 8; #298).

`packets` records what the step pictures were made from (build.json's `made_from`, and whether it has `stops`) in
words/lesson/pictures.json, and check-text --final keeps it as what the words were written for. `check-text` and
`check` refuse words written for other pictures. First the comparison on its own, then (slow) a fixture lesson whose
words were written before its step pictures were rebuilt with --stops: refused by both, and passing again after
`packets` and a stand-in writer. Then `check` on that lesson holds the build's two checks and carries its note.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import lessons  # noqa: E402
import lesson_words  # noqa: E402

PLAIN = {"made_from": "abc", "stops": False}
RULED = {"made_from": "def", "stops": True}


class OtherPicturesTests(unittest.TestCase):
    def test_the_same_pictures(self):
        self.assertIsNone(lesson_words.other_pictures(PLAIN, dict(PLAIN)))
        self.assertIsNone(lesson_words.other_pictures(RULED, dict(RULED)))

    def test_built_the_other_way(self):
        self.assertIn("with --stops", lesson_words.other_pictures(PLAIN, RULED))
        self.assertIn("without --stops", lesson_words.other_pictures(RULED, PLAIN))

    def test_made_again(self):
        self.assertIn("changed plan, chain or canvas",
                      lesson_words.other_pictures(PLAIN, {"made_from": "xyz", "stops": False}))

    def test_a_record_from_before_it(self):
        """Words checked before the record (a v3.1 lesson) stand while the lesson has no rule, and not with it."""
        self.assertIsNone(lesson_words.other_pictures(None, PLAIN))
        self.assertIn("with --stops", lesson_words.other_pictures(None, RULED))

    def test_no_pictures(self):
        self.assertIsNone(lesson_words.other_pictures(PLAIN, None))


def _check(lesson: Path) -> dict:
    code, r = lessons.run_tool("check", "--lesson", str(lesson))
    assert code == 0, r
    return r


def _about_pictures(failures: list[str]) -> list[str]:
    return [f for f in failures if "other step pictures" in f or "no last check of them" in f]


@lessons.slow
class RebuiltTests(unittest.TestCase):
    """The lavender balloon (the one fixture where a layer stops), worded without the rule, then rebuilt with it."""

    def test_old_words_are_refused_until_written_again(self):
        lesson = lessons.lesson("lavender-balloon", "worded")
        folder = lesson_words.folder_of(lesson)
        record = json.loads((folder / lesson_words.PICTURES).read_text(encoding="utf-8"))
        self.assertEqual(record["stops"], False)
        self.assertEqual(record, lesson_words.pictures_of(lesson))
        self.assertEqual(json.loads((folder / "rounds.json").read_text(encoding="utf-8"))["final"]["pictures"],
                         record)
        self.assertEqual(_about_pictures(_check(lesson)["failures"]), [])

        for tool in (("build-steps", "--stops"), ("step-aids",), ("mix",), ("draft-text",)):
            code, out = lessons.run_tool(tool[0], "--lesson", str(lesson), *tool[1:])
            self.assertEqual(code, 0, (tool, out))
        self.assertTrue(lesson_words.pictures_of(lesson)["stops"])

        # check-text refuses the old folder, each round and the arc
        for args in ((), ("--final",), ("--arc",), ("--arc", "--final")):
            code, out = lessons.run_tool("check-text", "--lesson", str(lesson), *args)
            self.assertIn("refused", out, args)
            self.assertIn("built with --stops since packets ran", out["refused"])
            self.assertIn("run packets, then the lesson's writer again", out["refused"])
        # check refuses the words text.json still holds (no number in them has to be wrong for it)
        said = _about_pictures(_check(lesson)["failures"])
        self.assertEqual(len(said), 1, said)
        self.assertIn("written for other step pictures (the step pictures were built with --stops since they "
                      "were)", said[0])

        # packets alone isn't enough: text.json still holds the words written for the old pictures
        code, out = lessons.run_tool("packets", "--lesson", str(lesson))
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads((folder / lesson_words.PICTURES).read_text(encoding="utf-8")),
                         lesson_words.pictures_of(lesson))
        said = _about_pictures(_check(lesson)["failures"])
        self.assertEqual(len(said), 1, said)
        self.assertIn("no last check of them", said[0])

        # the writer again (a stand-in) and its rounds: both pass
        lessons.words_into("lavender-balloon", lesson)
        self.assertEqual(_about_pictures(_check(lesson)["failures"]), [])
        code, out = lessons.run_tool("check-text", "--lesson", str(lesson), "--arc", "--final")
        self.assertNotIn("refused", out)

        # built again without the rule: the new words are refused the other way
        code, out = lessons.run_tool("build-steps", "--lesson", str(lesson))
        self.assertEqual(code, 0, out)
        code, out = lessons.run_tool("check-text", "--lesson", str(lesson))
        self.assertIn("built without --stops since packets ran", out["refused"])

    def test_check_holds_the_builds_checks_and_note(self):
        """`check` reads build.json as build-steps --stops left it: checks 1 and 2 (measured on the second laying)
        fail it, and the rule's note is one of its notes."""
        lesson = lessons.lesson("lavender-balloon", "chained")
        for tool in (("build-steps", "--stops"), ("step-aids",), ("mix",), ("draft-text",)):
            code, out = lessons.run_tool(tool[0], "--lesson", str(lesson), *tool[1:])
            self.assertEqual(code, 0, (tool, out))
        path = lesson / "v3" / "build.json"
        build = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("stops", build)
        self.assertLessEqual(build["final_gap"], 0.0005)
        self.assertLessEqual(build["outside_unit_max"], 0.0005)
        r = _check(lesson)
        self.assertFalse([f for f in r["failures"] if "isn't the finish" in f or "outside what its unit" in f])
        build.update(final_gap=0.01, stop_notes=["a planted note on a stopped layer"])
        path.write_text(json.dumps(build), encoding="utf-8")
        r = _check(lesson)
        self.assertTrue([f for f in r["failures"] if "isn't the finish (1.00% of it differs)" in f], r["failures"])
        self.assertIn("a planted note on a stopped layer", r["notes"])


if __name__ == "__main__":
    unittest.main()
