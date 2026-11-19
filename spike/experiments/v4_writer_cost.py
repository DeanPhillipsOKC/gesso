"""Spike for #267 (v4's C3): cutting what the lesson's writer, the arc's call and the finisher cost.

Wave 1 settled what a writer is sent: one writer for the whole lesson in fixed lines (W1, `v4_teacher.py`'s
lesson-slots), then the long arc added by its own call (W2, `v4_arc.py`'s arc-add-long). This spike runs both, and a
finisher (review.json, the construction diagrams, notes.json) on their words, on lessons made by `v4_loop.py` with
C1's cuts, and measures every call the way C1 did (`v4_loop.api_costs`). Then it tries cuts on each.

The pictures stay: the words and the finisher run on the step pictures of C1's three lessons made with all of its
cuts (`output/*_v4loop_20261119-18341[58]`, `-183427`), so the chain isn't rendered again and a cut's two sides
share every picture (the owner's call, 2026-11-19: about $3.70 of renders in all). One new cat run, made with C1's
cuts up to the chain's checker (`v4_loop.py run --until checker`), is the fourth lesson: its words and finisher are
the baseline made as v4 would run them, and it answers whether #250's fix cut the cat's merges.

    .venv/bin/python spike/experiments/v4_writer_cost.py bench [--set c1|new]
    .venv/bin/python spike/experiments/v4_writer_cost.py words --variant base [--picture P] [--set c1]
    .venv/bin/python spike/experiments/v4_writer_cost.py finish --variant base --words base [--picture P]
    .venv/bin/python spike/experiments/v4_writer_cost.py packets
    .venv/bin/python spike/experiments/v4_writer_cost.py ab-words --variant lean
    .venv/bin/python spike/experiments/v4_writer_cost.py ab-finish --variant f-lean
    .venv/bin/python spike/experiments/v4_writer_cost.py report

The student test reads a variant's words with `v4_student.py --bench <work>/bench-c1 --work <work>/student
--words-from <work>/words-c1/<variant> --results spike/experiments/v4_writer_cost/<variant>.json`.

Results go in `spike/experiments/v4_writer_cost.json`: every call (`calls`, in v4_loop's ledger shape, priced the
API's way by the report), each variant's words and arc (`words`), each finisher's output (`finish`) and the graders
(`ab`). Pictures, bench folders and lesson copies go in a work folder outside the repository (`--work`). Experiment
code: it changes no tool, and copies a lesson before its finisher publishes it (`GESSO_HISTORY` keeps it out of
`site/history/`).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "bench"))
sys.path.insert(0, str(ROOT / "spike"))

import v4_arc as arc  # noqa: E402
import v4_loop as loop  # noqa: E402
import v4_student as student  # noqa: E402
import v4_teacher as teacher  # noqa: E402

RESULTS = HERE / "v4_writer_cost.json"
STUDENT_DIR = HERE / "v4_writer_cost"
WORK = Path(tempfile.gettempdir()) / "gesso-v4-writer-cost"
PICTURES = student.PICTURES
SEED = 267
LOCK = threading.Lock()

# The lessons the words and the finisher run on. c1: C1's three made with all its cuts (docs/spikes/v4-cost-cuts.md).
# new: one cat made for this spike with C1's cuts, after #250, up to the chain's checker.
SETS = {
    "c1": {"highland-cow": "highland-cow_v4loop_20261119-183415", "sleeping-cat": "sleeping-cat_v4loop_20261119-183421",
           "birch-grove": "birch-grove_v4loop_20261119-183427"},
    "new": {},  # filled by `bench --set new --lesson <folder>`, kept in the results file
}

# ------------------------------------------------------------------------------------------------------------ the cuts
WORD_CUTS = {
    "pics-small": "the writer's pictures at 512 pixels a side (pair halves and the change, from 784), the photo and "
                  "finish at 768 (from 1024), the arc's stage pictures at 480 (from 640)",
    "facts-lean": "the fact sheet without what a step's words don't use: the exact values in brackets, v3's Where line, "
                  "the part as the finish shows it, and the neighbours not painted yet",
    "feedback-changes": "the writer answers check-text's feedback with only the steps it changes, not the whole JSON",
    "arc-same": "the arc is the writer's own conversation's next message, so it reads the plan, cards and pictures from "
                "the cache rather than being sent them again",
    "effort-low": "the writer and the arc at low effort (Claude Code's default is medium)",
    "sonnet": "the writer and the arc on Claude Sonnet 5.5",
}
FINISH_CUTS = {
    "f-pics-small": "the finisher's step pictures at 384 pixels (from 768), the finish at 512",
    "f-look-if-needed": "the second message (look at the diagrams) only when publish draws fewer diagrams than were "
                        "specced",
    "f-split": "review.json and the notes from one call with no pictures; the diagrams from a second call, sent only "
               "diagrams.md, the words and the step pictures",
    "f-effort-low": "the finisher at low effort",
    "f-sonnet": "the finisher on Claude Sonnet 5.5",
}
WORD_VARIANTS = {
    "base": [],
    "lean": ["pics-small", "facts-lean", "feedback-changes", "arc-same"],
    "lean-sonnet": ["pics-small", "facts-lean", "feedback-changes", "arc-same", "sonnet"],
    "lean-low": ["pics-small", "facts-lean", "feedback-changes", "arc-same", "effort-low"],
}
FINISH_VARIANTS = {
    "base": [],
    "f-lean": ["f-pics-small", "f-look-if-needed"],
    "f-lean-sonnet": ["f-pics-small", "f-look-if-needed", "f-sonnet"],
    "f-lean-low": ["f-pics-small", "f-look-if-needed", "f-effort-low"],
    "f-split": ["f-pics-small", "f-look-if-needed", "f-split"],
}


# --------------------------------------------------------------------------------------------------- the results file
def state() -> dict:
    st = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    for k in ("calls", "ab"):
        st.setdefault(k, [])
    for k in ("words", "finish", "lessons"):
        st.setdefault(k, {})
    return st


def update(fn):
    import fcntl
    with LOCK:
        WORK.mkdir(parents=True, exist_ok=True)
        with open(WORK / "results.lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            st = state()
            fn(st)
            tmp = RESULTS.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(st, indent=1) + "\n")
            tmp.replace(RESULTS)


def lessons(set_: str) -> dict[str, str]:
    return SETS[set_] or state()["lessons"].get(set_, {})


class Ledger:
    """v4_loop's Helper logs here: each call tagged with what it was for."""

    def __init__(self, **tags):
        self.tags = tags

    def add(self, rec: dict):
        rec = {**self.tags, **rec}
        update(lambda st: st["calls"].append(rec))


