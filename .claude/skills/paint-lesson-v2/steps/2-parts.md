# Step 2: parts and outlines

A part is one thing or area of the finished painting. Every later step paints inside one part's outline, so this
step decides how good the lesson can be. **Read one fixture plan first** to see the shape:
`spike/tests/fixtures/plans/chickadee.json` (and `docs/spikes/outlines-chickadee-parts.jpg` for what its outlines
look like).

## 2a. List the parts
1. `grid --percent` on `99_finish.png` and Read it.
2. Start `plan.json`:
   ```json
   {"plan_version": 2, "photo": "<the photo as step 0 left it>", "technique": "techniques/acrylic-paint-along-beginner.yaml",
    "subject": "...", "focal_point": "...", "light": "where the light comes from, in words",
    "parts": [], "paints": [], "stages": []}
   ```
3. Write `parts`, **back to front**, the order they'll be painted. The whole background first, then the objects.
   Leave `paints` and `stages` empty: `outline` needs only the parts.

| `kind` | For | Needs |
|---|---|---|
| `area` | a big region with a visible edge: sky, hill, field, water. The farthest one usually has box `[0, 0, 1, 1]`: it takes whatever nothing else claims | `box` |
| `object` | a compact thing with a clear edge: a bird, a sail, a balloon, a leaf, the sun. Several of the same (four leaves) are one part with `boxes` | `box` or `boxes` |
| `thin` | long and narrow: a branch, a mast, a rail | `paths` (points along its middle, one list per limb), `width`, and the color fields below |
| `marks` | paint with no single edge: clouds, mist, foliage clumps, a sun path, a reflection, a bird's black cap | `box` or `boxes`, and the color fields below |

- Every part: `"id"` (a lowercase slug), `"name"` (how the page will say it: "The chickadee", "Far misty trunks").
- Boxes are `[x0, y0, x1, y1]` as shares of the width and height, measured, 2 to 3% loose. For `marks`, **tight**:
  color is all that separates a mark from anything the same color in its box.
- **Color fields** for `marks` and `thin`: `points_in` (5 to 8 spots on the part, one per shade of it) and
  `points_out` (5 to 8 spots on what's behind and around it, one per color there).
- An `area` or `object` with one box takes `points_in` / `points_out` too: spots the outline must include or
  leave out. Use them only to fix an outline after seeing the preview.
- `"parent": "<id>"` when the part is painted on another part and stays inside it (clouds on the sky, the cap on the
  bird, a hull's deck line). Something that crosses its parent's edge (a bird's feet over a branch) is its own
  part, listed after, with no parent. A thing that only **sits on** something (a boat on water, a tree on a hill)
  is not its child: no parent. A `marks` part can't be the parent of another `marks` or `thin` part: list the
  second one after it with the same parent, or none.
- `"covers"` on an `area`: boxes saying how far its paint runs under what comes next, so a sky runs past the
  horizon. The technique's rule: a background is painted straight through, never stopped at a hill line.
- Keep parts with no parent within the technique's `detail_budget.max_parts`.
- **Try a pass before a part** for what's just one more color on a part (a deck line on a hull, light streaks on
  water): that's a pass in step 4, and costs nothing here. Make it a `marks` child only when `outline` says the
  area left a hole there (soil paths between lavender rows that the field's outline didn't take).

## 2b. Outline them
`outline --lesson <lesson>`, then **Read `parts/preview.jpg`**. Every part should be tinted where the part really
is, and `problems` should be empty. Fix what's wrong and run it again: at most 2 fix rounds per part. If a round
made a part worse, put its entry back the way it was; that doesn't count as a round.

| Seen in the preview | Fix |
|---|---|
| A marks part took something else the same color | tighten its box; add a `points_out` on the thing it took |
| A marks part missed some of itself | add a `points_in` there, one per shade |
| A thin part is broken or missing an end | add a path along the missing limb; add `points_in` on its light and dark sides; raise `width` |
| A piece of a thing sits outside its parent | make it a part of its own, listed after, with no parent |
| A marks part came out as specks, or its points keep missing | run `part-colors` and give `colors_in` / `colors_out` as hex; or drop the part and use a pass |
| An object took background, or came back in pieces | tighten or loosen its box; one box per thing |
| An area left a hole that went to a part behind it (water around a hull went to the sky) | add `points_in` in the hole; or make what's there a `marks` child of the area |
| A faint trace of an object shows in step pictures before its own step (seen in step 5) | its outline is too tight: loosen its box, or add `points_in` on the trace |

**If a small part still won't come apart after 2 rounds, drop it**: take it out of `parts`, and let the part it sat
on carry it. In step 4 that part gets one more paint for it (`paints --add <part id>`) and one more pass. Record
it in `notes.json` under `merged_parts`: `{"<part id>": "why it wouldn't outline, and which part carries it"}`.
A main part can't be dropped (the branch, the field): keep its best outline, and record what's still wrong with
it in `notes.json` (`learned`) and later in `review.json` as `left`.
