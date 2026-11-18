"""Spike for #254 (v4, W1): a teacher writes the step, and the fact sheet checks it.

On the frozen bench (`spike/experiments/bench/v3-words/`), on v3's own pictures, so only the words differ. A writer
(one fresh Claude conversation through `v4_loop.call_claude`: `claude -p`, Opus, no tools) gets each step's before
and after pictures, a picture of only what the step changed, the fact sheet, the stroke card and the whole plan, and
writes each step whole, as a person teaching it would. `check-text`'s checker (`facts.check_text`, strict, as v3's
`merge` runs it) then holds every number and side to the sheet: its failures go back to the writer once, and a
sentence that still fails is taken out, the way v3 takes one out.

Four variants, two by two:

- **who**: `stage` (one writer a stage, as v3) or `lesson` (one writer for the whole lesson);
- **form**: `free` (a few short paragraphs, in the order a teacher would say them) or `slots` (a fixed set of
  labelled lines: First, Start, Strokes, Where the paint sits, Leave, Stop when).

    .venv/bin/python spike/experiments/v4_teacher.py pictures
    .venv/bin/python spike/experiments/v4_teacher.py write --variant stage-free [--picture P]
    .venv/bin/python spike/experiments/v4_teacher.py packets
    .venv/bin/python spike/experiments/v4_teacher.py ab --variant stage-free
    .venv/bin/python spike/experiments/v4_teacher.py report

`packets` writes each variant's words as a bench packet (`<work>/words/<variant>/<picture>/packet.json`), which the
student test reads with `v4_student.py --words-from <work>/words/<variant> --results
spike/experiments/v4_teacher/<variant>.json`. `ab` runs the blind graders (`bench/ab_grader.md`), a variant's
words against v3's, two graders a picture with the sides swapped.

The words, the checker's findings and every call's tokens go in `spike/experiments/v4_teacher.json`; pictures go in
a work folder outside the repository (`--work`, by default `<temp>/gesso-v4-teacher`). Experiment code: it reads
the frozen bench and changes no tool.
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

BENCH = HERE / "bench" / "v3-words"
PICTURES = student.PICTURES
RESULTS = HERE / "v4_teacher.json"
STUDENT_DIR = HERE / "v4_teacher"  # the student test's answers for each variant
WORK = Path(tempfile.gettempdir()) / "gesso-v4-teacher"
VARIANTS = ["stage-free", "stage-slots", "lesson-free", "lesson-slots"]
SLOTS = [("first", "First"), ("start", "Start"), ("strokes", "Strokes"), ("inside", "Where the paint sits"),
         ("leave", "Leave"), ("stop", "Stop when")]
PAIR_SIDE = 784  # each half of a before-and-after picture
SEED = 254
LOCK = threading.Lock()


# ------------------------------------------------------------------------------------------------------- the bench
def data(picture: str) -> Path:
    return BENCH / picture / "data"


def plan(picture: str) -> dict:
    return json.loads((data(picture) / "plan.json").read_text())


def sheet(picture: str) -> dict:
    return json.loads((data(picture) / "words" / "sheet.json").read_text())


def stages(picture: str) -> list[Path]:
    return sorted((data(picture) / "words").glob("stage-[0-9][0-9]"))


def stage_steps(folder: Path) -> list[dict]:
    return json.loads((folder / "steps.json").read_text())["steps"]


def packet(picture: str) -> dict:
    return student.lesson(picture)


# ----------------------------------------------------------------------------------------------------- the pictures
def change_picture(before, after):
    """Only what the step changed: the after picture where it changed (v4_student's change mask, the student test's
    own), and the before picture washed pale everywhere else."""
    from PIL import Image
    m = student.change_mask(before, after, side=480)
    b = np.asarray(before, dtype=np.float32)
    a = np.asarray(after, dtype=np.float32)
    pale = b * 0.3 + 255 * 0.7
    k = student.soft(m, before.size, feather=1.5)
    return Image.fromarray(np.clip(a * k + pale * (1 - k), 0, 255).astype(np.uint8))


def pictures(args):
    """For every step: `pair-NN.jpg` (before, left; after, right) and `change-NN.jpg`."""
    from PIL import Image
    for pic in PICTURES:
        d = WORK / "pictures" / pic
        d.mkdir(parents=True, exist_ok=True)
        for s in packet(pic)["steps"]:
            n = s["n"]
            before, after = student.before_after(pic, n)
            k = PAIR_SIDE / max(after.size)
            size = (round(after.width * k), round(after.height * k))
            pair = Image.new("RGB", (size[0] * 2 + 12, size[1]), "white")
            pair.paste(before.resize(size, Image.LANCZOS), (0, 0))
            pair.paste(after.resize(size, Image.LANCZOS), (size[0] + 12, 0))
            pair.save(d / f"pair-{n:02d}.jpg", quality=88)
            change_picture(before, after).resize(size, Image.LANCZOS).save(d / f"change-{n:02d}.jpg", quality=88)
        print(pic, len(packet(pic)["steps"]), "steps")


# --------------------------------------------------------------------------------------------------------- the brief
BRIEF = """# Brief: teach each step of a beginner acrylic lesson (Gesso, a v4 spike)

