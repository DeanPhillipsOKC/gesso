"""Spike for #255 (v4, W2): the lesson has an arc.

On the frozen bench, on top of the teacher spike's adopted writer (`lesson-slots`, `v4_teacher.py`), so only the
arc differs. Three new things a lesson says:

- **an opening**: the two or three skills this painting teaches (each one a stroke card the lesson uses, and the
  steps that use it) and the road to the finish;
- **a stage opener** for each stage: what the stage is for, and what the canvas looks like at its end;
- **a step that points back**: a line ("As in step 8: ...") on a step that uses a stroke or a paint an earlier step
  already used.

Two variants:

- `arc-add`: one new, cheap call reads lesson-slots' words as they are (frozen), the plan, the cards, the photo,
  the finish and each stage's last picture, and adds the arc. It changes none of the step's lines.
- `arc-whole`: the lesson-slots writer itself (the same message and brief) with the arc added to its brief, writing
  the whole lesson in one go, then the same check and one round of feedback.

The checks, beside check-text (which holds every number and side in a step's lines, the back line included):

- a back line must point at an earlier step that shares the step's stroke card or one of its paints;
- an opening's skill must be a stroke card the lesson uses, on steps that use it;
- an opener (the road, a skill's sentence, a stage opener) says no number and no side: the sheet measures a step,
  not a stage, so nothing there could be checked.

A failure goes back to the writer once; what still fails is taken out (a sentence, or a back line whole).

How the arc reaches the tests: the student (carry, `v4_student.py`) reads a step's stage opener above the step (the
page shows it at the top of the stage, and the painter has read it on the way) and the back line among its lines.
It doesn't read the opening: that names skills and has nothing to paint. The blind graders read everything: the
opening, then each stage's opener above its first step.

    .venv/bin/python spike/experiments/v4_arc.py write --variant arc-add [--picture P]
    .venv/bin/python spike/experiments/v4_arc.py packets
    .venv/bin/python spike/experiments/v4_arc.py ab --variant arc-add
    .venv/bin/python spike/experiments/v4_arc.py report
    .venv/bin/python spike/experiments/v4_arc.py show sleeping-cat

`packets` writes `<work>/words/<variant>/<picture>/packet.json` for `v4_student.py --words-from`. Results go in
`spike/experiments/v4_arc.json`, the student test's in `spike/experiments/v4_arc/<variant>.json`. Experiment code:
it reads the frozen bench and the teacher spike's words, and changes no tool.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "spike"))

import v4_student as student  # noqa: E402
import v4_teacher as teacher  # noqa: E402

BENCH = teacher.BENCH
PICTURES = student.PICTURES
RESULTS = HERE / "v4_arc.json"
STUDENT_DIR = HERE / "v4_arc"
BASE = "lesson-slots"  # the teacher spike's adopted words: the baseline
BASE_STUDENT = HERE / "v4_teacher" / f"{BASE}.json"
WORK = Path(tempfile.gettempdir()) / "gesso-v4-arc"
VARIANTS = ["arc-add", "arc-whole", "arc-add-long"]
# arc-add-long (the owner, 2026-11-19, after reading the cat's lesson: "Make the opening longer and add more step
# callbacks"): arc-add with a fuller opening (a welcome, the light, two or three sentences a skill, a longer road)
# and a back line wherever a step repeats a stroke or a paint, not one step in four.
SEED = 255
LOCK = threading.Lock()
NUMBER_RE = re.compile(r"\d")


# ------------------------------------------------------------------------------------------------------- the lesson
def stages_of(picture: str) -> list[dict]:
    """The plan's stages in order: {id, name, steps: [{n, id, stroke, paints}]}, numbered as the packet is."""
    num = {s["id"]: s["n"] for s in teacher.packet(picture)["steps"]}
    out = []
    for st in teacher.plan(picture)["stages"]:
        steps = [{"n": num[s["id"]], "id": s["id"], "stroke": s.get("stroke"), "paints": list(s.get("paints") or [])}
                 for s in st["steps"] if s["id"] in num]
        out.append({"id": st["id"], "name": st["name"], "steps": steps})
    return out


def steps_by_n(picture: str) -> dict[int, dict]:
    return {s["n"]: s for st in stages_of(picture) for s in st["steps"]}


def base_words(picture: str) -> dict:
    """lesson-slots' final words: {step id: [{kind, text}]}."""
    return json.loads(teacher.RESULTS.read_text())["words"][BASE][picture]["final"]


