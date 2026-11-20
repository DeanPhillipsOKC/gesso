"""v3.1's words on the page, in `check` and through the seal (#277, docs/design/pipeline-v3.1.md section 7): a
step's six lines with their labels, the "As in step N" line, the opening and a stage's lines; `check` asking for
the six lines and holding the arc; and a lesson made before v3.1 (a summary and a tip a step) still sealing and
reading as before."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_steps as bs  # noqa: E402
import checks  # noqa: E402
import facts  # noqa: E402
import lesson_embed  # noqa: E402
import lesson_words as lw  # noqa: E402
import lessons  # noqa: E402
import page2  # noqa: E402
import tools  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "lessons"
SIX = [{"kind": "first", "text": "Let the sky dry."}, {"kind": "start", "text": "Start at the roof."},
       {"kind": "back", "step": 2, "text": "The same pull as the wall."}, {"kind": "strokes", "text": "Pull down."},
       {"kind": "inside", "text": "Over the roof."}, {"kind": "leave", "text": "The sky."},
       {"kind": "stop", "text": "Stop when it's red."}]


def run_tool(*argv) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = tools.main(list(argv))
    return code, json.loads(out.getvalue().strip().splitlines()[-1])


class PagePartsTests(unittest.TestCase):
    def test_the_labels_are_the_writers(self):
        self.assertEqual(page2.LABELS, lw.LABELS)

    def test_each_line_has_its_label_in_bold_and_the_back_line_links_to_its_step(self):
        html = page2.six_lines(SIX)
        for label in ("First", "Start", "Strokes", "Where the paint sits", "Leave", "Stop when"):
            self.assertIn(f"<b>{label}:</b>", html)
        self.assertIn('<b>As in <a href="#step-2">step 2</a>:</b> The same pull as the wall.', html)
        self.assertLess(html.index("Start:"), html.index("As in"))  # where check-text --arc put it
        self.assertTrue(page2.written(SIX))
        self.assertFalse(page2.written([{"kind": "load", "text": "Load the brush."}]))  # v3's drafted lines

    def test_the_opening_and_a_stages_lines(self):
        known = {"dotting": {"name": "Dotting"}}
        lesson = {"opening": {"welcome": "A cat.", "light": "From the window.", "road": "Back to front.",
                              "skills": [{"card": "dotting", "steps": [4, 6], "how": "Small dots."}]},
                  "stage_lines": {"front": {"for": "The cat itself.", "end": "A whole cat."}}}
        html = page2.opening(lesson, known)
        for want in ("A cat.", "<h3>The light</h3>", "<h3>What this painting teaches</h3>", "<h3>The way there</h3>",
                     '<a href="#stroke-dotting">Dotting</a>', '<a href="#step-6">6</a>', "Small dots."):
            self.assertIn(want, html)
        g = {"id": "front", "name": "The cat"}
        self.assertIn("The cat itself.", page2.stage_line(lesson, g, "for"))
        stop = page2.stop(g, lesson)
        self.assertLess(stop.index("A whole cat."), stop.index("a good place to stop"))
        self.assertEqual((page2.opening({}, known), page2.stage_line({}, g, "end")), ("", ""))  # a v3 lesson
        self.assertNotIn("stage-end", page2.stop(g))

    def test_a_card_line_with_no_summary_is_the_start_lines_first_sentence(self):
        stage = {"lines": SIX, "steps": [x["text"] for x in SIX]}
        self.assertEqual(lesson_embed.summary_of(stage), "Start at the roof.")  # not "Let the sky dry."
        self.assertEqual(lesson_embed.summary_of({"summary": "Paint the sky.", "lines": SIX}), "Paint the sky.")
        self.assertEqual(lesson_embed.summary_of({"steps": ["Load the brush. Then pull."]}), "Load the brush.")


class TextProblemsTests(unittest.TestCase):
    PLAN = {"stages": [{"steps": [{"id": "roof", "name": "Paint the roof"}]}]}

    def text(self, lines, **more):
        return {"roof": {"lines": [{**x, "edited": True} for x in lines], **more}}

    def test_six_lines_need_no_summary_or_tip_and_first_may_be_empty(self):
        lines = [x for x in SIX if x["kind"] != "first"]
        self.assertEqual(checks.text_problems(self.PLAN, self.text(lines), None), [])

    def test_a_missing_line_fails_unless_check_text_emptied_it(self):
        lines = [x for x in SIX if x["kind"] != "leave"]
        said = checks.text_problems(self.PLAN, self.text(lines), None)
        self.assertEqual(len(said), 1)
        self.assertIn("no Leave line", said[0])
        self.assertEqual(checks.text_problems(self.PLAN, self.text(lines), None, {("roof", "leave")}), [])

    def test_a_line_over_40_words_and_a_v3_summary_beside_the_six_lines(self):
        lines = [dict(x, text=" ".join(["paint"] * 41)) if x["kind"] == "inside" else x for x in SIX]
        said = " | ".join(checks.text_problems(self.PLAN, self.text(lines, summary="Paint it."), None))
        self.assertIn("is 41 words", said)
        self.assertIn("a v3 summary or tip too", said)

    def test_a_v3_step_still_needs_its_summary_and_tip(self):
        drafted = {"roof": {"lines": [{"kind": "load", "text": "Load the brush."}]}}
        said = " | ".join(checks.text_problems(self.PLAN, drafted, None))
        self.assertIn("no summary", said)
        self.assertIn("no tip", said)


def _review_and_notes(lesson: Path, name: str) -> None:
    ids = [s["id"] for s in bs.flat_steps(lessons.built(name)[0])]
    (lesson / "review.json").write_text(json.dumps({"finish_issues": [], "text_issues": []}), encoding="utf-8")
    (lesson / "notes.json").write_text(json.dumps({
        "read": "x", "technique": {"why": "x"}, "order": "x", "steps": {i: "x" for i in ids},
        "beginner_check": {"summary": "x", "diagrams": {}, "no_diagram": {i: "x" for i in ids}},
        "beginner_version": {"made": False, "busy": {"photo": {"fine_texture": 0.004}}}}), encoding="utf-8")


@contextlib.contextmanager
def _history(d: str):
    old = os.environ.get("GESSO_HISTORY")
    os.environ["GESSO_HISTORY"] = str(Path(d) / "history")
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("GESSO_HISTORY", None)
        else:
            os.environ["GESSO_HISTORY"] = old


@lessons.slow
class SealV31Tests(unittest.TestCase):
    """The acceptance: a fixture lesson with v3.1's words passes check and seals, and its page shows the opening,
    the stage lines, the labels and the back lines."""

    def test_a_v31_lesson_seals_and_its_page_shows_the_arc(self):
        with tempfile.TemporaryDirectory() as d, _history(d):
            lesson = lessons.lesson("chickadee", "worded", Path(d))
            code, r = run_tool("check", "--lesson", str(lesson))
            self.assertEqual((code, r["problems"]), (0, []))
            _review_and_notes(lesson, "chickadee")
            code, r = run_tool("publish", "--lesson", str(lesson), "--final")
            self.assertEqual(code, 0, r)
            self.assertTrue((lesson / "sealed.json").exists())
            data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
            text = json.loads((lesson / "text.json").read_text(encoding="utf-8"))
            self.assertEqual(data["opening"], text["opening"])
            self.assertEqual(data["stage_lines"], text["stages"])
            backs = [x for st in data["stages"] for x in st["lines"] if x["kind"] == "back"]
            self.assertTrue(backs)
            self.assertTrue(all(isinstance(x["step"], int) for x in backs))
            self.assertTrue(all(not st["summary"] and not st["tip"] for st in data["stages"]))
            html = (lesson / "lesson.html").read_text(encoding="utf-8")
            start = html.index('id="start"')
            self.assertIn('class="opening"', html[start:start + 4000])
            self.assertIn(text["opening"]["welcome"], html)
            self.assertIn("What this painting teaches", html)
            for st in text["stages"].values():
                self.assertIn(st["for"], html)
            self.assertEqual(html.count('class="stage-for"'), len(text["stages"]))
            self.assertEqual(html.count('class="stage-end"'), len(text["stages"]))
            self.assertEqual(html.count("<b>Stop when:</b>"), len(data["stages"]))
            self.assertEqual(len(re.findall(r'<b>As in <a href="#step-\d+">step \d+</a>:</b>', html)), len(backs))
            self.assertNotIn('<ol class="do">', html)
            self.assertNotIn("<b>Tip:</b>", html)
            embed = json.loads((lesson / "embed" / "lesson.json").read_text(encoding="utf-8"))
            self.assertTrue(all(s["summary"] for s in embed["steps"]))  # the card line falls back to Start

    def test_an_arc_changed_after_its_round_cant_be_sealed(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = lessons.lesson("chickadee", "worded", Path(d))
            path = lesson / "text.json"
            text = json.loads(path.read_text(encoding="utf-8"))
            text["opening"]["light"] += " It comes from the left."
            path.write_text(json.dumps(text), encoding="utf-8")
            code, r = run_tool("check", "--lesson", str(lesson))
            self.assertIn("the arc's opening.light: the opening and a stage's lines say no number and no side word",
                          " | ".join(r["problems"]))
            text.pop("opening")
            path.write_text(json.dumps(text), encoding="utf-8")
            code, r = run_tool("check", "--lesson", str(lesson))
            self.assertIn("text.json has no opening", " | ".join(r["problems"]))

    def test_a_missing_line_and_an_arc_part_the_last_checks_took_out_are_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            lesson = lessons.lesson("chickadee", "worded", Path(d))
            path = lesson / "text.json"
            text = json.loads(path.read_text(encoding="utf-8"))
            sid = text["steps"][0]["stage_id"]
            text["steps"][0]["lines"] = [x for x in text["steps"][0]["lines"] if x["kind"] != "leave"]
            text["opening"].pop("road")
            path.write_text(json.dumps(text), encoding="utf-8")
            code, r = run_tool("check", "--lesson", str(lesson))
            said = " | ".join(r["problems"])
            self.assertIn(f"{sid}: no Leave line", said)
            self.assertIn("the arc's opening.road: missing", said)
            folder = lw.folder_of(lesson)
            st = json.loads((folder / "rounds.json").read_text(encoding="utf-8"))
            st["final"]["emptied"] = [{"id": sid, "kind": "leave"}]
            (folder / "rounds.json").write_text(json.dumps(st), encoding="utf-8")
            (folder / "arc-dropped.json").write_text(json.dumps([{"where": "opening.road", "what": "x"}]),
                                                     encoding="utf-8")
            code, r = run_tool("check", "--lesson", str(lesson))
            self.assertEqual((code, r["problems"]), (0, []))

    def test_the_seal_asks_for_the_arcs_last_check(self):
        with tempfile.TemporaryDirectory() as d, _history(d):
            lesson = lessons.lesson("chickadee", "worded", Path(d))
            _review_and_notes(lesson, "chickadee")
            (lw.folder_of(lesson) / "arc-dropped.json").unlink()
            code, r = run_tool("publish", "--lesson", str(lesson), "--final")
            self.assertEqual(code, 2)
            self.assertIn("run check-text --arc --final", r["refused"])


@lessons.slow
class SealV3Tests(unittest.TestCase):
    """A lesson made before v3.1 (drafted lines, a summary and a tip a step, no arc) still seals and reads as
    before: the page shows what a lesson has."""

    def test_a_v3_lesson_still_seals_and_reads_as_before(self):
        with tempfile.TemporaryDirectory() as d, _history(d):
            lesson = lessons.lesson("chickadee", "checked", Path(d))
            path = lesson / "text.json"
            text = json.loads(path.read_text(encoding="utf-8"))
            words = {sid: w for stage in json.loads((FIX / "chickadee" / "words.json").read_text(
                encoding="utf-8")).values() for sid, w in (stage.get("steps") or {}).items()}
            for t in text["steps"]:  # what v3's check-text --final laid into text.json
                w = words[t["stage_id"]]
                t.update(summary=w["summary"], tip=w["tip"], **({"paint_notes": w["paint_notes"]}
                                                                if w.get("paint_notes") else {}))
            # v3's check-text --final took out what failed against the sheet; the fixture is 0.4 of the run's size
            gone = lw.take_out(text, lw.text_failures(facts.lesson_sheet(lesson)[0], text), [])
            self.assertTrue(all(g["field"].startswith(("tip", "summary")) for g in gone), gone)
            path.write_text(json.dumps(text), encoding="utf-8")
            (lesson / "words").mkdir(exist_ok=True)
            (lesson / "words" / "dropped.json").write_text(json.dumps(gone), encoding="utf-8")
            code, r = run_tool("check", "--lesson", str(lesson))
            self.assertEqual((code, r["problems"]), (0, []))
            _review_and_notes(lesson, "chickadee")
            code, r = run_tool("publish", "--lesson", str(lesson), "--final")
            self.assertEqual(code, 0, r)
            self.assertTrue((lesson / "sealed.json").exists())
            data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
            self.assertNotIn("opening", data)
            self.assertNotIn("stage_lines", data)
            html = (lesson / "lesson.html").read_text(encoding="utf-8")
            self.assertEqual(html.count('<ol class="do">'), len(data["stages"]))
            self.assertEqual(html.count("<b>Tip:</b>"), len(data["stages"]))
            for gone in ('class="opening"', 'class="stage-for"', 'class="stage-end"', '<ul class="plain six">'):
                self.assertNotIn(gone, html)
            embed = json.loads((lesson / "embed" / "lesson.json").read_text(encoding="utf-8"))
            self.assertEqual([s["summary"] for s in embed["steps"]], [st["summary"] for st in data["stages"]])


if __name__ == "__main__":
    unittest.main()