You are a painting teacher. The lesson's pictures are made and stay as they are: for every step there is the canvas
before it and after it. You write what the painter is told at each step, so that a beginner who has the canvas as it
was before the step, your words and the step's paints and brush gets to the canvas after it.

The painter is a beginner with acrylics, a white canvas, the photo, and this lesson on a phone. The page shows each
step's name, its paints (with their mixing recipes) and its brush above your words, so don't repeat the recipes.
The step's own picture is shown too, but write so that the step can be done without looking at it: the painter
compares with it when they are done.

## What you are sent

- `plan.json`: the whole lesson's plan: the things in the painting, the light, and every stage and step with what
  it lays (`lays`), what the canvas shows after it (`after`) and why. Written before the pictures were made: where a
  picture and the plan disagree, write to the picture.
- `facts.md`: what was measured on each step's picture: its area, the paint it adds, its marks, where its paint
  crosses the part's middle row and column, what it sits next to, and what is under it. Sizes and distances in
  inches.
- `cards.md`: the stroke card each step uses: how the stroke is done (load, motion, result, what comes after, and the
  usual mistakes). The cards are checked against painting research.
- For every step: `pair-NN.jpg` (the canvas before the step on the left, after it on the right) and `change-NN.jpg`
  (only what the step changed, at full colour; everything else is washed pale). Look at every one.
- `photo.jpg` and `finish.jpg`: what the painter wants to paint, and the finished painting.

## What a step says

Write each step whole, as you would say it standing beside a beginner at the easel:

- **where to start**: where the first strokes go, named by the thing and its parts (the top of the cat's back, the
  sky's upper left corner, the foot of the nearest trunk);
- **which way to pull**: the direction and path of the strokes on this thing;
- **where the paint sits inside the thing, and why**: which parts of it get this paint and which don't (the shadow
  under the belly where it meets the blanket, because the light comes from the upper left);
- **what to leave showing**: the earlier paint or bare canvas that has to stay;
- **what it looks like when you stop**: how much of the thing is covered, and how it should read.

Use `change-NN.jpg` for all of it. Your words must cover everything the step changed, and no more: if the change
covers the whole cat, don't send the painter to a patch, and if it is three thin lines, don't say "shade the side".

Say also, when it applies: what has to be dry before the step starts (a step painted over or beside paint that is
still wet), and a mistake a beginner is likely to make here.

## Technique

How a stroke is done is the card's, and you don't change it: no other stroke, tool, medium or load than the step's
card and brush give. You may put the card in this subject's own terms ("pull each curved stroke down the cat's
back, from the spine toward the belly"), and say where on this thing it goes. Name only the paints the step lists,
by their names as given.

## The rules for numbers and sides

Every number, side and position you write is checked by a tool against `facts.md`, and a claim that isn't there
fails. A sentence that still fails after one round of the tool's feedback is taken out.

