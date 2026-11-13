"""Construction diagrams: how to build a shape from simple pieces, drawn as small SVG panels (free, no render).

A finished step image shows the shape, not how to get there. When a step blocks in a shaped object (a pumpkin, a
cat, a house, a tree), the skill writes a `construct` spec in text.json and the lesson page draws it as a strip of
panels: each panel adds the next pieces on top of what's already there, with the new pieces outlined and optional
arrows for the brush's direction.

Spec (coordinates are a 100 x 100 box, y down):

    {"title": "Build each pumpkin from simple pieces",
     "paint": "Pumpkin orange",                      # default fill, a paint's name or id from the plan (or a #hex)
     "stages": [
       {"caption": "A center oval",
        "add": [{"ellipse": [50, 55, 13, 20]}]},
       {"caption": "A ( ) on each side, tucked behind",
        "add": [{"ellipse": [38, 57, 12, 18], "behind": true}, {"ellipse": [62, 57, 12, 18], "behind": true}],
        "arrows": ["M 30 42 Q 24 57 30 72"]},      # brush direction, shown in this panel only
       {"caption": "Rib lines along the seams",
        "add": [{"line": "M 44 38 Q 40 55 44 74", "paint": "Rib brown", "width": 1.6}]}]}

Shapes: ellipse [cx, cy, rx, ry] (optional "rotate"), circle [cx, cy, r], rect [x, y, w, h] (optional "round"),
path "<d>" (filled, optional "opacity"), line "<d>" (stroked only, "width"). Any shape may set "paint" and "behind" (draw under what's
there), and "done" (already painted in an earlier step: drawn without the dashed outline, so a later step's
diagram can start from it). Path data is checked to contain only path commands and numbers.
"""

from __future__ import annotations

import re
from html import escape as e

PATH_OK = re.compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9eE.,\s+-]{1,600}$")
HEX_OK = re.compile(r"^#[0-9a-fA-F]{3,8}$")


class BadSpec(ValueError):
    pass


