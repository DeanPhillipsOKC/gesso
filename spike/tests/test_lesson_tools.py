"""Tests for render-step and publish (#10), with a fake image client.

    python -m unittest discover spike/tests
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402

import tools  # noqa: E402
from test_render import FakeClient  # noqa: E402


def step(id_, covers=False):
    return {"id": id_, "name": f"Paint the {id_}", "paints": id_, "looks_like": f"{id_} painted", "covers_canvas": covers,
            "colors": ["Sky blue"], "brushes": "1 inch flat", "how": ["Paint it"], "watch_out": ["Don't rush"]}


class LessonToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = tools.CACHE_DIR
        tools.CACHE_DIR = self.tmp / "cache"
        self.lesson = self.tmp / "lesson"
        self.lesson.mkdir()
        Image.new("RGB", (40, 60), (90, 140, 220)).save(self.lesson / "99_finish.png")
        plan = {
            "photo": "photos/does-not-matter.jpg", "technique": "techniques/acrylic-paint-along-beginner.yaml",
            "quality": "low", "subject": "a sky", "focal_point": "the sun", "light": "from the left",
            "components": ["sky", "hill", "tree"],
            "paints": [{"name": "Sky blue", "recipe": "white and blue", "hex": "#5a8cdc", "used_for": "sky",
                        "sample_x": 0.5, "sample_y": 0.2}],
            "steps": [step("sky"), step("hill"), step("tree", True)],
        }
        (self.lesson / "plan.json").write_text(json.dumps(plan))
        self.client = FakeClient()

    def tearDown(self):
        tools.CACHE_DIR = self.cache

    def run_tool(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = tools.main(list(argv), client=self.client)
        return code, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_parallel_renders_each_step_and_makes_canvas(self):
        code, r = self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill",
                                "--why-not-filter", "no filter removes later parts yet")
        self.assertEqual(code, 0)
        self.assertEqual(self.client.images.calls, 2)
        self.assertTrue((self.lesson / "01_sky.png").exists())
        self.assertTrue((self.lesson / "02_hill.png").exists())
        self.assertTrue((self.lesson / "00_canvas.png").exists())

    def test_requires_reason(self):
        code, r = self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky")
        self.assertEqual(code, 2)
        self.assertEqual(self.client.images.calls, 0)

    def test_last_step_and_unknown_ids_refuse(self):
        for ids in (["tree"], ["nope"]):
            code, _ = self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", *ids, "--why-not-filter", "x")
            self.assertEqual(code, 2)
        self.assertEqual(self.client.images.calls, 0)

    def test_parallel_cap_is_shared(self):
        # $0.10 fits one low render (estimated $0.07) but not two at once.
        code, r = self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill",
                                "--why-not-filter", "x", "--max-cost", "0.10")
        self.assertEqual(code, 0)
        self.assertEqual(self.client.images.calls, 1)
        self.assertEqual(sum(1 for s in r["steps"] if "refused" in s), 1)

    def test_anchored_needs_next_step(self):
        code, r = self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "--mode", "anchored",
                                "--why-not-filter", "x")
        self.assertIn("refused", r["steps"][0])
        code, r = self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--mode", "anchored",
                                "--why-not-filter", "x")
        self.assertTrue(all("refused" not in s for s in r["steps"]))  # hill first (from the finish), then sky from hill

    def test_publish_builds_html_with_sources(self):
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        text = {"steps": [{"stage_id": "sky", "what_to_do": ["Blend the sky"], "mixes": [], "watch_out": [], "paint_notes": [],
                           "made_with": "render", "reason": "x"},
                          {"stage_id": "hill", "what_to_do": ["Block the hill"], "mixes": [], "watch_out": [], "paint_notes": [],
                           "made_with": "filter:simplify", "reason": "flat shape"}]}
        (self.lesson / "text.json").write_text(json.dumps(text))
        code, r = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertEqual(code, 0)
        html = (self.lesson / "lesson.html").read_text(encoding="utf-8")
        self.assertIn("Blend the sky", html)
        self.assertEqual(r["steps_by_source"], {"render": 2, "filter": 1})
        self.assertEqual(r["paid_renders"], 2)

    def test_publish_exports_a_walkthrough_embed(self):
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        text = {"steps": [{"stage_id": "sky", "summary": "Paint the sky.", "what_to_do": ["Blend it. Then wait."]},
                          {"stage_id": "hill", "what_to_do": ["Block the hill in one go. Keep it flat."]}]}
        (self.lesson / "text.json").write_text(json.dumps(text))
        code, r = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertEqual(code, 0)
        data = json.loads((self.lesson / "embed" / "lesson.json").read_text(encoding="utf-8"))
        self.assertEqual([s["summary"] for s in data["steps"][:2]], ["Paint the sky.", "Block the hill in one go."])
        self.assertEqual(data["steps"][0]["paints"][0]["first_step"], 1)
        self.assertEqual(data["steps"][0]["brushes"][0]["kind"], "flat")
        self.assertTrue(data["gesso"]["version"].startswith("POC "))
        self.assertIn("Made with Gesso POC", (self.lesson / "lesson.html").read_text(encoding="utf-8"))
        self.assertIsNone(r["previous_version"])  # first publish
        code, r = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertEqual(r["previous_version"], data["gesso"]["version"])
        for s in data["steps"]:
            self.assertTrue((self.lesson / "embed" / s["image"]).exists())
            self.assertTrue((self.lesson / "embed" / s["thumb"]).exists())

    def test_publish_shows_text_check_issues(self):
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        (self.lesson / "review.json").write_text(json.dumps({"text_issues": [
            {"step_id": "hill", "kind": "flat", "problem": "One green for a two-tone hill", "fix": "x", "action": "fixed"}]}))
        self.run_tool("publish", "--lesson", str(self.lesson))
        html = (self.lesson / "lesson.html").read_text(encoding="utf-8")
        self.assertIn("Text check: flat", html)
        self.assertIn("One green for a two-tone hill", html)

    def test_publish_lists_paints_named_but_not_listed(self):
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        plan = json.loads((self.lesson / "plan.json").read_text())
        plan["paints"].append({"name": "Coral cloud", "recipe": "red and white", "hex": "#e88070", "used_for": "clouds",
                               "sample_x": 0.5, "sample_y": 0.5})
        (self.lesson / "plan.json").write_text(json.dumps(plan))
        text = {"steps": [{"stage_id": "sky", "what_to_do": ["Blend Sky blue into Coral cloud."],
                           "values": [{"value": "dark", "paint": "Coral cloud", "where": "low"}]}]}
        (self.lesson / "text.json").write_text(json.dumps(text))
        code, r = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertIn({"id": "sky", "paint": "Coral cloud"}, r["paints_not_listed"])
        self.assertNotIn({"id": "sky", "paint": "Sky blue"}, r["paints_not_listed"])

    def test_owner_palette_mixes_from_their_tubes_and_lists_only_the_used_ones(self):
        import yaml
        import mixing
        self.addCleanup(mixing.CUSTOM.clear)  # registered tubes are process-wide; don't leak into other tests
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        plan = json.loads((self.lesson / "plan.json").read_text())
        plan["palette"] = "owner"
        (self.lesson / "plan.json").write_text(json.dumps(plan))
        code, r = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertEqual(code, 0)
        data = json.loads((self.lesson / "lesson.json").read_text(encoding="utf-8"))
        owned = [t["name"] for t in yaml.safe_load((tools.ROOT / "palettes" / "owner.yaml").read_text())["tubes"]]
        parts = data["photo_read"]["mixes"][0]["mix"]["parts"]
        self.assertTrue(set(parts) <= set(owned))
        self.assertTrue(0 < len(data["tubes"]) <= len(parts))  # only the tubes the recipes use
        self.assertEqual(data["palette_name"], "The owner's paints")

    def test_split_texture_inserts_passes_and_renumbers(self):
        import numpy as np
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        rng = np.random.default_rng(3)
        flat = np.full((60, 40, 3), (90, 70, 170), np.uint8)
        dabs = np.clip(flat + rng.integers(-60, 60, flat.shape), 0, 255).astype(np.uint8)  # heavy texture
        Image.fromarray(flat).save(self.lesson / "02_hill.png")
        Image.fromarray(dabs).save(self.lesson / "99_finish.png")
        code, r = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertTrue(any(j["step"] == "finish" for j in r["texture_jumps"]))
        code, r = self.run_tool("split-texture", "--lesson", str(self.lesson), "--step", "hill", "--ids", "hill-dark",
                                "--names", "Dab the dark marks")
        self.assertEqual(code, 0)
        self.assertEqual(r["inserted"], ["02_hill-dark.png"])
        self.assertTrue((self.lesson / "03_hill.png").exists())
        ids = [s["id"] for s in json.loads((self.lesson / "plan.json").read_text())["steps"]]
        self.assertEqual(ids, ["sky", "hill-dark", "hill", "tree"])
        new = json.loads((self.lesson / "plan.json").read_text())["steps"][1]
        self.assertEqual(new["colors"], [])  # its own pass, not a copy of the parent's
        self.assertIn("darkest marks", new["looks_like"])
        code, r = self.run_tool("canvas-view", str(self.lesson / "02_hill-dark.png"), "--lesson", str(self.lesson))
        self.assertEqual(code, 0)  # a full path works

    def test_values_table_shows_depth(self):
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        text = {"steps": [{"stage_id": "sky", "what_to_do": ["Paint the sky."], "values": [
            {"value": "dark", "paint": "Sky blue", "where": "the top"}, {"value": "light", "paint": "Glow", "where": "low"}]}]}
        (self.lesson / "text.json").write_text(json.dumps(text))
        self.run_tool("publish", "--lesson", str(self.lesson))
        html = (self.lesson / "lesson.html").read_text(encoding="utf-8")
        self.assertIn('<table class="values">', html)
        self.assertIn("the top", html)
        data = json.loads((self.lesson / "embed" / "lesson.json").read_text(encoding="utf-8"))
        self.assertEqual(data["steps"][0]["values"][0]["value"], "dark")

    def test_publish_lists_long_steps(self):
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        text = {"steps": [{"stage_id": "sky", "what_to_do": ["word " * 120]}, {"stage_id": "hill", "what_to_do": ["Short."]}]}
        (self.lesson / "text.json").write_text(json.dumps(text))
        code, r = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertEqual(r["long_steps"], [{"id": "sky", "words": 120}])
        self.assertEqual(r["long_instructions"], [{"id": "sky", "n": 1, "words": 120}])

    def test_preview_with_no_diagrams_says_why(self):
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        self.run_tool("publish", "--lesson", str(self.lesson))
        code, r = self.run_tool("preview-diagrams", "--lesson", str(self.lesson))
        self.assertIn("No diagrams in lesson.json", r["note"])

    def test_publish_crops_steps_to_the_canvas(self):
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        code, r = self.run_tool("fit-canvas", str(self.lesson / "99_finish.png"), "--lesson", str(self.lesson),
                                "--canvas", "11x14", "--why", "test")
        self.assertEqual(code, 0)
        self.assertTrue((self.lesson / "canvas.json").exists())
        code, r = self.run_tool("publish", "--lesson", str(self.lesson))
        data = json.loads((self.lesson / "lesson.json").read_text(encoding="utf-8"))
        self.assertEqual(data["canvas"]["w_in"], 11)
        if data["stages"][0]["image"].startswith("canvas/"):  # the 40x60 test finish sits in a 2:3 frame
            self.assertTrue((self.lesson / data["stages"][0]["image"]).exists())
        html = (self.lesson / "lesson.html").read_text(encoding="utf-8")
        self.assertIn("Canvas: <b>11 x 14 in</b>", html)
        self.assertIn("each 10% is 1.1 in", html)

    def test_mix_computes_recipes_and_every_step_lists_its_paints(self):
        code, r = self.run_tool("mix", "--lesson", str(self.lesson))
        self.assertEqual(code, 0)
        self.assertEqual(r["paints"][0]["your_recipe"], "white and blue")
        self.assertIn("ultramarine", r["paints"][0]["recipe"])
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        self.run_tool("publish", "--lesson", str(self.lesson))
        data = json.loads((self.lesson / "lesson.json").read_text(encoding="utf-8"))
        sky = data["photo_read"]["mixes"][0]
        self.assertEqual(sky["guess_recipe"], "white and blue")
        self.assertEqual(sky["recipe"], sky["mix"]["text"])
        html = (self.lesson / "lesson.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('<details class="mixfor"'), 3)  # Sky blue is on all three steps
        self.assertEqual(html.count('class="new"'), 1)  # new only where it's first needed
        self.assertIn("First needed in step 1", html)
        self.assertIn("How the paint recipes were worked out", html)

    def test_publish_shows_the_reasoning_folded_away(self):
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "no mask yet")
        notes = {"read": "Mostly sky.", "order": "Back to front.", "steps": {"sky": "The sky is behind everything."},
                 "technique": {"why": "Simple layers.", "considered": [{"name": "Block in", "why_not": "Too few values."}]},
                 "filters": [{"label": "Reference", "tool": "simplify", "image": "00_canvas.png", "why": "flatten it",
                              "verdict": "kept"}],
                 "learned": ["Composite the sky."]}
        (self.lesson / "notes.json").write_text(json.dumps(notes))
        (self.lesson / "review.json").write_text(json.dumps({"review_issues": [
            {"round": 1, "step_id": "sky", "problem": "A smudge.", "action": "left"}]}))
        code, _ = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertEqual(code, 0)
        html = (self.lesson / "lesson-artifact.html").read_text(encoding="utf-8")
        self.assertIn('id="behind"', html)
        for text in ("The sky is behind everything.", "Too few values.", "no mask yet", "Composite the sky.", "A smudge."):
            self.assertIn(text, html)
        self.assertEqual(html.count('<details class="why">'), 2)  # sky and hill; the finish has nothing logged
        self.assertNotIn("<details open", html)  # nothing unfolds on its own

    def test_publish_explains_diagrams_and_flags_unexplained_ones(self):
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        shape = {"stages": [{"caption": "An oval", "add": [{"ellipse": [50, 50, 20, 30]}]}]}
        text = {"steps": [{"stage_id": "sky", "what_to_do": ["Blend"], "construct": shape},
                          {"stage_id": "hill", "what_to_do": ["Block"], "construct": shape}]}
        (self.lesson / "text.json").write_text(json.dumps(text))
        notes = {"beginner_check": {"summary": "One shaped object.",
                                    "diagrams": {"sky": {"noticed": "The lumpy outline.", "pieces": "An oval first.",
                                                         "source": "beginner check"}},
                                    "no_diagram": {}}}
        (self.lesson / "notes.json").write_text(json.dumps(notes))
        code, r = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertEqual(code, 0)
        self.assertEqual(r["diagrams"], 2)
        self.assertEqual(r["undocumented_diagrams"], ["hill"])
        html = (self.lesson / "lesson-artifact.html").read_text(encoding="utf-8")
        for text in ("The lumpy outline.", "An oval first.", "Where Claude drew diagrams", "Diagrams (1)"):
            self.assertIn(text, html)

    def test_preview_diagrams_needs_publish_then_draws_each_one(self):
        code, r = self.run_tool("preview-diagrams", "--lesson", str(self.lesson))
        self.assertEqual(code, 2)  # no lesson.json yet
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        shape = {"stages": [{"caption": "An oval", "add": [{"ellipse": [50, 50, 20, 30]}]}]}
        broken = {"stages": [{"add": [{"path": "not a path"}]}]}
        (self.lesson / "text.json").write_text(json.dumps({"steps": [
            {"stage_id": "sky", "what_to_do": ["x"], "construct": shape},
            {"stage_id": "hill", "what_to_do": ["x"], "construct": broken}]}))
        self.run_tool("publish", "--lesson", str(self.lesson))
        code, r = self.run_tool("preview-diagrams", "--lesson", str(self.lesson))
        self.assertEqual(code, 0)
        self.assertEqual(r["diagrams"], 2)
        html = Path(r["html"]).read_text(encoding="utf-8")
        self.assertIn("An oval", html)
        self.assertIn("This spec is broken", html)

    def test_publish_refuses_missing_images(self):
        code, r = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
