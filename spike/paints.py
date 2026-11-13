"""The paints a lesson asks for, measured from the finish and kept to a few mixes (pipeline v2, design section 9).

    part_colors(finish, mask, k) -> [{"hex", "share", "x", "y"}], darkest first
    measure(finish, plan, owner, ...) -> the plan's paints, measured, with tints marked and merged toward the limit
    add(finish, plan, owner, part, ...) -> the plan's paints with one more measured color for one part

Claude used to name a lesson's paints and guess where each one sits, and a hand-written plan has a paint per step:
16 to 22 paints, more than a beginner should mix (the limit is 10, docs/decisions.md 2026-11-12). Measured, the
same finish gives the same paints every run, and a part's dark, middle, and light come out in the order they're
painted. Then:
- a lighter or darker version of a part's main paint is that paint plus white (or plus the darkest tube): one
  puddle, lightened or darkened, the way a teacher has a beginner work. It keeps its own step and doesn't count;
- the rest are merged, closest first, toward `max_mixes`, preferring pairs in different parts, but never two
  paints more than MAX_MERGE apart: a lesson ends above the target rather than lose a color the painter can see;
- an accent (the lightest paint, or the only paint of its hue) is never merged.
Distances are mixing.delta_e (CIEDE2000) throughout.

A paint is measured in every part its `parts` lists: a part listed by k paints is clustered into k colors, each
paint takes one (the nearest by an optimal match), and a paint in several parts is their colors averaged in Lab,
weighted by how much of the picture each covers. The first measurement (the plan has no paints yet, so no steps
are needed) gives each part the fewest colors that fit and merges toward the target. Every later run keeps what
the plan already has (2026-11-13: re-merging from scratch on every run renamed paints three times in one run, and
merged away a paint a step had just been given): it re-measures, keeps every id, never merges away a paint a step
uses or one `add` made, and drops only a paint whose parts are all gone.
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
SAME = 1.0  # a re-measured paint that moved less than this keeps its hex and spot exactly: a rerun changes nothing
MATCH_EXACT = 7  # paints matched to a part's colors by trying every order up to this many; nearest first above it
MAX_MERGE = 12.0  # paints further apart than this are never merged: it loses a color the painter can see
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
                    "x": round(float(x / w), 3), "y": round(float(y / h), 3)})
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


def _mean_hex(colors: list[tuple[str, float]]) -> str:
    """Colors averaged in Lab, weighted (by how much of the picture each covers)."""
    lab = [np.array(cv2.cvtColor(np.array([[mixing.hex_rgb(h)]], np.float32) / 255.0, cv2.COLOR_RGB2LAB)[0, 0])
           for h, _ in colors]
    weights = [w for _, w in colors]
    mean = sum(x * w for x, w in zip(lab, weights)) / max(sum(weights), 1e-9)
    rgb = cv2.cvtColor(mean.reshape(1, 1, 3).astype(np.float32), cv2.COLOR_LAB2RGB)[0, 0]
    return mixing.rgb_hex(np.clip(np.round(rgb * 255), 0, 255).astype(int))


def _merged_hex(a: dict, b: dict) -> str:
    """The two paints' colors averaged in Lab, weighted by how much of the picture each covers."""
    return _mean_hex([(a["hex"], _weight(a)), (b["hex"], _weight(b))])


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


def mergeable(bases: list[dict], keep: set[str], fixed: set[str] = frozenset(),
              held: set[str] = frozenset()) -> list[tuple[dict, dict]]:
    """Pairs of base paints that may still merge: neither is an accent (`keep`) or a paint `add` made (`held`), at
    most one is used by a step (`fixed`: it takes the other in; a paint a step uses is never merged away), and
    they're at most MAX_MERGE apart."""
    return [(a, b) for a, b in itertools.combinations(bases, 2)
            if not {a["id"], b["id"]} & (set(keep) | set(held)) and not {a["id"], b["id"]} <= set(fixed)
            and mixing.delta_e(a["hex"], b["hex"]) <= MAX_MERGE]


