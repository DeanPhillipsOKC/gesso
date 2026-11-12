"""The paints a lesson asks for, measured from the finish and kept to a few mixes (pipeline v2, design section 9).

    part_colors(finish, mask, k) -> [{"hex", "share", "x", "y"}], darkest first
    measure(finish, plan, owner, ...) -> the plan's paints and steps, measured, with tints marked and merged to the limit

Claude used to name a lesson's paints and guess where each one sits, and a hand-written plan has a paint per step:
16 to 22 paints, more than a beginner should mix (the limit is 10, docs/decisions.md 2026-11-12). Measured, the
same finish gives the same paints every run, and a part's dark, middle, and light come out in the order they're
painted. Then:
- a lighter or darker version of a part's main paint is that paint plus white (or plus the darkest tube): one
  puddle, lightened or darkened, the way a teacher has a beginner work. It keeps its own step and doesn't count;
- the rest are merged, closest first, until the lesson is down to `max_mixes`, preferring pairs in different
  parts. Two paints of one part merging means the two steps that used them become one;
- an accent (the lightest paint, or the only paint of its hue) is never merged.
Distances are mixing.delta_e (CIEDE2000) throughout.
"""

from __future__ import annotations

import itertools
import math
import re

import cv2
import numpy as np

import mixing

MAX_SAMPLE = 40_000  # pixels clustered per part: plenty for a few colors, and quick
ERROR_SAMPLE = 800  # pixels a part's color error is measured on
MAX_COLORS = 4  # most colors measured for one part
MAX_ERROR = 8.0  # with no steps yet, a part gets the fewest colors that leave its average error under this
REAL = 0.10  # a measured color is real when this share of the part is within MAX_ERROR of it, not an average
TINT = mixing.REACHABLE  # main paint plus white (or the dark tube) this close to a paint makes it a tint (or shade)
HUE_FAMILY = 40.0  # degrees of hue between paints of different families
CHROMA = 15.0  # a paint with less chroma than this (Lab) is a gray, of no hue family
KEEP_NAME = 3.0  # a paint that moved less than this keeps the name and used_for it was given
FAR_MERGE = 14.0  # a merge further apart than this lost a color some part needs (seen on all three fixtures)
FRACTIONS = [i / 40 for i in range(1, 40)]  # shares of white (or the dark tube) tried for a tint (or shade)


def part_colors(finish: np.ndarray, mask: np.ndarray, k: int) -> list[dict]:
    """The part's k main colors (k-means in Lab, fixed seed), darkest first, each with its share of the part and
    a spot (0-1) deep inside a patch of it."""
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return []
    L = cv2.cvtColor(cv2.GaussianBlur(finish, (0, 0), 1.0).astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)
    px = L[ys, xs]
    step = max(1, len(px) // MAX_SAMPLE)
    sample = np.ascontiguousarray(px[::step], np.float32)
    k = max(1, min(k, len(sample)))
    cv2.setRNGSeed(7)
    _, _, centers = cv2.kmeans(sample, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.2), 5,
                               cv2.KMEANS_PP_CENTERS)
    centers = centers[np.argsort(centers[:, 0], kind="stable")]
    label = np.argmin(((px[:, None, :] - centers[None]) ** 2).sum(2), axis=1)
    h, w = mask.shape
    out = []
    for i, c in enumerate(centers):
        rgb = cv2.cvtColor(c.reshape(1, 1, 3).astype(np.float32), cv2.COLOR_LAB2RGB)[0, 0]
        rgb = np.clip(np.round(rgb * 255), 0, 255).astype(int)
        here = np.zeros((h, w), np.uint8)
        here[ys[label == i], xs[label == i]] = 1
        if here.any():
            dist = cv2.distanceTransform(here, cv2.DIST_L2, 3)
            y, x = np.unravel_index(int(dist.argmax()), dist.shape)
        else:
            y, x = int(ys[0]), int(xs[0])
        out.append({"hex": "#%02x%02x%02x" % tuple(rgb), "share": round(float((label == i).mean()), 3),
                    "x": round(x / w, 3), "y": round(y / h, 3)})
    return out


# --- Measuring a part ---------------------------------------------------------------------------------------------


