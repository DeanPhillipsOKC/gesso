"""Version 2 lessons through build-steps, mix, publish, the seal, the page, and every reader of lesson.json
(issue #65, docs/design/pipeline-v2.md section 13).

Each fixture (fixtures/plans, finishes, owners) is built into a lesson folder once, as `build-steps`, `mix`, and
`publish` would leave it; no renders, no network, no model files.
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import history  # noqa: E402
import tools  # noqa: E402
from test_pipeline_v2 import NAMES, fixture  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
V1 = json.loads((FIX / "expected" / "v1-lesson.json").read_text(encoding="utf-8"))  # what version 1 readers get


def run_tool(*argv) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = tools.main(list(argv))
    return code, json.loads(out.getvalue().strip().splitlines()[-1])


def make_lesson(folder: Path, name: str) -> Path:
    """A version 2 lesson folder from a fixture, as outline would leave it (fixture plan, finish, saved outlines)."""
    finish, plan, owner = fixture(name)
    lesson = folder / f"{name}_skill_20261112-090000"
    (lesson / "parts").mkdir(parents=True)
    (lesson / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    Image.fromarray(finish).save(lesson / "99_finish.png")
    Image.fromarray(owner.astype(np.uint8)).save(lesson / "parts" / "owner.png")
    return lesson


class PublishV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.old_history = os.environ.get("GESSO_HISTORY")
        os.environ["GESSO_HISTORY"] = str(cls.root / "history")
        cls.lessons, cls.results = {}, {}
        for name in NAMES:
            lesson = make_lesson(cls.root, name)
            for tool in ("build-steps", "mix", "publish"):
                code, r = run_tool(tool, "--lesson", str(lesson))
                assert code == 0, (name, tool, r)
                cls.results[(name, tool)] = r
            cls.lessons[name] = lesson

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
                if value is not None and not (key == "canvas" and data[key] is None):  # no canvas.json in a fixture
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

    def test_a_version_1_page_has_no_stage_headings(self):
        from lesson_page import page
        import yaml
        technique = yaml.safe_load((tools.ROOT / "techniques/acrylic-paint-along-beginner.yaml").read_text(encoding="utf-8"))
        html = page(V1, technique, FIX / "v1-lesson")
        self.assertNotIn('class="group"', html)
        self.assertNotIn("h2.group", html)

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
        self.assertIn("Long strokes side to side.", html)
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

    # --- every other reader of lesson.json ---

    def test_history_records_a_version_2_run_like_any_run_with_minutes_total(self):
        for name in NAMES:
            lesson = self.lessons[name]
            rec = json.loads((self.root / "history" / name / lesson.name / "record.json").read_text(encoding="utf-8"))
            p = rec["publishes"][-1]
            self.assertEqual(p["metrics"]["steps"], len(self.data(name)["stages"]))
            self.assertEqual(p["metrics"]["paid_renders"], 0)
            self.assertGreater(p["metrics"]["minutes_total"], 0)  # from 09:00 on 2026-11-12, the folder's time
            self.assertEqual(p["metrics"]["checks"]["long_steps"], 0)
            self.assertTrue((self.root / "history" / name / lesson.name / p["strip"]).exists())
            self.assertEqual({s["made_with"] for s in p["steps"]}, {"composite:from-finish"})
            self.assertEqual(history.digest(lesson, self.data(name)), p["digest"])
        page = (self.root / "history" / "index.html").read_text(encoding="utf-8")
        self.assertIn("min start to publish", page)

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

    def test_publish_before_build_steps_says_to_run_it(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = make_lesson(Path(d), "red-sailboat")
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
