"""What the plan's writer is sent and what it answers with (pipeline v3.1, section 8; from #253's cuts 3 and 4).

- **The library's list, then the files it picks.** The writer is sent every element technique, every stroke card in
  a line (its id, name and result) and the research's "For Gesso" section with the list of its other headings. It
  asks for the element files, cards and sections it wants (`picks`), and only those are sent (`library`).
- **Changes, not the whole plan.** It answers `plan-check`, and a merge `check` asks for, with changes in
  `CHANGES_FORMAT`, which `apply_plan_changes` makes. A reply that is a whole plan is taken as it is.

`tools.py library` and `tools.py plan-change` are the commands; `spike/experiments/v4_loop.py` sends the same.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "docs" / "research" / "acrylic-paint-along.md"
FOR_GESSO = "For Gesso"
LIBRARY = "library"  # <lesson>/library/: the files the writer picked
CHANGES_LOG = "plan-changes-log.json"  # <lesson>/: every change plan-change made (the writer's own file is plan-changes.json)
KINDS = ("elements", "strokes", "research")

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
already exists merges the two: the old one is removed and its steps use the other. Renames are made first, so set \
a renamed paint's fields under its new name.
- `after` is null for the first place in the stage (or the plan)."""

CHANGE_KEYS = {"top", "things", "paints", "rename_paints", "stages", "steps", "add_stages", "add_steps", "move_steps"}


# ------------------------------------------------------------------------------------------------ the plan's changes
def is_whole_plan(ch) -> bool:
    return isinstance(ch, dict) and isinstance(ch.get("stages"), list) and "things" in ch and "paints" in ch


def apply_plan_changes(plan: dict, ch: dict) -> dict:
    """plan.json with the writer's changes (CHANGES_FORMAT) made. A reply that is a whole plan is taken as it is.
    Raises ValueError, naming what doesn't apply, and leaves `plan` untouched."""
    if is_whole_plan(ch):
        return ch
    if not isinstance(ch, dict):
        raise ValueError("the changes aren't a JSON object")
    unknown = set(ch) - CHANGE_KEYS
    if unknown:
        raise ValueError(f"unknown keys {sorted(unknown)}")
    for k in ("top", "things", "paints", "rename_paints", "stages", "steps"):
        if not isinstance(ch.get(k) or {}, dict):
            raise ValueError(f"{k} must be an object keyed by id or name, not a list")
    for k in ("add_stages", "add_steps", "move_steps"):
        if not isinstance(ch.get(k) or [], list) or not all(isinstance(x, dict) for x in ch.get(k) or []):
            raise ValueError(f"{k} must be a list of objects")
    renames = ch.get("rename_paints") or {}
    for old, new in renames.items():
        if not isinstance(new, str) or not new.strip():
            raise ValueError(f"rename_paints: {old!r} needs a new name, not {new!r}")
    gone = set(renames) & set(ch.get("paints") or {})
    if gone:  # renames are made first, so the old name no longer names a paint
        raise ValueError(f"paints: {sorted(gone)} renamed in the same changes; set their fields under the new name")
    p = copy.deepcopy(plan)

    def merge(obj: dict, fields: dict, what: str):
        if not isinstance(fields, dict):
            raise ValueError(f"{what}: the fields to set must be an object")
        for k, v in fields.items():
            if v is None:
                obj.pop(k, None)
            else:
                obj[k] = v

    for old, new in (ch.get("rename_paints") or {}).items():
        names = [x.get("name") for x in p.setdefault("paints", [])]
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
                x.pop("of", None)
        for st in p.get("stages") or []:
            for step in st.get("steps") or []:
                if old in (step.get("paints") or []):
                    step["paints"] = list(dict.fromkeys(new if c == old else c for c in step["paints"]))
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

    def place(lst: list, after, what="step"):
        if after is None:
            return 0
        for n, x in enumerate(lst):
            if x.get("id") == after:
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


# ------------------------------------------------------------------------------------------------------- the library
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
    by its own heading and each of its ### headings (a ## heading is the whole section). Sources are left out."""
    text = RESEARCH.read_text(encoding="utf-8")
    out, top, sub = {}, None, None
    for line in text.splitlines():
        if line.startswith("## "):
            top, sub = line, None
            if line.strip() == "## Sources":
                top = None
                continue
            out[FOR_GESSO if line.strip() == "## For Gesso" else line] = line + "\n"
            continue
        if top is None:
            continue
        tkey = FOR_GESSO if top.strip() == "## For Gesso" else top
        out[tkey] += line + "\n"
        if line.startswith("### ") and tkey != FOR_GESSO:
            sub = "  " + line
            out[sub] = line + "\n"
        elif sub and tkey != FOR_GESSO:
            out[sub] += line + "\n"
    return out