def _sample(finish: np.ndarray, mask: np.ndarray) -> list[tuple[int, int, int]]:
    """A fixed, evenly spread sample of the part's (lightly blurred) pixels, for measuring color error."""
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return []
    soft = cv2.GaussianBlur(finish, (0, 0), 1.0)
    pick = np.linspace(0, ys.size - 1, min(ERROR_SAMPLE, ys.size)).astype(int)
    return [tuple(int(v) for v in soft[ys[i], xs[i]]) for i in pick]


def _distances(sample: list, colors: list[dict]) -> np.ndarray:
    return np.array([[mixing.delta_e(px, c["hex"]) for c in colors] for px in sample])


def _keep_largest(colors: list[dict], k: int) -> list[dict]:
    """The k colors with the most of the part, darkest first; a dropped color's share goes to the nearest kept."""
    keep = sorted(sorted(range(len(colors)), key=lambda i: -colors[i]["share"])[:k])
    out = [dict(colors[i]) for i in keep]
    for i, c in enumerate(colors):
        if i not in keep:
            near = min(range(len(out)), key=lambda j: mixing.delta_e(c["hex"], out[j]["hex"]))
            out[near]["share"] = round(out[near]["share"] + c["share"], 3)
    return out


def part_paints(finish: np.ndarray, mask: np.ndarray, k: int | None = None) -> list[dict]:
    """A part's paints: k colors (as many as its steps name), or with no steps the fewest (1 to MAX_COLORS) that
    leave its average error under MAX_ERROR. A part with one paint must get a color it really has: one color
    from k-means is the part's average, and where the outline caught a little of a neighbor (the chickadee's
    white cheek with some of the black cap) that average is a gray on neither. Then the part is measured with
    more colors and the largest is kept."""
    sample = _sample(finish, mask)
    if not sample:
        return []
    if k is None:
        for k in range(1, MAX_COLORS + 1):
            colors = part_colors(finish, mask, k)
            if _distances(sample, colors).min(1).mean() < MAX_ERROR:
                break
    else:
        colors = part_colors(finish, mask, k)
    if k == 1:  # with two or more colors each is the middle of its own patch; with one it's the part's average
        for more in range(2, MAX_COLORS + 1):
            if all_real(sample, colors):
                break
            colors = _keep_largest(part_colors(finish, mask, more), 1)
    return colors


def all_real(sample: list, colors: list[dict]) -> bool:
    """True when every color is one the part really has: at least REAL of the pixels nearest it are within
    MAX_ERROR of it. An average of two colors the part has (gray from black and white) has almost none."""
    d = _distances(sample, colors)
    nearest = d.argmin(1)
    for j in range(len(colors)):
        mine = d[nearest == j, j]
        if mine.size and (mine < MAX_ERROR).mean() < REAL:
            return False
    return True


# --- Tints, shades, accents -----------------------------------------------------------------------------------------


def _lab(h: str) -> tuple[float, float, float]:
    return mixing._lab(mixing.hex_rgb(h))


def lightness(h: str) -> float:
    return _lab(h)[0]


def _hue(h: str) -> float | None:
    _, a, b = _lab(h)
    return math.degrees(math.atan2(b, a)) % 360 if math.hypot(a, b) >= CHROMA else None


def mixed_with(main: str, tube: tuple[int, int, int], target: str) -> float:
    """How close main plus some of `tube` gets to target (Delta E, by Mixbox), over the shares in FRACTIONS."""
    m = mixing.hex_rgb(main)
    return min(mixing.delta_e(target, mixing._mix_rgb([(m, 1 - f), (tube, f)])) for f in FRACTIONS)


def accents(paints: list[dict]) -> set[str]:
    """The lightest paint, and any paint with real chroma that's the only one of its hue family (more than
    HUE_FAMILY degrees from every other paint with real chroma): a sun, a sparkle, an eye light, a red hull."""
    if not paints:
        return set()
    out = {max(paints, key=lambda p: (lightness(p["hex"]), p["id"]))["id"]}
    hues = {p["id"]: _hue(p["hex"]) for p in paints}
    for p in paints:
        h = hues[p["id"]]
        if h is None:
            continue
        others = [hues[q["id"]] for q in paints if q["id"] != p["id"] and hues[q["id"]] is not None]
        if all(min(abs(h - o), 360 - abs(h - o)) > HUE_FAMILY for o in others):
            out.add(p["id"])
    return out


# --- The whole lesson -----------------------------------------------------------------------------------------------


def _weight(p: dict) -> float:
    return sum(p["shares"].values())