# --------------------------------------------------------------------------------------------------------- the brief
ARC = """## The arc of the lesson

The steps are not 20 separate forms: the lesson has an arc, and you write it too. Everything in it comes from the
plan, the cards and the pictures: no new technique, and no stroke or paint the lesson doesn't use.

- **The opening** (read once, before step 1): `skills`, the two or three things this painting teaches a beginner.
  Each one is a stroke card the lesson uses (`card`, its id from the cards), with the steps that use it (`steps`,
  their numbers) and one sentence (`how`) of what the painter learns doing it here. Pick the cards that do the most
  work in this painting, not every card. Then `road`: two to four sentences of the way to the finish, the stages in
  order and why that order (from the plan's `why`).
- **A stage opener** for every stage (read at the top of the stage): `for`, one sentence of what the stage is for;
  and `end`, one sentence of what the canvas looks like at its end (from that stage's last picture).
- **A step that points back** (`back`, on a step only when it helps): when a step uses a stroke or a paint an
  earlier step already used, a line that ties the two ("the same dry tap you used for the leaves, now lighter").
  `step` is the earlier step's number; it must share this step's stroke card or one of its paints. Most steps that
  could point back are better without it: use it where a beginner would think "I've done this", up to about one
  step in four. It adds to the step, and never replaces what the step says: the step must still say how.

**No numbers and no side words in the opening or the stage openers** (no inches, no left, right, top, bottom,
upper, lower, above, below, under, beside): the sheet measures a step, not a stage, so a tool can't check them
there, and a sentence with one is taken out. Name things by what they are. A back line is a step's line and follows
the step's rules above. Plain words, short sentences.
"""

ADD_BRIEF = """# Brief: give a beginner acrylic lesson its arc (Gesso, a v4 spike)

You are a painting teacher. A lesson for this painting is written: every step's name, paints, brush and stroke card,
and the words that tell a beginner how to do it (`words.md`). The words are good and stay as they are. What the
lesson lacks is an arc: nothing says what the painter will learn, why the steps come in this order, or that a step
repeats a stroke the painter already did. You write that.

The painter is a beginner with acrylics, a white canvas, the photo, and this lesson on a phone.

## What you are sent

- `plan.json`: the lesson's plan: the things in the painting, the light, why the stages come in their order, and
  every stage and step.
- `steps.md`: every step's header as the page shows it, with its stroke card.
- `cards.md`: every stroke card the lesson uses.
- `words.md`: every step's words, as the painter reads them.
- `photo.jpg` and `finish.jpg`, and `stage-NN.jpg`: the canvas at the end of each stage.

{arc}

## What to write

Reply with one ```json block, then one line: anything you couldn't square.

```json
{{"opening": {{"skills": [{{"card": "<card id>", "steps": [3, 8], "how": "..."}}], "road": "..."}},
 "stages": {{"<stage id>": {{"for": "...", "end": "..."}}}},
 "steps": {{"<step id>": {{"back": {{"step": 8, "text": "..."}}}}}}}}
```

`steps` holds only the steps that point back.
"""

WHOLE_JSON = """

With the arc, the reply's JSON is:

```json
{"opening": {"skills": [{"card": "<card id>", "steps": [3, 8], "how": "..."}], "road": "..."},
 "stages": {"<stage id>": {"for": "...", "end": "..."}},
 "steps": {"<step id>": {"first": "", "start": "...", "back": {"step": 8, "text": "..."}, "strokes": "...", "inside": "...", "leave": "...", "stop": "..."}}}
```

Every step has its lines; `back` only where a step points back."""


LONG = """## Longer, and more steps that point back (this run)

The owner read a lesson with a short opening and few back lines, and asked for more of both. So, in place of the
lengths above:

- **The opening is longer.** Add `welcome`: two or three sentences on what the painter is about to make and what
  will make it sing (the subject, its focal point, the mood of the light), as a teacher would say it before the
  first brushstroke. Add `light`: one or two sentences on where the light comes from in this painting and what it
  does to the things in it, since many steps put paint where the light falls or doesn't (name the light by its
  source, "the window light", "the low sun", not by a side). Each skill's `how` is two or three sentences: what the
  stroke is, where in this painting it does its work, and what to watch for (from the card). `road` is four to six
  sentences: every stage in order, what each one adds, and why the order (from the plan's `why`).
- **More steps point back.** Give a back line to every step that repeats an earlier step's stroke card or one of
  its paints, where saying so helps a beginner: they've done this, and here is what's different this time (the
  paint, the brush, the size, where it goes). That is likely about half the steps. Skip a step only when the tie is
  empty ("the same paint" with nothing else to say), and point to the earlier step a painter would remember best,
  not always the one just before.

The rules stay: no numbers and no side words in the opening or the stage openers, and a back line follows the
step's rules.
"""

LONG_JSON = """With this run, the opening's JSON also has the welcome and the light:

```json
{"opening": {"welcome": "...", "light": "...", "skills": [{"card": "<card id>", "steps": [3, 8], "how": "..."}], "road": "..."}}
```
"""


def add_brief(long: bool = False) -> str:
    out = ADD_BRIEF.format(arc=ARC + ("\n" + LONG if long else ""))
    return out + ("\n" + LONG_JSON if long else "")


def whole_form() -> str:
    """lesson-slots' form, with the arc and its JSON after it."""
    return teacher.FORM["slots"] + "\n\n" + ARC + WHOLE_JSON


def words_md(picture: str, words: dict) -> str:
    out = ["# Every step's words, as the painter reads them", ""]
    for s in teacher.packet(picture)["steps"]:
        out.append(f"## Step {s['n']} `{s['id']}`: {s['name']}")
        out += [f"- {x}" for x in teacher.page_lines("slots", words.get(s["id"]) or [])]
        out.append("")
    return "\n".join(out)


