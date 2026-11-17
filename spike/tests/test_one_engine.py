"""Tests for the engine (#176, spike/engine.py): one long-lived process that runs the tools and rebuilds only what
changed. What it writes must be what each tool writes as its own process, byte for byte; the full proof on the
three fixtures, through `outline` and `publish`, is spike/experiments/v3_one_engine.py (docs/spikes/v3-one-engine.md).
"""

from __future__ import annotations

import copy
import hashlib
import io
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))

import numpy as np  # noqa: E402

import build_steps as bs  # noqa: E402
import engine  # noqa: E402
import lessons  # noqa: E402
import outline as ol  # noqa: E402
import tools  # noqa: E402
from test_pipeline_v2 import scene, scene_plan  # noqa: E402

SPIKE = Path(__file__).resolve().parent.parent
PY = sys.executable


def digest(build) -> str:
    pictures, rows, painted = build
    h = hashlib.sha256(json.dumps(rows, sort_keys=True).encode())
    for a in list(pictures) + list(painted):
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def files(folder: Path) -> dict[str, str]:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


class PartsMemoTests(unittest.TestCase):
    """build_steps.remember_parts: the engine's per-part memo gives the same pictures as building from scratch."""

    def tearDown(self):
        bs.remember_parts(False)

    def scene(self):
        img, parts, _ = scene()
        owner = np.zeros(img.shape[:2], np.int32)
        owner[70:] = 2
        owner[:60][(img[:60] == (240, 150, 60)).all(2)] = 1
        yy, xx = np.mgrid[:120, :160]
        owner[((yy - 68) ** 2 + (xx - 60) ** 2) < 16 ** 2] = 3
        return img, scene_plan(parts), owner

    def test_off_by_default(self):
        self.assertIsNone(bs._parts_memo)

    def test_same_pictures_with_the_memo_and_after_a_change(self):
        img, plan, owner = self.scene()
        changed = copy.deepcopy(plan)
        changed["stages"][1]["steps"][1]["show"] = "full"  # the ball's last step: a stages-only edit
        before = [digest(bs._build(img, p, owner)) for p in (plan, changed)]
        bs.remember_parts(True)
        first = digest(bs._build(img, plan, owner))
        kept = len(bs._parts_memo)
        after = [digest(bs._build(img, p, owner)) for p in (changed, plan)]
        self.assertEqual([first, after[0]], before)
        self.assertEqual(after[1], before[0])
        self.assertEqual(len(bs._parts_memo), kept)  # the change touched no part's paints: nothing new to prepare

    def test_a_paint_change_prepares_only_that_part_again(self):
        img, plan, owner = self.scene()
        bs.remember_parts(True)
        bs._build(img, plan, owner)
        kept = set(bs._parts_memo)
        changed = copy.deepcopy(plan)
        changed["paints"][3]["hex"] = "#c03030"  # the ball's red
        bs.remember_parts(False)
        fresh = digest(bs._build(img, changed, owner))
        bs.remember_parts(True)
        bs._build(img, plan, owner)
        again = digest(bs._build(img, changed, owner))
        self.assertEqual(again, fresh)
        new = set(bs._parts_memo) - kept
        self.assertEqual(len(new), 2, new)  # the ball's prepared paint and its flat coat; the sky's stay


class FakeEncoder:
    def __init__(self):
        self.runs = 0

    def run(self, _, feeds):
        self.runs += 1
        x = feeds["input_image"]
        return [np.full((1, 4, 2, 2), float(x.mean()), np.float32)] + [np.full((1, 2, 2, 3), i, np.float32)
                                                                       for i in range(4)]