def _merged_hex(a: dict, b: dict) -> str:
    """The two paints' colors averaged in Lab, weighted by how much of the picture each covers."""
    wa, wb = _weight(a), _weight(b)
    lab = [(np.array(cv2.cvtColor(np.array([[mixing.hex_rgb(p["hex"])]], np.float32) / 255.0, cv2.COLOR_RGB2LAB)[0, 0]))
           for p in (a, b)]
    mean = (lab[0] * wa + lab[1] * wb) / max(wa + wb, 1e-9)
    rgb = cv2.cvtColor(mean.reshape(1, 1, 3).astype(np.float32), cv2.COLOR_LAB2RGB)[0, 0]
    return mixing.rgb_hex(np.clip(np.round(rgb * 255), 0, 255).astype(int))


def _main_of(paints: list[dict], part: str) -> dict | None:
    mine = [p for p in paints if part in p["shares"]]
    return max(mine, key=lambda p: (p["shares"][part], -lightness(p["hex"]), p["id"])) if mine else None


def mark_tints(paints: list[dict], part_order: list[str], white: tuple, dark: tuple, dark_name: str) -> None:
    """Set `of`/`plus` on every paint that is its part's main paint plus white (a tint) or plus the darkest tube
    (a shade), within TINT. A part's main paint (the one covering most of it) is never a tint."""
    mains = {pid: _main_of(paints, pid) for pid in part_order}
    main_ids = {m["id"] for m in mains.values() if m}
    for p in paints:
        p.pop("of", None)
        p.pop("plus", None)
        if p["id"] in main_ids:
            continue
        for pid in sorted(p["shares"], key=part_order.index):
            m = mains[pid]
            if lightness(p["hex"]) >= lightness(m["hex"]):
                tube, name = white, "white"
            else:
                tube, name = dark, dark_name
            if mixed_with(m["hex"], tube, p["hex"]) <= TINT:
                p["of"], p["plus"] = m["id"], name
                break


def _steps(stages: list[dict]) -> list[dict]:
    return [s for st in stages for s in st["steps"]]


def _merge_steps(stages: list[dict], part: str, a: str, b: str) -> dict | None:
    """When paints a and b of one part merge, the two steps of that part that used them become one: the first
    keeps its id, name, and place, and takes the other's paints. None when one step already uses both."""
    mine = [s for s in _steps(stages) if s["part"] == part]
    sa = [s for s in mine if a in s["paints"]]
    sb = [s for s in mine if b in s["paints"]]
    if not sa or not sb or set(map(id, sa)) & set(map(id, sb)):
        return None
    first, second = sorted([sa[0], sb[0]], key=lambda s: mine.index(s))
    for c in second["paints"]:
        if c not in first["paints"]:
            first["paints"].append(c)
    if second is mine[-1] and first.get("show") == "flat":
        first["show"] = "full"  # the coat is now the part's last step, and a last step finishes the part
    for st in stages:
        st["steps"] = [s for s in st["steps"] if s is not second]
    return {"kept": first["id"], "dropped": second["id"], "part": part}


def limit(paints: list[dict], stages: list[dict], max_mixes: int | None, part_order: list[str],
          white: tuple, dark: tuple, dark_name: str) -> tuple[list[dict], list[dict]]:
    """Merge base paints (not tints or shades), closest first, until there are at most max_mixes. Pairs in
    different parts go first; two paints of one part merge only when no other pair is left, and then their steps
    become one. Accents are never merged. Changes paints and stages in place; returns (merges, step merges)."""
    merges, step_merges = [], []
    while True:
        mark_tints(paints, part_order, white, dark, dark_name)
        bases = [p for p in paints if not p.get("of")]
        if max_mixes is None or len(bases) <= max_mixes:
            break
        keep = accents(paints)
        pairs = [(a, b) for a, b in itertools.combinations(bases, 2) if a["id"] not in keep and b["id"] not in keep]
        if not pairs:
            break
        cross = [(a, b) for a, b in pairs if not set(a["shares"]) & set(b["shares"])]
        a, b = min(cross or pairs, key=lambda ab: (mixing.delta_e(ab[0]["hex"], ab[1]["hex"]), ab[0]["id"], ab[1]["id"]))
        if (_weight(b), b["id"]) > (_weight(a), a["id"]):
            a, b = b, a  # the paint covering more of the picture keeps its id and spot
        record = {"into": a["id"], "parts": sorted(b["shares"], key=part_order.index), "was": [o for _, o in b["origins"]],
                  "hex": b["hex"], "delta_e": round(mixing.delta_e(a["hex"], b["hex"]), 1), "same_part": not cross}
        for part in sorted(set(a["shares"]) & set(b["shares"]), key=part_order.index):
            sm = _merge_steps(stages, part, a["id"], b["id"])
            if sm:
                step_merges.append(sm)
        a["hex"] = _merged_hex(a, b)
        for pid, share in b["shares"].items():
            a["shares"][pid] = a["shares"].get(pid, 0.0) + share
        a["origins"] += b["origins"]
        a["absorbed"] = a.get("absorbed", []) + [b["id"]] + b.get("absorbed", [])
        paints.remove(b)
        for s in _steps(stages):
            s["paints"] = list(dict.fromkeys(a["id"] if c == b["id"] else c for c in s["paints"]))
        merges.append(record)
    return merges, step_merges


