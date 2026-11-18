---
name: paint-lesson
description: Turns a photo into a step-by-step beginner acrylic painting lesson (Gesso pipeline v3). A painter's plan is written first, the finished painting is erased backward by the image model one piece of the plan at a time, and every step picture comes from that chain; the words are written a stage at a time from the pictures and a measured fact sheet. Use when the owner runs /paint-lesson <photo>, or asks for a painting lesson from a photo.
---

# paint-lesson

You are the lesson pipeline (version 3). You run the tools in `spike/tools.py` and start the helpers that plan,
check and write; the tools measure and draw. The lesson has to stand on its own: once you seal it, nobody fixes it
by hand.

The design behind this is `docs/design/pipeline-v3.md`. You don't need to read it to run the skill.

**How this skill is laid out.** This file is the spine. Steps 0 and 1 are in `steps/`; the rest of the run is
`v3/run.md`, which points back to `steps/8-finish.md` for the end. **Read a step's file when you start that step**,
even if you read it earlier. Don't read ahead. Pipeline v2's steps 2 to 7 were removed with v2 (#238).

## Arguments
- `<photo>` (required). Usually `photos/<name>.<ext>`: the site's pictures are kept there in git, so a fresh clone
  can rerun any of them. Step 0 stores a new picture there (`store-photo`).
- `--canvas WxH` (optional, inches, e.g. `11x14`) with `--orientation portrait|landscape`. Without it, step 0b2
  still fits the photo to a canvas: `fit-canvas` with no `--canvas` picks the standard size closest to the photo's
  shape (8x10, 9x12, 11x14, 12x16, or 16x20, 11x14 when two fit as well) and records `"chosen": "default"` in
  `canvas.json`. Every step says where in inches from the canvas edges, never by tape marks or percentages. The
  tools refuse a lesson with no `canvas.json` unless its finish already has a standard canvas's shape (only the
  test fixtures do)
- `--technique <file>` (optional): force the whole-painting approach (a file in `techniques/` with version 2 keys:
  `v2_step_range`, `v2_rules`). Without it, choose the approach that fits the picture and the level and say why in
  `technique_why`. Today only `acrylic-paint-along-beginner.yaml` has version 2 keys.
- `--palette <name>` (optional): the painter's own tubes from `palettes/<name>.yaml`. Put `"palette": "<name>"` in
  plan.json.
- `--v3` (optional, does nothing): v3 is the run with or without it. Older notes and commands still pass it.

Run every tool with the venv: `PY=.venv/Scripts/python.exe` (Windows) or `.venv/bin/python`.

## Rules for the whole run
1. **Renders:** the finished painting, and only when needed the beginner version, the canvas extend, and one
   background picture; then the chain, one low render a unit of the plan, about 2 cents each. `erase` caps the
   chain's own spending by itself (twice what the chain costs once); pass it no `--max-cost`. Pass `--max-cost 0.40`
   to every other render.
2. **Measure, don't guess.** Nothing is measured with `grid` and there is no `part-colors`: the paints are fitted
   by `paints`/`build-steps` from the chain, and every number in the words comes from the fact sheet `packets`
   writes.
3. **Every tool prints `problems`.** An empty list means go on. Otherwise each one says what to change: change it
   and run the tool again. The tools are free and take seconds, so loop until they're clean. Never edit a tool's
   output file by hand to make a problem go away.
4. **Technique comes from the technique file, the research file, the element techniques, and the cards**
   (`techniques/elements/`, `techniques/strokes/`, `techniques/basics/`), not from memory. Every part follows an
   element technique (the plan's writer picks them, `v3/plan-brief.md`).
   When you rely on something they don't cover, say so in `notes.json` under `learned`.
5. **One move per step.** One brush, one stroke, one to three paints. If a step needs "then", it's two steps.
6. **Don't flip a card's or an element's `checked`.** The owner does that after painting from it.
7. **Keep `notes.json` as you go,** not at the end.
8. **Stay in your lesson folder** (and `photos/`, where step 0's `store-photo` stores the picture). Don't edit code, skills, techniques, elements, cards, palettes, or docs during a
   run (a drafted element goes in `<lesson>/elements/`). If
   a tool is wrong, work within what the skill allows and report it. Scratch files and scripts go in
   `<lesson>/trials/`, nowhere else, and never keep the lesson's path in a shared file: other runs share the
   machine.
9. **The order is fixed, and going back means running forward again.** After any change to `plan.json`:
   `plan-check`, `erase`, `build-steps`, `step-aids`, `mix`, `draft-text`, `check`, then the chain's checker and its
   redos, then `packets`, the stage writers, `check-text`, and `check` again, in that order (`v3/run.md`). A chain
   request that didn't change costs nothing the second time. Don't skip one because it ran before.
10. **Seal last.** Your last command is `publish --lesson <lesson> --final`. It refuses until `check` is clean.
   After the seal, change nothing.

## Steps

| Step | File | Makes |
|---|---|---|
| 0. Set up, check the photo, fit the canvas, beginner version | `steps/0-setup.md` | lesson folder, `00_*.png` |
| 1. Reference and finished painting | `steps/1-reference-finish.md` | `00_reference.png`, `99_finish.png` |
| A to E. The plan, the chain, the pictures, the words, the check and seal | `v3/run.md` | `plan.json`, `chain/`, `NN_<id>.png`, `aids/`, `words/`, `text.json`, `review.json`, the sealed lesson |
