# Brief: write the painter's plan (spike S7, #172)

You are planning a beginner acrylic paint-along lesson for one picture, the way a painting teacher plans a session
before picking up a brush: what gets painted, in what order, and what each step puts on the canvas. You write the plan
only. Nobody has measured or outlined anything yet, and you won't either: the pictures are made to fit your plan
afterwards, so the plan has to stand on what a painter knows, not on what a tool can cut out.

You were given: a picture name, a folder with its files, and the path to write `painter.json` to.

## What to read

- In the picture's folder: `photo.jpg` or `photo.png` (what the painter wants to paint), `99_finish.png` (the finished
  painting the lesson ends at, in the image model's frame) and `canvas.json` (the canvas size in inches; `canvas_box`
  is the part of the frame the painter's canvas shows). If there is a `00_beginner.png`, the lesson is made from that
  simpler version, not the photo.
- `techniques/acrylic-paint-along-beginner.yaml`: the approach. Its `v2_rules`, `v2_step_range`, `v2_stage_range`,
  `max_mixes` and `stroke_results` bind you.
- The element techniques: `.venv/bin/python spike/tools.py elements` lists them (what each is for and its steps in
  order). Read the file in `techniques/elements/` of every one you pick.
- The stroke cards: `ls techniques/strokes/`. Read the card of every stroke you use (its `brushes` are the kinds of
  brush that stroke takes).
- `docs/research/acrylic-paint-along.md`: the research the technique comes from. Read its "For Gesso" rules and the
  sections your picture needs.

Read nothing else. In particular no `plan.json`, no outlines, no other lesson or run (`output/`, `site/`,
`spike/experiments/bench/baseline/`, `spike/experiments/bench/runs/`, `spike/experiments/bench/plan-first/`,
`spike/tests/fixtures/`), and nothing under `docs/spikes/` or `docs/design/`. The point is a plan that comes from the
picture and the technique, not from an earlier breakdown of it. Don't run any tool but `elements` and `painter-check`.

## What stands

These are the owner's decisions. Don't work around them.

- **Paint-along on a white canvas, back to front.** No toned ground, no sketch, no block-in of the whole canvas
  first. The background is painted straight through where things in front will go; what's nearest is painted last.
- **12 to 24 steps in 4 to 9 stages.** More small steps beat fewer big ones, up to the top of the range.
- **One move per step:** one brush, one stroke (a card's id), one to three paints. If a step needs "then", it's two
  steps. A background blended wet in one go (a sunset sky) is one step with all its paints: mark it `"blend": true`.
- **Technique comes from the element files and the cards, not from memory.** Every thing follows one element
  technique: its steps in the element's order, an `optional` one may be left out, a `repeat` one may be several
  steps. A step's stroke is one its element step lists. When nothing fits a thing, pick the closest element and say in
  the thing's `why` what it lacks.
- **Texture is never one step.** A base coat, then a pass per paint, each covering less than the one before. No step
  takes a thing from flat to finished.
- **About 10 mixes** for the whole lesson. A lighter or darker version of a paint ("plus white") doesn't count.
- The painter is a beginner. Leave out what a beginner can't make and say so.

## What is yours to decide

- **What the things are.** Name them as a painter sees them. No boxes, no positions.
- **The stages.** A stage is what the painter finishes before stopping. It can be one thing ("The sky") or a pass
  over the picture ("The shadows", "The last lights"), whichever a teacher would call out.
- **Steps that cross things.** A step may lay paint on more than one thing when a painter would do it in one go, with
  the brush and paint already loaded: the same dark under three things, a reflection pulled down under each thing in
  that thing's own mix, the last lights the sun puts on everything. Do this only where it is really one move (same
  brush, same stroke, same paints). Don't cross things for the sake of it, and don't split one move across steps
  because it touches two things.
- **The order**, inside what back to front allows.

## What a good plan does

- **Every thing you can see in the finish is laid by a step that names it.** Look hard at the focal point: an eye, a
  nose, a window, a whisker. If it's in the finish, some step's `what` says "and the dark of the nose and eye", and
  that step's paints can paint it. Nothing may turn up in the painting that no step put there.
- **Each step's `after` says what the canvas shows when the step is done:** what is new, and what is still flat or
  bare. Someone who has only the canvas before and your words should be able to tell what the canvas after looks like.
- **Each step's paints are what it really puts down.** If a step lays a gold rim and a pink nose, it names a gold and
  a pink.
- **A mix is used in steps close together** where it can be: mixes dry on the palette.
- **The last stages matter most.** Don't spend the step budget on the background.

## The file

Write `painter.json` at the path you were given:

```json
{
  "plan_first": 1,
  "picture": "<the picture's name>",
  "subject": "what the painting is of",
  "focal_point": "where the eye should land",
  "light": "where the light comes from, in words",
  "why": "two or three sentences: how you'd take a beginner through this picture, and why in this order",
  "things": [
    {"id": "sky", "name": "The sunset sky", "element": "sky-blend", "why": "one line: why this element fits",
     "left_out": "optional: what you leave out for a beginner"}
  ],
  "paints": [
    {"name": "Pale gold", "looks": "a pale warm yellow, the lightest color in the sky", "things": ["sky", "clouds"]}
  ],
  "stages": [
    {"id": "the-sky", "name": "The sky", "steps": [
      {"id": "sky-blend", "name": "Blend the sunset sky",
       "lays": [{"thing": "sky", "what": "the whole sky: pale gold at the hills, rising to gray-violet at the top"}],
       "paints": ["Pale gold", "Gray-violet"], "blend": true,
       "stroke": "side-to-side-blend", "brush": "1 inch flat",
       "after": "The top third of the canvas is a smooth sky, gold low and violet high. Everything below is bare.",
       "why": "optional: why this comes now"}
    ]}
  ]
}
```

- Ids are lowercase slugs (letters, digits, hyphens), and no stage and step share one.
- `lays` has one entry per thing the step puts paint on. More than one entry is a step that crosses things.
- A step's `name` is a short instruction ("Dab the rust foliage"), not a label ("Foliage").
- Paint names say what the paint looks like ("Warm rust"), and fit every thing that uses it. Brush sizes follow the
  canvas: the biggest brush for the biggest areas, a liner only for lines.

Then run `.venv/bin/python spike/experiments/v3_plan_first.py painter-check <your painter.json>` and fix what it
lists until `problems` is empty. It checks the file's shape only; whether it's a good lesson is on you.

Reply with the path, the number of steps and stages, which steps cross things and why each is one move, and anything
in the finish you chose to leave out.