def _has_hex(paint: dict) -> bool:
    return bool(re.match(r"^#[0-9a-fA-F]{6}$", paint.get("hex") or ""))


def measure(finish: np.ndarray, plan: dict, owner: np.ndarray, max_mixes: int | None,
            white: tuple = (255, 255, 255), dark: tuple = (20, 20, 22), dark_name: str = "black") -> dict:
    """The plan's paints measured from the finish, tints and shades marked, merged to max_mixes, with ids
    <part id>-<n> darkest first, and its steps pointed at them. A part gets as many colors as its steps name (each
    named paint goes to the measured color nearest the hex it had), or with no steps the fewest that fit.
    Returns {"paints", "stages", "merges", "step_merges", "accents", "shares", "kept_names"}; `plan` isn't changed."""
    parts = plan["parts"]
    order = [p["id"] for p in parts]
    stages = [dict(st, steps=[dict(s, paints=list(s.get("paints") or [])) for s in st.get("steps") or []])
              for st in plan.get("stages") or []]
    old = {c["id"]: c for c in plan.get("paints") or [] if c.get("id")}
    paints: list[dict] = []
    rename: dict[tuple[str, str], str] = {}  # (part, a step's paint id) -> the measured paint's id
    for k, part in enumerate(parts):
        pid = part["id"]
        mask = owner == k
        area = float(mask.mean())
        named = list(dict.fromkeys(c for s in _steps(stages) if s["part"] == pid for c in s["paints"]))
        colors = part_paints(finish, mask, len(named) if named else None)
        mine = [{"id": f"{pid}-{n + 1}", "hex": c["hex"], "sample_x": c["x"], "sample_y": c["y"],
                 "shares": {pid: c["share"] * area}, "origins": []} for n, c in enumerate(colors)]
        if named and mine:
            def cost(perm):
                return sum(mixing.delta_e(old[n]["hex"], mine[j]["hex"]) for n, j in zip(named, perm)
                           if n in old and _has_hex(old[n]))
            best = min(itertools.permutations(range(len(mine)), len(named)), key=lambda perm: (cost(perm), perm))
            for n, j in zip(named, best):
                rename[(pid, n)] = mine[j]["id"]
                if n in old:
                    mine[j]["origins"].append((pid, n))
        elif mine:  # no steps yet: a paint already listed for this part is matched to its nearest measured color
            for o in old.values():
                if pid in (o.get("parts") or []) and _has_hex(o):
                    near = min(mine, key=lambda m: mixing.delta_e(o["hex"], m["hex"]))
                    near["origins"].append((pid, o["id"]))
        paints += mine
    for s in _steps(stages):
        s["paints"] = list(dict.fromkeys(rename.get((s["part"], c), c) for c in s["paints"]))

    merges, step_merges = limit(paints, stages, max_mixes, order, white, dark, dark_name)

    def home(p):  # a shared paint belongs to the part it covers most of
        return max(p["shares"], key=lambda q: (p["shares"][q], -order.index(q)))

    final: dict[str, str] = {}  # ids: <home part>-<n>, darkest first
    for pid in order:
        for n, p in enumerate(sorted((p for p in paints if home(p) == pid), key=lambda p: (lightness(p["hex"]), p["id"]))):
            for old_id in [p["id"]] + p.get("absorbed", []):
                final[old_id] = f"{pid}-{n + 1}"
    for s in _steps(stages):
        s["paints"] = list(dict.fromkeys(final.get(c, c) for c in s["paints"]))
    stages = [st for st in stages if st["steps"]]
    for m in merges:
        m["into"] = final[m["into"]]
    for p in paints:
        if p.get("of"):
            p["of"] = final[p["of"]]
    for p in paints:
        p["id"] = final[p["id"]]

    # a paint that moved less than KEEP_NAME from a paint it came from keeps that paint's name and used_for: one
    # from the part it mostly covers first, then the nearest
    claims = sorted((part != home(p), mixing.delta_e(p["hex"], old[o]["hex"]), p["id"], o)
                    for p in paints for part, o in p["origins"] if _has_hex(old[o]))
    kept_names: dict[str, str] = {}
    for _, de, pid, o in claims:
        if de < KEEP_NAME and pid not in kept_names and o not in kept_names.values():
            kept_names[pid] = o

    used: dict[str, list[str]] = {}
    for s in _steps(stages):
        for c in s["paints"]:
            if s["part"] not in used.setdefault(c, []):
                used[c].append(s["part"])
    out = []
    for p in sorted(paints, key=lambda p: (order.index(home(p)), p["id"])):
        entry = {"id": p["id"]}
        if p["id"] in kept_names:
            o = old[kept_names[p["id"]]]
            entry.update({k: o[k] for k in ("name", "used_for") if o.get(k)})
        entry["hex"] = p["hex"]
        if p.get("of"):
            entry["of"], entry["plus"] = p["of"], p["plus"]
        entry["sample_x"], entry["sample_y"] = p["sample_x"], p["sample_y"]
        entry["parts"] = sorted(used.get(p["id"]) or list(p["shares"]), key=order.index)
        out.append(entry)
    shares = {p["id"]: {q: round(v, 4) for q, v in sorted(p["shares"].items(), key=lambda kv: order.index(kv[0]))}
              for p in paints}
    return {"paints": out, "stages": stages, "merges": merges, "step_merges": step_merges,
            "accents": sorted(accents(out)), "shares": shares, "kept_names": kept_names}