def stage_pictures(picture: str) -> list[tuple[int, Path]]:
    return [(i, BENCH / picture / "steps" / f"{st['steps'][-1]['n']:02d}.jpg")
            for i, st in enumerate(stages_of(picture), 1) if st["steps"]]


def add_message(picture: str, long: bool = False):
    from v4_loop import Message
    folders = teacher.stages(picture)
    ids, card_ids = set(), []
    for f in folders:
        for s in teacher.stage_steps(f):
            ids.add(s["id"])
            if s.get("stroke") and s["stroke"] not in card_ids:
                card_ids.append(s["stroke"])
    m = Message().text("Follow the brief. Everything you need is in this message.")
    m.text(f'<file name="brief.md">\n{add_brief(long)}\n</file>')
    m.file(teacher.data(picture) / "plan.json", "plan.json")
    m.text(f'<file name="steps.md">\n{teacher.headers(picture, ids)}\n</file>')
    m.text(f'<file name="cards.md">\n{teacher.card_text(card_ids)}\n</file>')
    m.text(f'<file name="words.md">\n{words_md(picture, base_words(picture))}\n</file>')
    m.picture(BENCH / picture / "photo.jpg", "photo.jpg", max_side=1024)
    m.picture(BENCH / picture / "finish.jpg", "finish.jpg", max_side=1024)
    for i, p in stage_pictures(picture):
        m.picture(p, f"stage-{i:02d}.jpg", max_side=640)
    m.text("Reply with the JSON as one ```json block, then your one line.")
    return m


def whole_message(picture: str):
    """The lesson-slots writer's own message (`v4_teacher.writer_message`), its brief carrying the arc."""
    teacher.FORM["arc"] = whole_form()
    try:
        return teacher.writer_message(picture, "arc", teacher.stages(picture))
    finally:
        teacher.FORM.pop("arc", None)


# ---------------------------------------------------------------------------------------------------- the checks
# The brief's side words that the student's SIDE_RE (made for swapping sides) doesn't hold, and lengths in words.
MORE_SIDES = re.compile(r"\b(under|underneath|beneath|beside|besides?)\b|\b(one|two|three|four|five|six|seven|eight|nine|"
                        r"ten|half|quarter)\s+(inch|inches)\b", re.I)


def has_claim(sentence: str) -> bool:
    """A number or a side word: what an opener mustn't say."""
    return bool(NUMBER_RE.search(sentence) or student.SIDE_RE.search(sentence) or MORE_SIDES.search(sentence))


def sentences(text: str) -> list[str]:
    from facts import sentences as fs
    return [x for x in fs(text or "") if x.strip()]


def check_arc(picture: str, arc: dict) -> list[dict]:
    """The arc's own failures: {where, what, sentence?}. `where` is `opening.road`, `opening.skill N`,
    `stage <id>.for|end` or `step <id>.back`."""
    stages = stages_of(picture)
    by_n = steps_by_n(picture)
    num = {s["id"]: s["n"] for s in by_n.values()}
    used = {s["stroke"] for s in by_n.values() if s["stroke"]}
    out = []

    def claims(where, text):
        for sent in sentences(text):
            if has_claim(sent):
                out.append({"where": where, "what": "an opener says no number and no side word", "sentence": sent})

    op = arc.get("opening") or {}
    skills = op.get("skills") or []
    if not 2 <= len(skills) <= 3:
        out.append({"where": "opening.skills", "what": f"two or three skills, not {len(skills)}"})
    for i, sk in enumerate(skills, 1):
        card, ns = sk.get("card"), sk.get("steps") or []
        if card not in used:
            out.append({"where": f"opening.skill {i}", "what": f"`{card}` isn't a stroke card this lesson uses"})
        bad = [n for n in ns if n not in by_n or by_n[n]["stroke"] != card]
        if bad or not ns:
            out.append({"where": f"opening.skill {i}",
                        "what": f"steps {bad or ns} don't use the card `{card}`" if ns else "no steps given"})
        claims(f"opening.skill {i}", sk.get("how") or "")
    if not (op.get("road") or "").strip():
        out.append({"where": "opening.road", "what": "the road is missing"})
    claims("opening.road", op.get("road") or "")
    for k in ("welcome", "light"):  # the long run's (arc-add-long)
        claims(f"opening.{k}", op.get(k) or "")
    for st in stages:
        o = (arc.get("stages") or {}).get(st["id"]) or {}
        for k in ("for", "end"):
            if not (o.get(k) or "").strip():
                out.append({"where": f"stage {st['id']}.{k}", "what": "missing"})
            claims(f"stage {st['id']}.{k}", o.get(k) or "")
    for sid, w in (arc.get("steps") or {}).items():
        b = (w or {}).get("back") if isinstance(w, dict) else None
        if not b or sid not in num:
            continue
        here, there = by_n[num[sid]], by_n.get(b.get("step"))
        if there is None or there["n"] >= here["n"]:
            out.append({"where": f"step {sid}.back", "what": f"step {b.get('step')} isn't an earlier step"})
        elif there["stroke"] != here["stroke"] and not set(there["paints"]) & set(here["paints"]):
            out.append({"where": f"step {sid}.back",
                        "what": f"step {there['n']} shares neither this step's stroke card ({here['stroke']}) nor a "
                                f"paint ({', '.join(here['paints'])})"})
    return out


