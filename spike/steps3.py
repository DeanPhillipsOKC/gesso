"""Paints, step pictures and shapes of a version 3 lesson, all from its chain (docs/design/pipeline-v3.md,
sections 7 to 9).

    fit(plan, us, ch)        -> each paint's color in this painting, fitted to what the units changed
    build(plan, finish, ch)  -> the step pictures, where each step lays paint, and the checks' numbers
    owner_from(ch)           -> which unit each pixel of the finish belongs to
    as_v2(plan, ...)         -> the plan in the shape the later tools read (a part a unit)

Pipeline v2 measured paints inside outlines and cut each step from the finish (removed in #238). Here the chain holds
a picture for the end of every unit (P[n]) and what the unit adds (D[n]): the plan names the paints and each is
fitted to the changes; a unit's last step is P[n] exactly; an earlier step of the unit shows the pixels nearest
its own paints. No outline model runs: a unit's shape is the core of what its render changed.

The teaching pictures, the drafted lines, the recipes and the page were written for v2, and read the plan through
`as_v2` and the shapes through `owner_from` (as the spikes ran them, #210 and #214).
"""

from __future__ import annotations

import cv2
import numpy as np

import build_steps as bs
import erase3
import from_finish as ff
import plan3

REFIT = 2  # rounds of "each pixel to its nearest paint, each paint to the middle of its pixels"
REACH = 30.0  # Lab units: a pixel further than this from a paint isn't that paint, whatever else is in the unit
FEW = 20  # a paint with fewer pixels than this near it in a unit keeps the color it came with
LITTLE = 0.002  # a step that changes less than this share of the canvas is reported (design section 8, check 4)
FAR = 25.0  # Lab units: a paint fitted this far from the plan's rough color, or a pixel this far from its step's paints
LAID = 6  # RGB levels: a pixel a step moved by more than this was laid by it


def to_hex(rgb) -> str:
    return "#" + "".join(f"{int(round(float(v))):02x}" for v in rgb)


def _dist(lab: np.ndarray, hx: str) -> np.ndarray:
    return np.sqrt(((lab - ff.hex_lab(hx)) ** 2).sum(-1))


def nearest(content: np.ndarray, hexes: list[str]) -> np.ndarray:
    """Which of `hexes` each pixel is nearest, smoothed so a pass arrives as marks, not as single pixels."""
    lab = ff.lab(cv2.GaussianBlur(content, (0, 0), 1.0))
    return cv2.medianBlur(np.stack([_dist(lab, h) for h in hexes]).argmin(0).astype(np.uint8), bs.SMOOTH)


def fit_paints(content: np.ndarray, where: np.ndarray, seeds: dict[str, str]) -> dict[str, str]:
    """Each paint's color as it is in this picture: from its seed (the plan's rough `color`), each pixel of `where`
    goes to its nearest paint and each paint to the middle of its pixels (`fit_paints` in
    spike/experiments/v4_forward.py), but only pixels within REACH of the paint count as its own. A unit's change
    holds more than its paint: the sky a render drew again round a moon, the whole of a thing drawn again without
    one layer. Without the reach the moon's pale gold was fitted to the sky's blue (the floating island, #219's
    first real run). A paint with few pixels keeps its seed."""
    names, hexes = list(seeds), dict(seeds)
    if not where.any() or not names:
        return hexes
    px = cv2.GaussianBlur(content, (0, 0), 1.0)[where]
    lab = ff.lab(px[None])[0].astype(np.float32)
    for _ in range(REFIT):
        dist = np.stack([_dist(lab, hexes[n]) for n in names])
        near = dist.argmin(0)
        for j, n in enumerate(names):
            mine = (near == j) & (dist[j] <= REACH)
            if mine.sum() >= FEW:
                hexes[n] = to_hex(np.median(px[mine], axis=0))
    return hexes


def unit_paints(steps: list[dict], u: dict) -> list[str]:
    return list(dict.fromkeys(p for i in u["steps"] for p in steps[i]["paints"]))


