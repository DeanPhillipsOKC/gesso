# Changelog

What each Gesso version added to the lessons it makes. Every lesson is stamped with the version that made it
(page footer, receipt, `lesson.json`), so an older lesson is missing whatever came after its version.

While Gesso is a proof of concept (POC), the minor number goes up for anything that changes what a lesson looks
like or contains, and the patch number for fixes. The numbers before 0.9.0 were given afterward, from the history.

## POC 0.17.0 (2026-11-11)
- `lock-steps` runs a backward pass from the finish when every step has regions: wherever no later step paints,
  a step already shows the finished painting, so the last step only shows what it adds (#30).

## POC 0.16.0 (2026-11-11)
- `protect` boxes: inside a step's regions, things already painted that must stay put. There only the step's own
  paints may change anything (matched mostly by hue, so shaded strokes count), with a crisp edge (#30).

## POC 0.15.0 (2026-11-11)
- Step pictures no longer repaint earlier work (#30): each step says where it paints (`regions` in plan.json),
  and `lock-steps` puts back any change outside them, free. Raw renders stay in trials/raw/.

## POC 0.14.1 (2026-11-11)
- Canvas crops split the cut evenly between both sides, shifting only as far as the subject needs.
- No band-fill render when the photo already has the frame's shape: the cut-off edges fill the bands for free.
- `grid --percent`: lines at every 10% of width and height, so measurements match the page's percentages on any
  canvas shape.
- A stroke result for horizontal dashes on water (ripples, sun paths, reflections).

## POC 0.14.0 (2026-11-11)
- `--canvas WxH` (inches): the picture is fitted to the painter's canvas before planning, cheapest first: no
  change, a free crop that keeps the subject, or one render that extends the scene. A rectangular canvas hangs
  either way, so it follows the picture unless `--orientation` says otherwise.
- Renders stay in the image model's nearest frame; every step picture the painter sees is cropped to the canvas.
- Canvas size scales the lesson: the detail budget (fewer parts on a 10x10, more on a 24x30) and brush sizes.
- The page shows the canvas size and how many inches each 10% is, so grid positions can be marked with a ruler.

## POC 0.13.0 (2026-11-11)
- Show, don't tell: when something takes more than a sentence to explain (a shape, a stroke path, which value
  goes where), the lesson shows it with a diagram, a `values` table, or the step picture, and the words point at it.
- Steps can carry a `values` table (dark, mid, light: paint and where), shown with swatches on the page and in
  the walkthrough export.
- `publish` also lists single instructions over about 40 words in `long_instructions`.
- The word budget is a signal, not a cap: a long step is trimmed only where it repeats the page; an instruction
  doing two moves is split; a step that really has a lot to do is split in the plan, moved into strokes or a
  diagram, or kept long with a reason. Length is checked before the step review, so the reviewer catches any
  instruction trimming made vague.

## POC 0.12.0 (2026-11-11)
- A word budget for step text (about 100 words a step), with `publish` listing steps over it in `long_steps`.
  The page already shows recipes, brushes, strokes, and drying, so the text doesn't repeat them.
- The first step says where the light comes from.
- Paints used straight from a tube keep a one-tube recipe instead of a computed three-tube mix.
- Two more stroke results: strokes toward a vanishing point (rows, paths) and horizontal strokes for flat ground.
- `preview-diagrams` says when lesson.json has no diagrams yet, instead of blaming the browser.

## POC 0.11.0 (2026-11-11)
- Technique rules and stroke results now come from cited research (`docs/research/acrylic-paint-along.md`):
  three values per 3D object, a stated light direction, distance and edges, stroke direction, paint load in
  every instruction, drying before layering, coats for light over dark, and test strokes.

## POC 0.10.0 (2026-11-11)
- A fresh reviewer checks each step's text against a measured map of what its picture changed, and the skill
  fixes flat, missing, vague, and wrong-stroke instructions from it, shown under "What the reviewer caught" (#24).
- New technique rules: let a layer dry before painting over it, and give each area the values the picture shows
  (dark, middle, light) instead of one flat mix.
- The technique records what each stroke really leaves on the canvas (`stroke_results`).

## POC 0.9.0 (2026-11-11)
- Each lesson is stamped with the Gesso version, commit, and date (#27).

## POC 0.8.0 (2026-11-11)
- `publish` also exports `embed/`, so a blog post can show the lesson as a step-by-step walkthrough, with a
  one-line summary per step (#26).

## POC 0.7.0 (2026-11-11)
- A drawing of each brush and the mark it makes, in "What you need" and on every step (#25).

## POC 0.6.0 (2026-11-11)
- Paint recipes are computed with a pigment mixing model (Mixbox) instead of written by eye, with a "closest
  you can get" note for colors the tubes can't make (#22).
- Every step lists the paints it uses with their recipes, so you can mix as you go.

## POC 0.5.0 (2026-11-11)
- Busy pictures get a simpler beginner version first, and the lesson is made from it (PR #21).

## POC 0.4.0 (2026-11-11)
- Construction diagrams for shapes a beginner needs broken down, and a beginner check that decides where they
  go and says why (PRs #19, #20).
- Screenshots are cropped to the picture automatically.

## POC 0.3.0 (2026-11-11)
- "How this lesson was made": technique, step order, filters, review notes, and the receipt, folded away
  (PR #17).
- The sky runs past what covers it, and shapes are built from simple pieces (PR #18).

## POC 0.2.0 (2026-11-10)
- The `paint-lesson` skill: Claude Code runs the lesson, free filters first, paid renders only when needed,
  published as a Claude artifact with brushes and strokes per step (#7, #9, #10).

## POC 0.1.0 (2026-10-19)
- The pipeline spike: a lesson as a folder of step images from one script (#3).
