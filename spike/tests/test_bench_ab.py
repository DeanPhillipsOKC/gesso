"""The blind A/B page and its scores (#165)."""

from __future__ import annotations

import base64
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "experiments" / "bench"))

import ab_page  # noqa: E402
from test_bench import published  # noqa: E402


def _key(html: str) -> dict:
    m = re.search(r'<script type="text/plain" id="key">([^<]+)</script>', html)
    return json.loads(base64.b64decode(m.group(1)))


def _visible(html: str) -> str:
    """The page without its encoded answer key."""
    return re.sub(r'<script type="text/plain" id="key">[^<]+</script>', "", html)


class ABPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_single_mode_page(self):
        lessons = [published(self.tmp / "a", "chickadee", "chickadee_skill_20261116-100000"),
                   published(self.tmp / "a", "red-sailboat", "red-sailboat_skill_20261116-100000", steps=2)]
        plan = ab_page.plan_round("baseline-test", lessons=lessons)
        out = ab_page.make(plan, self.tmp / "page.html")
        html = (self.tmp / "page.html").read_text(encoding="utf-8")
        self.assertLess(len(html.encode()), ab_page.MAX_BYTES)
        self.assertEqual((out["mode"], out["pictures"], out["steps"], out["side_px"]), ("single", 2, 5, 720))
        self.assertEqual(html.count("function saveScores("), 1)
        self.assertIn("localStorage.setItem", html)
        self.assertIn('id="copy"', html)
        self.assertIn("Would you paint from this lesson?", html)
        key = _key(html)
        self.assertEqual(key["mode"], "single")
        self.assertIsNone(key["seed"])
        self.assertEqual([p["picture"] for p in key["pictures"]], ["chickadee", "red-sailboat"])  # bench order
        self.assertEqual(json.loads((self.tmp / "page.key.json").read_text()), key)
        self.assertNotIn("the plan", html)  # nothing from plan.json
        data = json.loads(re.search(r'<script type="application/json" id="data">(.+?)</script>', html, re.S).group(1))
        step = data["pictures"][0]["sides"]["A"]["steps"][1]
        self.assertEqual((step["n"], step["name"], step["group"]), (2, "Paint part 2", "The sky"))
        self.assertEqual(step["paints"][0]["name"], "Warm gold")
        self.assertTrue(step["img"].startswith("data:image/jpeg;base64,"))

    def test_pair_mode_hides_the_sides_and_records_the_seed(self):
        one = published(self.tmp / "1", "chickadee", "chickadee_skill_20261116-100000")
        two = published(self.tmp / "2", "chickadee", "chickadee_skill_20261116-200000")
        plan = ab_page.plan_round("s1-test", pairs=[(one, two)], seed=7)
        ab_page.make(plan, self.tmp / "p.html")
        html = (self.tmp / "p.html").read_text(encoding="utf-8")
        self.assertNotIn(one.name, _visible(html))
        self.assertNotIn(two.name, _visible(html))
        key = _key(html)
        self.assertEqual(key["seed"], 7)
        self.assertEqual(sorted(key["pictures"][0]["lessons"].values()), sorted([one.name, two.name]))
        self.assertIn("Which would you paint from?", html)
        # the same inputs and seed give the same page, byte for byte
        ab_page.make(ab_page.plan_round("s1-test", pairs=[(one, two)], seed=7), self.tmp / "q.html")
        self.assertEqual((self.tmp / "q.html").read_bytes(), (self.tmp / "p.html").read_bytes())
        # the side is drawn from the seed: over many seeds both orders come up
        firsts = {ab_page.plan_round("r", pairs=[(one, two)], seed=s)["pictures"][0]["sides"]["A"].name
                  for s in range(20)}
        self.assertEqual(firsts, {one.name, two.name})
        # no seed: one from the round's name, recorded
        self.assertEqual(ab_page.plan_round("r", pairs=[(one, two)])["seed"], ab_page._seed_for("r"))

    def test_an_order_seed_shuffles_the_pictures_the_same_way_every_time(self):
        names = ["chickadee", "red-sailboat", "balloon-lavender", "sleeping-cat", "snow-lantern"]
        lessons = [published(self.tmp / "o", n, f"{n}_skill_20261116-100000", steps=1) for n in names]
        order = lambda plan: [r["picture"] for r in plan["pictures"]]  # noqa: E731
        plain = ab_page.plan_round("r", lessons=list(reversed(lessons)))
        self.assertEqual(order(plain), names)  # bench order, whatever order they're given in
        one = ab_page.plan_round("r", lessons=lessons, order_seed=165)
        self.assertEqual(order(one), order(ab_page.plan_round("r", lessons=list(reversed(lessons)), order_seed=165)))
        self.assertEqual(sorted(order(one)), sorted(names))
        self.assertNotEqual({tuple(order(ab_page.plan_round("r", lessons=lessons, order_seed=s))) for s in range(5)},
                            {tuple(names)})
        self.assertEqual(ab_page.answer_key(one)["order_seed"], 165)

    def test_refuses_mixed_pictures_and_mixed_modes(self):
        one = published(self.tmp / "1", "chickadee", "chickadee_skill_20261116-100000")
        two = published(self.tmp / "2", "red-sailboat", "red-sailboat_skill_20261116-100000")
        with self.assertRaises(ValueError):
            ab_page.plan_round("r", pairs=[(one, two)])
        with self.assertRaises(ValueError):
            ab_page.plan_round("r", lessons=[one], pairs=[(one, one)])
        with self.assertRaises(ValueError):
            ab_page.plan_round("r", lessons=[one, one])


