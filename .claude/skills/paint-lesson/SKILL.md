---
name: paint-lesson
description: Turns a photo into a step-by-step beginner acrylic painting lesson (Gesso #10). Claude Code plans the lesson, picks a tool for each step (free filters first, paid gpt-image renders only when no filter can do it), reviews every step in a fresh subagent, and writes lesson.html. Use when the owner runs /paint-lesson <photo> [technique] [quality], or asks for a lesson from a photo.
---

# paint-lesson

You are the lesson pipeline. You do the planning, checking, and writing yourself (no Anthropic API calls), and
call `spike/tools.py` for images. Filters are free; renders cost money, so they come last
(`docs/decisions.md`, 2026-11-10). Read `docs/decisions.md` and the technique file before starting.

Arguments: `<photo>` (required, e.g. `photos/sleeping-cat.jpg`), technique (optional), quality for steps (default
`low`), and `--canvas WxH` (optional, inches, e.g. `--canvas 11x14`; the owner paints mostly on 11x14, some 24x30
and 10x10) with `--orientation portrait|landscape` (optional; a rectangular canvas hangs either way, so by
default it follows the picture). If the owner names a technique, use it. Otherwise read every file in `techniques/` and choose the one that
fits this photo and the level (decisions: Claude chooses techniques per photo from the hand-checked library), and
record why, with every technique you passed on, in `notes.json`.

Run every tool with the venv: `PY=.venv/Scripts/python.exe` (Windows) or `.venv/bin/python`. `$PY spike/tools.py --help`
lists every tool and what it's for; read it at the start, since filters get added over time.

## Tool order for every image

For each image the lesson needs, take the first of these that does the job, and write down which one and why.
Every filter run with `--lesson` needs `--why` (what you want it to show you) and takes `--step <id>` when it's for
one step; both go in the ledger, and the lesson page shows them under "How this lesson was made".

1. **A filter** from `tools.py --help` (value study, notan, palette, simplify, posterize, edges, grid, ...).
2. **A composite** (masks of the finish, #8), once that tool exists.
3. **A throwaway filter** (#11): a one-off script in `<lesson>/filters/`, tried before renders, 2 tries at most.
   Write every try's output inside `<lesson>/filters/` too, and copy only the one you use to `<lesson>/NN_<id>.png`.
   If neither try works, keep the better one there as a seed for option 4. Until #11 adds filing filter requests,
   list each throwaway in the report to the owner. Worth trying when a step only takes away things that sit on a
   simple background (the trees in front of a sky). Skip it when a later layer hides something the step has to
   show (the swirl under the cat, the sky behind the vines): inpainting can't invent what was covered, and two
   runs (cat, pumpkin, 2026-11-10) spent both tries and still rendered. Example from the trees
   run: the first step (sky only) came from masking the dark trees in the finish, inpainting the holes, and
   blurring; it left a mark the review caught, and a render seeded by it fixed that for $0.018.
4. **A render seeded by a filter or composite**: `render --step <id> --inputs <seed image> --out <lesson>/NN_<id>.png`
   with your own prompt, since `render-step` builds its prompt from the finish. Start the prompt with what the
   image is ("This is an acrylic painting at the step where ..."), say what to fix or remove, say to keep the
   placement, sizes, and colors exactly, and end with the technique's `framing`.
5. **A plain render** (`render` or `render-step`), with `--why-not-filter` saying why 1 to 4 can't do it.

Renders are capped per lesson (`--max-cost`, default $1.00) and per step (`--max-redos`, default 2). A refusal
means stop rendering that step: flag it in the lesson for the owner, don't try to get around the cap. The same
render with the same inputs comes back free from the cache, so rerunning a lesson to change the text costs $0.

## Steps

### 0. Set up
- Lesson folder: `output/<photo stem>_skill_<YYYYMMDD-HHMMSS>/`. Pass it as `--lesson` to every tool.
- Files the tools make there besides yours: `ledger.json` (every render and filter run), `00_canvas.png` (white canvas, made by
  `render-step`), and the filter outputs. Put trial outputs you won't use under `<lesson>/trials/` with `--out`.
- Read the technique YAML: `rules`, `brush_moves`, `palette`, `step_range`, `ground`, `framing`, `simplify`, `finish`.
- Read the medium's research notes, `docs/research/acrylic-paint-along.md`: at least sections 4 (depth and texture)
  and 5 (beginner mistakes) and "For Gesso". Technique in the plan and the step text comes from these cited notes
  and the YAML, not from memory. When you rely on something they don't cover, say so in `notes.json` under
  `learned`, so the research can be extended.

### 0b. Check the photo is just the picture
Read the photo before anything else and say what the subject is. Then ask: is everything in this image part of
the picture someone wants to paint? Owners send screenshots (2026-11-11: a shop page with the painting in the
middle), so look for:
- a phone status bar, app or browser bars, buttons, prices, ratings, sale banners, captions, or page text;
- a carousel's dots or the edges of the next image;
- a photo of a screen, print, or canvas with the wall, frame, or desk around it;
- a border, watermark, or the subject taking up only a small part with a lot of unrelated scene around it.

If any of these show, crop: `crop <photo> --lesson <lesson> --out <lesson>/photo_cropped.png --why "<what's around
the picture>"` finds the picture on its own (the biggest block of photo-like rows and columns). Read the output:
it must hold the whole picture and nothing else. If it's off, measure the picture's edges yourself and pass
`--box X0 Y0 X1 Y1` (pixels in the original). Then use the cropped file as the photo everywhere: in `plan.json`,
`"photo": "output/<lesson folder>/photo_cropped.png"`, and as the finish render's photo input. Crop to the subject
only when what you'd cut away is clearly not part of the scene. Don't recompose a real photo.

Record it in `notes.json` as `photo_prep` (step 8), so the page says what was done before the lesson started. If
the image is already just the picture, skip the crop and say so in `photo_prep` in a few words.

### 0b2. Fit the picture to the canvas (only with `--canvas`)
The painter has a real canvas, and the lesson should match its shape, so nobody has to imagine how a wide picture
fits a square canvas (owner, 2026-11-11). Do this after 0b and before anything else looks at the picture.

1. Read the photo and decide the subject's box and the focal point (0-1 from the top left). The subject is what
   the picture is about (the balloon, the boat and its reflection), not the whole scene.
2. `fit-canvas <photo> --lesson <lesson> --canvas <WxH> [--orientation ...] --focus X Y --keep X0 Y0 X1 Y1 --why
   "<subject and what must stay>"`. It picks the cheapest fit:
   - `none`: the picture already has the canvas's shape;
   - `crop` (free): plain edges are cut and the subject stays whole, losing at most about a third;
   - `extend`: the subject wouldn't survive a crop, so the whole picture sits on the canvas with gray edges.
   It also places the canvas in the image model's nearest frame (square, 3:2, or 2:3). When the canvas has a
   different shape, the frame has gray bands outside it.
3. If `needs_render` is true, run the render command in its `advice` once. It fills every gray area by continuing
   the scene. Read the result: nothing already painted changed, the edges continue the scene, and nothing new
   appeared. Redo once at most.
4. From here on, "the photo" is `00_canvas_fit.png` (or `00_canvas_frame.png` when no render was needed). Every
   render and every step image stays in the model's frame. The painter sees only the canvas: `publish` crops every
   step picture to the canvas box (in `canvas/`), and the review sheets use those crops.
5. Two coordinate systems, so keep them apart:
   - the plan's `looks_like` and render prompts describe the frame;
   - the step text the painter reads describes the canvas. Before writing it, run
     `canvas-view 99_finish.png --lesson <lesson>` and measure on `canvas/99_finish.png` with `grid --percent`.
6. Record it in `notes.json` as `canvas_fit`: `{"canvas": "11 x 14 in, portrait", "mode": "crop", "why": "...",
   "lost": "the right 15% of empty water"}`.

**Size changes the lesson, not just its shape.** Scale to the canvas's area:
- **Detail budget:** under 120 sq in (a 10x10), use `max_parts` minus 2: fewer, bigger shapes, since small
  canvases can't hold small marks. From 120 to 300 sq in (11x14 is 154), use it as is. Over 300 (24x30 is 720),
  add 3, and textures can be one size smaller.
- **Brushes:** pick brush sizes for the canvas. On a 10x10, the biggest is a 3/4 inch flat. On an 11x14, a 1 inch
  flat. On a 24x30, a 2 inch flat or a wide house brush for the sky, with rounds a size or two up.
- **Measurements:** the page says how many inches each 10% is, so grid positions can be marked with a ruler.
  Inches in the text are fine for sizes ("about 2 inches wide").

### 0c. Is it beginner-sized? (`00_beginner.png`)
Every step is copied backward from the finished painting, so whatever detail the finish has, some step has to
paint. The balloon lesson (2026-11-11) kept a village of tiny houses, textured clouds, and every lavender stalk,
and one step jumped from flat purple rows to thousands of stalks. A beginner can't paint that. Look at the photo
(or the crop) and answer, for the technique's level (`detail_budget` in the technique file):
- **Tiny separate things** that aren't the subject: houses, windows, people, boats, fence posts, a village?
- **Textures made of hundreds of items**: stalks, blades of grass, single leaves, bricks, a fine dust of stars?
- **Detail inside big shapes** that one repeated mark can't make: veined clouds, carved bark, every wave?
- **More parts** at different distances than `detail_budget.max_parts`?

If any answer is yes, make a beginner version before anything else, and make the rest of the lesson from it:
`render --step beginner --inputs <photo> --quality medium --out <lesson>/00_beginner.png --why-not-filter "<why no filter can drop and merge these>" --prompt "<beginner_version.prompt> <your list> <framing>"`.
Your list names exactly what to drop ("remove the village"), merge ("the clouds become three big soft masses"),
and turn into a repeated mark ("the lavender becomes rows of loose purple dabs, darker at the base, no single
stalks"). Keep the composition, the subject, the light, and the mood. Read the result: everything the owner
would recognize the picture by is still there, and nothing on your list survived. One redo at most, then take the
better one. From here on, "the photo" means `00_beginner.png` (the reference, the palette, and the finish's color
source). If every answer is no, skip this and say so.

Record the answers and the list in `notes.json` as `beginner_version` (step 8), and put `00_beginner.png` in
`notes.filters` with `"label": "Beginner version"`, `"tool": "render"`, and `"verdict": "kept"`: it's a render, but
listing it there puts it in the page's contact sheet.

### 1. Simplified reference (`00_reference.png`)
The reference is what the painting is made from: fewer shapes, clear values, colors a beginner can mix
(decisions: "Simplify the photo first").
- Try `simplify --strength 2` or `3` on the photo, then look at it. If small clutter is still there, try a
  higher strength or `--method meanshift`. For line art or anything with outlines (an illustration, a cartoon),
  start with `--method meanshift --strength 3`: Kuwahara breaks thin dark lines apart (the cat lost its face).
  The same goes for many small bright dots (stars, fireflies, sparkles): Kuwahara wipes them out (tree of life,
  2026-11-11), so start with mean shift there too.
  Write trials to `<lesson>/trials/` with `--out`, and copy the one you pick to `<lesson>/00_reference.png`.
- Also make, for the painter and for you: `value-study --tones 3`, `palette --colors 6` (their outputs go in the
  lesson folder with `--lesson`).
- Only if no filter result reads as a clean reference (for example the photo is too busy for any strength),
  render it with the technique's `simplify.prompt` (`render --step reference`, reason required).

### 2. Finished painting (`99_finish.png`)
No filter turns a reference into an acrylic painting on canvas, so this is a render:
`render --step finish --inputs <reference> <photo> --prompt "<finish.prompt> The second image is the original photo: take every area's colors from it, and keep each area's share of the canvas (if the water is the bottom third there, it's the bottom third here). No text, signature, or watermark. <framing>" --quality high --out <lesson>/99_finish.png`
with a reason. Every step copies from the finish, so it gets high quality (as in the spike). Pass the photo too:
on the trees photo (2026-11-10) a Kuwahara reference alone turned a cream-gold sky into blue and purple patches,
and the finish needed a paid repaint. With a beginner version, pass it as the photo, not the original: the
original's detail flows back in through the second input. The canvas snaps to a few fixed shapes, so the share
line matters (tree of life, 2026-11-11: the lake got squeezed to a strip).

Then check it against the photo yourself (Read both images). Simplifying is expected; flag only what the owner
would notice and mind: an area changed color or hue, something added, removed, or turned into something else, a
texture changed character, the mood or time of day changed, or the subject looks stretched or squeezed. The
render snaps to 1024x1536, 1536x1024, or 1024x1024, so the canvas shape can differ a little from the photo; that's
fine as long as the shapes in it aren't distorted. With a beginner version, also flag anything on your drop or
merge list that came back. If anything is flagged, render once more with
`--inputs <finish> <photo>`, a prompt listing the fixes ("Repaint it with these fixes so it matches the second
image: ... Keep everything else the same"), and `--fresh` not needed (the prompt differs). Save the flagged list
for `review.json` as `finish_issues`.

### 3. Plan (`plan.json`)
Plan the lesson the way `plan_lesson` in `spike/run.py` does (read its prompt), from the finish, under the
technique's rules and step range. Write `<lesson>/plan.json` with exactly these fields (the spike's `LessonPlan`
plus three):

```json
{
  "photo": "photos/<file>", "technique": "techniques/<file>.yaml", "quality": "low",
  "subject": "...", "focal_point": "...", "light": "...",
  "components": ["farthest part first", "..."],
  "paints": [{"name": "Sunset orange", "recipe": "2 parts yellow, 1 part red, a touch of white",
              "hex": "#e8903a", "used_for": "...", "sample_x": 0.4, "sample_y": 0.2}],
  "steps": [{"id": "sky-gradient", "name": "Paint the sunset sky", "paints": "which parts this step adds",
             "looks_like": "the WHOLE canvas after this step, including what is still white canvas",
             "covers_canvas": false, "colors": ["Sunset orange"], "brushes": "...",
             "how": ["2 to 5 instructions, each naming its brush move"], "watch_out": ["1 or 2 beginner mistakes"]}]
}
```

Measure, don't guess. Before writing any `looks_like`, run `grid --percent` on the finish and read where things
are from it: "the sun's center is 44% across and 40% down", not "right of center" (balloon, 2026-11-11: that guess
was wrong and cost a paid redo). Give edges as numbers too: when a step leaves white canvas, say "a straight lower edge at 62% down" (balloon
rerun, 2026-11-11: three redos were renders stopping the sky short). Spell out a subject's exact pattern (stripe
colors in order, left to right) so a subject painted late matches the finish. Describe only what the finish shows. If later layers hide most of something
(branches inside a crown), say how much shows, so the render doesn't invent the rest.

Step `colors` and every diagram `paint` must be names from the plan's `paints`. A tube name like "Burnt sienna"
isn't one: add it as a paint (with its recipe) if a step uses it straight.

The last step is the finished painting: `"looks_like": "The finished painting."`, `"covers_canvas": true`. Step
ids are unique lowercase slugs. Use only palette tubes in recipes (a first guess; `mix` computes the real ones). `sample_x`/`sample_y` (0-1 from the top left)
point at a flat patch of that paint in the finish; `publish` snaps each hex to the painted color there. The palette
filter output on the finish helps you pick hexes.

Before moving on, read the plan as a painter would (owner's notes on the pumpkin lesson, 2026-11-11):
- A background step must let the brush keep moving. If the sky's `looks_like` stops at a hill line with white
  canvas below, swirly or circular strokes break at that line. Run the sky to the bottom edge (or well past the
  horizon) and let the ground step paint over it; that also stops the sky and hill edges disagreeing between steps.
- No step jumps from flat to dense texture. A texture step adds one kind of mark at a size a beginner can make in
  a few minutes. If the finish has dense texture (rows of lavender dabs, foliage), split it into passes: the dark
  marks, then the light marks on top, each its own step.
- A block-in step for a shaped object says how to build the shape from simple pieces in its `how` (a pumpkin: a
  center oval, then curved side segments like ( ) on each side). The image can show the plain shape; the words
  carry the construction.

Then decide, per step, how to make it (the tool order above), and note it for `text.json` later. For a paint-along
lesson most steps are "the finish with later parts not painted yet", which only compositing (#8) or a render can
make today; a sketch or tracing step (block-in technique) is the `edges` filter, and a value or color-blocking
step may be `value-study` or `posterize`. Put filter-made step images at `<lesson>/NN_<id>.png` (NN from 01).

### 4. Render the remaining steps
`render-step --lesson <lesson> --steps <ids...> --why-not-filter "<reason>" --quality <quality>` renders every
listed step at once, each from the finish, with the spike's step prompt (`--mode parallel`, the spike's default).
Leave out steps you made with filters. Check the JSON: any step with `"refused"` is flagged, not retried.

### 5. Review in a fresh context
Don't grade your own images. Start a subagent (Agent tool, general-purpose) with only this:
- the paths of the step images in order (last is `99_finish.png`) and, for each, its id, what it adds (`paints`),
  and `looks_like` from the plan;
- this checklist, from `review_steps` in `spike/run.py`: each step is the canvas after that step, so everything
  from earlier steps is still there in the same place and shape, plus only what this step adds. Flag only clear
  problems a painter following along would notice: something appears before the step that paints it; something
  painted earlier is missing, moved, or a clearly different shape or size; the image doesn't match `looks_like`
  (white canvas showing where it should be covered, or covered where it should be white). Ignore small differences
  in brushwork, texture, and exact color. Never flag the last step. Also check the technique's painting order,
  and flag a step that jumps from flat to dense texture a beginner couldn't paint in a few minutes (a step adding
  thousands of lavender stalks at once): the fix is a plan change, splitting it into passes, not a redo.
- when two neighboring steps disagree, compare both with the finish and flag the one that differs from it,
  not automatically the later one;
- ask it to Read every image and answer with JSON only: `{"issues": [{"step_id", "problem", "fix"}]}`, `fix`
  phrased as an instruction for redrawing that image.

Before redoing, check each issue yourself against the finish: if the flagged step matches the finish and its
neighbor doesn't, redo the neighbor instead and say so in `action`. Redo with
`render-step --steps <id> --fix "<fix>" --why-not-filter "<reason>"` (one step per call; several can run as
separate commands in parallel, since the ledger locks itself).

The rounds go as in the spike: review, redo, review again in a new subagent, redo what that flags, and stop. There
is no third review. A step whose redo was refused by the caps stays as it is. Save every issue in `review.json`:

```json
{"finish_issues": ["..."],
 "review_issues": [{"step_id": "moon", "problem": "...", "fix": "...", "round": 2,
                    "action": "redone | redone neighbor <id> | left"}]}
```

A mismatch you spot yourself after the last review round (when writing text or diagrams) goes in `review.json`
too, as `"left"` with `"round": 2`, and the step's words should tell the painter what to do about it.

Use `"left"` for anything not redone (a cap refused it, or you judged it not worth a redo). The lesson page shows
every `"left"` problem on its step as a heads-up for the painter.

### 6. Write the steps (`text.json`)
First run `mix --lesson <lesson>` (free). It works out every paint's recipe from the palette tubes with a pigment
mixing model and prints each one with how far it lands from the paint's swatch (Delta E). Your plan recipes were a
first guess: the computed ones replace them on the page, so never write amounts in the step text. Name paints only
(Five lessons, 2026-11-11: recipes written by eye missed by Delta E 11 on average, the mixer by 2). For each paint
in `unreachable`, the tubes can't make it: say so in that step's `paint_notes` ("as close as these tubes get") or
pick a sample spot nearer what the step needs.

Read the final images in order and write each step's instructions from what its image actually shows, like
`write_steps` in `spike/run.py`: name the real shapes and areas, give the mixes by paint name, keep the planned
advice that still applies, plain words, 2 to 5 short steps.

Keep it short; a beginner reads this with a wet brush in hand. Each step's `what_to_do` stays under about 100
words, and each instruction under about 35 (balloon rerun, 2026-11-11: the new rules doubled the text to about 160
words a step). To fit everything the technique asks for:
- Don't repeat what the page already shows: recipes are in "Paints for this step", brushes in the brush chips,
  stroke how-tos in `strokes`, and drying time in the drying line. Name the paint, brush, and stroke; don't
  explain them again.
- Say the drying cue in four words or so ("Let the sky dry."), and the paint load in one or two ("creamy",
  "nearly dry", "thinned like ink").
- The once-per-lesson notes (colors dry darker, the ugly stage, a test stroke) go in `paint_notes` or `watch_out`,
  not in the instructions.
The budget is a signal, not a cap: never make an instruction unclear to fit it. When `publish` lists a step in
`long_steps` or an instruction in `long_instructions`, ask why it's long:
- It repeats the page, or explains a stroke or a drying time: that's wordiness. Cut the repeat.
- It describes something that could be shown (a shape, a stroke path, the order of values): show it with a
  diagram or a `values` table and cut the description.
- It's one instruction doing two moves: split it into two instructions. The words stay; each one gets shorter.
- The step itself has a lot to do (several kinds of marks, several areas): that's a complicated step, not wordy
  text. Split the step in the plan if its pictures allow it, move how-to detail into `strokes` or a construction
  diagram, or leave it long and say why in `notes.json` under `long_steps_kept`. A clear long step beats a short
  vague one.
Never trim a size, a position, or a count: where something goes, how big it is, and how many there are are the
instruction itself (balloon trim, 2026-11-11: halving the text dropped the balloon's width, the number of lavender
rows, and the trunk's size, and the reviewer's vague findings went from 3 to 8). Give them as grid numbers
("centered 28% across, about 15% wide"), or show them in a diagram.
A mix used only in one step (a shadow or highlight made from another paint) still goes in that step's `colors`,
so the painter sees its recipe and swatch; better, put it in the step's `values` table.
The step review (6b) runs after this and flags any instruction that got vague, so trimming can't quietly drop
what the painter needs.

The first step's first instruction states where the light comes from ("The light comes from the sun, low and a
little left of center"), and every highlight after it stays on that side.

**Show, don't tell (owner, 2026-11-11).** When something takes more than a sentence to explain in words (a shape,
a stroke's path, where things go, the order of values), show it instead and keep the words to a pointer ("build
the hull as in the diagram"):
- a construction or stroke diagram (`construct`, step 7) for shapes, stroke paths and direction, and order of moves;
- a `values` table for depth: one row per value, dark first, each naming its paint and where it goes;
- the step picture itself for placement: "where the picture shows the gold glow", plus a grid percentage.
A beginner follows a picture faster than a paragraph. Prose is for what can't be drawn: timing, paint load, and
what to watch for.

`values` (optional, per step, in `text.json`): `[{"value": "dark", "paint": "Cloud shadow", "where": "tops and
far sides, away from the sun"}, {"value": "mid", ...}, {"value": "light", ...}]`. The page shows it as a small
table with swatches. Use it whenever a step builds depth from more than one value.

Every step's page lists its paints with their recipes,
because beginners mix as they go (acrylics dry on the palette), so a step's `colors` must hold every paint it uses.

Every step also recommends its brushes and strokes, because beginners don't know which brush makes which mark:
- `brushes`: each brush by its usual name and size (`1 inch flat`, `#8 round`, `Liner (#1 or #0)`, `fan brush`,
  `old stiff flat`) and what it's for in this step. The lesson's "What you need" list is built from these.
- `strokes`: the named stroke techniques for this step, from the technique's `brush_moves` where one fits (X stroke,
  wet blending, dabbing, press and lift, flicking, dry brushing, ...), each with one or two sentences on how to do it
  with that brush, for this picture.

Give every step a `summary`: one sentence, under about 90 characters, saying what the step paints. It's the
caption when the lesson is shown as a walkthrough (a blog embed), where the full text sits behind a toggle.

Write `<lesson>/text.json`:

```json
{"steps": [{"stage_id": "sky-gradient", "summary": "Blend the sunset sky from blue at the top to orange.",
            "what_to_do": ["..."], "mixes": ["Sunset orange"], "watch_out": ["..."],
            "paint_notes": [], "made_with": "render", "reason": "why this tool",
            "brushes": [{"brush": "1 inch flat", "use": "covering and blending the sky"}],
            "strokes": [{"name": "X stroke", "how": "Criss-cross the flat in overlapping X shapes so the paint blends with no streaks."}]}]}
```

Construction diagrams (`construct`) are added in step 7.

`made_with` is `filter:<name>`, `composite`, `throwaway:<script>`, `render+throwaway:<script>`,
`render+filter:<name>`, or `render`, for the image the lesson ends up with. When a redo replaced a filter or
seeded image, `made_with` says `render` and `reason` says what was tried first and why it was replaced.

### 6b. Step review: would the text get a beginner there? (#24)
A fresh reviewer checks your text against measured before and after pictures, because the text is written by
the same mind that planned the pictures and misses what it takes for granted.

1. Run `publish --lesson <lesson>` (a draft, so `lesson.json` exists). Deal with its `long_steps` and
   `long_instructions` first, as section 6 says, and publish again, so the reviewer reads the text you'll ship.
   Then run `step-pairs --lesson <lesson>`.
2. Start a subagent (Agent tool, general-purpose) with only this: follow
   `.claude/skills/paint-lesson/step-review.md` for the lesson folder, use only `trials/review/packet.json` and
   its sheets, and write `trials/review/review.json`. Don't pass it your reasoning or the plan.
3. Route each problem by its `kind`. Don't go by the verdict alone:
   - `flat`, `missing`, `vague`, `wrong_result`, `layering`: fix the step's text in `text.json` from the
     reviewer's `fix`. Check each fix against the sheet first; skip one whose evidence doesn't hold up, and say why.
   - `drift` (an area finished earlier changes in a later picture): leave the text alone. The picture is wrong.
     Record it; picture drift is fixed in the pipeline, not here.
   - `too_much`: if the reviewer proposes a split, record it with its proposal. Don't add a step this late.
   - `unpaintable`: record it as `left` and flag it on the step, like a review issue.
   - A `diagram` proposal goes to step 7 as a candidate. You still decide there, and say why.
4. One review round only: no second reviewer. Save what happened in the lesson's own `review.json` (not the reviewer's) under `text_issues`:
   `{"step_id", "kind", "problem", "fix", "action": "fixed | left | skipped: <why> | diagram"}`. The page shows
   them in "What the reviewer caught".

### 7. Beginner check: where the picture isn't enough
A step image shows what the canvas looks like after the step, not how to get there. Before writing notes, go
through every step as someone who has never painted, with only that step's picture and words, and ask: **could I
start this?** Nobody will tell you where it's missing; the owner had to point out the pumpkins (2026-11-11), and
this check exists so that doesn't happen again.

**Signs a step needs a construction diagram** (any one is enough):
- A shaped object appears whole in one step: a pumpkin, an animal, a person, a building, a boat, a vase.
- The outline is lumpy, segmented, or made of repeated parts (pumpkin lobes, petals, a row of fence posts).
- The step adds lines whose placement depends on the object's structure: rib lines on seams, fur that follows
  the body, a face's features, windows in perspective, branches forking off a trunk.
- You'd need to sketch it on scrap paper first to get it right.
- Where things start or join isn't clear from the picture: which trunk a branch grows from, where a trunk forks.
- An instruction needs more than a sentence to describe a shape, a stroke's path, or an order of moves. Draw it
  instead (show, don't tell), and shorten the instruction to point at the diagram.

**Also check the words against the picture.** While you look at each step, fix any instruction that says
something the picture doesn't show (the beginner checks on 2026-11-11 found a trunk said to pass "left of the
sun" that actually forks around it, and a cat head said to be a third of the body's width that is about half).

**Usually no diagram:** flat fills and backgrounds, skies and gradients, textures made by repeating one mark
(dabbed foliage, flicked grass, stars), and anything the words already make obvious ("a thin line along the
horizon"). Say why for each of these in `no_diagram`, so the page shows every step was looked at.

**How to break a shape into pieces.** Build it the way a drawing teacher would, from what the object actually is:
1. Name its structure. What is it made of? A pumpkin is lobes bulging around a core; a sleeping cat is a round
   head tucked against an oval body; a house is a box with a triangle on top; a tree is a trunk that splits into Y's.
2. The biggest mass first, as one simple shape (oval, circle, rectangle, triangle), where it sits in the picture.
3. Add the attached parts in order of size, back pieces tucked `behind`. Repeated parts get smaller or narrower
   toward the edges or the distance.
4. Let the pieces set up later steps: the seams between pumpkin lobes are where the rib lines go, so the shading
   step's diagram can start from the block-in's pieces (`done`) and draw ribs on the seams.
5. Check it against the step image and the finish (Read them): proportions (how wide against how tall), how many
   parts and where they attach. If the final panel's silhouette doesn't match the painted shape, fix the pieces.
   2 to 4 panels per diagram, captions of a few words, and the shape should fill most of the box.

Put the `construct` spec on that step in `text.json`. The lesson page draws it as a strip of small, free SVG panels
under the step. Each panel adds the next pieces with a dashed outline and arrows for the brush's direction.
Coordinates are a 100 x 100 box, y down. For a wide, short area (a field, a horizon), draw it at its real
proportions inside the box (a 100 x 40 band), not stretched to fill it:

```json
"construct": {"title": "Build the big pumpkin from simple pieces", "paint": "Pumpkin orange",
  "stages": [
    {"caption": "A center oval", "add": [{"ellipse": [50, 58, 12, 21]}], "arrows": ["M 50 40 Q 40 58 50 76"]},
    {"caption": "A ( ) on each side, tucked behind",
     "add": [{"ellipse": [38, 60, 12, 19], "behind": true}, {"ellipse": [62, 60, 12, 19], "behind": true}]}]}
```

Shapes: `ellipse [cx, cy, rx, ry]` (optional `rotate`), `circle [cx, cy, r]`, `rect [x, y, w, h]` (optional
`round`), `path "<d>"` (filled, optional `opacity`), `line "<d>"` (stroked, `width`). Any shape can set `paint` (a
paint name from the plan), `behind: true` (drawn under what's there), or `done: true` (already painted in an
earlier step). `arrows` are paths shown only in their panel. The renderer is `spike/construct.py`. A broken spec
is left off the page, so check `publish`'s `diagrams` count. Look at your diagrams before publishing:
`preview-diagrams --lesson <lesson>` draws every one next to its step image into `<lesson>/trials/diagrams.png`
(free; it needs Chrome or Edge installed) for you to Read.

Write what you noticed and decided into `notes.json` as `beginner_check` (next step). It's what the page shows
under "Why a diagram" on the step and in "Where Claude drew diagrams". `publish` lists any diagram without a note
in `undocumented_diagrams`; fix those before publishing the artifact. When the owner points out something the
check missed, set that diagram's `source` to the owner's feedback with the date, and add the gap to `learned` so
the signs above can grow.

### 8. Write down your thinking (`notes.json`)
The lesson page has a folded "How this lesson was made" section and a "How this picture was made" fold under every
step, so a curious painter (and the owner) can see why the lesson looks the way it does. The ledger and review
fill in what was run and caught; `notes.json` holds the reasoning only you know. Keep notes as you go (after the
reference, the plan, and each throwaway) so nothing is reconstructed at the end. Plain words, a sentence or two each:

```json
{"read": "a painter's read of the photo: what matters, what's hard, what the lesson should be about",
 "technique": {"why": "why this technique fits this photo and level",
               "considered": [{"name": "Block in, then build up", "why_not": "..."}],
               "how_chosen": "only if you didn't choose it, say so (e.g. the owner named it)"},
 "order": "why the steps go in this order",
 "steps": {"<step id>": "why this step, and why now"},
 "filters": [{"label": "Reference", "tool": "simplify", "settings": "meanshift, strength 3",
              "image": "trials/simp3_ms.png", "why": "what you wanted to see", "result": "what you saw",
              "verdict": "kept | dropped"}],
 "throwaways": [{"script": "filters/sky_only.py", "for": "...", "steps": ["sky-glow"], "tries": 1,
                 "outcome": "what happened", "verdict": "kept | seeded a render | dropped",
                 "images": ["filters/01_sky-glow_filter.png"]}],
 "photo_prep": {"subject": "what the picture is of", "found": "what else was in the image, or 'just the picture'",
                "action": "cropped with crop (box [x0, y0, x1, y1]) | none", "why": "why that was right"},
 "beginner_version": {"made": true, "found": "the answers to the four questions",
                      "list": "what you dropped, merged, and turned into marks", "why": "why this was beginner-sized"},
 "beginner_check": {"summary": "a sentence on what the check found overall",
                    "diagrams": {"<step id>": {"noticed": "what made this step need a diagram",
                                               "pieces": "how you broke the shape down, and why that way",
                                               "checked": "how the pieces compare with the step image",
                                               "source": "beginner check | owner feedback, <date>"}},
                    "no_diagram": {"<step id>": "why the picture and words are enough"}},
 "learned": ["what you'd do differently next time"]}
```

List every filter you looked at, kept or not, with its image path relative to the lesson; logged filters you
leave out still show, without a verdict. Every technique in `techniques/` you didn't pick goes in `considered`.

### 9. Publish the lesson as an artifact and report
(If whoever started you said they'll publish the artifact themselves, run `publish` and skip the Artifact tool.)
`publish --lesson <lesson>` writes `lesson.json`, `lesson.html` (local, images by path), and
`lesson-artifact.html` (images inlined as JPEGs, about 1 to 2 MB), built by `spike/lesson_page.py`, plus `embed/` (lesson.json and WebP images) for showing the lesson as a
step-by-step walkthrough on another page, like a blog post. Every lesson is stamped with the Gesso version that made it
(`spike/VERSION`, the commit, the date). Say the version in your report, and on a republish the version it had
before (`previous_version`). When a change alters what lessons look like or contain, bump `spike/VERSION` and add
a line to `docs/changelog.md`.

Then publish `lesson-artifact.html` as a Claude artifact with the Artifact tool, when it's available:
- Copy it into the session's scratchpad (or working directory) first, named `<photo stem>-lesson.html`, since the
  tool only publishes files from there. The page already meets the artifact page contract, so don't rewrite it.
- `icon: "paint"`, and a one-sentence `description` (steps, subject, level). For a lesson re-run on the same photo,
  publish to the same URL instead of creating a new artifact.
- Artifacts are private by default. Keep them that way: the page shows the owner's photo (decisions: photos stay
  private), so never suggest sharing it.

Tell the owner, starting with anything that needs them:
- steps flagged and left as they are, with the reason;
- the artifact link;
- image cost for the lesson (`image_cost_usd`), paid and cached renders, and steps by source (filter, render, ...);
- compared with the spike: its parallel lessons on the trees photo cost about $0.40 each, $0.19 of images plus
  $0.22 of Claude API calls (2026-10-19); this skill's Claude work costs nothing extra;
- any throwaway filters used (until #11 files them as requests).
