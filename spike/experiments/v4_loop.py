"""Spike for #241 (v4, measure): one v3 lesson made by a program, with Claude's tokens measured per call.

The program follows `.claude/skills/paint-lesson/v3/run.md` (and SKILL.md's steps 0, 1 and 8) in code: it runs the
tools in `spike/tools.py` in their order and starts every helper itself. A helper is one call to Claude, or a short
conversation of them, through Claude Code's one-shot mode (`claude -p`) on the owner's subscription, on Opus. Each
helper gets everything it would have read in one message, with no tools, and answers in one reply (the change
#241's first look asked for). The call sits behind `call_claude`, so an API client can replace that one function.

Every call is logged to `<lesson>/v4/calls.json`: the helper, its input, cache and output tokens, seconds, the cost
at the API's published rates, and an estimate of how much of the input was pictures, instructions and Claude
Code's own additions. `report` sums it for `docs/spikes/v4-loop-baseline.md`.

    .venv/bin/python spike/experiments/v4_loop.py run photos/sleeping-cat.jpg
    .venv/bin/python spike/experiments/v4_loop.py run photos/sleeping-cat.jpg --lesson <folder>   # go on after a stop
    .venv/bin/python spike/experiments/v4_loop.py report <lesson>

Experiment code: it changes no tool and writes only inside its lesson folder. The lesson isn't put on the site
(it wasn't made by /paint-lesson).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable
TOOLS = [PY, str(ROOT / "spike" / "tools.py")]
SKILL = ROOT / ".claude" / "skills" / "paint-lesson"
TECHNIQUE = "techniques/acrylic-paint-along-beginner.yaml"
MODEL = "opus"

# The API's published rates for Claude Opus 5.5, dollars a million tokens (the claude-api skill, cached 2026-11-03).
# Claude Code's own cost figure (`total_cost_usd`, costBasis "list") agrees with these on every call checked.
RATE = {"input": 4.00, "output": 20.00, "cache_write_5m": 5.00, "cache_write_1h": 8.00, "cache_read": 0.20}
# #267: Claude Sonnet 5.5's, from the same table: $2 in, $10 out, a cache read $0.10, the writes 1.25 and 2 times input.
RATES = {"opus": RATE, "sonnet": {"input": 2.00, "output": 10.00, "cache_write_5m": 2.50, "cache_write_1h": 4.00,
                                  "cache_read": 0.10}}


def rates_of(model) -> dict:
    """The rates for a call's model: a name ("sonnet", "opus") or the list Claude Code reports ("claude-sonnet-5-5")."""
    names = " ".join(model) if isinstance(model, (list, tuple)) else str(model or "")
    return RATES["sonnet"] if "sonnet" in names else RATE
# A picture costs about width x height / 750 tokens once its long side is brought down to 1568 pixels. Checked on
# this model with three of the lesson's own pictures: 1599, 2045 and 898 tokens measured, 1622, 2097, 878 by this.
LONG_SIDE = 1568

LOCK = threading.Lock()


# ----------------------------------------------------------------------------------------------------- Claude, one call
def picture_tokens(w: int, h: int) -> int:
    s = min(1.0, LONG_SIDE / max(w, h))
    return round(w * s * h * s / 750)


def cost(u: dict, model=None) -> float:
    RATE = rates_of(model)
    cc = u.get("cache_creation") or {}
    w1h = cc.get("ephemeral_1h_input_tokens", 0)
    w5m = cc.get("ephemeral_5m_input_tokens", 0)
    if not cc:  # no split given: Claude Code writes its cache for an hour
        w1h = u.get("cache_creation_input_tokens", 0)
    return (u.get("input_tokens", 0) * RATE["input"] + u.get("output_tokens", 0) * RATE["output"]
            + w1h * RATE["cache_write_1h"] + w5m * RATE["cache_write_5m"]
            + u.get("cache_read_input_tokens", 0) * RATE["cache_read"]) / 1e6


class Ledger:
    """Every Claude call of the run, kept in <lesson>/v4/calls.json as it goes."""

    def __init__(self, lesson: Path):
        self.path = lesson / "v4" / "calls.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.calls = json.loads(self.path.read_text()) if self.path.exists() else []

    def add(self, rec: dict):
        with LOCK:
            self.calls.append(rec)
            self.path.write_text(json.dumps(self.calls, indent=1))


# How Claude Code caches a call's input (#253, cut 2). "1h" is its default: every input token is written to the
# hour-long cache, at twice the input rate. "5m" writes the five-minute cache (1.25 times), what a conversation that
# goes on needs. "none" writes nothing, for input that is never read again. Both are Claude Code's own switches.
CACHE_ENV = {"1h": {}, "5m": {"FORCE_PROMPT_CACHING_5M": "1"}, "none": {"DISABLE_PROMPT_CACHING": "1"}}


def call_claude(content: list[dict], system: str, *, session: str | None = None, cwd: Path,
                cache: str = "1h", model: str | None = None, effort: str | None = None) -> dict:
    """One call to Claude: a user message (text and picture blocks, the Messages API's shape) and a system prompt;
    with `session`, the message continues that conversation. `cache` is how its input is cached (CACHE_ENV).
    Returns the reply's text, the session to continue, the usage and the seconds. This is the one place that knows
    about Claude Code: an API client replaces it."""
    cmd = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--model", model or MODEL, "--tools", "", "--strict-mcp-config", "--setting-sources", "",
           "--disable-slash-commands", "--system-prompt", system]
    if session:
        cmd += ["--resume", session]
    if effort:  # #267: Claude Code's default is medium
        cmd += ["--effort", effort]
    msg = {"type": "user", "message": {"role": "user", "content": content}}
    t0 = time.time()
    for attempt in range(3):
        r = subprocess.run(cmd, input=json.dumps(msg) + "\n", capture_output=True, text=True, cwd=cwd, timeout=1800,
                           env={k: v for k, v in os.environ.items() if k not in ("FORCE_PROMPT_CACHING_5M",
                                                                               "DISABLE_PROMPT_CACHING")}
                           | CACHE_ENV[cache])
        result = None
        for line in r.stdout.splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "result":
                result = e
        if result and not result.get("is_error"):
            break
        err = (result or {}).get("result") or r.stderr[-1500:]
        print(f"  claude call failed (try {attempt + 1}): {err}", file=sys.stderr)
        time.sleep(20 * (attempt + 1))
    else:
        raise RuntimeError(f"claude -p failed three times: {err}")
    return {"text": result.get("result") or "", "session": result["session_id"], "usage": result["usage"],
            "cli_cost_usd": result.get("total_cost_usd"), "seconds": round(time.time() - t0, 1),
            "turns": result.get("num_turns"), "model": list((result.get("modelUsage") or {}).keys())}


# ------------------------------------------------------------------------------------------------- what a helper reads
class Message:
    """A user message built from files and pictures, with a count of what went in."""

    def __init__(self):
        self.blocks: list[dict] = []
        self.picture_tokens = 0
        self.pictures = 0
        self.text_chars = 0

    def text(self, s: str):
        self.blocks.append({"type": "text", "text": s})
        self.text_chars += len(s)
        return self

    def file(self, path: Path, name: str | None = None):
        return self.text(f'<file name="{name or path.name}">\n{Path(path).read_text(encoding="utf-8")}\n</file>')

    def picture(self, path: Path, name: str | None = None, max_side: int | None = None):
        from PIL import Image
        im = Image.open(path).convert("RGB")
        if max_side and max(im.size) > max_side:
            s = max_side / max(im.size)
            im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        self.text(f"Picture `{name or Path(path).name}` ({im.width} x {im.height}):")
        self.blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                        "data": base64.b64encode(buf.getvalue()).decode()}})
        self.picture_tokens += picture_tokens(*im.size)
        self.pictures += 1
        return self