- **Use only numbers and sides that are on the sheet.** Say a length in the ruler value given first ("2 3/4 in"),
  never the decimal in brackets. One or two numbers a step, where they place the thing, are plenty: a teacher
  points at the thing more than they measure it.
- **Say what each number measures**, in the sheet's words: "its top is about 1/2 in from the top edge", "about
  3 in wide", "its middle is about 8 in from the left edge". A bare "about 3 in" is a fault.
- **Say what a side is of.** "Right of the hull", "on the right side of the balloon", "at the right edge (of the
  canvas)". Not "on the right", "below it", "the shape above".
- **Name parts by the sheet's names** ("the balloon", "the rolling fields"), and an earlier step's marks by their
  paint ("the Deep balloon red stripe"), so the tool can find what you mean.
- **"Most of it on the left side"** means at least half of what the step adds is in that half (the sheet's halves).
- **A place inside a thing that the sheet doesn't measure** (a crease, the belly, the shadow side of a trunk) can be
  named in the subject's own words. The tool checks a side word (left, right, top, bottom, above, below, under,
  beside) against the sheet, and fails one whose reference isn't a part on the sheet: say such a place by what it
  is ("where the belly meets the blanket", "the crease between the haunch and the body") rather than with a side
  word pointing at it.
- No percentages, ever.

{form}

## What to write

Every step you were given gets an entry. Reply with one ```json block, then one line: anything in the pictures your
words couldn't square.
"""

FORM = {
    "free": """## The form: free prose

Each step is two to five short paragraphs (one to three sentences each), in the order you would say them, under
about 130 words in all. Plain words a beginner knows.

```json
{"steps": {"<step id>": {"words": ["first paragraph", "second paragraph", "..."]}}}
```""",
    "slots": """## The form: a fixed set of lines

Each step fills the same lines, one to three sentences each, under about 130 words in all. Plain words a beginner
knows. `first` (what has to be dry, or rinsed, before you start) may be left empty when nothing does; every other
line is always written.

- `first`: what has to be dry first;
- `start`: where the first strokes go;
- `strokes`: which way to pull, and how, in this thing's terms;
- `inside`: where the paint sits inside the thing, and why;
- `leave`: what to leave showing;
- `stop`: what it looks like when you stop.

```json
{"steps": {"<step id>": {"first": "", "start": "...", "strokes": "...", "inside": "...", "leave": "...", "stop": "..."}}}
```""",
}


def brief(form: str) -> str:
    return BRIEF.replace("{form}", FORM[form])


def card_text(ids: list[str]) -> str:
    import cards
    known = cards.strokes()
    out = ["# The stroke cards these steps use", ""]
    for cid in ids:
        c = known.get(cid)
        if not c:
            out += [f"## {cid}", "(no card)", ""]
            continue
        out.append(f"## {c['id']}: {c.get('name', '')}")
        for k in ("load", "motion", "result", "then"):
            if c.get(k):
                v = c[k] if isinstance(c[k], str) else json.dumps(c[k])
                out.append(f"- {k}: {v}")
        for m in c.get("mistakes") or []:
            out.append(f"- mistake: {m if isinstance(m, str) else json.dumps(m)}")
        out.append("")
    return "\n".join(out)


def headers(picture: str, ids: set[str]) -> str:
    """Each step as the page shows it above the words: name, part, paints with recipes, brush, stroke card."""
    by_id = {}
    for f in stages(picture):
        for s in stage_steps(f):
            by_id[s["id"]] = s
    out = ["# The steps you write (their headers, as the page shows them)", ""]
    for s in packet(picture)["steps"]:
        if s["id"] not in ids:
            continue
        paints = "; ".join(f"{p['name']} ({p['recipe']})" for p in s.get("paints") or [])
        out.append(f"- step {s['n']} `{s['id']}`: {s['name']}. Part: {s.get('group')}. Paints: {paints}. "
                   f"Brush: {s.get('brushes')}. Stroke card: {by_id.get(s['id'], {}).get('stroke')}. "
                   f"Pictures: pair-{s['n']:02d}.jpg, change-{s['n']:02d}.jpg.")
    les = packet(picture)
    out += ["", f"The canvas is {les['canvas_in'][0]:g} in wide and {les['canvas_in'][1]:g} in tall, and the lesson "
                f"has {len(les['steps'])} steps."]
    return "\n".join(out)


def writer_message(picture: str, form: str, folders: list[Path]):
    """Everything one writer reads, in one message (the loop's shape: files in tags, pictures by name)."""
    from v4_loop import Message
    ids, card_ids, nums = set(), [], []
    for f in folders:
        for s in stage_steps(f):
            ids.add(s["id"])
            nums.append(s["n"])
            if s.get("stroke") and s["stroke"] not in card_ids:
                card_ids.append(s["stroke"])
    facts = "\n\n".join((f / "facts.md").read_text() for f in folders)
    m = Message().text("Follow the brief. Everything you need is in this message.")
    m.text(f'<file name="brief.md">\n{brief(form)}\n</file>')
    m.text(f'<file name="steps.md">\n{headers(picture, ids)}\n</file>')
    m.file(data(picture) / "plan.json", "plan.json")
    m.text(f'<file name="facts.md">\n{facts}\n</file>')
    m.text(f'<file name="cards.md">\n{card_text(card_ids)}\n</file>')
    d = WORK / "pictures" / picture
    for n in nums:
        m.picture(d / f"pair-{n:02d}.jpg", f"pair-{n:02d}.jpg")
        m.picture(d / f"change-{n:02d}.jpg", f"change-{n:02d}.jpg")
    m.picture(BENCH / picture / "photo.jpg", "photo.jpg", max_side=1024)
    m.picture(BENCH / picture / "finish.jpg", "finish.jpg", max_side=1024)
    m.text("Reply with the JSON as one ```json block, then your one line.")
    return m