def fit(plan: dict, us: list[dict], ch: list[dict]) -> tuple[dict[str, str], list[dict[str, str]], list[dict]]:
    """(each paint's one color for the lesson, each unit's own fit, a row a paint). A unit's paints are fitted to
    its change. A paint several units use takes its color from the unit that lays the most of it. The rows report a
    paint fitted far from the plan's rough color (`far_from_name`: its name may no longer suit it) and a paint
    almost no pixel came to (`not_in_finish`: the plan names a color the finish doesn't have)."""
    steps = plan3.steps(plan)
    seeds = {p["name"]: p["color"] for p in plan["paints"]}
    per_unit: list[dict[str, str]] = []
    laid: dict[str, list[tuple[int, int]]] = {}
    for n, u in enumerate(us):
        names = unit_paints(steps, u)
        hexes = fit_paints(ch[n]["P"], ch[n]["D"], {p: seeds[p] for p in names})
        near = nearest(ch[n]["P"], [hexes[p] for p in names])
        lab = ff.lab(cv2.GaussianBlur(ch[n]["P"], (0, 0), 1.0))
        per_unit.append(hexes)
        for j, p in enumerate(names):  # how much of the unit's change is this paint: nearest it, and like it
            laid.setdefault(p, []).append((int((ch[n]["D"] & (near == j) & (_dist(lab, hexes[p]) <= REACH)).sum()), n))
    one, rows = {}, []
    for p, seed in seeds.items():
        if p not in laid:
            continue
        px, n = max(laid[p], key=lambda x: (x[0], -x[1]))
        one[p] = per_unit[n][p]
        moved = round(float(np.sqrt(((ff.hex_lab(one[p]) - ff.hex_lab(seed)) ** 2).sum())), 1)
        rows.append({"paint": p, "hex": one[p], "color": seed, "from_unit": n, "units": [k for _, k in laid[p]],
                     "pixels_share": round(px / ch[0]["D"].size, 4), "moved": moved,
                     "far_from_name": moved > FAR, "not_in_finish": px < FEW})
    return one, per_unit, rows


def build(plan: dict, finish: np.ndarray, ch: list[dict]) -> dict:
    """The step pictures and what the checks measure: {"pictures", "masks", "rows", "paints", "hexes", and the
    lesson's numbers}. Each pixel of a unit's change belongs to one step: the first of the unit that names the paint
    nearest it. A step lays its own pixels; the unit's last step lays all that is left, so the picture after it is
    P[n] exactly.

    The three checks (docs/design/pipeline-v3-plan.md): `final_gap`, the share of the last picture that isn't the
    finish; `outside_unit`, the share of the canvas a step changed outside what its unit adds; `from_its_paints`,
    how far what a step lays is from the paints it names. And `little`: a step that changes almost nothing."""
    us, steps = plan3.units(plan), plan3.steps(plan)
    one, per_unit, paint_rows = fit(plan, us, ch)
    canvas = np.empty(finish.shape, np.float32)
    canvas[:] = ff.CANVAS
    pictures: list = [None] * len(steps)
    masks: list = [None] * len(steps)
    rows: list = [None] * len(steps)
    was = erase3._lab(np.clip(canvas, 0, 255).astype(np.uint8))
    for n, u in enumerate(us):
        content, D = ch[n]["P"], ch[n]["D"]
        names = unit_paints(steps, u)
        near = nearest(content, [per_unit[n][p] for p in names])
        lab = ff.lab(cv2.GaussianBlur(content, (0, 0), 1.0))
        first = {p: next(i for i in u["steps"] if p in steps[i]["paints"]) for p in names}
        for i in u["steps"]:
            s = steps[i]
            before = canvas.copy()
            last = i == u["steps"][-1]
            where = D if last else D & np.isin(near, [j for j, p in enumerate(names) if first[p] == i])
            canvas = bs._lay(canvas, content, where)
            pic = np.clip(canvas, 0, 255).astype(np.uint8)
            changed = np.abs(canvas - before).max(2) > LAID
            far = None
            if changed.any():
                dist = np.min([_dist(lab[changed], one[p]) for p in s["paints"]], axis=0)
                far = {"median": round(float(np.median(dist)), 1), "over": round(float((dist > FAR).mean()), 3)}
            now = erase3._lab(pic)
            # the share a painter would see change: a thing drawn again by a render moves every pixel a little
            seen = round(float((np.sqrt(((now - was) ** 2).sum(2)) >= erase3.WEAK).mean()), 4)
            was = now
            rows[i] = {"n": i + 1, "id": s["id"], "unit": n, "show": "all" if last else "pass",
                       "painted": round(float(where.mean()), 4), "changed": round(float(changed.mean()), 4),
                       "seen": seen, "outside_unit": round(float((changed & ~bs.halo(D)).mean()), 5),
                       "from_its_paints": far}
            pictures[i] = pic
            masks[i] = where & changed if (where & changed).any() else where
    gap = np.abs(pictures[-1].astype(np.int16) - finish.astype(np.int16)).max(2) > erase3.MOVED
    medians = [r["from_its_paints"]["median"] for r in rows if r["from_its_paints"]]
    return {"pictures": pictures, "masks": masks, "rows": rows, "paints": paint_rows, "hexes": one,
            "final_gap": round(float(gap.mean()), 4), "outside_unit_max": max(r["outside_unit"] for r in rows),
            "from_its_paints_median": round(float(np.median(medians)), 1) if medians else None,
            "little": [r["id"] for r in rows if r["seen"] < LITTLE]}


