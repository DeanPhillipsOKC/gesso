"""Behind the easel: the reasoning behind a lesson, folded away on the lesson page (#10).

Built from three records the paint-lesson skill leaves in the lesson folder:
    notes.json   what Claude decided and why: how it read the photo, the technique, the step order, the filters
                 and throwaway filters it tried, and what it would do differently
    ledger.json  every filter and render call, with the reason given for each
    review.json  what the fresh-context reviewer caught, and what was done about it

Every part is a <details> element, closed by default, so the painter never has to scroll past it.
"""

from __future__ import annotations

import os
from html import escape as e
from pathlib import Path

RUNGS = [  # the skill's tool order, cheapest first: (key, name, cost)
    ("filter", "Filter", "free, built in"),
    ("throw", "Throwaway filter", "free, written for this photo"),
    ("seeded", "Seeded render", "paid, started from a filter"),
    ("render", "Render", "paid, image model"),
]
RUNG_NAME = {k: n for k, n, _ in RUNGS}


def rung_of(made_with: str) -> str:
    m = (made_with or "render").lower()
    if "render" in m and "throwaway" in m:
        return "seeded"
    if m.startswith("throwaway"):
        return "throw"
    if m.startswith("filter"):
        return "filter"
    return "render"


def is_seeded(call: dict) -> bool:
    return "seed" in call.get("reason", "").lower()


def money(x: float) -> str:
    if x == 0:
        return "$0"
    return f"${x:.2f}" if x >= 0.995 else f"${x:.3f}"


def find_image(folder: Path, name: str) -> Path | None:
    """Notes paths are relative to the lesson; ledger paths are relative to the repo. Accept either."""
    if not name:
        return None
    p = Path(name)
    for c in (folder / p, p, folder.parent.parent / p, folder / p.name):
        if c.is_file():
            return c
    return None


def src_for(folder: Path, path: Path, embed: bool, max_side: int) -> str:
    from lesson_page import image_src
    if embed:
        return image_src(path.parent, path.name, True, max_side)
    return e(os.path.relpath(path, folder).replace("\\", "/"))


def stage_calls(lesson: dict, stage_id: str, is_last: bool) -> list[dict]:
    """Calls for one step. The finish is rendered under the step id "finish", and it is the last step."""
    return [c for c in lesson.get("calls", [])
            if c.get("step") == stage_id or (is_last and c.get("step") == "finish")]


def tag(kind: str, text: str) -> str:
    return f'<span class="tag t-{kind}">{e(text)}</span>'


def step_why(lesson: dict, s: dict, is_last: bool) -> str:
    """The fold under one step: why it comes now, why this tool, and every try and review note."""
    notes = lesson.get("notes") or {}
    calls = stage_calls(lesson, s["id"], is_last)
    renders = [c for c in calls if c.get("tool") == "render"]
    rung = rung_of(s.get("made_with", ""))
    paid = sum(c.get("cost_usd", 0) for c in renders)
    tries = f" · {len(renders)} {'try' if len(renders) == 1 else 'tries'} · {money(paid)}" if renders else " · free"

    trail = []
    for c in calls:
        if c.get("tool") == "filter":
            trail.append(f'<li><span class="head">{tag("filter", "Filter")}{e(c.get("filter", ""))}</span>'
                         f'<span>{e(c.get("why", ""))}</span></li>')
    # Render n, then review round n, then render n+1 (the redo): the order things happened in.
    timeline = []
    for n, c in enumerate(renders, 1):
        kind, name = ("seeded", "Seeded render") if is_seeded(c) else ("render", "Render")
        extra = " · cached" if c.get("cached") else ""
        timeline.append((2 * n, f'<li><span class="head">{tag(kind, f"{name} {n}")}{e(c.get("quality", ""))} quality · '
                                f'{money(c.get("cost_usd", 0))}{extra}</span><span>{e(c.get("reason", ""))}</span></li>'))
    for x in lesson.get("review_issues", []):
        if x.get("step_id") == s["id"]:
            r = int(x.get("round") or 1)
            timeline.append((2 * r + 1, f'<li><span class="head">{tag("review", f"Review round {r}")}'
                                        f'{e(x.get("action") or "redone")}</span><span>{e(x.get("problem", ""))}</span></li>'))
    trail += [h for _, h in sorted(timeline, key=lambda t: t[0])]

    why_now = notes.get("steps", {}).get(s["id"], "")
    reason = s.get("reason", "")
    body = "".join([
        f"<p><b>Why this step, now:</b> {e(why_now)}</p>" if why_now else "",
        f"<p><b>Why this tool:</b> {e(reason)}</p>" if reason else "",
        diagram_why(notes, s),
        f'<ol class="trail">{"".join(trail)}</ol>' if trail else "",
    ])
    if not body:
        return ""
    has_diagram = bool(s.get("construct")) and s["id"] in diagrams_of(notes)
    extra = " " + tag("diagram", "Diagram · free") if has_diagram else ""
    return (f'<details class="why"><summary>How this picture was made {tag(rung, RUNG_NAME[rung] + tries)}{extra}</summary>'
            f'<div class="why-body">{body}</div></details>')