NO_TOOLS = ("You have no tools. Everything you would read is in this message: files in <file> tags, pictures "
            "labelled by name. A program runs every command for you and sends back what it prints. ")


class Helper:
    """One helper: a conversation with Claude, each message logged."""

    def __init__(self, run: "Run", name: str, system: str):
        self.run, self.name, self.system = run, name, system
        self.session: str | None = None
        self.turn = 0
        self.model: str | None = None  # #267: None is Opus, Claude Code's default effort (medium)
        self.effort: str | None = None

    def ask(self, m: Message, label: str, last: bool = False) -> str:
        """`last`: nothing follows this message in the conversation, as far as the program knows beforehand."""
        self.turn += 1
        print(f"  [{self.name}] {label} ...", file=sys.stderr)
        # Claude Code's switch for no cache also stops a message reading what the conversation cached before it,
        # so only a conversation's one and only message goes uncached; a last message later on still reads.
        cache = ("none" if last and self.turn == 1 else "5m") if "api-cache" in self.run.cuts else "1h"
        r = call_claude(m.blocks, self.system, session=self.session, cwd=self.run.cwd, cache=cache, model=self.model,
                        effort=self.effort)
        self.session = r["session"]
        u = r["usage"]
        rec = {"helper": self.name, "label": label, "turn": self.turn, "session": r["session"], "cache": cache,
               "seconds": r["seconds"], "input_tokens": u.get("input_tokens", 0),
               "cache_write_tokens": u.get("cache_creation_input_tokens", 0),
               "cache_read_tokens": u.get("cache_read_input_tokens", 0), "output_tokens": u.get("output_tokens", 0),
               "thinking_tokens": (u.get("output_tokens_details") or {}).get("thinking_tokens", 0),
               "cost_usd": round(cost(u, r["model"]), 5), "effort": self.effort, "cli_cost_usd": r["cli_cost_usd"],  # the session's total so far
               "model": r["model"],
               "sent": {"pictures": m.pictures, "picture_tokens": m.picture_tokens, "text_chars": m.text_chars,
                        "system_chars": len(self.system) if self.turn == 1 else 0},
               "reply_chars": len(r["text"]), "at": datetime.now().isoformat(timespec="seconds")}
        self.run.ledger.add(rec)
        print(f"  [{self.name}] {label}: {rec['input_tokens'] + rec['cache_write_tokens'] + rec['cache_read_tokens']} "
              f"in, {rec['output_tokens']} out, ${rec['cost_usd']:.3f}, {r['seconds']} s", file=sys.stderr)
        return r["text"]

    def ask_json(self, m: Message, label: str, last: bool = False):
        text = self.ask(m, label, last)
        try:
            return last_json(text)
        except ValueError as e:
            again = Message().text(f"Your reply had no JSON I could read ({e}). Send the same answer again as one "
                                   "```json block, and nothing else.")
            return last_json(self.ask(again, label + " (JSON again)", True))


def last_json(text: str):
    blocks = re.findall(r"```(?:json)?\s*\n(.*?)\n```", text, re.S)
    for b in reversed(blocks or [text]):
        try:
            return json.loads(b)
        except ValueError:
            continue
    s, e = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1), max(text.rfind("}"),
                                                                                        text.rfind("]"))
    if s >= 0 and e > s:
        try:
            return json.loads(text[s:e + 1])
        except ValueError as err:
            raise ValueError(str(err))
    raise ValueError("no JSON found")


# ------------------------------------------------------------------------------------------------- the cuts (#253)
# Each is off unless named with --cuts, so a run with none is the baseline of #241.
CUTS = {
    "api-cache": "cache each call as the API would: the five-minute cache where the conversation goes on, none where "
                 "nothing follows",
    "plan-changes": "the plan's writer answers plan-check and check with changes to the plan, not the whole file",
    "plan-picks": "the plan's writer is sent the library's list and asks for the files it picks",
}

CHANGES_FORMAT = """Reply with only the changes to plan.json, as one ```json block in this shape. Leave out every key \
you don't need.
{"top": {"<a plan field, such as why>": <its new value>},
 "things": {"<thing id>": {<the fields to set>}},
 "paints": {"<paint name>": {<the fields to set>}},
 "rename_paints": {"<old name>": "<new name>"},
 "stages": {"<stage id>": {<the fields to set, not its steps>}},
 "steps": {"<step id>": {<the fields to set>}},
 "add_stages": [{"after": "<stage id>", "stage": {<the whole stage, with its steps>}}],
 "add_steps": [{"stage": "<stage id>", "after": "<step id>", "step": {<the whole step>}}],
 "move_steps": [{"step": "<step id>", "stage": "<stage id>", "after": "<step id>"}]}
- A field you set replaces what was there; a field set to null is removed.
- A thing, paint, stage or step set to null is removed. A thing or paint under a new id or name is added whole.
- `rename_paints` renames a paint everywhere it is named (steps, things, `of`). Renaming it to a paint that \
already exists merges the two: the old one is removed and its steps use the other.
- `after` is null for the first place in the stage (or the plan)."""


def apply_plan_changes(plan: dict, ch: dict) -> dict:
    """plan.json with the writer's changes (CHANGES_FORMAT) made. A reply that is a whole plan is taken as it is.
    Raises ValueError, naming what doesn't apply, and leaves `plan` untouched."""
    import copy
    if isinstance(ch, dict) and isinstance(ch.get("stages"), list) and "things" in ch and "paints" in ch:
        return ch
    if not isinstance(ch, dict):
        raise ValueError("the changes aren't a JSON object")
    unknown = set(ch) - {"top", "things", "paints", "rename_paints", "stages", "steps", "add_stages", "add_steps",
                         "move_steps"}
    if unknown:
        raise ValueError(f"unknown keys {sorted(unknown)}")
    p = copy.deepcopy(plan)

    def merge(obj: dict, fields: dict, what: str):
        if not isinstance(fields, dict):
            raise ValueError(f"{what}: the fields to set must be an object")
        for k, v in fields.items():
            if v is None:
                obj.pop(k, None)
            else:
                obj[k] = v

    merge(p, ch.get("top") or {}, "top")
    for key, idk in (("things", "id"), ("paints", "name")):
        items = p.setdefault(key, [])
        for i, fields in (ch.get(key) or {}).items():
            at = next((n for n, x in enumerate(items) if x.get(idk) == i), None)
            if fields is None:
                if at is None:
                    raise ValueError(f"{key}: no {i!r} to remove")
                items.pop(at)
            elif at is None:
                merge(new := {idk: i}, fields, f"{key} {i}")
                items.append(new)
            else:
                merge(items[at], fields, f"{key} {i}")
    for old, new in (ch.get("rename_paints") or {}).items():
        names = [x.get("name") for x in p["paints"]]
        if old not in names:
            raise ValueError(f"rename_paints: no paint {old!r}")
        if new in names and new != old:
            keep = p["paints"][names.index(new)]
            gone = p["paints"].pop(names.index(old))
            keep["things"] = list(dict.fromkeys((keep.get("things") or []) + (gone.get("things") or [])))
        else:
            p["paints"][names.index(old)]["name"] = new
        for x in p["paints"]:
            if x.get("of") == old:
                x["of"] = new
            if x.get("of") == x.get("name"):
                x.pop("of")
        for st in p.get("stages") or []:
            for step in st.get("steps") or []:
                if old in (step.get("paints") or []):
                    step["paints"] = list(dict.fromkeys(new if c == old else c for c in step["paints"]))
    stages = p.setdefault("stages", [])

    def stage(i):
        for st in stages:
            if st.get("id") == i:
                return st
        raise ValueError(f"no stage {i!r}")

    def find(i):
        for st in stages:
            for n, step in enumerate(st.get("steps") or []):
                if step.get("id") == i:
                    return st, n
        raise ValueError(f"no step {i!r}")

    def place(lst: list, after, key="id", what="step"):
        if after is None:
            return 0
        for n, x in enumerate(lst):
            if x.get(key) == after:
                return n + 1
        raise ValueError(f"no {what} {after!r} to put it after")

    for i, fields in (ch.get("stages") or {}).items():
        if fields is None:
            stages.remove(stage(i))
        else:
            if "steps" in fields:
                raise ValueError(f"stages {i}: set its steps with steps, add_steps or move_steps")
            merge(stage(i), fields, f"stage {i}")
    for i, fields in (ch.get("steps") or {}).items():
        st, n = find(i)
        if fields is None:
            st["steps"].pop(n)
        else:
            merge(st["steps"][n], fields, f"step {i}")
    for a in ch.get("add_stages") or []:
        if not isinstance(a.get("stage"), dict) or not a["stage"].get("id"):
            raise ValueError("add_stages: each needs a whole stage with an id")
        stages.insert(place(stages, a.get("after"), what="stage"), a["stage"])
    for a in ch.get("add_steps") or []:
        if not isinstance(a.get("step"), dict) or not a["step"].get("id"):
            raise ValueError("add_steps: each needs a whole step with an id")
        st = stage(a.get("stage"))
        st.setdefault("steps", []).insert(place(st["steps"], a.get("after")), a["step"])
    for a in ch.get("move_steps") or []:
        st, n = find(a.get("step"))
        step = st["steps"].pop(n)
        to = stage(a.get("stage"))
        to.setdefault("steps", []).insert(place(to["steps"], a.get("after")), step)
    p["stages"] = [st for st in stages if st.get("steps")]  # a stage left with no steps goes
    return p