class KeptReadingTests(unittest.TestCase):
    """outline.Sam(keep=...): a picture is read once, then from memory or disk, with the same arrays."""

    def sam(self, keep):
        s = object.__new__(ol.Sam)
        s.enc, s.emb, s.keep, s.ort_version, s._last = FakeEncoder(), None, keep, "test", None
        s.reads = {"model": 0, "memory": 0, "disk": 0}
        return s

    def test_read_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            pic = np.random.default_rng(1).integers(0, 255, (30, 40, 3), dtype=np.uint8)
            a = self.sam(Path(tmp))
            a.embed(pic)
            emb, interm = a.emb.copy(), a.interm.copy()
            a.emb = None
            a.embed(pic)  # the same picture: memory
            b = self.sam(Path(tmp))
            b.embed(pic)  # a new engine: disk
            self.assertEqual(a.enc.runs + b.enc.runs, 1)
            self.assertEqual((a.reads, b.reads), ({"model": 1, "memory": 1, "disk": 0}, {"model": 0, "memory": 0, "disk": 1}))
            for s in (a, b):
                self.assertTrue(np.array_equal(s.emb, emb) and np.array_equal(s.interm, interm))
                self.assertEqual(s.shape, (30, 40))
            other = pic.copy()
            other[0, 0] ^= 1
            b.embed(other)  # one pixel changed: read again
            self.assertEqual(b.enc.runs, 1)

    def test_cleanup_skips_files_that_vanish_and_old_temps(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep = Path(tmp)
            for i in range(ol._keep_readings + 2):
                (keep / f"r{i}.npz").write_bytes(b"x")
                os.utime(keep / f"r{i}.npz", (1000 + i, 1000 + i))
            (keep / "gone.npz").symlink_to(keep / "nothing")  # stat fails, as for a file renamed mid-listing
            (keep / "a.1.tmp.npz").write_bytes(b"x")
            os.utime(keep / "a.1.tmp.npz", (10, 10))  # left by a killed write
            (keep / "b.2.tmp.npz").write_bytes(b"x")  # another engine writing now
            ol.prune(keep, now=10 + ol._tmp_stale + 1)
            left = sorted(p.name for p in keep.iterdir())
            self.assertEqual(left, sorted(["b.2.tmp.npz", "gone.npz"] + [f"r{i}.npz" for i in range(2, ol._keep_readings + 2)]))

    def test_a_failed_save_isnt_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocked = Path(tmp) / "file"
            blocked.write_bytes(b"not a folder")
            s = self.sam(blocked)
            pic = np.zeros((10, 10, 3), np.uint8)
            s.embed(pic)  # can't write the reading: still read, and kept in memory
            s.emb = None
            s.embed(pic)
            self.assertEqual((s.enc.runs, s.reads["memory"]), (1, 1))

    def test_without_keep_every_picture_is_read(self):
        s = self.sam(None)
        pic = np.zeros((10, 10, 3), np.uint8)
        s.embed(pic)
        s.embed(pic)
        self.assertEqual(s.enc.runs, 2)
        self.assertEqual(s.reads, {"model": 0, "memory": 0, "disk": 0})


class EngineInProcessTests(unittest.TestCase):
    """Engine.call runs a tool in its own process as tools.py would, and close() puts everything back."""

    def test_call_matches_tools_main_and_close_restores(self):
        import filters

        load = filters.load
        with tempfile.TemporaryDirectory() as tmp:
            e = engine.Engine(readings=Path(tmp) / "readings")
            try:
                self.assertIsNotNone(bs._parts_memo)
                r = e.call(["elements"], os.getcwd(), dict(os.environ))
                bad = e.call(["no-such-tool"], os.getcwd(), dict(os.environ))
                again = e.call(["engine", "status"], os.getcwd(), dict(os.environ))
            finally:
                e.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            tools.main(["elements"])
        strip = lambda s: {k: v for k, v in json.loads(s).items() if k != "seconds"}  # noqa: E731
        self.assertEqual(r["code"], 0)
        self.assertEqual(strip(r["stdout"]), strip(out.getvalue()))
        self.assertEqual(bad["code"], 2)
        self.assertIn("invalid choice", bad["stderr"])
        self.assertEqual(again["code"], 2)
        self.assertIs(filters.load, load)
        self.assertIsNone(bs._parts_memo)
        self.assertIsNone(tools._outline_model)

    def lesson(self, tmp):
        lesson = Path(tmp) / "lesson"
        (lesson / "parts").mkdir(parents=True)
        plan = {"plan_version": 2, "parts": [{"id": "a"}], "paints": [], "stages": [], "subject": "x",
                "technique": "techniques/acrylic-paint-along-beginner.yaml"}
        (lesson / "plan.json").write_text(json.dumps(plan))
        for name in ("99_finish.png", "parts/owner.png", "canvas.json", "text.json"):
            (lesson / name).write_bytes(b"one")
        return lesson, plan

    def bare(self):
        e = object.__new__(engine.Engine)
        e.ran = {}
        return e

    def test_where_the_chain_starts(self):
        with tempfile.TemporaryDirectory() as tmp:
            lesson, plan = self.lesson(tmp)
            e = self.bare()
            self.assertEqual(e.start_of(lesson)[0], "outline")
            for tool in engine.ORDER[:3]:
                e.record(lesson, tool)
            self.assertEqual(e.start_of(lesson)[0], "step-aids")  # the first tool that hasn't run
            for tool in engine.ORDER:
                e.record(lesson, tool)
            self.assertEqual(e.start_of(lesson)[0], "check")
            plan_edits = (("subject", "y", "outline"), ("technique", "techniques/other.yaml", "outline"),
                          ("stages", [{"id": "s"}], "build-steps"), ("paints", [{"id": "p"}], "build-steps"),
                          ("parts", [{"id": "b"}], "outline"))
            for key, value, start in plan_edits:
                (lesson / "plan.json").write_text(json.dumps(dict(plan, **{key: value})))
                self.assertEqual(e.start_of(lesson)[0], start, key)
            (lesson / "plan.json").write_text(json.dumps(plan))
            files = (("99_finish.png", "outline"), ("parts/owner.png", "paints"), ("98_background.png", "build-steps"),
                     ("canvas.json", "step-aids"), ("elements/fur.yaml", "draft-text"), ("text.json", "check"),
                     ("notes.json", "check"))
            for name, start in files:
                path = lesson / name
                was = path.read_bytes() if path.exists() else None
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b"two")
                self.assertEqual(e.start_of(lesson)[0], start, name)
                path.unlink() if was is None else path.write_bytes(was)
            self.assertEqual(e.start_of(lesson)[0], "check")

    def test_a_failed_call_doesnt_count_as_run(self):
        """The review of #184: parts edited, then outline refuses (or any tool fails): the next chain must still start
        at outline, not at check."""
        with tempfile.TemporaryDirectory() as tmp:
            lesson, plan = self.lesson(tmp)
            e = engine.Engine(readings=Path(tmp) / "readings")
            try:
                for tool in engine.ORDER:
                    e.record(lesson, tool)
                (lesson / "plan.json").write_text(json.dumps(dict(plan, parts=[{"id": "b"}])))  # no kind: refused
                for tool in ("outline", "build-steps", "check"):  # refused, refused, and check runs (it lists them)
                    r = e.call([tool, "--lesson", str(lesson)], os.getcwd(), dict(os.environ))
                    self.assertEqual(r["code"] != 0, tool != "check", (tool, r["stdout"]))
                    self.assertEqual(e.start_of(lesson)[0], "outline", tool)
            finally:
                e.close()


    def test_an_edit_during_a_call_still_counts(self):
        """The second review of #184: what a tool read is taken before it runs, so an edit made while it runs (here
        build-steps' stand-in changes the stages) sends the next chain back to it."""
        with tempfile.TemporaryDirectory() as tmp:
            lesson, plan = self.lesson(tmp)
            e = engine.Engine(readings=Path(tmp) / "readings")
            real = e.tools.main
            try:
                for tool in engine.ORDER:
                    e.record(lesson, tool)

                def edits_stages(argv):
                    (lesson / "plan.json").write_text(json.dumps(dict(plan, stages=[{"id": "late"}])))
                    return 0
                e.tools.main = edits_stages
                r = e.call(["build-steps", "--lesson", str(lesson)], os.getcwd(), dict(os.environ))
                self.assertEqual(r["code"], 0)
                self.assertEqual(e.start_of(lesson)[0], "build-steps")
            finally:
                e.tools.main = real
                e.close()

    def test_a_palette_named_by_path_is_tracked(self):
        """The second review of #184: tools.load_palette takes "<path>.yaml" from the repo root, outside palettes/."""
        with tempfile.TemporaryDirectory() as tmp:
            lesson, plan = self.lesson(tmp)
            root = Path(tmp) / "root"
            (root / "mine").mkdir(parents=True)
            (root / "mine" / "tubes.yaml").write_text("one")
            (lesson / "plan.json").write_text(json.dumps(dict(plan, palette="mine/tubes.yaml")))
            with mock.patch.object(engine, "ROOT", root):
                e = self.bare()
                for tool in engine.ORDER:
                    e.record(lesson, tool)
                self.assertEqual(e.start_of(lesson)[0], "check")
                (root / "mine" / "tubes.yaml").write_text("two")
                self.assertNotEqual(e.start_of(lesson)[0], "check")