def diagrams_of(notes: dict) -> dict:
    return (notes.get("beginner_check") or {}).get("diagrams") or {}


def diagram_why(notes: dict, s: dict) -> str:
    """Why this step got a construction diagram (or why the beginner check decided it didn't need one)."""
    check = notes.get("beginner_check") or {}
    d = diagrams_of(notes).get(s["id"])
    if d and s.get("construct"):
        rows = [("Why a diagram", d.get("noticed")), ("How it broke the shape down", d.get("pieces")),
                ("Checked against the picture", d.get("checked")), ("Where this came from", d.get("source"))]
        return '<div class="diag">' + "".join(f"<p><b>{k}:</b> {e(v)}</p>" for k, v in rows if v) + "</div>"
    skip = (check.get("no_diagram") or {}).get(s["id"])
    return f"<p><b>No diagram:</b> {e(skip)}</p>" if skip else ""


def fold(title: str, hint: str, body: str) -> str:
    return (f'<details class="note"><summary>{e(title)}<span class="hint">{e(hint)}</span></summary>'
            f'<div class="note-body">{body}</div></details>')


def all_filters(lesson: dict) -> list[dict]:
    """Filters from notes.json, plus any the ledger logged that the notes don't mention."""
    notes = lesson.get("notes") or {}
    out = list(notes.get("filters", []))
    seen = {Path(f.get("image", "")).name for f in out}
    for c in lesson.get("calls", []):
        name = Path(c.get("out", "")).name
        if c.get("tool") == "filter" and name not in seen:
            seen.add(name)
            settings = ", ".join(f"{k} {v}" for k, v in (c.get("settings") or {}).items() if v is not None)
            out.append({"tool": c.get("filter", ""), "settings": settings, "image": c.get("out", ""),
                        "why": c.get("why", ""), "verdict": ""})
    return out


def ladder(lesson: dict, filters: list[dict]) -> str:
    """Where each picture ended up on the tool order, and what was tried on the way down."""
    notes = lesson.get("notes") or {}
    stages = lesson["stages"]
    num = {s["id"]: i + 1 for i, s in enumerate(stages)}
    last_id = stages[-1]["id"]
    ended = {k: [] for k, _, _ in RUNGS}
    tried = {k: [] for k, _, _ in RUNGS}
    for s in stages:
        ended[rung_of(s.get("made_with", ""))].append(s["id"])
    for t in notes.get("throwaways", []):
        for sid in t.get("steps", []):
            if sid in num and sid not in ended["throw"] and sid not in tried["throw"]:
                tried["throw"].append(sid)
    for c in lesson.get("calls", []):
        sid = last_id if c.get("step") == "finish" else c.get("step")
        if c.get("tool") == "render" and is_seeded(c) and sid in num and sid not in ended["seeded"] + tried["seeded"]:
            tried["seeded"].append(sid)

    def pip(sid: str, key: str, cls: str = "") -> str:
        n = num[sid]
        return (f'<a class="pip p-{key} {cls}" href="#step-{n}" title="Step {n}: {e(stages[n - 1]["name"])}'
                f'{" (tried first)" if cls else ""}">{n}</a>')

    rows = []
    for key, name, cost in RUNGS:
        chips = [f'<span class="pip p-filter">{e(f.get("label") or f.get("tool", ""))}</span>'
                 for f in filters if key == "filter" and f.get("verdict") == "kept"]
        chips += [pip(sid, key) for sid in ended[key]] + [pip(sid, key, "tried") for sid in sorted(tried[key], key=num.get)]
        empty = '<span class="pip none">not needed</span>'
        rows.append(f'<div class="rung"><div class="rname"><b>{name}</b><span>{cost}</span></div>'
                    f'<div class="rchips">{"".join(chips) or empty}</div></div>')
    return (f'<div class="ladder" role="group" aria-label="Which tool made each picture">{"".join(rows)}'
            '<p class="small">Numbers are steps. A dashed, struck-through number was tried on that rung first and '
            "didn't hold up. Claude starts at the top and pays for a render only when nothing free will do.</p></div>")