def heading(h: str) -> str:
    """A research heading as the writer may quote it: no #s, no section number, any case."""
    return re.sub(r"^\d+\.\s*", "", h.strip().lstrip("#").strip()).lower()


def stroke_list() -> str:
    """Every stroke card in a line: its id, its name and the result it gives."""
    import yaml
    out = []
    for f in sorted((ROOT / "techniques" / "strokes").glob("*.yaml")):
        c = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        out.append(f"- {f.stem}: {c.get('name', '')}. {c.get('result', '')}".rstrip())
    return "\n".join(out)


def research_sections() -> dict:
    """docs/research/acrylic-paint-along.md cut at its headings: "For Gesso" whole, every other numbered section
    by its own heading and each of its ### headings (a ## heading is the whole section)."""
    text = (ROOT / "docs" / "research" / "acrylic-paint-along.md").read_text(encoding="utf-8")
    out, top, sub = {}, None, None
    for line in text.splitlines():
        if line.startswith("## "):
            top, sub = line, None
            key = "For Gesso" if line.strip() == "## For Gesso" else line
            if line.strip() == "## Sources":
                top = None
                continue
            out[key] = line + "\n"
            continue
        if top is None:
            continue
        tkey = "For Gesso" if top.strip() == "## For Gesso" else top
        out[tkey] += line + "\n"
        if line.startswith("### ") and tkey != "For Gesso":
            sub = "  " + line
            out[sub] = line + "\n"
        elif sub and tkey != "For Gesso":
            out[sub] += line + "\n"
    return out


