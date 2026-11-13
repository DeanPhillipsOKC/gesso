# Pipeline v2: paint the finish once, cut every step from it

Design, 2026-11-12. The owner approved the direction that day (`docs/decisions.md`, "Pipeline v2"). Part 1 is
built and tested (`docs/spikes/outlines.md`: read it, and look at its pictures). This file is the plan the
remaining issues build. If an issue and this file disagree, this file wins; fix the issue.

**Read this whole file before starting any pipeline v2 issue.** It was reviewed twice by fresh reviewers before
the issues were filed; where they found something this design can't yet answer, it says so ("Not known yet").

Words used here:
- **finish**: the finished painting, `99_finish.png`. Rendered once by the image model.
- **part**: one thing or area in the finish (the sky, the far hill, the bird, the bird's wing).
- **outline**: a part's exact shape. `parts/owner.png` holds every part's outline in one picture.
- **stage**: a group of steps that paint one thing ("The chickadee"). What the lesson's contents list shows.
- **step**: one small move: one brush, one kind of stroke, one to three paints.
- **render**: a paid call to the image model. Everything else is a free tool run where the lesson is made.
- **v1**: the pipeline up to POC 0.26.1 (one render per step).

## 1. Why change

Measured on the lessons in `site/history/`:

| Problem in v1 | Evidence |
|---|---|
| Every step picture is its own render of "the finish with later parts not painted". The image model moves things between renders. | Chickadee: 21 paid renders for 11 steps, $0.51, 5 redos, and 5 drift problems still listed under Known problems. Sailboat: 13 renders, $0.40, 4 redos. |
| Most of a run is repair, not teaching: two image review rounds, redos, `lock-steps`, `carry-forward`, `split-texture`. | The chickadee run took 27 minutes from start to seal, 7 of them rendering. The sailboat took 21, 6 of them rendering. |
| Splitting a step costs a render, so steps stay too big. | Chickadee step 10 "Shade the feathers" was flagged "five kinds of moves in one step" and left. The bird goes from a flat shape to finished feathers in one step. |
| The skill caps detail: about 100 words a step, 2 to 5 instructions, and it tells Claude to cut. | `steps/6-text.md` "Keep it short"; `STEP_WORDS` in `spike/tools.py`; the technique's rule "2 to 5 short instructions per step". |
| Placement is given as numbers with nothing to measure against. | "paint the body as one big round: 37% to 60% across, 28% to 56% down". |
| Teaching content (how to do a stroke, how to load the brush) is written fresh each run. | The same stroke reads differently in every lesson. The chickadee asks for 16 mixes from 14 tubes. |

The owner (2026-11-12): not enough detail for new painters; use tools and filters instead of inference or image
generation wherever they give good results; save cost but never at the expense of quality; don't raise the image
model's quality setting.

## 2. The idea, and what's proven

Render the finish once. Find each part's outline with a free local tool. Build every step picture by laying the
parts on a white canvas in painting order, and build a part's in-between steps with filters (a flat coat, then one
pass per paint). Nothing can drift, because every step is cut from the same picture. Splitting a step is free, so
steps can be as small as a beginner needs. The same outlines give free teaching pictures: where to paint, a
close-up, which paint goes where.

**Proven** (`docs/spikes/outlines.md`, code and tests in the repo): on the sailboat, the lavender balloon, and
the chickadee, every step is cut from the finish with no renders, in about 20 seconds, the same bytes each run.
The chickadee's bird is 9 small steps where v1 had 3.

**Not known yet:**
- whether Claude writes good parts (boxes, points) inside the skill in 2 rounds. They were hand-tuned in the spike;
- how a real run's finish behaves (a larger PNG in the image model's frame, sometimes with gray bands);
- whether the full run meets the cost and time targets (section 14).

## 3. What stays, what changes, what goes

| | v1 | v2 |
|---|---|---|
| Photo check, crop, canvas fit, beginner version | skill `steps/0-setup.md` | **stays as is** |
| Simplified reference, finish render, finish check | `steps/1-reference-finish.md` | **stays as is** |
| Plan | steps with `regions` boxes | **changes**: parts, paints, stages, small steps (section 5). Built. |
| Step pictures | one render per step | **changes**: cut from the finish (sections 6 to 8). Built. |
| Image review rounds, redos | `steps/4-render-review-lock.md` | **goes**: measured checks instead (section 12) |
| `lock-steps`, `carry-forward`, `finish-from-step`, `split-texture`, `from-finish`, throwaway filter scripts | same file, and `steps/6-text.md`, `steps/tools.md` | **go** |
| Paints | named and placed by Claude | **changes**: measured from the finish, limited, named by Claude (section 9) |
| Mix recipes (`mix`, Mixbox) | computed | **stays as is** |
| Step text | written from scratch, cut to a word limit | **changes**: built from data and hand-checked cards; Claude adds what only this photo needs (section 10) |
| Text review in a fresh context | `steps/6b-text-review.md` | **stays**, smaller (section 12) |
| Construction diagrams | `steps/7-diagrams.md` | **stay** |
| Notes, seal, publish, history, site | `steps/8-notes.md`, `steps/9-publish.md` | **stay**; `publish` learns to read a version 2 plan (section 13) |

Renders left in v2: the finish (high quality), and when needed the beginner version, the canvas extend, and one
background picture (section 7). Nothing else is rendered.

**Nothing in v1 is deleted until the gate in section 14 passes.** v2 is new files and new subcommands next to
v1. Version 1 lessons, their pages, and `site/history/` must keep working: run the whole test suite on every
issue.

## 4. The run, start to end

| # | What | Who | Writes |
|---|---|---|---|
| 0 | Set up, check photo, fit canvas, beginner version | Claude + tools, as v1 | `00_*.png`, `notes.json` |
| 1 | Reference and finish | filters + 1 render, as v1 | `00_reference.png`, `99_finish.png` |
| 2 | List the parts | Claude, measuring with `grid --percent` | `plan.json`: `plan_version`, `parts` |
| 3 | Outline the parts | `outline` | `parts/owner.png`, `parts/<id>.png`, `parts/preview.jpg`, `parts/stats.json` |
| 4 | Read the preview once; fix boxes, points, colors; run 3 again | Claude | `plan.json` (at most 2 fix rounds per part) |
| 5 | Measure the paints, then name them | `paints`, then Claude | `plan.json`: `paints` |
| 6 | Stages and steps | Claude, inside the technique's rules | `plan.json`: `stages` |
| 7 | Step pictures | `build-steps` | `NN_<id>.png` for every step, `trials/steps.jpg` |
| 8 | Background picture, only when 7 printed `"needs_background": true`; then 7 again | `background` (1 render) | `98_background.png` |
| 9 | Teaching pictures | `step-aids` | `aids/` |
| 10 | Text | `draft-text`, then Claude | `text.json` |
| 11 | Checks | `check` (also run by `publish`) | a list of failures, each saying what to change |
| 12 | Text review, once | a fresh subagent | `review.json`: `text_issues` |
| 13 | Diagrams, notes, seal, publish | as v1 | the sealed lesson |

Built today: `outline`, `part-colors` (the measuring half of `paints`), `build-steps`. Run them with
`python spike/tools.py <tool> --lesson <lesson>`; each prints one line of JSON (`outline` and `build-steps` with
`problems`, a list that is empty when all is well, and `advice`).