def element_files(lesson: Path | None = None) -> dict[str, Path]:
    """Every element technique's file by id: techniques/elements/, then a lesson's drafted ones (<lesson>/elements/)."""
    files = {f.stem: f for f in sorted((ROOT / "techniques" / "elements").glob("*.yaml"))}
    if lesson is not None and (Path(lesson) / "elements").is_dir():
        files.update({f.stem: f for f in sorted((Path(lesson) / "elements").glob("*.yaml"))})
    return files


def library_list() -> dict:
    """What the writer picks from, beside what `elements` prints: every card in a line, the research's "For Gesso"
    section whole and the headings of the rest."""
    r = research_sections()
    return {"strokes": stroke_list().splitlines(), "for_gesso": r[FOR_GESSO],
            "research": [k for k in r if k != FOR_GESSO]}


def resolve(picks: dict, lesson: Path | None = None) -> dict:
    """The writer's picks matched to files: {"elements": {id: path}, "strokes": {id: path}, "research": [heading
    keys, in the file's order], "unknown": {kind: [as asked]}}. An id may carry its folder or `.yaml`; a heading
    matches with or without its #s and number, in any case. A ### section inside a ## section also picked is
    left out (the ## holds it)."""
    if not isinstance(picks, dict):
        raise ValueError('the picks aren\'t a JSON object: {"elements": [...], "strokes": [...], "research": [...]}')
    extra = set(picks) - set(KINDS)
    if extra:
        raise ValueError(f"unknown keys {sorted(extra)}: the picks are elements, strokes and research")
    for k in KINDS:
        if not isinstance(picks.get(k) or [], list):
            raise ValueError(f"{k} must be a list")
    els = element_files(lesson)
    cards = {f.stem: f for f in sorted((ROOT / "techniques" / "strokes").glob("*.yaml"))}
    got = {"elements": {}, "strokes": {}, "research": [], "unknown": {k: [] for k in KINDS}}
    for kind, have in (("elements", els), ("strokes", cards)):
        for i in dict.fromkeys(str(x) for x in picks.get(kind) or []):
            stem = Path(i.strip()).stem
            if stem in have:
                got[kind][stem] = have[stem]
            else:
                got["unknown"][kind].append(i)
    r = research_sections()
    keys = list(r)
    wanted = set()
    for h in dict.fromkeys(str(x) for x in picks.get("research") or []):
        key = next((k for k in keys if heading(k) == heading(h)), None)
        if key is None:
            got["unknown"]["research"].append(h)
        elif key != FOR_GESSO:  # always sent
            wanted.add(key)
    top = None
    for k in keys:
        if not k.startswith("  "):
            top = k
        if k in wanted and not (k.startswith("  ") and top in wanted):
            got["research"].append(k)
    return got


def write_library(lesson: Path, picks: dict) -> dict:
    """<lesson>/library/ with the files picked, added to any picked before: elements/<id>.yaml, strokes/<id>.yaml,
    and research.md ("For Gesso", then each section picked). picks.json there keeps what was asked."""
    lesson = Path(lesson)
    folder = lesson / LIBRARY
    before = {}
    if (folder / "picks.json").exists():
        try:
            before = json.loads((folder / "picks.json").read_text(encoding="utf-8"))
        except ValueError:
            before = {}
    got = resolve(picks, lesson)  # raises before anything is written
    allp = {k: list(dict.fromkeys((before.get(k) or []) + [str(x) for x in picks.get(k) or []])) for k in KINDS}
    every = resolve(allp, lesson)
    if folder.exists():
        shutil.rmtree(folder)
    for kind in ("elements", "strokes"):
        (folder / kind).mkdir(parents=True, exist_ok=True)
        for i, f in every[kind].items():
            shutil.copyfile(f, folder / kind / f"{i}.yaml")
    r = research_sections()
    md = [r[FOR_GESSO].rstrip()] + [r[k].rstrip() for k in every["research"]]
    (folder / "research.md").write_text(
        "# docs/research/acrylic-paint-along.md: the sections picked\n\n" + "\n\n".join(md) + "\n", encoding="utf-8")
    (folder / "picks.json").write_text(json.dumps(allp, indent=1), encoding="utf-8")
    files = ([f"{LIBRARY}/elements/{i}.yaml" for i in every["elements"]]
             + [f"{LIBRARY}/strokes/{i}.yaml" for i in every["strokes"]] + [f"{LIBRARY}/research.md"])
    return {"folder": str(folder), "files": files, "research": [k.strip().lstrip("#").strip() for k in every["research"]],
            "added": {k: list(got[k]) if k != "research" else [x.strip() for x in got[k]] for k in KINDS},
            "unknown": {k: v for k, v in got["unknown"].items() if v}}
