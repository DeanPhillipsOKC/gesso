"""Tests for the stroke cards and basics cards (spike/cards.py): what a card must have, where each basics card goes,
the load terms, and the page's card. Moved out of the version 2 tests when v2 was removed (#238)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cards  # noqa: E402
import lessons  # noqa: E402
import plan3  # noqa: E402


class CardTests(unittest.TestCase):
    def test_the_cards_in_the_repo_are_complete(self):
        self.assertEqual(cards.problems(), [])
        self.assertEqual(len(cards.strokes()), len(cards.stroke_results()))  # one card per stroke result

    def test_every_stroke_the_fixture_plans_use_has_a_card(self):
        have = set(cards.strokes())
        for name in lessons.NAMES:
            plan = json.loads((lessons.FIX / name / "plan.json").read_text(encoding="utf-8"))
            used = {s["stroke"] for s in plan3.steps(plan)}
            self.assertEqual(used - have, set(), name)

    def test_what_a_broken_card_is_told(self):
        results = ["Dry brush (x)"]
        good = {"id": "dry-brush", "stroke_result": "Dry brush (x)", "name": "Dry brush", "result": "Broken marks.",
                "sources": ["research, section 2"], "checked": False, "brushes": ["flat"],
                "diagram": {"stages": [{"caption": "a", "add": [{"circle": [50, 50, 10], "paint": "#2f3b2a"}]}]}}
        self.assertEqual(cards.problems({"dry-brush": good}, {}, results), [])  # #127: a shape needs its paint
        for change, expect in (({"sources": []}, "no sources"), ({"result": ""}, "no result"),
                               ({"stroke_result": "Made up"}, "isn't an entry"), ({"brushes": ["spoon"]}, "can draw"),
                               ({"diagram": {"stages": [{"add": [{"blob": 1}]}]}}, "doesn't draw"),
                               ({"mistakes": [{"mistake": "Blobs."}]}, "'mistake' and 'fix'")):
            self.assertIn(expect, " | ".join(cards.problems({"dry-brush": {**good, **change}}, {}, results)))
        self.assertIn("no stroke card for", " | ".join(cards.problems({}, {}, results)))
        self.assertIn("no lines", " | ".join(cards.problems({}, {"x": {"id": "x", "name": "X", "sources": ["s"], "checked": False}}, [])))

    def test_every_basics_card_has_a_valid_when_and_a_missing_one_is_a_problem(self):
        for cid, c in cards.basics().items():
            self.assertIn(c.get("when"), cards.WHEN, cid)
        good = {"id": "x", "name": "X", "when": "start", "lines": ["a"], "sources": ["s"], "checked": False}
        self.assertEqual(cards.problems({}, {"x": good}, []), [])
        self.assertIn("x: no when", " | ".join(cards.problems({}, {"x": {**good, "when": None}}, [])))
        self.assertIn("isn't one of", " | ".join(cards.problems({}, {"x": {**good, "when": "someday"}}, [])))
        self.assertIn("only a start card", " | ".join(cards.problems({}, {"x": {**good, "when": "midway",
                                                                                 "fold": "F"}}, [])))

    def test_where_each_basics_card_goes_in_a_made_up_lesson(self):
        def st(part, show, group, hexes, kinds=(), area=None, of=False):
            return {"part": part, "show": show, "group": group, "lines": [{"kind": k, "text": "t"} for k in kinds],
                    "colors": [{"hex": h, **({"of": "p"} if of else {})} for h in hexes],
                    "aids": {} if area is None else {"area": area}}
        stages = [st("sun", "full", "sky", ["#f0e080"], area=0.02),                       # 1: small
                  st("sky", "blend", "sky", ["#5070c0", "#a0b0e0"], area=0.6),           # 2: the first big coat
                  st("hill", "flat", "land", ["#204020"], ["dry"], area=0.2),             # 3: over the sky; the stage start nearest halfway
                  st("hill", "pass", "land", ["#103010"], ["dry"]),                       # 4: darker, not a light value
                  st("hill", "pass", "land", ["#60a060"], ["dry"], of=True),              # 5: lighter, and a tint
                  st("tree", "flat", "tree", ["#302010"], ["dry"]),                       # 6: a later stage start
                  st("tree", "pass", "tree", ["#c0c0a0"], ["dry", "coats"])]              # 7: a coats line
        got = cards.places(stages)
        self.assertEqual({c: at for c, at in got.items() if at != "start"},
                         {"dries-darker": 1, "let-it-dry": 2, "one-light": 4, "lighter-darker": 4, "ugly-stage": 2,
                          "light-over-dark": 6})
        self.assertEqual(cards.unplaced(stages), [])
        # no coats line, no tint, no lighter pass: those cards don't show at all
        plain = [{**s, "lines": [x for x in s["lines"] if x["kind"] != "coats"],
                  "colors": [{"hex": "#101010"}]} for s in stages]
        got = cards.places(plain)
        self.assertFalse({"light-over-dark", "lighter-darker", "one-light"} & set(got))
        # with no step aids, the first coat stands in for the first big one
        self.assertEqual(cards.places([{**s, "aids": {}} for s in stages])["dries-darker"], 0)
        # nothing painted over anything: check notes the card that has nowhere to go
        bare = [st("a", "full", "g1", ["#ffffff"]), st("b", "full", "g2", ["#000000"])]
        self.assertEqual(len(cards.unplaced(bare)), 1)
        self.assertIn("let-it-dry", cards.unplaced(bare)[0])
        self.assertEqual(cards.unplaced(bare[:1]), [])  # one step: nothing is expected

    def test_the_ugly_stage_is_the_stage_start_nearest_halfway_never_the_last_step(self):
        def lesson(starts, n):
            group = 0
            out = []
            for i in range(n):
                group += i in starts and i > 0
                out.append({"group": f"g{group}", "show": "full", "colors": []})
            return out
        self.assertEqual(cards.moment("midway", lesson({0, 2, 9}, 10)), 2)    # not step 10 of 10
        self.assertEqual(cards.moment("midway", lesson({0, 9}, 10)), 5)       # only a last-step start: halfway
        self.assertEqual(cards.moment("midway", lesson({0}, 10)), 5)          # one stage: halfway
        self.assertEqual(cards.moment("midway", lesson({0, 4, 6}, 10)), 4)    # a tie goes to the earlier one
        self.assertIsNone(cards.moment("midway", lesson({0}, 1)))

    def test_a_when_that_isnt_a_word_is_a_problem_not_a_crash(self):
        good = {"id": "x", "name": "X", "lines": ["a"], "sources": ["s"], "checked": False}
        for when in (["start"], {"step": 3}):
            self.assertIn("isn't one of", " | ".join(cards.problems({}, {"x": {**good, "when": when}}, [])))
            self.assertEqual(cards.places([], {"x": {**good, "when": when}}), {})

    def test_every_stroke_cards_load_uses_only_the_fixed_terms_and_another_word_is_a_problem(self):
        import loads

        for cid, c in cards.strokes().items():  # #99: one vocabulary for how thick and how much
            self.assertEqual(loads.problems(c.get("load"), cid), [], cid)
            if c.get("load"):
                self.assertTrue(set(c["load"]) <= set(loads.KEYS), cid)
        self.assertEqual(loads.text({"thickness": "creamy", "amount": "full"}), "Creamy paint, a full load.")
        self.assertEqual(loads.text({"amount": "dry", "note": "Reload often."}), "Wiped nearly dry. Reload often.")
        good = {**cards.strokes()["press-and-lift"]}
        results = [good["stroke_result"]]
        for load, expect in (("Wet and creamy.", "not free text"), ({"thickness": "runny"}, "isn't one of"),
                             ({"amount": "heaps"}, "isn't one of"), ({"thickness": "creamy", "how": "x"}, "takes only"),
                             ({}, "is empty"), ({"amount": "light", "note": "Creamy, not runny."}, "says 'Creamy'"),
                             ({"thickness": "thin", "note": "Thin it with water until inky."}, "says 'Thin'"),
                             ({"note": "Don't overload the brush."}, "says 'overload'"),
                             ({"thickness": ["creamy"]}, "isn't one of"), ({"note": ["x"]}, "must be text")):
            got = " | ".join(cards.problems({good["id"]: {**good, "load": load}}, {}, results))
            self.assertIn(expect, got, load)

    def test_the_paint_load_card_has_one_picture_and_one_line_per_term(self):
        import loads

        card = cards.basics()[loads.CARD]
        self.assertEqual(card["when"], "start")
        self.assertEqual(sorted(t["term"] for t in card["terms"]), sorted(loads.TERMS))
        self.assertTrue(all(t.get("line") for t in card["terms"]))
        html = cards.basic_html(card)
        self.assertEqual(html.count('<svg class="loadpic"'), len(loads.TERMS))
        self.assertEqual(html.count("<figcaption>"), len(loads.TERMS))
        for t in loads.TERMS:
            self.assertIn(f"id='load-{t}'", html)
            self.assertIn(loads.LABELS[t], html)
        self.assertIn("href='#basic-water'", html)  # thin paint points at How much water
        # a term missing, twice, unknown, or with no line is a problem
        terms = card["terms"]
        for broken, expect in ((terms[1:], "shows 0 times"), (terms + terms[:1], "shows 2 times"),
                               (terms + [{"term": "goopy", "line": "x"}], "isn't one of the load terms"),
                               ([{**terms[0], "line": ""}] + terms[1:], "has no line"),
                               ([{**terms[0], "see": "nowhere"}] + terms[1:], "doesn't exist")):
            got = " | ".join(cards.problems({}, {**cards.basics(), loads.CARD: {**card, "terms": broken}}, []))
            self.assertIn(expect, got)

    def test_a_load_line_links_its_terms_and_carries_their_pictures(self):
        import loads

        html = loads.linked("Brush: #6 round. Load: Creamy paint, a full load. Reload often.")
        self.assertEqual(html.count('href="#basic-paint-load"'), 2)
        self.assertEqual(html.count('class="loadpic sm"'), 2)
        self.assertIn(loads.LABELS["creamy"], html)
        self.assertIn(loads.LABELS["full"], html)
        self.assertIn(" Reload often.<span class=\"loadpics\">", html)
        one = loads.linked("Brush: liner. Load: Wiped nearly dry.")
        self.assertEqual(one.count('class="loadpic sm"'), 1)
        self.assertIn(loads.LABELS["dry"], one)
        # the same words outside a load, or an old free-text load, stay plain text
        for plain in ("Start thick at the trunk and thin it out.", "Load: Wet and creamy.", "Paint: Creamy white."):
            self.assertEqual(loads.linked(plain), plain.replace("'", "&#x27;"))
        self.assertIn("&lt;b&gt;", loads.linked("Load: Thin paint. <b>"))  # still escaped
        card = cards.stroke_html(cards.strokes()["press-and-lift"])
        self.assertEqual(card.count('class="loadword"'), 2)  # the stroke card's Load row links its words too,
        self.assertNotIn('class="loadpic', card)              # without the pictures its step's line already shows

    def test_an_unchecked_card_says_so_and_the_page_holds_every_card(self):
        page = cards.page()
        for cid in cards.strokes():
            self.assertIn(f"id='stroke-{cid}'", page)
        self.assertIn("Not checked yet", cards.stroke_html({**cards.strokes()["dabbing"], "checked": False}))
        self.assertNotIn("Not checked yet", cards.stroke_html({**cards.strokes()["dabbing"], "checked": True}))


if __name__ == "__main__":
    unittest.main()