# ---------------------------------------------------------------------------------------------- the results file
def state() -> dict:
    st = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    st.setdefault("words", {})
    st.setdefault("calls", [])
    st.setdefault("ab", [])
    return st


def update(fn):
    """Change the results file under a lock: `fn(state)`, then write it."""
    import fcntl
    with LOCK:
        WORK.mkdir(parents=True, exist_ok=True)
        with open(WORK / "results.lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            st = state()
            fn(st)
            tmp = RESULTS.with_suffix(".json.tmp")  # written whole, then moved: a full disk can't cut the file short
            tmp.write_text(json.dumps(st, indent=1) + "\n")
            tmp.replace(RESULTS)


class Writer:
    """One writer: a conversation with Claude, every call logged in `calls`."""
    SYSTEM = ("You have no tools. Everything you would read is in this message: files in <file> tags, pictures "
              "labelled by name. A program runs the checks for you and sends back what they find. You are the "
              "painting teacher who writes a Gesso lesson's steps.")

    def __init__(self, variant: str, picture: str, name: str):
        self.variant, self.picture, self.name = variant, picture, name
        self.session = None

    def ask(self, m, label: str):
        from v4_loop import call_claude, cost, last_json
        cwd = WORK / "cwd"
        cwd.mkdir(parents=True, exist_ok=True)
        r = call_claude(m.blocks, self.SYSTEM, session=self.session, cwd=cwd)
        self.session = r["session"]
        u = r["usage"]
        rec = {"variant": self.variant, "picture": self.picture, "writer": self.name, "label": label,
               "seconds": r["seconds"], "input_tokens": u.get("input_tokens", 0),
               "cache_write_tokens": u.get("cache_creation_input_tokens", 0),
               "cache_read_tokens": u.get("cache_read_input_tokens", 0), "output_tokens": u.get("output_tokens", 0),
               "cost_usd": round(cost(u), 5), "pictures": m.pictures, "picture_tokens": m.picture_tokens,
               "text_chars": m.text_chars}
        update(lambda st: st["calls"].append(rec))
        print(f"  [{self.variant} {self.picture} {self.name}] {label}: ${rec['cost_usd']:.3f}, {r['seconds']} s",
              file=sys.stderr)
        try:
            return last_json(r["text"]), r["text"]
        except ValueError:
            from v4_loop import Message
            again = Message().text("Your reply had no JSON I could read. Send the same answer again as one ```json "
                                   "block, and nothing else.")
            return self.ask(again, label + " (JSON again)")


# ------------------------------------------------------------------------------------------------- words and checks
def lines_of(form: str, w: dict) -> list[dict]:
    """A writer's entry for one step as text.json lines ({kind, text})."""
    if not isinstance(w, dict):
        return []
    if form == "free":
        return [{"kind": "teacher", "text": str(x).strip()} for x in w.get("words") or [] if str(x).strip()]
    out = []
    for key, _label in SLOTS:
        v = str(w.get(key) or "").strip()
        if v:
            out.append({"kind": key, "text": v})
    return out


def page_lines(form: str, lines: list[dict]) -> list[str]:
    """The lines as the page (and the student) reads them: a slot's label in front of its text."""
    labels = dict(SLOTS)
    return [x["text"] if form == "free" else f"{labels[x['kind']]}: {x['text']}" for x in lines if x["text"].strip()]


def text_of(picture: str, form: str, words: dict) -> dict:
    """The writers' words as a text.json for `facts.check_text`: every step's lines, no summary or tip."""
    return {"steps": [{"stage_id": s["id"], "summary": "", "tip": "", "lines": lines_of(form, words.get(s["id"]))}
                      for s in packet(picture)["steps"]]}


def check(picture: str, text: dict) -> dict:
    """check-text's checker, strict, as v3's merge runs it."""
    from facts import check_text
    return check_text(sheet(picture), text, strict=True)


def say(c: dict) -> str:
    from facts import say as fsay
    return fsay(c)


def feedback(failures: list[dict]) -> str:
    lines = [f"- {say(c)}\n  in: \"{c['sentence']}\"" for c in failures]
    return ("# The checker's failures in your words\n\nFix each one (write the whole JSON again, every step): use the "
            "fact the sheet gives, or say it without a number or a side. A sentence that still fails is taken out.\n\n"
            + "\n".join(lines) + "\n")


def take_out(text: dict, failures: list[dict]) -> list[dict]:
    """Every sentence that still fails, taken out of its line, as v3's `--final` does. Returns what went."""
    from facts import sentences
    by_id = {t["stage_id"]: t for t in text["steps"]}
    gone, seen = [], set()
    for c in failures:
        t = by_id[c["id"]]
        for field, sent in zip(c["field"].split(" and "), c["sentence"].split(" / ")):
            m = re.match(r"line (\d+)", field)
            if not m or (c["id"], field, sent) in seen:
                continue
            seen.add((c["id"], field, sent))
            ln = t["lines"][int(m.group(1)) - 1]
            kept = [x for x in sentences(ln["text"]) if x.strip() != sent.strip()]
            if len(kept) < len(sentences(ln["text"])):
                ln["text"] = " ".join(kept)
                gone.append({"step": c["step"], "id": c["id"], "field": field, "sentence": sent, "why": say(c)})
    for t in text["steps"]:
        t["lines"] = [x for x in t["lines"] if x["text"].strip()]
    return gone


def kinds(failures: list[dict]) -> dict:
    """The failures sorted by what went wrong: a reference the sheet can't find, or a number or side the sheet
    contradicts."""
    out = {}
    for c in failures:
        k = "no such thing on the sheet" if c.get("ok") is None else f"wrong {c['kind']}"
        out[k] = out.get(k, 0) + 1
    return out


def write_one(variant: str, picture: str):
    who, form = variant.split("-")
    groups = [[f] for f in stages(picture)] if who == "stage" else [stages(picture)]
    writers = [Writer(variant, picture, g[0].name if who == "stage" else "lesson") for g in groups]
    words: dict = {}

    def first(i):
        a, _ = writers[i].ask(writer_message(picture, form, groups[i]), "first words")
        return i, (a or {}).get("steps") or {}

    with ThreadPoolExecutor(len(groups)) as ex:
        got = dict(ex.map(first, range(len(groups))))
    owner = {}
    for i, g in got.items():
        mine = {s["id"] for f in groups[i] for s in stage_steps(f)}
        for sid, w in g.items():
            if sid in mine:
                words[sid] = w
                owner[sid] = i
    first_words = json.loads(json.dumps(words))
    text = text_of(picture, form, words)
    r1 = check(picture, text)
    fails1 = r1["failures"]

    def again(i):
        mine = [c for c in fails1 if owner.get(c["id"]) == i]
        if not mine:
            return i, None
        from v4_loop import Message
        a, _ = writers[i].ask(Message().text(feedback(mine)), "feedback")
        return i, (a or {}).get("steps") or {}

    with ThreadPoolExecutor(len(groups)) as ex:
        for i, g in ex.map(again, range(len(groups))):
            if g:
                mine = {s["id"] for f in groups[i] for s in stage_steps(f)}
                words.update({sid: w for sid, w in g.items() if sid in mine})
    text = text_of(picture, form, words)
    r2 = check(picture, text)
    gone = take_out(text, r2["failures"])
    r3 = check(picture, text)
    missing = [s["id"] for s in packet(picture)["steps"] if not lines_of(form, words.get(s["id"]) or {})]
    rec = {"first": first_words, "second": words, "final": {t["stage_id"]: t["lines"] for t in text["steps"]},
           "missing": missing,
           "check": {"claims_first": len(r1["claims"]), "failures_first": len(fails1), "kinds_first": kinds(fails1),
                     "failed_first": [{"step": c["step"], "words": c["words"], "why": say(c)} for c in fails1],
                     "claims_second": len(r2["claims"]), "failures_second": len(r2["failures"]),
                     "kinds_second": kinds(r2["failures"]), "taken_out": gone,
                     "left_failing": len(r3["failures"]), "claims_final": len(r3["claims"])},
           "words_count": sum(len(" ".join(x["text"] for x in t["lines"]).split()) for t in text["steps"])}
    update(lambda st: st["words"].setdefault(variant, {}).__setitem__(picture, rec))
    print(f"{variant} {picture}: {len(words)} steps, {len(fails1)} failures first, {len(r2['failures'])} after "
          f"feedback, {len(gone)} sentences taken out, missing {missing}")


def write(args):
    pics = [args.picture] if args.picture else PICTURES
    have = state()["words"].get(args.variant, {})
    todo = [p for p in pics if p not in have or args.again]
    with ThreadPoolExecutor(len(todo) or 1) as ex:
        for f in [ex.submit(write_one, args.variant, p) for p in todo]:
            f.result()


def packets(args):
    """Each variant's words as a bench packet, for the student test (`v4_student.py --words-from`)."""
    st = state()
    for variant, pics in st["words"].items():
        form = variant.split("-")[1]
        for pic, rec in pics.items():
            les = json.loads(json.dumps(packet(pic)))
            for s in les["steps"]:
                s["lines"] = page_lines(form, rec["final"].get(s["id"]) or [])
                s["tip"] = ""
            d = WORK / "words" / variant / pic
            d.mkdir(parents=True, exist_ok=True)
            (d / "packet.json").write_text(json.dumps(les, indent=1))
            print(d / "packet.json")


# ------------------------------------------------------------------------------------------------- the blind graders
def ab_one(variant: str, pic: str, g: int):
    """One blind grader: the owner's rubric (`bench/ab_grader.md`) on two lessons, v3's words and the variant's, in
    the order A/B that `g` sets. The two lessons share every picture, so each step's picture goes in once with both
    lessons' words under it."""
    from v4_loop import Message
    les = packet(pic)
    form = variant.split("-")[1]
    rec = state()["words"][variant][pic]
    sides = ["v3", variant] if (g + random.Random(f"{pic}-{SEED}").randrange(2)) % 2 else [variant, "v3"]
    brief_text = (HERE / "bench" / "ab_grader.md").read_text()
    brief_text = brief_text.replace("You were given a folder.", "You were given everything in this message, in place of a folder.")
    m = Message().text(f'<file name="ab_grader.md">\n{brief_text}\n</file>')
    m.text("The two lessons, A and B, have the same photo, finish and step pictures; each step's picture is shown "
           "once, with both lessons' words for it below.")
    m.picture(BENCH / pic / "photo.jpg", "photo.jpg", max_side=1024)
    m.picture(BENCH / pic / "finish.jpg", "finish.jpg", max_side=1024)
    for s in les["steps"]:
        words = {}
        for side, who in zip("AB", sides):
            w = None if who == "v3" else {"lines": page_lines(form, rec["final"].get(s["id"]) or []), "tip": ""}
            words[side] = student.step_text(s, les["canvas_in"], len(les["steps"]), w)
        m.text(f"Step {s['n']}. Its picture (the canvas after the step):")
        m.picture(BENCH / pic / "steps" / f"{s['n']:02d}.jpg", f"steps/{s['n']:02d}.jpg", max_side=640)
        m.text(f"Lesson A's words:\n{words['A']}\n\nLesson B's words:\n{words['B']}")
    m.text('Reply with grade.json as one ```json block (the brief\'s shape, `"picture": "' + pic + '"`), then the '
           "scores, the preference and how sure you are.")
    from v4_loop import call_claude, cost, last_json
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
V3_GRADE = {"highland-cow": 3.15, "sleeping-cat": 3.21, "birch-grove": 3.03}  # docs/spikes/v4-student-test.md
V3_FAULTS = ["highland-cow 2", "sleeping-cat 2", "birch-grove 10", "birch-grove 20"]
V3_WRITERS_USD = 1.42  # the cat's stage writers in the loop's baseline (docs/spikes/v4-loop-baseline.md)


def student_state(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def report(args) -> dict:
    st = state()
    base = student_state(HERE / "v4_student.json")
    header = {(r["picture"], r["n"]): r["p_real"] for r in base.get("pick", []) if r["condition"] == "header"}
    v3_pick = {}
    for r in base.get("pick", []):
        if r["condition"] == "words" and r["rep"] == 1:
            v3_pick[(r["picture"], r["n"])] = r["p_real"]
    v3_beats = {}
    for r in base.get("carry", []):
        if r["condition"] == "words" and r["rep"] == 1:
            v3_beats[(r["picture"], r["n"])] = r["beats"]
    v3_grades = {}
    for r in base.get("carry_grades", []):
        if r.get("solo") and r["condition"] == "words":
            v3_grades.setdefault((r["picture"], r["n"]), []).append(r["grade"])
    v3_grade_step = {k: sum(v) / len(v) for k, v in v3_grades.items()}
    v3_dropped = {p: len(json.loads((data(p) / "words" / "dropped.json").read_text())) for p in PICTURES}
    v3_words = {p: sum(len(" ".join(s["lines"] + [s.get("tip") or ""]).split()) for s in packet(p)["steps"])
                for p in PICTURES}
    out = {"v3": {"carry_grade": V3_GRADE, "taken_out": v3_dropped, "words": v3_words,
                  "pick": {p: round(float(np.mean([v for (q, _), v in v3_pick.items() if q == p])), 3) for p in PICTURES}},
           "variants": {}}
    for variant in VARIANTS:
        if variant not in st["words"]:
            continue
        v = {"pictures": {}}
        ss = student_state(STUDENT_DIR / f"{variant}.json")
        grades = {}
        for r in ss.get("carry_grades", []):
            if r.get("solo") and r["condition"] == "words":
                grades.setdefault((r["picture"], r["n"]), []).append(r["grade"])
        gstep = {k: sum(x) / len(x) for k, x in grades.items()}
        beats = {(r["picture"], r["n"]): r["beats"] for r in ss.get("carry", []) if r["condition"] == "words"}
        pk = {(r["picture"], r["n"]): r["p_real"] for r in ss.get("pick", []) if r["condition"] == "words"}
        calls = [c for c in st["calls"] if c["variant"] == variant]
        for pic in PICTURES:
            rec = st["words"][variant].get(pic)
            if not rec:
                continue
            ck = rec["check"]
            mine = lambda d: [x for (p, _), x in d.items() if p == pic]  # noqa: E731
            g = mine(gstep)
            both = [k for k in gstep if k[0] == pic and k in v3_grade_step]
            faults = sorted(f"{pic} {n}" for (p, n), x in pk.items() if p == pic and (p, n) in header
                            and x - header[(p, n)] <= -0.25)
            pv = {"steps_written": len(rec["final"]) - len(rec["missing"]), "words": rec["words_count"],
                  "check": {k: ck[k] for k in ("claims_first", "failures_first", "kinds_first", "failures_second",
                                               "kinds_second", "left_failing", "claims_final")},
                  "taken_out": len(ck["taken_out"]),
                  "carry_grade": round(float(np.mean(g)), 2) if g else None, "graded": len(g),
                  "carry_grade_vs_v3": round(float(np.mean([gstep[k] - v3_grade_step[k] for k in both])), 2) if both else None,
                  "steps_rose": sum(gstep[k] > v3_grade_step[k] for k in both),
                  "steps_fell": sum(gstep[k] < v3_grade_step[k] for k in both),
                  "carry_beats": round(float(np.mean(mine(beats))), 3) if mine(beats) else None,
                  "pick": round(float(np.mean(mine(pk))), 3) if mine(pk) else None,
                  "word_faults": faults,
                  "v3_faults_fixed": [f for f in V3_FAULTS if f.startswith(pic) and (pic, int(f.split()[1])) in pk
                                      and f not in faults],
                  "claude_usd": round(sum(c["cost_usd"] for c in calls if c["picture"] == pic), 3),
                  "ab": [{k: r[k] for k in ("grader", "A", "B", "preferred", "note")}
                         for r in st["ab"] if r["variant"] == variant and r["picture"] == pic]}
            v["pictures"][pic] = pv
        v["claude_usd_a_lesson"] = round(sum(c["cost_usd"] for c in calls) / max(1, len(v["pictures"])), 3)
        v["calls"] = len(calls)
        v["renders_usd"] = round(sum(r["render_usd"] for r in ss.get("carry", [])), 3)
        out["variants"][variant] = v
    update(lambda s: s.__setitem__("report", out))
    print(json.dumps(out, indent=1))
    return out


def compare(args):
    """One step in v3's words and each variant's, for the write-up."""
    st = state()
    s = student.step_of(args.picture, args.step)
    print(f"## {args.picture} step {args.step}: {s['name']}\n\n### v3\n")
    print("\n".join(f"{i}. {x}" for i, x in enumerate(s["lines"], 1)) + (f"\nTip: {s['tip']}" if s.get("tip") else ""))
    for variant in VARIANTS:
        rec = st["words"].get(variant, {}).get(args.picture)
        if rec:
            form = variant.split("-")[1]
            print(f"\n### {variant}\n")
            print("\n".join(f"{i}. {x}" for i, x in enumerate(page_lines(form, rec["final"].get(s["id"]) or []), 1)))


def main(argv=None):
    global WORK
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=WORK)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pictures")
    w = sub.add_parser("write")
    w.add_argument("--variant", choices=VARIANTS, required=True)
    w.add_argument("--picture", choices=PICTURES)
    w.add_argument("--again", action="store_true", help="write a picture's words again even if they exist")
    sub.add_parser("packets")
    a = sub.add_parser("ab")
    a.add_argument("--variant", choices=VARIANTS, required=True)
    sub.add_parser("report")
    c = sub.add_parser("compare")
    c.add_argument("picture", choices=PICTURES)
    c.add_argument("step", type=int)
    args = ap.parse_args(argv)
    WORK = args.work
    {"pictures": pictures, "write": write, "packets": packets, "ab": ab, "report": report,
     "compare": compare}[args.cmd](args)


if __name__ == "__main__":
    main()
