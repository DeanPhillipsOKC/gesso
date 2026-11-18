"""The frozen bench (#165): freeze a sealed run, build lesson folders from it, and get the same bytes every time.

Also holds the made-up lesson folders the other test_bench_* files use (sealed(), published()).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "experiments" / "bench"))
sys.path.insert(0, str(HERE))

import contextlib  # noqa: E402
import io  # noqa: E402
from unittest import mock  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import bench  # noqa: E402
import benchlib  # noqa: E402
import lessons  # noqa: E402

FIX = HERE / "fixtures"
RUN = "chickadee_skill_20261112-090000"
# The JSON files a build of the frozen chickadee makes, by sha256: the same on every machine (#165 review, finding 3).
PINNED = {
    "00_reference_palette.json": "7de225370db338cd4762d8450108cc5085f4f7424a6696c45e77f532e0cfc8c3",
    "bench.json": "c4a63341f9e268cc7c42fe3246c606d827dfb211f693a8fa216110397aa65e10",
    "canvas.json": "2e45e2f5b49e163a44bb75344152c6023eda14b71aa6070e1a7c2190799ef6ec",
    "ledger.json": "4b528af9d3fb5eca6b456b192ee9e563d4ec46efbd78714a7e98c297f8d549ca",
    "notes.json": "49b04dc17358f8746fff75645ef4d1662c94fcfe80a3bf3a4900b2f6628f778b",
    "review.json": "98d9044a0c01c74c1336486902714fc7e7a84aad8dd078d25b04febe69599174",
}


def sealed(root: Path, name: str = "chickadee", beginner: bool = False, run: str = RUN, full: bool = False) -> Path:
    """A made-up sealed run of a fixture, laid out as the skill leaves it: <root>/output/<run>/, with its photo at
    <root>/photos/<name>.jpg (canvas.json's input, relative to the checkout). Small pictures unless `full` (the
    fixture's own size, for running tools on it)."""
    lesson = Path(root) / "output" / run
    lesson.mkdir(parents=True)
    (Path(root) / "photos").mkdir(exist_ok=True)
    finish = Image.open(FIX / "finishes" / "chickadee.jpg").convert("RGB")
    if not full:
        finish = finish.resize((250, 196))
    finish.save(Path(root) / "photos" / f"{name}.jpg", quality=90)
    finish.save(lesson / "99_finish.png")
    finish.save(lesson / "00_canvas_frame.png")
    finish.resize((125, 98)).save(lesson / "00_reference.png")
    (lesson / "00_reference_palette.json").write_bytes(b'{"colors": ["#9c97a8"]}\r\n')  # CRLF, as Windows leaves it
    if beginner:
        finish.resize((125, 98)).resize(finish.size).save(lesson / "00_beginner.png")
    canvas = {"canvas": {"w_in": 14.0, "h_in": 11.0, "orientation": "landscape"}, "canvas_box": [0.0, 0.0, 1.0, 1.0],
              "chosen": "default", "mode": "none", "lost_share": 0.0, "needs_render": False,
              "input": f"photos/{name}.jpg", "frame": f"output/{run}/00_canvas_frame.png", "why": "test"}
    (lesson / "canvas.json").write_text(json.dumps(canvas), encoding="utf-8")
    (lesson / "sealed.json").write_text(json.dumps({"at": "2026-11-12T09:30:00", "digest": "x", "version": "POC 1.12.1"}))
    (lesson / "lesson.json").write_text(json.dumps({
        "gesso": {"version": "POC 1.12.1", "commit": "bb39e54", "dirty": False,
                  "made": {"version": "POC 1.12.1", "commit": "bb39e54", "published": "2026-11-12"}},
        "provenance": {"kind": "hands-off", "sealed": "2026-11-12T09:30:00"}}))
    calls = [{"tool": "render", "step": "finish", "model": "m", "quality": "high", "out": f"output/{run}/99_finish.png",
              "seconds": 30.0, "cost_usd": 0.0667, "cached": False},
             {"tool": "render", "step": "background", "model": "m", "quality": "low",
              "out": f"output/{run}/trials/background_raw.png", "seconds": 14.0, "cost_usd": 0.0177, "cached": False}]
    if beginner:
        calls.insert(0, {"tool": "render", "step": "beginner", "model": "m", "quality": "medium",
                         "out": f"output/{run}/00_beginner.png", "seconds": 20.0, "cost_usd": 0.024, "cached": False})
    (lesson / "ledger.json").write_text(json.dumps({"calls": calls, "total_cost_usd": 0.1}))
    notes = {"photo_prep": {"subject": "a bird"}, "canvas_fit": {"canvas": "14 x 11 in"},
             "beginner_version": {"made": beginner, "busy": {"photo": {"fine_texture": 0.004}}},
             "technique": {"why": "paint-along fits"}, "read": "not frozen: written after step 1",
             "filters": [{"image": "trials/simp.png"}]}
    (lesson / "notes.json").write_text(json.dumps(notes))
    (lesson / "review.json").write_text(json.dumps({"finish_issues": ["the first finish turned the sky blue: redone"],
                                                    "text_issues": [{"action": "left as is"}]}))
    photo = "00_beginner.png" if beginner else "00_canvas_frame.png"
    (lesson / "plan.json").write_text(json.dumps({"plan_version": 2, "photo": f"output/{run}/{photo}"}))
    return lesson


def published(root: Path, name: str = "chickadee", run: str = RUN, steps: int = 3) -> Path:
    """A made-up published lesson: lesson.json with a few steps, their canvas pictures, the photo, the finish."""
    lesson = Path(root) / run
    (lesson / "canvas").mkdir(parents=True)
    rng = np.random.default_rng(len(run))
    stages = []
    for i in range(steps):
        img = (rng.random((300, 400, 3)) * 255).astype(np.uint8)
        Image.fromarray(img).save(lesson / "canvas" / f"{i + 1:02d}_s{i + 1}.png")
        stages.append({"id": f"s{i + 1}", "name": f"Paint part {i + 1}", "image": f"canvas/{i + 1:02d}_s{i + 1}.png",
                       "steps": [f"Line one of step {i + 1}.", "Line two."], "tip": "A tip." if i else "",
                       "brushes": "1 inch flat",
                       "colors": [{"name": "Warm gold", "hex": "#e8a661", "recipe": "3 parts white, 1 part yellow"}]})
    data = {"stages": stages, "groups": [{"id": "g", "name": "The sky", "steps": ["s1", "s2"]}],
            "photo_file": "photo.png"}
    (lesson / "lesson.json").write_text(json.dumps(data), encoding="utf-8")
    Image.fromarray((rng.random((300, 400, 3)) * 255).astype(np.uint8)).save(lesson / "photo.png")
    Image.fromarray((rng.random((300, 400, 3)) * 255).astype(np.uint8)).save(lesson / "99_finish.png")
    (lesson / "plan.json").write_text(json.dumps({"secret": "the plan"}))
    (lesson / "canvas.json").write_text(json.dumps({"canvas": {"w_in": 16, "h_in": 12}, "canvas_box": [0, 0, 1, 1]}))
    return lesson


class FreezeBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = self.tmp / "bench"

    def test_freeze_copies_the_files_byte_for_byte_with_a_manifest(self):
        run = sealed(self.tmp, beginner=True)
        out = bench.freeze(run, bench=self.store)
        dest = self.store / "chickadee"
        self.assertEqual(out["picture"], "chickadee")
        for f in ("99_finish.png", "00_canvas_frame.png", "00_beginner.png", "00_reference.png"):
            self.assertEqual((dest / f).read_bytes(), (run / f).read_bytes(), f)
        self.assertEqual((dest / "00_reference_palette.json").read_bytes(), b'{"colors": ["#9c97a8"]}\n')  # LF
        self.assertEqual((dest / "photo.jpg").read_bytes(), (self.tmp / "photos" / "chickadee.jpg").read_bytes())
        m = json.loads((dest / "manifest.json").read_text())
        self.assertEqual(m["source"]["run"], RUN)
        self.assertEqual(m["source"]["version"], "POC 1.12.1")
        self.assertEqual(m["source"]["commit"], "bb39e54")
        self.assertEqual(m["plan_photo"], "00_beginner.png")
        for f, v in m["files"].items():
            self.assertEqual(benchlib.sha256(dest / f), v["sha256"], f)
        # the renders that made frozen files, not the background
        self.assertEqual([r["step"] for r in m["renders"]], ["beginner", "finish"])
        canvas = json.loads((dest / "canvas.json").read_text())
        self.assertEqual((canvas["frame"], canvas["input"]), ("00_canvas_frame.png", "photos/chickadee.jpg"))
        self.assertNotIn(RUN, (dest / "canvas.json").read_text())
        notes = json.loads((dest / "notes0.json").read_text())
        self.assertEqual(sorted(notes), ["beginner_version", "canvas_fit", "photo_prep", "technique"])
        self.assertEqual(json.loads((dest / "review0.json").read_text()),
                         {"finish_issues": ["the first finish turned the sky blue: redone"]})

    def test_building_twice_gives_the_same_bytes(self):
        bench.freeze(sealed(self.tmp, beginner=True), bench=self.store)
        one = bench.build("chickadee", self.tmp / "one", "20261116-100000", bench=self.store)
        two = bench.build("chickadee", self.tmp / "two", "20261117-235959", bench=self.store)
        h1, h2 = bench.folder_hashes(one), bench.folder_hashes(two)
        self.assertEqual(h1, h2)
        self.assertEqual(sorted(h1), ["00_beginner.png", "00_canvas_frame.png", "00_reference.png",
                                      "00_reference_palette.json", "99_finish.png", "bench.json", "canvas.json",
                                      "ledger.json", "notes.json", "review.json"])
        for f in ("bench.json", "canvas.json", "ledger.json", "notes.json", "review.json"):
            self.assertNotIn(b"\r\n", (one / f).read_bytes(), f)
            text = (one / f).read_text()
            self.assertNotIn(one.name, text, f)
            self.assertNotIn(str(self.tmp / "one"), text, f)
        self.assertTrue((one / "trials").is_dir())

    def test_a_built_folder_is_ready_from_the_parts_step(self):
        bench.freeze(sealed(self.tmp), bench=self.store)
        lesson = bench.build("chickadee", self.tmp / "b", "20261116-100000", bench=self.store)
        info = json.loads((lesson / "bench.json").read_text())
        self.assertTrue(info["plan_photo"].endswith("chickadee/00_canvas_frame.png"))
        self.assertTrue(Path(info["plan_photo"]).exists() or (benchlib.ROOT / info["plan_photo"]).exists())
        ledger = json.loads((lesson / "ledger.json").read_text())
        self.assertEqual(ledger["total_cost_usd"], 0.0)
        self.assertEqual([(c["tool"], c["step"], c["cost_usd"]) for c in ledger["calls"]], [("frozen", "finish", 0.0)])
        self.assertEqual(ledger["calls"][0]["baseline"]["seconds"], 30.0)
        notes = json.loads((lesson / "notes.json").read_text())
        self.assertIn("photo", notes["beginner_version"]["busy"])  # what the seal checks
        self.assertNotIn("read", notes)
        self.assertEqual(json.loads((lesson / "review.json").read_text())["finish_issues"],
                         ["the first finish turned the sky blue: redone"])
        self.assertIn("background render", info["varies"])
        import tools
        self.assertEqual(tools.busy_problems(lesson, notes), [])

    def test_refuses_an_unsealed_or_edited_run_and_a_second_freeze(self):
        run = sealed(self.tmp)
        (run / "sealed.json").unlink()
        with self.assertRaises(bench.Refused):
            bench.freeze(run, bench=self.store)
        bench.freeze(run, bench=self.store, allow_unsealed=True)
        with self.assertRaises(bench.Refused):
            bench.freeze(run, bench=self.store, allow_unsealed=True)
        bench.freeze(run, bench=self.store, allow_unsealed=True, force=True)

    def test_build_refuses_changed_frozen_files_and_an_existing_folder(self):
        bench.freeze(sealed(self.tmp), bench=self.store)
        bench.build("chickadee", self.tmp / "b", "20261116-100000", bench=self.store)
        with self.assertRaises(bench.Refused):
            bench.build("chickadee", self.tmp / "b", "20261116-100000", bench=self.store)
        with open(self.store / "chickadee" / "99_finish.png", "ab") as f:
            f.write(b"x")
        self.assertIn("changed", bench.verify(self.store)["chickadee"])
        self.assertEqual(len(bench.verify(self.store)["problems"]), 1)
        with self.assertRaises(bench.Refused):
            bench.build("chickadee", self.tmp / "c", "20261116-100000", bench=self.store)
        with self.assertRaises(bench.Refused):
            bench.build("lake-cabin", self.tmp / "c", bench=self.store)


    def test_a_build_that_wrote_crlf_would_not_match(self):
        """folder_hashes hashes raw bytes, so the pinned-hash test catches a build that writes CRLF."""
        bench.freeze(sealed(self.tmp), bench=self.store)
        one = bench.build("chickadee", self.tmp / "one", "20261116-100000", bench=self.store)
        before = bench.folder_hashes(one)["bench.json"]
        (one / "bench.json").write_bytes((one / "bench.json").read_bytes().replace(b"\n", b"\r\n"))
        self.assertNotEqual(bench.folder_hashes(one)["bench.json"], before)

    def test_a_crlf_checkout_still_verifies_and_builds_the_same_bytes(self):
        """Git for Windows with core.autocrlf turns LF into CRLF in text files on checkout."""
        bench.freeze(sealed(self.tmp), bench=self.store)
        lf = bench.build("chickadee", self.tmp / "lf", "20261116-100000", bench=self.store)
        for f in (self.store / "chickadee").glob("*.json"):
            f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(bench.verify(self.store)["chickadee"], "ok")
        crlf = bench.build("chickadee", self.tmp / "crlf", "20261116-100000", bench=self.store)
        self.assertEqual(bench.folder_hashes(crlf), bench.folder_hashes(lf))
        self.assertEqual((crlf / "canvas.json").read_bytes(), (lf / "canvas.json").read_bytes())

    def test_verify_fails_on_a_changed_or_extra_file(self):
        bench.freeze(sealed(self.tmp), bench=self.store)
        self.assertEqual(bench.verify(self.store)["problems"], [])
        (self.store / "chickadee" / "stray.png").write_bytes(b"x")
        out = bench.verify(self.store)
        self.assertIn("not in the manifest", out["chickadee"])
        with mock.patch.object(bench, "PICTURES_DIR", self.store), mock.patch.object(bench, "verify",
                                                                                     lambda: out):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bench.main(["verify"]), 1)

    def test_the_default_build_is_outside_output_so_publish_keeps_out_of_the_history(self):
        import tools
        self.assertNotIn((benchlib.ROOT / "output").resolve(), bench.DEFAULT_INTO.resolve().parents)
        bench.freeze(sealed(self.tmp), bench=self.store)
        folder = bench.build("chickadee", bench.DEFAULT_INTO, "19990101-000000", bench=self.store,
                             name=f"test-{os.getpid()}-chickadee_skill_19990101-000000")
        self.addCleanup(shutil.rmtree, folder, True)
        with mock.patch.dict(os.environ):
            os.environ.pop("GESSO_HISTORY", None)
            self.assertFalse(tools.history_wanted(folder))
        self.assertTrue(json.loads((folder / "bench.json").read_text())["history"].startswith("spike/"))


