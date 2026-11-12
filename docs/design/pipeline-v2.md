# Pipeline v2: paint the finish once, cut every step from it

Design, 2026-11-12. The owner approved the direction the same day (`docs/decisions.md`, "Pipeline v2"). This file
is the plan the build issues point at. If an issue and this file disagree, this file wins; fix the issue.

**Read this whole file before starting any pipeline v2 issue.** Each issue builds one section of it.

Words used here:
- **finish**: the finished painting, `99_finish.png`. Rendered once by the image model.
- **part**: one thing or area in the finish (the sky, the far hill, the bird, one leaf).
- **outline**: a part's exact shape, one black and white picture per part (white where the part is).
- **stage**: a group of steps that paint one part or one area ("The bird"). What a lesson's contents list shows.
- **step**: one small move: one brush, one kind of stroke, usually one or two paints.
- **render**: a paid call to the image model. Everything else is a free tool run on the painter's computer.

## 1. Why change

Measured on the lessons in `site/history/` (v1 is the pipeline up to POC 0.26.1):

| Problem in v1 | Evidence |
|---|---|
| Every step picture is its own render of "the finish with later parts not painted". The image model moves things between renders. | Chickadee: 21 paid renders for 11 steps, $0.51, 5 redos, and 5 drift problems still listed under Known problems. Sailboat: 13 renders, $0.40, 4 redos. |
| Most of a run is repair, not teaching: two image review rounds, redos, `lock-steps`, `carry-forward`, `split-texture`. | The ledger's render time is 4 to 7 minutes of a run the owner times at over 20. |
| Splitting a step costs a render, so steps stay too big. | Chickadee step 10 "Shade the feathers" was flagged "five kinds of moves in one step" and left. The bird goes from a flat shape to finished feathers in one step. |
| The skill caps detail: about 100 words per step, 2 to 5 instructions, and it tells Claude to cut. | `steps/6-text.md` "Keep it short"; `STEP_WORDS` and `INSTRUCTION_WORDS` in `spike/tools.py`. |
| Placement is given as numbers with nothing to measure against. | "paint the body as one big round: 37% to 60% across, 28% to 56% down". |
| Teaching content (how to do a stroke, how to load the brush) is written fresh each run. | The same stroke is described differently in every lesson; the chickadee asks for 16 mixes from 14 tubes. |

The owner's words (2026-11-12): not enough detail for new painters; use tools and filters instead of inference or
image generation wherever they give good results; save cost but never at the expense of quality; don't raise the
image model's quality setting (no clear gain in the lessons, and the cost wasn't sustainable).

## 2. The idea

Render the finish once. Find each part's outline with a free local tool. Build every step picture by laying the
parts back on a white canvas in painting order, and build the in-between steps of a part with filters (flat coat,
then dark, middle, and light passes). Nothing can drift, because every step is cut from the same picture. Splitting
a step is free, so steps can be as small as a beginner needs. The same outlines give free teaching pictures: where
to paint, a close-up, which paint goes where.

Evidence that outlines work: `docs/spikes/outline-probe.md` (read it; it includes working code).

## 3. What stays, what changes, what goes

| | v1 | v2 |
|---|---|---|
| Photo check, crop, canvas fit, beginner version | step 0 | **stays as is** |
| Simplified reference, finish render, finish check | steps 1-2 | **stays as is** |
| Plan | steps with `regions` boxes | **changes**: parts, stages, small steps (section 5) |
| Step pictures | one render per step | **changes**: cut from the finish (sections 6-8) |
| Image review rounds 1 and 2, redos | step 5 | **goes** (replaced by pixel checks, section 11) |
| `lock-steps`, `carry-forward`, `finish-from-step`, `split-texture`, throwaway filter scripts | steps 5b, 6a, 6b | **go** |
| Paints | named and placed by Claude | **changes**: measured from the finish, named by Claude (section 9) |
| Mix recipes (`mix`, Mixbox) | computed | **stays as is** |
| Step text | written from scratch | **changes**: built from data and stroke cards; Claude adds what's specific to the photo (section 10) |
| Text review in a fresh context | step 6b | **stays**, smaller (section 11) |
| Construction diagrams | step 7 | **stay** |
| Notes, seal, publish, history, site | steps 8-9 | **stay**; checks updated |