# ------------------------------------------------------------------------------------------------------------- the run
class Run:
    def __init__(self, photo: str, lesson: Path, cuts: list[str] | tuple = ()):
        self.photo = photo
        self.lesson = lesson
        lesson.mkdir(parents=True, exist_ok=True)
        (lesson / "trials").mkdir(exist_ok=True)
        self.ledger = Ledger(lesson)
        self.state_path = lesson / "v4" / "state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {
            "photo": photo, "started": datetime.now().isoformat(timespec="seconds"), "done": [], "phases": {},
            "tools": [], "cuts": sorted(cuts)}
        self.cuts = set(self.state.get("cuts") or [])
        unknown = self.cuts - set(CUTS)
        if unknown:
            raise SystemExit(f"unknown cuts: {sorted(unknown)} (known: {', '.join(CUTS)})")
        self.cwd = Path(tempfile.gettempdir()) / f"gesso-v4-{lesson.name}"  # outside the repo: no CLAUDE.md loads
        self.cwd.mkdir(exist_ok=True)
        self.log: list[str] = []

    def save(self):
        self.state_path.write_text(json.dumps(self.state, indent=1))

    def tool(self, *args, ok_refused: bool = False) -> dict:
        t0 = time.time()
        r = subprocess.run(TOOLS + [str(a) for a in args], capture_output=True, text=True, cwd=ROOT)
        secs = round(time.time() - t0, 1)
        out = {}
        for line in reversed(r.stdout.strip().splitlines()):
            try:
                out = json.loads(line)
                break
            except ValueError:
                continue
        self.state["tools"].append({"tool": args[0], "seconds": secs, "code": r.returncode})
        print(f"  $ {args[0]} ({secs} s){'  REFUSED: ' + str(out.get('refused'))[:300] if 'refused' in out else ''}",
              file=sys.stderr)
        if r.returncode not in (0, 2) or ("refused" in out and not ok_refused):
            raise RuntimeError(f"{args[0]} failed ({r.returncode}): {out.get('refused') or r.stderr[-2000:]}")
        return out

    def phase(self, name: str, fn):
        if name in self.state["done"]:
            print(f"== {name}: done before", file=sys.stderr)
            return
        print(f"== {name}", file=sys.stderr)
        t0 = time.time()
        fn()
        self.state["phases"][name] = round(time.time() - t0)
        self.state["done"].append(name)
        self.save()

    def note(self, key: str, value):
        p = self.lesson / "notes.json"
        n = json.loads(p.read_text()) if p.exists() else {}
        if key == "beginner_version" and "busy" in (n.get(key) or {}):
            value = {**value, "busy": n[key]["busy"]}  # written by the busy tool, never by hand
        if key == "learned":
            n.setdefault("learned", []).extend(value)
        else:
            n[key] = value
        p.write_text(json.dumps(n, indent=1))

    def L(self, name: str) -> Path:
        return self.lesson / name

    # ----------------------------------------------------------------------------------------- steps 0 and 1
    def setup(self):
        lesson = self.lesson
        self.tool("store-photo", self.photo)
        h = Helper(self, "setup", NO_TOOLS + "You do the painter's judgment of steps 0 and 1 of a Gesso lesson: the "
                   "photo check, the canvas fit, the beginner version, the reference and the finished painting. "
                   "Answer each message with one ```json block in the shape it asks for.")
        self.helpers["setup"] = h
        m = Message().file(SKILL / "steps" / "0-setup.md").file(SKILL / "steps" / "1-reference-finish.md")
        m.file(ROOT / TECHNIQUE, TECHNIQUE).picture(ROOT / self.photo, "photo")
        m.text(f"The technique is {TECHNIQUE}: it is the only file in techniques/ with version 2 keys "
               "(acrylic-block-in-beginner.yaml has none). No canvas was named, so fit-canvas picks the standard "
               "size closest to the photo's shape.\n\nStep 0b and 0b2 first. Reply with:\n"
               '{"photo_prep": {"subject": "", "found": "", "action": "none | cropped with crop (box [...])", '
               '"why": ""}, "crop_box": null or [x0, y0, x1, y1] in the photo\'s pixels, "focus": [x, y], '
               '"keep": [x0, y0, x1, y1] (0-1 from the top left), "fit_why": "the subject and what must stay", '
               '"technique": {"why": "", "considered": [{"name": "", "why_not": ""}]}}')
        a = h.ask_json(m, "0b photo check and canvas fit")
        self.note("photo_prep", a["photo_prep"])
        self.note("technique", a["technique"])
        photo = self.photo
        if a.get("crop_box"):
            self.tool("crop", photo, "--lesson", lesson, "--out", self.L("photo_cropped.png"), "--why",
                      a["photo_prep"].get("found", "around the picture"), "--box", *a["crop_box"])
            photo = str(self.L("photo_cropped.png"))
        fit = self.tool("fit-canvas", photo, "--lesson", lesson, "--focus", *a["focus"], "--keep", *a["keep"],
                        "--why", a["fit_why"])
        fitted = self.L("00_canvas_frame.png")
        filters = []
        extend_prompt = ("Replace every flat gray area by continuing the painting naturally: the same sky, land, water, "
                         "and light, in the same style and brushwork. Change nothing that is already painted. No new "
                         "objects.")
        if fit.get("needs_render"):
            self.tool("render", "--step", "canvas", "--lesson", lesson, "--inputs", fitted, "--quality", "medium",
                      "--out", self.L("00_canvas_fit.png"), "--max-cost", "0.40", "--why-not-filter",
                      "no filter can paint the scene past the edges of the picture", "--prompt", extend_prompt)
            fitted = self.L("00_canvas_fit.png")
        busy = self.tool("busy", fitted, "--lesson", lesson)
        m = Message().text("fit-canvas printed:\n" + json.dumps({k: v for k, v in fit.items() if k != "advice"}))
        if fit.get("needs_render"):
            m.picture(self.L("00_canvas_frame.png"), "00_canvas_frame.png (the frame, gray where it extends)")
            m.picture(fitted, "00_canvas_fit.png (the extend render)")
        else:
            m.picture(fitted, "00_canvas_frame.png")
        m.text("busy printed:\n" + json.dumps(busy)).picture(lesson / "busy" / f"{fitted.stem}.jpg",
                                                             f"busy/{fitted.stem}.jpg")
        m.text('Step 0b2 3 to 6 and 0c. Reply with: {"extend_ok": true | false (true when no render was needed), '
               '"extend_redo_prompt": null or the render prompt for the one redo, "canvas_fit": {"canvas": "", '
               '"mode": "", "why": "", "lost": ""}, "beginner": {"made": true | false, "found": "", "list": "", '
               '"why": ""}, "beginner_prompt": null or the whole render prompt (beginner_version.prompt, your list, '
               'the framing), "beginner_why_not_filter": null or ""}')
        b = h.ask_json(m, "0b2 extend check and 0c beginner questions")
        if fit.get("needs_render"):
            filters.append({"label": "Canvas extend", "tool": "render", "settings": "medium",
                            "image": "00_canvas_fit.png", "why": "paint the edges the canvas adds",
                            "result": "kept" if b.get("extend_ok") else "redone", "verdict": "kept"})
        if fit.get("needs_render") and not b.get("extend_ok") and b.get("extend_redo_prompt"):
            shutil.copy(fitted, self.L("trials/canvas_fit_try1.png"))
            filters[-1].update(image="trials/canvas_fit_try1.png", verdict="dropped")
            self.tool("render", "--step", "canvas", "--lesson", lesson, "--inputs", self.L("00_canvas_frame.png"),
                      "--quality", "medium", "--out", fitted, "--max-cost", "0.40", "--fresh", "--why-not-filter",
                      "no filter can paint the scene past the edges of the picture", "--prompt",
                      b["extend_redo_prompt"])
            self.tool("busy", fitted, "--lesson", lesson)
            filters.append({"label": "Canvas extend, redo", "tool": "render", "settings": "medium",
                            "image": "00_canvas_fit.png", "why": "the fixes the first try needed",
                            "result": "the one redo", "verdict": "kept"})
        self.note("canvas_fit", b["canvas_fit"])
        self.note("beginner_version", b["beginner"])
        photo_used = fitted
        if b["beginner"].get("made") and b.get("beginner_prompt"):
            self.tool("render", "--step", "beginner", "--lesson", lesson, "--inputs", fitted, "--quality", "medium",
                      "--max-cost", "0.40", "--out", self.L("00_beginner.png"), "--why-not-filter",
                      b.get("beginner_why_not_filter") or "no filter can drop and merge these", "--prompt",
                      b["beginner_prompt"])
            bb = self.tool("busy", self.L("00_beginner.png"), "--lesson", lesson)
            m = Message().picture(self.L("00_beginner.png"), "00_beginner.png").text(
                "busy printed:\n" + json.dumps(bb)).picture(lesson / "busy" / "00_beginner.jpg", "busy/00_beginner.jpg")
            m.text('Check the beginner version (0c). Reply with {"ok": true | false, "redo_prompt": null or "", '
                   '"result": "what you saw"}')
            c = h.ask_json(m, "0c beginner check")
            filters.append({"label": "Beginner version", "tool": "render", "settings": "medium",
                            "image": "00_beginner.png", "why": "drop and merge what a beginner can't paint",
                            "result": c.get("result", ""), "verdict": "kept"})
            if not c.get("ok") and c.get("redo_prompt"):
                self.tool("render", "--step", "beginner", "--lesson", lesson, "--inputs", fitted, "--quality",
                          "medium", "--max-cost", "0.40", "--fresh", "--out", self.L("00_beginner.png"),
                          "--why-not-filter", "no filter can drop and merge these", "--prompt", c["redo_prompt"])
                self.tool("busy", self.L("00_beginner.png"), "--lesson", lesson)
            photo_used = self.L("00_beginner.png")
        self.state["photo_used"] = str(photo_used)
        # 1a: the reference
        trials = [("kuwahara", "2"), ("kuwahara", "3"), ("meanshift", "3")]
        m = Message()
        for meth, st in trials:
            out = self.L(f"trials/simplify_{meth[0]}{st}.png")
            self.tool("simplify", photo_used, "--lesson", lesson, "--out", out, "--method", meth, "--strength", st,
                      "--why", "a reference with fewer shapes")
            m.picture(out, out.name)
        self.tool("value-study", photo_used, "--lesson", lesson, "--tones", "3", "--why", "the three values")
        self.tool("palette", photo_used, "--lesson", lesson, "--colors", "6", "--why", "the main colors")
        m.text("Step 1a: pick the reference, then write the finish render's prompt (1b: the technique's "
               "finish.prompt, the photo sentence, the framing). Reply with {\"pick\": \"<trial file name>\", "
               "\"trials\": {\"<file>\": \"what you saw\"}, \"finish_prompt\": \"\", \"finish_why\": \"\"}")
        d = h.ask_json(m, "1a reference pick and finish prompt")
        pick = self.L("trials") / Path(d["pick"]).name
        shutil.copy(pick, self.L("00_reference.png"))
        for meth, st in trials:
            nm = f"simplify_{meth[0]}{st}.png"
            filters.append({"label": "Reference", "tool": "simplify", "settings": f"{meth}, strength {st}",
                            "image": f"trials/{nm}", "why": "fewer shapes", "result": d["trials"].get(nm, ""),
                            "verdict": "kept" if nm == pick.name else "dropped"})
        # 1b: the finish
        fin = self.L("99_finish.png")
        self.tool("render", "--step", "finish", "--lesson", lesson, "--inputs", self.L("00_reference.png"),
                  photo_used, "--quality", "high", "--max-cost", "0.40", "--out", fin, "--why-not-filter",
                  d.get("finish_why") or "no filter turns a reference into an acrylic painting", "--prompt",
                  d["finish_prompt"])
        m = Message().picture(fin, "99_finish.png").picture(photo_used, photo_used.name)
        if b["beginner"].get("made"):
            m.text("busy on the finish:\n" + json.dumps(self.tool("busy", fin, "--lesson", lesson)))
        m.text('Step 1b: compare the finish with the photo. Reply with {"flags": ["..."] (empty when nothing), '
               '"redo_prompt": null or the prompt for the one redo (its inputs are the finish and the photo)}')
        e = h.ask_json(m, "1b finish check", last=True)
        if e.get("flags") and e.get("redo_prompt"):
            shutil.copy(fin, self.L("trials/finish_try1.png"))
            self.tool("render", "--step", "finish", "--lesson", lesson, "--inputs", self.L("trials/finish_try1.png"),
                      photo_used, "--quality", "high", "--max-cost", "0.40", "--fresh", "--out", fin,
                      "--why-not-filter", "fixing the finish's flagged areas", "--prompt", e["redo_prompt"])
            if b["beginner"].get("made"):
                self.tool("busy", fin, "--lesson", lesson)
        self.state["finish_issues"] = e.get("flags") or []
        self.note("filters", filters)
        self.note("learned", ["Made by the v4 loop (#241): a program ran the tools and started every helper as one-shot "
                              "Claude calls with no tools; this run is a cost baseline, not a /paint-lesson run.",
                              "Steps 0 and 1: one helper, a conversation of 4 to 6 messages, given the step files, "
                              "the technique, and each tool's output and pictures."])

    # ----------------------------------------------------------------------------------------- A. the plan
    def plan_message(self) -> Message:
        lesson = self.lesson
        m = Message().file(SKILL / "v3" / "plan-brief.md")
        if "plan-picks" in self.cuts:
            return self.picks_message(m)
        m.text(f"Lesson folder: {lesson.relative_to(ROOT)}. Photo: {Path(self.state['photo_used']).relative_to(ROOT)}. "
               f"Technique: {TECHNIQUE}.")
        m.picture(self.L("99_finish.png"), "99_finish.png").picture(self.state["photo_used"],
                                                                     Path(self.state["photo_used"]).name)
        m.file(self.L("canvas.json"), "canvas.json").file(ROOT / TECHNIQUE, TECHNIQUE)
        el = subprocess.run(TOOLS + ["elements"], capture_output=True, text=True, cwd=ROOT).stdout
        m.text("`spike/tools.py elements` printed:\n" + el)
        for f in sorted((ROOT / "techniques" / "elements").glob("*.yaml")):
            m.file(f, f"techniques/elements/{f.name}")
        for f in sorted((ROOT / "techniques" / "strokes").glob("*.yaml")):
            m.file(f, f"techniques/strokes/{f.name}")
        m.file(ROOT / "docs" / "research" / "acrylic-paint-along.md", "docs/research/acrylic-paint-along.md")
        m.text("Every element file and stroke card is above, so pick from them. Reply with the whole plan.json as one "
               "```json block, then your brief's reply in a few lines. The program writes it and runs plan-check.")
        return m

    def picks_message(self, m: Message) -> Message:
        """#253, cut 4: the plan's writer is sent the library's list, not the library, and asks for what it picks."""
        lesson = self.lesson
        m.text(f"Lesson folder: {lesson.relative_to(ROOT)}. Photo: {Path(self.state['photo_used']).relative_to(ROOT)}. "
               f"Technique: {TECHNIQUE}.")
        m.picture(self.L("99_finish.png"), "99_finish.png").picture(self.state["photo_used"],
                                                                     Path(self.state["photo_used"]).name)
        m.file(self.L("canvas.json"), "canvas.json").file(ROOT / TECHNIQUE, TECHNIQUE)
        el = subprocess.run(TOOLS + ["elements"], capture_output=True, text=True, cwd=ROOT).stdout
        m.text("`spike/tools.py elements` printed:\n" + el)
        m.text("`ls techniques/strokes/`, with each card's name and the result it gives:\n" + stroke_list())
        research = research_sections()
        m.text('docs/research/acrylic-paint-along.md, its "For Gesso" section:\n' + research["For Gesso"])
        m.text("Its other sections:\n" + "\n".join(k for k in research if k != "For Gesso"))
        m.text("Before you write the plan, ask for what you'll read: the element files of the things you'll paint, "
               "the stroke card of every stroke you'll use, and the research sections your picture needs. The "
               "program sends them, then you write the plan. You can ask once, so take every one you might use. "
               'Reply with one ```json block: {"elements": ["<element id>"], "strokes": ["<card id>"], '
               '"research": ["<a section heading, as listed>"]}')
        return m

    def picks_files(self, picks: dict) -> Message:
        research = research_sections()
        m = Message()
        got = {"elements": [], "strokes": [], "research": [], "unknown": []}
        for kind, folder in (("elements", "elements"), ("strokes", "strokes")):
            for i in dict.fromkeys(picks.get(kind) or []):
                f = ROOT / "techniques" / folder / f"{Path(str(i)).stem}.yaml"
                if f.exists():
                    m.file(f, f"techniques/{folder}/{f.name}")
                    got[kind].append(f.stem)
                else:
                    got["unknown"].append(str(i))
        for h in dict.fromkeys(picks.get("research") or []):
            key = next((k for k in research if heading(k) == heading(str(h))), None)
            if key and key != "For Gesso":
                m.text(f"docs/research/acrylic-paint-along.md, {key.lstrip('#').strip()}:\n{research[key]}")
                got["research"].append(key)
            elif not key:
                got["unknown"].append(str(h))
        self.state["picks"] = got
        if got["unknown"]:
            m.text("Not found, so not sent: " + ", ".join(got["unknown"]))
        m.text("These are the files you asked for. Write the plan now. Reply with the whole plan.json as one ```json "
               "block, then your brief's reply in a few lines. The program writes it and runs plan-check.")
        return m

    def write_plan(self, plan):
        (self.L("plan.json")).write_text(json.dumps(plan, indent=1))

    def plan_fix(self, h: "Helper", ask: str, label: str):
        """Send the plan's writer what a check found and write the plan it answers with. With cut 3 (#253) the
        writer answers with changes to the plan, not the whole file again."""
        if "plan-changes" not in self.cuts:
            self.write_plan(h.ask_json(Message().text(ask + " Reply with the whole plan.json again."), label))
            return
        plan = json.loads(self.L("plan.json").read_text())
        a = h.ask_json(Message().text(ask + "\n\n" + CHANGES_FORMAT), label)
        for attempt in range(2):
            try:
                self.write_plan(apply_plan_changes(plan, a))
                return
            except ValueError as e:
                if attempt:
                    raise RuntimeError(f"the plan's changes don't apply: {e}")
                a = h.ask_json(Message().text(f"Your changes don't apply to the plan: {e}\nThe plan is as it was "
                                              "before them. Send the changes again, fixed, as one ```json block."),
                               label + " (changes again)")

    def plan(self):
        h = Helper(self, "plan-writer", NO_TOOLS + "You are the plan's writer for a Gesso painting lesson.")
        self.helpers["plan-writer"] = h
        if "plan-picks" in self.cuts:
            picks = h.ask_json(self.plan_message(), "A0 the picks")
            self.write_plan(h.ask_json(self.picks_files(picks), "A1 the plan"))
        else:
            self.write_plan(h.ask_json(self.plan_message(), "A1 the plan"))
        for rnd in range(3):
            pc = self.tool("plan-check", "--lesson", self.lesson, ok_refused=True)
            unnamed = [u["steps"][0] for u in pc.get("units") or [] if u.get("name") is None]
            if unnamed:  # plan-check's advice: a unit named null needs its first step's `unit`
                pc.setdefault("problems", []).append("these steps start a unit with no name; give each a `unit`: "
                                                     + ", ".join(map(str, unnamed)))
            if not pc.get("problems") and "refused" not in pc:
                break
            self.plan_fix(h, "plan-check printed:\n" + json.dumps(pc) + "\n\nFix what `problems` lists.",
                          f"A2 plan-check round {rnd + 1}")
        else:
            pc = self.tool("plan-check", "--lesson", self.lesson, ok_refused=True)
            if pc.get("problems"):
                raise RuntimeError(f"plan-check still lists problems after three rounds: {pc['problems']}")
        self.state["plan_check"] = {"steps": pc.get("steps"), "stages": pc.get("stages"),
                                    "units": len(pc.get("units") or []), "renders": pc.get("renders"),
                                    "mixes": pc.get("mixes"), "over_target": pc.get("over_target")}
        self.state["plan_session"] = h.session
        print(f"  plan: {pc.get('steps')} steps, {pc.get('stages')} stages, renders {pc.get('renders')}",
              file=sys.stderr)

    # ----------------------------------------------------------------------------------------- B, C
    def chain(self):
        pc = self.state.get("plan_check") or {}
        n = pc.get("renders")
        print(f"  The chain: {n} renders, about {2 * (n or 0)} cents and {(n or 0) / 4:.0f} minutes.", file=sys.stderr)
        if isinstance(n, int) and n > 20:
            raise RuntimeError(f"the chain is {n} renders, over 20: run.md says stop and ask")
        self.erase()
        self.build_and_check()

    def erase(self, redo: str | None = None):
        args = ["erase", "--lesson", self.lesson] + (["--redo", redo] if redo else [])
        for attempt in range(3):
            try:
                r = self.tool(*args, ok_refused=True)
            except RuntimeError as e:  # a network error: run again the same way, without --redo's second ask
                print(f"  erase stopped: {e}", file=sys.stderr)
                continue
            self.state.setdefault("erase", []).append({k: r.get(k) for k in ("renders", "paid", "cost_usd", "again",
                                                                               "left", "problems", "refused")})
            self.save()
            return r
        raise RuntimeError("erase failed three times")

    def build_and_check(self):
        bs = self.tool("build-steps", "--lesson", self.lesson)
        if bs.get("problems"):
            raise RuntimeError(f"build-steps problems: {bs['problems']}")
        self.state["build_notes"] = bs.get("notes")
        for t in ("step-aids", "mix", "draft-text"):
            self.tool(t, "--lesson", self.lesson)
        ck = self.tool("check", "--lesson", self.lesson, ok_refused=True)
        plan_asks = [p for p in ck.get("problems") or [] if "plan.json" in p]
        if plan_asks and not self.state.get("merged"):
            self.state["merged"] = plan_asks
            h = self.helpers.get("plan-writer")
            if h is None:
                h = Helper(self, "plan-writer", NO_TOOLS + "You are the plan's writer for a Gesso painting lesson.")
                h.session = self.state.get("plan_session")
                h.turn = 9
                self.helpers["plan-writer"] = h
            ask = "`check` asks for this change to the plan:\n" + "\n".join(plan_asks)
            if "plan-changes" in self.cuts:  # the conversation already holds the plan and every change to it
                ask += "\n\nMake only that change."
            else:
                ask += "\n\nThe plan as it stands:\n" + self.L("plan.json").read_text() + "\n\nMake only that change."
            self.plan_fix(h, ask, "C3 merge asked by check")
            pc = self.tool("plan-check", "--lesson", self.lesson, ok_refused=True)
            if pc.get("problems"):
                self.plan_fix(h, "plan-check printed:\n" + json.dumps(pc) + "\nFix it.",
                              "C3 plan-check after the merge")
            self.erase()
            return self.build_and_check()
        self.state["check_first"] = ck.get("problems")

    def checker(self):
        looks = self.lesson / "chain" / "looks"
        for rnd in range(3):
            h = Helper(self, f"chain-checker-{rnd + 1}", NO_TOOLS + "You are the chain's checker for a Gesso lesson.")
            m = Message().file(SKILL / "v3" / "chain-check.md", "chain-check.md")
            m.text(f"Folder: {looks.relative_to(ROOT)}").file(looks / "asked.json", "asked.json")
            for p in sorted(looks.glob("U*.jpg")):
                m.picture(p, p.name)
            m.text("Reply with answers.json as one ```json block, then your one line. The program writes the file.")
            answers = h.ask_json(m, f"C4 chain check round {rnd + 1}", last=True)
            (looks / "answers.json").write_text(json.dumps(answers, indent=1))
            marked = [a for a in answers if a.get("stray") or a.get("left")]
            self.state.setdefault("checker", []).append([{"look": a["look"], "why": a.get("why"),
                                                          "stray": a.get("stray"), "left": a.get("left")}
                                                         for a in marked])
            self.save()
            if not marked or rnd == 2:
                break
            redo = ",".join(f"{int(re.sub(r'\D', '', a['look']))}:{'left' if a.get('left') else 'stray'}"
                            for a in marked)
            r = self.erase(redo)
            if "refused" in r:  # a unit had its two more tries: what is marked stays
                break
        self.build_and_check()

    # ----------------------------------------------------------------------------------------- D. the words
    def writer_message(self, folder: Path) -> Message:
        m = Message().text("Follow `brief.md` in your folder. Read only that folder. Name only the paints each step "
                           "lists for itself, and keep every line under 40 words. Your folder, "
                           f"{folder.relative_to(ROOT)}, holds:")
        m.file(folder / "brief.md").file(folder / "steps.json").file(folder / "facts.md")
        for p in sorted(folder.glob("pair-*.jpg")):
            m.picture(p, p.name)
        m.picture(folder / "photo.jpg", "photo.jpg").picture(folder / "finish.jpg", "finish.jpg")
        m.text("Reply with out.json as one ```json block, then your one line. The program writes the file.")
        return m

    def words(self):
        self.tool("packets", "--lesson", self.lesson)
        stages = sorted((self.lesson / "words").glob("stage-*"))
        writers = {s.name: Helper(self, f"writer-{s.name}", NO_TOOLS + "You write one stage of a Gesso lesson.")
                   for s in stages}
        self.helpers.update({f"writer-{k}": v for k, v in writers.items()})

        def first(s: Path):
            out = writers[s.name].ask_json(self.writer_message(s), "D2 words")
            (s / "out.json").write_text(json.dumps(out, indent=1))

        with ThreadPoolExecutor(len(stages)) as ex:
            list(ex.map(first, stages))
        ct = self.tool("check-text", "--lesson", self.lesson)
        self.state["check_text_first"] = {k: ct.get(k) for k in ("failed", "dropped", "stages_with_feedback")
                                          if k in ct}

        def again(name: str):
            s = self.lesson / "words" / name
            out = writers[name].ask_json(Message().file(s / "feedback.md").text(
                "Read feedback.md (above) and write out.json again: the whole file, as one ```json block."),
                "D3 feedback", last=True)
            (s / "out.json").write_text(json.dumps(out, indent=1))

        fb = ct.get("stages_with_feedback") or []
        with ThreadPoolExecutor(max(1, len(fb))) as ex:
            list(ex.map(again, fb))
        ctf = self.tool("check-text", "--lesson", self.lesson, "--final")
        self.state["check_text_final"] = {k: ctf.get(k) for k in ("dropped", "problems", "left_failing") if k in ctf}
        bad = [p for p in ctf.get("problems") or [] if "stage-" in str(p)]
        for name in sorted({re.search(r"stage-\d\d", str(p)).group(0) for p in bad}):
            s = self.lesson / "words" / name
            w = Helper(self, f"writer-{name}-new", NO_TOOLS + "You write one stage of a Gesso lesson.")
            self.helpers[f"writer-{name}"] = w
            (s / "out.json").write_text(json.dumps(w.ask_json(self.writer_message(s), "D3 new writer", last=True), indent=1))
        if bad:
            self.tool("check-text", "--lesson", self.lesson, "--final")
        self.save()

    def stage_of(self) -> dict:
        m = {}
        for s in sorted((self.lesson / "words").glob("stage-*")):
            for st in json.loads((s / "steps.json").read_text()).get("steps", []):
                m[st.get("id")] = s.name
        return m

    def fix_words_from_check(self, problems: list[str]) -> list[str]:
        """E1: a line over 40 words, or a paint a step doesn't list, goes back to its stage's writer."""
        where = self.stage_of()
        sent = {}
        rest = []
        for p in problems:
            ids = [sid for sid in where if sid in p]
            if ids and re.search(r"line \d+ is \d+ words|isn't one of its paints", p):
                sent.setdefault(where[ids[0]], []).append(p)
            else:
                rest.append(p)
        if not sent:
            return rest

        def back(name):
            s = self.lesson / "words" / name
            h = self.helpers.get(f"writer-{name}")
            if h is None:
                h = Helper(self, f"writer-{name}", NO_TOOLS + "You write one stage of a Gesso lesson.")
                self.helpers[f"writer-{name}"] = h
                h.session = next((c["session"] for c in reversed(self.ledger.calls)
                                  if c["helper"] == f"writer-{name}"), None)
            msg = Message().text("The last check found this in your words:\n" + "\n".join(sent[name]) +
                                 "\n\nFix it and write the whole out.json again, as one ```json block.")
            (s / "out.json").write_text(json.dumps(h.ask_json(msg, "E1 check's ask", last=True), indent=1))

        with ThreadPoolExecutor(len(sent)) as ex:
            list(ex.map(back, sent))
        self.tool("check-text", "--lesson", self.lesson, "--final")
        return rest

    # ----------------------------------------------------------------------------------------- D4 and E
    def finish(self):
        ck = self.tool("check", "--lesson", self.lesson, ok_refused=True)
        rest = self.fix_words_from_check(ck.get("problems") or [])
        if len(rest) != len(ck.get("problems") or []):
            ck = self.tool("check", "--lesson", self.lesson, ok_refused=True)
            rest = ck.get("problems") or []
        h = Helper(self, "finisher", NO_TOOLS + "You finish a Gesso lesson: its review, construction diagrams and "
                   "notes. You write the files' contents; the program saves them and runs publish.")
        self.helpers["finisher"] = h
        plan = json.loads(self.L("plan.json").read_text())
        text = json.loads(self.L("text.json").read_text())
        m = Message().file(SKILL / "v3" / "run.md", "v3/run.md").file(SKILL / "steps" / "8-finish.md")
        m.file(SKILL / "steps" / "diagrams.md").file(SKILL / "steps" / "notes.md")
        m.text("Everything before this was done by the program. What the tools printed that you need:\n" + json.dumps({
            "finish_issues": self.state.get("finish_issues"), "plan_check": self.state.get("plan_check"),
            "erase": self.state.get("erase"), "checker_marked_each_round": self.state.get("checker"),
            "build_steps_notes": self.state.get("build_notes"), "check_now": ck,
            "check_text_first": self.state.get("check_text_first"),
            "check_text_final": self.state.get("check_text_final"), "merged_by_check": self.state.get("merged")},
            indent=1))
        m.file(self.L("words/dropped.json"), "words/dropped.json").text("plan.json:\n" + json.dumps(plan))
        m.text("text.json, each step's summary, tip and lines:\n" + json.dumps(
            [{"step": s["stage_id"], "summary": s.get("summary"), "tip": s.get("tip"),
              "lines": [x["text"] for x in s.get("lines", [])]} for s in text["steps"]]))
        m.file(self.L("notes.json"), "notes.json (so far)")
        for i, s in enumerate(text["steps"], 1):
            p = self.L(f"{i:02d}_{s['stage_id']}.png")
            if p.exists():
                m.picture(p, p.name, max_side=768)
        m.picture(self.L("99_finish.png"), "99_finish.png", max_side=768)
        m.text("Do D4 (review.json) and E2 (8a diagrams, 8b notes) for this lesson. Reply with one ```json block: "
               '{"review": {review.json}, "construct": {"<step id>": {construct spec}}, "notes": {"read": "", '
               '"order": "", "steps": {"<step id>": ""}, "beginner_check": {...}, "merged_parts": {}, '
               '"learned": ["..."]}, "other_fixes": "what you would change for check\'s other problems, if any"}')
        a = h.ask_json(m, "D4 review, 8a diagrams, 8b notes")
        self.apply_finish(a)
        pub = self.tool("publish", "--lesson", self.lesson, ok_refused=True)
        prev = self.tool("preview-diagrams", "--lesson", self.lesson, ok_refused=True)
        m = Message().text("publish printed:\n" + json.dumps({k: v for k, v in pub.items() if k not in ("steps",)})[:6000])
        if self.L("trials/diagrams.png").exists():
            m.picture(self.L("trials/diagrams.png"), "trials/diagrams.png")
        m.text('Look at your diagrams next to their steps. Reply with {"construct": {only the specs you change}, '
               '"notes": {only the fields you change}} or {} when nothing changes.')
        b = h.ask_json(m, "8a look at the diagrams")
        if b:
            self.apply_finish(b)
        for rnd in range(3):
            fin = self.tool("publish", "--lesson", self.lesson, "--final", ok_refused=True)
            if "refused" not in fin:
                self.state["sealed"] = True
                break
            c = h.ask_json(Message().text("publish --final refused:\n" + str(fin["refused"])[:6000] +
                                          '\nReply with {"review": ..., "construct": ..., "notes": ...}, only what '
                                          "changes, to fix it."), f"8c seal refused, round {rnd + 1}", last=True)
            self.apply_finish(c)
        self.save()

    def apply_finish(self, a: dict):
        if a.get("review"):
            self.L("review.json").write_text(json.dumps(a["review"], indent=1))
        if a.get("construct"):
            p = self.L("text.json")
            t = json.loads(p.read_text())
            for s in t["steps"]:
                if s["stage_id"] in a["construct"]:
                    s["construct"] = a["construct"][s["stage_id"]]
            p.write_text(json.dumps(t, indent=1))
        notes = dict(a.get("notes") or {})
        learned = notes.pop("learned", None)
        for k, v in notes.items():
            self.note(k, v)
        if learned:
            self.note("learned", learned)

    # ----------------------------------------------------------------------------------------- the whole run
    def go(self, until: str | None = None):
        self.helpers: dict[str, Helper] = {}
        self.phase("setup", self.setup)
        self.phase("plan", self.plan)
        self.phase("chain", self.chain)
        self.phase("checker", self.checker)
        if until == "checker":  # #267: the words and the finish are written by v4_writer_cost.py
            self.save()
            return
        self.phase("words", self.words)
        if "finish" not in self.state["done"]:
            self.note("learned", [
                "Plan writer: one helper given plan-brief.md, the finish, the photo, canvas.json, the technique, "
                "every element file, every stroke card and the research file in one message; plan-check's output "
                "went back to it.",
                "Chain checker: a fresh helper each round, given chain-check.md, asked.json and every look.",
                "Stage writers: one helper a stage, all at once, each given its whole words/stage-NN folder in one "
                "message; feedback.md went back to the same writer.",
                "Finisher: one helper for review.json, the diagrams and the notes, given run.md, step 8's files, what "
                "the tools printed, plan.json, text.json and the step pictures at 768 pixels."])
        self.phase("finish", self.finish)
        self.state["ended"] = datetime.now().isoformat(timespec="seconds")
        self.save()
        print(json.dumps(report(self.lesson), indent=1))