def over_target(paints: list[dict], fixed: set[str] = frozenset(), held: set[str] = frozenset()) -> list[dict]:
    """Why each base paint is still its own mix: its nearest other base paint and how far it is, nearest first, and
    whether it's an accent, used by a step, or made by `add`."""
    bases = [p for p in paints if not p.get("of")]
    keep = accents(paints)
    out = []
    for p in bases:
        others = [q for q in bases if q is not p]
        if not others:
            continue
        near = min(others, key=lambda q: (mixing.delta_e(p["hex"], q["hex"]), q["id"]))
        out.append({"id": p["id"], "nearest": near["id"], "delta_e": round(mixing.delta_e(p["hex"], near["hex"]), 1),
                    "accent": p["id"] in keep, "used": p["id"] in fixed, "added": p["id"] in held})
    return sorted(out, key=lambda o: (o["delta_e"], o["id"]))


def limit(paints: list[dict], max_mixes: int | None, part_order: list[str], white: tuple, dark: tuple,
          dark_name: str, fixed: set[str] = frozenset(), held: set[str] = frozenset(), settle=None) -> list[dict]:
    """Merge base paints (not tints or shades), closest first, toward max_mixes. Pairs in different parts go
    first; two paints of one part merge only when no other pair is left. Accents are never merged, and neither are
    two paints more than MAX_MERGE apart: that loses a color the painter can see, so a lesson may end above
    max_mixes. A paint a step uses (`fixed`) is never merged away, and a paint `add` made (`held`) never merges.
    The merged paint keeps the id of the one covering more (or the one a step uses), and is measured again by
    `settle(paints)` when given (else the two colors averaged). Changes paints in place; returns the merges."""
    merges = []
    while True:
        mark_tints(paints, part_order, white, dark, dark_name)
        bases = [p for p in paints if not p.get("of")]
        if max_mixes is None or len(bases) <= max_mixes:
            break
        pairs = mergeable(bases, accents(paints), fixed, held)
        if not pairs:
            break
        cross = [(a, b) for a, b in pairs if not set(a["shares"]) & set(b["shares"])]
        a, b = min(cross or pairs, key=lambda ab: (mixing.delta_e(ab[0]["hex"], ab[1]["hex"]), ab[0]["id"], ab[1]["id"]))
        if b["id"] in fixed or (a["id"] not in fixed and (_weight(b), b["id"]) > (_weight(a), a["id"])):
            a, b = b, a  # the paint a step uses, or else the one covering more of the picture, keeps its id
        merges.append({"into": a["id"], "id": b["id"], "parts": sorted(b["shares"], key=part_order.index),
                       "hex": b["hex"], "delta_e": round(mixing.delta_e(a["hex"], b["hex"]), 1), "same_part": not cross})
        a["hex"] = _merged_hex(a, b)
        for pid, share in b["shares"].items():
            a["shares"][pid] = a["shares"].get(pid, 0.0) + share
        if "members" in a:
            a["members"] = [q for q in part_order if q in a["members"] or q in b["members"]]
        a["absorbed"] = a.get("absorbed", []) + [b["id"]] + b.get("absorbed", [])
        paints.remove(b)
        if settle:
            settle(paints)
    return merges


def _has_hex(paint: dict) -> bool:
    return bool(re.match(r"^#[0-9a-fA-F]{6}$", paint.get("hex") or ""))


def _match(have: list[str], colors: list[str]) -> list[int]:
    """Which of `colors` each of `have` takes, one each (len(have) <= len(colors)), for the least total Delta E.
    Every order is tried up to MATCH_EXACT; above that, the closest pairs first."""
    cost = [[mixing.delta_e(h, c) for c in colors] for h in have]
    if len(colors) <= MATCH_EXACT:
        return list(min(itertools.permutations(range(len(colors)), len(have)),
                        key=lambda perm: (sum(cost[i][j] for i, j in enumerate(perm)), perm)))
    out, taken = [None] * len(have), set()
    for d, i, j in sorted((cost[i][j], i, j) for i in range(len(have)) for j in range(len(colors))):
        if out[i] is None and j not in taken:
            out[i] = j
            taken.add(j)
    return out