class FakeRun:
    """What v4_loop.Helper needs of a run: the cuts (C1's caching), a working folder and a ledger."""

    def __init__(self, ledger: Ledger):
        self.cuts = {"api-cache"}
        self.cwd = WORK / "cwd"
        self.cwd.mkdir(parents=True, exist_ok=True)
        self.ledger = ledger


def helper(name: str, system: str, cuts: list[str], ledger: Ledger, prefix: str = "") -> loop.Helper:
    h = loop.Helper(FakeRun(ledger), name, system)
    if prefix + "sonnet" in cuts:
        h.model = "sonnet"
    if prefix + "effort-low" in cuts:
        h.effort = "low"
    return h


# ---------------------------------------------------------------------------------------------------------- the bench
def bench_dir(set_: str) -> Path:
    return WORK / f"bench-{set_}"


def point(set_: str):
    """Point the W1, W2 and student modules at this set's bench (they read module globals at call time)."""
    b = bench_dir(set_)
    teacher.BENCH = arc.BENCH = student.BENCH = b
    teacher.WORK = WORK / f"teacher-{set_}"


def bench(args):
    """A bench folder for each lesson, in the frozen bench's shape (packet.json, steps/, photo, finish, data/), and the
    writer's pictures (pair-NN, change-NN) from its steps, as v4_teacher makes them."""
    import packet as pk
    from PIL import Image
    if args.set == "new":
        if not args.lesson:
            raise SystemExit("bench --set new needs --lesson <folder>")
        les = Path(args.lesson).resolve()
        pic = les.name.split("_v4loop_")[0]
        update(lambda st: st["lessons"].setdefault("new", {}).__setitem__(pic, les.name))
        prepare_new(les)
    point(args.set)
    for pic, name in lessons(args.set).items():
        les = ROOT / "output" / name
        dest = bench_dir(args.set) / pic
        if dest.exists():
            shutil.rmtree(dest)
        pk.build_one(les, dest)
        data = dest / "data"
        (data / "words").mkdir(parents=True)
        for f in ("plan.json", "canvas.json", "text.json"):
            shutil.copy(les / f, data / f)
        for f in ("sheet.json", "dropped.json"):
            if (les / "words" / f).exists():
                shutil.copy(les / "words" / f, data / "words" / f)
        for s in sorted((les / "words").glob("stage-[0-9][0-9]")):
            (data / "words" / s.name).mkdir()
            for f in ("steps.json", "facts.md"):
                shutil.copy(s / f, data / "words" / s.name / f)
        d = teacher.WORK / "pictures" / pic
        d.mkdir(parents=True, exist_ok=True)
        for s in student.lesson(pic)["steps"]:
            n = s["n"]
            before, after = student.before_after(pic, n)
            k = teacher.PAIR_SIDE / max(after.size)
            size = (round(after.width * k), round(after.height * k))
            pair = Image.new("RGB", (size[0] * 2 + 12, size[1]), "white")
            pair.paste(before.resize(size, Image.LANCZOS), (0, 0))
            pair.paste(after.resize(size, Image.LANCZOS), (size[0] + 12, 0))
            pair.save(d / f"pair-{n:02d}.jpg", quality=88)
            teacher.change_picture(before, after).resize(size, Image.LANCZOS).save(d / f"change-{n:02d}.jpg",
                                                                                  quality=88)
        print(f"{args.set} {pic}: {len(student.lesson(pic)['steps'])} steps, {dest}")


def prepare_new(les: Path):
    """A lesson stopped after the chain's checker (`v4_loop.py run --until checker`): the fact sheet's folders
    (`packets`) and a publish, so the bench can be made from it. The words that publish shows are draft-text's."""
    env = {**os.environ, "GESSO_HISTORY": str(WORK / "history")}
    for args in (["packets", "--lesson", les], ["publish", "--lesson", les]):
        r = subprocess.run(loop.TOOLS + [str(a) for a in args], capture_output=True, text=True, cwd=ROOT, env=env)
        print(f"  $ {args[0]}: {r.returncode}", file=sys.stderr)


# ---------------------------------------------------------------------------------------------- what the writer reads
BRACKETS = re.compile(r" \((?:\d+ )?\d+(?:/\d+)?\)")  # "3 in (3 1/16)": the exact value the brief says not to use


def lean_facts(text: str) -> str:
    """The fact sheet without what the writer's lines don't use (cut `facts-lean`). check-text reads sheet.json, so
    the check is unchanged."""
    out = []
    for line in text.splitlines():
        if line.startswith("Where line (kept as it is"):
            continue  # v3's Where line, for draft-text
        if " as the finish shows it:" in line:
            continue  # the part when finished: the step's own measures say where its paint goes
        if line.startswith("Next to it:"):
            parts = [p for p in line[len("Next to it: "):].rstrip(".").split("; ") if "(not painted yet)" not in p]
            if not parts:
                continue
            line = "Next to it: " + "; ".join(parts) + "."
        out.append(BRACKETS.sub("", line))
    return "\n".join(out)


