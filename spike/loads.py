"""Paint loads (#99): one small, fixed vocabulary for how thick the paint is and how much is on the brush, with a
picture of each.

    TERMS                         {term: (kind, words)}: thick, creamy, thin; full, light, dry
    text(load)  -> "Creamy paint, a full load. Reload often."     from a stroke card's `load`
    problems(load, where) -> what's wrong with a stroke card's `load`
    picture(term, size)   -> inline SVG: a dab on the palette (thickness) or a loaded brush (amount), and its mark
    linked(text)          -> the text as HTML, its load words linked to the card, with their two small pictures

Beginners read "creamy" as "a lot of paint". It's two different things: how thick the paint is (straight from the
tube, like heavy cream, or watered like ink) and how much of it is on the brush (into the belly, just the tip, or
wiped nearly dry). Every stroke card's `load` names one of each (or only the one its research gives) from this
list, in the same words, and the basics card `paint-load` explains and shows each term
(docs/research/acrylic-paint-along.md, section 2a).

Drawn here like the brush pictures (spike/brushes.py): nothing to fetch, themed with the page's color tokens.
"""

from __future__ import annotations

import re
from html import escape as e

CARD = "paint-load"  # the basics card that explains the terms; a step's load words link to it
THICKNESS = {"thick": "Thick paint", "creamy": "Creamy paint", "thin": "Thin paint"}
AMOUNT = {"full": "a full load", "light": "a light load", "dry": "wiped nearly dry"}
TERMS = {**{t: ("thickness", w) for t, w in THICKNESS.items()}, **{t: ("amount", w) for t, w in AMOUNT.items()}}
KEYS = ("thickness", "amount", "note")
# Words that say how thick or how loaded outside the fixed terms. A card's `note` (anything else about loading:
# which corner, reload often, dip for each dot) may not use them, so a beginner meets one vocabulary only.
OTHER_WORDS = re.compile(r"\b(creamy|cream|runny|inky?|watery|fluid|thick\w*|thin\w*|load|loaded|loads|overload\w*|"
                         r"light (touch|paint)|little paint|fairly dry|nearly dry|wet and)\b", re.I)


def text(load: dict | None) -> str:
    """A stroke card's load as one line: "Creamy paint, a full load." then its note. "" for no load."""
    if not isinstance(load, dict):
        return ""
    t, a = THICKNESS.get(str(load.get("thickness") or "")), AMOUNT.get(str(load.get("amount") or ""))
    head = f"{t}, {a}." if t and a else f"{t}." if t else f"{a[0].upper()}{a[1:]}." if a else ""
    return " ".join(x for x in (head, str(load.get("note") or "").strip()) if x)


def problems(load, where: str) -> list[str]:
    """What's wrong with a stroke card's `load` ({thickness, amount, note}); a card with no load is fine (the research
    doesn't say)."""
    if load is None:
        return []
    if not isinstance(load, dict):
        return [f"{where}: load must be thickness ({', '.join(THICKNESS)}), amount ({', '.join(AMOUNT)}), and an "
                "optional note, not free text"]
    out = [f"{where}: load has {k!r}; it takes only {', '.join(KEYS)}" for k in load if k not in KEYS]
    if load.get("thickness") is not None and (not isinstance(load["thickness"], str) or load["thickness"] not in THICKNESS):
        out.append(f"{where}: load thickness {load['thickness']!r} isn't one of {', '.join(THICKNESS)}")
    if load.get("amount") is not None and (not isinstance(load["amount"], str) or load["amount"] not in AMOUNT):
        out.append(f"{where}: load amount {load['amount']!r} isn't one of {', '.join(AMOUNT)}")
    if not any(load.get(k) for k in KEYS):
        out.append(f"{where}: load is empty")
    if load.get("note") is not None and not isinstance(load["note"], str):
        out.append(f"{where}: load note must be text")
    if (m := OTHER_WORDS.search(str(load.get("note") or ""))):
        out.append(f"{where}: load note says {m.group(0)!r}; say how thick and how much with thickness and amount only")
    return out