def back_of(w) -> dict | None:
    b = w.get("back") if isinstance(w, dict) else None
    if isinstance(b, dict) and str(b.get("text") or "").strip() and isinstance(b.get("step"), int):
        return {"step": b["step"], "text": str(b["text"]).strip()}
    return None


def step_lines(slots: list[dict], back: dict | None) -> list[dict]:
    """A step's lines with its back line just before its strokes (or first, after `first`)."""
    if not back:
        return list(slots)
    line = {"kind": "back", "step": back["step"], "text": back["text"]}
    out, put = [], False
    for x in slots:
        if not put and x["kind"] not in ("first", "start"):
            out.append(line)
            put = True
        out.append(x)
    return out if put else out + [line]


def page_lines(lines: list[dict]) -> list[str]:
    labels = dict(teacher.SLOTS)
    return [f"As in step {x['step']}: {x['text']}" if x["kind"] == "back" else f"{labels[x['kind']]}: {x['text']}"
            for x in lines if x["text"].strip()]


def compose(picture: str, variant: str, arc: dict) -> dict:
    """The lesson's words: {step id: [line]}. arc-add keeps lesson-slots' lines; arc-whole takes the writer's."""
    base = base_words(picture)
    out = {}
    for s in teacher.packet(picture)["steps"]:
        w = (arc.get("steps") or {}).get(s["id"]) or {}
        slots = (base.get(s["id"]) or []) if variant.startswith("arc-add") else teacher.lines_of("slots", w)
        out[s["id"]] = step_lines(slots, back_of(w))
    return out


def text_for_check(picture: str, words: dict) -> dict:
    return {"steps": [{"stage_id": s["id"], "summary": "", "tip": "", "lines": words.get(s["id"]) or []}
                      for s in teacher.packet(picture)["steps"]]}


def feedback(text_fails: list[dict], arc_fails: list[dict], whole: bool) -> str:
    lines = [f"- {teacher.say(c)}\n  in: \"{c['sentence']}\"" for c in text_fails]
    lines += [f"- {c['where']}: {c['what']}" + (f"\n  in: \"{c['sentence']}\"" if c.get("sentence") else "")
              for c in arc_fails]
    what = "every step, the opening and the stage openers" if whole else "the opening, the stage openers and the back lines"
    return ("# The checker's failures\n\nFix each one (write the whole JSON again: " + what + "): use the fact the "
            "sheet gives, or say it without a number or a side. What still fails is taken out.\n\n"
            + "\n".join(lines) + "\n")


def take_out_arc(arc: dict, fails: list[dict]) -> list[dict]:
    """Every arc failure that's still there, taken out: a sentence with a claim, a skill or a back line whole."""
    gone = []
    op = arc.setdefault("opening", {})
    drop_skills = set()
    for c in fails:
        w = c["where"]
        if w.startswith("step ") and w.endswith(".back"):
            sid = w[5:-5]
            if isinstance(arc.get("steps", {}).get(sid), dict) and arc["steps"][sid].pop("back", None):
                gone.append(c)
        elif w.startswith("opening.skill "):
            i = int(w.split()[-1]) - 1
            if c.get("sentence"):
                sk = op["skills"][i]
                sk["how"] = " ".join(x for x in sentences(sk.get("how")) if x.strip() != c["sentence"].strip())
            else:
                drop_skills.add(i)
            gone.append(c)
        elif c.get("sentence"):
            if w in ("opening.road", "opening.welcome", "opening.light"):
                k = w.split(".")[1]
                op[k] = " ".join(x for x in sentences(op.get(k)) if x.strip() != c["sentence"].strip())
            else:
                sid, k = w[6:].rsplit(".", 1)
                o = arc["stages"][sid]
                o[k] = " ".join(x for x in sentences(o.get(k)) if x.strip() != c["sentence"].strip())
            gone.append(c)
    if drop_skills:
        op["skills"] = [sk for i, sk in enumerate(op.get("skills") or []) if i not in drop_skills]
    return gone


def back_lines_gone(text: dict, failures: list[dict]) -> list[dict]:
    """check-text's failures on a back line: the line goes whole, as `take_out` would take its one sentence."""
    return [c for c in failures for f in c["field"].split(" and ") if "(back)" in f]


# ---------------------------------------------------------------------------------------------- the results file
def state() -> dict:
    st = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    st.setdefault("arc", {})
    st.setdefault("calls", [])
    st.setdefault("ab", [])
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