Steps 3 to 8 can loop: change the plan, run `outline` and `build-steps` again. Both are free and take seconds.

**Changed 2026-11-13, from three real runs.** Steps 3 to 5 need only what comes before them: `outline` and
`part-colors` check only the parts (`plan2.parts_problems`), and `paints` measures with no stages (section 9), so
a plan has `parts` at step 3, `paints` after step 5, and `stages` from step 6. Before, `outline` refused a plan
without stages and paints, and all three runs invented placeholder steps to get past it. After step 6, rerun
`paints` only when `outline` changed the parts; it keeps what the steps use. `paints --add <part>` (section 9)
gives one part one more color, to split a pass in two. `check` prints `problems` (and, as before, `failures`, the
same list), like every other tool.

## 5. The plan file (`plan.json`, version 2)

`spike/plan2.py` loads it and lists what's wrong with it (`plan2.problems`). Fields not listed keep their v1
meaning (`photo`, `technique`, `subject`, `focal_point`, `light`, `palette`). Three complete examples:
`spike/tests/fixtures/plans/*.json`. **Read one before writing one.**

```json
{
  "plan_version": 2,
  "parts": [
    {"id": "sky", "name": "Sunset sky", "kind": "area", "box": [0, 0, 1, 0.5], "covers": [[0, 0, 1, 0.56]]},
    {"id": "sun", "name": "The sun", "kind": "object", "parent": "sky", "box": [0.445, 0.38, 0.52, 0.465]},
    {"id": "water", "name": "The water", "kind": "area", "box": [0, 0.52, 1, 1]},
    {"id": "sun-path", "name": "The sun path", "kind": "marks", "parent": "water", "box": [0.05, 0.53, 0.72, 0.97],
     "points_in": [[0.48, 0.6], [0.5, 0.73]], "points_out": [[0.2, 0.9], [0.1, 0.6]]},
    {"id": "sail", "name": "The sail", "kind": "object", "box": [0.72, 0.27, 0.91, 0.58]},
    {"id": "mast", "name": "The mast", "kind": "thin", "width": 0.012, "paths": [[[0.812, 0.26], [0.812, 0.595]]],
     "points_in": [[0.812, 0.4]], "points_out": [[0.79, 0.45], [0.85, 0.5]]}
  ],
  "paints": [
    {"id": "water-1", "name": "Deep teal", "hex": "#1d677a", "used_for": "the water's base coat",
     "sample_x": 0.3, "sample_y": 0.8, "parts": ["water"]}
  ],
  "stages": [
    {"id": "water", "name": "The water", "steps": [
      {"id": "water-coat", "name": "Lay in the teal water", "part": "water", "show": "flat",
       "paints": ["water-1"], "stroke": "horizontal-strokes", "brush": "1 inch flat"},
      {"id": "water-light", "name": "Streak the lighter water", "part": "water", "show": "pass",
       "paints": ["water-2"], "stroke": "horizontal-strokes", "brush": "3/4 inch flat"}
    ]}
  ]
}
```

### Parts

Listed **back to front**: the order they're painted. A later part is in front of an earlier one and wins any
pixel both claim.

| `kind` | For | How its outline is found | Needs |
|---|---|---|---|
| `area` | a big region with a visible edge: sky, hill, field, water | the outline model, from its box. An area with no parent whose box covers 90% or more of the picture is the backdrop: no model, it claims everything, and every later part takes its share back. List it first | `box` |
| `object` | a compact thing with a clear edge: a bird, a sail, a balloon, a leaf, the sun | the outline model, from its box, or one box per thing (`boxes`) for several of the same (four leaves) | `box` or `boxes` |
| `thin` | long and narrow: a branch, a mast, a rail | the color rule, inside a band around its `paths` | `paths`, `width`, `points_in`/`colors_in`, `points_out`/`colors_out` |
| `marks` | paint with no single edge: clouds, mist, foliage clumps, a sun path, sparkles, a reflection, a bird's black cap | the color rule, inside its box | `box` or `boxes`, `points_in`/`colors_in`, `points_out`/`colors_out` |

- **Boxes** are `[x0, y0, x1, y1]`, shares of width and height, measured with `grid --percent`, 2 to 3% loose
  for the model. For `marks` they must be **tight**: color is all that separates a mark from anything the same
  color inside its box (the chickadee's white cheek box took the white chest until it was shrunk).
- **The color rule:** a pixel is in the part when its color is nearer the part's own colors than the colors behind
  it. `points_in` are spots on the part, `points_out` spots on what's behind it and around it (5 to 8 of each,
  covering every color on both sides). When a point can't be trusted to land on the paint (a narrow path,
  sparkles), give colors outright: `colors_in` / `colors_out` as hex, read from `part-colors`.