def writer_message(picture: str, cuts: list[str]) -> loop.Message:
    """v4_teacher.writer_message for one writer of the whole lesson in fixed lines, with the cuts' changes."""
    folders = teacher.stages(picture)
    ids, card_ids, nums = set(), [], []
    for f in folders:
        for s in teacher.stage_steps(f):
            ids.add(s["id"])
            nums.append(s["n"])
            if s.get("stroke") and s["stroke"] not in card_ids:
                card_ids.append(s["stroke"])
    facts = "\n\n".join((f / "facts.md").read_text() for f in folders)
    if "facts-lean" in cuts:
        facts = lean_facts(facts)
    small = "pics-small" in cuts
    m = loop.Message().text("Follow the brief. Everything you need is in this message.")
    m.text(f'<file name="brief.md">\n{teacher.brief("slots")}\n</file>')
    m.text(f'<file name="steps.md">\n{teacher.headers(picture, ids)}\n</file>')
    m.file(teacher.data(picture) / "plan.json", "plan.json")
    m.text(f'<file name="facts.md">\n{facts}\n</file>')
    m.text(f'<file name="cards.md">\n{teacher.card_text(card_ids)}\n</file>')
    d = teacher.WORK / "pictures" / picture
    for n in nums:
        m.picture(d / f"pair-{n:02d}.jpg", f"pair-{n:02d}.jpg", max_side=1036 if small else None)
        m.picture(d / f"change-{n:02d}.jpg", f"change-{n:02d}.jpg", max_side=512 if small else None)
    m.picture(teacher.BENCH / picture / "photo.jpg", "photo.jpg", max_side=768 if small else 1024)
    m.picture(teacher.BENCH / picture / "finish.jpg", "finish.jpg", max_side=768 if small else 1024)
    m.text("Reply with the JSON as one ```json block, then your one line.")
    return m


CHANGES_ONLY = ("\n\nReply with only the steps you change, in the same shape ({\"steps\": {\"<step id>\": {every line "
                "of that step}}}), as one ```json block. A step you leave out keeps its words.")


def arc_message_same(picture: str, words: dict, cuts: list[str]) -> loop.Message:
    """The arc's brief as the writer's next message (cut `arc-same`): the plan, steps, cards, photo and finish are
    already in the conversation, and a stage's end picture is the after half of its last step's pair."""
    ends = ", ".join(f"stage {i}: pair-{st['steps'][-1]['n']:02d}.jpg" for i, st in enumerate(arc.stages_of(picture), 1)
                     if st["steps"])
    brief = arc.add_brief(True).replace("- `photo.jpg` and `finish.jpg`, and `stage-NN.jpg`: the canvas at the end of "
                                        "each stage.", "- `photo.jpg` and `finish.jpg`, above; the canvas at the end of "
                                        "each stage is the after half (right) of its last step's pair: " + ends + ".")
    m = loop.Message().text("Your step words are done and checked; they stay as they are. Now a second job, on the "
                            "same lesson: follow this brief. `plan.json`, `steps.md` and `cards.md` are the ones "
                            "above.")
    m.text(f'<file name="brief.md">\n{brief}\n</file>')
    m.text(f'<file name="words.md">\n{arc.words_md(picture, words)}\n</file>')
    m.text("Reply with the JSON as one ```json block, then your one line.")
    return m


def arc_message_new(picture: str, cuts: list[str]) -> loop.Message:
    """v4_arc.add_message (arc-add-long), with the cuts' picture sizes."""
    if "pics-small" not in cuts:
        return arc.add_message(picture, True)
    m = arc.add_message(picture, True)
    # the same message with smaller pictures: rebuild its picture blocks
    out = loop.Message()
    pics = [("photo.jpg", teacher.BENCH / picture / "photo.jpg", 768),
            ("finish.jpg", teacher.BENCH / picture / "finish.jpg", 768)]
    pics += [(f"stage-{i:02d}.jpg", p, 480) for i, p in arc.stage_pictures(picture)]
    by_name = {n: (p, s) for n, p, s in pics}
    blocks = m.blocks
    i = 0
    while i < len(blocks):
        b = blocks[i]
        mt = re.match(r"Picture `([^`]+)`", b.get("text", "")) if b["type"] == "text" else None
        if mt and mt.group(1) in by_name:
            p, side = by_name[mt.group(1)]
            out.picture(p, mt.group(1), max_side=side)
            i += 2
            continue
        if b["type"] == "text":
            out.text(b["text"])
        i += 1
    return out


# ------------------------------------------------------------------------------------------------- the words, written
FINAL: dict[str, dict] = {}  # each picture's checked step lines, which v4_arc.compose reads as its `base_words`
arc.base_words = lambda pic: FINAL[pic]