class EngineClientTests(unittest.TestCase):
    """The client, as its own process."""

    def test_no_engine_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run([PY, str(SPIKE / "tools.py"), "engine", "call", "--state", str(Path(tmp) / "none.json"),
                                "check", "--lesson", tmp], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("no engine is running", json.loads(p.stdout)["refused"])


@lessons.slow
class EngineServerRoundTripTests(unittest.TestCase):
    """A server started as its own process answers like the tool does, then stops (seconds: it loads every module)."""

    def test_call_status_and_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "engine.json"
            server = subprocess.Popen([PY, str(SPIKE / "tools.py"), "engine", "serve", "--state", str(state),
                                       "--readings", str(Path(tmp) / "readings")],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.time() + 60
                while not state.exists() and time.time() < deadline and server.poll() is None:
                    time.sleep(0.05)
                run = lambda *a: subprocess.run([PY, str(SPIKE / "tools.py"), *a], capture_output=True, text=True,  # noqa: E731
                                                timeout=120)
                direct = run("elements")
                via = run("engine", "call", "--state", str(state), "elements")
                self.assertEqual((via.returncode, direct.returncode), (0, 0))
                strip = lambda s: {k: v for k, v in json.loads(s).items() if k != "seconds"}  # noqa: E731
                self.assertEqual(strip(via.stdout), strip(direct.stdout))
                status = json.loads(run("engine", "status", "--state", str(state)).stdout)
                self.assertEqual(status["calls"], 1)
                stop = run("engine", "stop", "--state", str(state))
                self.assertTrue(json.loads(stop.stdout)["stopped"])
                server.wait(timeout=30)
                self.assertFalse(state.exists())
            finally:
                if server.poll() is None:
                    server.kill()


@lessons.slow
class EngineFixtureTests(unittest.TestCase):
    """On a fixture lesson, the engine writes what the tools write without it, and again after a stages edit."""

    CHECKED = ["build-steps", "step-aids", "mix", "draft-text", "check"]  # lessons.py's "checked" stage
    CHAIN = engine.ORDER[engine.ORDER.index("build-steps"):]

    def test_same_files_as_the_tools(self):
        from v3_one_engine import change_stage

        tmp = Path(tempfile.mkdtemp())
        try:
            plain = lessons.lesson("red-sailboat", "checked", into=tmp / "plain")  # the tools, in this process
            via = lessons.lesson("red-sailboat", "outlined", into=tmp / "via")
            e = engine.Engine(readings=tmp / "readings")
            try:
                for tool in self.CHECKED:
                    r = e.call([tool, "--lesson", str(via)], os.getcwd(), dict(os.environ))
                    self.assertEqual(r["code"], 0, (tool, r["stdout"][-500:], r["stderr"][-2000:]))
                self.assertEqual(files(via), files(plain))
                self.assertEqual(e.start_of(via)[0], "outline")  # the engine hasn't seen outline succeed here
                for tool in ("outline", "paints"):  # the fixture's saved outlines and paints stand in for them
                    e.record(via, tool)
                for lesson_ in (plain, via):  # the same stages edit on both
                    path = lesson_ / "plan.json"
                    plan = json.loads(path.read_text())
                    change_stage(plan)
                    path.write_text(json.dumps(plan, indent=1) + "\n")
                chain = e.chain(str(via), os.getcwd(), dict(os.environ), None, "check")
                result = json.loads(chain["stdout"])
                self.assertEqual(result["from"], "build-steps")
                self.assertEqual([x["tool"] for x in result["ran"]], self.CHAIN)
                self.assertEqual(e.start_of(via)[0], "check")  # nothing changed since
            finally:
                e.close()
            for tool in self.CHAIN:
                code, r = lessons.run_tool(tool, "--lesson", str(plain))
                self.assertEqual(code, 0, (tool, r))
            self.assertEqual(files(via), files(plain))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
