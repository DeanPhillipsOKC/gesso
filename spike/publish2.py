"""Version 2 lessons through publish, mix, the seal, and the page (pipeline v2, docs/design/pipeline-v2.md section 13).

    as_v1(plan)           -> the version 2 plan as a version 1 LessonPlan, for what reads one (mix, step_paths, the seal)
    paint_extras(plan)    -> {paint name: the version 2 keys of that paint (id, parts, ...)}, kept on lesson.json's paints
    stages(plan, ...)     -> lesson.json's stages: one per step, the version 1 keys with the same types, plus new ones
    groups(plan)          -> lesson.json's groups: the plan's stages, each with its step ids

Everything that reads lesson.json (the page, the history, the step review, the notes, the embed, the site) was
written for version 1. Rather than teach each of them a second shape, a version 2 lesson.json keeps every key they
use, with the same types, and adds its new keys beside them. A step with no text yet publishes as a draft: its name
as its one instruction, and its paints.
"""

from __future__ import annotations

MADE_WITH = "composite:from-finish"  # what v1 already calls a step cut from the finish: counted as free everywhere
REASON = "cut from the finish inside the part's outline"


def _name(x: dict) -> str:
    return x.get("name") or x["id"]


def paint_names(plan: dict) -> dict[str, str]:
    """{paint id: the name the mixer and the page know it by}. The mixer keys paints by name, so a name two paints
    share gets the id after it."""
    out: dict[str, str] = {}
    for c in plan.get("paints") or []:
        name = _name(c)
        if name in out.values():
            name = f"{name} ({c['id']})"
        out[c["id"]] = name
    return out


def as_v1(plan: dict):
    """A version 1 LessonPlan built from a version 2 plan: one paint per paint (recipe empty until mix fills it), one
    step per step, and the parts with no parent as the components."""
    from run import LessonPlan, Paint, PlannedStep

    names = paint_names(plan)
    parts = {p["id"]: p for p in plan["parts"]}
    return LessonPlan(
        subject=plan.get("subject", ""), focal_point=plan.get("focal_point", ""), light=plan.get("light", ""),
        components=[_name(p) for p in plan["parts"] if not p.get("parent")],
        paints=[Paint(name=names[c["id"]], recipe="", hex=c["hex"], used_for=c.get("used_for", ""),
                      sample_x=c.get("sample_x", 0.5), sample_y=c.get("sample_y", 0.5)) for c in plan.get("paints") or []],
        steps=[PlannedStep(id=s["id"], name=_name(s), paints=_name(parts[s["part"]]), looks_like="", covers_canvas=False,
                           colors=[names[c] for c in s.get("paints") or []], brushes=s.get("brush", ""), how=[_name(s)],
                           watch_out=[]) for st in plan["stages"] for s in st["steps"]])


def paint_extras(plan: dict) -> dict[str, dict]:
    names = paint_names(plan)
    return {names[c["id"]]: {k: v for k, v in c.items() if k not in ("name", "hex")} for c in plan.get("paints") or []}


MAX_PAGE_BYTES = 8_000_000  # publish fails a version 2 page bigger than this (design section 11)


def attach_aids(lesson, stages: list[dict]) -> dict:
    """Put each step's teaching pictures (aids/aids.json, from step-aids) on its lesson.json stage as `aids`, and
    return what the whole lesson shares (the page's picture size, the transfer outline). With no aids yet, or aids
    made for other steps, every step gets an empty `aids` and the page shows the step pictures alone."""
    import json
    from pathlib import Path

    path = Path(lesson) / "aids" / "aids.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    rows = {r["id"]: r for r in data.get("steps") or []}
    fits = [r.get("id") for r in data.get("steps") or []] == [s["id"] for s in stages]
    for s in stages:
        r = rows.get(s["id"]) if fits else None
        s["aids"] = {k: v for k, v in r.items() if k not in ("id", "image")} if r else {}
    if not fits:
        return {}
    return {"view": data["view"], "canvas_box": data.get("canvas_box"), "transfer": data.get("transfer")}


def groups(plan: dict) -> list[dict]:
    return [{"id": st["id"], "name": _name(st), "steps": [s["id"] for s in st["steps"]]} for st in plan["stages"]]


def stages(plan: dict, text: dict[str, dict], paints: dict[str, dict], images: list[str], technique: dict) -> list[dict]:
    """lesson.json's stages for a version 2 lesson (the table in design section 13). `text` is text.json's steps by
    id, `paints` lesson.json's paint dicts by name, `images` each step's picture as the page shows it."""
    import cards

    known = cards.strokes()
    names = paint_names(plan)
    parts = {p["id"]: p for p in plan["parts"]}
    out = []
    flat = [(st["id"], s) for st in plan["stages"] for s in st["steps"]]
    for (group, s), image in zip(flat, images):
        t = text.get(s["id"]) or {}
        name = _name(s)
        lines = [{"kind": x.get("kind", ""), "text": x.get("text", "")} for x in t.get("lines") or []]
        ids = t.get("stroke_cards") or ([s["stroke"]] if s.get("stroke") else [])
        brush = s.get("brush", "")
        watch = [x["text"] for x in lines if x["kind"] == "watch"]
        out.append({
            "id": s["id"], "name": name, "image": image, "paints": _name(parts[s["part"]]), "looks_like": "",
            "steps": [x["text"] for x in lines] or [name], "mixes": t.get("mixes", []),
            "colors": [paints[names[c]] for c in s.get("paints") or [] if names.get(c) in paints],
            "paint_notes": t.get("paint_notes", []), "watch_out": watch or t.get("watch_out", []),
            "brushes": brush, "dry_time": technique["dry_time"],
            "made_with": t.get("made_with", MADE_WITH), "reason": t.get("reason", REASON), "summary": t.get("summary", ""),
            "values": t.get("values", []),
            "brush_list": t.get("brushes") or ([{"brush": brush, "use": name}] if brush else []),
            "strokes": [{"name": known[c]["name"], "how": known[c].get("motion", "")} if c in known
                        else {"name": c, "how": ""} for c in ids],
            "construct": t.get("construct", {}),
            # new in version 2
            "lines": lines, "tip": t.get("tip", ""), "stroke_cards": [c for c in ids if c in known],
            "part": s["part"], "show": s.get("show", "full"), "group": group,
        })
    return out
