"""Little pictures of brushes, so a beginner can see what "#8 round" or "liner" means.

    kind("Liner (#1 or #0)")  -> "liner"
    picture("1 inch flat")      -> inline SVG: the brush head, plus the mark it makes

Drawn here instead of linking out: nothing to break, works offline and inside the artifact, and themed with
the lesson page's color tokens.
"""

from __future__ import annotations

import re

# Bristle outlines, tip at the right. The ferrule ends at x=58; the bristles run to about x=92.
HEADS = {
    "flat": "M58 13 L88 13 Q91 13 91 16 L91 24 Q91 27 88 27 L58 27 Z",
    "stiff": "M58 13 L84 12 L90 10 L87 15 L92 17 L88 20 L93 23 L87 25 L90 30 L84 28 L58 27 Z",
    "round": "M58 14 Q80 13 94 20 Q80 27 58 26 Z",
    "liner": "M58 16 Q82 17 104 20 Q82 23 58 24 Z",
    "filbert": "M58 13 L80 13 Q92 13 92 20 Q92 27 80 27 L58 27 Z",
    "fan": "M58 18 L86 4 Q94 20 86 36 L58 22 Z",
    "angle": "M58 13 L92 13 L84 27 L58 27 Z",
}
# The mark each one makes, to the right of the brush.
MARKS = {
    "flat": '<rect x="112" y="11" width="44" height="18" rx="2"/>',
    "stiff": '<path d="M112 12 h44 v3 h-44z M112 18 h40 v2 h-40z M114 23 h42 v3 h-42z M112 28 h36 v1.5 h-36z"/>',
    "round": '<path d="M112 20 Q132 10 156 20 Q132 27 112 20 Z"/>',
    "liner": '<path d="M112 24 C124 10 136 32 156 14" fill="none" stroke-width="1.6"/>',
    "filbert": '<path d="M112 12 h36 q8 0 8 8 q0 8 -8 8 h-36z"/>',
    "fan": '<path d="M114 32 l4 -20 M122 32 l1 -22 M130 32 l-2 -18 M138 32 l3 -21 M146 32 l-1 -19 M154 32 l2 -16" '
           'fill="none" stroke-width="1.4"/>',
    "angle": '<path d="M112 28 L126 10 L156 10 L156 28 Z"/>',
}
NAMES = {
    "flat": "Flat: square end, for big areas and straight edges",
    "stiff": "Old stiff flat: worn, splayed bristles, for rough texture like grass and foliage",
    "round": "Round: pointed tip, thin or thick depending on how hard you press",
    "liner": "Liner: long, very thin bristles, for fine lines like twigs and grass",
    "filbert": "Filbert: flat with a rounded end, for soft-edged shapes",
    "fan": "Fan: bristles spread like a fan, for grass, fur, and soft blending",
    "angle": "Angle: flat cut on a slant, for crisp corners and curves",
}


def kind(name: str) -> str | None:
    low = name.lower()
    for k, words in (("liner", r"liner|rigger|script"), ("fan", r"\bfan\b"), ("filbert", r"filbert"),
                     ("angle", r"angle|angular"), ("stiff", r"stiff|old|scruffy|worn"), ("round", r"\bround\b"),
                     ("flat", r"\bflat\b|\bbright\b|\bwash\b")):
        if re.search(words, low):
            return k
    return None


def picture(name: str, size: str = "big") -> str:
    """Inline SVG of the brush and its mark (size "big"), or just the brush head ("small"), or "" if unknown."""
    k = kind(name)
    if not k:
        return ""
    head = (f'<rect x="2" y="17" width="40" height="6" rx="3" fill="var(--muted)"/>'
            f'<rect x="40" y="14" width="19" height="12" rx="1.5" fill="var(--rule)" stroke="var(--muted)" stroke-width=".8"/>'
            f'<path d="{HEADS[k]}" fill="var(--r-seeded)"/>')
    if size == "small":
        return (f'<svg class="brushpic sm" viewBox="30 2 78 36" aria-hidden="true" focusable="false">{head}</svg>')
    return (f'<svg class="brushpic" viewBox="22 0 138 40" role="img" aria-label="{NAMES[k]}">'
            f'<title>{NAMES[k]}</title>{head}'
            f'<g fill="var(--ultramarine)" stroke="var(--ultramarine)" opacity=".8">{MARKS[k]}</g></svg>')


def describe(name: str) -> str:
    k = kind(name)
    return NAMES[k] if k else ""
