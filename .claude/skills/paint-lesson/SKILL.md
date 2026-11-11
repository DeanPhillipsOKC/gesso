---
name: paint-lesson
description: Turns a photo into a step-by-step beginner acrylic painting lesson (Gesso #10). Claude Code plans the lesson, picks a tool for each step (free filters first, paid gpt-image renders only when no filter can do it), reviews every step in a fresh subagent, and writes lesson.html. Use when the owner runs /paint-lesson <photo> [technique] [quality], or asks for a lesson from a photo.
---

# paint-lesson

You are the lesson pipeline. You do the planning, checking, and writing yourself (no Anthropic API calls), and
call `spike/tools.py` for images. Filters are free; renders cost money, so they come last
(`docs/decisions.md`, 2026-11-10). Read `docs/decisions.md` and the technique file before starting.

Arguments: `<photo>` (required, e.g. `photos/sleeping-cat.jpg`), technique (default
`techniques/acrylic-paint-along-beginner.yaml`), quality for steps (default `low`). Per-photo technique choice
(#12) isn't built yet: use the technique given.

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

### 1. Simplified reference (`00_reference.png`)
The reference is what the painting is made from: fewer shapes, clear values, colors a beginner can mix
(decisions: "Simplify the photo first").
- Try `simplify --strength 2` or `3` on the photo, then look at it. If small clutter is still there, try a
  higher strength or `--method meanshift`. For line art or anything with outlines (an illustration, a cartoon),
  start with `--method meanshift --strength 3`: Kuwahara breaks thin dark lines apart (the cat lost its face).
  Write trials to `<lesson>/trials/` with `--out`, and copy the one you pick to `<lesson>/00_reference.png`.
- Also make, for the painter and for you: `value-study --tones 3`, `palette --colors 6` (their outputs go in the
  lesson folder with `--lesson`).
- Only if no filter result reads as a clean reference (for example the photo is too busy for any strength),
  render it with the technique's `simplify.prompt` (`render --step reference`, reason required).

### 2. Finished painting (`99_finish.png`)
No filter turns a reference into an acrylic painting on canvas, so this is a render:
`render --step finish --inputs <reference> <photo> --prompt "<finish.prompt> The second image is the original photo: take every area's colors from it. No text, signature, or watermark. <framing>" --quality high --out <lesson>/99_finish.png`
with a reason. Every step copies from the finish, so it gets high quality (as in the spike). Pass the photo too:
on the trees photo (2026-11-10) a Kuwahara reference alone turned a cream-gold sky into blue and purple patches,
and the finish needed a paid repaint.

Then check it against the photo yourself (Read both images). Simplifying is expected; flag only what the owner
would notice and mind: an area changed color or hue, something added, removed, or turned into something else, a
texture changed character, the mood or time of day changed, or the subject looks stretched or squeezed. The
render snaps to 1024x1536, 1536x1024, or 1024x1024, so the canvas shape can differ a little from the photo; that's
fine as long as the shapes in it aren't distorted. If anything is flagged, render once more with
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

The last step is the finished painting: `"looks_like": "The finished painting."`, `"covers_canvas": true`. Step
ids are unique lowercase slugs. Use only palette tubes in recipes. `sample_x`/`sample_y` (0-1 from the top left)
point at a flat patch of that paint in the finish; `publish` snaps each hex to the painted color there. The palette
filter output on the finish helps you pick hexes.

Before moving on, read the plan as a painter would (owner's notes on the pumpkin lesson, 2026-11-11):
- A background step must let the brush keep moving. If the sky's `looks_like` stops at a hill line with white
  canvas below, swirly or circular strokes break at that line. Run the sky to the bottom edge (or well past the
  horizon) and let the ground step paint over it; that also stops the sky and hill edges disagreeing between steps.
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
  in brushwork, texture, and exact color. Never flag the last step. Also check the technique's painting order.
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

Use `"left"` for anything not redone (a cap refused it, or you judged it not worth a redo). The lesson page shows
every `"left"` problem on its step as a heads-up for the painter.

### 6. Write the steps (`text.json`)
Read the final images in order and write each step's instructions from what its image actually shows, like
`write_steps` in `spike/run.py`: name the real shapes and areas, give the mixes by paint name, keep the planned
advice that still applies, plain words, 2 to 5 short steps.

Every step also recommends its brushes and strokes, because beginners don't know which brush makes which mark:
- `brushes`: each brush by its usual name and size (`1 inch flat`, `#8 round`, `Liner (#1 or #0)`, `fan brush`,
  `old stiff flat`) and what it's for in this step. The lesson's "What you need" list is built from these.
- `strokes`: the named stroke techniques for this step, from the technique's `brush_moves` where one fits (X stroke,
  wet blending, dabbing, press and lift, flicking, dry brushing, ...), each with one or two sentences on how to do it
  with that brush, for this picture.

Write `<lesson>/text.json`:

```json
{"steps": [{"stage_id": "sky-gradient", "what_to_do": ["..."], "mixes": ["Sunset orange"], "watch_out": ["..."],
            "paint_notes": [], "made_with": "render", "reason": "why this tool",
            "brushes": [{"brush": "1 inch flat", "use": "covering and blending the sky"}],
            "strokes": [{"name": "X stroke", "how": "Criss-cross the flat in overlapping X shapes so the paint blends with no streaks."}]}]}
```

Construction diagrams (`construct`) are added in step 7.

`made_with` is `filter:<name>`, `composite`, `throwaway:<script>`, `render+throwaway:<script>`,
`render+filter:<name>`, or `render`, for the image the lesson ends up with. When a redo replaced a filter or
seeded image, `made_with` says `render` and `reason` says what was tried first and why it was replaced.

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
Coordinates are a 100 x 100 box, y down:

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
is left off the page, so check `publish`'s `diagrams` count.

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
`publish --lesson <lesson>` writes `lesson.json`, `lesson.html` (local, images by path), and
`lesson-artifact.html` (images inlined as JPEGs, about 1 to 2 MB), built by `spike/lesson_page.py`.

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