class _Measure:
    """Each part's colors, measured once per number of colors, and a lesson's paints measured from them."""

    def __init__(self, finish: np.ndarray, plan: dict, owner: np.ndarray):
        self.finish, self.owner = finish, owner
        self.order = [p["id"] for p in plan["parts"]]
        self.area = {pid: float((owner == k).mean()) for k, pid in enumerate(self.order)}
        self.cache: dict[tuple[str, int | None], list[dict]] = {}

    def colors(self, pid: str, k: int | None = None) -> list[dict]:
        """The part's k colors (part_paints), or with k None the fewest that fit."""
        if (pid, k) not in self.cache:
            self.cache[(pid, k)] = part_paints(self.finish, self.owner == self.order.index(pid), k)
        return self.cache[(pid, k)]

    def settle(self, paints: list[dict]) -> None:
        """Measure every paint from the parts it's in (`members`): a part in k paints is clustered into k colors and
        each paint takes one (matched to its current hex); a paint in several parts is their colors averaged,
        weighted by how much of the picture each covers. Sets hex, shares, and the sample spot (in the part it
        covers most of)."""
        got: dict[int, dict[str, dict]] = {id(p): {} for p in paints}
        for pid in self.order:
            mine = [p for p in paints if pid in p["members"]]
            colors = self.colors(pid, len(mine)) if mine else []
            if len(colors) < len(mine):  # the part has no pixels left: its paints keep what they had
                continue
            for p, j in zip(mine, _match([p["hex"] for p in mine], [c["hex"] for c in colors])):
                got[id(p)][pid] = colors[j]
        for p in paints:
            here = got[id(p)]
            if not here:
                p["shares"] = {pid: 0.0 for pid in p["members"]}
                continue
            p["shares"] = {pid: c["share"] * self.area[pid] for pid, c in here.items()}
            p["hex"] = here[next(iter(here))]["hex"] if len(here) == 1 else \
                _mean_hex([(c["hex"], p["shares"][pid]) for pid, c in here.items()])
            spot = here[max(here, key=lambda q: (p["shares"][q], -self.order.index(q)))]
            p["sample_x"], p["sample_y"] = spot["x"], spot["y"]


def _number(pid: str) -> tuple[str, int]:
    head, _, tail = pid.rpartition("-")
    return (head, int(tail)) if tail.isdigit() else (pid, 0)


def _next_id(part: str, taken: set[str]) -> str:
    n = 1
    while f"{part}-{n}" in taken:
        n += 1
    return f"{part}-{n}"


def _used(plan: dict) -> dict[str, list[str]]:
    """Each paint id a step names, and the parts those steps paint."""
    out: dict[str, list[str]] = {}
    for st in plan.get("stages") or []:
        for s in st.get("steps") or []:
            for c in s.get("paints") or []:
                if s.get("part") not in out.setdefault(c, []):
                    out[c].append(s.get("part"))
    return out


def _steps_using(plan: dict, paint_id: str) -> list[str]:
    return [s["id"] for st in plan.get("stages") or [] for s in st.get("steps") or [] if paint_id in (s.get("paints") or [])]


def _existing(plan: dict, order: list[str]) -> tuple[list[dict], list[dict]]:
    """The plan's paints as records to measure again (in every part their `parts` or a step puts them in), and the
    paints whose parts are all gone, with the steps that still name them."""
    used = _used(plan)
    records, removed = [], []
    for c in plan.get("paints") or []:
        if not c.get("id") or not _has_hex(c):
            continue
        listed = list(c.get("parts") or []) + used.get(c["id"], [])
        members = [q for q in order if q in listed]
        if not members:
            removed.append({"id": c["id"], "parts": list(dict.fromkeys(listed)), "steps": _steps_using(plan, c["id"])})
            continue
        records.append({"id": c["id"], "members": members, "hex": c["hex"], "old": c, "shares": {},
                        "sample_x": c.get("sample_x"), "sample_y": c.get("sample_y")})
    return records, removed


def _entries(records: list[dict], plan: dict, order: list[str], white, dark, dark_name: str) -> tuple[list[dict], dict]:
    """The plan's paints from measured records: a paint that barely moved (SAME) keeps its hex and spot exactly, and
    one that moved less than KEEP_NAME keeps its name and used_for. Returns (paints, what changed)."""
    changed, kept, kept_names = [], [], {}
    for r in records:
        o = r.get("old")
        if o is None:
            continue
        de = mixing.delta_e(o["hex"], r["hex"])
        if de < SAME:
            r["hex"], r["sample_x"], r["sample_y"] = o["hex"], o.get("sample_x", r["sample_x"]), o.get("sample_y", r["sample_y"])
            kept.append(r["id"])
        else:
            changed.append({"id": r["id"], "from": o["hex"], "to": r["hex"], "delta_e": round(de, 1),
                            "name_kept": de < KEEP_NAME and bool(o.get("name"))})
        if de < KEEP_NAME and (o.get("name") or o.get("used_for")):
            kept_names[r["id"]] = r["id"]
    mark_tints(records, order, white, dark, dark_name)
    used = _used(plan)

    def home(r):  # a shared paint belongs to the part it covers most of
        return max(r["members"], key=lambda q: (r["shares"].get(q, 0.0), -order.index(q)))

    out = []
    for r in sorted(records, key=lambda r: (order.index(home(r)), _number(r["id"]))):
        entry = {"id": r["id"]}
        if r["id"] in kept_names:
            entry.update({k: r["old"][k] for k in ("name", "used_for") if r["old"].get(k)})
        entry["hex"] = r["hex"]
        if r.get("of"):
            entry["of"], entry["plus"] = r["of"], r["plus"]
        entry["sample_x"], entry["sample_y"] = r["sample_x"], r["sample_y"]
        entry["parts"] = [q for q in order if q in r["members"] or q in used.get(r["id"], [])]
        if r.get("added") or (r.get("old") or {}).get("added"):
            entry["added"] = True
        out.append(entry)
    return out, {"changed": changed, "kept": kept, "kept_names": kept_names}