class Writer(teacher.Writer):
    """The teacher spike's writer, logging to this spike's file."""

    def ask(self, m, label: str):
        from v4_loop import Message, call_claude, cost, last_json
        cwd = WORK / "cwd"
        cwd.mkdir(parents=True, exist_ok=True)
        r = call_claude(m.blocks, self.SYSTEM, session=self.session, cwd=cwd)
        self.session = r["session"]
        u = r["usage"]
        rec = {"variant": self.variant, "picture": self.picture, "label": label, "seconds": r["seconds"],
               "input_tokens": u.get("input_tokens", 0), "cache_write_tokens": u.get("cache_creation_input_tokens", 0),
               "cache_read_tokens": u.get("cache_read_input_tokens", 0), "output_tokens": u.get("output_tokens", 0),
               "cost_usd": round(cost(u), 5), "pictures": m.pictures, "picture_tokens": m.picture_tokens}
        update(lambda st: st["calls"].append(rec))
        print(f"  [{self.variant} {self.picture}] {label}: ${rec['cost_usd']:.3f}, {r['seconds']} s", file=sys.stderr)
        try:
            return last_json(r["text"]), r["text"]
        except ValueError:
            return self.ask(Message().text("Your reply had no JSON I could read. Send the same answer again as one "
                                           "```json block, and nothing else."), label + " (JSON again)")


def write_one(variant: str, picture: str):
    from v4_loop import Message
    whole = variant == "arc-whole"
    w = Writer(variant, picture, "lesson")
    arc, _ = w.ask(whole_message(picture) if whole else add_message(picture, variant == "arc-add-long"), "first words")
    arc = arc or {}
    first = json.loads(json.dumps(arc))
    words = compose(picture, variant, arc)
    text = text_for_check(picture, words)
    r1 = teacher.check(picture, text)
    # arc-add's step lines are lesson-slots', already checked: only its back lines are its own to fix
    t1 = [c for c in r1["failures"] if whole or "(back)" in c["field"]]
    a1 = check_arc(picture, arc)
    if t1 or a1:
        again, _ = w.ask(Message().text(feedback(t1, a1, whole)), "feedback")
        if again:
            arc = again
    words = compose(picture, variant, arc)
    text = text_for_check(picture, words)
    r2 = teacher.check(picture, text)
    a2 = check_arc(picture, arc)
    gone_arc = take_out_arc(arc, a2)
    # a back line that check-text fails goes whole; any other failing sentence is taken out, as v4_teacher does
    for c in back_lines_gone(text, r2["failures"]):
        w = arc.get("steps", {}).get(c["id"])
        if isinstance(w, dict) and w.pop("back", None):  # counted once, and not if the arc's check took it out
            gone_arc.append({"where": f"step {c['id']}.back", "what": teacher.say(c), "sentence": c["sentence"]})
    words = compose(picture, variant, arc)
    text = text_for_check(picture, words)
    r3 = teacher.check(picture, text)
    gone_text = teacher.take_out(text, r3["failures"]) if whole else []
    r4 = teacher.check(picture, text)
    final = {t["stage_id"]: t["lines"] for t in text["steps"]}
    backs = sum(any(x["kind"] == "back" for x in v) for v in final.values())
    rec = {"first": first, "arc": {"opening": arc.get("opening"), "stages": arc.get("stages")},
           "final": final,
           "check": {"text_failures_first": len(t1), "arc_failures_first": len(a1),
                     "arc_failed_first": a1, "text_failed_first": [{"step": c["step"], "why": teacher.say(c)} for c in t1],
                     "text_failures_second": len([c for c in r2["failures"] if whole or "(back)" in c["field"]]),
                     "arc_failures_second": len(a2), "arc_taken_out": gone_arc, "text_taken_out": gone_text,
                     "left_failing": len(r4["failures"]) if whole else
                     len([c for c in r4["failures"] if "(back)" in c["field"]]),
                     "claims_final": len(r4["claims"])},
           "backs": backs,
           "words_count": sum(len(" ".join(x["text"] for x in v).split()) for v in final.values()),
           "arc_words": arc_words(arc)}
    update(lambda st: st["arc"].setdefault(variant, {}).__setitem__(picture, rec))
    print(f"{variant} {picture}: {len(t1)}+{len(a1)} failures first, {len(a2)} arc after feedback, "
          f"{len(gone_arc)} arc items and {len(gone_text)} sentences taken out, {backs} steps point back")


def arc_words(arc: dict) -> int:
    op = arc.get("opening") or {}
    txt = [op.get(k) or "" for k in ("welcome", "light", "road")] + [sk.get("how") or "" for sk in op.get("skills") or []]
    txt += [o.get(k) or "" for o in (arc.get("stages") or {}).values() for k in ("for", "end")]
    return len(" ".join(txt).split())


def write(args):
    pics = [args.picture] if args.picture else PICTURES
    have = state()["arc"].get(args.variant, {})
    todo = [p for p in pics if p not in have or args.again]
    with ThreadPoolExecutor(len(todo) or 1) as ex:
        for f in [ex.submit(write_one, args.variant, p) for p in todo]:
            f.result()


# ------------------------------------------------------------------------------------------------------- the page
def card_name(cid: str) -> str:
    import cards
    return (cards.strokes().get(cid) or {}).get("name") or cid


