# Brief: write the painter's plan (pipeline v3)

You are planning a beginner acrylic paint-along lesson for one picture, the way a painting teacher plans a session
before picking up a brush: what gets painted, in what order, and what each step puts on the canvas. You write the
plan only. Nobody has measured or outlined anything, and you won't either: the step pictures are made to fit your
plan afterwards (the image model erases the finished painting backward, one piece of your plan at a time), so the
plan has to stand on what a painter knows.

You were given: the lesson folder, the photo's path, the technique file, and the palette's name when the painter
uses their own tubes. Write `plan.json` in the lesson folder.

## What to read

- In the lesson folder: `99_finish.png` (the finished painting the lesson ends at), the picture it was painted from
  (`00_beginner.png` when there is one, else `00_canvas_frame.png` or `00_canvas_fit.png`), and `canvas.json` (the
  canvas size in inches).
- The technique file. Its `v2_rules`, `v2_step_range`, `v2_stage_range`, `max_mixes` and `stroke_results` bind you.
- The element techniques: `.venv/bin/python spike/tools.py elements` lists them (what each is for and its steps in
  order). Read the file in `techniques/elements/` of every one you pick.
- The stroke cards: `ls techniques/strokes/`. Read the card of every stroke you use (its `brushes` are the kinds of
  brush that stroke takes).
- `docs/research/acrylic-paint-along.md`: its "For Gesso" rules and the sections your picture needs.

Read nothing else: no other lesson or run (`output/`, `site/`, `spike/`), and nothing under `docs/spikes/` or
`docs/design/`. Run no tool but `elements` and `plan-check`.

## What stands

These are the owner's decisions. Don't work around them.

- **Paint-along on a white canvas, back to front.** No toned ground, no sketch, no block-in of the whole canvas
  first. The background is painted straight through where things in front will go; what's nearest is painted last.