def measure(finish: np.ndarray, plan: dict, owner: np.ndarray, max_mixes: int | None,
            white: tuple = (255, 255, 255), dark: tuple = (20, 20, 22), dark_name: str = "black") -> dict:
    """The plan's paints, measured from the finish, tints and shades marked, merged toward max_mixes. `plan` isn't
    changed, and neither are its steps: a step's paints are Claude's to choose.

    First measurement (the plan has no paints): each part gets the fewest colors (1 to MAX_COLORS) that leave its
    average error under MAX_ERROR, and the paints merge toward max_mixes; ids are <part id>-<n>, darkest first. No
    steps are needed.

    Again (the plan has paints, and `outline` changed): every paint is measured again in its parts and keeps its id,
    and its name and used_for when it moved less than KEEP_NAME. A part with no paint yet gets its fewest colors,
    with the next free ids. Only paints no step uses (and not made by `add`) may merge; a paint whose parts are all
    gone is removed, and the steps that name it are listed.

    Returns {"paints", "merges", "accents", "shares", "kept_names", "over_target", "first", "changed", "kept",
    "new", "removed"}."""
    m = _Measure(finish, plan, owner)
    order = m.order
    records, removed = _existing(plan, order)
    first = not records and not removed
    used = set(_used(plan))
    held = {r["id"] for r in records if r["old"].get("added")}
    fixed = {r["id"] for r in records} & used
    taken = {r["id"] for r in records} | {x["id"] for x in removed}
    new = []
    for pid in order:
        if any(pid in r["members"] for r in records):
            continue
        for c in m.colors(pid):
            rid = _next_id(pid, taken)
            taken.add(rid)
            records.append({"id": rid, "members": [pid], "hex": c["hex"], "shares": {}, "sample_x": c["x"],
                            "sample_y": c["y"]})
            new.append(rid)
    m.settle(records)
    merges = limit(records, max_mixes, order, white, dark, dark_name, fixed, held, m.settle)
    if first:  # ids <home part>-<n>, darkest first
        def home(r):
            return max(r["members"], key=lambda q: (r["shares"].get(q, 0.0), -order.index(q)))
        final = {}
        for pid in order:
            mine = sorted((r for r in records if home(r) == pid), key=lambda r: (lightness(r["hex"]), r["id"]))
            for n, r in enumerate(mine):
                for was in [r["id"]] + r.get("absorbed", []):
                    final[was] = f"{pid}-{n + 1}"
        for r in records:
            r["id"] = final[r["id"]]
        for x in merges:  # a first measurement's merges, by the paint each color ended in
            x["into"] = final[x["into"]]
            x.pop("id")
        new = [r["id"] for r in records]
    else:
        new = [i for i in new if any(r["id"] == i for r in records)]
    paints, what = _entries(records, plan, order, white, dark, dark_name)
    shares = {r["id"]: {q: round(v, 4) for q, v in sorted(r["shares"].items(), key=lambda kv: order.index(kv[0]))}
              for r in records}
    over = (over_target(paints, fixed, held) if max_mixes is not None and len(base_mixes(paints)) > max_mixes else [])
    return {"paints": paints, "merges": merges, "accents": sorted(accents(paints)), "shares": shares,
            "kept_names": what["kept_names"], "over_target": over, "first": first, "changed": what["changed"],
            "kept": what["kept"], "new": new, "removed": removed}


