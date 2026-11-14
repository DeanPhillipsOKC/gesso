# Step 0: set up, check the photo, fit the canvas, beginner version

## 0. Set up
- Lesson folder: `output/<photo stem>_skill_<YYYYMMDD-HHMMSS>/` (the history and the site find runs by that
  name). Pass it as `--lesson` to every tool.
- Every filter run with `--lesson` needs `--why "<what you want it to show you>"`. Pass `--max-cost 0.40` to every
  render.
- The tools also write `ledger.json` (every render and filter run), `00_canvas.png`, and filter outputs there. Put
  trial outputs you won't use under `<lesson>/trials/` with `--out`.
- Read `docs/decisions.md`.
- Technique: if the owner named one (`--technique`), use it. Otherwise read every file in `techniques/` with
  version 2 keys (`v2_step_range`, `v2_rules`) and pick the one that fits this photo and level. Record why, and
  every technique you passed on, in `notes.json` (`technique`), and say why in plan.json's `technique_why`.
- Read the technique YAML: `v2_rules`, `brush_moves`, `palette`, `v2_step_range`, `v2_stage_range`, `max_mixes`,
  `ground`, `framing`, `simplify`, `finish`, `detail_budget`, `beginner_version`.
- Read `docs/research/acrylic-paint-along.md`: at least sections 4 (depth and texture), 5 (beginner mistakes), and
  "For Gesso".

## 0b. Check the photo is just the picture
Read the photo and say what the subject is. Is everything in the image part of the picture someone wants to
paint? Look for:
- a phone status bar, app or browser bars, buttons, prices, ratings, banners, captions, or page text;
- a carousel's dots or the edge of the next image;
- a photo of a screen, print, or canvas with the wall, frame, or desk around it;
- a border, watermark, or a small subject with a lot of unrelated scene around it.

If any show, `crop <photo> --lesson <lesson> --out <lesson>/photo_cropped.png --why "<what's around it>"`. Read
the output: the whole picture and nothing else. If it's off, measure the edges and pass `--box X0 Y0 X1 Y1`
(pixels in the original). Use the cropped file as the photo everywhere (plan.json `"photo"`, the finish render's
photo input). Crop only what's clearly not part of the scene; don't recompose a real photo.

Record it in `notes.json` as `photo_prep`, a dict: `{"subject": "...", "found": "what else was in the image, or
'just the picture'", "action": "cropped with crop (box [x0, y0, x1, y1]) | none", "why": "..."}`. Start
`notes.json` now and add to it as you go; the full schema is in `steps/notes.md` (step 8b).

## 0b2. Fit the picture to the canvas (always, with or without `--canvas`)
1. Decide the subject's box and the focal point (0-1 from the top left). The subject is what the picture is
   about (the balloon, the boat and its reflection), not the whole scene.
2. `fit-canvas <photo> --lesson <lesson> [--canvas <WxH>] [--orientation ...] --focus X Y --keep X0 Y0 X1 Y1 --why
   "<subject and what must stay>"`. It picks the cheapest fit: `none` (same shape), `crop` (free, subject whole,
   at most about a third lost), or `extend` (the picture sits on the canvas with gray edges). It places the canvas
   in the image model's nearest frame (square, 3:2, or 2:3), with gray bands outside it when the shapes differ.
   With no `--canvas` it uses the standard size closest to the photo's shape, so a photo whose subject
   won't survive that crop gets the extend render.
3. If `needs_render` is true, run the render command in its `advice` once. Read the result: nothing painted
   changed, the edges continue the scene, nothing new appeared. Redo once at most.
4. From here on, "the photo" is `00_canvas_fit.png` (or `00_canvas_frame.png` when no render was needed). Renders
   and step images stay in the model's frame; `publish` crops every step to the canvas for the painter.
5. Keep two coordinate systems apart: `looks_like` and render prompts describe the frame; the step text describes
   the canvas. Before writing text, run `canvas-view 99_finish.png --lesson <lesson>` and measure on
   `canvas/99_finish.png` with `grid --percent`. (Those shares are for the plan only; the step text says where in
   inches, from `draft-text`, never in percentages or by tape marks.)
6. Record `canvas_fit` in `notes.json`: `{"canvas": "11 x 14 in, portrait", "mode": "crop", "why": "...", "lost":
   "the right 15% of empty water"}`.

**Size changes the lesson, not just its shape.** Scale to the canvas's area:
- Detail budget: under 120 sq in (10x10), `max_parts` minus 2. From 120 to 300 (11x14 is 154), as is. Over 300
  (24x30 is 720), add 3, and textures can be a size smaller.
- Biggest brush: a 3/4 inch flat on a 10x10, a 1 inch flat on an 11x14, a 2 inch flat or wide house brush on a
  24x30 (rounds a size or two up).
- The steps give positions and sizes in inches ("about 2 inches wide").

## 0c. Is it beginner-sized? (`00_beginner.png`)
Every step is copied backward from the finish, so whatever detail the finish has, some step has to paint.

First measure it: `busy <photo> --lesson <lesson>` (the fitted photo, `00_canvas_frame.png` or `00_canvas_fit.png`).
It prints `fine_texture`, the share of the canvas that is fine texture (hundreds of small items), and writes
`busy/<name>.jpg`, the photo faded with those places outlined. Read the picture. From the spike for #52: the lavender
photo is 10.3% (the outlines sit on the stalks), the chickadee 0.4%, the sailboat 0.0%. It's not a threshold: you
still decide. It doesn't see tiny separate things (it put one tile on the lavender's village) or count parts, so
answer those by looking. It records the number in `notes.json` (`beginner_version.busy`) itself.

For the technique's level (`detail_budget`), answer:
- **Tiny separate things** that aren't the subject: houses, windows, people, fence posts, a village?
- **Textures made of hundreds of items**: stalks, blades of grass, single leaves, bricks, a dust of stars?
- **Detail inside big shapes** one repeated mark can't make: veined clouds, carved bark, every wave?
- **More parts** at different distances than `detail_budget.max_parts`?

If any answer is yes, make a beginner version first and make the rest of the lesson from it:
`render --step beginner --inputs <photo> --quality medium --max-cost 0.40 --out <lesson>/00_beginner.png --why-not-filter "<why no
filter can drop and merge these>" --prompt "<beginner_version.prompt> <your list> <framing>"`.
Your list names what to drop ("remove the village"), merge ("the clouds become three big soft masses"), and turn
into a repeated mark ("the lavender becomes rows of loose purple dabs, darker at the base, no single stalks").
Where `busy` outlined texture, say where in the list ("the stalks across the bottom third"). Keep the composition,
subject, light, and mood.

Then `busy <lesson>/00_beginner.png --lesson <lesson>` and read the result: everything the picture is recognized by
is there, nothing on your list survived, and fine texture came down from the photo's (`came_down`; the lavender went
from 10.3% to 0.2% and under). If it didn't come down, or something on your list is still there, that's a reason
for the redo: name the places still outlined in `busy/00_beginner.jpg`. One redo at most (run `busy` on it again).
From here on, "the photo" means `00_beginner.png`.

Record the answers and the list in `notes.json` as `beginner_version`, a dict: `{"made": true|false, "found":
"...", "list": "...", "why": "...", "busy": {...}}`. `busy` is what the tool recorded: keep it as it is whenever you
write the notes (the seal checks it's there). Put `00_beginner.png` in
`notes.filters` with `"label": "Beginner version"`, `"tool": "render"`, `"verdict": "kept"`. If every answer is
no, skip it and say so.
