"""The run trace (#165): wall time per skill step, split into Claude, tools and renders, from a transcript."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "experiments" / "bench"))

import run_trace  # noqa: E402

RUN = "chickadee_skill_20261116-191619"
T0 = dt.datetime(2026, 11, 16, 19, 16, 0, tzinfo=dt.timezone.utc)


class Transcript:
    """A made-up Claude Code transcript: tool calls and results at given seconds from T0."""

    def __init__(self):
        self.rows = []
        self.n = 0

    def at(self, s: float) -> str:
        return (T0 + dt.timedelta(seconds=s)).isoformat().replace("+00:00", "Z")

    def user(self, s, text):
        self.rows.append({"type": "user", "timestamp": self.at(s), "message": {"role": "user", "content": text}})

    def call(self, s, took, name, inp, result=""):
        self.n += 1
        tid = f"toolu_{self.n}"
        self.rows.append({"type": "assistant", "timestamp": self.at(s), "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tid, "name": name, "input": inp}]}})
        self.rows.append({"type": "user", "timestamp": self.at(s + took), "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tid, "content": result}]}})

    def bash(self, s, took, command, result=""):
        self.call(s, took, "Bash", {"command": command}, result)

    def write(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(r) for r in self.rows) + "\n", encoding="utf-8")


def run_transcript() -> Transcript:
    t = Transcript()
    L = f"output/{RUN}"
    t.user(0, "Rerun the lesson for photos/chickadee.jpg")
    t.call(2, 0, "Skill", {"skill": "paint-lesson", "args": "photos/chickadee.jpg"}, "Launching skill")
    t.bash(4, 1, "cat .claude/skills/paint-lesson/steps/0-setup.md")
    t.bash(10, 1, "L=output/chickadee_skill_$(date +%Y%m%d-%H%M%S); mkdir -p $L", L)
    t.bash(20, 2, f".venv/bin/python spike/tools.py fit-canvas photos/chickadee.jpg --lesson {L}",
           '{"canvas": {}, "problems": [], "seconds": 0.4}')
    # step 1 starts at 30: a render of 30 s inside a 32 s call, then a Read
    t.bash(30, 1, "cat .claude/skills/paint-lesson/steps/1-reference-finish.md")
    t.bash(40, 32, f".venv/bin/python spike/tools.py render --lesson {L} --step finish",
           '  finish: 30s\n{"out": "x", "step": "finish", "cached": false, "cost_usd": 0.0667, "seconds": 30.0}')
    t.call(80, 0.5, "Read", {"file_path": f"/home/user/gesso/{L}/99_finish.png"}, "image")
    # step 2 at 100: two calls at once (10 s and 6 s, overlapping) count 10 s of tool time
    t.call(100, 0.5, "Read", {"file_path": "/home/user/gesso/.claude/skills/paint-lesson/steps/2-parts.md"}, "text")
    t.bash(110, 10, f".venv/bin/python spike/tools.py outline --lesson {L}", '{"problems": [], "seconds": 8.0}')
    t.bash(112, 6, f".venv/bin/python spike/tools.py part-colors --lesson {L}", "{}")
    # a fresh-context review in step 7 is a subagent: tool time
    t.bash(150, 1, "cat .claude/skills/paint-lesson/steps/7-review.md")
    t.call(160, 60, "Agent", {"prompt": f"Review {L}"}, "done")
    t.call(230, 0, "SubagentHandback", {"message": f"sealed {L}"}, "ok")
    return t


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projects = self.tmp / "projects" / "-home-user-gesso"
        run_transcript().write(self.projects / "sess-1" / "subagents" / "agent-a1.jsonl")
        decoy = Transcript()  # the parent session only hands the job out and reads the report
        decoy.user(0, "run the lessons")
        decoy.call(1, 240, "Agent", {"prompt": "Rerun chickadee"}, f"Report: sealed output/{RUN}")
        decoy.write(self.projects / "sess-1.jsonl")
        self.lesson = self.tmp / "output" / RUN
        self.lesson.mkdir(parents=True)
        (self.lesson / "ledger.json").write_text(json.dumps({"calls": [
            {"tool": "render", "step": "finish", "seconds": 30.0, "cost_usd": 0.0667, "cached": False}]}))
        (self.lesson / "sealed.json").write_text("{}")

    def test_finds_the_subagent_transcript_by_the_folder_name(self):
        best, found = run_trace.find(RUN, [self.tmp / "projects"])
        self.assertEqual(best.name, "agent-a1.jsonl")
        self.assertEqual(len(found), 2)
        self.assertEqual(found[1]["calls_naming_it"], 0)

    def test_splits_each_step_into_claude_tools_and_renders(self):
        r = run_trace.trace(self.lesson, [self.tmp / "projects"])
        self.assertEqual(r["phases_from"], "step files")
        self.assertEqual(r["window"]["wall_s"], 230.0)
        ph = {p["phase"]: p for p in r["phases"]}
        self.assertEqual(ph[0]["wall_s"], 30.0)
        self.assertEqual(ph[0]["tool_s"], 4.0)  # skill 0 + cat 1 + mkdir 1 + fit-canvas 2
        self.assertEqual(ph[0]["claude_s"], 26.0)
        self.assertEqual(ph[0]["tool_printed_s"], 0.4)
        self.assertEqual((ph[1]["wall_s"], ph[1]["tool_s"], ph[1]["render_s"], ph[1]["tool_other_s"]),
                         (70.0, 33.5, 30.0, 3.5))
        self.assertEqual(ph[1]["renders"], 1)
        self.assertEqual((ph[2]["wall_s"], ph[2]["tool_s"]), (50.0, 10.5))  # the two calls overlap
        self.assertEqual(ph[7]["by_tool_s"]["subagent"], 60.0)
        self.assertEqual(ph[7]["wall_s"], 80.0)
        self.assertEqual(r["totals"]["wall_s"], 230.0)
        self.assertEqual(r["totals"]["render_s"], r["ledger"]["seconds"])
        self.assertEqual(r["warnings"], [])
        self.assertIn("sealed.json", r["file_marks"])
        self.assertIn("2. parts and outlines", run_trace.table(r))

    def test_without_step_files_the_tools_set_the_steps(self):
        t = Transcript()
        L = f"output/{RUN}"
        t.bash(0, 1, f"spike/tools.py fit-canvas p --lesson {L}")
        t.bash(10, 1, f"spike/tools.py render --lesson {L} --step finish", '{"step": "finish", "cached": false, "seconds": 1.0}')
        t.bash(20, 1, f"spike/tools.py outline --lesson {L}")
        t.bash(30, 1, f"spike/tools.py fit-canvas p --lesson {L}")  # going back doesn't move the step back
        t.bash(40, 1, f"spike/tools.py publish --lesson {L} --final")
        path = self.tmp / "main.jsonl"
        t.write(path)
        r = run_trace.trace(self.lesson, transcript=path)
        self.assertEqual(r["phases_from"], "tool names")
        walls = {p["phase"]: p["wall_s"] for p in r["phases"] if p["wall_s"]}
        self.assertEqual(walls, {0: 10.0, 1: 10.0, 2: 20.0, 8: 1.0})
        self.assertEqual(r["phases"][8]["calls"], 1)

    def test_a_main_session_run_ends_at_its_own_end_not_a_later_freeze(self):
        """The review's case: the coordinator freezes the run an hour later in the same session."""
        t = run_transcript()
        t.user(3600, "freeze it")
        t.bash(3610, 1, f".venv/bin/python spike/experiments/bench/bench.py freeze output/{RUN}")
        path = self.projects / "main-session.jsonl"
        t.write(path)
        r = run_trace.trace(self.lesson, transcript=path)
        self.assertEqual(r["window"]["wall_s"], 228.0)  # from the skill's launch at 2 s to the handback at 230
        self.assertEqual(r["phases"][7]["wall_s"], 80.0)
        self.assertTrue(any("later calls name the folder" in w for w in r["warnings"]), r["warnings"])

    def test_a_seal_ends_the_run_and_two_runs_in_one_session_stay_apart(self):
        t = Transcript()
        other = "red-sailboat_skill_20261116-191627"
        for k, run in ((0, other), (1000, RUN)):
            t.call(k + 1, 0, "Skill", {"skill": "paint-lesson", "args": "x"}, "Launching skill")
            t.bash(k + 2, 1, "cat .claude/skills/paint-lesson/steps/0-setup.md")
            t.bash(k + 10, 5, f"spike/tools.py fit-canvas p --lesson output/{run}")
            t.bash(k + 100, 20, f"spike/tools.py publish --lesson output/{run} --final")
        t.bash(1500, 2, f"spike/experiments/bench/run_trace.py output/{RUN}")  # after its seal: not the run
        path = self.tmp / "two-runs.jsonl"
        t.write(path)
        r = run_trace.trace(self.lesson, transcript=path)
        self.assertEqual((r["window"]["start"], r["window"]["wall_s"]), ("2026-11-16T19:32:41Z", 119.0))
        self.assertEqual(r["totals"]["calls"], 4)

    def test_a_background_call_is_counted_apart_until_its_notification(self):
        t = Transcript()
        L = f"output/{RUN}"
        t.call(0, 0, "Skill", {"skill": "paint-lesson", "args": "x"}, "Launching skill")
        t.bash(1, 1, "cat .claude/skills/paint-lesson/steps/2-parts.md")
        t.call(10, 0.1, "Bash", {"command": f"spike/tools.py outline --lesson {L}", "run_in_background": True},
               "Command running in background with ID: b1")
        bg_id = f"toolu_{t.n}"
        t.rows.append({"type": "attachment", "timestamp": t.at(70), "attachment": {
            "type": "queued_command", "prompt": f"<task-notification> <tool-use-id>{bg_id}</tool-use-id> done"}})
        t.bash(80, 2, f"spike/tools.py publish --lesson {L} --final")
        path = self.tmp / "bg.jsonl"
        t.write(path)
        r = run_trace.trace(self.lesson, transcript=path)
        ph = r["phases"][2]
        self.assertEqual((ph["background_calls"], ph["background_s"]), (1, 60.0))
        self.assertEqual(ph["tool_s"], 3.0)  # the cat and the publish, not the background outline
        self.assertTrue(any("background calls" in w for w in r["warnings"]))

    def test_no_transcript(self):
        r = run_trace.trace(self.lesson, [self.tmp / "nowhere"])
        self.assertIsNone(r["transcript"])
        self.assertEqual(r["ledger"]["seconds"], 30.0)
        self.assertIn("no transcript", run_trace.table(r))


if __name__ == "__main__":
    unittest.main()