def add(finish: np.ndarray, plan: dict, owner: np.ndarray, part: str, max_mixes: int | None,
        white: tuple = (255, 255, 255), dark: tuple = (20, 20, 22), dark_name: str = "black") -> dict:
    """One more measured color for one part: the part is clustered into one more color than it has paints, its
    paints keep the clusters nearest them (a paint only this part has moves to its cluster), and the color left
    over is a new paint with the next free id and "added": true, so no later run merges it. Nothing is merged and
    no other part is touched. When the left-over color is within TINT of one of the part's paints, the part has no
    other distinct color: nothing is added, and `problems` says so.

    Returns measure()'s keys (with "added": the new paint's id or None) and "problems"."""
    m = _Measure(finish, plan, owner)
    order = m.order
    if part not in order:
        raise ValueError(f"{part!r} isn't one of the plan's parts ({', '.join(order)})")
    records, removed = _existing(plan, order)
    mine = [r for r in records if part in r["members"]]
    colors = m.colors(part, len(mine) + 1)
    problems, new_id = [], None
    for r in records:  # nothing else is measured again: shares only, for tints and the swatch sheet
        r["shares"] = {q: 0.0 for q in r["members"]}
    for q in order:
        here = [r for r in records if q in r["members"]]
        if q == part or not here:
            continue
        cs = m.colors(q, len(here))
        if len(cs) >= len(here):
            for r, j in zip(here, _match([r["hex"] for r in here], [c["hex"] for c in cs])):
                r["shares"][q] = cs[j]["share"] * m.area[q]
    if len(colors) < len(mine) + 1:
        problems.append(f"{part}: has no pixels to measure. Check its outline (run outline) before adding a paint.")
    else:
        took = _match([r["hex"] for r in mine], [c["hex"] for c in colors])
        j_left = next(j for j in range(len(colors)) if j not in took)
        left = colors[j_left]
        near = min(mine, key=lambda r: mixing.delta_e(left["hex"], r["hex"])) if mine else None
        de = mixing.delta_e(left["hex"], near["hex"]) if near else None
        sample = _sample(m.finish, m.owner == order.index(part))
        d = _distances(sample, colors)
        theirs = d[d.argmin(1) == j_left, j_left]
        if near is not None and de <= TINT:
            problems.append(f"{part}: its pixels don't hold another distinct color: the next one measured, "
                            f"{left['hex']}, is only Delta E {de:.1f} from {near['id']} ({near['hex']}). Nothing was "
                            "added. Split the pass by place instead, or let one step carry both.")
        elif not theirs.size or (theirs < MAX_ERROR).mean() < REAL:
            problems.append(f"{part}: its pixels don't hold another distinct color: the next one measured, "
                            f"{left['hex']}, is a blend along its edges, not a color it has. Nothing was added.")
        else:
            for r, j in zip(mine, took):
                r["shares"][part] = colors[j]["share"] * m.area[part]
                if r["members"] == [part]:  # only this part's paints follow its new colors
                    r["hex"], r["sample_x"], r["sample_y"] = colors[j]["hex"], colors[j]["x"], colors[j]["y"]
            new_id = _next_id(part, {r["id"] for r in records} | {x["id"] for x in removed})
            records.append({"id": new_id, "members": [part], "hex": left["hex"], "added": True,
                            "shares": {part: left["share"] * m.area[part]}, "sample_x": left["x"], "sample_y": left["y"]})
    if new_id is None:  # nothing changes: the plan's paints as they are
        for r in records:
            r["hex"], r["sample_x"], r["sample_y"] = r["old"]["hex"], r["old"].get("sample_x"), r["old"].get("sample_y")
    paints, what = _entries(records, plan, order, white, dark, dark_name)
    if removed:  # add touches no other part, so a paint whose part is gone stays until paints runs again
        paints += [c for c in plan.get("paints") or [] if c.get("id") in {x["id"] for x in removed}]
    used = set(_used(plan))
    held = {p["id"] for p in paints if p.get("added")}
    over = (over_target(paints, used & {p["id"] for p in paints}, held)
            if max_mixes is not None and len(base_mixes(paints)) > max_mixes else [])
    shares = {r["id"]: {q: round(v, 4) for q, v in r["shares"].items()} for r in records}
    return {"paints": paints, "merges": [], "accents": sorted(accents(paints)), "shares": shares,
            "kept_names": what["kept_names"], "over_target": over, "first": False, "changed": what["changed"],
            "kept": what["kept"], "new": [new_id] if new_id else [], "removed": [], "added": new_id,
            "problems": problems}


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