# ----------------------------------------------------------------------------------------------------------- report
def _when(c: dict) -> tuple[float, float]:
    end = datetime.fromisoformat(c["at"]).timestamp()
    return end - c["seconds"], end


def api_costs(calls: list[dict], without_claude_code: bool = False) -> list[float]:
    """Each call priced as the API would charge it (#253, cut 2), from what it was sent and when. Input that the
    conversation's next message reads within five minutes is written to the five-minute cache ($5 a million);
    input nothing reads again is plain input ($4). What an earlier message wrote is read from the cache ($0.20)
    when it was written under five minutes before, and sent again otherwise. Output is the same. With
    `without_claude_code`, the 1,395 tokens Claude Code adds to a conversation's first message are left out."""
    by_session: dict[str, list[int]] = {}
    for n, c in enumerate(calls):
        by_session.setdefault(c["session"], []).append(n)
    out = [0.0] * len(calls)
    for idx in by_session.values():
        idx.sort(key=lambda n: _when(calls[n])[0])
        for j, n in enumerate(idx):
            c = calls[n]
            start, end = _when(c)
            new, read = c["input_tokens"] + c["cache_write_tokens"], c["cache_read_tokens"]
            if j and start - _when(calls[idx[j - 1]])[1] > 300:
                new, read = new + read, 0  # the five-minute cache is gone: what it held is sent again
            elif j and c.get("cache") == "none":
                # sent with Claude Code's cache switched off, so what the earlier messages cached was sent again;
                # the API would have read it (#253's first cut runs, before the fix in Helper.ask)
                p = calls[idx[j - 1]]
                read = min(new, p["input_tokens"] + p["cache_write_tokens"] + p["cache_read_tokens"])
                new -= read
            if j == 0 and without_claude_code:
                new = max(0, new - CLAUDE_CODE_ADDED)
            follows = j + 1 < len(idx) and _when(calls[idx[j + 1]])[0] - end <= 300
            RATE = rates_of(c.get("model"))
            out[n] = (new * (RATE["cache_write_5m"] if follows else RATE["input"]) + read * RATE["cache_read"]
                      + c["output_tokens"] * RATE["output"]) / 1e6
    return out