def opening_text(arc: dict) -> str:
    op = arc.get("opening") or {}
    out = []
    if op.get("welcome"):
        out += [op["welcome"], ""]
    if op.get("light"):
        out += [f"The light: {op['light']}", ""]
    out.append("What this painting teaches:")
    for sk in op.get("skills") or []:
        steps = ", ".join(str(n) for n in sk.get("steps") or [])
        out.append(f"- {card_name(sk['card'])} (steps {steps}): {sk.get('how', '')}")
    if op.get("road"):
        out += ["", f"The way there: {op['road']}"]
    return "\n".join(out)


def stage_text(stage: dict, o: dict, end: bool = True) -> str:
    out = f"This stage, {stage['name']}: {o.get('for', '')}"
    return (out + (f" By its end: {o.get('end', '')}" if end else "")).strip()


def intros(picture: str, arc: dict, end_on_last: bool = False) -> dict[int, str]:
    """Each step's stage opener, as the student reads it above the step. With `end_on_last`, the stage's end
    sentence is said only above its last step, where it is that step's own after picture."""
    out = {}
    for st in stages_of(picture):
        o = (arc.get("stages") or {}).get(st["id"]) or {}
        if o.get("for") or o.get("end"):
            for i, s in enumerate(st["steps"]):
                out[s["n"]] = stage_text(st, o, end=not end_on_last or i == len(st["steps"]) - 1)
    return out


NOEND = "arc-add-noend"  # arc-add's words, the stage's end sentence only above its last step (the rerun)


def packets(args):
    st = state()
    runs = [(v, v, v == "arc-add-long") for v in st["arc"]]  # the long run puts a stage's end on its last step
    runs += [("arc-add", NOEND, True)] if "arc-add" in st["arc"] else []
    for source, variant, end_on_last in runs:
        for pic, rec in st["arc"][source].items():
            les = json.loads(json.dumps(teacher.packet(pic)))
            intro = intros(pic, rec["arc"], end_on_last)
            for s in les["steps"]:
                s["lines"] = page_lines(rec["final"].get(s["id"]) or [])
                s["tip"] = ""
                s["intro"] = intro.get(s["n"], "")
            les["opening"] = opening_text(rec["arc"])
            les["not_last"] = [x["n"] for stg in stages_of(pic) for x in stg["steps"][:-1]]
            d = WORK / "words" / variant / pic
            d.mkdir(parents=True, exist_ok=True)
            (d / "packet.json").write_text(json.dumps(les, indent=1))
            print(d / "packet.json")


def show(args):
    """One lesson's opening and stage openers in full, and its back lines, for the write-up."""
    for variant in VARIANTS:
        rec = state()["arc"].get(variant, {}).get(args.picture)
        if not rec:
            continue
        print(f"## {variant}: {args.picture}\n\n{opening_text(rec['arc'])}\n")
        for st in stages_of(args.picture):
            o = (rec["arc"].get("stages") or {}).get(st["id"]) or {}
            print(f"- {stage_text(st, o)}")
        print()
        for s in teacher.packet(args.picture)["steps"]:
            for x in rec["final"].get(s["id"]) or []:
                if x["kind"] == "back":
                    print(f"- step {s['n']} ({s['name']}): As in step {x['step']}: {x['text']}")
        print()


def page(args):
    """A whole lesson as a painter reads it, with its arc and every step's picture, for the owner
    (`docs/spikes/v4-arc-<picture>.md`). A stage's end goes after its last step (the rerun's finding)."""
    pic, variant = args.picture, args.variant
    rec = state()["arc"][variant][pic]
    les, arc = teacher.packet(pic), rec["arc"]
    rel = f"../../spike/experiments/bench/v3-words/{pic}"
    out = [f"# The {pic.replace('-', ' ')}, with its arc (v4 spike #255, {variant})",
           "", "The whole lesson as a painter would read it: the opening, each stage's opener, and every step's words "
           "(the teacher spike's words, with the arc's \"As in step N\" lines added). Pictures are v3's. Back to the "
           "write-up: [v4-arc.md](v4-arc.md).", "", f"![The photo]({rel}/photo.jpg)", "",
           f"Canvas: {les['canvas_in'][0]:g} in wide, {les['canvas_in'][1]:g} in tall. {len(les['steps'])} steps.", ""]
    op = arc.get("opening") or {}
    out += ["## Before you start", ""]
    if op.get("welcome"):
        out += [op["welcome"], ""]
    if op.get("light"):
        out += [f"**The light:** {op['light']}", ""]
    out += ["**What this painting teaches:**", ""]
    out += [f"- **{card_name(sk['card'])}** (steps {', '.join(map(str, sk.get('steps') or []))}): {sk.get('how', '')}"
            for sk in op.get("skills") or []]
    if op.get("road"):
        out += ["", f"**The way there:** {op['road']}"]
    out.append("")
    by = {s["id"]: s for s in les["steps"]}
    for st in stages_of(pic):
        o = (arc.get("stages") or {}).get(st["id"]) or {}
        out += [f"## {st['name']}", "", f"*{o.get('for', '')}*", ""]
        for x in st["steps"]:
            s = by[x["id"]]
            out += [f"### Step {s['n']}: {s['name']}", "",
                    "**Paints:** " + "; ".join(f"{p['name']} ({p['recipe']})" for p in s.get("paints") or []), "",
                    f"**Brush:** {s.get('brushes')}", ""]
            for line in page_lines(rec["final"].get(s["id"]) or []):
                k, _, t = line.partition(": ")
                out.append(f"- **{k}:** {t}")
            out += ["", f"![After step {s['n']}]({rel}/steps/{s['n']:02d}.jpg)", ""]
        if o.get("end"):
            out += [f"*Where this stage ends:* {o['end']}", ""]
    path = ROOT / "docs" / "spikes" / f"v4-arc-{pic}.md"
    path.write_text("\n".join(out))
    print(path)