# --- Pictures -------------------------------------------------------------------------------------------------------
# Left: a dab on the palette (thickness) or a round brush with paint on it (amount). Right: a patch of canvas with a
# dark line across it and one stroke over the line: thick and creamy hide it, thin lets it show (see-through), and a
# brush wiped nearly dry leaves broken marks with the line showing between them.

_CANVAS = ('<rect x="70" y="5" width="88" height="50" rx="3" fill="var(--gesso)" stroke="var(--rule)"/>'
           '<path d="M74 30 H154" stroke="var(--muted)" stroke-width="2.4"/>')
_PAINT = 'fill="var(--ultramarine)"'
_BRUSH = ('<rect x="0" y="27" width="22" height="6" rx="3" fill="var(--muted)"/>'
          '<rect x="21" y="24" width="12" height="12" rx="1.5" fill="var(--rule)" stroke="var(--muted)" stroke-width=".8"/>'
          '<path d="M33 24 Q52 23 64 30 Q52 37 33 36 Z" fill="var(--r-seeded)"/>')
_LEFT = {
    # a peak that holds its shape, with ridges
    "thick": f'<path d="M8 50 Q10 42 16 40 L22 30 L27 36 L33 16 L39 32 L44 26 L48 40 Q55 42 56 50 Z" {_PAINT}/>'
             '<path d="M33 22 L31 40 M42 31 L41 42 M23 35 L22 44" stroke="var(--gesso)" stroke-width="1.1" opacity=".55"/>',
    # a soft mound that has slumped a little, smooth
    "creamy": f'<path d="M6 50 Q10 36 32 34 Q54 36 58 50 Z" {_PAINT}/>',
    # a flat, spreading puddle you can see the palette through
    "thin": f'<ellipse cx="32" cy="46" rx="27" ry="5" {_PAINT} opacity=".45"/>'
            f'<ellipse cx="48" cy="40" rx="6" ry="2" {_PAINT} opacity=".35"/>',
    # paint up into the belly of the bristles
    "full": _BRUSH + f'<path d="M40 24.4 Q54 24 64 30 Q54 36 40 35.6 Z" {_PAINT}/>',
    # only the tip
    "light": _BRUSH + f'<path d="M54 26.4 Q60 28 64 30 Q60 32 54 33.6 Z" {_PAINT}/>',
    # a trace on the tip, and the towel it was wiped on
    "dry": _BRUSH + f'<path d="M57 27.6 Q61 29 64 30 Q61 31 57 32.4 Z" {_PAINT} opacity=".55"/>'
           '<rect x="8" y="44" width="50" height="10" rx="2" fill="var(--panel)" stroke="var(--rule)"/>'
           f'<path d="M12 49 H46" stroke="var(--ultramarine)" stroke-width="3" opacity=".5" stroke-linecap="round"/>',
}
_MARK = {
    # opaque, hides the line, brush marks stand up in it
    "thick": f'<path d="M76 21 H150 Q155 30 150 39 H76 Q72 30 76 21 Z" {_PAINT}/>'
             '<path d="M78 25 H148 M78 30 H150 M78 35 H148" stroke="var(--gesso)" stroke-width="1" opacity=".55"/>',
    # opaque and smooth
    "creamy": f'<path d="M76 22 H150 Q155 30 150 38 H76 Q72 30 76 22 Z" {_PAINT}/>',
    # see-through: the line shows, and it runs a little
    "thin": f'<path d="M76 22 H150 Q155 30 150 38 H76 Q72 30 76 22 Z" {_PAINT} opacity=".38"/>'
            f'<path d="M100 38 Q101 46 103 47 Q105 46 104 38 Z" {_PAINT} opacity=".38"/>',
    # a long, solid stroke
    "full": f'<path d="M76 22 H150 Q155 30 150 38 H76 Q72 30 76 22 Z" {_PAINT}/>',
    # a shorter stroke that runs out
    "light": f'<path d="M76 24 H112 Q130 26 136 30 Q130 34 112 36 H76 Q73 30 76 24 Z" {_PAINT}/>',
    # broken, scratchy marks with the line between them
    "dry": '<g stroke="var(--ultramarine)" stroke-width="2.2" stroke-linecap="round" opacity=".8">'
           '<path d="M76 23 H150" stroke-dasharray="14 4 6 7 18 3 9 6"/>'
           '<path d="M78 27 H148" stroke-dasharray="5 6 16 3 4 9 12 4"/>'
           '<path d="M76 31 H150" stroke-dasharray="9 8 4 5 20 6 6 3"/>'
           '<path d="M80 35 H146" stroke-dasharray="17 5 3 8 10 4 7 9"/></g>',
}
LABELS = {
    "thick": "Thick paint: a peak on the palette, and a stroke that hides the line under it and keeps its brush marks",
    "creamy": "Creamy paint: a soft mound on the palette, and a smooth stroke that hides the line under it",
    "thin": "Thin paint: a runny puddle on the palette, and a see-through stroke the line shows through",
    "full": "A full load: paint up into the belly of the brush, and a long solid stroke",
    "light": "A light load: paint only on the tip, and a shorter stroke that runs out",
    "dry": "Wiped nearly dry: a trace of paint on the tip after wiping on a towel, and broken, scratchy marks",
}


