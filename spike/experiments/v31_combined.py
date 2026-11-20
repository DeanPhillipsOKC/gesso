"""The combined v3.1 lesson (`docs/design/pipeline-v3.1.md`, section 12, step 1; under #240).

Everything the design adopts run together for the first time: the lesson's writer in six lines with the lean cuts
and the paint check (`v4_writer_cost.py`'s `lean-paints`), the long arc as its next message, the design's three
changes to the writer's brief (section 5), and the lean finisher (`f-lean`) on those words. No render is made: the
pictures are lessons already made. The sleeping cat is the one #267 made after #250 (`v4_writer_cost.py`'s set
`new`), and it gets the finisher. The chickadee and the lavender balloon are the site's sealed v3 lessons (the
owner's ask, 2026-11-20: the ones his partner means to paint), and get the words only: their diagrams, notes and
known problems are the sealed lesson's.

    .venv/bin/python spike/experiments/v31_combined.py bench  --picture chickadee   # a sealed lesson's bench folder
    .venv/bin/python spike/experiments/v31_combined.py words  --picture chickadee   # the writer, its checks, the arc
    .venv/bin/python spike/experiments/v31_combined.py finish                       # the cat's finisher
    .venv/bin/python spike/experiments/v31_combined.py page   --picture chickadee   # docs/spikes/v31-combined-<picture>.md
    .venv/bin/python spike/experiments/v31_combined.py report --picture chickadee
    .venv/bin/python spike/experiments/v31_combined.py lesson --picture chickadee   # a whole lesson page to paint from

Results go in `spike/experiments/v31_combined.json`, in `v4_writer_cost.json`'s shape. Experiment code: it changes
no tool, and the lesson isn't sealed or put on the site.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import v4_arc as arc  # noqa: E402
import v4_loop as loop  # noqa: E402
import v4_student as student  # noqa: E402
import v4_teacher as teacher  # noqa: E402
import v4_writer_cost as wc  # noqa: E402

RESULTS = HERE / "v31_combined.json"
WORDS, FINISH = "v31", "f-lean"
# picture: (the set in v4_writer_cost's sense, its lesson folder under output/)
LESSONS = {"sleeping-cat": ("new", "sleeping-cat_v4loop_20261119-215313"),
           "chickadee": ("site", "chickadee_skill_20261118-091227"),
           "balloon-lavender": ("site", "balloon-lavender_skill_20261118-094526")}
LINE_WORDS = 40
SET, PICTURE, LESSON = "new", "sleeping-cat", LESSONS["sleeping-cat"][1]  # set by `choose`


def choose(picture: str):
    global SET, PICTURE, LESSON
    PICTURE = picture
    SET, LESSON = LESSONS[picture]


def page_path() -> Path:
    return ROOT / "docs" / "spikes" / f"v31-combined-{PICTURE}.md"


def pics_dir() -> Path:
    return ROOT / "docs" / "spikes" / "v31-combined" / PICTURE

# The design's three changes to the writer's brief (section 5). Each is (the spike's words, the new words).
BRIEF_CHANGES = [
    # 3. the writer is told what the page shows beside its words
    ("The step's own picture is shown too, but write so that the step can be done without looking at it: the painter\n"
     "compares with it when they are done.",
     "The step's own picture is shown too, but write so that the step can be done without looking at it: the painter\n"
     "compares with it when they are done.\n\n"
     "The page shows two more things you can point at. Beside each step is its **Where picture**: the canvas before\n"
     "the step, dimmed, with the area this step paints outlined on it. Before step 1 there is an optional **transfer\n"
     "outline**: the outlines of the main shapes on a grid of quarters, which the painter may have drawn on the canvas\n"
     "in pencil. You may send the painter to either (\"inside the outline on the Where picture\"), once in a step and\n"
     "only where it helps. It never replaces saying where the paint goes: the outline is the step's whole area, not\n"
     "where inside it the paint sits."),
    # 1. an earlier step's marks by their look and step, not their paint
    ("- **Name parts by the sheet's names** (\"the balloon\", \"the rolling fields\"), and an earlier step's marks by their\n"
     "  paint (\"the Deep balloon red stripe\"), so the tool can find what you mean.",
     "- **Name parts by the sheet's names** (\"the balloon\", \"the rolling fields\"), so the tool can find what you mean.\n"
     "- **Name an earlier step's marks by their look and their step** (\"the brown streaks from step 8\", \"the gray first\n"
     "  coat\"), never by their paint's name: a second tool fails a sentence that names a paint its step doesn't list.\n"
     "  The one exception is a side word that needs the name for the tool to find the marks (\"left of the Deep balloon\n"
     "  red stripe\"); prefer a sentence that needs neither."),
]
FORM_CHANGE = ("one to three sentences each, under about 130 words in all.",
               f"one to three sentences each, under about 130 words in all. No line is over {LINE_WORDS} words: a "
               "tool counts them.")


def setup():
    """Point v4_writer_cost at this spike's results file and lesson, and put the brief's changes in."""
    wc.RESULTS = RESULTS
    wc.WORD_VARIANTS[WORDS] = wc.WORD_VARIANTS["lean-paints"]
    wc.SETS.setdefault("site", {k: v[1] for k, v in LESSONS.items() if v[0] == "site"})
    if not RESULTS.exists():
        RESULTS.write_text(json.dumps({"lessons": {"new": {"sleeping-cat": LESSONS["sleeping-cat"][1]}}}, indent=1)
                           + "\n")
    for old, new in BRIEF_CHANGES:
        if new not in teacher.BRIEF:
            assert teacher.BRIEF.count(old) == 1, old
            teacher.BRIEF = teacher.BRIEF.replace(old, new)
    old, new = FORM_CHANGE
    if new not in teacher.FORM["slots"]:
        assert teacher.FORM["slots"].count(old) == 1
        teacher.FORM["slots"] = teacher.FORM["slots"].replace(old, new)
    wc.point(SET)


def bench(args):
    """A sealed lesson's bench folder and its writer's pictures (`v4_writer_cost.bench`, which reads the lesson and
    writes only in the work folder). The cat's was made by #267."""
    setup()
    if SET != "site":
        raise SystemExit("the cat's bench is v4_writer_cost.py's (bench --set new)")
    only = {PICTURE: LESSON}
    with_all = wc.SETS["site"]
    wc.SETS["site"] = only
    try:
        wc.bench(argparse.Namespace(set="site", lesson=None))
    finally:
        wc.SETS["site"] = with_all