def report(lesson: Path) -> dict:
    calls = json.loads((lesson / "v4" / "calls.json").read_text())
    state = json.loads((lesson / "v4" / "state.json").read_text())
    ledger = json.loads((lesson / "ledger.json").read_text()) if (lesson / "ledger.json").exists() else {}
    tot = lambda cs, k: sum(c[k] for c in cs)
    for c, a, b in zip(calls, api_costs(calls), api_costs(calls, True)):
        c["api_usd"], c["api_usd_no_cc"] = a, b
    by = {}
    for c in calls:
        kind = re.sub(r"-stage-\d\d.*|-\d+$", "", c["helper"])
        b = by.setdefault(kind, {"calls": 0, "input": 0, "cache_write": 0, "cache_read": 0, "output": 0,
                                 "cost_usd": 0.0, "api_usd": 0.0, "api_usd_no_cc": 0.0, "seconds": 0.0,
                                 "pictures": 0, "picture_tokens": 0})
        b["calls"] += 1
        b["input"] += c["input_tokens"]
        b["cache_write"] += c["cache_write_tokens"]
        b["cache_read"] += c["cache_read_tokens"]
        b["output"] += c["output_tokens"]
        b["cost_usd"] += c["cost_usd"]
        b["api_usd"] += c["api_usd"]
        b["api_usd_no_cc"] += c["api_usd_no_cc"]
        b["seconds"] += c["seconds"]
        b["pictures"] += c["sent"]["pictures"]
        b["picture_tokens"] += c["sent"]["picture_tokens"]
    # Shares of the cost: each call's fresh input split by what was sent (pictures by their tokens, the rest
    # instructions and data, Claude Code's additions the measured fixed part); cache reads go to the same split
    # pro rata; output is words written (thinking included).
    share = {"pictures": 0.0, "instructions_and_data": 0.0, "claude_code_added": 0.0, "written": 0.0}
    for c in calls:
        fresh = c["input_tokens"] + c["cache_write_tokens"]
        read_cost = c["cache_read_tokens"] * RATE["cache_read"] / 1e6
        fresh_cost = c["cost_usd"] - read_cost - c["output_tokens"] * RATE["output"] / 1e6  # as each was cached
        added = CLAUDE_CODE_ADDED if c["turn"] == 1 else 0
        pics = c["sent"]["picture_tokens"]
        rest = max(0, fresh - pics - added)
        n = max(1, pics + rest + added)
        share["pictures"] += fresh_cost * pics / n
        share["instructions_and_data"] += fresh_cost * rest / n
        share["claude_code_added"] += fresh_cost * added / n
        share["written"] += c["output_tokens"] * RATE["output"] / 1e6
        # what was cached was sent before in the same proportions, roughly
        share["instructions_and_data"] += read_cost
    for b in by.values():
        for k in ("cost_usd", "api_usd", "api_usd_no_cc"):
            b[k] = round(b[k], 3)
        b["seconds"] = round(b["seconds"])
    return {"lesson": str(lesson), "cuts": state.get("cuts") or [], "calls": len(calls),
            "claude_cost_usd": round(tot(calls, "cost_usd"), 3),
            "api_usd": round(tot(calls, "api_usd"), 3), "api_usd_no_cc": round(tot(calls, "api_usd_no_cc"), 3),
            # Claude Code's figure is the session's running total, so each session counts once, at its last call
            "claude_cli_cost_usd": round(sum({c["session"]: c["cli_cost_usd"] or 0 for c in calls}.values()), 3),
            "tokens": {"input": tot(calls, "input_tokens"), "cache_write": tot(calls, "cache_write_tokens"),
                       "cache_read": tot(calls, "cache_read_tokens"), "output": tot(calls, "output_tokens"),
                       "thinking": tot(calls, "thinking_tokens")},
            "claude_seconds": round(tot(calls, "seconds")), "image_cost_usd": ledger.get("total_cost_usd"),
            "by_helper": by, "share_usd": {k: round(v, 3) for k, v in share.items()},
            "phases_seconds": state.get("phases"), "biggest_calls": sorted(
                ({"helper": c["helper"], "label": c["label"], "cost_usd": c["cost_usd"]} for c in calls),
                key=lambda x: -x["cost_usd"])[:8]}


# Measured on 2026-11-18 (#241): a one-word message with this program's flags and a one-line system prompt read
# 1406 input tokens; the message itself is about 10. The rest is what Claude Code adds to every first message
# (its prefix, the working directory, the model, the date, the account and session lines).
CLAUDE_CODE_ADDED = 1395


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("photo")
    r.add_argument("--lesson")
    r.add_argument("--cuts", default="", help="comma-separated, from: " + ", ".join(CUTS))
    r.add_argument("--until", choices=["checker"], help="stop after this phase (#267)")
    p = sub.add_parser("report")
    p.add_argument("lesson")
    a = ap.parse_args(argv)
    if a.cmd == "report":
        print(json.dumps(report(Path(a.lesson)), indent=1))
        return
    stem = Path(a.photo).stem
    lesson = Path(a.lesson) if a.lesson else ROOT / "output" / f"{stem}_v4loop_{datetime.now():%Y%m%d-%H%M%S}"
    cuts = [c for c in a.cuts.split(",") if c]
    Run(a.photo, lesson.resolve(), cuts).go(a.until)


if __name__ == "__main__":
    main()
