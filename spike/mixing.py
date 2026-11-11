"""Paint mixing recipes computed from pigment physics, not written by eye (#22).

    recipe = solve("#7fa3c8", ["Titanium white", "Ultramarine blue", "Burnt sienna", ...])
    recipe["text"]      -> "3 parts titanium white, 1 part ultramarine blue, a touch of burnt sienna"
    recipe["delta_e"]   -> how far the mixed color lands from the target (CIEDE2000; under ~2 is hard to see)

Paint doesn't mix like screen light (blue and yellow make green, not gray), so the mixing model is Mixbox
(pymixbox, by Secret Weapons), which is fit to real pigments. Its license is CC BY-NC 4.0: free while Gesso
isn't sold. If it ever is, swap `_mix_rgb` for Spectral.js-style Kubelka-Munk or buy a Mixbox license;
nothing else in this file depends on Mixbox (docs/decisions.md, 2026-11-11).

The solver tries every friendly recipe (up to 3 colored tubes plus white, in whole parts or "a touch") and
keeps the closest. Among recipes that look the same (within 1 Delta E of the best), it keeps the simplest.
"""

from __future__ import annotations

import itertools
import math
from functools import lru_cache

import mixbox

# Tube colors. Mixbox's own pigment colors where it has one; the rest are close generic values.
TUBES = {
    "white": (255, 255, 255),
    "cadmium yellow": (254, 236, 0),
    "hansa yellow": (252, 211, 0),
    "yellow ochre": (196, 143, 36),  # not a Mixbox pigment; a typical ochre masstone
    "cadmium orange": (255, 105, 0),
    "cadmium red": (255, 39, 2),
    "quinacridone magenta": (128, 2, 46),
    "cobalt violet": (78, 0, 66),
    "ultramarine": (25, 0, 89),
    "cobalt blue": (0, 33, 133),
    "phthalo blue": (13, 27, 68),
    "phthalo green": (0, 60, 50),
    "permanent green": (7, 109, 22),
    "sap green": (107, 148, 4),
    "burnt sienna": (123, 72, 0),
    "burnt umber": (74, 46, 26),  # not a Mixbox pigment
    "black": (20, 20, 22),
}
TOUCH = 0.2  # "a touch" in parts
COLOR_PARTS = [0, TOUCH, 1, 2, 3]  # colored tubes
WHITE_PARTS = [0, TOUCH, 1, 2, 3, 4, 6, 8, 12]  # tints need a lot of white
MAX_COLORED = 3
REACHABLE = 8.0  # Delta E above this: the tubes can't really make it


class UnknownTube(ValueError):
    pass


CUSTOM: dict[str, tuple[int, int, int]] = {}  # a painter's own tubes, by exact name (palettes/*.yaml)


def register(tubes: list[dict]) -> list[str]:
    """Load a painter's palette ({name, rgb} each) so recipes can use those tubes by name. Returns the names."""
    for t in tubes:
        CUSTOM[t["name"]] = tuple(int(v) for v in t["rgb"])
    return [t["name"] for t in tubes]


def tube_rgb(name: str) -> tuple[int, int, int]:
    if name in CUSTOM:
        return CUSTOM[name]
    """'Cadmium yellow medium (hue)' -> the cadmium yellow pigment. Matches the longest known key in the name."""
    low = name.lower()
    hits = [k for k in TUBES if k in low] or (["white"] if "white" in low else [])
    if not hits:
        raise UnknownTube(f"no pigment color for tube {name!r}; add it to TUBES in spike/mixing.py")
    return TUBES[max(hits, key=len)]


def short_name(tube: str) -> str:
    """The name a painter says: 'Cadmium yellow medium (hue)' -> 'yellow', 'Titanium white' -> 'white'. A
    painter's own tube is said the way it's labeled."""
    if tube in CUSTOM and not any(k in tube.lower() for k in TUBES):
        return tube.lower()  # "Light magenta", "Cashew": said the way they're labeled
    low = tube.lower()
    key = max([k for k in TUBES if k in low] or ["white" if "white" in low else low], key=len)
    return {"cadmium yellow": "yellow", "cadmium red": "red", "cadmium orange": "orange"}.get(key, key)


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_hex(c) -> str:
    return "#" + "".join(f"{int(v):02x}" for v in c)


@lru_cache(maxsize=None)
def _latent(rgb: tuple[int, int, int]) -> tuple[float, ...]:
    return tuple(mixbox.rgb_to_latent(rgb))


def _mix_rgb(parts: list[tuple[tuple[int, int, int], float]]) -> tuple[int, int, int]:
    total = sum(w for _, w in parts)
    z = [0.0] * mixbox.LATENT_SIZE
    for rgb, w in parts:
        for i, v in enumerate(_latent(rgb)):
            z[i] += v * w / total
    return tuple(mixbox.latent_to_rgb(z))


def mix(recipe: dict[str, float]) -> str:
    """{'Titanium white': 2, 'Ultramarine blue': 1} -> the mixed color as #rrggbb."""
    return rgb_hex(_mix_rgb([(tube_rgb(t), w) for t, w in recipe.items() if w > 0]))


# --- CIEDE2000 -------------------------------------------------------------