# ------------------------------------------------------------------------------------------------- the blind graders
def ab_one(variant: str, pic: str, g: int):
    """One blind grader (`bench/ab_grader.md`): lesson-slots' words against the variant's, the sides set by `g`.
    Each lesson's opening comes first, and each stage's opener with its first step."""
    from v4_loop import Message, call_claude, cost, last_json
    les = teacher.packet(pic)
    rec = state()["arc"][variant][pic]
    base = base_words(pic)
    sides = [BASE, variant] if (g + random.Random(f"{pic}-{SEED}").randrange(2)) % 2 else [variant, BASE]
    first_of = {st["steps"][0]["n"]: st for st in stages_of(pic) if st["steps"]}
    brief_text = (HERE / "bench" / "ab_grader.md").read_text().replace(
        "You were given a folder.", "You were given everything in this message, in place of a folder.")
    m = Message().text(f'<file name="ab_grader.md">\n{brief_text}\n</file>')
    m.text("The two lessons, A and B, have the same photo, finish and step pictures; each step's picture is shown "
           "once, with both lessons' words for it below. A lesson may open with a few lines before step 1, and a "
           "stage with a few lines before its first step; a lesson that has none says so.")
    m.picture(BENCH / pic / "photo.jpg", "photo.jpg", max_side=1024)
    m.picture(BENCH / pic / "finish.jpg", "finish.jpg", max_side=1024)
    opening = {side: (opening_text(rec["arc"]) if who == variant else "(no opening)") for side, who in zip("AB", sides)}
    m.text(f"Lesson A's opening:\n{opening['A']}\n\nLesson B's opening:\n{opening['B']}")
    for s in les["steps"]:
        words = {}
        for side, who in zip("AB", sides):
            lines = page_lines(rec["final"].get(s["id"]) or []) if who == variant else \
                teacher.page_lines("slots", base.get(s["id"]) or [])
            text = student.step_text(s, les["canvas_in"], len(les["steps"]), {"lines": lines, "tip": ""})
            if s["n"] in first_of:
                st = first_of[s["n"]]
                o = (rec["arc"].get("stages") or {}).get(st["id"]) or {}
                text = (stage_text(st, o) if who == variant else f"(no stage opener for {st['name']})") + "\n\n" + text
            words[side] = text
        m.text(f"Step {s['n']}. Its picture (the canvas after the step):")
        m.picture(BENCH / pic / "steps" / f"{s['n']:02d}.jpg", f"steps/{s['n']:02d}.jpg", max_side=640)
        m.text(f"Lesson A's words:\n{words['A']}\n\nLesson B's words:\n{words['B']}")
    m.text('Reply with grade.json as one ```json block (the brief\'s shape, `"picture": "' + pic + '"`), then the '
           "scores, the preference and how sure you are.")
    cwd = WORK / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    r = call_claude(m.blocks, "You have no tools. You grade one blind A/B pair, in the owner's place.", cwd=cwd)
    try:
        a = last_json(r["text"])
    except ValueError:
        a = {}
    prefer = a.get("prefer")
    out = {"variant": variant, "picture": pic, "grader": g, "A": sides[0], "B": sides[1], "prefer": prefer,
           "preferred": sides["AB".index(prefer)] if prefer in ("A", "B") else "none",
           "scores": {sides["AB".index(k)]: v for k, v in (a.get("scores") or {}).items() if k in ("A", "B")},
           "note": a.get("note", ""), "cost_usd": round(cost(r["usage"]), 5), "seconds": r["seconds"]}
    update(lambda st: st["ab"].append(out))
    print(f"ab {variant} {pic} g{g}: prefers {out['preferred']} ({prefer}), ${out['cost_usd']:.3f}")


def ab(args):
    done = {(r["variant"], r["picture"], r["grader"]) for r in state()["ab"]}
    jobs = [(args.variant, p, g) for p in PICTURES for g in (1, 2) if (args.variant, p, g) not in done]
    with ThreadPoolExecutor(6) as ex:
        for f in [ex.submit(ab_one, *j) for j in jobs]:
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                print(f"  failed: {e}", file=sys.stderr)