class ScoresTests(unittest.TestCase):
    def scores(self, mode="single"):
        lessons = {"A": "chickadee_skill_20261116-100000"}
        sc = {"A": {"real": 4, "paintable": 3, "agree": None, "worst_steps": [{"n": 5, "id": "branch-dark"}],
                    "note": "feet look odd"}}
        if mode == "single":
            sc["A"]["would_paint"] = "maybe"
        else:
            lessons["B"] = "chickadee_skill_20261116-200000"
            sc["B"] = {"real": 2, "paintable": 2, "agree": 3, "worst_steps": [], "note": ""}
        return {"format": ab_page.FORMAT, "round": "baseline-1.12.1", "mode": mode, "seed": None if mode == "single" else 7,
                "saved_at": "2026-11-16T21:00:00.000Z",
                "pictures": [{"picture": "chickadee", "lessons": lessons, "scores": sc,
                              "prefer": None if mode == "single" else "A", "note": ""}]}

    def test_valid_scores_pass_and_bad_ones_are_named(self):
        self.assertEqual(ab_page.check_scores(self.scores()), [])
        self.assertEqual(ab_page.check_scores(self.scores("pair")), [])
        bad = self.scores()
        bad["pictures"][0]["scores"]["A"]["real"] = 7
        bad["pictures"][0]["prefer"] = "C"
        problems = ab_page.check_scores(bad)
        self.assertEqual(len(problems), 2, problems)
        self.assertEqual(ab_page.check_scores({"format": "x"}), [f"not a {ab_page.FORMAT} scores file"])
        two = self.scores()
        two["pictures"][0]["lessons"]["B"] = "x"
        self.assertTrue(ab_page.check_scores(two))

    def test_import_saves_next_to_the_round_and_wont_overwrite(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        src = tmp / "copied.json"
        src.write_text(json.dumps(self.scores()))
        out = ab_page.import_scores(src, dest=tmp / "scores")
        saved = tmp / "scores" / "baseline-1.12.1.json"
        self.assertEqual(Path(out["saved"]), saved)
        self.assertEqual(json.loads(saved.read_text()), self.scores())
        self.assertEqual(out["not_fully_scored"], ["chickadee"])
        ab_page.import_scores(src, dest=tmp / "scores")  # the same scores again: fine
        changed = self.scores()
        changed["pictures"][0]["note"] = "later"
        src.write_text(json.dumps(changed))
        with self.assertRaises(ab_page.Invalid):
            ab_page.import_scores(src, dest=tmp / "scores")
        ab_page.import_scores(src, dest=tmp / "scores", force=True)


if __name__ == "__main__":
    unittest.main()