def words(args):
    setup()
    if PICTURE in wc.state()["words"].get(SET, {}).get(WORDS, {}) and not args.again:
        return print("the words are written (--again writes them again)")
    wc.write_words(SET, WORDS, PICTURE)


def finish(args):
    setup()
    if SET != "new":
        raise SystemExit("only the cat gets the finisher: a sealed lesson keeps its own diagrams and notes")
    wc.finish_one(SET, WORDS, FINISH, PICTURE)


def long_lines(rec: dict) -> list[tuple[str, str, int]]:
    return [(sid, x["kind"], len(x["text"].split())) for sid, lines in rec["final"].items() for x in lines
            if len(x["text"].split()) > LINE_WORDS]


def report(args=None) -> dict:
    setup()
    st = wc.state()
    rec = st["words"][SET][WORDS][PICTURE]
    calls = [c for c in st["calls"] if c.get("picture") == PICTURE]
    cost = loop.api_costs(calls)
    by = {}
    for c, d in zip(calls, cost):
        by.setdefault((c.get("part"), c.get("label") or c.get("helper")), []).append(round(d, 3))
    parts = {p: round(sum(d for c, d in zip(calls, cost) if c.get("part") == p), 2) for p in ("words", "finish")}
    fin = st["finish"].get(SET, {}).get(f"{WORDS}+{FINISH}", {}).get(PICTURE)
    out = {"steps": len(rec["final"]), "words": rec["words_count"], "arc_words": rec["arc_words"],
           "back_lines": rec["backs"], "check": rec["check"], "lines_over_40_words": long_lines(rec),
           "missing": rec["missing"], "cost_api": parts, "calls": {f"{k[0]}: {k[1]}": v for k, v in by.items()},
           "finish": fin and {k: fin[k] for k in ("specced", "drawn", "looked", "publish_refused")},
           "known_problems": fin and len((fin.get("review") or {}).get("text_issues") or [])}
    print(json.dumps(out, indent=1))
    return out


