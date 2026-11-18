"""Tests for the chain of a version 3 lesson (spike/erase3.py, `erase`; docs/design/pipeline-v3.md section 6): what
each render is asked for, the guard, the second laying that keeps a blocked-in thing's renders whole, asking
again, and the tool. A made-up scene and a stand-in for the image model: no renders, no network, no model files."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import erase3  # noqa: E402
import lessons  # noqa: E402
import from_finish as ff  # noqa: E402
import plan3  # noqa: E402
import tools  # noqa: E402
from test_plan3 import plan, step  # noqa: E402
from test_render import FakeClient  # noqa: E402

H, W = 320, 480
CANVAS = np.array(ff.CANVAS, np.uint8)
SKY, RUG, CAT, SHADOW, PALE, EYE = (150, 190, 230), (165, 55, 45), (128, 128, 128), (60, 44, 36), (205, 205, 205), (20, 20, 20)


def box(y0, y1, x0, x1) -> np.ndarray:
    m = np.zeros((H, W), bool)
    m[y0:y1, x0:x1] = True
    return m


WHERE = {"sky": box(0, 150, 0, W), "rug": box(190, 300, 60, 420), "cat": box(120, 250, 170, 330),
         "rug-shadow": box(270, 300, 60, 420), "cat-shadow": box(215, 250, 170, 330), "light": box(125, 150, 200, 300),
         "eyes": box(160, 175, 215, 285)}


def pictures() -> list[np.ndarray]:
    """The made-up scene after each unit of test_plan3's plan: sky, rug, cat, the shadows (and the cat's light,
    one unit of two steps), the cat's eyes."""
    out = []
    img = np.empty((H, W, 3), np.uint8)
    img[:] = CANVAS
    for layers in ([("sky", SKY)], [("rug", RUG)], [("cat", CAT)],
                   [("rug-shadow", SHADOW), ("cat-shadow", SHADOW), ("light", PALE)], [("eyes", EYE)]):
        for name, color in layers:
            img[WHERE[name]] = color
        out.append(img.copy())
    return out


def striped() -> np.ndarray:
    """A render that was to take the cat out and left it standing in stripes, like trunks."""
    scene = pictures()
    out = scene[1].copy()
    for x in range(170, 330, 30):
        out[:, x:x + 12] = scene[2][:, x:x + 12]
    return out


class Model:
    """Stands in for the image model: asked to erase unit n, it answers with the scene before unit n."""

    def __init__(self, answers: dict[str, np.ndarray] | None = None, fail_at: str | None = None):
        self.calls: list[tuple[str, str, bool]] = []
        self.answers = answers or {}
        self.scene = pictures()
        self.fail_at = fail_at

    def __call__(self, name, src, prompt, fresh):
        if name == self.fail_at:
            raise RuntimeError("the cost cap")
        self.calls.append((name, prompt, fresh))
        n = int(name[1:3])
        got = self.answers.get(name, self.scene[n - 1])
        return got.copy(), {"seconds": 1.0, "cost_usd": 0.02, "cached": False}