def behind(lesson: dict, technique: dict, folder: Path, embed: bool, thumbs: list[str], sizes: list[str]) -> str:
    from lesson_page import dims
    from version import line, made_line
    notes = lesson.get("notes") or {}
    stages = lesson["stages"]
    calls = lesson.get("calls", [])
    renders = [c for c in calls if c.get("tool") == "render"]
    num = {s["id"]: i + 1 for i, s in enumerate(stages)}
    last_id = stages[-1]["id"]
    filters = all_filters(lesson)
    parts = []

    # How Claude read the photo
    read = lesson["photo_read"]
    comps = "".join(f"<li>{e(c)}</li>" for c in read.get("components", []))
    prep = notes.get("photo_prep") or {}
    if isinstance(prep, str):  # a run wrote a sentence instead of the dict (sailboat, 2026-11-12)
        prep = {"found": prep}
    prep_html = ('<div class="diag"><p class="label">Before starting</p>' + "".join(
        f"<p><b>{k}:</b> {e(prep[f])}</p>" for k, f in (("Subject", "subject"), ("Found in the image", "found"),
                                                        ("Done", "action"), ("Why", "why")) if prep.get(f)) + "</div>"
                 ) if prep else ""
    cf = notes.get("canvas_fit") or {}
    if cf:
        prep_html += ('<div class="diag"><p class="label">Fitted to your canvas</p>' + "".join(
            f"<p><b>{k}:</b> {e(cf[f])}</p>" for k, f in (("Canvas", "canvas"), ("Done", "mode"), ("Left out", "lost"),
                                                          ("Why", "why")) if cf.get(f)) + "</div>")
    bv = notes.get("beginner_version") or {}
    bv_html = ('<div class="diag"><p class="label">Beginner version</p>' + "".join(
        f"<p><b>{k}:</b> {e(bv[f])}</p>" for k, f in (("What made it too busy", "found"), ("Changed", "list"),
                                                      ("Why", "why")) if bv.get(f)) + "</div>") if bv else ""
    parts.append(fold("How Claude read your photo", "subject, light, layers", "".join([
        prep_html,
        bv_html,
        f"<p>{e(notes['read'])}</p>" if notes.get("read") else "",
        f"<p><b>Subject:</b> {e(read['subject'])}<br><b>Focal point:</b> {e(read['focal_point'])}<br>"
        f"<b>Light:</b> {e(read['light'])}</p>",
        f'<div><p class="label">What it saw, back to front</p><ol>{comps}</ol></div>' if comps else ""])))

    # Technique
    t = notes.get("technique") or {}
    if t:
        cards = [f'<div class="card chosen"><span class="stamp keep">Chosen</span><b>{e(technique.get("name", ""))}</b>'
                 f'<span class="small">{e(technique.get("summary", ""))}</span><p>{e(t.get("why", ""))}</p></div>']
        cards += [f'<div class="card"><span class="stamp">Passed on</span><b>{e(c.get("name") or c.get("id", ""))}</b>'
                  f'<p>{e(c.get("why_not", ""))}</p></div>' for c in t.get("considered", [])]
        how = f'<p class="small">{e(t["how_chosen"])}</p>' if t.get("how_chosen") else ""
        parts.append(fold("Why this technique", technique.get("name", ""), f'{how}<div class="pick">{"".join(cards)}</div>'))

    # Paint recipes: worked out by the mixer, compared with the ones written by eye
    mixed = [m for m in read.get("mixes", []) if m.get("mix")]
    if mixed:
        def chip(hexv: str, label: str) -> str:
            return f'<span class="mix"><span class="dot" style="background:{e(hexv)}"></span>{e(label)}</span>'
        rows = "".join(
            f'<li><b>{e(m["name"])}</b> {tag("filter" if m["mix"]["reachable"] else "review", "Delta E " + str(m["mix"]["delta_e"]))}'
            f'<div class="mixes">{chip(m["mix"]["target_hex"], "in the painting")}{chip(m["mix"]["mixed_hex"], "the recipe mixed")}</div>'
            f'<p><b>Mixer:</b> {e(m["recipe"])}</p>'
            + (f'<p class="small"><b>Written by eye first:</b> {e(m["guess_recipe"])}</p>' if m.get("guess_recipe") else "")
            + "</li>" for m in mixed)
        worst = max(m["mix"]["delta_e"] for m in mixed)
        parts.append(fold("How the paint recipes were worked out", f"{len(mixed)} paints, free", "".join([
            "<p>Paint doesn't mix like light on a screen: blue and yellow make green, not gray. So the recipes come from "
            "a pigment mixing model (Mixbox), not a guess. For each paint it tried every simple recipe from your tubes, "
            "up to three colors plus white, and kept the one that lands closest to the color in the painting. Delta E is "
            "how far off it lands: under 2 is hard to see, under 5 is close, and over 8 means these tubes can't quite "
            "make it.</p>",
            f'<ul class="plain diaglist">{rows}</ul>',
            f'<p class="small">Furthest off: Delta E {worst}. Real tubes vary by brand, so mix, compare with the step '
            "picture, and nudge.</p>"])))

    # Step order, as a storyboard
    if notes.get("order") or notes.get("steps"):
        board = "".join(
            f'<li><img src="{thumbs[i]}"{sizes[i]} alt="" loading="lazy"><div><b>{i + 1}. {e(s["name"])}</b>'
            f'<p class="small">{e(notes.get("steps", {}).get(s["id"], ""))}</p></div></li>' for i, s in enumerate(stages))
        order = f"<p>{e(notes['order'])}</p>" if notes.get("order") else ""
        parts.append(fold("Why the steps go in this order", f"{len(stages)} steps", f'{order}<ol class="board">{board}</ol>'))

    # Filters, as a contact sheet
    figs = []
    for f in filters:
        path = find_image(folder, f.get("image", ""))
        if not path:
            continue
        stamp = {"kept": '<span class="stamp keep">Kept</span>',
                 "dropped": '<span class="stamp">Not used</span>'}.get(f.get("verdict", ""), "")
        settings = f" · {e(f['settings'])}" if f.get("settings") else ""
        result = f" {e(f['result'])}" if f.get("result") else ""
        figs.append(f'<figure><img src="{src_for(folder, path, embed, 420)}"{dims(path)} alt="{e(f.get("tool", ""))} filter output" '
                    f'loading="lazy">{stamp}<b>{e(f.get("label") or f.get("tool", ""))}</b>'
                    f'<code>{e(f.get("tool", ""))}{settings}</code><figcaption>{e(f.get("why", ""))}{result}</figcaption></figure>')
    if figs:
        parts.append(fold("Filters it tried", f"{len(figs)} free looks", f'<div class="sheet">{"".join(figs)}</div>'))

    # Throwaway filters
    cards = []
    for t in notes.get("throwaways", []):
        imgs = [p for p in (find_image(folder, x) for x in t.get("images", [])) if p]
        sheet = "".join(f'<figure><img src="{src_for(folder, p, embed, 420)}"{dims(p)} alt="Throwaway filter output" loading="lazy">'
                        f"<code>{e(p.name)}</code></figure>" for p in imgs)
        steps_txt = ", ".join(f"step {num[x]}" for x in t.get("steps", []) if x in num)
        verdict = t.get("verdict", "")
        cards.append(
            f'<div class="card"><span class="stamp{" keep" if verdict in ("kept", "seeded a render") else ""}">{e(verdict)}</span>'
            f'<b class="mono">{e(t.get("script", ""))}</b>'
            f'<p><b>For:</b> {e(t.get("for", ""))}{f" ({steps_txt})" if steps_txt else ""}</p>'
            f'<p><b>What happened:</b> {e(t.get("outcome", ""))}</p>'
            + (f'<p class="small">{e(str(t["tries"]))} of 2 tries used</p>' if t.get("tries") else "")
            + (f'<div class="sheet">{sheet}</div>' if sheet else "") + "</div>")
    if cards:
        parts.append(fold("Throwaway filters it wrote", "small scripts for this photo only", "".join(cards)))

    # Beginner check: which steps got construction diagrams, and why
    check = notes.get("beginner_check") or {}
    drawn = [(st, diagrams_of(notes)[st["id"]]) for st in stages
             if st["id"] in diagrams_of(notes) and st.get("construct")]
    if check or drawn:
        rows = []
        for st, d in drawn:
            n = num[st["id"]]
            rows.append(f'<li><a href="#step-{n}"><b>Step {n}: {e(st["name"])}</b></a> {tag("diagram", d.get("source") or "beginner check")}'
                        f'<p><b>Noticed:</b> {e(d.get("noticed", ""))}</p><p><b>Pieces:</b> {e(d.get("pieces", ""))}</p></li>')
        skipped = "".join(f'<li><b>Step {num[k]}:</b> {e(v)}</li>' for k, v in (check.get("no_diagram") or {}).items()
                          if k in num)
        parts.append(fold("Where Claude drew diagrams", f"{len(drawn)} steps, free", "".join([
            f"<p>{e(check['summary'])}</p>" if check.get("summary") else "",
            f'<ul class="plain diaglist">{"".join(rows)}</ul>' if rows else "<p>No step needed one.</p>",
            f'<div><p class="label">Looked at and left without one</p><ul>{skipped}</ul></div>' if skipped else ""])))

    # Review
    rev = [f'<li>{tag("review", "Finish check")} {e(x)}</li>' for x in lesson.get("finish_issues", [])]
    for x in sorted(lesson.get("review_issues", []), key=lambda r: (r.get("round", 0), num.get(r.get("step_id"), 0))):
        rev.append(f'<li>{tag("review", "Round " + str(x.get("round", "")))} <b>Step {num.get(x.get("step_id"), "?")}:</b> '
                   f'{e(x.get("problem", ""))} <span class="mono">({e(x.get("action") or "redone")})</span></li>')
    for x in sorted(lesson.get("text_issues", []), key=lambda r: num.get(r.get("step_id"), 0)):
        rev.append(f'<li>{tag("review", "Text check: " + x.get("kind", ""))} <b>Step {num.get(x.get("step_id"), "?")}:</b> '
                   f'{e(x.get("problem", ""))} <span class="mono">({e(x.get("action") or "fixed")})</span></li>')
    if rev:
        parts.append(fold("What the reviewer caught", f"{len(rev)} notes",
                          "<p>A second Claude, with fresh eyes and none of this reasoning, compared each picture with its "
                          "neighbors and the finish. It gets two rounds of fixes, then stops; anything still off is "
                          "flagged on its step. A third checked each step's words against a measured map of what the "
                          "picture changed, asking whether a beginner following them would get there.</p>" f'<ul class="plain">{"".join(rev)}</ul>'))

    # Receipt
    total = sum(c.get("cost_usd", 0) for c in calls)
    rows = []
    def step_no(c: dict) -> int:
        return num.get(last_id if c.get("step") == "finish" else c.get("step"), 0)
    for c in sorted(renders, key=step_no):  # stable, so a step's tries stay in order
        sid = last_id if c.get("step") == "finish" else c.get("step")
        label = f"{num[sid]}. {stages[num[sid] - 1]['name']}" if sid in num else str(sid)
        rows.append(f'<div class="row"><span>{e(label)}</span><span>{money(c.get("cost_usd", 0))}</span></div>'
                    f'<div class="sub">{e(c.get("quality", ""))} quality{" · seeded" if is_seeded(c) else ""}'
                    f'{" · cached" if c.get("cached") else ""}</div>')
    n_filters = len(filters)
    receipt = (f'<div class="receipt" aria-label="What this lesson cost">{"".join(rows)}'
               f'<div class="row"><span>Filters ({n_filters})</span><span>$0</span></div>'
               + (f'<div class="row"><span>Diagrams ({len(drawn)})</span><span>$0</span></div>' if drawn else "") +
               '<div class="row"><span>Planning, review, writing</span><span>$0*</span></div>'
               f'<div class="row total"><span>Total, {len(renders)} renders</span><span>${total:.2f}</span></div>'
               + (f'<div class="row sub"><span>{e(made_line(lesson["gesso"]))}</span></div>' if lesson.get("gesso") else "") +
               '<p class="thanks">thanks for painting!</p></div>'
               '<p class="small">* Claude did this in Claude Code on a subscription, so there was no API charge.</p>')
    parts.append(fold("The receipt", f"${total:.2f} in image renders", receipt))

    if notes.get("learned"):
        parts.append(fold("What Claude would do differently", "for the next lesson",
                          f'<ul>{"".join(f"<li>{e(x)}</li>" for x in notes["learned"])}</ul>'))

    return f"""
  <section class="behind" id="behind" aria-labelledby="behind-h">
    <header><p class="eyebrow">Behind the easel</p><h2 id="behind-h">How this lesson was made</h2>
      <p class="lede">You don't need any of this to paint. It's for the curious: how Claude read your photo, picked a
        technique, and chose between free filters and paid image renders for every picture above.</p>
      <p class="margin">notes from the studio</p></header>
    {ladder(lesson, filters)}
    {"".join(parts)}
  </section>"""