Renders left in v2: the finish (high quality), the beginner version when needed, the canvas extend when needed,
and at most 2 "hidden area" renders (section 7). Nothing else is rendered.

**Nothing in v1 is deleted until the gate in section 13 passes.** v2 is built next to v1 as new files and new
subcommands. Old lessons and `site/history/` must keep working.

## 4. The run, start to end

| # | What | Who | Reads | Writes |
|---|---|---|---|---|
| 0 | Set up, check photo, fit canvas, beginner version | Claude + tools, as v1 | photo | `00_*.png`, `notes.json` |
| 1 | Reference and finish | filters, 1 render, as v1 | photo | `00_reference.png`, `99_finish.png` |
| 2 | List the parts | Claude | finish + `grid --percent` | `plan.json` `parts` |
| 3 | Outline the parts | tool `outline` | `plan.json`, finish | `parts/<id>.png`, `parts/preview.jpg`, `parts/owner.png` |
| 4 | Look at the preview once, fix boxes | Claude | `parts/preview.jpg` | `plan.json` (at most 2 fix rounds per part) |
| 5 | Paints | tool `paints` + Claude names them | finish, outlines | `plan.json` `paints` |
| 6 | Stages and steps | Claude, inside the technique's rules | parts, paints | `plan.json` `stages` |
| 7 | Step pictures | tool `build-steps` | all of the above | `NN_<id>.png` for every step |
| 8 | Teaching pictures | tool `step-aids` | steps, outlines | `aids/NN_<id>_where.jpg`, `_zoom.jpg`, `_map.png`, `transfer.png` |
| 9 | Text | tool `draft-text` + Claude | plan, stroke cards | `text.json` |
| 10 | Checks | tool `check` (also inside `publish`) | everything | a list of failures, each with a fix |
| 11 | Text review | fresh subagent, once | `step-pairs` sheets | `review.json` `text_issues` |
| 12 | Diagrams, notes, seal, publish | as v1 | | the sealed lesson |

Claude makes judgment calls at steps 0, 2, 4, 5 (names only), 6, 9, 11, 12. Everything that can be measured is.

## 5. The plan file (`plan.json`, version 2)

`"plan_version": 2` at the top. Fields not listed here keep their v1 meaning (`photo`, `technique`, `subject`,
`focal_point`, `light`, `palette`).

```json
{
  "plan_version": 2,
  "parts": [
    {"id": "sky", "name": "Sunset sky", "kind": "area", "box": [0, 0, 1, 0.47],
     "covers": [[0, 0, 1, 0.62]], "points_in": [], "points_out": []},
    {"id": "mountains", "name": "Far mountains", "kind": "area", "box": [0, 0.36, 1, 0.54], "covers": []},
    {"id": "bird", "name": "The chickadee", "kind": "object", "box": [0.12, 0.08, 0.63, 0.78]},
    {"id": "bird-cap", "name": "Black cap and bib", "kind": "object", "parent": "bird", "box": [0.38, 0.11, 0.58, 0.30]},
    {"id": "branch", "name": "The branch", "kind": "thin", "box": [0, 0, 1, 1],
     "path": [[0.05, 0.0], [0.08, 0.6], [0.4, 0.7], [0.95, 0.9]], "width": 0.06}
  ],
  "paints": [
    {"id": "p1", "name": "Sunset gold", "hex": "#e8a53a", "used_for": "the glow around the sun",
     "sample_x": 0.4, "sample_y": 0.2, "parts": ["sky"]}
  ],
  "stages": [
    {"id": "sky", "name": "The sky", "parts": ["sky"],
     "steps": [
       {"id": "sky-blend", "name": "Blend the sunset sky", "part": "sky", "show": "full",
        "stroke": "x-stroke", "brush": "1 inch flat", "paints": ["p1", "p2"], "tip": "..."}
     ]},
    {"id": "bird", "name": "The chickadee", "parts": ["bird", "bird-cap"],
     "steps": [
       {"id": "bird-shape", "name": "Block in the body", "part": "bird", "show": "flat", "stroke": "build-from-pieces", "brush": "1/2 inch filbert", "paints": ["p9", "p10"]},
       {"id": "bird-cap", "name": "Paint the cap and bib", "part": "bird-cap", "show": "full", "stroke": "fill", "brush": "#6 round", "paints": ["p11"]},
       {"id": "bird-dark", "name": "Shade the belly", "part": "bird", "show": "pass", "pass": [1, 3], "stroke": "curved-strokes", "brush": "#6 round", "paints": ["p12"]},
       {"id": "bird-mid", "name": "Wing feathers", "part": "bird", "show": "pass", "pass": [2, 3], "stroke": "pull-and-taper", "brush": "#2 round", "paints": ["p13"]},
       {"id": "bird-light", "name": "Light the chest", "part": "bird", "show": "pass", "pass": [3, 3], "stroke": "curved-strokes", "brush": "#6 round", "paints": ["p14"]}
     ]}
  ]
}
```