def problems(built: dict) -> tuple[list[str], list[str]]:
    """(what must be fixed, what is reported). The first two checks hold by construction, so a failure there is a
    fault in the chain's files, not in the plan. The rest is reported: fixing it means a new plan and a new chain."""
    bad, notes = [], []
    if built["final_gap"] > 0.0005:
        bad.append(f"the last step picture isn't the finish ({built['final_gap']:.2%} of it differs). The chain's "
                   "files don't belong to this finish: run erase again.")
    if built["outside_unit_max"] > 0.0005:
        r = max(built["rows"], key=lambda r: r["outside_unit"])
        bad.append(f"{r['id']}: changes {r['outside_unit']:.2%} of the canvas outside what its unit adds. The chain's "
                   "files don't belong together: run erase again.")
    for r in built["paints"]:
        if r["not_in_finish"]:
            notes.append(f"paint {r['paint']!r}: almost nothing where the plan lays it is within {REACH:g} Lab units of "
                         f"the plan's {r['color']}, so it keeps that color. Either the finish doesn't have this "
                         "paint there, or the plan's rough color is too far from it.")
        elif r["far_from_name"]:
            notes.append(f"paint {r['paint']!r} was fitted to {r['hex']}, {r['moved']:.0f} Lab units from the plan's "
                         f"{r['color']}: check that its name still says what it looks like.")
    for sid in built["little"]:
        notes.append(f"{sid}: changes almost nothing a painter would see (under {LITTLE:.1%} of the canvas).")
    return bad, notes


