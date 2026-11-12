# Step 0: set up, check the photo, fit the canvas, beginner version

## 0. Set up
- Lesson folder: `output/<photo stem>_skill_<YYYYMMDD-HHMMSS>/`. Pass it as `--lesson` to every tool.
- The tools also write `ledger.json` (every render and filter run), `00_canvas.png`, and filter outputs there. Put
  trial outputs you won't use under `<lesson>/trials/` with `--out`.
- Read `docs/decisions.md`.
- Technique: if the owner named one, use it. Otherwise read every file in `techniques/` and pick the one that fits
  this photo and level. Record why, and every technique you passed on, in `notes.json` (`technique`).
- Read the technique YAML: `rules`, `brush_moves`, `palette`, `step_range`, `ground`, `framing`, `simplify`,
  `finish`, `detail_budget`, `beginner_version`.
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
`notes.json` now and add to it as you go; the full schema is in step 8.

## 0b2. Fit the picture to the canvas (only with `--canvas`)
1. Decide the subject's box and the focal point (0-1 from the top left). The subject is what the picture is
   about (the balloon, the boat and its reflection), not the whole scene.
2. `fit-canvas <photo> --lesson <lesson> --canvas <WxH> [--orientation ...] --focus X Y --keep X0 Y0 X1 Y1 --why
   "<subject and what must stay>"`. It picks the cheapest fit: `none` (same shape), `crop` (free, subject whole,
   at most about a third lost), or `extend` (the picture sits on the canvas with gray edges). It places the canvas
   in the image model's nearest frame (square, 3:2, or 2:3), with gray bands outside it when the shapes differ.
3. If `needs_render` is true, run the render command in its `advice` once. Read the result: nothing painted
   changed, the edges continue the scene, nothing new appeared. Redo once at most.
4. From here on, "the photo" is `00_canvas_fit.png` (or `00_canvas_frame.png` when no render was needed). Renders
   and step images stay in the model's frame; `publish` crops every step to the canvas for the painter.
5. Keep two coordinate systems apart: `looks_like` and render prompts describe the frame; the step text describes
   the canvas. Before writing text, run `canvas-view 99_finish.png --lesson <lesson>` and measure on
   `canvas/99_finish.png` with `grid --percent`.
6. Record `canvas_fit` in `notes.json`: `{"canvas": "11 x 14 in, portrait", "mode": "crop", "why": "...", "lost":
   "the right 15% of empty water"}`.

**Size changes the lesson, not just its shape.** Scale to the canvas's area:
- Detail budget: under 120 sq in (10x10), `max_parts` minus 2. From 120 to 300 (11x14 is 154), as is. Over 300
  (24x30 is 720), add 3, and textures can be a size smaller.
- Biggest brush: a 3/4 inch flat on a 10x10, a 1 inch flat on an 11x14, a 2 inch flat or wide house brush on a
  24x30 (rounds a size or two up).
- The page says how many inches each 10% is. Inches in the text are fine for sizes ("about 2 inches wide").

## 0c. Is it beginner-sized? (`00_beginner.png`)
Every step is copied backward from the finish, so whatever detail the finish has, some step has to paint. For the
technique's level (`detail_budget`), answer:
- **Tiny separate things** that aren't the subject: houses, windows, people, fence posts, a village?
- **Textures made of hundreds of items**: stalks, blades of grass, single leaves, bricks, a dust of stars?
- **Detail inside big shapes** one repeated mark can't make: veined clouds, carved bark, every wave?
- **More parts** at different distances than `detail_budget.max_parts`?

If any answer is yes, make a beginner version first and make the rest of the lesson from it:
`render --step beginner --inputs <photo> --quality medium --out <lesson>/00_beginner.png --why-not-filter "<why no
filter can drop and merge these>" --prompt "<beginner_version.prompt> <your list> <framing>"`.
Your list names what to drop ("remove the village"), merge ("the clouds become three big soft masses"), and turn
into a repeated mark ("the lavender becomes rows of loose purple dabs, darker at the base, no single stalks").
Keep the composition, subject, light, and mood. Read the result: everything the picture is recognized by is
there, nothing on your list survived. One redo at most. From here on, "the photo" means `00_beginner.png`.

Record the answers and the list in `notes.json` as `beginner_version`, and put `00_beginner.png` in
`notes.filters` with `"label": "Beginner version"`, `"tool": "render"`, `"verdict": "kept"`. If every answer is
no, skip it and say so.