def base_mixes(paints: list[dict]) -> list[str]:
    """The paints a beginner has to mix: every paint that isn't a tint or shade of another (no `of`)."""
    return [p["id"] for p in paints if not p.get("of")]


def swatch_sheet(finish: np.ndarray, parts: list[dict], paints: list[dict], shares: dict[str, dict]) -> np.ndarray:
    """The finish beside one row per part: each of its paints as a swatch with its id, its share of the part,
    and "+ white" (or the dark tube) under a tint or shade. A paint shared by parts shows in each of their rows."""
    row_h, sw, pad, side = 46, 190, 8, 640
    h, w = finish.shape[:2]
    left = cv2.resize(finish, (side, int(side * h / w)), interpolation=cv2.INTER_AREA)
    rows = []
    for part in parts:
        mine = [p for p in paints if part["id"] in shares.get(p["id"], {})]
        total = sum(shares[p["id"]][part["id"]] for p in mine) or 1.0
        rows.append((part.get("name") or part["id"], [(p, shares[p["id"]][part["id"]] / total) for p in mine]))
    width = 190 + max([len(r[1]) for r in rows] + [1]) * (sw + pad)
    right = np.full((max(len(rows) * row_h + pad, left.shape[0]), width, 3), 255, np.uint8)
    for i, (label, mine) in enumerate(rows):
        y = pad + i * row_h
        cv2.putText(right, label[:24], (6, y + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1, cv2.LINE_AA)
        for j, (p, share) in enumerate(mine):
            x = 190 + j * (sw + pad)
            rgb = mixing.hex_rgb(p["hex"])
            cv2.rectangle(right, (x, y), (x + 38, y + row_h - 8), rgb, -1)
            cv2.rectangle(right, (x, y), (x + 38, y + row_h - 8), (120, 120, 120), 1)
            under = f"= {p['of']} + {p['plus']}" if p.get("of") else "mix"
            for n, text in enumerate((p["id"], f"{share:.0%}  {under}")):
                cv2.putText(right, text[:28],(x + 44, y + 15 + 16 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (20, 20, 20), 1,
                            cv2.LINE_AA)
    canvas = np.full((max(left.shape[0], right.shape[0]), side + 10 + width, 3), 255, np.uint8)
    canvas[:left.shape[0], :side] = left
    canvas[:right.shape[0], side + 10:] = right
    return canvas