def picture(term: str, size: str = "big") -> str:
    """Inline SVG of one term: what's on the palette or brush, and the mark it leaves. "" for an unknown term.
    "small" is the same picture, sized to sit in a line of text."""
    if term not in TERMS:
        return ""
    cls = "loadpic sm" if size == "small" else "loadpic"
    return (f'<svg class="{cls}" viewBox="0 0 160 60" role="img" aria-label="{e(LABELS[term])}">'
            f'<title>{e(LABELS[term])}</title>{_LEFT[term]}{_CANVAS}{_MARK[term]}</svg>')


# A load in a line: "Load: Creamy paint, a full load." (a step's how line), or the same words at the start (a card's
# Load row). Matched in the escaped text, so the words are the ones `text` writes.
_T = "|".join(w.split()[0] for w in THICKNESS.values())
_A = "|".join(re.escape(w) for w in AMOUNT.values())
_A_UP = "|".join(re.escape(w[0].upper() + w[1:]) for w in AMOUNT.values())
PHRASE = re.compile(rf"(?:(?<=Load: )|^)(?:(?P<t>{_T}) paint(?:, (?P<a>{_A}))?|(?P<a2>{_A_UP}))\.")


def _term(words: str) -> str:
    low = words.lower()
    return next(t for t, (_, w) in TERMS.items() if w.lower() == low or w.split()[0].lower() == low)


def linked(text_: str, pictures: bool = True) -> str:
    """The line as HTML: its load words linked to the paint-load card, and the two small pictures right after them, so
    the painter doesn't scroll back to the card. The pictures go under the line, big enough to read on a phone. A line with no load comes back escaped and nothing else."""
    out = e(text_)
    m = PHRASE.search(out)
    if not m:
        return out
    terms = []

    def link(words: str) -> str:
        terms.append(_term(words))
        return f'<a class="loadword" href="#basic-{CARD}">{words}</a>'

    if m.group("t"):
        body = link(m.group("t")) + " paint"
        if m.group("a"):
            body += ", " + link(m.group("a"))
    else:
        body = link(m.group("a2"))
    if not pictures:  # a stroke card's Load row: its step's line just above already shows them
        return f'{out[:m.start()]}{body}.{out[m.end():]}'
    pics = "".join(picture(t, "small") for t in terms)
    return f'{out[:m.start()]}{body}.{out[m.end():]}<span class="loadpics">{pics}</span>'


# The pictures' layout, for the lesson page and the cards page: a card's pictures in two rows that wrap on a phone,
# and a step's two small ones in a row under its line.
STYLE = """
.loadpic{width:100%;max-width:15rem;height:auto;display:block}
.loadterms{display:grid;grid-template-columns:repeat(auto-fill, minmax(12rem, 1fr));gap:1rem;margin:.25rem 0 .6rem}
.loadterm{margin:0;display:grid;gap:.3rem;align-content:start}
.loadterm figcaption{font-size:.88rem;line-height:1.4}
.loadpics{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.35rem}
.loadpic.sm{width:7.5rem;max-width:45%}
"""