def owner_from(ch: list[dict]) -> np.ndarray:
    """Which unit each pixel of the finish belongs to: the last unit whose core holds it, else the last whose change
    does, else the nearest pixel that has one."""
    owner = np.full(ch[0]["D"].shape, -1, np.int32)
    for n, c in enumerate(ch):
        owner[c["core"]] = n
    loose = np.full(owner.shape, -1, np.int32)
    for n, c in enumerate(ch):
        loose[c["D"]] = n
    owner[owner < 0] = loose[owner < 0]
    if (owner < 0).all():
        return np.zeros(owner.shape, np.int32)
    if (owner < 0).any():
        _, idx = cv2.distanceTransformWithLabels((owner < 0).astype(np.uint8), cv2.DIST_L2, 3,
                                                 labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.nonzero(owner >= 0)
        lut = np.zeros(idx.max() + 1, np.int32)
        lut[idx[ys, xs]] = owner[ys, xs]
        owner[owner < 0] = lut[idx[owner < 0]]
    return owner


def shapes(ch: list[dict], owner: np.ndarray) -> list[np.ndarray]:
    """Each unit's shape for the fact sheet: what it changed, core first. `owner` alone gives a returning unit only
    where it is still on top at the end, and the sheet then measured the cat's fur as 1 1/2 inches wide (#214)."""
    out = []
    for n, c in enumerate(ch):
        mine = c["core"] if c["core"].any() else c["D"]
        out.append(mine if mine.any() else owner == n)
    return out


def as_v2(plan: dict, us: list[dict], ch: list[dict], hexes: dict[str, str], owner: np.ndarray,
          finish: np.ndarray) -> dict:
    """The plan in the shape the version 2 tools read: a part a unit, its box measured from its place in `owner`
    (`v2_plan` in spike/experiments/v3_combined.py). What the spikes kept by hand is worked out here:

    - a unit that comes back to a thing is `marks` on the unit that started the thing; so is a new thing painted in
      several steps (version 2 wants a flat coat first on anything else);
    - a new thing that starts as a block-in on things already painted is an `object`: the page offers its outline to
      chalk. Every other new thing is an `area`;
    - a unit's last step shows all of it (`full`, or `blend`); an earlier one is a `pass`."""
    steps = plan3.steps(plan)
    thing = {t["id"]: t for t in plan["things"]}
    h, w = owner.shape
    shape = shapes(ch, owner)  # a returning unit's box is what it changed, not only where it is still on top
    started: dict[str, str] = {}  # thing -> the part that started it
    made: dict[str, dict] = {}
    parts, part_of = [], {}
    for n, u in enumerate(us):
        t = thing[u["things"][0]]
        ys, xs = np.nonzero(shape[n] if shape[n].any() else np.ones_like(owner, bool))
        first = steps[u["steps"][0]]
        if u["kind"] == "back" or len(u["steps"]) > 1:
            kind = "marks"
        elif u["kind"] == "behind" and first.get("block_in"):
            kind = "object"
        else:
            kind = "area"
        p = {"id": u["id"], "name": u["name"], "kind": kind, "thing": u["things"], "unit": n,
             "element": t["element"], "element_why": t.get("why", ""),
             "box": [round(float(xs.min() / w), 3), round(float(ys.min() / h), 3),
                     round(float((xs.max() + 1) / w), 3), round(float((ys.max() + 1) / h), 3)]}
        if t.get("left_out"):
            p["element_left_out"] = t["left_out"]
        parent = next((started[x] for x in u["things"] if x in started), None)
        if parent is None and kind == "marks":  # a new thing in several steps sits on what is behind it
            parent = next((started[b] for b in t.get("behind") or [] if b in started), None)
        # version 2 has no marks on marks: a mark whose parent would be one sits on that part's own parent
        # (plan2.parts_problems says the same), and on nothing when there is none
        while parent and kind == "marks" and made[parent]["kind"] == "marks":
            parent = made[parent].get("parent")
        if parent and parent != u["id"]:
            p["parent"] = parent
        made[u["id"]] = p
        if kind == "marks":  # version 2 wants a mark's colors; nothing reads them, since no outline runs
            mine = [hexes[q] for q in unit_paints(steps, u) if q in hexes]
            p.update(colors_in=mine, colors_out=[x for x in hexes.values() if x not in mine][:3] or mine)
        parts.append(p)
        for x in u["things"]:
            started.setdefault(x, u["id"])
        for i in u["steps"]:
            part_of[i] = u["id"]
    lab = ff.lab(cv2.GaussianBlur(finish, (0, 0), 1.0))
    order = [p["id"] for p in parts]
    by_name = {p["name"]: p for p in plan["paints"]}
    paints = []
    for name, hx in hexes.items():
        users = sorted({part_of[i] for i, s in enumerate(steps) if name in s["paints"]}, key=order.index)
        y, x = np.unravel_index(_dist(lab, hx).argmin(), lab.shape[:2])
        c = {"id": plan3.slug(name), "name": name, "used_for": by_name[name].get("looks", ""), "hex": hx,
             "sample_x": round(float(x / w), 3), "sample_y": round(float(y / h), 3), "parts": users}
        if by_name[name].get("of") in hexes:
            c["of"] = plan3.slug(by_name[name]["of"])
        paints.append(c)
    last_of_unit = {u["steps"][-1] for u in us}
    stages, i = [], 0
    for st in plan["stages"]:
        out = []
        for s in st["steps"]:
            show = ("blend" if s.get("blend") else "full") if i in last_of_unit else "pass"
            out.append({k: v for k, v in {"id": s["id"], "name": s["name"], "part": part_of[i], "show": show,
                                          "paints": [plan3.slug(p) for p in s["paints"]], "stroke": s["stroke"],
                                          "brush": s["brush"], "why": s.get("why")}.items() if v})
            i += 1
        stages.append({"id": st["id"], "name": st.get("name") or st["id"], "steps": out})
    head = {k: plan[k] for k in ("technique", "technique_why", "subject", "focal_point", "light", "photo", "palette")
            if plan.get(k)}
    return {"plan_version": 2, "made_from": 3, **head, "parts": parts, "paints": paints, "stages": stages}
