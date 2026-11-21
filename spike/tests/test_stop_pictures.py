"""Pipeline v4's third build step (#297; docs/design/pipeline-v4.md, sections 5, 7 and 10): the teaching pictures
follow the stopped pictures, the stretch of a Where outline that is a stop line is a second path the page draws
dashed, the page says how much painting the lesson skips, and lesson.json carries `spared`, `spared_canvas` and
`"pipeline": 4`.

On a made-up scene: a sky that stops at a wavy line. Then the page's two ideas, each turned off alone, and the
stamp. Then (slow) the cow's bench chain against section 7's sizes, and a fixture lesson built with --stops and
without, through step-aids and publish."""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "experiments"))
sys.path.insert(0, str(HERE))

import aids  # noqa: E402
import lessons  # noqa: E402
import page2  # noqa: E402
import site_lessons  # noqa: E402

CANVAS = {"w_in": 16, "h_in": 12}
SIZE = (1000, 750)


def sky(h: int = 240, w: int = 320) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(where the sky shows, where it is laid in full, the line's row a column): a sky laid over the whole canvas
    that shows down to a line about 8 in down (of 12), wobbling half an inch either way."""
    ys, xs = np.indices((h, w))
    line = (8 + 0.5 * np.sin(2 * np.pi * xs[0] / w)) * h / 12
    return ys < line[None], np.ones((h, w), bool), line


def points(path: str) -> np.ndarray:
    return np.array([int(v) for v in re.findall(r"-?\d+", path)]).reshape(-1, 2)


class StopPathTests(unittest.TestCase):
    def test_the_stretch_is_the_line(self):
        shown, full, line = sky()
        d = aids.stop_path(shown, full, SIZE)
        self.assertTrue(d.startswith("M"))
        self.assertNotIn("Z", d)  # open: a stretch, not a shape
        p = points(d)
        # every point is on the line (in page units: 750 is the canvas's height), and it runs nearly edge to edge
        want = np.interp(p[:, 0], np.arange(320) * SIZE[0] / 320, line * SIZE[1] / 240)
        self.assertLess(np.abs(p[:, 1] - want).max(), 6)
        self.assertLess(p[:, 0].min(), 15)
        self.assertGreater(p[:, 0].max(), SIZE[0] - 15)
        # the outline's other sides (the top, the left and right edges above the line) aren't in it
        self.assertGreater(p[:, 1].min(), 7 * SIZE[1] / 12)

    def test_nothing_hidden_no_stretch(self):
        shown, _, _ = sky()
        self.assertEqual(aids.stop_path(shown, shown, SIZE), "")
        self.assertEqual(aids.stop_path(np.zeros_like(shown), np.zeros_like(shown), SIZE), "")

    def test_a_corner_is_too_short_to_dash(self):
        h, w = 240, 320
        shown = np.zeros((h, w), bool)
        shown[40:120, 40:200] = True
        full = shown.copy()
        full[120:122, 196:200] = True  # a sliver hidden under one corner
        self.assertEqual(aids.stop_path(shown, full, SIZE), "")

    def test_make_gives_it_only_with_full_masks(self):
        shown, full, _ = sky()
        h, w = shown.shape
        plan = {"parts": [{"id": "sky", "name": "The sky", "kind": "area"}],
                "paints": [{"id": "blue", "name": "Sky blue", "hex": "#78a0dc"}],
                "stages": [{"id": "s", "name": "Sky", "steps": [{"id": "lay-sky", "name": "Lay the sky", "part": "sky",
                                                                  "show": "full", "paints": ["blue"]}]}]}
        pic = np.full((h, w, 3), 250, np.uint8)
        pic[shown] = (120, 160, 220)
        owner = np.zeros((h, w), np.int32)
        with tempfile.TemporaryDirectory() as d:
            plain = aids.make(plan, [pic], [shown], owner, None, CANVAS, Path(d) / "a", ["01.png"])
            stopped = aids.make(plan, [pic], [shown], owner, None, CANVAS, Path(d) / "b", ["01.png"], full=[full])
            same = aids.make(plan, [pic], [shown], owner, None, CANVAS, Path(d) / "c", ["01.png"], full=[shown])
        self.assertNotIn("stop_path", plain["steps"][0])
        self.assertNotIn("stop_path", same["steps"][0])
        self.assertEqual(stopped["steps"][0]["stop_path"], aids.stop_path(shown, full, tuple(plain["view"])))
        # the outline is of the paint shown either way
        self.assertEqual(stopped["steps"][0]["path"], plain["steps"][0]["path"])


def lesson_with(stop_path: str = "M10 500L500 520 990 500", spared=1.42) -> dict:
    a = {"path": "M0 0 1000 0 1000 500 0 500Z", "where_words": "Inside the outlined area.", "area": 0.5}
    if stop_path:
        a["stop_path"] = stop_path
    out = {"aids": {"view": [1000, 750]}, "stages": [{"name": "Lay the sky", "aids": a}, {"name": "Hills", "aids": a}]}
    if spared is not None:
        out["spared_canvas"] = spared
    return out


class PageTests(unittest.TestCase):
    def test_the_dashed_stretch(self):
        lesson = lesson_with()
        for i in (0, 1):
            svg = page2.where_view(lesson, i)
            self.assertIn('class="stop-line" d="M10 500L500 520 990 500"', svg)
            self.assertIn(f'id="sm-{i + 1}"', svg)  # the solid outline is masked away along it
            self.assertIn(f'mask="url(#sm-{i + 1})"', svg)
        plain = page2.where_view(lesson_with(stop_path=""), 0)
        self.assertNotIn("stop-line", plain)
        self.assertNotIn("sm-1", plain)

    def test_the_line(self):
        self.assertEqual(page2.spared_line(lesson_with(spared=1.42)),
                         '<p class="spared">This lesson skips about 1 1/2 canvases of painting that later layers '
                         'would cover.</p>')
        self.assertEqual(page2._canvases(0.5), "half a canvas")
        self.assertEqual(page2._canvases(0.3), "a quarter of a canvas")
        self.assertEqual(page2._canvases(0.7), "three quarters of a canvas")
        self.assertEqual(page2._canvases(1.0), "a whole canvas")
        self.assertEqual(page2._canvases(2.1), "2 canvases")
        self.assertIn("under an eighth of a canvas", page2.spared_line(lesson_with(spared=0.05)))
        self.assertEqual(page2.spared_line(lesson_with(spared=0.0)), "")  # built with the rule, nothing stopped
        self.assertEqual(page2.spared_line(lesson_with(spared=None)), "")  # an older lesson

    def test_each_turns_off_alone(self):
        lesson = lesson_with()
        with mock.patch.object(page2, "DASHED_STOP", False):
            svg = page2.where_view(lesson, 0)
            self.assertNotIn("stop-line", svg)
            self.assertEqual(svg, page2.where_view(lesson_with(stop_path=""), 0))  # as a lesson without it
            self.assertIn("This lesson skips", page2.spared_line(lesson))
        with mock.patch.object(page2, "SPARED_LINE", False):
            self.assertEqual(page2.spared_line(lesson), "")
            self.assertIn("stop-line", page2.where_view(lesson, 0))


class StampTests(unittest.TestCase):
    def test_kind_reads_pipeline_3_or_more(self):
        stages = [{"made_with": "composite:from-finish"}] * 3
        for p in (3, 4, 5):
            self.assertEqual(site_lessons.kind({"pipeline": p, "stages": stages}), "steps erased back from the finish")
        self.assertEqual(site_lessons.kind({"stages": stages}), "steps cut from the finish")
        self.assertEqual(site_lessons.kind({"pipeline": "4", "stages": stages}), "steps cut from the finish")


def bench(pic: str) -> dict:
    """A bench chain's teaching pictures built with the rule and without, as build-steps --stops (or not) and
    step-aids would make them: {"on", "off" (aids.json), "dirs", "canvas", "shown", "full"}."""
    import cover_margin as cm
    import steps3
    import stops
    from test_stops import BENCH

    L = cm.load(pic)
    base = cm.baseline(L)
    c = json.loads((BENCH / pic / "data" / "canvas.json").read_text())
    z = np.load(BENCH / pic / "chain" / "masks.npz")
    shapes = [z[f"s{n:02d}"] for n in range(len(L["units"]))]
    view = steps3.as_v2(L["plan"], L["units"], [{"core": s, "D": s} for s in shapes], L["hexes"], L["owner_png"],
                        L["P"][-1])
    fr = stops.frame(L["P"][0].shape, c["canvas_box"], c["canvas"])
    worked = stops.work_out(L["plan"], L["units"], L["m"], L["owner_png"], fr)
    laid = stops.lay(base, L["m"], L["units"], worked["want"])
    said = stops.report(L["plan"], L["units"], L["m"], worked, laid, fr)
    shown = [f & ~(h > stops.HIDDEN) for f, h in zip(L["m"], laid["hidden"])]
    shown = [s if s.any() else f for s, f in zip(shown, L["m"])]
    names = [f"{i + 1:02d}.png" for i in range(len(shown))]
    root = Path(tempfile.mkdtemp())
    on = aids.make(view, laid["pictures"], shown, L["owner_png"], c["canvas_box"], c["canvas"], root / "on", names,
                   full=L["m"])
    off = aids.make(view, base, L["m"], L["owner_png"], c["canvas_box"], c["canvas"], root / "off", names)
    return {"on": on, "off": off, "root": root, "canvas": c, "shown": shown, "full": L["m"], "stops": said["stops"]}


def tall(path: str, view: list[int], h_in: float) -> float:
    m = aids.path_mask(path, tuple(view))
    ys = np.nonzero(m.any(1))[0]
    return (ys.max() + 1 - ys.min()) / view[1] * h_in


@lessons.slow
class CowTests(unittest.TestCase):
    """Section 7 on the cow's bench chain (spike/experiments/bench/v31-gate/highland-cow/)."""

    def test_the_cow(self):
        """One test, so the runner builds the cow's pictures once (about ten seconds)."""
        self.b = bench("highland-cow")
        try:
            for part in (self.the_where_outlines, self.the_dashed_stretch_is_each_stopped_layer_s_line,
                         self.the_paint_maps_cover_only_the_shown_paint, self.the_transfer_outline_doesn_t_change):
                with self.subTest(part.__name__):
                    part()
        finally:
            shutil.rmtree(self.b["root"], ignore_errors=True)

    def the_where_outlines(self):
        """The sky's outline goes from 16 in tall to 4 1/4 in, the clouds' from 9 3/4 and 6 in to 4 and 4 1/4 in,
        the far hills' from 13 3/4 in to 4 in; every later step's is as it was."""
        on, off, h = self.b["on"], self.b["off"], self.b["canvas"]["canvas"]["h_in"]
        want = [(16, 4.25), (9.75, 4), (6, 4.25), (13.75, 4)]
        for i, (before, after) in enumerate(want):
            self.assertAlmostEqual(tall(off["steps"][i]["path"], off["view"], h), before, delta=0.25, msg=i + 1)
            self.assertAlmostEqual(tall(on["steps"][i]["path"], on["view"], h), after, delta=0.125, msg=i + 1)
        for a, b in zip(on["steps"][4:], off["steps"][4:]):
            self.assertEqual(a["path"], b["path"], a["id"])
            self.assertEqual(*({k: v for k, v in (x.get("map") or {}).items() if k != "image"} for x in (a, b)), a["id"])
            self.assertEqual((a.get("closeup") or {}).get("box"), (b.get("closeup") or {}).get("box"), a["id"])
            self.assertNotIn("stop_path", a)

    def the_dashed_stretch_is_each_stopped_layer_s_line(self):
        """Steps 1 to 4 have a stop stretch, and it lies along the line build.json gives (its highest to its
        lowest point, from the top edge), give or take the outline's joining."""
        on, h = self.b["on"], self.b["canvas"]["canvas"]["h_in"]
        lines = {n: r["line"] for r in self.b["stops"]["stopped"] for n in r["steps"]}
        self.assertEqual([i + 1 for i, r in enumerate(on["steps"]) if r.get("stop_path")], [1, 2, 3, 4])
        for i in range(4):
            y = points(on["steps"][i]["stop_path"])[:, 1] / on["view"][1] * h
            line = lines[i + 1]
            self.assertGreater(y.min(), line["highest"] - 0.25, i + 1)
            self.assertLess(y.max(), line["lowest"] + 0.125, i + 1)

    def the_paint_maps_cover_only_the_shown_paint(self):
        """Each map's box is the shown paint's, not the whole layer's: the sky's map is about as tall as its 4 1/4
        in, where without the rule it is the whole 16 in."""
        on, off = self.b["on"], self.b["off"]
        h, w = self.b["canvas"]["canvas"]["h_in"], self.b["canvas"]["canvas"]["w_in"]
        for i in (0, 1, 3):
            for data, mask in ((on, self.b["shown"][i]), (off, self.b["full"][i])):
                m = data["steps"][i].get("map")
                self.assertIsNotNone(m, i + 1)
                area = aids.to_canvas(mask, self.b["canvas"]["canvas_box"])
                ys, xs = np.nonzero(area)
                box = ((ys.max() + 1 - ys.min()) / area.shape[0] * h) / ((xs.max() + 1 - xs.min()) / area.shape[1] * w)
                got = m["size"][1] / m["size"][0]
                self.assertAlmostEqual(got, box, delta=0.1 * max(1, box), msg=(i + 1, data is on))
        self.assertLess(on["steps"][0]["map"]["size"][1] / on["steps"][0]["map"]["size"][0], 0.5)

    def the_transfer_outline_doesn_t_change(self):
        on, off = self.b["on"], self.b["off"]
        self.assertEqual(on["transfer"], {**off["transfer"], "image": on["transfer"]["image"]})
        self.assertEqual((self.b["root"] / "on" / "transfer.png").read_bytes(),
                         (self.b["root"] / "off" / "transfer.png").read_bytes())


@lessons.slow
class PublishTests(unittest.TestCase):
    """A fixture lesson (the lavender balloon: its darker ridges and its tree's canopy stop, #295) built with
    --stops and published is stamped pipeline 4 and its page shows the dashed stretch and the line; built without
    it, it is published as before."""

    def test_with_and_without_the_rule(self):
        before = lessons.lesson("lavender-balloon", "published")
        old = json.loads((before / "lesson.json").read_text(encoding="utf-8"))
        self.assertEqual(old["pipeline"], 3)
        self.assertNotIn("spared_canvas", old)
        self.assertTrue(all("spared" not in s for s in old["stages"]))
        aids_json = json.loads((before / "aids" / "aids.json").read_text(encoding="utf-8"))
        self.assertTrue(all("stop_path" not in r for r in aids_json["steps"]))
        page = (before / "lesson-standalone.html").read_text(encoding="utf-8")
        self.assertNotIn('class="stop-line"', page)
        self.assertNotIn('class="spared"', page)

        lesson = lessons.lesson("lavender-balloon", "chained")
        for tool in (("build-steps", "--stops"), ("step-aids",), ("mix",), ("publish",)):
            code, out = lessons.run_tool(tool[0], "--lesson", str(lesson), *tool[1:])
            self.assertEqual(code, 0, (tool, out))
        build = json.loads((lesson / "v3" / "build.json").read_text(encoding="utf-8"))
        data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
        self.assertEqual(data["pipeline"], 4)
        self.assertEqual(data["spared_canvas"], build["spared_canvas"])
        self.assertGreater(data["spared_canvas"], 0)
        self.assertEqual([s["spared"] for s in data["stages"]], [r["spared"] for r in build["rows"]])
        self.assertEqual(site_lessons.kind(data), "steps erased back from the finish")
        stopped = sorted(n for r in build["stops"]["stopped"] for n in r["steps"])
        dashed = [i + 1 for i, s in enumerate(data["stages"]) if s["aids"].get("stop_path")]
        self.assertTrue(dashed)
        self.assertLessEqual(set(dashed), set(stopped))
        page = (lesson / "lesson-standalone.html").read_text(encoding="utf-8")
        self.assertIn('class="stop-line"', page)
        self.assertIn('<p class="spared">This lesson skips under an eighth of a canvas of painting', page)
        shutil.rmtree(lesson)


if __name__ == "__main__":
    unittest.main()
