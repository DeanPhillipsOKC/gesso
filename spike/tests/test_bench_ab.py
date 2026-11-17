"""The blind A/B page and its scores (#165)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "experiments" / "bench"))

import ab_page  # noqa: E402
import lessons  # noqa: E402
from test_bench import published  # noqa: E402

PICTURES = ["chickadee", "red-sailboat", "balloon-lavender", "sleeping-cat", "snow-lantern", "highland-cow",
            "lake-cabin", "birch-grove"]


def _data(html: str) -> dict:
    return json.loads(re.search(r'<script type="application/json" id="data">(.+?)</script>', html, re.S).group(1))


def _node() -> tuple[str, dict] | None:
    """node with Playwright, or None when this machine has neither."""
    node = shutil.which("node")
    if not node:
        return None
    env = dict(os.environ)
    try:
        root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        root = ""
    if root:
        env["NODE_PATH"] = root
    ok = subprocess.run([node, "-e", "require('playwright')"], capture_output=True, env=env, timeout=20)
    return (node, env) if ok.returncode == 0 else None


# Opens the page as a phone, with the clipboard blocked and a stand-in artifact database, taps a score and a worst
# step, taps Copy scores, and prints everything the page let out: the copy box, localStorage, and the db records.
DRIVE = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  await page.addInitScript(() => {
    window.__db = [];
    Object.defineProperty(navigator, 'clipboard', { value: undefined });
    window.claude = { use: () => Promise.resolve({ collection: (c) => ({ doc: (id) => ({
      set: (rec) => { window.__db.push({ c, id, rec }); return Promise.resolve(); } }) }) }) };
  });
  await page.goto('file://' + process.argv[2]);
  await page.locator('section.pic.on .scale').first().locator('button').nth(3).click();
  await page.locator('section.pic.on button.worst').first().click();
  await page.locator('#copy').click();
  await page.waitForTimeout(1500);
  const out = await page.evaluate(() => {
    const ls = {};
    for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); ls[k] = localStorage.getItem(k); }
    return { copy: document.getElementById('copybox').value, ls, db: window.__db };
  });
  console.log(JSON.stringify(out));
  await browser.close();
})();
"""


class ABPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_single_mode_page(self):
        lessons_ = [published(self.tmp / "a", "chickadee", "chickadee_skill_20261116-100000"),
                    published(self.tmp / "a", "red-sailboat", "red-sailboat_skill_20261116-100000", steps=2)]
        out = ab_page.make(ab_page.plan_round("baseline-test", lessons=lessons_, seed=3), self.tmp / "page.html")
        html = (self.tmp / "page.html").read_text(encoding="utf-8")
        self.assertLess(len(html.encode()), ab_page.MAX_BYTES)
        self.assertEqual((out["mode"], out["pictures"], out["steps"], out["side_px"]), ("single", 2, 5, 720))
        self.assertEqual(html.count("function saveScores("), 1)
        self.assertIn("localStorage.setItem", html)
        self.assertIn("'__' + device", html)  # one database record per device
        self.assertIn('id="copy"', html)
        self.assertIn("Would you paint from this lesson?", html)
        self.assertNotIn('id="key"', html)
        key = json.loads((self.tmp / "page.key.json").read_text())
        self.assertEqual(key["format"], ab_page.KEY_FORMAT)
        self.assertEqual([p["picture"] for p in key["pictures"]], ["chickadee", "red-sailboat"])  # bench order
        data = _data(html)
        self.assertEqual([p["lessons"] for p in data["pictures"]], [p["tokens"] for p in key["pictures"]])
        self.assertNotIn("the plan", html)  # nothing from plan.json
        step = data["pictures"][0]["sides"]["A"]["steps"][1]
        self.assertEqual((step["n"], step["name"], step["group"]), (2, "Paint part 2", "The sky"))
        self.assertEqual(step["paints"][0]["name"], "Warm gold")
        self.assertTrue(step["img"].startswith("data:image/jpeg;base64,"))

    def pair_round(self, seed=7):
        one = published(self.tmp / "1", "chickadee", "chickadee_skill_20261116-100000")
        two = published(self.tmp / "2", "chickadee", "chickadee_skill_20261116-200000")
        plan = ab_page.plan_round("s1-test", pairs=[(one, two)], seed=seed)
        ab_page.make(plan, self.tmp / "p.html")
        return one, two, (self.tmp / "p.html").read_text(encoding="utf-8")

    def test_the_pair_page_holds_no_folder_name_or_seed(self):
        one, two, html = self.pair_round(seed=24680)
        for secret in (one.name, two.name, "20261116-100000", "20261116-200000", "24680"):
            self.assertNotIn(secret, html)  # the whole page, nothing stripped
        key = json.loads((self.tmp / "p.key.json").read_text())
        self.assertEqual(key["seed"], 24680)
        self.assertEqual(sorted(key["pictures"][0]["lessons"].values()), sorted([one.name, two.name]))
        self.assertEqual(_data(html)["pictures"][0]["lessons"], key["pictures"][0]["tokens"])
        self.assertIn("Which would you paint from?", html)
        # the same inputs and seed give the same page, byte for byte
        ab_page.make(ab_page.plan_round("s1-test", pairs=[(one, two)], seed=24680), self.tmp / "q.html")
        self.assertEqual((self.tmp / "q.html").read_bytes(), (self.tmp / "p.html").read_bytes())

    def test_sides_are_balanced_and_drawn_from_the_seed(self):
        pairs = [(published(self.tmp / "1", n, f"{n}_skill_20261116-100000", steps=1),
                  published(self.tmp / "2", n, f"{n}_skill_20261116-200000", steps=1)) for n in PICTURES]
        for n in (1, 2, 3, 5, 8):
            counts = set()
            for seed in range(40):
                plan = ab_page.plan_round("r", pairs=pairs[:n], seed=seed)
                firsts = sum(r["sides"]["A"].name.endswith("100000") for r in plan["pictures"])
                self.assertIn(firsts, {n // 2, n - n // 2}, (n, seed))  # balanced, one either way when n is odd
                counts.add(firsts)
            # the seed, not the order the lessons were named in, decides: with n odd both splits come up
            self.assertEqual(counts, {n // 2, n - n // 2}, n)
        self.assertNotEqual(*(tuple(r["sides"]["A"] for r in ab_page.plan_round("r", pairs=pairs, seed=s)["pictures"])
                              for s in (1, 2)))
        self.assertIsInstance(ab_page.plan_round("r", pairs=pairs)["seed"], int)  # none given: a random one, kept

    def test_an_order_seed_shuffles_the_pictures_the_same_way_every_time(self):
        names = PICTURES[:5]
        ls = [published(self.tmp / "o", n, f"{n}_skill_20261116-100000", steps=1) for n in names]
        order = lambda plan: [r["picture"] for r in plan["pictures"]]  # noqa: E731
        self.assertEqual(order(ab_page.plan_round("r", lessons=list(reversed(ls)))), names)
        one = ab_page.plan_round("r", lessons=ls, order_seed=165)
        self.assertEqual(order(one), order(ab_page.plan_round("r", lessons=list(reversed(ls)), order_seed=165)))
        self.assertEqual(sorted(order(one)), sorted(names))
        self.assertNotEqual({tuple(order(ab_page.plan_round("r", lessons=ls, order_seed=s))) for s in range(5)},
                            {tuple(names)})
        self.assertEqual(ab_page.answer_key(one)["order_seed"], 165)

    def test_refuses_mixed_pictures_and_mixed_modes(self):
        one = published(self.tmp / "1", "chickadee", "chickadee_skill_20261116-100000")
        two = published(self.tmp / "2", "red-sailboat", "red-sailboat_skill_20261116-100000")
        with self.assertRaises(ValueError):
            ab_page.plan_round("r", pairs=[(one, two)])
        with self.assertRaises(ValueError):
            ab_page.plan_round("r", lessons=[one], pairs=[(one, one)])
        with self.assertRaises(ValueError):
            ab_page.plan_round("r", lessons=[one, one])


@lessons.slow
class BlindInTheBrowserTests(unittest.TestCase):
    """What the pair page lets out when the owner scores and copies, in a real browser."""

    def test_copy_storage_and_database_carry_no_folder_name_or_seed(self):
        found = _node()
        if not found:
            self.skipTest("node with Playwright isn't installed here")
        node, env = found
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        one = published(tmp / "1", "chickadee", "chickadee_skill_20261116-100000")
        two = published(tmp / "2", "chickadee", "chickadee_skill_20261116-200000")
        ab_page.make(ab_page.plan_round("s1-test", pairs=[(one, two)], seed=24680), tmp / "p.html")
        script = tmp / "drive.js"
        script.write_text(DRIVE)
        run = subprocess.run([node, str(script), str(tmp / "p.html")], capture_output=True, text=True, env=env,
                             timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        out = json.loads(run.stdout.strip().splitlines()[-1])
        copied = json.loads(out["copy"])  # the clipboard is blocked: the fallback box shows the JSON
        self.assertEqual(copied["pictures"][0]["scores"]["A"]["real"], 4)
        at = copied["pictures"][0]["scores"]["A"]["at"]  # each item's own save time
        self.assertEqual(sorted(at), ["real", "worst_steps"])
        self.assertTrue(out["db"], "no database record was written")
        self.assertTrue(out["db"][-1]["id"].startswith("s1-test__d"))
        everything = json.dumps(out)
        for secret in (one.name, two.name, "20261116-100000", "20261116-200000", "24680"):
            self.assertNotIn(secret, everything)
        key = json.loads((tmp / "p.key.json").read_text())
        self.assertEqual(copied["pictures"][0]["lessons"], key["pictures"][0]["tokens"])


class ScoresTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.key = {"format": ab_page.KEY_FORMAT, "round": "s1-test", "mode": "pair", "seed": 7,
                    "pictures": [{"picture": "chickadee", "tokens": {"A": "Laaa", "B": "Lbbb"},
                                  "lessons": {"A": "chickadee_skill_1", "B": "chickadee_skill_2"}}]}
        (self.tmp / "scores").mkdir()
        (self.tmp / "scores" / "s1-test.key.json").write_text(json.dumps(self.key))

    def record(self, device, saved_at, real=None, worst=(), prefer=None, note=""):
        return {"format": ab_page.FORMAT, "round": "s1-test", "mode": "pair", "saved_at": saved_at, "device": device,
                "pictures": [{"picture": "chickadee", "lessons": {"A": "Laaa", "B": "Lbbb"},
                              "scores": {"A": {"real": real, "paintable": None, "agree": None,
                                               "worst_steps": [{"n": n} for n in worst], "note": note},
                                         "B": {"real": None, "paintable": 2, "agree": None, "worst_steps": [],
                                               "note": ""}},
                              "prefer": prefer, "note": ""}]}

    def write(self, name, data):
        path = self.tmp / name
        path.write_text(json.dumps(data))
        return path

    def test_valid_scores_pass_and_bad_ones_are_named(self):
        good = self.record("d1", "2026-11-17T10:00:00Z", real=4)
        self.assertEqual(ab_page.check_scores(good), [])
        bad = json.loads(json.dumps(good))
        bad["pictures"][0]["scores"]["A"]["real"] = 7
        bad["pictures"][0]["prefer"] = "C"
        self.assertEqual(len(ab_page.check_scores(bad)), 2)
        self.assertEqual(ab_page.check_scores({"format": "x"}), [f"not a {ab_page.FORMAT} scores file"])

    def test_two_devices_merge_item_by_item_latest_wins(self):
        phone = self.record("d1", "2026-11-17T10:00:00Z", real=4, worst=[5], prefer="A")
        laptop = self.record("d2", "2026-11-17T11:00:00Z", real=3, note="later look")  # only touched A's real and note
        out = ab_page.import_scores([self.write("phone.json", phone), self.write("db.json", [laptop])],
                                    dest=self.tmp / "scores")
        self.assertEqual((out["records"], out["conflicts"]), (2, 1))
        saved = json.loads((self.tmp / "scores" / "s1-test.json").read_text())
        p = saved["pictures"][0]
        self.assertEqual(p["lessons"], {"A": "chickadee_skill_1", "B": "chickadee_skill_2"})  # joined by the key
        self.assertEqual(p["tokens"], {"A": "Laaa", "B": "Lbbb"})
        self.assertEqual(p["scores"]["A"]["real"], 3)  # the later one wins
        self.assertEqual(p["scores"]["A"]["worst_steps"], [{"n": 5}])  # only the phone set it: kept
        self.assertEqual(p["scores"]["A"]["note"], "later look")
        self.assertEqual(p["prefer"], "A")
        self.assertEqual(saved["conflicts"][0]["item"], "real")
        self.assertEqual(saved["seed"], 7)
        self.assertEqual([m["device"] for m in saved["merged_from"]], ["d1", "d2"])

    def test_each_item_merges_by_its_own_time_and_a_later_clear_wins(self):
        phone = self.record("d1", "2026-11-17T12:00:00Z", real=4, worst=[5])  # saved last, but set real at 10:00
        phone["pictures"][0]["scores"]["A"]["at"] = {"real": "2026-11-17T10:00:00Z", "worst_steps": "2026-11-17T10:00:00Z"}
        laptop = self.record("d2", "2026-11-17T11:00:00Z", real=2, worst=[])  # corrected real, un-tapped step 5
        laptop["pictures"][0]["scores"]["A"]["at"] = {"real": "2026-11-17T11:00:00Z", "worst_steps": "2026-11-17T11:00:00Z"}
        out = ab_page.import_scores([self.write("p.json", phone), self.write("l.json", laptop)], dest=self.tmp / "scores")
        sc = json.loads((self.tmp / "scores" / "s1-test.json").read_text())["pictures"][0]["scores"]["A"]
        self.assertEqual(sc["real"], 2)  # the laptop's later correction, though the phone saved later
        self.assertEqual(sc["worst_steps"], [])  # the later clear wins
        self.assertEqual(out["conflicts"], 2)

    def test_refuses_tokens_the_key_doesnt_know_and_wont_overwrite(self):
        rec = self.record("d1", "2026-11-17T10:00:00Z", real=4)
        rec["pictures"][0]["lessons"]["A"] = "chickadee_skill_1"  # a folder name, not the token
        with self.assertRaises(ab_page.Invalid):
            ab_page.import_scores([self.write("x.json", rec)], dest=self.tmp / "scores")
        good = self.write("g.json", self.record("d1", "2026-11-17T10:00:00Z", real=4))
        ab_page.import_scores([good], dest=self.tmp / "scores")
        ab_page.import_scores([good], dest=self.tmp / "scores")  # the same scores again: fine
        later = self.write("h.json", self.record("d1", "2026-11-17T12:00:00Z", real=5))
        with self.assertRaises(ab_page.Invalid):
            ab_page.import_scores([later], dest=self.tmp / "scores")
        ab_page.import_scores([later], dest=self.tmp / "scores", force=True)

    def test_a_key_from_before_tokens_matches_folder_names(self):
        """The baseline-1.12.1 page (single mode, published before tokens) puts folder names in its scores."""
        old = {"format": ab_page.FORMAT, "round": "baseline-old", "mode": "single", "seed": None,
               "pictures": [{"picture": "chickadee", "lessons": {"A": "chickadee_skill_1"}}]}
        (self.tmp / "scores" / "baseline-old.key.json").write_text(json.dumps(old))
        rec = {"format": ab_page.FORMAT, "round": "baseline-old", "mode": "single", "seed": None,
               "saved_at": "2026-11-17T10:00:00Z", "device": "d1",
               "pictures": [{"picture": "chickadee", "lessons": {"A": "chickadee_skill_1"},
                             "scores": {"A": {"real": 4, "paintable": 3, "agree": 4, "would_paint": "yes",
                                              "worst_steps": [], "note": ""}}, "prefer": None, "note": ""}]}
        out = ab_page.import_scores([self.write("b.json", rec)], dest=self.tmp / "scores")
        self.assertEqual(out["not_fully_scored"], [])
        saved = json.loads((self.tmp / "scores" / "baseline-old.json").read_text())
        self.assertEqual(saved["pictures"][0]["scores"]["A"]["would_paint"], "yes")


if __name__ == "__main__":
    unittest.main()