- **12 to 24 steps in 4 to 9 stages** (the technique's ranges). More small steps beat fewer big ones.
- **One move per step:** one brush, one stroke (a card's id), one to three paints. If a step needs "then", it's two
  steps. A background blended wet in one go (a sunset sky) is one step with all its paints: `"blend": true`.
- **Technique comes from the element files and the cards, not from memory.** Every thing follows one element
  technique: its steps in the element's order, an `optional` one may be left out, a `repeat` one may be several
  steps. A step's stroke is one its thing's element lists. When nothing fits a thing, pick the closest element and
  say in the thing's `why` what it lacks.
- **Texture is never one step.** A base coat, then a pass per paint, each covering less than the one before. No step
  takes a thing from flat to finished.
- **At most 10 mixes** (the technique's `max_mixes`). A lighter or darker version of a paint (that paint with white
  or a dark added) isn't counted: give it `"of": "<the paint's name>"`. Two paints a painter can tell apart are
  never merged to get under 10, so a plan may end above it; `plan-check` says when two could be one.
- The painter is a beginner. Leave out what a beginner can't make and say so (`left_out`).

## What is yours to decide

- **What the things are.** Name them as a painter sees them. No boxes, no positions.
- **The stages.** A stage is what the painter finishes before stopping. It can be one thing ("The sky") or a pass
  over the picture ("The shadows", "The last lights"), whichever a teacher would call out.
- **Steps that cross things.** A step may lay paint on more than one thing when a painter would do it in one go,
  with the brush and paint already loaded: the same dark under three things, the last lights on everything. Only
  where it is really one move (same brush, same stroke, same paints).
- **The order**, inside what back to front allows.

## What a good plan does

- **Every thing you can see in the finish is laid by a step that names it.** Look hard at the focal point: an eye, a
  nose, a window, a whisker. If it's in the finish, some step's `what` says it, and that step's paints can paint
  it. Nothing may turn up in the painting that no step put there.
- **Each step's `after` says what the canvas shows when the step is done:** what is new, and what is still flat or
  bare. A render is asked to take the finished painting back to it, so it must be true of the canvas, and exact
  about the thing the step painted ("a flat rust-brown cow shape with no shading, eyes or horns").
- **Each step's paints are what it really puts down.** If a step lays a gold rim and a pink nose, it names a gold
  and a pink.
- **A mix is used in steps close together** where it can be: mixes dry on the palette. `plan-check` lists every
  paint that is used again three or more steps after its last use (`mix_again`).
- **The last stages matter most.** Don't spend the step budget on the background.

## The file

```json
{
  "plan_version": 3,
  "photo": "<the photo's path, as you were given it>",
  "technique": "<the technique file, as you were given it>",
  "technique_why": "one line: why this approach fits the picture and the painter's level",
  "palette": "<only when you were given one>",
  "subject": "what the painting is of",
  "focal_point": "where the eye should land",
  "light": "where the light comes from, in words",
  "why": "two or three sentences: how you'd take a beginner through this picture, and why in this order",
  "things": [
    {"id": "sky", "name": "The sunset sky", "element": "sky-blend", "why": "one line: why this element fits",
     "behind": []},
    {"id": "cow", "name": "The highland cow", "element": "shaggy-animal", "why": "...",
     "behind": ["hillside", "meadow"], "plain": "the plain rust-brown cow shape",
     "left_out": "optional: what you leave out for a beginner"}
  ],
  "paints": [
    {"name": "Pale gold", "looks": "a pale warm yellow, the lightest color in the sky", "color": "#f1d9a0",
     "things": ["sky", "clouds"]},
    {"name": "Cream gold", "looks": "Pale gold with more white", "color": "#f8ecc8", "of": "Pale gold",
     "things": ["clouds"]}
  ],
  "stages": [
    {"id": "the-sky", "name": "The sky", "steps": [
      {"id": "sky-blend", "name": "Blend the sunset sky",
       "lays": [{"thing": "sky", "what": "the whole sky: pale gold at the hills, rising to gray-violet at the top"}],
       "paints": ["Pale gold", "Gray-violet"], "blend": true,
       "stroke": "side-to-side-blend", "brush": "1 inch flat",
       "after": "The top third of the canvas is a smooth sky, gold low and violet high. Everything below is bare.",
       "why": "optional: why this comes now"}
    ]},
    {"id": "the-cow", "name": "The cow", "steps": [
      {"id": "block-in-cow", "name": "Block in the cow", "block_in": true,
       "lays": [{"thing": "cow", "what": "the whole cow as one flat rust-brown shape, built from an oval and a box"}],
       "paints": ["Rust brown"], "stroke": "build-from-pieces", "brush": "1/2 inch flat",
       "after": "A flat rust-brown cow shape stands on the meadow, with no shading, face or horns."},
      {"id": "shade-cow", "name": "Shade the cow's underside", "unit": "The cow's shading",
       "lays": [{"thing": "cow", "what": "dark umber under the belly, behind the legs and under the chin"}],
       "paints": ["Dark umber"], "stroke": "curved-strokes", "brush": "#8 round",
       "after": "The cow has a dark underside and still no face or coat texture."}
    ]}
  ]
}
```

- Ids are lowercase slugs (letters, digits, hyphens), and no stage and step share one.
- **`behind`** on every thing: the ids of the things already painted that it sits on, as the canvas shows them
  where the thing will go (the cow stands on the hillside and the meadow). `[]` when it goes on bare canvas.
- **`plain`** on a thing painted in more than one go: how it looks after its first coat, as a short phrase ("the
  plain gray cat shape"). A render told to keep the thing while it is still plain is told this.
- **`called`** (optional) on a thing whose name would mislead someone asked to remove it or keep it: a name that
  says only what it is ("the pale sky through the window", for a thing named "The sky and trees through the
  window" when the trees are a thing of their own).
- **`color`** on every paint: a rough hex of it. The paints are fitted to the painting starting from it.
- **`lays`** has one entry per thing the step puts paint on. More than one entry is a step that crosses things.
- **`"block_in": true`** on a step that is a thing's first coat as one flat color: the whole shape, edge to edge,
  in its main or dark paint, with nothing else on it yet. Mark it only where that is true: dabs, a blend, or a coat
  on part of a thing are not a block-in. Its picture will be the thing as a flat shape, and later steps bring the
  rest.
- **`unit`** on the step `plan-check` asks for: a name for what that step and the steps with it add, as the page
  will say it ("The cow's shaggy coat"). You can't know which steps need one until `plan-check` has run.
- A step's `name` is a short instruction ("Dab the rust foliage"), not a label ("Foliage").
- Paint names say what the paint looks like ("Warm rust"), and fit every thing that uses it. Brush sizes follow the
  canvas: the biggest brush for the biggest areas, a liner only for lines.

Then run `.venv/bin/python spike/tools.py plan-check --lesson <the lesson folder>` and fix what `problems` lists
until it is empty. It checks the plan against itself, the technique and the library; whether it's a good lesson is
on you.

Reply with: the number of steps and stages, the units `plan-check` printed (how many renders), which steps cross
things and why each is one move, the mixes count, and anything in the finish you chose to leave out.