def chain(tmp, model=None, p=None, **more) -> tuple[dict, Model]:
    model = model or Model()
    Image.fromarray(pictures()[-1]).save(Path(tmp) / "99_finish.png")
    return erase3.run(Path(tmp), p or plan(), pictures()[-1], model, **more), model


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan()
        self.us = plan3.units(self.plan)

    def ask(self, n, why=()) -> str:
        return erase3.request(self.plan, self.us, n, why)

    def test_a_thing_on_bare_canvas_leaves_bare_canvas_and_names_what_stays(self):
        text = self.ask(1)
        self.assertIn("Remove these things from it completely: the plain red rug.", text)
        self.assertIn("leave bare, unpainted white canvas", text)
        self.assertIn("Everything that stays (The sky) keeps", text)
        self.assertTrue(text.endswith(erase3.END))

    def test_a_thing_on_painted_things_names_what_is_behind_and_what_stays(self):
        text = self.ask(2)
        self.assertIn("completely: the plain gray cat shape.", text)
        # the rug has had only its block-in: it is named as it looks now
        self.assertIn("Behind them there is only this: the plain red rug; The sky.", text)
        self.assertIn("All of this goes: the plain gray cat shape.", text)
        self.assertIn("stay exactly as they are, wherever they can be seen now: The sky; the plain red rug.", text)

    def test_a_later_stage_takes_one_layer_off_and_the_first_one_back_says_what_a_block_in_is(self):
        text = self.ask(3)
        self.assertIn("un-paint only the paint that was laid last, on The rug; The cat.", text)
        self.assertIn("The paint to take off: (1) the rug; the cat. (2) the cat.", text)
        self.assertIn("looked like this: Block in the cat is done. The rug: Block in the rug is done.", text)
        self.assertIn("These stay exactly as they are now: The sky.", text)
        self.assertIn("What is left, the plain red rug, is a block-in and nothing more: one flat coat of a single "
                      "paint, Rug red (a dull red), the same from edge to edge", text)
        self.assertIn("What is left, the plain gray cat shape, is a block-in", text)
        self.assertIn("None of this is painted yet, so none of it may show: the rug; the cat; the cat; the cat.", text)

    def test_a_later_stage_still_lists_what_is_not_painted_yet_but_the_block_in_is_said_once(self):
        text = self.ask(4)
        self.assertNotIn("is a block-in", text)
        self.assertIn("Take all of that layer off", text)
        self.assertIn("None of this is painted yet, so none of it may show: the cat.", text)
        # the cat has had two units by now: its own name, not its plain one. The rug is finished
        self.assertIn("These stay exactly as they are now: The sky; The rug.", text)

    def test_a_thing_is_called_what_the_plan_says_a_request_should_call_it(self):
        self.plan["things"][0]["called"] = "the pale sky"
        self.assertIn("this: the plain red rug; the pale sky.", self.ask(2))

    def test_asking_again_says_what_went_wrong(self):
        self.assertIn(erase3.AGAIN["left"]["go"], self.ask(2, ("left",)))
        self.assertIn(erase3.AGAIN["stray"]["go"], self.ask(1, ("stray",)))
        text = self.ask(4, ("stray", "left"))
        self.assertIn(erase3.AGAIN["left"]["back"] + erase3.AGAIN["stray"]["back"] + erase3.END, text)
        self.assertNotEqual(self.ask(2), self.ask(2, ("left",)))

    def test_what_is_not_there_yet_is_left_out_of_how_the_painting_looked(self):
        self.assertEqual(erase3._state("A flat cow stands on the meadow. No horns yet; the sky is done. No face."),
                         "A flat cow stands on the meadow. the sky is done.")

    def test_what_the_checker_is_told(self):
        a = erase3.asked(self.plan, self.us, 2)
        self.assertEqual((a["look"], a["kind"], a["stays"]), ("U02", "behind", ["The sky", "the plain red rug"]))
        self.assertTrue(a["goes"].startswith("all of: the plain gray cat shape."))
        self.assertTrue(erase3.asked(self.plan, self.us, 4)["goes"].startswith("only the last layer of paint on: The cat."))

    def test_which_renders_are_kept_over_a_whole_thing(self):
        self.assertEqual([erase3.kept_whole(self.plan, self.us, n) for n in range(5)], [[], [], [], [1, 2], [2]])
        del step(self.plan, "block-cat")["block_in"]
        us = plan3.units(self.plan)
        self.assertEqual(erase3.kept_whole(self.plan, us, len(us) - 1), [])