### Parts

Listed **back to front**: the order they're painted. A later part is in front of an earlier one.

- `kind` decides how the outline is found (section 6):
  - `area`: a big region with a visible edge (sky, hill, field, water, a wall).
  - `object`: a compact thing with a clear edge (a bird, a boat, a balloon, one leaf, the sun).
  - `thin`: long and narrow (a branch, a mast, a fence rail, a path). Needs `path` (points along its middle, 0-1)
    and `width` (its widest thickness as a share of the picture's width).
  - `soft`: no real edge (mist, haze, far foliage, glow, a reflection's blur).
- `box`: `[x0, y0, x1, y1]`, shares of width and height, **measured with `grid --percent`**, a little loose
  (2 to 3% bigger than the part on each side).
- `covers` (optional, `area` and `soft` only): boxes where the painter lays this part's paint, including where
  later parts will go over it. A sky that should run past the horizon lists a box that reaches below it. If
  left out, the part covers its own outline plus anything in front of it inside its `box`.
- `parent` (optional): this part sits on another part and is painted during the parent's stage (cap on the bird,
  windows on a house). A child is always later in the list than its parent.
- `points_in` / `points_out` (optional): `[x, y]` points that must be inside or outside the outline. Use them only
  to fix an outline after looking at the preview.
- The technique's `detail_budget.max_parts` limits parts without a `parent`.

### Stages and steps

- A stage groups the steps for one part or a few parts painted together. Stages are in painting order.
- A step paints inside **one** part. `show` says what the step picture shows for that part:
  - `flat`: the part as flat color, its paints only, no texture (a base coat or block-in);
  - `pass` with `"pass": [k, n]`: pass k of n over a part that has a `flat` step first. Marks arrive by value,
    darkest first. After pass n of n the part looks exactly like the finish;
  - `full`: the part exactly as in the finish, in one step. Only for a part one move can make (a blended sky, a
    flat hill, a sun disk, a small one-color child part).
- Rules the `check` tool enforces:
  - every part has at least one step, and its last step is `full` or pass n of n;
  - a part with texture (measured: section 11, `texture_jumps`) has `flat` then at least 2 passes;
  - a step uses one stroke and one brush; at most 3 paints;
  - the last stage ends with a step that adds the smallest details, and the picture after the last step is the
    finish, pixel for pixel;
  - step ids are unique lowercase slugs.
- Step count: the technique's `step_range` becomes `[12, 30]` for the beginner paint-along, with `stage_range`
  `[5, 10]`. More small steps are better than fewer big ones (owner, 2026-11-12).

## 6. Outlines (tool: `outline`)

`python spike/tools.py outline --lesson <lesson>` reads `plan.json` `parts` and the finish, and writes
`parts/<id>.png` (white = the part), `parts/owner.png` (which part owns each pixel), `parts/preview.jpg` (the
finish with every part tinted and labeled, to Read), and prints one line of numbers per part.

How each kind is found:

| Kind | Method | Status |
|---|---|---|
| `object`, `area` | SAM (quantized ONNX, CPU) with the part's `box`, plus `points_in`/`points_out` when given. | **Checked** in the probe: clean on 13 of 13 such parts. |
| `thin` | The `path` drawn at `width` as a starting shape, then OpenCV GrabCut (the path's center line is sure foreground, far from the path is sure background). | **Not checked.** #62 tests it on the chickadee branch. |
| `soft` | No outline model. Among the pixels no `object`, `area`, or `thin` part took, inside the part's `box`: each pixel goes to the soft or area part whose paints it is closest to in color (the logic already in `from_finish.owners`). | **Partly checked** (it is how the lavender dabs are split today). #62 tests it on the chickadee's mist and foliage. |

Then, for every pixel:
1. If more than one outline claims it, the **later** part wins (it's in front). A child wins over its parent.
2. If no outline claims it, it goes to the nearest part's outline (the probe left 8% of pixels unclaimed, all thin
   gaps between neighbors).
3. Remove specks: any piece of a part smaller than 0.05% of the picture goes to the part around it.

Numbers printed per part, and what `check` does with them:
- SAM's confidence. Below 0.80: fail, "fix the box or add points".
- Share of the `box` the outline fills. Under 15% or over 98% for an `object`: fail (it took the background, or
  missed).
- Number of separate pieces. More than 3 for an `object`: fail.

Claude Reads `parts/preview.jpg` **once** after the tool runs and fixes any part that is visibly wrong (a box, a
point). At most 2 fix rounds per part.

**When a `soft` or `thin` part still won't come apart after 2 rounds, don't fake it and don't render it. Merge
it** into the part behind it (delete the part, widen the other part's `box`), and teach that area as a `flat` coat
and passes. Record it in `notes.json` under `merged_parts` with the reason. A misty background painted as one
coat and three passes is a normal way to teach it; a wrong outline is not.

The model files (108 MB) are downloaded once to `models/` (git-ignored) by `outline` itself on first use, from the
URLs in the probe. `onnxruntime` is added to `spike/requirements.txt`. No PyTorch.

## 7. Hidden areas (painting straight through)

Painting back to front, the sky is painted straight through where the bird will sit. The finish doesn't show that
sky. A step picture has to show something there until the bird's stage covers it.

A part's **painted area** = its own pixels + the pixels of later parts that fall inside its `covers` (or, with no
`covers`, inside its `box` and enclosed by it). The second group is the hidden area. Fill it, in this order:

1. **Free fill** (default): `from_finish.row_paint` for parts that run in bands (skies, water, fields: any `area`
   wider than 60% of the picture), `from_finish.continue_paint` otherwise, plus the brush texture borrowed from
   beside the hole (`borrowed_marks`). These exist and are tested.
2. **One render** ("plate"), only when the free fill fails the ghost check below:
   `render --step plate-<part id> --inputs 99_finish.png --quality low --prompt "<what to remove>. Paint what is
   behind them, continuing the <part name> exactly as it is around them. Change nothing else." ...`
   The tool then pastes **only the hidden area** from the render into the fill (feathered 3 pixels, and its
   average color matched to a ring 12 pixels wide around the hole). Nothing outside the hidden area can change,
   so a plate cannot cause drift.
3. If the plate also fails the check, keep the free fill and record it in `review.json` as `left`.

**Ghost check** (measured, per hidden area bigger than 1% of the picture): compare the fill with the ring around
it. Fail when the fill's average color differs from the ring's by more than Delta E 8, or when an edge detector
finds an edge along more than 30% of the hole's border (the hole's shape shows). These two numbers are starting
values; #63 tunes them on the three test lessons and writes the final values here.

Limit: 2 plates per lesson, low quality. The lesson's render cap (`--max-cost`) drops from $1.00 to $0.40.

Hidden areas matter less than they seem: each one is only visible until the part in front is painted. The bar is
"doesn't look wrong", not "looks finished".

## 8. Step pictures (tool: `build-steps`)

`python spike/tools.py build-steps --lesson <lesson>`. No renders. Start from a white canvas (`CANVAS` in
`from_finish.py`). For each step in order, change only the pixels of its part's painted area:

- `full`: the finish inside the part's own pixels, the hidden fill (section 7) inside its hidden area.
- `flat`: `from_finish.flat_paint` over the painted area, snapped to the step's paints. No texture.
- `pass [k, n]`: split the part's own pixels into n groups by lightness (darkest group first, equal shares, as
  `split_passes` does). After pass k, groups 1 to k show the finish and the rest still show the flat coat.
