"""Version 2 lessons through build-steps, mix, publish, the seal, the page, and every reader of lesson.json
(issue #65, docs/design/pipeline-v2.md section 13).

Each fixture (fixtures/plans, finishes, owners) is built into a lesson folder once per test run, as `build-steps`,
`step-aids`, `mix`, and `publish` would leave it (tests/lessons.py); no renders, no network, no model files.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from html import escape as html_escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import history  # noqa: E402
import lessons  # noqa: E402
import tools  # noqa: E402
from test_pipeline_v2 import NAMES, fixture  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
V1 = json.loads((FIX / "expected" / "v1-lesson.json").read_text(encoding="utf-8"))  # what version 1 readers get


def run_tool(*argv) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = tools.main(list(argv))
    return code, json.loads(out.getvalue().strip().splitlines()[-1])


@lessons.slow
class PublishV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.old_history = os.environ.get("GESSO_HISTORY")
        os.environ["GESSO_HISTORY"] = str(cls.root / "history")
        cls.lessons, cls.results = {}, {}
        for name in NAMES:  # built once per run and shared (tests/lessons.py); a copy each, to read
            cls.lessons[name] = lessons.lesson(name, "published", cls.root)
            for tool, r in lessons.results(name, "published").items():
                cls.results[(name, tool)] = r

    @classmethod
    def tearDownClass(cls):
        if cls.old_history is None:
            os.environ.pop("GESSO_HISTORY", None)
        else:
            os.environ["GESSO_HISTORY"] = cls.old_history
        cls.tmp.cleanup()

    def data(self, name: str) -> dict:
        return json.loads((self.lessons[name] / "lesson.json").read_text(encoding="utf-8"))

    def copy(self, name: str) -> Path:
        """A copy of a published fixture lesson, to change without spoiling the others."""
        dst = Path(tempfile.mkdtemp(dir=self.root)) / self.lessons[name].name
        shutil.copytree(self.lessons[name], dst)
        return dst

    # --- lesson.json, key by key (design section 13) ---

    def test_every_version_1_key_keeps_its_type_and_the_new_keys_sit_beside_them(self):
        v1_stage = V1["stages"][0]
        for name in NAMES:
            data, plan = self.data(name), fixture(name)[1]
            steps = [s for st in plan["stages"] for s in st["steps"]]
            self.assertEqual(data["plan_version"], 2)
            for key, value in V1.items():
                self.assertIn(key, data, f"{name}: lesson.json lost {key}")
                if value is not None:
                    want = (int, float) if isinstance(value, (int, float)) else type(value)  # an empty ledger sums to 0
                    self.assertIsInstance(data[key], want, f"{name}: {key}")
            for key in ("subject", "focal_point", "light", "components", "mixes"):
                self.assertIsInstance(data["photo_read"][key], type(V1["photo_read"][key]), key)
            self.assertEqual(data["photo_read"]["components"],
                             [p["name"] for p in plan["parts"] if not p.get("parent")])
            self.assertEqual([s["id"] for s in data["stages"]], [s["id"] for s in steps])
            for i, (s, step) in enumerate(zip(data["stages"], steps)):
                for key, value in v1_stage.items():
                    self.assertIn(key, s, f"{name} {s['id']}: no {key}")
                    self.assertIsInstance(s[key], type(value), f"{name} {s['id']}: {key}")
                self.assertEqual(s["image"], f"{i + 1:02d}_{step['id']}.png")
                self.assertTrue(all(isinstance(x, str) for x in s["steps"]))
                self.assertEqual(s["steps"], [step["name"]])  # no text yet: a draft, its name only
                self.assertTrue(all(set(t) == {"name", "how"} for t in s["strokes"]))
                self.assertEqual([c["id"] for c in s["colors"]], step["paints"])
                for c in s["colors"]:
                    self.assertTrue(c["name"] and c["hex"] and c["recipe"], c)
                self.assertEqual(s["brushes"], step["brush"])
                self.assertEqual(s["brush_list"], [{"brush": step["brush"], "use": step["name"]}])
                self.assertEqual(s["made_with"], "composite:from-finish")
                self.assertEqual((s["part"], s["show"]), (step["part"], step["show"]))
                self.assertEqual(s["stroke_cards"], [step["stroke"]])  # every fixture stroke has a card
                self.assertTrue(s["strokes"][0]["how"])  # the card's motion
            self.assertEqual(data["groups"], [{"id": st["id"], "name": st["name"], "steps": [s["id"] for s in st["steps"]]}
                                              for st in plan["stages"]])
            self.assertEqual([s["group"] for s in data["stages"]],
                             [st["id"] for st in plan["stages"] for _ in st["steps"]])

    def test_the_last_step_is_its_own_picture_a_copy_of_the_finish(self):
        for name in NAMES:
            lesson = self.lessons[name]
            last = self.data(name)["stages"][-1]["image"]
            self.assertNotEqual(last, "99_finish.png")
            a = np.asarray(Image.open(lesson / last))
            self.assertTrue((a == np.asarray(Image.open(lesson / "99_finish.png"))).all())

    def test_mix_keeps_the_measured_hex_and_solves_every_paint(self):
        for name in NAMES:
            plan = fixture(name)[1]
            mixes = json.loads((self.lessons[name] / "mixes.json").read_text(encoding="utf-8"))
            self.assertEqual(len(mixes), len(plan["paints"]))
            r = self.results[(name, "mix")]
            self.assertEqual([p["target"] for p in r["paints"]], [c["hex"] for c in plan["paints"]])  # no swatch snapping
            self.assertTrue(all(p["recipe"] for p in r["paints"]))
            mixed = {m["id"]: m for m in self.data(name)["photo_read"]["mixes"]}
            self.assertEqual(set(mixed), {c["id"] for c in plan["paints"]})
            self.assertEqual(mixed[plan["paints"][0]["id"]]["parts"], plan["paints"][0]["parts"])

    def test_a_paint_with_no_name_uses_its_id(self):
        import publish2
        plan = fixture("red-sailboat")[1]
        plan["paints"][0].pop("name")
        plan["paints"][2]["name"] = plan["paints"][1]["name"]
        names = publish2.paint_names(plan)
        self.assertEqual(names[plan["paints"][0]["id"]], plan["paints"][0]["id"])
        self.assertEqual(len(set(names.values())), len(names))  # a shared name is told apart by the id

    # --- the page ---

    def test_the_page_puts_every_step_under_its_stage(self):
        for name in NAMES:
            data = self.data(name)
            num = {s["id"]: i + 1 for i, s in enumerate(data["stages"])}
            self.assertTrue(all((self.lessons[name] / s["image"]).exists() for s in data["stages"]))
            for page in ("lesson.html", "lesson-standalone.html"):
                html = (self.lessons[name] / page).read_text(encoding="utf-8")
                heads = [html.index(f'id="stage-{g["id"]}"') for g in data["groups"]] + [len(html)]
                self.assertEqual(heads[:-1], sorted(heads[:-1]))
                for k, g in enumerate(data["groups"]):
                    self.assertIn(f'>{g["name"]} <span class="small">{len(g["steps"])} step', html)
                    for sid in g["steps"]:
                        at = html.index(f'id="step-{num[sid]}"')
                        self.assertTrue(heads[k] < at < heads[k + 1], f"{name}: step {sid} isn't under {g['id']}")

    def test_every_step_shows_where_its_paint_goes_and_its_folds(self):
        import cards
        known = cards.strokes()
        for name in NAMES:
            data = self.data(name)
            stages = data["stages"]
            self.assertEqual(set(data["aids"]), {"view", "canvas_box", "transfer"})
            self.assertTrue(all(s["aids"]["path"] and s["aids"]["where_words"] for s in stages), name)
            html = (self.lessons[name] / "lesson-standalone.html").read_text(encoding="utf-8")
            self.assertEqual(html.count('<div class="sw">'), len(stages))
            self.assertEqual(html.count('<image id="pic-'), len(stages))  # each step picture once, shared by its views
            for i in range(1, len(stages)):
                self.assertIn(f'<use href="#pic-{i}"/>', html)
            self.assertNotIn("percentages", html)
            self.assertNotRegex(" ".join(s["aids"]["where_words"] for s in stages), r"%|percent")
            self.assertEqual(html.count("Close-up</summary>") + html.count("Close-up <span"),
                             sum(1 for s in stages if s["aids"].get("closeup")))
            self.assertEqual(html.count('aria-label="Paint map"'), sum(1 for s in stages if s["aids"].get("map")))
            used = {c for s in stages for c in s["stroke_cards"]}
            for c in used:  # a stroke's card is open once, where it's first used; later steps link back to it
                self.assertEqual(html.count(f"id='stroke-{c}'"), 1, f"{name} {c}")
                if not known[c].get("checked"):
                    self.assertIn("Not checked yet", html)
            self.assertEqual(html.count('class="stop"'), len(data["groups"]))
            self.assertIn('id="start"', html)
            self.assertEqual(html.count("class='card' id='basic-"), len(cards.places(stages)))  # each placed card once
            self.assertIn("The transfer outline", html)
            self.assertIn('<nav class="toc"', html)
            # self-contained: every picture inlined, nothing fetched but the fonts
            refs = re.findall(r'(?:src|href)="([^"#][^"]*)"', html)
            self.assertEqual([r for r in refs if not r.startswith(("data:", "https://"))], [], name)
            self.assertLess(self.results[(name, "publish")]["page_mb"], 8)
            self.assertFalse(self.results[(name, "publish")]["missing_aids"])

    def test_before_you_start_has_only_the_start_basics_and_each_other_card_is_open_in_its_step(self):
        import cards
        import page2
        known = cards.basics()
        start = {c for c, k in known.items() if k["when"] == "start"}
        self.assertEqual(start, {"set-up", "clean-brush", "water", "keep-paint-wet", "fix-a-mistake"})
        for name in NAMES:
            stages = self.data(name)["stages"]
            html = (self.lessons[name] / "lesson-standalone.html").read_text(encoding="utf-8")
            head, rest = html.split('id="start"', 1)[1].split("<h2>The steps</h2>", 1)
            self.assertEqual({c for c in known if f"id='basic-{c}'" in head}, start, name)
            self.assertIn("<summary>If something goes wrong", head)
            self.assertIn("The other basics are in the steps", head)
            self.assertNotIn("Basics: ", head)
            placed = cards.places(stages)
            self.assertTrue({"let-it-dry", "dries-darker", "ugly-stage"} <= set(placed), name)
            for c, at in placed.items():
                self.assertEqual(html.count(f"id='basic-{c}'"), 1, f"{name} {c}")
                if at == "start":
                    continue
                step = rest.split(f'id="step-{at + 1}"', 1)[1].split("</article>", 1)[0]
                self.assertIn(f'<details class="aid basic" open><summary>Basics: {html_escape(known[c]["name"])}', step)
            # published with no drafted text: no coats line, so no light-over-dark card anywhere
            self.assertNotIn("light-over-dark", placed)
            self.assertNotIn("id='basic-light-over-dark'", html)

    def test_a_version_2_step_is_labelled_cut_from_the_finish_not_a_render(self):
        for name in NAMES:
            html = (self.lessons[name] / "lesson.html").read_text(encoding="utf-8")
            self.assertEqual(html.count("How this picture was made"), len(self.data(name)["stages"]))
            self.assertNotIn('<span class="tag t-render">Render', html)
            self.assertIn('<span class="tag t-cut">Cut from the finish · free</span>', html)

    def test_without_step_aids_the_page_still_works_and_the_seal_asks_for_them(self):
        lesson = self.copy("red-sailboat")
        shutil.rmtree(lesson / "aids")
        code, r = run_tool("publish", "--lesson", str(lesson))
        self.assertEqual(code, 0, r)
        self.assertTrue(r["missing_aids"])
        data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
        self.assertEqual({json.dumps(s["aids"]) for s in data["stages"]}, {"{}"})
        self.assertNotIn('class="sw"', (lesson / "lesson.html").read_text(encoding="utf-8"))
        raw, plan, _ = tools.load_plan(lesson)
        self.assertIn("run step-aids", " ".join(tools.seal_problems(lesson, plan, {}, {}, {}, r)))

    def test_a_version_2_page_over_8_mb_is_refused(self):
        import publish2
        lesson = self.copy("red-sailboat")
        old, publish2.MAX_PAGE_BYTES = publish2.MAX_PAGE_BYTES, 1_000_000
        try:
            code, r = run_tool("publish", "--lesson", str(lesson))
        finally:
            publish2.MAX_PAGE_BYTES = old
        self.assertEqual(code, 2)
        self.assertIn("MB", r["refused"])

    # --- the top of the page: tubes first, the rest folded (#94) ---

    def test_the_tubes_come_first_one_swatch_each_in_first_use_order(self):
        for name in NAMES:
            data = self.data(name)
            html = (self.lessons[name] / "lesson-standalone.html").read_text(encoding="utf-8")
            self.assertLess(html.index('id="tubes"'), html.index("<h2>What you need</h2>"), name)
            self.assertLess(html.index("Where you'll end up"), html.index('id="tubes"'), name)
            block = html[html.index('<ul class="tubelist">'):]
            block = block[:block.index("</ul>")]
            want = []  # the first step whose paints use each tube, worked out here from lesson.json
            for i, s in enumerate(data["stages"]):
                for c in s["colors"]:
                    for t, amount in c["mix"]["parts"].items():
                        if amount and t not in [x for x, _ in want]:
                            want.append((t, i + 1))
            self.assertTrue(want, name)
            pal = data["tubes"]  # within one step, the palette's order
            want.sort(key=lambda x: (x[1], pal.index(x[0]) if x[0] in pal else len(pal)))
            shown = re.findall(r'<li><span class="swatch" style="background:(#[0-9a-f]{6})"></span><span><b>([^<]+)</b>'
                               r'<span class="small">first in <a href="#step-(\d+)">step \d+</a>', block)
            self.assertEqual([(t, int(n)) for _, t, n in shown], want, name)
            self.assertEqual(block.count("<li>"), len(want))
            self.assertEqual(len({h for h, _, _ in shown}), len(want), f"{name}: one swatch color per tube")

    def test_a_painters_own_tube_takes_its_color_from_their_palette_file(self):
        import page2
        own = page2._palette_colors("The owner's paints")
        self.assertEqual(page2.tube_hex("Dark ultramarine", own), "#140a46")
        self.assertEqual(page2.tube_hex("Burnt sienna", {}), "#7b4800")
        self.assertEqual(page2.tube_hex("Unobtainium", {}), "")
        self.assertEqual(page2._palette_colors(""), {})

    def test_with_no_mix_data_every_tube_is_listed_with_no_step(self):
        import page2
        lesson = {"stages": [{"colors": [{"name": "Sky"}]}]}
        self.assertEqual(page2.tube_order(lesson, ["Titanium white", "Burnt sienna"]),
                         [("Titanium white", None), ("Burnt sienna", None)])
        self.assertNotIn("first in", page2.tubes_first(lesson, ["Titanium white"]))

    def test_the_tubes_are_not_also_in_the_kit_and_the_kit_has_a_ruler_and_no_tape(self):
        def kit_of(html: str) -> str:
            return html[html.index('<div class="kit">'):html.index("</section>", html.index('<div class="kit">'))]
        for name in NAMES:
            data = self.data(name)
            kit = kit_of((self.lessons[name] / "lesson-standalone.html").read_text(encoding="utf-8"))
            self.assertNotIn('<p class="label">Tubes</p>', kit)
            for t in data["tubes"]:
                self.assertNotIn(f"<li>{t}</li>", kit, name)
            # #122: every lesson has a canvas size (the fixtures get the default), and the steps measure in inches
            self.assertIn("<li>A 14 x 11 in canvas, landscape (hang it that way). Using another size? Scale every "
                          "measurement.</li>", kit, name)
            self.assertIn("<li>A ruler</li>", kit, name)
            self.assertNotIn("tape", kit.lower(), name)

    def test_your_paints_is_closed_with_its_summary_and_the_cards_unchanged_inside(self):
        for name in NAMES:
            data = self.data(name)
            html = (self.lessons[name] / "lesson-standalone.html").read_text(encoding="utf-8")
            n = len(data["photo_read"]["mixes"])
            m = re.search(r'<section id="paints"><details class="aid allpaints"><summary><h2 class="foldh">Your paints</h2>'
                          r'<span class="small">'
                          rf'All {n} paints and their recipes\. Each step lists the ones it needs, so you can mix as you go'
                          r'</span></summary>(.*?)</details></section>', html, re.S)
            self.assertTrue(m, name)
            inside = m.group(1)
            self.assertEqual(inside.count('<div class="paint">'), n)
            for p in data["photo_read"]["mixes"]:  # each card whole: swatch, name, recipe, what it's for, first step
                card = inside[inside.index(f'<span class="blob" style="background:{p["hex"]}"></span><div><b>{p["name"]}</b>'):]
                card = card[:card.index('</div></div>')]
                self.assertIn(f'<span class="recipe">{html_escape(p["recipe"])}</span>', card)
                self.assertIn(html_escape(p.get("used_for", "")), card)
                self.assertIn("First needed in step", card)

    def test_the_transfer_outline_sits_alone_in_a_closed_optional_fold_placed_by_inches(self):
        for name in NAMES:
            html = (self.lessons[name] / "lesson-standalone.html").read_text(encoding="utf-8")
            start = html[html.index('id="start"'):]
            m = re.search(r'<details class="aid placing"><summary>Placing shapes with a transfer outline '
                          r'<span class=small>optional</span></summary>(.*?)</details>', start, re.S)
            self.assertTrue(m, name)
            self.assertIn("The transfer outline", m.group(1))
            self.assertIn("On your 14 x 11 in canvas the grid lines are 3 1/2 in apart across and 2 3/4 in apart "
                          "down.", m.group(1))
            self.assertIn("measuring from the edges with a ruler", m.group(1))
            self.assertNotIn('class="tape"', html)
            self.assertEqual(html.count('class="transfer"'), 1)

    def test_a_lesson_published_without_a_canvas_gets_the_default_size_for_its_shape(self):
        # #122: the fixtures have no canvas.json and no --canvas. 1000 x 786 is the shape of 14 x 11 in.
        for name in NAMES:
            info = json.loads((self.lessons[name] / "canvas.json").read_text(encoding="utf-8"))
            self.assertEqual(info["chosen"], "default", name)
            self.assertEqual(info["canvas"], {"w_in": 14.0, "h_in": 11.0, "orientation": "landscape"}, name)
            self.assertEqual(info["canvas_box"], [0.0, 0.0, 1.0, 1.0], name)  # the shape fits: nothing is cropped
            self.assertEqual(self.data(name)["canvas"], info["canvas"], name)

    def test_no_tape_anywhere_on_a_version_2_page_and_close_ups_give_inches(self):
        for name in NAMES:
            html = (self.lessons[name] / "lesson-standalone.html").read_text(encoding="utf-8")
            self.assertNotRegex(html, r"(?i)\btape\b", name)
            stages = self.data(name)["stages"]
            if any(s["aids"].get("closeup") for s in stages):
                self.assertIn("The dotted lines are every 1 3/4 in across and 1 3/8 in down.", html, name)
            self.assertNotIn("halfway between", html)

    # --- text, drafts, and the seal ---

    def test_text_fills_a_step_a_step_without_it_is_a_draft_and_the_seal_needs_text(self):
        lesson = self.copy("red-sailboat")
        plan = fixture("red-sailboat")[1]
        ids = [s["id"] for st in plan["stages"] for s in st["steps"]]
        text = {"steps": [{"stage_id": "sky-blend", "summary": "Blend the sky from violet down to gold.",
                           "tip": "Keep the horizon glow lightest.",
                           "lines": [{"kind": "paints", "text": "Sky 1, Sky 2, then Sky 3.", "edited": False},
                                     {"kind": "how", "text": "Long strokes side to side.", "edited": False},
                                     {"kind": "watch", "text": "Don't let the joins dry.", "edited": False}],
                           "brushes": [{"brush": "1 inch flat", "use": "the whole sky"}], "stroke_cards": ["wet-blend"],
                           "made_with": "composite:from-finish", "reason": "cut from the finish"}]}
        (lesson / "text.json").write_text(json.dumps(text), encoding="utf-8")
        (lesson / "review.json").write_text(json.dumps({"finish_issues": [], "text_issues": []}), encoding="utf-8")
        code, r = run_tool("publish", "--lesson", str(lesson), "--final")
        self.assertEqual(code, 2)
        refused = r["refused"]
        self.assertIn("text.json has no step water-coat", refused)
        self.assertIn("text.json has no step sun", refused)  # a draft step can't be sealed
        self.assertNotIn("sky-blend: text.json has no", refused)
        for gone in ("review_issues", "regions", "long_steps", "strokes"):
            self.assertNotIn(gone, refused)
        data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))  # written before the seal's check
        sky, sun = data["stages"][0], data["stages"][1]
        self.assertEqual(sky["steps"], ["Sky 1, Sky 2, then Sky 3.", "Long strokes side to side.", "Don't let the joins dry."])
        self.assertEqual(sky["lines"][2], {"kind": "watch", "text": "Don't let the joins dry."})
        self.assertEqual(sky["watch_out"], ["Don't let the joins dry."])
        self.assertEqual((sky["summary"], sky["tip"]), ("Blend the sky from violet down to gold.", "Keep the horizon glow lightest."))
        self.assertEqual(sky["brush_list"], [{"brush": "1 inch flat", "use": "the whole sky"}])
        self.assertEqual(sky["stroke_cards"], ["wet-blend"])
        self.assertEqual(sky["strokes"][0]["name"], "Wet-on-wet blend")
        self.assertEqual(sun["steps"], ["Paint the sun"])
        self.assertTrue(sun["colors"])
        html = (lesson / "lesson.html").read_text(encoding="utf-8")
        self.assertIn("<li>Long strokes side to side.</li>", html)
        self.assertIn("<b>Tip:</b> Keep the horizon glow lightest.", html)
        self.assertEqual(len(ids), len(data["stages"]))

    def test_the_seal_for_version_2_needs_text_and_two_reviews_not_regions(self):
        lesson = self.copy("lavender-balloon")
        raw, plan, _ = tools.load_plan(lesson)
        ids = [s.id for s in plan.steps]
        text = {sid: {"summary": "x", "lines": [{"kind": "how", "text": "x"}], "brushes": [{"brush": "#6 round", "use": "x"}],
                      "made_with": "composite:from-finish"} for sid in ids}
        review = {"finish_issues": [], "text_issues": []}
        (lesson / "review.json").write_text(json.dumps(review), encoding="utf-8")
        (lesson / "trials" / "review").mkdir(parents=True)
        (lesson / "trials" / "review" / "review.json").write_text("{}", encoding="utf-8")
        notes = {"read": "x", "technique": {"why": "x"}, "order": "x", "steps": {sid: "x" for sid in ids},
                 "beginner_check": {"summary": "x", "diagrams": {}, "no_diagram": {sid: "x" for sid in ids}}}
        self.assertEqual(tools.seal_problems(lesson, plan, text, review, notes, {}), [])
        text[ids[3]].pop("lines")
        self.assertEqual(tools.seal_problems(lesson, plan, text, review, notes, {}), [f"{ids[3]}: text.json has no lines"])
        self.assertIn("review.json has no text_issues", " ".join(tools.seal_problems(lesson, plan, text, {}, notes, {})))
        shutil.rmtree(lesson / "trials" / "review")
        (lesson / "review.json").unlink(missing_ok=True)
        said = " | ".join(tools.seal_problems(lesson, plan, text, review, notes, {}))
        self.assertIn("the text review (step 7b) hasn't run", said)  # the v2 skill's step, not v1's 6b
        self.assertIn("review.json is missing (step 7b)", said)
        self.assertNotIn("6b", said)

    def test_a_review_by_the_session_that_wrote_the_text_is_a_known_problem(self):
        import known_problems
        lesson = self.copy("red-sailboat")
        (lesson / "review.json").write_text(json.dumps({"finish_issues": [], "text_issues": [], "review_context": "same"}),
                                            encoding="utf-8")
        code, r = run_tool("publish", "--lesson", str(lesson))
        self.assertEqual(code, 0, r)
        data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
        self.assertEqual(data["review_context"], "same")
        self.assertIn({"step": None, "name": "", "problem": "The text review was done by the same session that wrote "
                       "the text, not a fresh one."}, known_problems.left(data))
        self.assertIn("same session that wrote the text", known_problems.section(known_problems.left(data), []))
        self.assertEqual(known_problems.left({**data, "review_context": "fresh"}), [])
        self.assertEqual(known_problems.left({**data, "plan_version": None}), [])  # version 1 lessons: unchanged

    # --- every other reader of lesson.json ---

    def test_history_records_a_version_2_run_like_any_run_with_minutes_total(self):
        for name in NAMES:
            lesson = self.lessons[name]
            home = lessons.history(name)  # where the shared build's publish recorded it
            rec = json.loads((home / name / lesson.name / "record.json").read_text(encoding="utf-8"))
            p = rec["publishes"][-1]
            self.assertEqual(p["metrics"]["steps"], len(self.data(name)["stages"]))
            self.assertEqual(p["metrics"]["paid_renders"], 0)
            self.assertGreater(p["metrics"]["minutes_total"], 0)  # from 09:00 on 2026-11-12, the folder's time
            self.assertEqual(p["metrics"]["checks"]["long_steps"], 0)
            self.assertTrue((home / name / lesson.name / p["strip"]).exists())
            self.assertEqual({s["made_with"] for s in p["steps"]}, {"composite:from-finish"})
            self.assertEqual(history.digest(lesson, self.data(name)), p["digest"])
            self.assertIn("min start to publish", (home / "index.html").read_text(encoding="utf-8"))

    def test_minutes_total_is_from_the_folder_time_and_left_out_without_one(self):
        at = dt.datetime(2026, 11, 12, 9, 21, 30)
        self.assertEqual(history.minutes_total("chickadee_skill_20261112-090000", at), 21.5)
        self.assertIsNone(history.minutes_total("v1-lesson", at))
        self.assertNotIn("minutes_total", history.metrics(V1, None, "v1-lesson", at))
        self.assertEqual(history.metrics(V1, None, "x_skill_20261112-090000", at)["minutes_total"], 21.5)
        self.assertNotIn("minutes_total", history.metrics(V1, None))

    def test_step_pairs_reads_a_version_2_lesson(self):
        lesson = self.copy("red-sailboat")
        code, r = run_tool("step-pairs", "--lesson", str(lesson))
        self.assertEqual(code, 0, r)
        self.assertEqual(r["sheets"], 14)
        packet = json.loads((lesson / "trials" / "review" / "packet.json").read_text(encoding="utf-8"))
        self.assertEqual(packet["steps"][0]["what_to_do"], ["Blend the sunset sky"])
        self.assertTrue(all(s["paints"] for s in packet["steps"]))

    def test_the_embed_and_the_notes_read_a_version_2_lesson(self):
        for name in NAMES:
            lesson, data = self.lessons[name], self.data(name)
            embed = json.loads((lesson / "embed" / "lesson.json").read_text(encoding="utf-8"))
            self.assertEqual(len(embed["steps"]), len(data["stages"]))
            self.assertEqual(embed["steps"][0]["summary"], data["stages"][0]["name"])
            self.assertTrue(embed["steps"][0]["paints"] and embed["steps"][0]["brushes"])
            html = (lesson / "lesson-artifact.html").read_text(encoding="utf-8")
            self.assertIn('id="behind"', html)  # lesson_notes: behind the easel
            self.assertIn("Total, 0 renders", html)

    def test_notes_in_any_shape_never_stop_a_publish(self):
        # the lavender balloon's beginner_version came back as a list, and publish crashed (2026-11-13)
        lesson = self.copy("lavender-balloon")
        ids = [s["id"] for st in fixture("lavender-balloon")[1]["stages"] for s in st["steps"]]
        notes = {"beginner_version": ["Dropped the village", "Merged the mountains"], "photo_prep": ["cropped"],
                 "canvas_fit": "fitted to 16 x 20", "technique": "the paint-along", "read": ["a balloon", "lavender"],
                 "order": {"first": "the sky"}, "steps": ["x"], "beginner_check": "no step needs a diagram",
                 "learned": "outline paths as marks", "filters": ["blur"], "throwaways": "none"}
        (lesson / "notes.json").write_text(json.dumps(notes), encoding="utf-8")
        (lesson / "review.json").write_text(json.dumps({"finish_issues": "none", "text_issues": ["one"]}), encoding="utf-8")
        code, r = run_tool("publish", "--lesson", str(lesson))
        self.assertEqual(code, 0, r)
        html = (lesson / "lesson.html").read_text(encoding="utf-8")
        self.assertIn("Dropped the village; Merged the mountains", html)
        self.assertIn("outline paths as marks", html)
        code, r = run_tool("publish", "--lesson", str(lesson), "--final")
        self.assertIn("beginner_check must be a dict", r["refused"])  # a seal problem that says what to change
        self.assertTrue(ids)

    def test_a_sealed_version_2_lesson_goes_on_the_site(self):
        import provenance
        import site_lessons
        lesson = self.copy("chickadee")
        provenance.seal(lesson, json.loads((lesson / "lesson.json").read_text(encoding="utf-8")))
        code, _ = run_tool("publish", "--lesson", str(lesson))
        self.assertEqual(code, 0)
        site = self.root / "site"
        r = site_lessons.add(lesson, "chickadee-v2", site)
        self.assertEqual(r["url_path"], "/lessons/chickadee-v2/")
        entry = json.loads((site / "lessons.json").read_text(encoding="utf-8"))[0]
        self.assertEqual(entry["steps"], len(self.data("chickadee")["stages"]))  # however many the plan has
        self.assertEqual(site_lessons.kind(self.data("chickadee")), "steps cut from the finish")

    # --- refusals ---

    def diagram_lesson(self, second: dict) -> tuple[Path, list[str]]:
        """A copy of the sailboat with a diagram on its first step and `second` on its second."""
        lesson = self.copy("red-sailboat")
        ids = [st["id"] for st in self.data("red-sailboat")["stages"]]
        shape = {"stages": [{"caption": "An oval", "add": [{"ellipse": [50, 50, 20, 30]}]}]}
        (lesson / "text.json").write_text(json.dumps({"steps": [
            {"stage_id": ids[0], "construct": shape}, {"stage_id": ids[1], "construct": second}]}), encoding="utf-8")
        return lesson, ids

    def test_publish_explains_diagrams_and_flags_unexplained_ones(self):  # from the version 1 tests (#82)
        lesson, ids = self.diagram_lesson({"stages": [{"caption": "A box", "add": [{"rect": [10, 10, 50, 40]}]}]})
        (lesson / "notes.json").write_text(json.dumps({"beginner_check": {
            "summary": "One shaped object.", "no_diagram": {},
            "diagrams": {ids[0]: {"noticed": "The lumpy outline.", "pieces": "An oval first.", "source": "beginner check"}}}}),
            encoding="utf-8")
        code, r = run_tool("publish", "--lesson", str(lesson))
        self.assertEqual(code, 0, r)
        self.assertEqual(r["diagrams"], 2)
        self.assertEqual(r["undocumented_diagrams"], [ids[1]])
        html = (lesson / "lesson-artifact.html").read_text(encoding="utf-8")
        for text in ("The lumpy outline.", "An oval first."):
            self.assertIn(text, html)

    def test_a_diagram_given_a_paint_id_draws_in_that_paint_on_the_page(self):  # #91
        paint = json.loads((self.lessons["red-sailboat"] / "plan.json").read_text(encoding="utf-8"))["paints"][0]
        lesson, _ = self.diagram_lesson({"paint": paint["id"], "stages": [{"add": [{"rect": [10, 10, 50, 40]}]}]})
        code, r = run_tool("publish", "--lesson", str(lesson))
        self.assertEqual(code, 0, r)
        html = (lesson / "lesson-artifact.html").read_text(encoding="utf-8")
        rects = re.findall(r'<rect x="10.0" y="10.0"[^>]*>', html)
        self.assertTrue(rects)
        for rect in rects:
            self.assertIn(f'fill="{paint["hex"]}"', rect)

    def test_preview_diagrams_needs_publish_then_draws_each_one(self):  # from the version 1 tests (#82)
        lesson, _ = self.diagram_lesson({"stages": [{"add": [{"path": "not a path"}]}]})
        (lesson / "lesson.json").unlink()
        code, r = run_tool("preview-diagrams", "--lesson", str(lesson))
        self.assertEqual(code, 2)  # no lesson.json yet
        code, r = run_tool("publish", "--lesson", str(lesson))
        self.assertEqual(code, 0, r)
        code, r = run_tool("preview-diagrams", "--lesson", str(lesson))
        self.assertEqual(code, 0)
        self.assertEqual(r["diagrams"], 2)
        html = Path(r["html"]).read_text(encoding="utf-8")
        self.assertIn("An oval", html)
        self.assertIn("This spec is broken", html)

    def test_preview_with_no_diagrams_says_why(self):
        code, r = run_tool("preview-diagrams", "--lesson", str(self.lessons["chickadee"]))
        self.assertIn("No diagrams in lesson.json", r["note"])

    def test_publish_crops_steps_to_the_canvas(self):  # from the version 1 tests (#82)
        lesson = self.copy("chickadee")
        code, r = run_tool("fit-canvas", str(lesson / "99_finish.png"), "--lesson", str(lesson), "--canvas", "11x14",
                           "--why", "test")
        self.assertEqual(code, 0, r)
        self.assertTrue((lesson / "canvas.json").exists())
        code, r = run_tool("publish", "--lesson", str(lesson))
        self.assertEqual(code, 0, r)
        data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
        w, h = data["canvas"]["w_in"], data["canvas"]["h_in"]
        self.assertEqual(sorted([w, h]), [11, 14])  # turned to the picture's shape
        for st in data["stages"]:
            self.assertTrue((lesson / st["image"]).exists())
        self.assertIn(f"{w:g} x {h:g} in", (lesson / "lesson.html").read_text(encoding="utf-8"))

    def test_a_version_1_plan_is_refused(self):  # the version 1 pipeline was removed (#82)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "plan.json").write_text(json.dumps({"technique": "techniques/acrylic-paint-along-beginner.yaml",
                                                         "steps": []}), encoding="utf-8")
            for tool in ("publish", "mix"):
                code, r = run_tool(tool, "--lesson", d)
                self.assertEqual(code, 2)
                self.assertIn("version 2", r["refused"])

    def test_publish_before_build_steps_says_to_run_it(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = lessons.lesson("red-sailboat", "outlined", Path(d))
            code, r = run_tool("publish", "--lesson", str(lesson))
            self.assertEqual(code, 2)
            self.assertIn("Run build-steps", r["refused"])

    def test_a_broken_version_2_plan_is_refused_with_what_to_change(self):
        lesson = self.copy("red-sailboat")
        plan = json.loads((lesson / "plan.json").read_text(encoding="utf-8"))
        plan["stages"][0]["steps"][0]["paints"] = ["mauve"]
        (lesson / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        for tool in ("mix", "publish"):
            code, r = run_tool(tool, "--lesson", str(lesson))
            self.assertEqual(code, 2)
            self.assertTrue(re.search(r"fix plan.json first: .*'mauve' isn't in paints", r["refused"]), r)


if __name__ == "__main__":
    unittest.main()