class GuardTests(unittest.TestCase):
    def test_only_what_changed_by_a_lot_is_kept_and_canvas_already_bare_stays(self):
        scene = pictures()
        noisy = scene[1].copy()
        noisy[5:40, 5:60] = np.clip(noisy[5:40, 5:60].astype(int) + 6, 0, 255)  # brushwork drawn again: not a change
        d = erase3.changed(scene[2], noisy)
        self.assertGreater((d & WHERE["cat"]).sum() / WHERE["cat"].sum(), 0.97)
        self.assertEqual(int(d[:100].sum()), 0)
        never = box(0, H, 0, 250)
        self.assertFalse((erase3.changed(scene[2], noisy, never) & never).any())

    def test_the_core_is_the_solid_part_of_a_change_and_solid_fills_holes(self):
        scene = pictures()
        d = erase3.changed(scene[2], scene[1])
        self.assertGreater((erase3.core(scene[1], scene[2], d) & WHERE["cat"]).sum() / WHERE["cat"].sum(), 0.9)
        ring = box(100, 200, 100, 300) & ~box(130, 170, 150, 250)
        self.assertTrue(erase3.solid(ring)[150, 200])
        self.assertFalse(erase3.solid(ring)[50, 50])

    def test_a_bare_unit_becomes_canvas_and_a_unit_on_things_shows_the_render_there_only(self):
        scene = pictures()
        none = np.zeros((H, W), bool)
        out, d = erase3.erase_one(scene[1], scene[0], True, none)
        self.assertTrue((out[d] == CANVAS).all())
        self.assertTrue(np.array_equal(out[~d], scene[1][~d]))
        raw = scene[1].copy()
        raw[:60] = (10, 200, 10)  # the render also repainted the sky far from the cat... by a lot: the guard keeps it
        raw[90:120, :100] = np.clip(raw[90:120, :100].astype(int) + 5, 0, 255)  # ...and a little: it doesn't
        out, d = erase3.erase_one(scene[2], raw, False, none)
        self.assertTrue(np.array_equal(out[90:120, :100], scene[2][90:120, :100]))
        self.assertGreater(float((np.abs(out.astype(int) - scene[1]).max(2)[WHERE["cat"]] < 12).mean()), 0.95)

    def test_a_thing_left_standing_is_measured_beside_what_went(self):
        scene = pictures()
        none = np.zeros((H, W), bool)
        whole = erase3.left_standing(scene[2], scene[1], erase3.changed(scene[2], scene[1]), none)
        half = striped()
        left = erase3.left_standing(scene[2], half, erase3.changed(scene[2], half), none)
        self.assertLess(whole, 0.005)
        self.assertGreater(left, erase3.LEFT)