def write_words(set_: str, variant: str, picture: str):
    """lesson-slots' writer, its check and one round of feedback (v4_teacher.write_one), then the long arc and its
    checks (v4_arc.write_one, arc-add-long), with the variant's cuts."""
    cuts = WORD_VARIANTS[variant]
    ledger = Ledger(set=set_, variant=variant, picture=picture, part="words")
    w = helper("writer", teacher.Writer.SYSTEM, cuts, ledger)
    a = w.ask_json(writer_message(picture, cuts), "W1 words")
    ids = {s["id"] for s in student.lesson(picture)["steps"]}
    words = {k: v for k, v in ((a or {}).get("steps") or {}).items() if k in ids}
    first_words = json.loads(json.dumps(words))
    text = teacher.text_of(picture, "slots", words)
    r1 = teacher.check(picture, text)
    fails1 = r1["failures"]
    if fails1:
        fb = teacher.feedback(fails1)
        if "feedback-changes" in cuts:
            fb = fb.replace("(write the whole JSON again, every step)", "(only the steps that change)") + CHANGES_ONLY
        again = w.ask_json(loop.Message().text(fb), "W1 feedback")
        words.update({k: v for k, v in ((again or {}).get("steps") or {}).items() if k in ids})
    text = teacher.text_of(picture, "slots", words)
    r2 = teacher.check(picture, text)
    gone = teacher.take_out(text, r2["failures"])
    r3 = teacher.check(picture, text)
    final = {t["stage_id"]: t["lines"] for t in text["steps"]}
    missing = [s["id"] for s in student.lesson(picture)["steps"] if not final.get(s["id"])]

    # the arc, on the final words (arc.compose reads them as `base_words`)
    with LOCK:
        FINAL[picture] = final
    if "arc-same" in cuts:
        h = w
        msg = arc_message_same(picture, final, cuts)
    else:
        h = helper("arc", teacher.Writer.SYSTEM, cuts, ledger)
        msg = arc_message_new(picture, cuts)
    obj = h.ask_json(msg, "W2 arc") or {}
    first_arc = json.loads(json.dumps(obj))
    composed = arc.compose(picture, "arc-add-long", obj)
    t = arc.text_for_check(picture, composed)
    t1 = [c for c in teacher.check(picture, t)["failures"] if "(back)" in c["field"]]
    a1 = arc.check_arc(picture, obj)
    if t1 or a1:
        again = h.ask_json(loop.Message().text(arc.feedback(t1, a1, False)), "W2 arc feedback")
        if again:
            obj = again
    composed = arc.compose(picture, "arc-add-long", obj)
    t = arc.text_for_check(picture, composed)
    r = teacher.check(picture, t)
    a2 = arc.check_arc(picture, obj)
    gone_arc = arc.take_out_arc(obj, a2)
    for c in arc.back_lines_gone(t, r["failures"]):
        x = obj.get("steps", {}).get(c["id"])
        if isinstance(x, dict) and x.pop("back", None):
            gone_arc.append({"where": f"step {c['id']}.back", "what": teacher.say(c), "sentence": c["sentence"]})
    composed = arc.compose(picture, "arc-add-long", obj)
    t = arc.text_for_check(picture, composed)
    r4 = teacher.check(picture, t)
    final_arc = {k: v for k, v in composed.items()}
    rec = {"first": first_words, "final_slots": final, "final": final_arc, "missing": missing,
           "arc": {"opening": obj.get("opening"), "stages": obj.get("stages")}, "first_arc": first_arc,
           "check": {"failures_first": len(fails1), "failures_second": len(r2["failures"]), "taken_out": gone,
                     "left_failing": len(r3["failures"]), "claims_final": len(r3["claims"]),
                     "arc_text_failures_first": len(t1), "arc_failures_first": len(a1), "arc_failures_second": len(a2),
                     "arc_taken_out": gone_arc,
                     "back_left_failing": len([c for c in r4["failures"] if "(back)" in c["field"]])},
           "backs": sum(any(x["kind"] == "back" for x in v) for v in final_arc.values()),
           "words_count": sum(len(" ".join(x["text"] for x in v).split()) for v in final.values()),
           "arc_words": arc.arc_words(obj)}
    update(lambda st: st["words"].setdefault(set_, {}).setdefault(variant, {}).__setitem__(picture, rec))
    print(f"words {set_} {variant} {picture}: {len(fails1)} failures, then {len(r2['failures'])}; {len(gone)} taken "
          f"out; arc {len(a1)}+{len(t1)} failures, {len(gone_arc)} taken out; {rec['backs']} back lines; "
          f"missing {missing}")


def words(args):
    point(args.set)
    pics = [args.picture] if args.picture else list(lessons(args.set))
    have = state()["words"].get(args.set, {}).get(args.variant, {})
    todo = [p for p in pics if p not in have or args.again]
    with ThreadPoolExecutor(len(todo) or 1) as ex:
        for f in [ex.submit(write_words, args.set, args.variant, p) for p in todo]:
            f.result()


def page_steps(rec: dict, picture: str) -> dict[str, list[str]]:
    return {sid: arc.page_lines(lines) for sid, lines in rec["final"].items()}


def packets(args):
    """Each variant's words as a bench packet for the student test (v4_arc's long-arc packets: the stage opener above
    a step, its end on the stage's last step only, the back line among the step's lines)."""
    st = state()
    for set_, variants in st["words"].items():
        point(set_)
        for variant, pics in variants.items():
            for pic, rec in pics.items():
                les = json.loads(json.dumps(student.lesson(pic)))
                intro = arc.intros(pic, rec["arc"], True)
                lines = page_steps(rec, pic)
                for s in les["steps"]:
                    s["lines"] = lines.get(s["id"]) or []
                    s["tip"] = ""
                    s["intro"] = intro.get(s["n"], "")
                les["opening"] = arc.opening_text(rec["arc"])
                d = WORK / f"words-{set_}" / variant / pic
                d.mkdir(parents=True, exist_ok=True)
                (d / "packet.json").write_text(json.dumps(les, indent=1))
                print(d / "packet.json")


# ------------------------------------------------------------------------------------------------------- the finisher
def lesson_copy(set_: str, wvariant: str, fvariant: str, picture: str) -> Path:
    """A copy of the lesson for one finisher to publish into: everything but the chain and the canvas folders,
    which are linked (the finisher's tools only read them)."""
    src = ROOT / "output" / lessons(set_)[picture]
    dest = WORK / "lessons" / set_ / f"{wvariant}+{fvariant}" / src.name
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("chain", "canvas", "lesson-*.html", "embed"))
    for d in ("chain", "canvas"):
        if (src / d).exists():
            (dest / d).symlink_to(src / d)
    return dest


def put_words(les: Path, picture: str, rec: dict):
    """The v4 words into the copy's text.json, as the page would show them (a slot's label in front of its text),
    each line marked edited so no tool redrafts it; the summary and tip v3 asked for are left empty."""
    t = json.loads((les / "text.json").read_text())
    lines = page_steps(rec, picture)
    for s in t["steps"]:
        s["lines"] = [{"kind": "v4", "text": x, "edited": True} for x in lines.get(s["stage_id"]) or []]
        s["summary"], s["tip"] = "", ""
        s.pop("construct", None)
    (les / "text.json").write_text(json.dumps(t, indent=1))
    (les / "v4_words.json").write_text(json.dumps({"opening": rec["arc"].get("opening"),
                                                   "stages": rec["arc"].get("stages")}, indent=1))