def page(args):
    """The whole lesson as a painter would read it, for the owner: the opening, each stage, every step's lines and
    picture, then what the finisher listed as known problems."""
    from PIL import Image
    setup()
    st = wc.state()
    rec = st["words"][SET][WORDS][PICTURE]
    fin = st["finish"].get(SET, {}).get(f"{WORDS}+{FINISH}", {}).get(PICTURE) or {}
    les, a = teacher.packet(PICTURE), rec["arc"]
    PICS, PAGE = pics_dir(), page_path()
    PICS.mkdir(parents=True, exist_ok=True)
    for name in ["photo.jpg", "finish.jpg"] + [f"steps/{s['n']:02d}.jpg" for s in les["steps"]]:
        im = Image.open(teacher.BENCH / PICTURE / name).convert("RGB")
        im.thumbnail((560, 560))
        im.save(PICS / Path(name).name, quality=78, optimize=True)
    rel = f"v31-combined/{PICTURE}"
    issues = (fin.get("review") or {}).get("text_issues")
    if issues is None and (ROOT / "output" / LESSON / "review.json").exists():  # a sealed lesson's own
        issues = json.loads((ROOT / "output" / LESSON / "review.json").read_text()).get("text_issues")
    out = [f"# The {PICTURE.replace('-', ' ')} as a v3.1 lesson (the combined lesson)", "",
           "The whole lesson as a painter would read it, made the way `docs/design/pipeline-v3.1.md` describes "
           "(section 12, step 1). The pictures are v3's. How it was made and what it cost: "
           "[v31-combined.md](v31-combined.md).", "",
           f"![The photo]({rel}/photo.jpg)", "",
           f"Canvas: {les['canvas_in'][0]:g} in wide, {les['canvas_in'][1]:g} in tall. {len(les['steps'])} steps.", ""]
    op = a.get("opening") or {}
    out += ["## Before you start", ""]
    if op.get("welcome"):
        out += [op["welcome"], ""]
    if op.get("light"):
        out += [f"**The light:** {op['light']}", ""]
    out += ["**What this painting teaches:**", ""]
    out += [f"- **{arc.card_name(sk['card'])}** (steps {', '.join(map(str, sk.get('steps') or []))}): "
            f"{sk.get('how', '')}" for sk in op.get("skills") or []]
    if op.get("road"):
        out += ["", f"**The way there:** {op['road']}"]
    out.append("")
    by = {s["id"]: s for s in les["steps"]}
    for stg in arc.stages_of(PICTURE):
        o = (a.get("stages") or {}).get(stg["id"]) or {}
        out += [f"## {stg['name']}", "", f"*{o.get('for', '')}*", ""]
        for x in stg["steps"]:
            s = by[x["id"]]
            out += [f"### Step {s['n']}: {s['name']}", "",
                    "**Paints:** " + "; ".join(f"{p['name']} ({p['recipe']})" for p in s.get("paints") or []), "",
                    f"**Brush:** {s.get('brushes')}", ""]
            for line in arc.page_lines(rec["final"].get(s["id"]) or []):
                k, _, t = line.partition(": ")
                out.append(f"- **{k}:** {t}")
            out += ["", f"![After step {s['n']}]({rel}/{s['n']:02d}.jpg)", ""]
        if o.get("end"):
            out += [f"*Where this stage ends:* {o['end']}", ""]
    if issues:
        out += ["## Known problems", "", "What the finisher listed for this lesson's pictures and paints:", ""]
        out += [f"- **{i.get('step_id')}** ({i.get('kind')}): {i.get('problem')}" for i in issues]
        out.append("")
    PAGE.write_text("\n".join(out))
    print(PAGE)