@lessons.slow
class ChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_the_chain_ends_on_the_finish_starts_on_the_first_unit_and_changes_nothing_else(self):
        r, model = chain(self.tmp)
        ch = erase3.load(Path(self.tmp), plan())
        scene = pictures()
        self.assertTrue(np.array_equal(ch[-1]["P"], scene[-1]))
        self.assertEqual([c[0] for c in model.calls], ["U04", "U03", "U02", "U01"])
        self.assertEqual((r["renders"], r["paid"], r["cost_usd"]), (4, 4, 0.08))
        for n in range(1, 5):
            same = ~ch[n]["D"]
            self.assertTrue(np.array_equal(ch[n]["P"][same], ch[n - 1]["P"][same]), n)
        self.assertGreater((ch[2]["core"] & WHERE["cat"]).sum() / WHERE["cat"].sum(), 0.9)
        # the rug went on bare canvas: where it was is canvas in every earlier picture
        self.assertTrue((ch[0]["P"][WHERE["rug"] & ~WHERE["cat"]] == CANVAS).all())
        self.assertFalse(ch[0]["D"][250, 100])
        self.assertTrue(ch[0]["D"][50, 100])
        folder = Path(self.tmp) / "chain"
        for name in ("chain.jpg", "chain.json", "looks/U01.jpg", "looks/U04.jpg", "looks/asked.json", "P00.png", "D04.png"):
            self.assertTrue((folder / name).exists(), name)
        self.assertEqual(len(json.loads((folder / "looks" / "asked.json").read_text())), 4)
        self.assertEqual(erase3.problems(r), ([], []))

    def test_a_back_render_on_a_blocked_in_thing_is_kept_over_the_whole_thing(self):
        # the render that takes the shadows off answers with the rug and the cat as flat coats a touch off their
        # color everywhere: too little for the guard, which would keep it only where the shadows were
        scene = pictures()
        flat = scene[2].copy()
        flat[WHERE["rug"] & ~WHERE["cat"]] = (171, 61, 51)
        flat[WHERE["cat"]] = (134, 134, 134)
        _, _ = chain(self.tmp, Model({"U03": flat}))
        ch = erase3.load(Path(self.tmp), plan())
        cat_top = box(180, 205, 180, 320)  # clear of the light, the eyes and the shadow
        self.assertTrue((np.abs(ch[2]["P"][cat_top].astype(int) - 134).max() <= 3))
        self.assertGreater(ch[3]["D"][cat_top].mean(), 0.99)
        first = erase3.lay(plan(), plan3.units(plan()), scene[-1], {n: (flat if n == 3 else scene[n - 1]) for n in range(1, 5)})
        self.assertTrue((np.abs(first["P"][2][cat_top].astype(int) - 128).max() <= 1))  # the guard alone: as it was
        self.assertTrue(np.array_equal(ch[4]["P"], scene[-1]))

    def test_a_unit_left_standing_is_asked_again_by_itself_before_the_units_before_it(self):
        half = striped()
        r, model = chain(self.tmp, Model({"U02": half}))
        self.assertEqual([c[0] for c in model.calls], ["U04", "U03", "U02", "U02r", "U01"])
        self.assertIn(erase3.AGAIN["left"]["go"], model.calls[3][1])
        self.assertTrue(model.calls[3][2])  # a fresh render, not the cache's
        self.assertEqual(r["again"], {"2": ["left"]})
        self.assertEqual(r["rows"][1]["render"], "U02r")
        self.assertFalse(r["rows"][1]["ask_again"])
        # the try that was thrown away was paid for too
        self.assertEqual((r["renders"], r["paid"], r["cost_usd"]), (4, 5, 0.1))
        self.assertEqual([t["render"] for t in r["rows"][1]["tries"]], ["U02", "U02r"])

    def test_a_run_that_stops_partway_remembers_its_tries_and_pays_for_none_twice(self):
        half = striped()
        with self.assertRaises(RuntimeError):
            chain(self.tmp, Model({"U02": half}, fail_at="U01"))
        r, model = chain(self.tmp, Model({"U02": half}))
        # the second run asks for the same try, and not as a fresh render: the cache has it
        self.assertEqual([(c[0], c[2]) for c in model.calls], [("U04", False), ("U03", False), ("U02r", False),
                                                               ("U01", False)])
        self.assertEqual(r["again"], {"2": ["left"]})
        with self.assertRaises(RuntimeError):
            chain(tempfile.mkdtemp(), Model(fail_at="U02"), redo=None)
        other = tempfile.mkdtemp()
        chain(other)
        for _ in range(2):  # an asked-for try whose run stops is a try all the same: the cap still holds
            with self.assertRaises(RuntimeError):
                chain(other, Model(fail_at="U02"), redo={3: "stray"})
        with self.assertRaises(erase3.Refused):
            chain(other, redo={3: "stray"})
        r, model = chain(other)
        self.assertEqual([(c[0], c[2]) for c in model.calls][:2], [("U04", False), ("U03rr", False)])
        # the same --redo given again after a run that stopped before rendering it is the same try, not a new one
        third = tempfile.mkdtemp()
        chain(third)
        with self.assertRaises(RuntimeError):
            chain(third, Model(fail_at="U03r"), redo={3: "stray"})
        r, model = chain(third, redo={3: "stray"})
        self.assertEqual(r["again"], {"3": ["stray"]})
        self.assertEqual([(c[0], c[2]) for c in model.calls][:2], [("U04", False), ("U03r", True)])

    def test_a_unit_still_left_after_its_tries_stays_and_is_reported(self):
        half = striped()
        r, model = chain(self.tmp, Model({"U02": half, "U02r": half, "U02rr": half}))
        self.assertEqual(r["again"], {"2": ["left", "left"]})
        todo, kept = erase3.problems(r)
        self.assertEqual(todo, [])
        self.assertIn("unit 2 (The cat)", kept[0])
        r2, _ = chain(tempfile.mkdtemp(), Model({"U02": half}), auto=False)
        self.assertIn("erase --redo 2:left", erase3.problems(r2)[0][0])

    def test_asking_again_is_remembered_and_capped(self):
        chain(self.tmp)
        r, model = chain(self.tmp, redo={3: "stray"})
        self.assertEqual(r["again"], {"3": ["stray"]})
        self.assertEqual([(c[0], c[2]) for c in model.calls], [("U04", False), ("U03r", True), ("U02", False), ("U01", False)])
        r, model = chain(self.tmp)  # run again with nothing new: the same requests, none asked for fresh
        self.assertEqual([c[0] for c in model.calls][1], "U03r")
        self.assertFalse(any(c[2] for c in model.calls))
        chain(self.tmp, redo={3: "left"})
        for bad, words in (({3: "left"}, "2 times already"), ({9: "left"}, "no unit 9"), ({0: "left"}, "no unit 0"),
                           ({2: "ugly"}, "left or stray")):
            with self.assertRaises(erase3.Refused) as e:
                chain(self.tmp, redo=bad)
            self.assertIn(words, str(e.exception))

    def test_a_chain_made_for_other_units_is_refused_and_forgotten(self):
        chain(self.tmp, redo={3: "stray"})
        p = plan()
        del step(p, "cat-eyes")["unit"]
        step(p, "cat-eyes")["paints"] = ["Pale gray", "Sky blue"]  # now one unit with the shadows
        with self.assertRaises(erase3.Refused) as e:
            erase3.load(Path(self.tmp), p)
        self.assertIn("other units", str(e.exception))
        with self.assertRaises(erase3.Refused):
            erase3.load(Path(tempfile.mkdtemp()), p)
        other = tempfile.mkdtemp()
        chain(other)
        (Path(other) / "chain" / "looks" / "answers.json").write_text("[]")
        (Path(other) / "chain" / "looks" / "kept").mkdir()
        chain(other)  # a folder in looks/ is left alone, and the old answers go with the old pictures
        self.assertFalse((Path(other) / "chain" / "looks" / "answers.json").exists())
        q = plan()
        step(q, "block-cat")["after"] = "A flat gray cat lies on the rug."  # the same units, another request
        with self.assertRaises(erase3.Refused) as e:
            erase3.load(Path(other), q)
        self.assertIn("words changed", str(e.exception))
        Image.fromarray(pictures()[-2]).save(Path(other) / "99_finish.png")
        with self.assertRaises(erase3.Refused):
            erase3.load(Path(other), plan())
        r = erase3.run(Path(self.tmp), p, pictures()[-1], Model({"U03": pictures()[2]}))
        self.assertEqual(r["again"], {})


