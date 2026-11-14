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
    "technique_why": "one line: why this approach fits the picture and the painter's level",
    "subject": "...", "focal_point": "...", "light": "where the light comes from, in words",
    "parts": [], "paints": [], "stages": []}
   ```
3. Write `parts`, **back to front**, the order they'll be painted. The whole background first, then the objects.
   Leave `paints` and `stages` empty: `outline` needs only the parts.

| `kind` | For | Needs |
|---|---|---|
| `area` | a big region with a visible edge: sky, hill, field, water. The farthest one usually has box `[0, 0, 1, 1]`: it takes whatever nothing else claims | `box` |
| `object` | a compact thing with a clear edge: a bird, a sail, a balloon, a leaf, the sun. **Small things with a clear edge too: a bird's feet.** Several of the same (four leaves) are one part with `boxes` | `box` or `boxes` |
| `thin` | long and narrow: a branch, a mast, a rail | `paths` (points along its middle, one list per limb), `width`, and the color fields below |
| `marks` | paint with no single edge: clouds, mist, misty trunks, foliage clumps, a sun path, a reflection, a bird's black cap | `box` or `boxes`, and the color fields below |

- Every part: `"id"` (a lowercase slug: letters, digits, and hyphens, no underscores), `"name"` (how the page will
  say it: "The chickadee", "Far misty trunks").
- Boxes are `[x0, y0, x1, y1]` as shares of the width and height, measured, 2 to 3% loose. For `marks`, **tight**:
  color is all that separates a mark from anything the same color in its box.
- **Color fields** for `marks` and `thin`: `points_in` (5 to 8 spots on the part, one per shade of it) and
  `points_out` (5 to 8 spots on what's behind and around it, one per color there).
- **A `thin` part is found by the outline model**, asked once for the whole part (a box around all its paths, with
  your points) and once per path (points along that path). So give **one path per limb**: the trunk, each bough,
  each twig, a leaf's stem, a mast and its boom. `width` is the part's widest thickness as a share of the
  picture's width (a bough 12% of the width across at its base: `0.12`); nothing farther than that from a path is
  taken. A limb with no path of its own can be lost. Put `points_in` on the thick body,
  and `points_out` on everything that touches it or lies between two limbs (foliage between twigs, the sail
  beside a mast): the color fields decide what a limb's outline keeps.
- **`marks` or `object`?** If you could cut the thing out with scissors (feet, a leaf, a sun), it's an `object`
  with a box, however small. If it's soft, scattered, or see-through (mist, trunks in haze, clouds, a sun path, a
  reflection, foliage), it's `marks`.
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
- **Too small to be a part:** anything under about a quarter of one percent of the picture (an eye, a beak, a
  basket's ropes) can't be outlined. Don't list it. The step that paints the thing it sits on mentions it in its
  tip ("dot the eye in last, with the tip of the brush").
- An `area` counts as background wherever you list it (a field in front of a tree is still ground). Objects, thin
  parts, and marks listed after the first object are what the background picture (step 5b) takes out.
- **Try a pass before a part** for what's just one more color on a part (a deck line on a hull, light streaks on
  water): that's a pass in step 4, and costs nothing here. Make it a `marks` child only when `outline` says the
  area left a hole there (soil paths between lavender rows that the field's outline didn't take).

## 2b. Pick each part's element technique
An element technique (`techniques/elements/`) is how that kind of thing is painted, step by step: a sky blended
wet, foliage dabbed dark to light, lavender rows laid flat then stamped dark, mid, and light. Step 4 follows it, so
the lesson paints each kind of thing the way the research says, every run.

1. `elements` (no `--lesson`) lists them: what each is for, which part kinds, and its steps in order.
2. On every part, add `"element": "<id>"` and `"element_why"`: one line on why it fits this part at this level
   ("Far trunks: dry-brushed verticals, no light pass at this distance"). Pick by what the thing is and how the
   finish shows it, not by its name: a flat white cheek is `simple-shape`, a bird's body with a lit chest is
   `shaped-object`. When you leave something out for a beginner (fur texture, the far rows' tips), say what in
   `"element_left_out"`.
3. **When nothing in the library fits a part** (fur, skin, glass, metal, a night sky, feathers worth their own
   strokes), draft one in `<lesson>/elements/<new id>.yaml`, the same shape as a library file (`id`, `name`, `for`,
   `kinds`, `medium`, `levels`, `steps`, `sources`), with `drafted: true` and `checked: false`. Its steps name stroke
   cards (`ls techniques/strokes`), never a stroke written out. Build it from the research file where it can
   (`docs/research/acrylic-paint-along.md`; say which sections in `sources`) and from the closest library element;
   where you go past them, say so in `sources` ("general practice: the research has no section on fur"). The lesson
   marks that part's steps "technique not checked yet".
4. **File it for the owner now**, while you draft it (`check` won't pass while a draft the plan uses has no
   `filed`):
   - Search: `gh api -X GET search/issues -f q="repo:DeanPhillipsOKC/gesso is:issue is:open element technique <what it's for>"`.
   - An open issue already asks for this technique (an earlier run of this photo filed it): put its url in `filed`,
     and comment on it only when your draft's steps differ from the one there (say how, and name this lesson folder).
   - Otherwise file one: title "Element technique: <name>", labels `feature` and `status:needs-review`, and in the
     body what it's for, why no library element fit, the draft's YAML, which lines came from the research and which
     didn't, and the lesson folder: `gh api repos/DeanPhillipsOKC/gesso/issues -f title=... -f body=...
     -f "labels[]=feature" -f "labels[]=status:needs-review"`. Put the new issue's url in `filed`.
   - If GitHub can't be reached, say so in `notes.json` (`learned`) and in the report, and stop before the seal.
   - A draft you stop using (you picked a library element after all) is deleted from `elements/`; `check` reports
     one left over.
5. Never edit a library element during a run. If one is close but wrong for this picture, draft your own with a new id.

## 2c. Outline them
`outline --lesson <lesson>`, then **Read `parts/preview.jpg`**. Every part should be tinted where the part really
is, and `problems` should be empty. Fix what's wrong and run it again: at most 2 fix rounds per part, and at most 5 runs of `outline` in this step however they go. If a round made a
part worse, put its entry back the way it was.

| Seen in the preview | Fix |
|---|---|
| A marks part took something else the same color | tighten its box; add a `points_out` on the thing it took |
| A marks part missed some of itself | add a `points_in` there, one per shade |
| A thin part is missing a limb or an end | add a path along the missing limb; raise `width` if its band cuts the limb off |
| A thin part took what lies beside it (foliage between twigs, a strip of sail) | add a `points_out` there, one per color; lower `width` |
| A piece of a thing sits outside its parent | make it a part of its own, listed after, with no parent |
| A marks part came out as specks, or its points keep missing | run `part-colors` and give `colors_in` / `colors_out` as hex; or drop the part and use a pass |
| An object took background, or came back in pieces | tighten or loosen its box; one box per thing |
| An area left a hole that went to a part behind it (water around a hull went to the sky; soil paths in a field) | add `points_in` in the hole so the area takes it. If what's in the hole should be its own steps (soil paths), then also list it after the area as an `area` or `marks` part with that area as its `parent` |
| A faint trace of an object shows in step pictures before its own step (seen in step 5) | its outline is too tight: loosen its box, or add `points_in` on the trace |

**If a small part still won't come apart after 2 rounds, drop it**: take it out of `parts`, and let the part it sat
on carry it. In step 4 that part gets one more paint for it (`paints --add <part id>`) and one more pass; if
`--add` finds no separate color, the thing is too small or too close in color to teach as its own step, so name it
in a tip instead. Record
it in `notes.json` under `merged_parts`: `{"<part id>": "why it wouldn't outline, and which part carries it"}`.
A main part can't be dropped (the branch, the field): keep its best outline, and record what's still wrong with
it in `notes.json` (`learned`) and later in `review.json` as `left`.