# ------------------------------------------------------------------------------------------------------------ report
def solo_grades(path: Path) -> dict:
    ss = json.loads(path.read_text()) if path.exists() else {}
    g = {}
    for r in ss.get("carry_grades", []):
        if r.get("solo") and r["condition"] == "words":
            g.setdefault((r["picture"], r["n"]), []).append(r["grade"])
    return {k: sum(v) / len(v) for k, v in g.items()}, ss


def report(args) -> dict:
    st = state()
    base, _ = solo_grades(BASE_STUDENT)
    out = {"base": {p: round(float(np.mean([v for (q, _), v in base.items() if q == p])), 2) for p in PICTURES},
           "variants": {}}
    for variant in VARIANTS + [NOEND]:
        source = "arc-add" if variant == NOEND else variant  # the rerun scores arc-add's words, its 40 steps not last
        if source not in st["arc"]:
            continue
        gs, ss = solo_grades(STUDENT_DIR / f"{variant}.json")
        calls = [c for c in st["calls"] if c["variant"] == variant]
        v = {"pictures": {}}
        diffs_all, split, with_back = [], [], []  # (the step is last in its stage / has a back line, its difference)
        for pic in PICTURES:
            rec = st["arc"][source].get(pic)
            if not rec:
                continue
            both = [k for k in gs if k[0] == pic and k in base]
            last = {stg["steps"][-1]["n"] for stg in stages_of(pic) if stg["steps"]}
            diffs = [gs[k] - base[k] for k in both]
            diffs_all += diffs
            split += [(k[1] in last, gs[k] - base[k]) for k in both]
            backs = {s["n"]: x for s in teacher.packet(pic)["steps"] for x in rec["final"].get(s["id"]) or []
                     if x["kind"] == "back"}
            back_diff = [gs[(pic, n)] - base[(pic, n)] for n in backs if (pic, n) in gs and (pic, n) in base]
            with_back += [(k[1] in backs, gs[k] - base[k]) for k in both]
            g = [x for (p, _), x in gs.items() if p == pic]
            v["pictures"][pic] = {
                "carry_grade": round(float(np.mean(g)), 2) if g else None, "graded": len(g),
                "vs_base": round(float(np.mean(diffs)), 2) if diffs else None,
                "rose": sum(d > 0 for d in diffs), "fell": sum(d < 0 for d in diffs),
                "backs": len(backs), "vs_base_on_back_steps": round(float(np.mean(back_diff)), 2) if back_diff else None,
                "check": rec["check"] | {"arc_failed_first": len(rec["check"]["arc_failed_first"]),
                                         "text_failed_first": len(rec["check"]["text_failed_first"]),
                                         "arc_taken_out": len(rec["check"]["arc_taken_out"]),
                                         "text_taken_out": len(rec["check"]["text_taken_out"])},
                "words": rec["words_count"], "arc_words": rec["arc_words"],
                "claude_usd": round(sum(c["cost_usd"] for c in calls if c["picture"] == pic), 3),
                "ab": [{k: r[k] for k in ("grader", "A", "B", "preferred", "note")}
                       for r in st["ab"] if r["variant"] == variant and r["picture"] == pic],
                "ab_scores": [r["scores"] for r in st["ab"] if r["variant"] == variant and r["picture"] == pic]}
        if diffs_all:
            v["vs_base_all"] = round(float(np.mean(diffs_all)), 3)
            v["vs_base_se"] = round(float(np.std(diffs_all, ddof=1) / np.sqrt(len(diffs_all))), 3)
        for name, pairs in (("last_in_stage", split), ("has_back_line", with_back)):
            v[f"vs_base_{name}"] = {str(flag): {"steps": len(d), "mean": round(float(np.mean(d)), 2)}
                                    for flag in (True, False) if (d := [x for f, x in pairs if f == flag])}
        v["claude_usd_a_lesson"] = round(sum(c["cost_usd"] for c in calls) / max(1, len(v["pictures"])), 3)
        v["calls"] = len(calls)
        v["renders_usd"] = round(sum(r["render_usd"] for r in ss.get("carry", [])), 3)
        out["variants"][variant] = v
    update(lambda s: s.__setitem__("report", out))
    print(json.dumps(out, indent=1))
    return out


def main(argv=None):
    global WORK
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=WORK)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("--variant", choices=VARIANTS, required=True)
    w.add_argument("--picture", choices=PICTURES)
    w.add_argument("--again", action="store_true")
    sub.add_parser("packets")
    a = sub.add_parser("ab")
    a.add_argument("--variant", choices=VARIANTS, required=True)
    sub.add_parser("report")
    pg = sub.add_parser("page")
    pg.add_argument("picture", choices=PICTURES)
    pg.add_argument("--variant", choices=VARIANTS, default="arc-add-long")
    s = sub.add_parser("show")
    s.add_argument("picture", choices=PICTURES)
    args = ap.parse_args(argv)
    WORK = args.work
    {"write": write, "packets": packets, "ab": ab, "report": report, "show": show, "page": page}[args.cmd](args)


if __name__ == "__main__":
    main()
