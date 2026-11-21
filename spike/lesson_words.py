"""The lesson's words, pipeline v3.1 (docs/design/pipeline-v3.1.md, sections 5 to 7; built in #276).

One writer, in a fresh context, writes every step of the lesson in the same six lines; the fact sheet checks them
and no longer writes them. In its one conversation the writer is sent back twice for its steps and once for the
arc, and answers each round with only what it changes:

    packet(lesson)            -> words/lesson/: what the writer reads (section 5, "What the writer is sent")
    steps_round(lesson, ...)  -> the steps' rounds: check-text, then the paint check and the long lines; --final
                                 takes out what still fails and writes text.json
    arc_round(lesson, ...)    -> the arc's round (its checks, check-text and the paint check on the back lines);
                                 --final writes the opening, the stage lines and the back lines into text.json

The writer's files, all in words/lesson/:

    out.json        its first words: {"steps": {"<step id>": {"first", "start", "strokes", "inside", "leave", "stop"}}}
    fix-1.json      its answer to round 1 (check-text's failures): only the steps it changes, in out.json's shape
    fix-2.json      its answer to round 2 (paints its step doesn't list, lines over 40 words), the same way
    arc.json        the arc: {"opening", "stages", "steps": {"<step id>": {"back": {"step", "text"}}}}
    arc-fix.json    its answer to the arc's round: the whole arc again (as #267's run asked for it)

The tools write `feedback.md` and `arc-feedback.md` (what to fix, and which file to write), `rounds.json` (each
round's counts), `words.md` (the checked step words, for the arc) and `arc-dropped.json`; `words/dropped.json` is
what the steps' last check took out, as in v3. `pictures.json` is what the step pictures the writer was sent were
made from (build.json's `made_from`, and whether it has `stops`: pipeline v4, section 8), and check-text --final
keeps it in rounds.json as what the words were written for, so words written for other pictures aren't sealed.

What was moved here from the experiments, and from where: the change picture and the lean fact sheet
(`v4_teacher.py`, `v4_writer_cost.py`), the paint check on the words (`v4_writer_cost.paint_failures`), the arc's
checks and how a back line sits among a step's lines (`v4_arc.py`). The experiments keep their own copies: they
are the record of the runs.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import numpy as np

import build_steps as bs
import facts
import publish2

ROOT = Path(__file__).resolve().parents[1]
BRIEFS = ROOT / ".claude" / "skills" / "paint-lesson" / "v3"
LESSON_BRIEF = BRIEFS / "lesson-brief.md"
ARC_BRIEF = BRIEFS / "arc-brief.md"
FOLDER = "lesson"  # <lesson>/words/lesson/
KINDS = [("first", "First"), ("start", "Start"), ("strokes", "Strokes"), ("inside", "Where the paint sits"),
         ("leave", "Leave"), ("stop", "Stop when")]
LABELS = dict(KINDS)
NEEDED = [k for k, _ in KINDS if k != "first"]  # `first` may be empty
LINE_WORDS = 40  # a line over this many words goes back in round 2 (and `check` holds it at the end)
PAIR_HALF = 512  # pixels: each half of a before-and-after picture (#267's `pics-small`)
CHANGE_SIDE = 512
PHOTO_SIDE = 768
BLANK = (246, 246, 246)  # the canvas before step 1
MASK_SIDE = 480  # where a step's change is found, as v4_teacher's change picture found it
CHANGE_DE = 5.0  # a pixel changed if its blurred color moved this far (CIE76; v4_student's)


class Refused(ValueError):
    pass


def folder_of(lesson: Path) -> Path:
    return Path(lesson) / facts.WORK / FOLDER


# ------------------------------------------------------------------- words belong to their pictures (v4, section 8)
PICTURES = "pictures.json"  # in words/lesson/: what the step pictures in the packet were made from
AGAIN = ("run packets, then the lesson's writer again on the new folder, and its rounds (check-text, then "
         "check-text --final and the arc; v3/run.md D)")


def pictures_of(lesson: Path) -> dict | None:
    """What the lesson's step pictures are made from now: build.json's `made_from` (the plan, the chain, the finish,
    and with the rule the canvas) and whether it was built with the rule. None before build-steps."""
    path = Path(lesson) / "v3" / "build.json"
    try:
        build = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {"made_from": build.get("made_from"), "stops": "stops" in build}


def packet_pictures(lesson: Path) -> dict | None:
    """What the step pictures in the writer's folder were made from, as packets recorded it; None for a folder made
    before the record (#298)."""
    try:
        got = json.loads((folder_of(lesson) / PICTURES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def other_pictures(was: dict | None, now: dict | None) -> str | None:
    """Why words written for the pictures `was` describes don't belong to the pictures `now` describes, or None
    when they do. `was` None is a record from before #298: those words were written for pictures without the rule,
    so they stand only while the lesson has none."""
    if now is None:
        return None  # no step pictures: lesson3.read's own refusal says so
    if was is None:
        return "the step pictures were built with --stops since" if now["stops"] else None
    if was.get("stops") != now["stops"]:
        return f"the step pictures were built {'with' if now['stops'] else 'without'} --stops since"
    if was.get("made_from") != now["made_from"]:
        return "the step pictures were made again from a changed plan, chain or canvas since"
    return None


def pictures_refusal(lesson: Path) -> str | None:
    """check-text's refusal of a writer's folder cut from other step pictures than the lesson's now."""
    why = other_pictures(packet_pictures(lesson), pictures_of(lesson))
    return f"the writer's folder was made for other step pictures ({why} packets ran): {AGAIN}" if why else None


def words_problem(lesson: Path, text: dict) -> str | None:
    """`check`'s: the lesson writer's words in text.json must be the ones check-text --final laid for the step
    pictures as they are now. None for words that aren't the writer's (drafted lines, a lesson before v3.1)."""
    if not is_written(text):
        return None
    final = _state(folder_of(lesson)).get("final")
    if final is None:
        return ("text.json holds the lesson writer's words, but words/lesson/ has no last check of them (packets made "
                f"the writer's folder again after they were written, or check-text --final hasn't run): {AGAIN}")
    why = other_pictures(final.get("pictures"), pictures_of(lesson))
    return f"text.json's words were written for other step pictures ({why} they were): {AGAIN}" if why else None


# ----------------------------------------------------------------------------------------- what the writer reads
def change_picture(before, after):
    """Only what the step changed: the after picture where its color moved, and the before picture washed pale
    everywhere else (v4_teacher.change_picture, with v4_student's change mask)."""
    import cv2
    from PIL import Image

    def lab(img):
        a = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
        k = MASK_SIDE / max(a.shape[:2])
        a = cv2.resize(a, (max(1, round(a.shape[1] * k)), max(1, round(a.shape[0] * k))), interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(cv2.GaussianBlur(a, (0, 0), 1.5), cv2.COLOR_RGB2LAB)

    m = (np.linalg.norm(lab(after) - lab(before), axis=2) > CHANGE_DE).astype(np.uint8)
    k3 = np.ones((3, 3), np.uint8)
    m = cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_OPEN, k3), cv2.MORPH_CLOSE, k3, iterations=2).astype(np.float32)
    k = cv2.resize(m, before.size, interpolation=cv2.INTER_LINEAR)
    k = np.clip(cv2.GaussianBlur(k, (0, 0), 1.5 * before.size[0] / 600), 0, 1)[..., None]
    b = np.asarray(before.convert("RGB"), dtype=np.float32)
    a = np.asarray(after.convert("RGB"), dtype=np.float32)
    pale = b * 0.3 + 255 * 0.7
    return Image.fromarray(np.clip(a * k + pale * (1 - k), 0, 255).astype(np.uint8))


def pair_picture(before, after, half: int = PAIR_HALF):
    """The canvas before the step (left) and after it (right), labeled, `half` pixels on each half's long side."""
    from PIL import Image, ImageDraw

    after = after.convert("RGB")
    k = half / max(after.size)
    size = (round(after.width * k), round(after.height * k))
    gap, label = 12, 24
    out = Image.new("RGB", (size[0] * 2 + gap, size[1] + label), (255, 255, 255))
    out.paste(before.convert("RGB").resize(size, Image.LANCZOS), (0, label))
    out.paste(after.resize(size, Image.LANCZOS), (size[0] + gap, label))
    d = ImageDraw.Draw(out)
    d.text((6, 5), "BEFORE (the step before)", fill=(0, 0, 0))
    d.text((size[0] + gap + 6, 5), "AFTER (this step)", fill=(0, 0, 0))
    return out


def card_text(ids: list[str]) -> str:
    """The stroke cards the steps use, as the writer reads them (v4_teacher.card_text)."""
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
                out.append(f"- {k}: {c[k] if isinstance(c[k], str) else json.dumps(c[k])}")
        for m in c.get("mistakes") or []:
            out.append(f"- mistake: {m if isinstance(m, str) else json.dumps(m)}")
        out.append("")
    return "\n".join(out)


def _lesson(lesson: Path, sheet_plan: tuple[dict, dict] | None = None) -> dict:
    """What the words' tools need of a lesson: the sheet, the plan in version 2's shape, the version 3 plan, and each
    step's number, name, part, paints (names), stroke and brush, in painting order. `sheet_plan` is the sheet and
    the plan when the caller has measured them already (`check`)."""
    import plan3

    sheet, plan = sheet_plan or facts.lesson_sheet(lesson)
    raw = plan3.load(lesson)
    names = publish2.paint_names(plan)
    by_v3 = {s["id"]: s for s in plan3.steps(raw)}
    rows = {st["id"]: st for st in sheet["steps"]}
    steps = []
    for s in bs.flat_steps(plan):
        st = rows[s["id"]]
        steps.append({"n": st["n"], "id": s["id"], "name": st["name"], "part": st["part_name"],
                      "paints": [names[c] for c in s.get("paints") or [] if c in names],
                      "stroke": (by_v3.get(s["id"]) or {}).get("stroke") or s.get("stroke"),
                      "brush": (by_v3.get(s["id"]) or {}).get("brush") or s.get("brush")})
    stages = []
    num = {s["id"]: s for s in steps}
    for stg in raw["stages"]:
        stages.append({"id": stg["id"], "name": stg.get("name") or stg["id"],
                       "steps": [num[s["id"]] for s in stg["steps"] if s["id"] in num]})
    return {"sheet": sheet, "plan": plan, "raw": raw, "steps": steps, "stages": stages,
            "paint_names": list(dict.fromkeys(names.values()))}


def headers(les: dict, mixes: dict, canvas: dict) -> str:
    """Each step's header as the page shows it above the words (name, part, paints with recipes, brush) and its
    stroke card (v4_teacher.headers)."""
    out = ["# The steps you write (their headers, as the page shows them)", ""]
    for s in les["steps"]:
        paints = []
        for p in s["paints"]:
            m = mixes.get(p) or {}
            recipe = m.get("text") or "no recipe"
            paints.append(f"{p} ({recipe}" + ("" if m.get("reachable", True) else
                                              "; these tubes can only come close to it") + ")")
        out.append(f"- step {s['n']} `{s['id']}`: {s['name']}. Part: {s['part']}. Paints: {'; '.join(paints)}. "
                   f"Brush: {s['brush']}. Stroke card: {s['stroke']}. "
                   f"Pictures: pair-{s['n']:02d}.jpg, change-{s['n']:02d}.jpg.")
    out += ["", f"The canvas is {canvas['w_in']:g} in wide and {canvas['h_in']:g} in tall, and the lesson has "
                f"{len(les['steps'])} steps."]
    return "\n".join(out)


def stages_md(les: dict) -> str:
    out = ["# The lesson's stages", "", "The canvas at the end of a stage is the after half (right) of its last "
           "step's pair.", ""]
    for k, stg in enumerate(les["stages"], 1):
        ns = [s["n"] for s in stg["steps"]]
        out.append(f"- stage {k} `{stg['id']}`: {stg['name']}. Steps {', '.join(map(str, ns))}. Its end: "
                   f"pair-{ns[-1]:02d}.jpg." if ns else f"- stage {k} `{stg['id']}`: {stg['name']}. No steps.")
    return "\n".join(out) + "\n"


def packet(lesson: Path) -> dict:
    """words/sheet.json, and words/lesson/ for the lesson's one writer. Throws away v3's stage folders, the old
    words, their checks and the arc: they were written for the packet before this one."""
    from PIL import Image

    lesson = Path(lesson)
    les = _lesson(lesson)
    mixes_path = lesson / "mixes.json"
    if not mixes_path.exists():
        raise Refused(f"no mixes.json in {lesson}: run mix (the headers show each paint's recipe)")
    mixes = json.loads(mixes_path.read_text(encoding="utf-8"))
    work = lesson / facts.WORK
    work.mkdir(parents=True, exist_ok=True)
    (work / "sheet.json").write_text(json.dumps(les["sheet"], indent=1), encoding="utf-8")
    for old in work.glob("stage-[0-9][0-9]"):  # v3's one writer a stage
        if old.is_dir():
            shutil.rmtree(old)
    (work / "dropped.json").unlink(missing_ok=True)
    folder = folder_of(lesson)
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir()
    box, canvas = facts.canvas_of(lesson, (1, 1))
    pics = {s["id"]: lesson / f"{i + 1:02d}_{s['id']}.png" for i, s in enumerate(bs.flat_steps(les["plan"]))}
    before = None
    for s in les["steps"]:
        after = facts._crop(Image.open(pics[s["id"]]), box).convert("RGB")
        b = before if before is not None else Image.new("RGB", after.size, BLANK)
        pair_picture(b, after).save(folder / f"pair-{s['n']:02d}.jpg", quality=88)
        ch = change_picture(b, after)
        ch.thumbnail((CHANGE_SIDE, CHANGE_SIDE))
        ch.save(folder / f"change-{s['n']:02d}.jpg", quality=88)
        before = after
    photo = next((lesson / n for n in facts.PHOTOS if (lesson / n).exists()), None)
    for src, dst in ((photo, "photo.jpg"), (lesson / "99_finish.png", "finish.jpg")):
        if src is not None and src.exists():
            img = facts._crop(Image.open(src), box).convert("RGB")
            img.thumbnail((PHOTO_SIDE, PHOTO_SIDE))
            img.save(folder / dst, quality=88)
    stage_of = {s["id"]: k for k, stg in enumerate(les["stages"], 1) for s in stg["steps"]}
    fact_rows, k_now = [], None
    for st in les["sheet"]["steps"]:
        k = stage_of.get(st["id"])
        if k != k_now:
            fact_rows += [f"# Stage {k}: {les['stages'][k - 1]['name']}", ""]
            k_now = k
        fact_rows += [facts.facts_text(les["sheet"], les["plan"], st), ""]
    (folder / "facts.md").write_text(facts.lean(("\n".join(fact_rows)).rstrip() + "\n"), encoding="utf-8")
    (folder / "steps.md").write_text(headers(les, mixes, canvas) + "\n", encoding="utf-8")
    cards_used = list(dict.fromkeys(s["stroke"] for s in les["steps"] if s["stroke"]))
    (folder / "cards.md").write_text(card_text(cards_used), encoding="utf-8")
    (folder / "stages.md").write_text(stages_md(les), encoding="utf-8")
    shutil.copyfile(lesson / "plan.json", folder / "plan.json")
    shutil.copyfile(LESSON_BRIEF, folder / "brief.md")
    shutil.copyfile(ARC_BRIEF, folder / "arc-brief.md")
    (folder / PICTURES).write_text(json.dumps(pictures_of(lesson)) + "\n", encoding="utf-8")
    return {"folder": str(folder), "steps": len(les["steps"]), "stages": len(les["stages"]),
            "sheet": str(work / "sheet.json")}


# ------------------------------------------------------------------------------------------------ the writer's words
def _read(path: Path) -> tuple[object, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except ValueError as e:
        return None, f"{path.name} isn't valid JSON ({e})"


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else None


def fixes(folder: Path) -> list[Path]:
    """The writer's answers to the steps' rounds, in order."""
    got = [p for p in folder.glob("fix-*.json") if re.fullmatch(r"fix-\d+\.json", p.name)]
    return sorted(got, key=lambda p: int(p.stem[4:]))


def words_of(folder: Path, ids: list[str]) -> tuple[dict, list[str]]:
    """out.json with every fix-N.json laid on it: {step id: {kind: text, "paint_notes": [...]}}, and what couldn't be
    used. A file is read as it comes: anything not in the brief's shape is reported, never raised."""
    words, bad = {}, []
    for path in [folder / "out.json", *fixes(folder)]:
        if not path.exists():
            continue
        got, err = _read(path)
        if err:
            bad.append(err)
            continue
        steps = got.get("steps") if isinstance(got, dict) else None
        if not isinstance(steps, dict):
            bad.append(f"{path.name} must be {{\"steps\": {{\"<step id>\": {{\"start\": ..., ...}}}}}}")
            continue
        for sid, w in steps.items():
            if sid not in ids:
                bad.append(f"{path.name}: no step {sid} in this lesson")
                continue
            if not isinstance(w, dict):
                bad.append(f"{path.name}: {sid}'s entry must be an object")
                continue
            entry = words.setdefault(sid, {})
            for key, v in w.items():
                if key in LABELS:
                    if isinstance(v, str):
                        entry[key] = v.strip()
                    else:
                        bad.append(f"{path.name}: {sid}'s {key} must be text")
                elif key == "paint_notes":
                    if isinstance(v, list) and all(isinstance(x, str) for x in v):
                        entry[key] = [x.strip() for x in v if x.strip()]
                    else:
                        bad.append(f"{path.name}: {sid}'s paint_notes must be a list of sentences")
                elif key != "back":
                    bad.append(f"{path.name}: {sid} has `{key}`, which isn't one of the lines ({', '.join(LABELS)})")
    return words, bad


def lines_of(w: dict) -> list[dict]:
    """A writer's entry for one step as text.json lines, in the six lines' order."""
    return [{"kind": k, "text": w[k], "edited": True} for k, _ in KINDS if (w.get(k) or "").strip()]


def lay(lesson: Path, words: dict, redraft) -> dict:
    """text.json with the writer's lines as each step's words: draft-text runs again (each step's header: its
    brushes, mixes, receipt), then a step's lines are the writer's six, and nothing else. No summary, no tip, no
    arc. Returns the text."""
    path = Path(lesson) / "text.json"
    text = json.loads(path.read_text(encoding="utf-8"))
    for k in ("opening", "stages"):
        text.pop(k, None)
    for t in text.get("steps") or []:
        for k in ("summary", "tip", "paint_notes"):
            t.pop(k, None)
        t["lines"] = []
    path.write_text(json.dumps(text, indent=1) + "\n", encoding="utf-8")
    redraft()  # the drafted lines, which are only the header's now: they're replaced below
    text = json.loads(path.read_text(encoding="utf-8"))
    for t in text["steps"]:
        w = words.get(t["stage_id"]) or {}
        t["lines"] = lines_of(w)
        if w.get("paint_notes"):
            t["paint_notes"] = list(w["paint_notes"])
    return text


def save_text(lesson: Path, text: dict) -> None:
    (Path(lesson) / "text.json").write_text(json.dumps(text, indent=1) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------------------------------- the checks
def text_failures(sheet: dict, text: dict) -> list[dict]:
    """check-text's checker, strict, on every line the writer wrote."""
    return facts._writers(text, facts.check_text(sheet, text, strict=True)["failures"])


def paint_failures(les: dict, text: dict, back_only: bool = False) -> list[dict]:
    """v3 check's `isn't one of its paints` (tools.paints_not_listed) a sentence at a time: a sentence that names a
    paint its step doesn't list, so the page shows no recipe for it there (#270)."""
    from tools import paints_not_listed

    listed = {s["id"]: set(s["paints"]) for s in les["steps"]}
    num = {s["id"]: s["n"] for s in les["steps"]}
    out = []
    for t in text["steps"]:
        mine = listed.get(t["stage_id"], set())
        colors = [{"name": n} for n in mine]
        for k, ln in enumerate(t.get("lines") or [], 1):
            if back_only and ln.get("kind") != "back":
                continue
            for sent in facts.sentences(ln.get("text") or ""):
                for x in paints_not_listed([{"id": t["stage_id"], "colors": colors, "steps": [sent]}],
                                           les["paint_names"]):
                    out.append({"step": num.get(t["stage_id"]), "id": t["stage_id"],
                                "field": f"line {k} ({ln.get('kind')})", "sentence": sent, "paint": x["paint"],
                                "listed": sorted(mine)})
    return out


def say_paint(c: dict) -> str:
    return (f"step {c['step']} ({c['id']}), {c['field']}, names {c['paint']}, which isn't one of its paints "
            f"({', '.join(c['listed']) or 'it lists none'}), so the page shows no recipe for it there")


def long_lines(les: dict, text: dict) -> list[dict]:
    num = {s["id"]: s["n"] for s in les["steps"]}
    return [{"step": num.get(t["stage_id"]), "id": t["stage_id"], "kind": x["kind"], "words": len(x["text"].split())}
            for t in text["steps"] for x in t.get("lines") or [] if len(x["text"].split()) > LINE_WORDS]


def unwritten(les: dict, words: dict) -> list[str]:
    """Steps the writer gave no words, or not every line it must write."""
    out = []
    for s in les["steps"]:
        w = words.get(s["id"])
        if not w:
            out.append(f"step {s['n']} ({s['id']}) has no words")
            continue
        gone = [k for k in NEEDED if not (w.get(k) or "").strip()]
        if gone:
            out.append(f"step {s['n']} ({s['id']}) has no {', '.join(f'`{k}`' for k in gone)} line")
    return out


CHANGES_ONLY = ("Write `{file}` in your folder with only the steps you change, in out.json's shape "
                "(`{{\"steps\": {{\"<step id>\": {{every line of that step}}}}}}`). A step you leave out keeps its "
                "words. Then reply with one line.")


def feedback_round1(fails: list[dict]) -> str:
    items = [f"- {facts.say(c)}\n  in: \"{c['sentence']}\"" for c in fails]
    return ("# The checker's failures in your words (round 1)\n\nFix each one: use the fact the sheet gives, or say it "
            "without a number or a side. A sentence that still fails after the next round is taken out.\n\n"
            + "\n".join(items) + "\n\n" + CHANGES_ONLY.format(file="fix-1.json") + "\n")


def feedback_round2(paints: list[dict], long: list[dict]) -> str:
    out = ["# Paints a step doesn't list, and lines that are too long (round 2)", ""]
    if paints:
        out += ["Fix each one: if you meant one of the step's own paints, name that one; if you meant paint already "
                "on the canvas, say it without the paint's name (\"the gray from step 5\"). A sentence that still "
                "names a paint its step doesn't list is taken out.", ""]
        out += [f"- {say_paint(c)}\n  in: \"{c['sentence']}\"" for c in paints]
        out.append("")
    if long:
        out += [f"Every line is under {LINE_WORDS} words. Shorten each of these, keeping what it says that matters "
                "most to the painter:", ""]
        out += [f"- step {c['step']} ({c['id']}): its `{c['kind']}` line is {c['words']} words" for c in long]
        out.append("")
    return "\n".join(out) + "\n" + CHANGES_ONLY.format(file="fix-2.json") + "\n"


def take_out(text: dict, fails: list[dict], paints: list[dict]) -> list[dict]:
    """Every sentence that still fails either check, taken out of its line (never reworded: a listed paint the
    writer didn't mean would have the painter load the wrong color). Returns what went."""
    by_id = {t["stage_id"]: t for t in text["steps"]}
    gone, done = [], set()
    todo = [(c, f, s, facts.say(c)) for c in fails for f, s in facts._parts(c)]
    todo += [(c, c["field"], c["sentence"], say_paint(c)) for c in paints]
    for c, field, sent, why in todo:
        t = by_id[c["id"]]
        if (c["id"], field, sent) in done or not facts._owned(t, field):
            continue
        done.add((c["id"], field, sent))
        if facts._take_out(t, field, sent):
            gone.append({"step": c["step"], "id": c["id"], "field": field, "sentence": sent, "why": why})
    return gone


def emptied(text: dict) -> list[dict]:
    """The lines a take-out left empty, taken off the step (each is a known problem for review.json)."""
    out = []
    for t in text["steps"]:
        for x in t.get("lines") or []:
            if not (x.get("text") or "").strip():
                out.append({"id": t["stage_id"], "kind": x.get("kind")})
        t["lines"] = [x for x in t.get("lines") or [] if (x.get("text") or "").strip()]
        if t.get("paint_notes"):
            t["paint_notes"] = [x for x in t["paint_notes"] if x.strip()]
    return out


def words_md(les: dict, text: dict) -> str:
    """Every step's words as the painter reads them: what the arc's writer is sent (`v4_arc.words_md`)."""
    by = {t["stage_id"]: t for t in text["steps"]}
    out = ["# Every step's words, as the painter reads them (after the checks)", ""]
    for s in les["steps"]:
        out.append(f"## Step {s['n']} `{s['id']}`: {s['name']}")
        out += [f"- {LABELS.get(x['kind'], x['kind'])}: {x['text']}" for x in (by.get(s["id"]) or {}).get("lines") or []]
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------- the rounds' record
def _state(folder: Path) -> dict:
    p = folder / "rounds.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError:
        return {}


def _save_state(folder: Path, st: dict) -> None:
    (folder / "rounds.json").write_text(json.dumps(st, indent=1) + "\n", encoding="utf-8")


def _pending(folder: Path, rounds: list[dict]) -> dict | None:
    return next((r for r in rounds if r.get("answer") and not (folder / r["answer"]).exists()), None)


def steps_round(lesson: Path, redraft, final: bool = False) -> dict:
    """The steps' rounds (design section 5). Run without `final` after the writer writes out.json, and again after
    each answer: round 1 sends back check-text's failures (answer: fix-1.json); round 2 the sentences that name a
    paint their step doesn't list and the lines over 40 words (fix-2.json). A round with nothing to send back is
    passed by. `final` takes out every sentence that still fails either check and writes words/dropped.json."""
    lesson = Path(lesson)
    folder = folder_of(lesson)
    work = lesson / facts.WORK
    if not folder.is_dir():
        raise Refused(f"no lesson writer's folder in {lesson}: run packets")
    wrong = pictures_refusal(lesson)
    if wrong:
        raise Refused(wrong)
    les = _lesson(lesson)
    kept = work / "sheet.json"
    if not kept.exists() or json.loads(kept.read_text(encoding="utf-8")) != json.loads(json.dumps(les["sheet"])):
        raise Refused("the step pictures changed since the writer's packet was made: run packets again, and the "
                      "writer again")
    out_path = folder / "out.json"
    problems, said = [], []
    if not out_path.exists():
        return {"problems": ["the lesson's writer wrote no out.json in words/lesson/"], "ok": False,
                "round": None, "send_back": None, "rounds": []}
    st = _state(folder)
    if st.get("out") != _sha(out_path):  # a new out.json: its rounds start again
        for p in [*fixes(folder), folder / "feedback.md"]:
            p.unlink(missing_ok=True)
        st = {"out": _sha(out_path), "rounds": []}
        said.append("out.json is new: its rounds start from round 1")
    ids = [s["id"] for s in les["steps"]]
    words, bad = words_of(folder, ids)
    problems += bad + unwritten(les, words)
    text = lay(lesson, words, redraft)
    sheet = les["sheet"]
    rounds = st["rounds"]
    send = None
    if not final:
        (work / "dropped.json").unlink(missing_ok=True)  # the words are laid again: a last check no longer stands
        (folder / "feedback.md").unlink(missing_ok=True)
        waiting = _pending(folder, rounds)
        if waiting:
            send = waiting["answer"]
            (folder / "feedback.md").write_text(waiting["feedback"], encoding="utf-8")
        if not waiting and not rounds:
            fails = text_failures(sheet, text)
            r = {"n": 1, "kind": "check-text", "sent": len(fails), "claims": len(facts.check_text(
                sheet, text, strict=True)["claims"])}
            if fails:
                r.update(answer="fix-1.json", feedback=feedback_round1(fails))
            rounds.append(r)
        if not _pending(folder, rounds) and len(rounds) == 1:
            paints, long = paint_failures(les, text), long_lines(les, text)
            r = {"n": 2, "kind": "paints and long lines", "sent": len(paints) + len(long), "paints": len(paints),
                 "long_lines": len(long), "check_text_left": len(text_failures(sheet, text))}
            if paints or long:
                r.update(answer="fix-2.json", feedback=feedback_round2(paints, long))
            rounds.append(r)
        waiting = _pending(folder, rounds)
        if waiting:
            send = waiting["answer"]
            (folder / "feedback.md").write_text(waiting["feedback"], encoding="utf-8")
        _save_state(folder, st)
        save_text(lesson, text)
        done = not waiting and len(rounds) == 2
        if send:
            problems.append(f"send the writer back once: it reads feedback.md in words/lesson/ and writes {send}")
        return {"problems": problems, "ok": not problems, "round": waiting["n"] if waiting else None,
                "send_back": send, "done": done, "said": said,
                "rounds": [{k: v for k, v in r.items() if k != "feedback"} for r in rounds],
                "advice": ("Send the writer back with: \"Read feedback.md in your folder and write " + send + ".\" "
                           "Then run check-text again." if send else
                           "The rounds are done: run check-text --final." if done else "")}
    # final: what still fails either check is taken out
    if _pending(folder, rounds) or len(rounds) < 2:
        problems.append("the rounds aren't done: run check-text (without --final) and send the writer back as it "
                        "says, until it says they are done")
    fails, paints = text_failures(sheet, text), paint_failures(les, text)
    gone = take_out(text, fails, paints)
    empty = emptied(text)
    left = len(text_failures(sheet, text)) + len(paint_failures(les, text))
    (work / "dropped.json").write_text(json.dumps(gone, indent=1), encoding="utf-8")
    save_text(lesson, text)
    (folder / "words.md").write_text(words_md(les, text), encoding="utf-8")
    arc_note = ("the arc was laid on the words before this: run check-text --arc --final again"
                if (folder / "arc.json").exists() else "")
    st["final"] = {"dropped": len(gone), "emptied": empty, "long_lines": len(long_lines(les, text)),
                   "pictures": pictures_of(lesson)}  # what these words were written for (#298)
    _save_state(folder, st)
    return {"problems": problems, "ok": not problems, "dropped": len(gone), "left_failing": left,
            "emptied": empty, "long_lines": long_lines(les, text), "words": sum(
                len(x["text"].split()) for t in text["steps"] for x in t["lines"]),
            "rounds": [{k: v for k, v in r.items() if k != "feedback"} for r in rounds],
            "advice": "Taken out: words/dropped.json. " + (arc_note or "Next, the arc: send the same writer "
                      "\"Follow arc-brief.md in your folder and write arc.json.\", then run check-text --arc.")}


# ---------------------------------------------------------------------------------------------------------- the arc
NUMBER_RE = re.compile(r"\d")
SIDE_RE = re.compile(r"\b(leftmost|rightmost|topmost|bottommost|left|right|top|bottom|upper|lower|above|below)\b", re.I)
MORE_SIDES = re.compile(r"\b(under|underneath|beneath|beside|besides?)\b|\b(one|two|three|four|five|six|seven|eight|"
                        r"nine|ten|half|quarter)\s+(inch|inches)\b", re.I)


def has_claim(sentence: str) -> bool:
    """A number or a side word: what the opening and a stage's lines mustn't say (the sheet measures steps)."""
    return bool(NUMBER_RE.search(sentence) or SIDE_RE.search(sentence) or MORE_SIDES.search(sentence))


def check_arc(les: dict, arc: dict) -> list[dict]:
    """The arc's own failures (v4_arc.check_arc): {where, what, sentence?}. `where` is `opening.<field>`,
    `opening.skill N`, `stage <id>.for|end` or `step <id>.back`."""
    by_n = {s["n"]: s for s in les["steps"]}
    num = {s["id"]: s["n"] for s in les["steps"]}
    used = {s["stroke"] for s in les["steps"] if s["stroke"]}
    out = []
    if not isinstance(arc, dict):
        return [{"where": "arc.json", "what": "must be {\"opening\": ..., \"stages\": ..., \"steps\": ...}"}]

    def claims(where, text):
        for sent in facts.sentences(text if isinstance(text, str) else ""):
            if has_claim(sent):
                out.append({"where": where, "what": "the opening and a stage's lines say no number and no side word",
                            "sentence": sent})

    op = arc.get("opening") if isinstance(arc.get("opening"), dict) else {}
    skills = [sk for sk in op.get("skills") or [] if isinstance(sk, dict)]
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
    for k in ("welcome", "light", "road"):
        if not (op.get(k) or "").strip():
            out.append({"where": f"opening.{k}", "what": "missing"})
        claims(f"opening.{k}", op.get(k) or "")
    stages = arc.get("stages") if isinstance(arc.get("stages"), dict) else {}
    for stg in les["stages"]:
        o = stages.get(stg["id"]) if isinstance(stages.get(stg["id"]), dict) else {}
        for k in ("for", "end"):
            if not (o.get(k) or "").strip():
                out.append({"where": f"stage {stg['id']}.{k}", "what": "missing"})
            claims(f"stage {stg['id']}.{k}", o.get(k) or "")
    for sid, w in (arc.get("steps") or {}).items() if isinstance(arc.get("steps"), dict) else []:
        b = w.get("back") if isinstance(w, dict) else None
        if not b:
            continue
        if sid not in num:
            out.append({"where": f"step {sid}.back", "what": f"there is no step {sid}"})
            continue
        if not isinstance(b, dict) or not isinstance(b.get("step"), int) or not str(b.get("text") or "").strip():
            out.append({"where": f"step {sid}.back", "what": "a back line is {\"step\": <an earlier step's number>, "
                                                             "\"text\": \"...\"}"})
            continue
        here, there = by_n[num[sid]], by_n.get(b["step"])
        if there is None or there["n"] >= here["n"]:
            out.append({"where": f"step {sid}.back", "what": f"step {b['step']} isn't an earlier step"})
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


def with_back(lines: list[dict], back: dict | None) -> list[dict]:
    """A step's lines with its back line just before its strokes (after `first` and `start`; v4_arc.step_lines)."""
    lines = [x for x in lines if x.get("kind") != "back"]
    if not back:
        return lines
    line = {"kind": "back", "step": back["step"], "text": back["text"], "edited": True}
    for i, x in enumerate(lines):
        if x["kind"] not in ("first", "start"):
            return lines[:i] + [line] + lines[i:]
    return lines + [line]


def compose(text: dict, arc: dict) -> dict:
    """text.json's steps with the arc's back lines put in (a copy)."""
    steps = arc.get("steps") if isinstance(arc, dict) and isinstance(arc.get("steps"), dict) else {}
    out = json.loads(json.dumps(text))
    for t in out["steps"]:
        t["lines"] = with_back(t.get("lines") or [], back_of(steps.get(t["stage_id"])))
    return out


def arc_failures(les: dict, text: dict, arc: dict) -> tuple[list[dict], list[dict]]:
    """(the arc's own failures with the back lines' paint failures in its shape, check-text's failures on back
    lines)."""
    t = compose(text, arc)
    back = [c for c in text_failures(les["sheet"], t) if "(back)" in c["field"]]
    own = check_arc(les, arc)
    own += [{"where": f"step {c['id']}.back", "what": say_paint(c) + ": name one of its own paints, or say it "
             "without the paint's name", "sentence": c["sentence"]} for c in paint_failures(les, t, back_only=True)]
    return own, back


def arc_feedback(own: list[dict], back: list[dict]) -> str:
    items = [f"- {facts.say(c)}\n  in: \"{c['sentence']}\"" for c in back]
    items += [f"- {c['where']}: {c['what']}" + (f"\n  in: \"{c['sentence']}\"" if c.get("sentence") else "")
              for c in own]
    return ("# The checker's failures in the arc\n\nFix each one: use the fact the sheet gives, or say it without a "
            "number or a side. What still fails is taken out.\n\n" + "\n".join(items) + "\n\nWrite `arc-fix.json` in "
            "your folder: the whole arc again (the opening, the stage lines and the back lines), in arc.json's shape. "
            "Then reply with one line.\n")


def take_out_arc(arc: dict, fails: list[dict]) -> list[dict]:
    """Every arc failure still there, taken out: a sentence that says a number or side, a skill whose card or steps
    are wrong, or a back line whole (v4_arc.take_out_arc)."""
    gone = []
    if not isinstance(arc.get("opening"), dict):
        arc["opening"] = {}
    op = arc["opening"]
    skills = op.get("skills") if isinstance(op.get("skills"), list) else []
    drop = set()

    def cut(text, sentence):
        return " ".join(x for x in facts.sentences(text or "") if x.strip() != sentence.strip())

    for c in fails:
        w = c["where"]
        if w.startswith("step ") and w.endswith(".back"):
            x = (arc.get("steps") or {}).get(w[5:-5])
            if isinstance(x, dict) and x.pop("back", None) is not None:
                gone.append(c)
        elif w.startswith("opening.skill "):
            i = int(w.split()[-1]) - 1
            if c.get("sentence") and i < len(skills):
                skills[i]["how"] = cut(skills[i].get("how"), c["sentence"])
            else:
                drop.add(i)
            gone.append(c)
        elif c.get("sentence") and w.startswith("opening."):
            k = w.split(".", 1)[1]
            op[k] = cut(op.get(k), c["sentence"])
            gone.append(c)
        elif c.get("sentence") and w.startswith("stage "):
            sid, k = w[6:].rsplit(".", 1)
            o = (arc.get("stages") or {}).get(sid)
            if isinstance(o, dict):
                o[k] = cut(o.get(k), c["sentence"])
                gone.append(c)
    if drop:
        op["skills"] = [sk for i, sk in enumerate(skills) if i not in drop]
    return gone


def arc_words(arc: dict) -> int:
    op = arc.get("opening") or {}
    txt = [op.get(k) or "" for k in ("welcome", "light", "road")] + [sk.get("how") or "" for sk in op.get("skills") or []]
    txt += [o.get(k) or "" for o in (arc.get("stages") or {}).values() if isinstance(o, dict) for k in ("for", "end")]
    return len(" ".join(txt).split())


def arc_round(lesson: Path, final: bool = False) -> dict:
    """The arc's round (design section 6). After `steps_round(final=True)`: the writer writes arc.json; this checks
    it and, once, sends back what fails (answer: arc-fix.json, the whole arc again). `final` takes out what still
    fails and writes the arc into text.json: each back line among its step's lines, `opening`, and `stages`."""
    lesson = Path(lesson)
    folder = folder_of(lesson)
    work = lesson / facts.WORK
    if not folder.is_dir() or not (work / "dropped.json").exists():
        raise Refused("the steps' words haven't had their last check: run check-text --final before the arc")
    wrong = pictures_refusal(lesson) or words_problem(lesson, json.loads((lesson / "text.json").read_text(
        encoding="utf-8")))
    if wrong:
        raise Refused(wrong)
    les = _lesson(lesson)
    path = lesson / "text.json"
    text = json.loads(path.read_text(encoding="utf-8"))
    for k in ("opening", "stages"):
        text.pop(k, None)
    for t in text["steps"]:
        t["lines"] = [x for x in t.get("lines") or [] if x.get("kind") != "back"]
    arc_path = folder / "arc.json"
    if not arc_path.exists():
        return {"problems": ["the writer wrote no arc.json in words/lesson/"], "ok": False, "send_back": None}
    st = _state(folder)
    a = st.get("arc") or {}
    said = []
    if a.get("sha") != _sha(arc_path):
        for p in (folder / "arc-fix.json", folder / "arc-feedback.md"):
            p.unlink(missing_ok=True)
        a = {"sha": _sha(arc_path)}
        said.append("arc.json is new: its round starts again")
    source = folder / "arc-fix.json" if (folder / "arc-fix.json").exists() else arc_path
    arc, err = _read(source)
    problems = [err] if err else []
    arc = arc if isinstance(arc, dict) else {}
    own, back = arc_failures(les, text, arc)
    if not final:
        send = None
        if "sent" not in a:
            a["sent"] = len(own) + len(back)
            a["first"] = {"arc": len(own), "back_check_text": len(back)}
            if own or back:
                a["answer"], a["feedback"] = "arc-fix.json", arc_feedback(own, back)
        if a.get("answer") and not (folder / a["answer"]).exists():
            send = a["answer"]
            (folder / "arc-feedback.md").write_text(a["feedback"], encoding="utf-8")
            problems.append("send the writer back once: it reads arc-feedback.md in words/lesson/ and writes "
                            "arc-fix.json")
        st["arc"] = a
        _save_state(folder, st)
        return {"problems": problems, "ok": not problems, "send_back": send, "said": said,
                "first": a.get("first"), "failing_now": len(own) + len(back),
                "advice": ("Send the writer back with: \"Read arc-feedback.md in your folder and write "
                           "arc-fix.json.\" Then run check-text --arc --final." if send else
                           "Run check-text --arc --final.")}
    if "sent" not in a or (a.get("answer") and not (folder / a["answer"]).exists()):
        problems.append("the arc's round isn't done: run check-text --arc (without --final) and send the writer back "
                        "as it says")
    gone = take_out_arc(arc, own)
    for c in back:  # a back line check-text fails goes whole
        x = (arc.get("steps") or {}).get(c["id"])
        if isinstance(x, dict) and x.pop("back", None) is not None:
            gone.append({"where": f"step {c['id']}.back", "what": facts.say(c), "sentence": c["sentence"]})
    own2, back2 = arc_failures(les, text, arc)
    text = compose(text, arc)
    op = arc.get("opening") if isinstance(arc.get("opening"), dict) else {}
    text["opening"] = {k: op[k] for k in ("welcome", "light", "skills", "road") if op.get(k)}
    stages = arc.get("stages") if isinstance(arc.get("stages"), dict) else {}
    text["stages"] = {s["id"]: {k: stages[s["id"]][k] for k in ("for", "end")
                                if isinstance(stages.get(s["id"]), dict) and (stages[s["id"]].get(k) or "").strip()}
                      for s in les["stages"]}
    save_text(lesson, text)
    (folder / "arc-dropped.json").write_text(json.dumps(gone, indent=1), encoding="utf-8")
    a["final"] = {"taken_out": len(gone)}
    st["arc"] = a
    _save_state(folder, st)
    backs = sum(any(x["kind"] == "back" for x in t["lines"]) for t in text["steps"])
    return {"problems": problems, "ok": not problems, "taken_out": len(gone), "left_failing": len(own2) + len(back2),
            "back_lines": backs, "arc_words": arc_words(arc), "first": a.get("first"),
            "advice": "The arc is in text.json (arc-dropped.json: what was taken out). Then run check."}


# ------------------------------------------------------------------------------------------ what `check` holds (#277)
def arc_of(text: dict) -> dict:
    """The arc as text.json holds it after check-text --arc --final, in arc.json's shape."""
    steps = {}
    for t in text.get("steps") or []:
        b = next((x for x in t.get("lines") or [] if x.get("kind") == "back"), None)
        if b:
            steps[t["stage_id"]] = {"back": {"step": b.get("step"), "text": b.get("text", "")}}
    return {"opening": text.get("opening") or {}, "stages": text.get("stages") or {}, "steps": steps}


def is_written(text: dict) -> bool:
    """Whether a lesson's words are the lesson writer's (v3.1): a step's lines are the six, not drafted ones."""
    import draft_text

    return any(draft_text.written(t.get("lines")) for t in text.get("steps") or [])


def taken(lesson: Path) -> tuple[set, set]:
    """What the last checks took out and so may be missing: ({(step id, line kind)} emptied by check-text --final,
    {an arc place}, from words/lesson/rounds.json and arc-dropped.json)."""
    folder = folder_of(Path(lesson))
    st = _state(folder)
    lines = {(x.get("id"), x.get("kind")) for x in ((st.get("final") or {}).get("emptied") or [])}
    try:
        arc = json.loads((folder / "arc-dropped.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        arc = []
    places = {x.get("where") for x in arc if isinstance(x, dict)}
    return lines, places


def arc_problems(lesson: Path, text: dict, sheet_plan: tuple[dict, dict]) -> list[str]:
    """The arc's checks on the arc as text.json holds it (design section 7), so an arc changed after its round can't
    be sealed. A part the arc's last check took out (arc-dropped.json) may be missing; what is there must pass."""
    if not is_written(text):
        return []  # a lesson made before v3.1 has no arc
    if not text.get("opening"):
        return ["text.json has no opening: the arc hasn't been written in. Run check-text --arc, then check-text "
                "--arc --final (v3/run.md D4)."]
    les = _lesson(Path(lesson), sheet_plan)
    _, gone = taken(lesson)
    out = []
    for c in check_arc(les, arc_of(text)):
        missing = c["what"] == "missing" or c["where"] == "opening.skills"
        if missing and (c["where"] in gone or (c["where"] == "opening.skills" and any(
                str(g).startswith("opening.skill") for g in gone))):
            continue  # taken out by the arc's last check, and said so in arc-dropped.json
        said = f" in: \"{c['sentence']}\"" if c.get("sentence") else ""
        out.append(f"the arc's {c['where']}: {c['what']}{said}. Run check-text --arc and send the writer back, then "
                   "check-text --arc --final.")
    return out