@lessons.slow
class EraseToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache, tools.CACHE_DIR = tools.CACHE_DIR, self.tmp / "cache"
        self.addCleanup(setattr, tools, "CACHE_DIR", self.cache)
        self.lesson = self.tmp / "lesson"
        self.lesson.mkdir()
        self.client = FakeClient()

    def write(self, p: dict, finish: bool = True) -> None:
        (self.lesson / "plan.json").write_text(json.dumps(p), encoding="utf-8")
        if finish:
            Image.fromarray(pictures()[-1]).save(self.lesson / "99_finish.png")

    def run_tool(self, *more: str) -> tuple[int, dict]:
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = tools.main(["erase", "--lesson", str(self.lesson), *more], client=self.client)
        return code, json.loads(buf.getvalue())

    def real_plan(self) -> dict:
        """test_plan3's plan with strokes the real elements list, and no technique ranges to meet."""
        p = plan()
        for sid, stroke in (("shadows", "curved-strokes"), ("light-cat", "curved-strokes"), ("cat-eyes", "dotting")):
            step(p, sid)["stroke"] = stroke
        patch = mock.patch.object(tools, "_v3_plan", lambda lesson: (json.loads((lesson / "plan.json").read_text()), {}))
        patch.start()
        self.addCleanup(patch.stop)
        return p

    def test_it_refuses_without_a_clean_plan_or_a_finish(self):
        self.write(json.loads((HERE / "fixtures" / "plans3" / "sleeping-cat.json").read_text(encoding="utf-8")))
        code, r = self.run_tool()
        self.assertEqual(code, 2)
        self.assertIn("fix plan.json first", r["refused"])
        self.assertEqual(self.client.images.calls, 0)
        self.write({"plan_version": 2}, finish=False)
        self.assertIn("isn't a version 3 plan", self.run_tool()[1]["refused"])

    def test_one_render_a_unit_in_the_ledger_and_nothing_paid_the_second_time(self):
        self.write(self.real_plan())
        code, r = self.run_tool("--no-auto")
        self.assertEqual(code, 0, r)
        self.assertEqual((r["renders"], r["paid"]), (4, 4))
        self.assertEqual(self.client.images.calls, 4)
        ledger = json.loads((self.lesson / "ledger.json").read_text())
        self.assertEqual(sorted({c["step"] for c in ledger["calls"]}), ["erase-U01", "erase-U02", "erase-U03", "erase-U04"])
        self.assertAlmostEqual(r["cost_usd"], ledger["total_cost_usd"], places=3)
        self.assertEqual([x["unit"] for x in r["rows"]], [1, 2, 3, 4])
        code, r = self.run_tool("--no-auto")
        self.assertEqual((r["renders"], r["paid"], r["cost_usd"]), (4, 0, 0.0))
        self.assertEqual(self.client.images.calls, 4)
        code, r = self.run_tool("--redo", "9")
        self.assertEqual(code, 2)
        self.assertIn("<unit>:<why>", r["refused"])
        self.assertIn("twice", self.run_tool("--redo", "2:stray,2:left")[1]["refused"])
        self.assertIn("leave --redo out", self.run_tool("--probe", "4", "--redo", "2:left")[1]["refused"])
        code, r = self.run_tool("--probe", "4")
        self.assertEqual((code, r["probe"], r["kind"], r["cached"]), (0, 4, "back", True))  # the chain's own render
        self.assertTrue(Path(r["look"]).exists())
        self.assertIn("no unit 5", self.run_tool("--probe", "5")[1]["refused"])
        code, r = self.run_tool("--no-auto", "--max-cost", "0.01", "--redo", "4:stray")
        self.assertEqual(code, 2)
        self.assertIn("cap", r["refused"])
        # a run refused at the cap leaves the chain before it whole: the later tools still read it
        erase3.load(self.lesson, json.loads((self.lesson / "plan.json").read_text()))

    def test_the_cap_is_the_chains_own_and_follows_its_size(self):
        self.write(self.real_plan())
        # the finish cost 90 cents before the chain: not the chain's, so the chain's default cap still lets it run
        (self.lesson / "ledger.json").write_text(json.dumps({"calls": [
            {"tool": "render", "step": "finish", "quality": "high", "cost_usd": 0.9, "seconds": 1}], "total_cost_usd": 0.9}))
        code, r = self.run_tool("--no-auto")
        self.assertEqual((code, r["paid"]), (0, 4), r)
        # 4 renders: 2 x 2.5 cents x 4 + 7 = 27 cents for the chain. Each render here costs about 2.5 and reserves 7,
        # so a fresh render fits while under 20 cents are spent: 4 made, then 4 more redos, and the ninth is refused
        spent = lambda: sum(c["cost_usd"] for c in json.loads((self.lesson / "ledger.json").read_text())["calls"]  # noqa: E731
                            if c["step"].startswith("erase-"))
        code, r = self.run_tool("--no-auto", "--redo", "4:stray")
        self.assertEqual(code, 0, r)
        code, r = self.run_tool("--no-auto", "--redo", "4:left")
        self.assertEqual(code, 2, r)
        self.assertIn("cap", r["refused"])
        self.assertLessEqual(spent(), 0.27)

    def test_a_picture_that_is_not_the_models_shape_goes_in_with_bands_and_comes_back_its_own_size(self):
        self.write(self.real_plan())
        Image.fromarray(pictures()[-1][:, :300]).save(self.lesson / "99_finish.png")  # 300 x 320: no frame is this shape
        code, r = self.run_tool("--no-auto")
        self.assertEqual(code, 0, r)
        self.assertEqual(Image.open(self.lesson / "chain" / "P00.png").size, (300, 320))
        self.assertEqual(Image.open(self.lesson / "chain" / "U04_in.png").size, (300, 320))
        sent = self.client.images.sent[0]
        self.assertIn("Keep the plain gray bands at the edges", sent["prompt"])
        self.assertEqual(sent["size"], "1024x1024")
        got = Image.open(io.BytesIO(sent["image"][1]))
        self.assertEqual(got.size, (1024, 1024))
        self.assertEqual(got.getpixel((5, 500)), tools.GRAY)

if __name__ == "__main__":
    unittest.main()