- **`parent`**: the part is painted on another part (clouds on the sky, the cap on the bird). A `marks` or `thin`
  child only takes pixels its parent (or the parent's other children) had; an `area` or `object` child is kept
  inside its own box. A child comes after its parent in the list. Don't give a parent to something that reaches outside it: the
  bird's feet cross the branch, so they're a part of their own after the bird, not a child.
- **`covers`** (optional, `area` only): boxes where the painter lays this part's paint past its visible edge, so
  a sky runs below the horizon. Left out, a part's paint runs 1.2% of the long side under the next part's edge.
- **`paths`**: for `thin`, lists of points along the middle of each limb. `width` is its widest thickness as a
  share of the picture's width.
- **Back and front:** find the first part with no parent whose kind is `object` or `thin`. Parts with no parent
  listed before it are *behind*; it and the parentless parts after it are *in front*; a child is wherever its
  parent is (`build_steps.back_parts`). So list the whole background first, then the objects. Marks painted after
  an object (a reflection) go after it, with no parent.
- **Don't make a part of what a pass can do.** If something is just one more color on a part (the lavender's
  earth paths, a hull's deck line), give the part a paint for it and a pass in that paint. That worked where
  outlining it as marks failed.
- The technique's `detail_budget.max_parts` counts parts with no parent; a `boxes` part counts once.

### Paints

One entry per paint: `id`, `hex` (measured, section 9), `sample_x`/`sample_y` (a spot of it in the finish),
`parts` (every part it's measured in and every part a step uses it on), and from Claude `name` and `used_for`.
`"added": true` marks a paint `paints --add` made: no later run merges it (2026-11-13). Steps refer to paints by
`id`. `plan2.problems` checks `id` and `hex` today; issue 4 adds the rest.

### Stages and steps

A stage groups steps. A step paints inside **one** part. `show` says what the step picture shows there:

| `show` | The picture shows | Use for |
|---|---|---|
| `flat` | the part as flat color in the step's paints (one, or two for a part with two color areas), no texture | a base coat or block-in. Its paint is the part's dark or main color: what's painted first |
| `pass` | the finish, wherever its color is nearest one of this step's paints (among all the paints the part's steps name); the rest stays as it was | each layer over the coat: one paint, or two close ones, per pass |
| `full` | the part exactly as the finish has it | a part one move can make: a hill, a sun disk, a small one-color part |
| `blend` | the same as `full` | colors blended wet in one go (a sunset sky). May use more than 3 paints |

A step's `name` lives here in the plan (a short instruction: "Block in the body"). A part's **last** step always
shows everything of the part that's left, whatever its paints. Rules (`plan2.problems` enforces these five):
- every part has at least one step; its last step isn't `flat`;
- an `area` or `object` starts with `flat`, `full`, or `blend` (a `marks` or `thin` part may start with a pass);
- nothing follows a `full` or `blend` step on the same part;
- at most 3 paints in a step, except a `blend`;
- ids are unique lowercase slugs.

Order passes the way they're painted: after the coat, usually darker then lighter, each covering less than the
one before (research section 4). `build-steps` reports a step that changes almost nothing; merge it into its
neighbor or fix its paints.

A parent's steps paint over its children's places until the child's first step, then leave them alone. So the
order inside a stage is free: body coat, wing coat, cap, cheek, then the chest pass.

Step count for the beginner paint-along: 12 to 24 steps in 4 to 9 stages (owner, 2026-11-12: more, smaller
steps). Not more: a mix dries on the palette between distant steps, and the last stages matter most.

## 6. Outlines (`outline`, built: `spike/outline.py`)

`outline --lesson <lesson>` writes `parts/owner.png` (each pixel's part, as its index in `parts`),
`parts/<id>.png`, `parts/preview.jpg` (the finish with every part tinted and labeled), `parts/stats.json`, and
prints `problems`.

1. Parts are taken in order; each claims pixels by its kind's method; a later claim replaces an earlier one.
2. Pixels nobody claimed go to the nearest part.
3. Pieces smaller than 0.05% of the picture go to whatever surrounds them.

A child of kind `marks` or `thin` only takes pixels its parent's family already had. `outline.problems` reports: nothing outlined; model confidence under 0.80; an object filling under 15% or over 98%
of its box; an object in more than 3 pieces per box. Each says what to change.

**Changed 2026-11-13, from three real runs:**
- `outline` and `part-colors` check only the parts (`plan2.parts_problems`), so they run on a plan with no paints
  or stages yet. Before, they demanded both, and every run invented placeholder steps and paints to get past it.
- A `marks` or `thin` part whose parent is `marks` or `thin` is refused by `plan2.parts_problems`. It outlined
  nothing, silently: a marks parent owns only pixels of its own colors, and the child, a different color, finds
  none of them to take (the sailboat's mast reflection, child of the reflection, failed two rounds this way). Give
  it the parent's parent, or no parent, and list it after. Refusing is smaller than a new family rule, and gives the
  same outline the grandparent would.
- `outline.problems` also reports an `area` whose filled outline (with it, its children, and the box's sides on the
  picture's edge, gaps narrower than about 4% of the long side closed) encloses more than 3% of the picture that
  went to an `area` or `object` behind it, with a spot in it and the two fixes: `points_in` there, or a `marks` child
  of the area for what's there. The lavender's earth paths went to the sky that way. A marks part listed before the
  area took its pixels on purpose and isn't counted.

Claude Reads `parts/preview.jpg` once and fixes what's visibly wrong, at most 2 rounds per part. What goes wrong
and the fix, from the spike:

| Seen in the preview | Fix |
|---|---|
| A marks part took something else the same color | tighten its box; add `points_out` on the thing it took |
| A marks part missed some of itself | add `points_in` there, one per shade |
| A thin part is broken or missing an end | add a path along the missing limb; add `points_in` on its light and dark sides; raise `width` |
| A piece of a thing sits outside its parent | make it a part of its own, listed after, with no parent |
| A marks part came out as specks, or its points keep missing | give `colors_in`/`colors_out` from `part-colors`; or drop the part and use a pass |

**If a part still won't come apart after 2 rounds, drop it** and let the part behind it carry its paint as one
more pass. Record it in `notes.json` under `merged_parts` with the reason. A pass in the right paint is a correct
way to teach it; a wrong outline is not. Don't render a step to get around it.

The model: Segment Anything ViT-B, quantized ONNX, 108 MB, downloaded once to `models/` (git-ignored) with its
SHA-256 checked. `onnxruntime`, no PyTorch. About 10 seconds a picture on 4 cores.

## 7. What's behind things (built, except the render)

Painting back to front, the sky is painted straight through where the bird will sit, and the finish doesn't show
that sky. Three cases:

1. **Under a part's own children, and under the next part's edge** (sky under clouds; a field under the lavender's
   top edge): the part's own paint carried across (`from_finish.continue_paint`; along the rows for a part wider
   than 60% of the picture), with brush texture borrowed from beside the gap. Built; good wherever it was tried.
2. **Behind objects, when they're small:** the same fill, per part, with the gap divided between the parts behind
   along each row so a horizon carries straight on. An object's soft rim (0.8% of the long side) is cleared with
   it and comes back when the object is painted. Built. It looked fine on the fixture sailboat and lavender
   (objects are 8% of each picture), but not on the real runs of 2026-11-13 (below): only tiny objects get it now.
3. **Behind objects, when they're big** (33% on the chickadee): the fill is soft and patchy. `build-steps` reports
   `objects_share` and asks for a background picture above **2%** (`NEEDS_BACKGROUND`).

**Changed 2026-11-13: the background render is wanted far more often.** `NEEDS_BACKGROUND` was 15%, a number
between the two fixture cases. It was found wrong in three real runs on 2026-11-13: in two of them objects covered
about 8% of the picture, and a blurred ghost of the boat, and of the balloon and the tree, showed in every step
before they were painted. The earlier fixture comparison that showed "no visible difference" at 7 to 8% (below) did
not hold on fresh finishes. The render costs about 2 cents, so it's now asked for whenever objects cover more than
2% of the picture: in practice, whenever the picture has an object in front.

**The background picture** (`98_background.png`, tool `background`, built: issue 2 of 8). One low-quality render
of the finish with everything in front removed. The tool writes the prompt from the plan (the names of the front
parts to remove and the back parts to continue), puts the finish in the image model's frame with gray bands when
their shapes differ and crops the answer back, and records the render in the ledger like any other.
`build-steps` uses the file when it's there (`build_steps.make_background`): only its pixels inside the objects'
outlines and rims are taken, matched to the color around the hole, so the render can't move or recolor anything
else. Marks the render shows behind an object (foliage behind the bird) are found there by the same color rule.

Tried on the three fixtures (`docs/spikes/outlines.md`): $0.018 and 13 seconds each; clean on the chickadee; no
visible gain on the two pictures where objects are 7 to 8% of the picture (the real runs of 2026-11-13 showed
otherwise; see above). It's run when `build-steps` prints `"needs_background": true`.

`build_steps.background_problems` checks the render: it reports when more than 25% of the scene away from the
objects changed (the three real renders changed 0.0 to 0.3%), or when the objects are still there. One redo at
most (`--redo`); if that fails too, delete the file and keep the free fill, and record it as `left`. The v2 skill
passes `--max-cost 0.40` to every render (the default stays $1.00 for v1).

What's behind a thing is only on screen until the thing is painted. The bar is "doesn't look wrong".

## 8. Step pictures (`build-steps`, built: `spike/build_steps.py`)

`build-steps --lesson <lesson>` writes `NN_<step id>.png` for every step (NN counts across all stages from 01)
and `trials/steps.jpg`, all the steps on one sheet to Read. No renders.

It starts from a white canvas and takes the steps in order. Each changes only its part's painted area (the
part, its children's places until they're painted, and what's carried under the next edge), by its `show`
(section 5). Edges are softened inward by under a pixel, so nothing outside the area changes. The last picture is
then set to the finish itself; how far the built one was from it is reported as `final_gap`.

`build_steps.problems` reports: a step that changed something outside its part (a bug; it has never happened);
a step that changes almost nothing; a last picture more than 2% away from the finish.

By construction a step can't move, reshape, or recolor another part. There is nothing to review, redo, or lock.

## 9. Paints (`paints`, built: `spike/paints.py`)

Built: `paints.part_colors(finish, mask, k)` and the `part-colors` tool: a part's k main colors (k-means in
Lab, fixed seed), darkest first, each with its share and a spot inside it. And (issue 4 of 8) the `paints` tool,
which writes the plan's `paints` (ids `<part id>-<n>`, darkest first), points the steps at them, prints what it
merged and why, and writes `trials/paints.jpg` (the finish beside each part's paints with their shares). Color
distances are `mixing.delta_e` (CIEDE2000) throughout.

The limit is on **mixes a beginner has to work out**, and the fixtures show why that needs care: written by hand
with a paint per step they have 16, 20, and 22 paints. Most of those are a part's own lighter and darker
versions (bark dark, mid, light). So:
1. **Colors per part:** the fewest (1 to 4) that leave the part's average color error under Delta E 8 (was: as many
   as its steps name; changed 2026-11-13, below). A part with one paint gets a color it really has (below), not its
   average.
2. **Tints and shades don't count as mixes.** Within a part, a paint is a *tint* of the part's main paint (the
   one covering most of it) when that paint plus white, in some proportion, lands within Delta E 8 of it by
   `mixing.py`'s model, and a *shade* when the main paint plus the palette's darkest tube does. It's listed as
   "\<main paint\> plus white" (or the dark tube), keeps its own step, and doesn't count toward the limit. This is
   also how a teacher has a beginner work: one puddle, lightened or darkened (research section 4). In the plan such
   a paint carries `"of": "<main paint id>"` and `"plus": "white"` (or the dark tube's name).
3. **Merge the rest toward the target, never past a color the painter can see.** The technique's `max_mixes`
   (**10** for the beginner paint-along; owner, 2026-11-12) is a target, not a cap. While the lesson has more base
   mixes than that, merge the two closest into one paint shared by both parts, preferring pairs in different parts.
   If the only pairs left are in one part, merge them, merge the two steps that used them into one, and say so in
   the output (no longer: since 2026-11-13 a paint a step uses is never merged away, below). **Never merge two
   paints more than Delta E 12 apart** (`MAX_MERGE`): that loses a color the painter
   can see (a red hull blocked in brown). When the ceiling stops the merging above the target, `paints` says so,
   with each paint's nearest neighbor and how far ("Hull 1 stays: nearest is reflection-1, 16.3 away").
   That's a finished result, not a problem: `plan2.problems` reports going over the target only while two base
   paints are still close enough to merge.
4. **Never merge away an accent:** the lightest paint in the lesson, and any paint that is the only one of its
   hue family (more than 40 degrees of hue from every other paint with real chroma), even if it covers little
   (a sun, a sparkle, an eye light).
5. Keep any `name` and `used_for` already given to a paint whose color moved less than Delta E 3.

Claude names each paint and says what it's for, and chooses which of a part's paints each step uses. `mix`
computes recipes as today.

**Tuned on the three fixtures (issue 4).** The numbers are `paints.py` constants:
- Merge ceiling (step 3): **Delta E 12**. Without one, every fixture reached 10 only by losing a color on its last
  merges, at 13.3 to 17.6: the sailboat's hull red (into the reflection's brown, 16.3), the chickadee's leaf red
  (into the bark tan, 14.8), the lavender's sky blue, mountain blue-violet, and balloon teal (into one lilac, 13.3
  to 17.5). A ceiling of 13 kept those, but the merge just under it, the balloon's red into the clouds' coral
  (12.2), blocked the balloon in pink; so 12. Every merge at or under 11.1 reads right in the step pictures.
- Tint or shade (step 2): **Delta E 8, was 6**, the same as `mixing.REACHABLE`, the mixer's own line for a color
  the tubes can make. 8 adds one tint (the chickadee's feather edges, the wing's gray plus white) without calling a
  color a tint that "main plus white" can't really make. A paint within 8 of the main itself counts too ("a touch of
  white").
- Average error for the fewest colors (step 1): **Delta E 8**, unchanged. The fixtures all have steps, so it wasn't
  exercised on them.
- Hue family (step 4): **40 degrees**, unchanged; "real chroma" is **15** (Lab chroma), under which a paint is a gray
  in no family. With the ceiling, the hue rule marks nothing on the three fixtures; only the lightest-paint rule
  fires (each fixture's sun). It stays (a test covers it) for a lone-hue accent within 12 of another paint.
- Keep a name (step 5): **Delta E 3**, unchanged. Running `paints` on its own output changes no paint or step (a
  merged paint's sample spot can move).
- From what the fixtures showed: a part with one paint, measured with one k-means color, gets its *average*, and
  where its outline caught some of a neighbor that's a color on neither (the chickadee's white cheek came out gray,
  `#918780`, from its white and a little black cap). So a one-paint part's color must be real: at least **10%** of
  its pixels within Delta E 8 of it; if not, it's measured with more colors and the largest is kept. A merged paint
  is the two colors averaged in Lab, weighted by how much of the picture each covers, and keeps the id of the one
  covering more.

**What the fixtures came to** (hand-written paints, then base mixes; the step pictures match `docs/spikes/` by eye):
- **Chickadee**: 20 paints, **10** base mixes and 2 tints. The foliage's rust and orange merged (10.8, one part), so
  its two passes are one step: 18 steps, was 19. The leaves block in red.
- **Lavender balloon**: 22 paints, **14** base mixes and 1 shade. The mountains' two paints both merged into the
  lavender's blue-violet (11.0, 11.1), so the mountains are one step: 18 steps, was 19. The sky keeps its blue, the
  balloon its red and teal. What's left is 12.2 or more apart.
- **Red sailboat**: 16 paints, **13** base mixes and 1 shade (the sun path's olive, its gold plus blue). 14 steps,
  unchanged. The hull blocks in red. What's left is 12.9 or more apart (the sun path's gold and the sky's orange).

So a beginner lesson aims for 10 and lands at 10 to 14: the owner's rule (2026-11-12) is "aim for 10, but never
lose a visible color".

**Changed 2026-11-13: `paints` no longer churns.** In the three real runs, `paints` needed steps first (it measured
"as many colors per part as its steps name"), and every run re-merged from scratch: one run had its paints renamed
three times, and a fix for a texture jump failed three times because each rerun merged away the paint the new pass
had just been given. Now (`paints.measure`, `paints.add`):
- **A paint is measured in every part its `parts` lists.** A part listed by k paints is clustered into k colors
  and each paint takes one (an optimal match to its current hex); a paint in several parts is their colors averaged
  in Lab, weighted by how much of the picture each covers. That's also how a merge is measured.
- **First measurement** (the plan has no paints): each part gets the fewest colors (1 to 4) that leave its average
  error under Delta E 8, tints and shades are marked, and the paints merge toward `max_mixes` under the rules above
  (a same-part merge measures that part again with one color fewer). No steps needed; ids `<part>-<n>`, darkest
  first. Its `problems` don't list the missing stages.
- **Again** (the plan has paints; run it after `outline` changed the parts): every paint is measured again and
  keeps its `id`; its `name` and `used_for` when it moved under Delta E 3 (`KEEP_NAME`); and its `hex` and spot
  exactly when it moved under Delta E 1 (`SAME`), so running `paints` on its own result changes nothing (true of
  all three fixture plans, which didn't need re-saving). A part with no paint gets its fewest colors with the next
  free ids. A paint whose parts are all gone is removed, and the output names the steps that still use it. Steps
  are never changed. It prints what changed, what was kept, what's new, and what was removed.
- **Merging, from now on:** a paint a step uses is never merged away (it may take in a paint no step uses, keeping
  its id), and a paint `--add` made never merges. So `step_merges` is gone: steps are Claude's to choose.
- **`paints --add <part>`** gives one part one more color: the part is clustered into one more color than it has
  paints, its paints keep the clusters nearest them (a paint only this part has moves to its cluster; a shared one
  doesn't), and the color left over is a new paint, `<part>-<next free n>`, with `"added": true`. Nothing merges and
  no other part changes. When the left-over color is within Delta E 8 (`TINT`) of one of the part's paints, or is
  only a blend along the part's edges (fewer than 10% of its pixels near it), nothing is added and `problems` says
  so. It's how a pass is split in two, and how a part that took in a dropped part gets that part's color. Going over
  `max_mixes` this way is allowed and reported in `over_target`, never a problem.
- **The over-target rule** (`plan2.problems`) now reports going over `max_mixes` only while two base paints could
  still merge by `paints`' own rules: neither is an accent or `added`, they're at most Delta E 12 apart, and at most
  one of them is used by a step. The task asked for "not two paints used by different steps of the same part"; that
  would still flag two step-used paints in different parts, which `paints` must not merge, so "run paints again"
  would loop. The rule matches what the tool will do instead, which covers the split pass too.

## 10. Teaching content

### Cards, written once and checked by the owner

`techniques/strokes/<id>.yaml`: **one card per entry in the technique file's `stroke_results`** (28 today), each
linked to it by `stroke_result:` so the text review still judges strokes against that table. Built: 28 stroke
cards and 11 basics cards, `spike/cards.py` (load, check, and draw them), and `tools.py cards --out <file>` (one
page of them all for the owner). A plan's `stroke` is a card's id; `ls techniques/strokes` lists them. There is no
card for plainly filling a small flat shape, because the research doesn't cover it: use `build-from-pieces`.

```yaml
id: dabbing
stroke_result: Dabbing or stippling (round tip or stiff brush, little paint)
name: Dabbing
brushes: [old stiff flat, round bristle brush]
load: Dip only the bristle tips. Tap most of it off on a paper towel.
consistency: Thick, straight from the mix. No water.
motion: Hold the brush upright. Tap straight down and lift. Turn the brush a little between taps.
result: Ragged spots with gaps. More taps make it more solid.
then: Stop while the color underneath still shows.
mistakes:
  - mistake: Solid blobs instead of spots.
    why: Too much paint on the brush.
    fix: Wipe the brush and tap again. When dry, dab the under color back into the gaps.
practice: Try five taps on scrap paper first.
diagram: {title: "...", stages: [...]}   # same format as a step's `construct`
sources: ["acrylic-paint-along.md, section 4"]
checked: false   # true once the owner has read it
```

Every line comes from `docs/research/acrylic-paint-along.md` or the technique file, with the section in
`sources`. A field the research doesn't cover is **left out** and listed for the owner; nothing is filled from
the model's memory (`docs/decisions.md`, 2026-11-11). A card with `checked: false` shows "not checked yet" on the
page. A step's `stroke` must name a card; a stroke the library lacks is drafted in the lesson folder, shown as
not checked, and filed for the owner, the same rule as element techniques (#12).

`techniques/basics/<id>.yaml`: short cards for what every beginner needs once, in the same hand-checked way:
setting up (two water jars, a towel, the palette), rinsing between colors (fully before white or yellow), how
much water, keeping a mix wet between steps, fixing a mistake (let it dry, paint over), the ugly stage, colors
drying darker, stepping back. The technique file's `rules` already say most of these; the cards give them a
place on the page.

### Step text (`draft-text`, then Claude; issue 7 of 8)

`draft-text` writes into `text.json` every line that is data. Per step:

| Line | Comes from |
|---|---|
| "Let the \<stage\> dry." | this step's area overlaps paint from an earlier step that isn't part of the same `blend` |
| "Rinse well first." | this step's first paint is far in color (Delta E over 40) from the last step's, or is the lightest so far |
| Where | the part's outline: "inside the outlined area", plus two or three anchor points in inches from the canvas edges for an object ("its top is about 2 in from the top edge, 6 in from the left"). **No percentages in the text.** With no canvas size, quarters of the picture |
| Paints, in order | the step's `paints`, darkest first; for a `blend`, in order of position (top to bottom, or out from the light) |
| "Mix once for steps X to Y; cover it between." | the same paint is used in later steps |
| Brush, load, consistency, motion | the step's `brush` and its stroke card |
| What it should look like after | the stroke card's `result` |
| "Two or three thin coats." | the paint is lighter than what it goes over by more than 30 in lightness (the technique's light-over-dark rule) |
| Watch out | the stroke card's first `mistake`; the rest stay in the card |
| "Step back and look." | the last step of each stage |
| "Lightly chalk its outline first." (optional) | the first step of an `object` part with no parent |

**Built (#51): `spike/draft_text.py`, `draft-text --lesson`.** What it decided, row by row, from the fixtures:
- *Dry*: an earlier step's painted area covers 2% or more of this step's (`OVERLAP`; below that it's feathered
  edges). It names the two most recent such steps, each by its stage's name, or by its part's name when it's in this
  step's stage ("Let the black cap and bib dry", not "the chickadee" again), and adds the let-it-dry card's "A hair
  dryer on low speeds it up". Not "the same blend": a blend is one step, so only earlier steps count.
- *Rinse*: "the lightest so far" is the step's first paint being lighter (Lab L) than every paint before it; the
  first step never rinses. The wording is the clean-brush card's.
- *Where*: `aids.where_words` as is, except an area that touches all four edges is "the whole canvas" only when it
  covers 90% of it (`aids.WHOLE`): the chickadee's branch touches all four and was called the whole canvas.
- *Paints*: a blend's paints are ordered top to bottom by where each lands in the step picture. "Out from the light"
  isn't built: nothing in the plan says where the light is in a form a tool can read.
- *Mix*: on a paint's first use only, naming every later step ("for this step and steps 4, 7 and 10; cover it
  between them"); later uses rely on the page's "from step N, mix more if it has dried".
- *Brush, load, consistency, motion*: "Brush: <brush>. Load: <card load>", then the card's motion. **No card has a
  `consistency` field**; where the research gives one, the card's `load` already says it ("Wet and creamy"), so
  there's no separate consistency line. Cards with no `load` (9) or no `motion` (4) give no line for it.
- *Result*: "It should leave" plus the card's `result`; and, measured, "Leave what step N painted showing around these
  marks" when more than 10% of the part's earlier paint is unchanged after the step (the technique's rule: "each step
  ends by saying ... what should still show through").
- *Coats*: per paint, its lightness against the median lightness of the picture before the step where that paint
  lands. The light-over-dark card's words.
- *Watch out*: the card's first mistake with its why and fix. Cards with no `mistakes` (8 of 28) give none.
- *Step back*: the ugly-stage card's "Step back, squint, or take a photo ..." line.
- Card text longer than 40 words is split between sentences. The words around the data are constants at the top of
  `draft_text.py`, each naming the card or rule it comes from.
- Claude corrects a line by changing it and setting `"edited": true`; an edited line keeps its slot (the nth line of
  its kind) on every later `draft-text`, and an edited line with empty text takes the drafted line out (the page
  skips it). `draft-text` also never touches `summary`, `tip`, `construct`, `paint_notes`, or brushes Claude wrote
  for the same brush. It needs the step masks, so it runs `build_steps.build` itself (about 5 seconds).

Claude then writes, per step, `summary` (under 90 characters) and `tip`: one to three sentences only this
photo needs (which way the strokes run on this hill, which side the light is on, what to leave showing). Claude
reads each drafted line against the step picture and corrects any that reads wrong. `draft-text` never overwrites
what Claude wrote.

`text.json` for a version 2 lesson: `{"steps": [{"stage_id": "<step id>", "summary", "tip",
"lines": [{"kind": "dry|rinse|chalk|where|paints|mix|how|result|coats|watch|step-back", "text": "...",
"edited": false}], "brushes": [{"brush", "use"}], "stroke_cards": ["<card id>"],
"made_with": "composite:from-finish", "reason": "cut from the finish inside the part's outline"}]}`. The key stays
`stage_id` because `publish` and the history read it. `made_with` is the value v1 already uses for a step cut
from the finish, so the receipt, the site, and the history count it as free without changes.

**No word limit on a step.** The page shows a step's lines short and numbered, with everything longer one tap
away. `long_steps` isn't checked for version 2; `long_instructions` (40 words) stays, because a long line is two
moves. The technique file gains keys only version 2 reads, so v1 keeps working: `v2_step_range: [12, 24]`,
`v2_stage_range: [4, 9]`, `max_mixes: 10`, and `v2_rules` (the `rules` list with "2 to 5 short instructions per
step" replaced by "one move per step").

How much paint to mix needs a source the research file doesn't have. Until the owner measures it (a `human`
issue: how far a pea, a grape, and a walnut of paint go), the page says "mix more than you think you need".

### Teaching pictures (`step-aids`; issue 6 of 8), all free and all from the outlines

- **Where** (every step): the picture before this step, dimmed, with this step's area outlined. Drawn on the page
  as an SVG outline over the previous step's picture, so it adds no image. A light grid of quarters over it; the
  first screen tells the painter to mark the halves and quarters on tape along the canvas's edges (chalk on the
  canvas would be painted over by the sky).
- **Close-up** (a step whose area is under 20% of the picture): before and after, cropped to the area with a
  margin, with a finer grid. Built (#68): not when the area reaches across more than half the canvas's long side
  (scattered marks such as a sun path, a long branch), since the crop would be hardly closer; it starts open when the area is under 3%.
- **Paint map** (every `flat`, `pass`, and `blend` step with 2 or more paints, and the first step of each part):
  the part filled with flat patches, one per paint, numbered, with a legend in painting order. It replaces the
  hand-written `values` table. Built (#68): the first step's map shows all of the part's paints over the whole part;
  a part with only one paint gets no map (it would be the Where outline again). A blend's paints are numbered top
  to bottom.
- **Where, in words** (`aids.where_words`, built in #68, for `draft-text` to use): "Inside the outlined area", then
  for a band across the canvas the edges it reaches and where its other ends are, and for a thing its nearer top or
  bottom, its nearer side, and its size, in inches on the painter's canvas (to the half inch, the quarter under
  2 in), or against the halves and quarters on the tape when there's no canvas size.
- **Transfer outline** (once per lesson): the outlines of the `object` parts with no parent, as lines on the
  quarter grid at the canvas's shape. The stage that starts an object opens with an optional line: "Lightly chalk
  its outline first." (Owner, 2026-11-12: whatever helps beginners most. The paint-along stays sketch-free
  otherwise.)
- Construction diagrams (`construct`) stay, written by Claude.

## 11. The page (issue 6 of 8)

- Contents by stage, with each stage's step count. Steps numbered inside a stage and overall. The end of a stage
  is marked as a good place to stop. (No times: the research has no per-step durations to build them from.)
- A step, top to bottom: the picture with a Where / Result switch; the numbered lines and the tip when
  `text.json` has them (issue 7 writes them; until then the step's name); the paints with recipes; then folds: close-up, paint map, stroke card (open the first time a lesson uses it), diagram.
- "Before you start": the basics cards, the quarter marks, the transfer outline, the lesson's strokes to try on
  scrap paper.
- One self-contained HTML page per lesson, as now. Pages are 2.3 to 2.9 MB at 10 to 12 steps today; `publish`
  fails a version 2 page over 8 MB (step pictures at up to 900 px, close-ups at up to 600 px).
- Version 1 lessons render exactly as before.

## 12. Checks (`check`; issue 7 of 8)

`spike/checks.py` gathers `plan2.problems`, `outline.problems`, `build_steps.problems` (all built) and adds:
- `v2_step_range` and `v2_stage_range` from the technique; more top-level parts than `detail_budget.max_parts`;
- a stroke with no card; a brush `spike/brushes.py` doesn't know;
- `texture_jumps`, as today: no step turns more than 10% of the picture from flat to textured (fix: one more pass);
- a percentage in step text; a line over 40 words;
- the ones that stay: `paints_not_listed`, `duplicate_recipes`, `unreachable_paints`, `undocumented_diagrams`;
- (`max_mixes`, and a step whose paint doesn't list its part, are in `plan2.problems` from issue 4; the 8 MB
  page limit is in `publish` from issue 6; `check` reports them all in one list.)

`publish` runs `check`; `publish --final` won't seal a version 2 lesson while anything fails. Version 1 lessons
seal by the old rules.

**Changed 2026-11-13, from three real runs:** `check` prints `problems` (the same list as `failures`, kept for
`publish`), as every other v2 tool does. For version 2, `publish`'s own `texture_jumps` is `check`'s list
(`checks.texture_jumps`, no `flat` step), where it had listed a flat coat at 0.118 that `check` rightly leaves out.
The seal's messages name the v2 skill's step 7b for the text review, not v1's 6b. When `review.json` says
`"review_context": "same"` (the skill couldn't start a fresh reviewer), `publish` keeps it in `lesson.json` and
`known_problems.left` adds "The text review was done by the same session that wrote the text, not a fresh one." to
the lesson's Known problems. And the notes on the page (`lesson_notes.behind`) show a note of any shape (a string,
a list, or a dict) as text: `publish` crashed when `beginner_version` was a list.

**Built (#51): `spike/checks.py`, `check --lesson`, and `publish` (its result's `check` and `check_notes`).**
Decided while building it:
- `check` also reports what's left for Claude, so the list is the whole to-do: a step with no `summary` (or one over
  90 characters) or no `tip`, a step with no name, a paint with no `name` or `used_for`, a step with no drafted
  lines, and drafted lines that no longer match the plan and pictures ("run draft-text again"). The acceptance
  "draft-text then check leaves only name, summary, and tip" depends on these.
- *Strokes and brushes*: besides a stroke with no card and an unknown brush, a brush whose kind isn't one the card
  names (press-and-lift with a flat; the card says round). Added because the drafted text would say "Brush: 1/2 inch
  flat" and then "press so the belly spreads". It found 4 fixture steps; they were fixed in the plans (chickadee
  branch-dark to thick-to-thin, branch-light to a 1/2 inch flat; lavender clouds to small-circles, paths to
  toward-vanishing-point).
- *Texture jumps*: `texture_jumps` as today, but not on a `flat` step. A flat coat is flat by construction; what's
  measured there is the new edge, not texture (the chickadee's branch coat measured 13% from the branch's edges
  alone). It still fires on the fixtures where a pass really goes from flat to marks: **the sailboat's
  `water-light` (12%) and the lavender's `lavender-mid` (23%)**. Those are left for issue 8's plans to fix (another
  pass), not hidden by a higher threshold.
- *Outlines*: from `parts/stats.json`; a lesson with only `parts/owner.png` (the fixtures) is measured from it by
  `outline.owner_stats`, with no model confidence, and `check` says so in its notes.
- *`paints_not_listed`* matches a paint's name as a whole word. Version 1's regex had a literal backspace where
  `\b` was meant, so it never matched instruction text; version 1 keeps that, so its lessons seal as before.
- *Unreachable paints*: a failure until a step's `paint_notes` names the paint, as the seal already required (the
  lavender's balloon teal needs one). `mixes.json` missing or for other paints is a failure ("run mix").
- `publish --final` for version 2 lists the seal's own needs (reviews, notes) plus `check`'s failures; the publish
  counts `check` already reports aren't listed twice.

The fresh-context text review (`step-review.md`) stays, once per lesson, on the `step-pairs` sheets. For version
2 its kinds `drift`, `shape_change`, and `split_edge` go (they can't happen). `too_much` is now fixed, not
recorded: split the step in the plan and run `build-steps` again.

## 13. Version 2 lessons through `publish` (issue 3 of 8)

`load_plan` validates against the version 1 model (`LessonPlan` in `spike/run.py`), and `publish`, `mix`,
`seal_problems`, `step_paths`, `step-pairs`, the page, the history, the embed, and the notes all read version 1
fields. The rule for version 2: **`lesson.json` keeps every key those readers use, with the same types, and adds
new keys beside them.** Then nothing downstream has to change to keep working.

Each entry of `lesson.json`'s `stages` (one per step, flat, as today):

| Key | Type today | Version 2 value |
|---|---|---|
| `id`, `name`, `image` | strings | the step's `id`, `name`, and `NN_<id>.png` |
| `steps` | list of strings (the instructions) | the text of each of `text.json`'s `lines`, in order; with no text yet, `[name]` |
| `lines` | *new* | the `lines` dicts (`kind`, `text`), for the page |
| `summary`, `watch_out`, `paint_notes` | string, lists of strings | from `text.json`; `watch_out` is the text of the `watch` lines |
| `paints` | string (what the step adds) | the part's `name` |
| `colors` | list of paint dicts | the step's paints, looked up by id, in the same dict shape (`name`, `hex`, `recipe`, ...) |
| `brushes`, `brush_list` | string, list of `{brush, use}` | the step's `brush`; `text.json`'s `brushes`, or `[{"brush": <brush>, "use": <name>}]` |
| `strokes` | list of `{name, how}` | one per stroke card: its `name` and `motion`. With no card yet, `{"name": <the step's stroke id>, "how": ""}` |
| `stroke_cards` | *new* | the card ids |
| `made_with`, `reason` | strings | `composite:from-finish`, and why |
| `part`, `show`, `group` | *new* | from the plan; `group` is the plan stage's id |

Top level: `plan_version: 2` and `groups` (the plan's stages: `id`, `name`, step ids) are new.
`photo_read.components` is the names of the parts with no parent.

Elsewhere:
- **Paints.** The mixer keys paints by name and reads `name`, `hex`, and `recipe`. Build it a version 1 paint
  for each version 2 paint (`recipe` empty until `mix` fills it). A paint with no `name` yet uses its id.
  `sample_swatches` is skipped: the hex is measured.
- **`step_paths`:** `NN_<id>.png` for every step (the last is a copy of the finish, as `build-steps` writes it).
- **Seal:** `review.json` needs `finish_issues` and `text_issues`, not `review_issues`; steps don't need `regions`;
  `long_steps` isn't checked (`publish` doesn't list them); each step's `text.json` entry needs `summary`, `lines`,
  `brushes`, and `made_with`, where version 1 needs `strokes` in place of `lines` (version 2's text.json has no
  `strokes`: they come from the plan's `stroke` and its card); everything else as today.
- **A paint's version 2 keys** (`id`, `parts`, and later `of`, `plus`) stay on its dict in `lesson.json` beside the
  version 1 ones. A name two paints share gets the id after it, since the mixer keys paints by name.
- **`paid_renders`** counts what the ledger holds: the finish, the beginner version, the canvas extend, the
  background.
- **History:** `minutes_total` joins the metrics for every run: minutes from the run folder's
  `_YYYYMMDD-HHMMSS` (`history.RUN_TIME`) to the time of that publish; left out when the folder name has no time.

Version 1 must not change. There's no version 1 lesson in the repo to test with, so issue 3 first commits one as
a fixture (a small plan, text, and pictures, made by hand or cut down from a real run's folder), publishes it
before touching anything, saves that `lesson.json` as the expected result, and compares ignoring the keys that
carry the time, commit, and version (`gesso`, `calls`, `provenance`).

## 14. Build order and the gate

One issue per row, in this order. Don't start one before the ones it needs are closed.

| | Issue | Needs | Who |
|---|---|---|---|
| 1 | Outlines and step pictures from them (#62) | | **done**, 2026-11-12 |
| 2 | The background picture: one render for what's behind large objects (#64) | 1 | **done**, 2026-11-12 |
| 3 | Version 2 lessons through `publish`, the history, and the page (#65) | 1 | |
| 4 | Paints measured from the finish, with a limit on mixes (#66) | 1 | |
| 5 | Stroke cards and basics cards (#67) | | **done**, 2026-11-12; the owner still has to read and check them |
| 6 | Teaching pictures and the lesson page (#68) | 3, 5 | |
| 7 | Step text from data, and measured checks in place of the reviews (#51) | 3, 4, 5, 6 | |
| 8 | The v2 skill, three hands-off runs, and the gate (#69) | all | needs a key and the source photos; the owner scores |

Issues 3, 4, and 5 don't depend on each other. Issues 3 to 7 need no API key and no model files: the three
fixtures (`spike/tests/fixtures/`: finish, plan, and saved outlines for each) are enough, and
`spike/tests/test_pipeline_v2.py` shows how to load them.

**The gate (issue 8).** Run the v2 skill hands-off on the chickadee, the red sailboat, and the lavender balloon.
v2 replaces v1 only if all of these hold and the owner agrees after looking:

| Measure | v1 (from `site/history/`) | v2 must be |
|---|---|---|
| Renders per lesson | 13 to 21 | the finish, plus at most 3 (beginner version, canvas extend, background) |
| Image cost per lesson | $0.40 to $0.51 | $0.25 or less (the chickadee's fixed renders alone were $0.18 in v1) |
| Time, start to seal (`minutes_total`) | 21 and 27 minutes | 15 minutes or less, reported per phase so the slow part is known |
| Drift, shape, and split-edge problems | 5 left on the chickadee's page | 0 (they can't happen). Any other `left` explained |
| Steps | 10 to 12 | 12 to 24, in 4 to 9 stages |
| Same finish and plan, built twice on one machine | different pictures every run | identical bytes |
| Same finish, planned twice from scratch | never measured | reported: how much the parts and steps differ. Not a pass or fail yet |
| Owner's score, per lesson and for each lesson's weakest stage | each v1 run's score | not lower than v1 on any |

Time is a target, not a reason to cut a step a beginner needs ("Slow is fine", `docs/decisions.md`).

If the gate passes: remove `lock.py`, `from_finish`'s tool (keep the functions `build_steps` imports),
`lock-steps`, `carry-forward`, `finish-from-step`, `split-texture`, `render-step`, the throwaway-filter rules,
the v1 skill steps for rendering, review, and lock, and their tests. If a merged or dropped part's stage scores
below v1's: keep v2 and write up which kind of part failed; the fallback to try next is one render for that stage,
pasted only inside its part. If it fails more widely: stop and report to the owner.

## 15. Rules for whoever builds this

- One issue at a time, in order. Read this file, the issue, `docs/spikes/outlines.md`, and `docs/decisions.md`.
- Look before you build: Read a fixture's plan and its contact sheet in `docs/spikes/`.
- New code goes in new files with a subcommand each in `spike/tools.py`, like `outline`. Reuse `outline.py`,
  `build_steps.py`, and `from_finish.py`'s functions; don't copy them.
- Every tool gives the same output for the same input on one machine. Fix every random seed. Don't promise the
  same bytes across machines.
- Every tool has tests that run with no network, no model files, and no API key.
- Sizes are shares of the picture, never pixels: fixtures are 1000 x 786 and real finishes are bigger.
- A real finish is in the image model's frame; the painter's canvas is a crop of it (`canvas.json`,
  `canvas-view`). Boxes and outlines are in the frame. Inches, the transfer outline, and anything the painter
  measures are in the canvas.
- Every number here called a starting value is tuned on the three fixtures by the issue that owns it, and the
  final value is written back here in the same commit.
- If a rule here turns out wrong, change this file in the same commit as the code and say why. Don't quietly do
  something else.
- Don't raise render quality, add renders, or add a review round to fix a problem. If a free tool can't do it,
  drop the part (section 6) or report it.
- Version: issues 2 to 7 add tools next to v1 and don't change what a v1 lesson contains, so they leave
  `spike/VERSION` alone and add one line each under a "Pipeline v2 (in progress)" heading at the top of
  `docs/changelog.md`. Issue 8 sets **POC 1.0.0** with the first sealed v2 lesson, once the gate
  has passed (owner, 2026-11-12: this is a big enough change for the major number).
- Each issue covers a few tightly linked things on purpose (a tool, its checks, and its place on the page). That's
  an exception to "one issue per item" in `docs/backlog.md`, made so that each issue leaves something that works.

## 15a. What the first six hands-off runs changed (2026-11-13)

Three runs with the strongest model and three with Opus, on the three test pictures, all sealed. What they
changed in the tools, beyond the fixes already described in sections 6, 7, and 9:
- **The background picture is matched to the finish around each hole** (`build_steps.make_background`), not by
  one shift for the whole picture: a render's sky and water come back off by different amounts, and one shift left
  a tinted sail-shaped patch in the sky. Pixels where the two differ a lot aren't used for matching: they're a
  leftover of the object.
- **Over a flat coat, a pass leaves its children's places as the coat** until the child's own step. A carried
  fill there showed as a blurred patch in every step in between.
- **An area is always behind**, wherever it's listed (`build_steps.back_parts`). A lavender field listed after
  the tree was taken out by the background render.
- **The texture rule is for a `full` step only** (`checks.texture_jumps`): a part finished in one step. A coat is
  flat by construction, and a pass is one paint in one stroke, which is how texture is taught. Holding passes to
  it cost three runs about 8 minutes each with no clean fix.
- **A part's last step may add little** (`build_steps.problems`): light tips go last.
- **A tint stays a tint** when `paints --add` gives its part another color.

Still open after these runs: time (17 to 27 minutes, against a 15-minute target; the checking and review step is
6 to 10 of them); no agent could start a fresh reviewer, so every text review was done in the same session; small
things (an eye, a beak) can't be parts; three stroke cards are missing (#71).

## 15b. The gate runs (2026-11-13)

Opus, hands-off, on the final skill and tools, from 900 px copies of the three source pictures. All three sealed.

| Measure | v1 | Target | Red sailboat | Chickadee | Lavender balloon |
|---|---|---|---|---|---|
| Renders | 13 to 21 | finish + 3 at most | 1 (finish from the cache) | 2 | 3 |
| Start to seal | 21 to 27 min | 15 min | 16 min | 16.6 min | 20 min |
| Steps (stages) | 10 to 12 | 12 to 24 (4 to 9) | 17 (6) | 17 (6) | 21 (6) |
| Base mixes | up to 16 | aim for 10 | 12 | 12 | 15 |
| Drift, shape, split-edge problems | 5 on the chickadee | 0 | 0 | 0 | 0 |
| Same finish and plan, built twice | differs | identical | identical (tested) | identical | identical |

- **Met:** renders, steps, drift, and the same-bytes rule. Image cost was a fifth to a third of v1's on every run.
- **Not met:** time, by 1 to 5 minutes. The check-and-review step is 3 to 8 of them. Sonnet ran the same skill in
  9 to 16.5 minutes with weaker plans.
- **Not met:** a text review in a fresh context. The runs were made by agents that can't start another, so each
  reviewed its own text and each page says so. A run started by the owner can start one.
- **Left on the sealed pages:** outline leaks on the chickadee's branch; on the lavender, soil bits painted on
  bare canvas for eleven steps. The second is fixed in the tool (`outline.drop_islands`) and checked by rebuilding
  that lesson's plan; the sealed lesson itself still has it.
- **Planned twice from scratch** (the two Opus runs of each picture): the same stages in the same order, 17 against
  17, 17 against 17, and 24 against 21 steps; different finishes, so pictures aren't comparable pixel for pixel.
- **The owner's score:** not given yet. The gate isn't passed until it is, and nothing of v1 is removed before.

## 16. Known risks

| Risk | What limits it |
|---|---|
| The background render doesn't come back clean on some picture (it did on all three tried). | Only its pixels behind the objects are used, color-matched, and it's checked. If it still shows, the free fill stays and the lesson says so under Known problems. |
| Claude's parts need more than 2 rounds. | Tools are free and take seconds, and the fix table in section 6 covers what went wrong in the spike. Issue 8 measures it. |
| A pass by nearest paint doesn't match how the area is really painted. | Splitting and reordering passes is free; the text review's `wrong_result` and `flat` kinds still catch it. |
| The finish is more detailed than a beginner can paint, and v2 copies it faithfully. | Unchanged from v1: the beginner version and `detail_budget`. Not made worse. |
| 12 to 24 steps is a long session, and mixes dry between steps. | Stages with stopping points; "mix once for steps X to Y"; steps on the same paint kept next to each other. |
| Paints measured by clustering lose a small accent or give muddy averages. | The accent rule (section 9); the owner's score at the gate. |
| The outline model is 108 MB and runs only where the lesson is made. | Viewing a lesson needs nothing: the site is static pages. An app would need a hosted model later; out of scope for the POC. |