def _lab(rgb) -> tuple[float, float, float]:
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(float(v)) for v in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(c1, c2) -> float:
    """CIEDE2000 between two colors (#hex or RGB tuples)."""
    if isinstance(c1, str):
        c1 = hex_rgb(c1)
    if isinstance(c2, str):
        c2 = hex_rgb(c2)
    L1, a1, b1 = _lab(c1)
    L2, a2, b2 = _lab(c2)
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    if C1p * C2p == 0:
        dh = 0
    elif dh > 180:
        dh -= 360
    elif dh < -180:
        dh += 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dh / 2))
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    else:
        hbp = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dtheta = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / math.sqrt(20 + (Lbp - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


# --- Solver ------------------------------------------------------------------


def words(parts: dict[str, float]) -> str:
    """Biggest amount first: '3 parts titanium white, 1 part ultramarine blue, a touch of burnt sienna'."""
    order = sorted(((w, t) for t, w in parts.items() if w > 0), key=lambda x: -x[0])
    if len(order) == 1:
        return f"{short_name(order[0][1]).capitalize()}, straight from the tube"
    out = []
    for w, t in order:
        n = short_name(t)
        out.append(f"a touch of {n}" if w == TOUCH else f"{w:g} part{'s' if w != 1 else ''} {n}")
    return ", ".join(out)


def _candidates(palette: list[str]):
    whites = [t for t in palette if "white" in t.lower()]
    white = whites[0] if whites else None
    colored = [t for t in palette if t != white]
    for k in range(0, MAX_COLORED + 1):
        for tubes in itertools.combinations(colored, k):
            for amounts in itertools.product(COLOR_PARTS[1:], repeat=k):
                for w in (WHITE_PARTS if white else [0]):
                    parts = dict(zip(tubes, amounts))
                    if w:
                        parts[white] = w
                    if not parts or all(v == TOUCH for v in parts.values()):
                        continue
                    # skip scaled copies (2:2 is 1:1); keep the smallest whole-part form
                    whole = [v for v in parts.values() if v != TOUCH]
                    if whole and math.gcd(*[int(v) for v in whole]) > 1:
                        continue
                    yield parts


def _complexity(parts: dict[str, float]) -> tuple:
    return (len(parts), sum(v for v in parts.values()))


SHORTLIST = 7  # a big palette is first narrowed to this many colored tubes for the full search


def _shortlist(goal, palette: list[str]) -> list[str]:
    """With a big palette (a painter's 30 tubes), search one- and two-tube recipes first, then keep the tubes the
    best of those use. The full three-tube search over 30 tubes would be millions of mixes."""
    white = next((t for t in palette if "white" in t.lower()), None)
    colored = [t for t in palette if t != white]
    tubes = {t: tube_rgb(t) for t in palette}
    tries = []
    for k in (1, 2):
        for combo in itertools.combinations(colored, k):
            for amounts in itertools.product([1, 2, 3], repeat=k):
                for w in ([0, 1, 3, 8] if white else [0]):
                    parts = dict(zip(combo, amounts))
                    if w:
                        parts[white] = w
                    rgb = _mix_rgb([(tubes[t], v) for t, v in parts.items()])
                    tries.append((delta_e(goal, rgb), combo))
    keep: list[str] = []
    for _, combo in sorted(tries, key=lambda x: x[0]):
        for t in combo:
            if t not in keep:
                keep.append(t)
        if len(keep) >= SHORTLIST:
            break
    return ([white] if white else []) + keep[:SHORTLIST]


@lru_cache(maxsize=None)
def _solve(target: str, palette: tuple[str, ...]) -> dict:
    goal = hex_rgb(target)
    if len(palette) > SHORTLIST + 1:
        palette = tuple(_shortlist(goal, list(palette)))
    tubes = {t: tube_rgb(t) for t in palette}
    scored = []
    for parts in _candidates(list(palette)):
        rgb = _mix_rgb([(tubes[t], w) for t, w in parts.items()])
        scored.append((delta_e(goal, rgb), parts, rgb))
    best = min(s[0] for s in scored)
    near = [s for s in scored if s[0] <= best + 1.0]
    de, parts, rgb = min(near, key=lambda s: (_complexity(s[1]), s[0]))
    return {"parts": {t: parts[t] for t in palette if t in parts}, "text": words(parts), "mixed_hex": rgb_hex(rgb),
            "target_hex": target.lower(), "delta_e": round(de, 1), "reachable": de <= REACHABLE}


def solve(target_hex: str, palette: list[str]) -> dict:
    """The friendliest recipe from these tubes that lands closest to the target color."""
    return dict(_solve(target_hex.lower(), tuple(palette)))


def single_tube(name: str, recipe: str, palette: list[str]) -> str | None:
    """The tube, when a paint is meant straight from it: the paint is named after one tube ("Burnt sienna") or its
    recipe names one tube and says so ("burnt sienna, straight from the tube"). The solver would otherwise mix
    the swatch's color from three tubes (balloon rerun, 2026-11-11)."""
    def tubes_in(text: str) -> list[str]:
        low = text.lower()
        return [t for t in palette if short_name(t) in low or t.lower() in low]

    named = tubes_in(name)
    if len(named) == 1 and name.lower().strip() in (short_name(named[0]), named[0].lower()):
        return named[0]
    in_recipe = tubes_in(recipe)
    says_straight = any(w in recipe.lower() for w in ("straight", "from the tube", "unmixed", "on its own"))
    if len(in_recipe) == 1 and says_straight:
        return in_recipe[0]
    return None


def straight(tube: str, target_hex: str) -> dict:
    """A paint used straight from one tube, in the same shape solve() returns."""
    mixed = rgb_hex(tube_rgb(tube))
    de = delta_e(target_hex, mixed)
    return {"parts": {tube: 1}, "text": words({tube: 1}), "mixed_hex": mixed, "target_hex": target_hex.lower(),
            "delta_e": round(de, 1), "reachable": True, "straight": True}