V3_TEXT_RULES = re.compile(r"no summary|no tip|its summary is|line \d+ is \d+ words|drafted lines|check-text|"
                           r"isn't one of its paints")


def tool(les: Path, *args) -> dict:
    env = {**os.environ, "GESSO_HISTORY": str(WORK / "history")}
    r = subprocess.run(loop.TOOLS + [str(a) for a in args], capture_output=True, text=True, cwd=ROOT, env=env)
    for line in reversed(r.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {"refused": r.stderr[-1500:]}


def words_json(text: dict, opening: dict) -> str:
    return json.dumps({"opening": opening.get("opening"), "stages": opening.get("stages"),
                       "steps": [{"step": s["stage_id"], "lines": [x["text"] for x in s.get("lines", [])]}
                                 for s in text["steps"]]})


V4_NOTE = ("The words are v4's: one teacher wrote every step in fixed lines (First, Start, Strokes, Where the paint "
           "sits, Leave, Stop when), checked against the fact sheet, and an opening and stage openers were added. v3's "
           "summary and tip aren't written, and v3's rule of 40 words a line doesn't hold, so `check`'s problems about "
           "those are left out below and aren't yours to fix. Don't rewrite the words.")


def finish_one(set_: str, wvariant: str, fvariant: str, picture: str):
    """The finisher (v4_loop.Run.finish's D4 and E2) on a copy of the lesson with the v4 words, with the variant's
    cuts. No seal: publish --final holds v3's text rules (a summary and tip a step, 40 words a line)."""
    cuts = FINISH_VARIANTS[fvariant]
    rec = state()["words"][set_][wvariant][picture]
    les = lesson_copy(set_, wvariant, fvariant, picture)
    put_words(les, picture, rec)
    if not (les / "words" / "dropped.json").exists():  # v3's check-text writes it; a v4 run's checks drop nothing there
        (les / "words" / "dropped.json").write_text("[]\n")
    st = json.loads((les / "v4" / "state.json").read_text())
    ck = tool(les, "check", "--lesson", les)
    ck["problems"] = [p for p in ck.get("problems") or [] if not V3_TEXT_RULES.search(p)]
    ledger = Ledger(set=set_, variant=f"{wvariant}+{fvariant}", picture=picture, part="finish")
    plan = json.loads((les / "plan.json").read_text())
    text = json.loads((les / "text.json").read_text())
    v4w = json.loads((les / "v4_words.json").read_text())
    side = 384 if "f-pics-small" in cuts else 768
    printed = json.dumps({
        "finish_issues": st.get("finish_issues"), "plan_check": st.get("plan_check"), "erase": st.get("erase"),
        "checker_marked_each_round": st.get("checker"), "build_steps_notes": st.get("build_notes"), "check_now": ck,
        "merged_by_check": st.get("merged")}, indent=1)
    S = loop.SKILL

    def pictures(m: loop.Message):
        for i, s in enumerate(text["steps"], 1):
            p = les / f"{i:02d}_{s['stage_id']}.png"
            if p.exists():
                m.picture(p, p.name, max_side=side)
        m.picture(les / "99_finish.png", "99_finish.png", max_side=512 if "f-pics-small" in cuts else 768)

    if "f-split" in cuts:
        h1 = helper("finisher-review", loop.NO_TOOLS + "You write a Gesso lesson's review.json and notes.json. You write "
                    "the files' contents; the program saves them.", cuts, ledger, "f-")
        m = loop.Message().file(S / "v3" / "run.md", "v3/run.md").file(S / "steps" / "notes.md")
        m.text(V4_NOTE + "\n\nWhat the tools printed that you need:\n" + printed)
        m.file(les / "words" / "dropped.json", "words/dropped.json").text("plan.json:\n" + json.dumps(plan))
        m.text("The lesson's words:\n" + words_json(text, v4w)).file(les / "notes.json", "notes.json (so far)")
        m.text("Do D4 (review.json) and 8b (notes) for this lesson, all but `beginner_check`, which the diagrams' "
               'writer adds. Reply with one ```json block: {"review": {review.json}, "notes": {"read": "", "order": "", '
               '"steps": {"<step id>": ""}, "merged_parts": {}, "learned": ["..."]}}')
        a = h1.ask_json(m, "D4 review and 8b notes", last=True)
        apply_finish(les, a)
        h = helper("finisher-diagrams", loop.NO_TOOLS + "You draw a Gesso lesson's construction diagrams. You write the "
                   "specs; the program saves them and runs publish.", cuts, ledger, "f-")
        m = loop.Message().file(S / "steps" / "diagrams.md").text(V4_NOTE)
        m.text("plan.json:\n" + json.dumps(plan)).text("The lesson's words:\n" + words_json(text, v4w))
        pictures(m)
        m.text("Do 8a (the beginner check and the diagrams) for this lesson. Reply with one ```json block: "
               '{"construct": {"<step id>": {construct spec}}, "notes": {"beginner_check": {...}}}')
        a = h.ask_json(m, "8a diagrams")
    else:
        h = helper("finisher", loop.NO_TOOLS + "You finish a Gesso lesson: its review, construction diagrams and notes. "
                   "You write the files' contents; the program saves them and runs publish.", cuts, ledger, "f-")
        m = loop.Message().file(S / "v3" / "run.md", "v3/run.md").file(S / "steps" / "8-finish.md")
        m.file(S / "steps" / "diagrams.md").file(S / "steps" / "notes.md")
        m.text(V4_NOTE + "\n\nEverything before this was done by the program. What the tools printed that you "
               "need:\n" + printed)
        m.file(les / "words" / "dropped.json", "words/dropped.json").text("plan.json:\n" + json.dumps(plan))
        m.text("The lesson's words (its opening, its stage openers, and each step's lines):\n" + words_json(text, v4w))
        m.file(les / "notes.json", "notes.json (so far)")
        pictures(m)
        m.text("Do D4 (review.json) and E2 (8a diagrams, 8b notes) for this lesson. Reply with one ```json block: "
               '{"review": {review.json}, "construct": {"<step id>": {construct spec}}, "notes": {"read": "", '
               '"order": "", "steps": {"<step id>": ""}, "beginner_check": {...}, "merged_parts": {}, '
               '"learned": ["..."]}}')
        a = h.ask_json(m, "D4 review, 8a diagrams, 8b notes")
    apply_finish(les, a)
    specced = len(a.get("construct") or {})
    pub = tool(les, "publish", "--lesson", les)
    prev = tool(les, "preview-diagrams", "--lesson", les)
    drawn = pub.get("diagrams")
    look = "f-look-if-needed" not in cuts or (isinstance(drawn, int) and drawn < specced) or "refused" in pub
    if look:
        m = loop.Message().text("publish printed:\n" + json.dumps({k: v for k, v in pub.items()
                                                                  if k not in ("steps",)})[:6000])
        if (les / "trials" / "diagrams.png").exists():
            m.picture(les / "trials" / "diagrams.png", "trials/diagrams.png")
        m.text('Look at your diagrams next to their steps. Reply with {"construct": {only the specs you change}, '
               '"notes": {only the fields you change}} or {} when nothing changes.')
        b = h.ask_json(m, "8a look at the diagrams", last=True)
        if b:
            apply_finish(les, b)
            pub = tool(les, "publish", "--lesson", les)
            prev = tool(les, "preview-diagrams", "--lesson", les)
    out = {"lesson": str(les), "review": json.loads((les / "review.json").read_text()) if (les / "review.json").exists()
           else None, "construct": {s["stage_id"]: s["construct"] for s in json.loads((les / "text.json").read_text())
                                    ["steps"] if s.get("construct")},
           "specced": specced, "drawn": pub.get("diagrams"), "looked": look,
           "publish_refused": str(pub.get("refused"))[:500] if "refused" in pub else None,
           "preview": {k: v for k, v in prev.items() if k != "steps"} if isinstance(prev, dict) else None}
    update(lambda s: s["finish"].setdefault(set_, {}).setdefault(f"{wvariant}+{fvariant}", {}).__setitem__(picture, out))
    print(f"finish {set_} {wvariant}+{fvariant} {picture}: {specced} specced, {out['drawn']} drawn, looked {look}")


def apply_finish(les: Path, a: dict):
    """v4_loop.Run.apply_finish, on the copy."""
    if not isinstance(a, dict):
        return
    if a.get("review"):
        (les / "review.json").write_text(json.dumps(a["review"], indent=1))
    if a.get("construct"):
        p = les / "text.json"
        t = json.loads(p.read_text())
        for s in t["steps"]:
            if s["stage_id"] in a["construct"]:
                s["construct"] = a["construct"][s["stage_id"]]
        p.write_text(json.dumps(t, indent=1))
    notes_p = les / "notes.json"
    n = json.loads(notes_p.read_text()) if notes_p.exists() else {}
    notes = dict(a.get("notes") or {})
    learned = notes.pop("learned", None)
    for k, v in notes.items():
        if k == "beginner_version" and "busy" in (n.get(k) or {}):
            v = {**v, "busy": n[k]["busy"]}
        n[k] = v
    if learned:
        n.setdefault("learned", []).extend(learned)
    notes_p.write_text(json.dumps(n, indent=1))


def finish(args):
    point(args.set)
    pics = [args.picture] if args.picture else list(lessons(args.set))
    have = state()["finish"].get(args.set, {}).get(f"{args.words}+{args.variant}", {})
    todo = [p for p in pics if p not in have or args.again]
    with ThreadPoolExecutor(len(todo) or 1) as ex:
        for f in [ex.submit(finish_one, args.set, args.words, args.variant, p) for p in todo]:
            f.result()


# ------------------------------------------------------------------------------------------------- the blind graders
def ab_words_one(set_: str, variant: str, pic: str, g: int) -> dict:
    """One blind grader (`bench/ab_grader.md`): the baseline's words against a cut's, on the same pictures. Each
    lesson's opening comes first, each stage's opener with its first step, a stage's end after its last step."""
    point(set_)
    les = student.lesson(pic)
    recs = {w: state()["words"][set_][w][pic] for w in ("base", variant)}
    sides = ["base", variant] if (g + random.Random(f"{pic}-{variant}-{SEED}").randrange(2)) % 2 else [variant, "base"]
    stages = arc.stages_of(pic)
    first_of = {st["steps"][0]["n"]: st for st in stages if st["steps"]}
    last_of = {st["steps"][-1]["n"]: st for st in stages if st["steps"]}
    brief = (HERE / "bench" / "ab_grader.md").read_text().replace(
        "You were given a folder.", "You were given everything in this message, in place of a folder.").replace(
        "Read only that folder.", "Read only this message.")
    m = loop.Message().text(f'<file name="ab_grader.md">\n{brief}\n</file>')
    m.text("The two lessons, A and B, have the same photo, finish and step pictures; each step's picture is shown "
           "once, with both lessons' words for it below. Each lesson opens with a few lines before step 1, and each "
           "stage with a line before its first step and one after its last.")
    m.picture(teacher.BENCH / pic / "photo.jpg", "photo.jpg", max_side=1024)
    m.picture(teacher.BENCH / pic / "finish.jpg", "finish.jpg", max_side=1024)
    m.text("\n\n".join(f"Lesson {side}'s opening:\n{arc.opening_text(recs[w]['arc'])}" for side, w in zip("AB", sides)))
    lines = {w: page_steps(recs[w], pic) for w in recs}
    for s in les["steps"]:
        words = {}
        for side, w in zip("AB", sides):
            text = student.step_text(s, les["canvas_in"], len(les["steps"]), {"lines": lines[w].get(s["id"]) or [],
                                                                              "tip": ""})
            o = lambda st: (recs[w]["arc"].get("stages") or {}).get(st["id"]) or {}  # noqa: E731
            if s["n"] in first_of:
                st = first_of[s["n"]]
                text = f"This stage, {st['name']}: {o(st).get('for', '')}\n\n" + text
            if s["n"] in last_of and o(last_of[s["n"]]).get("end"):
                text += f"\nWhere this stage ends: {o(last_of[s['n']])['end']}"
            words[side] = text
        m.text(f"Step {s['n']}. Its picture (the canvas after the step):")
        m.picture(teacher.BENCH / pic / "steps" / f"{s['n']:02d}.jpg", f"steps/{s['n']:02d}.jpg", max_side=640)
        m.text(f"Lesson A's words:\n{words['A']}\n\nLesson B's words:\n{words['B']}")
    m.text('Reply with grade.json as one ```json block (the brief\'s shape, `"picture": "' + pic + '"`), then the '
           "scores, the preference and how sure you are.")
    return grade(m, {"kind": "words", "set": set_, "variant": variant, "picture": pic, "grader": g}, sides)


def ab_finish_one(set_: str, variant: str, pic: str, g: int) -> dict:
    """One blind grader on two finishers' output for the same lesson (the same words and pictures): each lesson's
    construction diagrams beside their steps (preview-diagrams' picture) and its Known problems."""
    point(set_)
    les = student.lesson(pic)
    names = {"base": "base+base", variant: f"base+{variant}"}
    recs = {k: state()["finish"][set_][v][pic] for k, v in names.items()}
    sides = ["base", variant] if (g + random.Random(f"{pic}-{variant}-{SEED}").randrange(2)) % 2 else [variant, "base"]
    brief = (HERE / "bench" / "ab_grader.md").read_text().replace(
        "You were given a folder.", "You were given everything in this message, in place of a folder.").replace(
        "Read only that folder.", "Read only this message.")
    m = loop.Message().text(f'<file name="ab_grader.md">\n{brief}\n</file>')
    m.text("Here the two lessons, A and B, have the same photo, finish, step pictures and words, shown once. They "
           "differ only in what a page adds to them: construction diagrams (how to build a shape, drawn beside the "
           "steps that have one) and the Known problems list. Grade the two lessons whole, as the rubric says, with "
           "those in them: which would you paint from?")
    m.picture(teacher.BENCH / pic / "photo.jpg", "photo.jpg", max_side=1024)
    m.picture(teacher.BENCH / pic / "finish.jpg", "finish.jpg", max_side=1024)
    rec = state()["words"][set_]["base"][pic]
    lines = page_steps(rec, pic)
    for s in les["steps"]:
        m.text(student.step_text(s, les["canvas_in"], len(les["steps"]), {"lines": lines.get(s["id"]) or [], "tip": ""}))
        m.picture(teacher.BENCH / pic / "steps" / f"{s['n']:02d}.jpg", f"steps/{s['n']:02d}.jpg", max_side=512)
    for side, w in zip("AB", sides):
        r = recs[w]
        issues = (r.get("review") or {}).get("text_issues") or []
        m.text(f"===== Lesson {side}'s Known problems:\n" + ("\n".join(f"- step {x.get('step_id')}: {x.get('problem')} "
                                                                       f"({x.get('action')})" for x in issues) or "(none)"))
        p = Path(r["lesson"]) / "trials" / "diagrams.png"
        if p.exists() and r.get("drawn"):
            m.text(f"Lesson {side}'s construction diagrams, each beside its step's picture ({r['drawn']} diagrams):")
            m.picture(p, f"{side}/diagrams.png")
        else:
            m.text(f"Lesson {side} has no construction diagrams.")
    m.text('Reply with grade.json as one ```json block (the brief\'s shape, `"picture": "' + pic + '"`), then the '
           "scores, the preference and how sure you are.")
    return grade(m, {"kind": "finish", "set": set_, "variant": variant, "picture": pic, "grader": g}, sides)


def grade(m: loop.Message, tags: dict, sides: list[str]) -> dict:
    cwd = WORK / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    r = loop.call_claude(m.blocks, "You have no tools. You grade one blind A/B pair, in the owner's place.", cwd=cwd,
                         cache="none")
    try:
        a = loop.last_json(r["text"])
    except ValueError:
        a = {}
    prefer = a.get("prefer")
    out = {**tags, "A": sides[0], "B": sides[1], "prefer": prefer,
           "preferred": sides["AB".index(prefer)] if prefer in ("A", "B") else "none",
           "scores": {sides["AB".index(k)]: v for k, v in (a.get("scores") or {}).items() if k in ("A", "B")},
           "note": a.get("note", ""), "cost_usd": round(loop.cost(r["usage"]), 5), "seconds": r["seconds"],
           "pictures": m.pictures}
    update(lambda st: st["ab"].append(out))
    print(f"ab {tags['kind']} {tags['variant']} {tags['picture']} g{tags['grader']}: prefers {out['preferred']}, "
          f"${out['cost_usd']:.3f}")
    return out


def ab(args, kind: str):
    done = {(r["kind"], r["set"], r["variant"], r["picture"], r["grader"]) for r in state()["ab"]}
    jobs = [(args.set, args.variant, p, g) for p in lessons(args.set) for g in (1, 2)
            if (kind, args.set, args.variant, p, g) not in done]
    fn = ab_words_one if kind == "words" else ab_finish_one
    with ThreadPoolExecutor(6) as ex:
        for f in [ex.submit(fn, *j) for j in jobs]:
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                print(f"  failed: {e}", file=sys.stderr)


# ------------------------------------------------------------------------------------------------------------ report
def solo(path: Path) -> dict:
    ss = json.loads(path.read_text()) if path.exists() else {}
    g = {}
    for r in ss.get("carry_grades", []):
        if r.get("solo") and r["condition"] == "words":
            g.setdefault((r["picture"], r["n"]), []).append(r["grade"])
    return {k: sum(v) / len(v) for k, v in g.items()}, sum(r["render_usd"] for r in ss.get("carry", []))


def report(args) -> dict:
    import numpy as np
    st = state()
    calls = st["calls"]
    api = loop.api_costs(calls)
    for c, a in zip(calls, api):
        c["api_usd"] = a
    out = {"words": {}, "finish": {}, "student": {}, "ab": {}}
    for set_ in ("c1", "new"):
        for kind, key in (("words", "words"), ("finish", "finish")):
            for variant, pics in (st[key].get(set_) or {}).items():
                v = out[kind].setdefault(f"{set_}:{variant}", {"pictures": {}})
                for pic in pics:
                    cs = [c for c in calls if c["set"] == set_ and c["variant"] == variant and c["picture"] == pic
                          and c["part"] == kind]
                    by = {}
                    for c in cs:
                        b = by.setdefault(c["helper"], {"calls": 0, "api_usd": 0.0, "charged_usd": 0.0, "sent": 0,
                                                        "read": 0, "output": 0, "thinking": 0, "picture_tokens": 0})
                        b["calls"] += 1
                        b["api_usd"] += c["api_usd"]
                        b["charged_usd"] += c["cost_usd"]
                        b["sent"] += c["input_tokens"] + c["cache_write_tokens"]
                        b["read"] += c["cache_read_tokens"]
                        b["output"] += c["output_tokens"]
                        b["thinking"] += c.get("thinking_tokens") or 0
                        b["picture_tokens"] += c["sent"]["picture_tokens"]
                    for b in by.values():
                        b["api_usd"] = round(b["api_usd"], 3)
                        b["charged_usd"] = round(b["charged_usd"], 3)
                    p = {"api_usd": round(sum(c["api_usd"] for c in cs), 3), "calls": len(cs), "by_helper": by,
                         "models": sorted({m for c in cs for m in c.get("model") or []})}
                    if kind == "words":
                        r = pics[pic]
                        p.update(words=r["words_count"], arc_words=r["arc_words"], backs=r["backs"],
                                 check=r["check"] | {"taken_out": len(r["check"]["taken_out"]),
                                                     "arc_taken_out": len(r["check"]["arc_taken_out"])},
                                 missing=r["missing"])
                    else:
                        r = pics[pic]
                        p.update(specced=r["specced"], drawn=r["drawn"], looked=r["looked"],
                                 known_problems=len((r.get("review") or {}).get("text_issues") or []))
                    v["pictures"][pic] = p
                v["api_usd_mean"] = round(float(np.mean([p["api_usd"] for p in v["pictures"].values()])), 3)
    base_g, _ = solo(STUDENT_DIR / "base.json")
    for f in sorted(STUDENT_DIR.glob("*.json")) if STUDENT_DIR.exists() else []:
        g, renders = solo(f)
        rows = {"renders_usd": round(renders, 3), "pictures": {}}
        for pic in PICTURES:
            mine = {k: x for k, x in g.items() if k[0] == pic}
            both = [k for k in mine if k in base_g]
            rows["pictures"][pic] = {"carry_grade": round(float(np.mean(list(mine.values()))), 2) if mine else None,
                                     "graded": len(mine),
                                     "vs_base": round(float(np.mean([g[k] - base_g[k] for k in both])), 2) if both
                                     and f.stem != "base" else None}
        both = [k for k in g if k in base_g]
        if both and f.stem != "base":
            d = np.array([g[k] - base_g[k] for k in both])
            rows["vs_base"] = {"mean": round(float(d.mean()), 2), "se": round(float(d.std(ddof=1) / np.sqrt(len(d))), 2),
                               "steps": len(d), "rose": int((d > 0).sum()), "fell": int((d < 0).sum())}
        rows["all"] = round(float(np.mean(list(g.values()))), 2) if g else None
        out["student"][f.stem] = rows
    for r in st["ab"]:
        k = f"{r['kind']}:{r['set']}:{r['variant']}"
        a = out["ab"].setdefault(k, {"for_cut": 0, "for_base": 0, "none": 0, "reads": [], "cost_usd": 0.0})
        a["for_cut" if r["preferred"] == r["variant"] else "for_base" if r["preferred"] == "base" else "none"] += 1
        a["cost_usd"] = round(a["cost_usd"] + r["cost_usd"], 3)
        a["reads"].append({"picture": r["picture"], "grader": r["grader"], "preferred": r["preferred"],
                           "paintable": {k2: (v2 or {}).get("paintable") for k2, v2 in (r.get("scores") or {}).items()},
                           "note": r["note"]})
    update(lambda s: s.__setitem__("report", out))
    print(json.dumps(out, indent=1))
    return out


def main(argv=None):
    global WORK
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=WORK)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bench")
    b.add_argument("--set", choices=list(SETS), default="c1")
    b.add_argument("--lesson", help="for --set new: the lesson v4_loop stopped after the chain's checker")
    w = sub.add_parser("words")
    w.add_argument("--variant", choices=list(WORD_VARIANTS), required=True)
    f = sub.add_parser("finish")
    f.add_argument("--variant", choices=list(FINISH_VARIANTS), required=True)
    f.add_argument("--words", choices=list(WORD_VARIANTS), default="base")
    for p in (w, f):
        p.add_argument("--set", choices=list(SETS), default="c1")
        p.add_argument("--picture")
        p.add_argument("--again", action="store_true")
    sub.add_parser("packets")
    for name, choices in (("ab-words", WORD_VARIANTS), ("ab-finish", FINISH_VARIANTS)):
        p = sub.add_parser(name)
        p.add_argument("--variant", choices=[c for c in choices if c != "base"], required=True)
        p.add_argument("--set", choices=list(SETS), default="c1")
    sub.add_parser("report")
    args = ap.parse_args(argv)
    WORK = args.work
    {"bench": bench, "words": words, "finish": finish, "packets": packets, "report": report,
     "ab-words": lambda a: ab(a, "words"), "ab-finish": lambda a: ab(a, "finish")}[args.cmd](args)


if __name__ == "__main__":
    main()