def _num(v, lo=-50.0, hi=150.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise BadSpec(f"not a number: {v!r}")
    return max(lo, min(hi, x))


def _path(d: str) -> str:
    if not isinstance(d, str) or not PATH_OK.match(d):
        raise BadSpec(f"bad path data: {str(d)[:40]!r}")
    return d


def lookup(paints: list[dict]) -> dict[str, str]:
    """{name or id: hex} for a lesson's paints, the map strip() and problems() take. A diagram may name a paint by
    either; a diagram given ids drew every shape gray before this (#91)."""
    out = {p["id"]: p["hex"] for p in paints if p.get("id") and p.get("hex")}
    out.update({p["name"]: p["hex"] for p in paints if p.get("name") and p.get("hex")})
    return out


def _kind(shape: dict) -> str:
    return next((k for k in ("ellipse", "circle", "rect", "path", "line") if k in shape), "shape")


def problems(spec: dict | None, paints: dict[str, str], where: str) -> list[str]:
    """Shapes whose paint is no paint's name or id in `paints` and no #hex: they would draw gray. Empty for a missing
    spec; a spec that doesn't draw at all is strip()'s to report."""
    out: list[str] = []
    if not isinstance(spec, dict) or not isinstance(spec.get("stages"), list):
        return out
    default = spec.get("paint") or ""
    title = spec.get("title") or "its diagram"
    for k, stage in enumerate(spec["stages"]):
        # a stage or shape of the wrong type is a spec that doesn't draw: strip() reports that, this mustn't crash
        add = stage.get("add") if isinstance(stage, dict) else None
        for n, shape in enumerate(add if isinstance(add, list) else []):
            if not isinstance(shape, dict):
                continue
            name = shape.get("paint") or default
            if isinstance(name, str) and (name in paints or HEX_OK.match(name)):
                continue
            what = f"paint {name!r}" if name else "no paint"
            out.append(f"{where}: diagram {title!r}, panel {k + 1}, shape {n + 1} ({_kind(shape)}) has {what}, "
                       "so it draws gray. Use a paint's name or id from the plan, or a #hex.")
    return out


def _fill(shape: dict, default: str, paints: dict[str, str]) -> str:
    name = shape.get("paint") or default
    if name in paints:
        return paints[name]
    if isinstance(name, str) and HEX_OK.match(name):
        return name
    return "var(--muted)"


def shape_svg(shape: dict, fill: str, new: bool) -> str:
    """One shape. New pieces get a dashed outline in the accent color so the eye finds what this panel adds."""
    # Every filled piece keeps a faint seam so overlapping pieces of one color still read as separate shapes.
    outline = (' stroke="var(--ultramarine)" stroke-width="1.1" stroke-dasharray="2.2 1.6"' if new
               else ' stroke="var(--ink)" stroke-opacity=".45" stroke-width=".7"')
    if "ellipse" in shape:
        cx, cy, rx, ry = (_num(v) for v in shape["ellipse"])
        rot = f' transform="rotate({_num(shape.get("rotate", 0), -360, 360)} {cx} {cy})"' if shape.get("rotate") else ""
        return f'<ellipse cx="{cx}" cy="{cy}" rx="{abs(rx)}" ry="{abs(ry)}" fill="{fill}"{outline}{rot}/>'
    if "circle" in shape:
        cx, cy, r = (_num(v) for v in shape["circle"])
        return f'<circle cx="{cx}" cy="{cy}" r="{abs(r)}" fill="{fill}"{outline}/>'
    if "rect" in shape:
        x, y, w, h = (_num(v) for v in shape["rect"])
        rr = _num(shape.get("round", 0), 0, 50)
        return f'<rect x="{x}" y="{y}" width="{abs(w)}" height="{abs(h)}" rx="{rr}" fill="{fill}"{outline}/>'
    if "path" in shape:
        op = f' opacity="{_num(shape["opacity"], 0, 1)}"' if "opacity" in shape else ""
        return f'<path d="{_path(shape["path"])}" fill="{fill}"{outline}{op}/>'
    if "line" in shape:
        w = _num(shape.get("width", 1.5), 0.3, 8)
        glow = (f'<path d="{_path(shape["line"])}" fill="none" stroke="var(--ultramarine)" stroke-width="{w + 1.6}" '
                f'stroke-linecap="round" opacity=".35"/>') if new else ""
        return (f'{glow}<path d="{_path(shape["line"])}" fill="none" stroke="{fill}" stroke-width="{w}" '
                f'stroke-linecap="round"/>')
    raise BadSpec(f"unknown shape: {sorted(shape)}")


def strip(spec: dict, paints: dict[str, str], uid: str) -> str:
    """The whole diagram as HTML: a titled row of numbered panels. Returns "" for a missing or broken spec, so a
    bad diagram never breaks the lesson page."""
    if not isinstance(spec, dict) or not spec.get("stages"):
        return ""
    try:
        return _strip(spec, paints, uid)
    except (BadSpec, AttributeError, KeyError, TypeError, ValueError):
        return ""


def _strip(spec: dict, paints: dict[str, str], uid: str) -> str:
    default = spec.get("paint", "")
    layers: list[tuple[int, dict]] = []  # (stage it was added in, shape), bottom to top
    panels = []
    marker = f"arrow-{e(uid)}"
    for k, stage in enumerate(spec["stages"]):
        for shape in stage.get("add", []):
            if shape.get("behind"):
                layers.insert(0, (k, shape))
            else:
                layers.append((k, shape))
        body = "".join(shape_svg(sh, _fill(sh, default, paints), added == k and not sh.get("done"))
                       for added, sh in layers)
        arrows = "".join(f'<path d="{_path(d)}" fill="none" stroke="var(--ink)" stroke-width="1.1" '
                         f'stroke-linecap="round" marker-end="url(#{marker})"/>' for d in stage.get("arrows", []))
        caption = e(stage.get("caption", ""))
        panels.append(
            f'<figure class="panel"><svg viewBox="0 0 100 100" role="img" aria-label="{k + 1}. {caption}">'
            f'<defs><marker id="{marker}" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" '
            f'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="var(--ink)"/></marker></defs>'
            f'{body}{arrows}</svg><figcaption><b>{k + 1}</b> {caption}</figcaption></figure>')
        marker = f"arrow-{e(uid)}-{k + 1}"  # ids must be unique on the page
    title = e(spec.get("title", "Build it from simple pieces"))
    return (f'<div class="build"><p class="label">{title}</p><div class="panels">{"".join(panels)}</div>'
            '<p class="small">Dashed outline: what to paint in that picture. Arrows: which way to move the brush.</p></div>')