- Child parts: a parent's `flat` and `pass` steps cover the child's pixels too (flat color or the pass, never the
  child's detail). The child's own step then shows the finish there.
- Edges are feathered by about 1 pixel so parts don't look cut out with scissors.

Write `NN_<step id>.png` (NN from 01, counting steps across all stages). The last one is copied from the finish.

By construction: a step never changes anything outside its part; a part never changes shape; the last picture is
the finish. There is nothing to review, redo, or lock.

## 9. Paints (tool: `paints`)

`python spike/tools.py paints --lesson <lesson>` measures the paints from the finish:

1. For each part without a parent, cluster its pixels' colors (k-means in Lab). k is 1 for a part whose colors
   vary little, up to 3 for a part with clear dark, middle, and light. Child parts get 1.
2. Merge the two closest paints across the whole lesson while there are more than the technique's `max_mixes`
   (new field, **10** for the beginner paint-along; owner, 2026-11-12) or any two are within Delta E 6.
3. Write each paint's `hex`, a sample spot (`sample_x`, `sample_y`: a flat patch of that color), and its `parts`.

Claude then gives each paint a `name` and `used_for`, and nothing else. `mix` computes recipes as today.

A step's `paints` must come from its part's paints. `flat` uses the part's most common paint (two when the part
has two clear color areas, like the bird's buff body and gray wing); passes use the others, darkest first.

## 10. Teaching content

### Stroke cards (`techniques/strokes/<id>.yaml`)

One hand-checked file per stroke, written once from `docs/research/acrylic-paint-along.md` (every card cites the
research sections it comes from; technique never comes from the model's memory). The first set is the technique
file's `brush_moves` and `stroke_results`: `x-stroke`, `side-to-side-blend`, `dabbing`, `pull-and-taper`,
`flicking`, `dry-brush`, `horizontal-strokes`, `liner`, `build-from-pieces`, `curved-strokes`, `fill`.

```yaml
id: dabbing
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
    fix: Wipe the brush and tap again. Let it dry and dab the under color back in the gaps.
practice: Try five taps on scrap paper first.
diagram: {title: "...", stages: [...]}   # same format as a step's `construct`
sources: ["acrylic-paint-along.md section 4"]
```

The page shows a stroke's whole card, open, the first time a lesson uses it, and as a one-line link back to it
after that. A stroke with no card can't be used in a plan: `check` fails and names it. A stroke the library
lacks is written as a draft card in the lesson folder, marked "not checked yet" on the page, and filed as an issue
for the owner to check (same rule as element techniques, `docs/decisions.md` 2026-11-10).

### Step text (tool: `draft-text`, then Claude)

`draft-text` fills in everything that is data. For each step:

| Line | Comes from |
|---|---|
| "Let the \<stage\> dry." | measured: this step's area overlaps an earlier step's area that isn't the same wet blend |
| Where to paint | the part's outline: its bounding box in words and inches from the canvas edges ("starts about 4 in from the left and 2 in from the top, about 5 in wide"), and "the outlined area in the picture". **No percentages in the text.** |
| Which paints, in what order | the step's `paints`, darkest first |
| How much to mix | the step's area in square inches and the technique's `amounts` table (below) |
| Brush, stroke, load, consistency, motion | the step's `brush` and its stroke card |
| What it should look like after | the stroke card's `result` |
| Watch out | the stroke card's `mistakes` (the first; the rest sit in the card) |

Claude then adds, per step: `name`, `summary` (under 90 characters), and `tip`: one to three sentences only this
photo needs (which way the strokes run on this hill, where the light side is on this bird, what to leave
showing). Claude also checks every drafted line against the step picture and fixes any that reads wrong.

**No word cap on a step.** The page shows a step as short numbered lines (what `draft-text` wrote plus the tip),
with everything longer one tap away: the stroke card, the paint map, the close-up. `STEP_WORDS` and `long_steps`
go; `INSTRUCTION_WORDS` (40) stays for single lines, because a long line is two moves.

`amounts` is a new table in the technique file: area in square inches to a size a beginner knows ("a pea", "a
grape", "a walnut"). Its numbers need a cited source in the research file or the owner's own measurement; until
then the page says "mix more than you think you need" and gives no size.

### Teaching pictures (tool: `step-aids`), all free

- **Where** (`aids/NN_<id>_where.jpg`, every step): the picture *before* this step, dimmed, with this step's area
  outlined in a bright line and a light grid of quarters. The lesson's first screen tells the painter to chalk
  small marks at the halves and quarters of their canvas edges so the grid means something.
- **Close-up** (`_zoom.jpg`, when the step's area is under 20% of the picture): before and after, cropped to the
  area with a margin, at full resolution.
- **Paint map** (`_map.png`, every `flat` and `pass` step and any step with 2 or more paints): the step's area
  filled with flat patches, one color per paint, numbered, with a legend, dark to light. It replaces the
  hand-written `values` table.
- **Transfer outline** (`aids/transfer.png`, once per lesson): the outlines of every `object` part without a parent,
  as lines on the quarter grid, at the canvas's shape. The stage that starts an object opens with an optional
  line: "Lightly chalk the outline first, from the transfer picture." (Owner, 2026-11-12: whatever helps beginners
  most; this changes the paint-along's "no sketch" rule to "no sketch, except an optional chalk outline of an
  object".)
- Construction diagrams (`construct`) stay as they are, written by Claude in the diagrams step.

## 11. Checks

`check` runs inside `publish` and on its own. Every failure names the step or part and says what to change.

Measured on every run (replacing the image reviews and the lock):
- outline numbers (section 6) and the ghost check (section 7);
- every plan rule in section 5;
- **coverage**: each step changes at least 60% of its painted area and nothing outside it;
- **no canvas left**: after a part's last step, under 0.5% of its painted area is still canvas white;
- **texture_jumps**: as today, no step turns more than 10% of the picture from flat to textured (fix: more passes);
- **last = finish**: the last step picture equals the finish;
- existing ones that stay: `paints_not_listed`, `duplicate_recipes`, `unreachable_paints`, `undocumented_diagrams`,
  `long_instructions`;
- new: more paints than `max_mixes`; a stroke with no card; a percentage in step text.

The fresh-context text review (`step-review.md`) stays, once per lesson, on the `step-pairs` sheets. Its kinds
`drift`, `shape_change`, and `split_edge` are removed (they can't happen). It keeps `missing`, `wrong_result`,
`vague`, `flat`, `layering`, `too_much`, `unpaintable`. `too_much` is now fixed, not recorded: split the step in
the plan and run `build-steps` again (free).

## 12. The page

- Contents by stage; steps numbered inside each stage ("The bird · step 3 of 5") and overall.
- Each step, top to bottom: the Where picture, then the result picture (tap to switch, or side by side on a wide
  screen), the numbered lines, paints for the step with recipes and amounts, then folds: close-up, paint map,
  stroke card (open on first use), diagram, watch out.
- The first screen gains "Before you start": chalk the quarter marks, the transfer outline, and the lesson's
  strokes to try on scrap paper.
- Everything stays one self-contained HTML page per lesson (the lessons site and `site/history/` don't change).
  More pictures per step means bigger pages: aids are JPEG at up to 700 px, and `publish` fails if the page is over
  12 MB.

## 13. Build order and the gate

Each row is one issue. Build them in this order; don't start one before the ones it depends on are closed.

| # | Issue | Needs | Needs an OpenAI key? |
|---|---|---|---|
| 1 | #62 Outlines and step pictures from them (`outline`, `build-steps`), tested on three finishes | none | no |
| 2 | #63 Hidden areas: free fill, ghost check, plate render | 1 | yes, for the plate |
| 3 | #64 Paints measured from the finish, with a mix limit (`paints`) | 1 | no |
| 4 | #65 Stroke cards and the amounts table | none | no |
| 5 | #66 Teaching pictures (`step-aids`) and the page | 1 | no |
| 6 | #51 Step text from data, and measured checks in place of the reviews | 1, 3, 4 | no |
| 7 | #67 The v2 skill, a full run on three photos, and the gate | all | yes |

Issue numbers 63 to 67 are the ones filed with this design; if GitHub gave them different numbers, the issue titles
are the reference.

**Test pictures for issues 1, 3, and 5** need no renders: take the finished paintings out of the three lesson pages
in `site/lessons/` (the last large inline image in each `index.html`; the probe did this) into
`spike/tests/fixtures/finishes/` at their full 1000 x 786 size. They're already public on the site.

**The gate (#67).** Run the v2 skill hands-off on the chickadee, the red sailboat, and the lavender balloon. v2
replaces v1 only if all of these hold, and the owner agrees after looking:

| Measure | v1 (from `site/history/`) | v2 must be |
|---|---|---|
| Image cost per lesson | $0.40 to $0.51 | $0.20 or less |
| Time from start to seal (wall clock; add it to the history record as `minutes_total`) | over 20 min (owner's timing) | 10 min or less |
| Problems left on the page (`left`) | 5 on the chickadee | 0 drift or shape problems (they can't happen); any other `left` explained |
| Steps | 10 to 11 | 12 to 30 in 5 to 10 stages |
| Same photo run twice | different step pictures each run | identical step pictures given the same finish and plan (`build-steps` twice gives the same bytes) |
| Owner's score (`history-rate`) | whatever each v1 run has | not lower than v1 on any of the three |

If the gate passes: delete `lock.py`, `lock-steps`, `carry-forward`, `finish-from-step`, `split-texture`,
`render-step`, the throwaway-filter rules, skill steps 4-5b and 6a, and their tests; move `spike/run.py` out of the
way only if nothing imports it. If it fails on soft or thin parts only: keep v2 and the merge rule (section 6),
and write up what failed. If it fails more widely: stop and report to the owner; don't patch around it.

## 14. Rules for whoever builds this

- One issue at a time, in the order above. Read this file and the issue. Check `docs/decisions.md`.
- New code goes in new files (`spike/outline.py`, `spike/build_steps.py`, `spike/paints.py`, `spike/aids.py`,
  `spike/draft_text.py`, `spike/checks.py`) with a subcommand each in `spike/tools.py`. Reuse `from_finish.py`'s
  functions; don't copy them.
- Every tool is deterministic: the same inputs give the same output bytes. No random seeds left unset (k-means
  uses a fixed seed).
- Every tool has tests in `spike/tests/` that run without network, model files, or API keys. Tests that need the
  SAM files are skipped when `models/` is empty, and say so.
- Every number in this file marked as a starting value is tuned on the three test pictures by the issue that owns
  it, and the final value is written back here in the same commit.
- If a rule here turns out wrong, change this file in the same commit as the code and say why in the commit
  message. Don't quietly do something else.
- Don't raise render quality, add renders, or add a review round to fix a problem. If a free tool can't do it,
  merge the part (section 6) or report it.
- Version: each issue that changes what a lesson contains bumps `spike/VERSION` (minor) and adds a
  `docs/changelog.md` entry, as today. v2's first sealed lesson is POC 0.30.0.

## 15. Known risks

| Risk | What limits it |
|---|---|
| Soft and thin parts don't separate (mist, hazy foliage, branches). | Tested first, in #62, before anything else is built. The merge rule gives a correct lesson either way. |
| Hidden-area fills look wrong (a ghost of the thing in front). | Measured ghost check; one plate render pasted only into the hole; they're on screen for a few steps only. |
| Passes by lightness don't match how the area is really painted (a pass that is half shadow, half a different color). | A part with two color areas gets child parts or two `flat` paints; the text review's `wrong_result` and `flat` kinds still catch it; splitting is free. |
| The finish is more detailed than a beginner can paint, and v2 copies it faithfully. | Unchanged from v1: the beginner version (step 0c) and `detail_budget`. Not made worse. |
| More steps and pictures make the page long and heavy. | Stages in the contents, folds, the 12 MB limit. |
| The outline model is 108 MB and runs only where the lesson is made. | It isn't needed to view a lesson. The site is static pages. An app would need a hosted model later; out of scope for the POC. |