def lesson_page(args):
    """A sealed lesson's own page with the new words in place of the old, to paint from: a copy of the lesson with
    the words in `text.json`, published (not sealed), so the outline, the Where pictures, the recipes, the cards and
    the diagrams are the sealed lesson's. The page doesn't know an opening or a stage's lines yet (the design's
    section 7), so the opening is put under "Before you start" and a stage's two lines among its first and last
    steps' lines. The file goes in `output/v31-trial/`, which git ignores; it isn't put on the site."""
    import html
    setup()
    if SET != "site":
        raise SystemExit("a lesson page is made from a sealed lesson: the chickadee or the lavender balloon")
    rec = wc.state()["words"][SET][WORDS][PICTURE]
    les = wc.lesson_copy(SET, WORDS, "page", PICTURE)
    keep = {x["stage_id"]: x.get("construct") for x in json.loads((les / "text.json").read_text())["steps"]}
    wc.put_words(les, PICTURE, rec)
    a, t = rec["arc"], json.loads((les / "text.json").read_text())
    by = {x["stage_id"]: x for x in t["steps"]}
    for x in t["steps"]:
        if keep.get(x["stage_id"]):  # the sealed lesson's diagrams stay
            x["construct"] = keep[x["stage_id"]]
    for stg in arc.stages_of(PICTURE):
        o = (a.get("stages") or {}).get(stg["id"]) or {}
        ids = [x["id"] for x in stg["steps"] if x["id"] in by]
        if ids and o.get("for"):
            by[ids[0]]["lines"].insert(0, {"kind": "v4", "edited": True, "text": f"This stage ({stg['name']}): {o['for']}"})
        if ids and o.get("end"):
            by[ids[-1]]["lines"].append({"kind": "v4", "edited": True, "text": f"Where this stage ends: {o['end']}"})
    (les / "text.json").write_text(json.dumps(t, indent=1))
    pub = wc.tool(les, "publish", "--lesson", les)
    e, op = html.escape, a.get("opening") or {}
    block = ['<div class="v31-opening"><p><em>A trial page: pipeline v3.1\'s words on this lesson\'s own pictures. '
             'Not sealed, and not on the lessons site.</em></p>']
    if op.get("welcome"):
        block.append(f"<p>{e(op['welcome'])}</p>")
    if op.get("light"):
        block.append(f"<p><b>The light:</b> {e(op['light'])}</p>")
    if op.get("skills"):
        block.append("<p><b>What this painting teaches:</b></p><ul>" + "".join(
            f"<li><b>{e(arc.card_name(k['card']))}</b> (steps {', '.join(map(str, k.get('steps') or []))}): "
            f"{e(k.get('how', ''))}</li>" for k in op["skills"]) + "</ul>")
    if op.get("road"):
        block.append(f"<p><b>The way there:</b> {e(op['road'])}</p>")
    block.append("</div>")
    mark = "<h2>Before you start</h2>"
    page_html = (les / "lesson-standalone.html").read_text()
    if page_html.count(mark) != 1:
        raise SystemExit(f"the page has {page_html.count(mark)} 'Before you start' headings, not one")
    out = ROOT / "output" / "v31-trial" / f"{PICTURE}-v31.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page_html.replace(mark, mark + "".join(block)))
    print(json.dumps({"page": str(out), "mb": round(out.stat().st_size / 1e6, 1), "diagrams": pub.get("diagrams"),
                      "refused": pub.get("refused")}))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("words").add_argument("--again", action="store_true")
    for name in ("bench", "finish", "page", "report", "lesson"):
        sub.add_parser(name)
    for p in sub.choices.values():
        p.add_argument("--picture", choices=list(LESSONS), default="sleeping-cat")
    args = ap.parse_args(argv)
    choose(args.picture)
    {"bench": bench, "words": words, "finish": finish, "page": page, "report": report,
     "lesson": lesson_page}[args.cmd](args)


if __name__ == "__main__":
    main()
