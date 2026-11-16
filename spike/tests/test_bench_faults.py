"""The fault counter's packets and its agreement with the owner (#165)."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "experiments" / "bench"))

import agreement  # noqa: E402
import packet  # noqa: E402
from test_bench import published  # noqa: E402

BRIEF = HERE.parent / "experiments" / "bench" / "fault_counter.md"


class PacketTests(unittest.TestCase):
    def test_a_packet_holds_what_a_painter_gets_and_nothing_that_names_the_run(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        one = published(tmp / "l", "chickadee", "chickadee_skill_20261116-100000")
        two = published(tmp / "l", "red-sailboat", "red-sailboat_skill_20261116-100000", steps=2)
        out = packet.build([one, two], tmp / "packets", seed=1)
        key = json.loads((tmp / "packets" / "key.json").read_text())
        self.assertEqual(sorted(key["packets"]), ["p01", "p02"])
        self.assertEqual(sorted(v["lesson"] for v in key["packets"].values()), sorted([one.name, two.name]))
        self.assertEqual(out["packets"], key["packets"])
        pid = next(k for k, v in key["packets"].items() if v["lesson"] == one.name)
        p = tmp / "packets" / pid
        names = sorted(str(f.relative_to(p)) for f in p.rglob("*") if f.is_file())
        self.assertEqual(names, ["finish.jpg", "lesson.md", "packet.json", "pairs/01.jpg", "pairs/02.jpg",
                                 "pairs/03.jpg", "photo.jpg", "steps/01.jpg", "steps/02.jpg", "steps/03.jpg"])
        for f in p.rglob("*"):
            if f.is_file():
                data = f.read_bytes()
                self.assertNotIn(one.name.encode(), data, f)
                self.assertNotIn(b"the plan", data, f)
        info = json.loads((p / "packet.json").read_text())
        self.assertEqual(info["canvas_in"], [16, 12])
        self.assertEqual(info["steps"][1]["lines"], ["Line one of step 2.", "Line two."])
        self.assertIn("- Warm gold (#e8a661): 3 parts white, 1 part yellow", (p / "lesson.md").read_text())

    def test_the_brief_defines_every_class_and_the_output(self):
        text = BRIEF.read_text(encoding="utf-8")
        for c, name in agreement.CLASSES.items():
            self.assertIn(f"### {c}. {name.capitalize()}", text)
        for word in ("faults.json", "same_as", "not_visible", "worst_steps", "blocker", "major", "minor"):
            self.assertIn(word, text)


def _result(steps: int, faults: dict[int, list[tuple[str, str]]], worst=()):
    return {"steps": [{"n": n, "id": f"s{n}", "faults": [{"id": f"f{n}{i}", "class": c, "severity": s}
                                                         for i, (c, s) in enumerate(faults.get(n, []))]}
                      for n in range(1, steps + 1)],
            "lesson_faults": [], "worst_steps": list(worst)}


class AgreementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        lessons = {"p01": "a_skill_1", "p02": "b_skill_1", "p03": "c_skill_1"}
        (self.tmp / "key.json").write_text(json.dumps(
            {"seed": 1, "packets": {p: {"lesson": l, "picture": l[0], "steps": 4} for p, l in lessons.items()}}))
        results = {"p01": _result(4, {2: [("A", "blocker")]}, [2]),
                   "p02": _result(4, {1: [("A", "minor")], 3: [("E", "major"), ("D", "major")]}, [3]),
                   "p03": _result(4, {})}
        for p, r in results.items():
            (self.tmp / p).mkdir()
            (self.tmp / p / "faults.json").write_text(json.dumps(r))

    def scores(self):
        def lesson(name, real, paintable, agree_, worst):
            return {"picture": name[0], "lessons": {"A": name},
                    "scores": {"A": {"real": real, "paintable": paintable, "agree": agree_,
                                     "worst_steps": [{"n": n} for n in worst], "would_paint": "yes", "note": ""}},
                    "prefer": None, "note": ""}
        return {"format": "gesso-ab-scores/1", "round": "t", "mode": "single", "seed": None,
                "pictures": [lesson("a_skill_1", 2, 4, 4, [2]), lesson("b_skill_1", 4, 2, 2, [3, 4]),
                             lesson("c_skill_1", 5, 5, 5, [])]}

    def test_not_scored_yet(self):
        r = agreement.agree(self.tmp, None)
        self.assertEqual(r["scored"], 0)
        self.assertTrue(all(v == agreement.NOT_SCORED for v in r["correlations"].values()))
        self.assertEqual(r["steps"], agreement.NOT_SCORED)
        self.assertEqual(r["lessons"]["a_skill_1"]["owner"], agreement.NOT_SCORED)
        self.assertEqual(r["lessons"]["b_skill_1"]["faults"]["weighted"], 5)
        self.assertIn(agreement.NOT_SCORED, agreement.table(r))

    def test_agreement_with_the_owner(self):
        r = agreement.agree(self.tmp, self.scores())
        self.assertEqual(r["scored"], 3)
        # fewest faults (c) scored best, most faults (b) worst on the mean
        self.assertEqual(r["correlations"]["all"]["rho"], 1.0)
        self.assertEqual(r["correlations"]["A"]["rho"], 1.0)  # a has the A blocker and the lowest "real"
        s = r["steps"]
        self.assertEqual((s["steps"], s["owner_worst"], s["counter_flagged"], s["both"]), (12, 3, 2, 2))
        self.assertEqual(s["agree"], 11)  # only b's step 4 differs
        self.assertEqual((s["recall"], s["precision"], s["owner_worst_in_counter_worst"]), (0.667, 1.0, 2))
        self.assertEqual(r["preference"], "single mode: no preferences to compare")

    def test_the_format_check(self):
        good = _result(2, {1: [("A", "major")]})
        good["steps"][0]["faults"][0].update(sees="a ghost", where="AFTER, x 10%", same_as=None)
        good["steps"][1]["faults"] = [{"id": "f2", "class": "A", "severity": "minor", "sees": "the same ghost",
                                       "where": "AFTER", "same_as": "f10"}]
        good.update(counts={"A": 2}, distinct={"A": 1}, not_visible={"G": "", "H": ""}, summary="s")
        self.assertEqual(agreement.check_faults(good, 2), [])
        bad = json.loads(json.dumps(good))
        bad["steps"][1]["faults"][0].update(id="f10", **{"class": "Z", "severity": "awful", "same_as": "nope"})
        bad["counts"] = {"A": 3}
        del bad["summary"]
        problems = agreement.check_faults(bad, 3)
        for words in ("no summary", "steps should be 1 to 3", "unique", "isn't A to H", "isn't blocker",
                      "names no fault", "counts"):
            self.assertTrue(any(words in p for p in problems), (words, problems))
        r = agreement.agree(self.tmp, None)  # the made-up results here have no sees/where/counts: all reported
        self.assertTrue(r["lessons"]["a_skill_1"]["faults"]["format_problems"])

    def test_spearman(self):
        self.assertEqual(agreement.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertEqual(agreement.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)
        self.assertIsNone(agreement.spearman([1, 2], [1, 2]))
        self.assertIsNone(agreement.spearman([1, 1, 1], [1, 2, 3]))
        self.assertEqual(agreement._rank([5, 1, 5]), [2.5, 1.0, 2.5])


if __name__ == "__main__":
    unittest.main()