class FrozenBenchTests(unittest.TestCase):
    """The bench in the repo: every frozen picture matches its manifest and builds to the same bytes twice."""

    def test_the_frozen_bench_builds_the_same_bytes_twice(self):
        frozen = [p for p in benchlib.PICTURES if (benchlib.PICTURES_DIR / p / "manifest.json").exists()]
        if not frozen:
            self.skipTest("no picture frozen yet")
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.assertEqual({p: v for p, v in bench.verify().items() if p in frozen}, {p: "ok" for p in frozen})
        for p in frozen:
            one = bench.build(p, tmp / "one", "20261116-100000")
            two = bench.build(p, tmp / "two", "20261116-100001")
            self.assertEqual(bench.folder_hashes(one), bench.folder_hashes(two), p)

    def test_the_chickadee_build_matches_its_pinned_hashes(self):
        """The same bytes on any machine, not only twice on this one: a built chickadee's JSON files against fixed
        hashes. Re-pin these only when the chickadee is frozen again on purpose."""
        if not (benchlib.PICTURES_DIR / "chickadee" / "manifest.json").exists():
            self.skipTest("chickadee isn't frozen")
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        got = bench.folder_hashes(bench.build("chickadee", tmp, "20261116-100000"))
        self.assertEqual({f: got[f] for f in PINNED}, PINNED)


@lessons.slow
class BenchToolsTests(unittest.TestCase):
    """A built folder takes the run from the plan on: a version 3 plan written into it passes plan-check, which
    sizes the chain before anything is rendered."""

    def test_plan_check_runs_on_a_built_folder(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        bench.freeze(sealed(tmp, full=True), bench=tmp / "bench")
        lesson = bench.build("chickadee", tmp / "b", "20261116-100000", bench=tmp / "bench")
        info = json.loads((lesson / "bench.json").read_text())
        plan = json.loads((lessons.FIX / "chickadee" / "plan.json").read_text())
        plan["photo"] = info["plan_photo"]
        (lesson / "plan.json").write_text(json.dumps(plan))
        code, out = lessons.run_tool("plan-check", "--lesson", str(lesson))
        self.assertEqual((code, out["problems"]), (0, []), out)
        self.assertEqual(out["renders"], len(out["units"]) - 1)
        self.assertTrue((lesson / "99_finish.png").exists())  # what erase starts from


if __name__ == "__main__":
    unittest.main()
