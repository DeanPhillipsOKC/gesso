# Step 3: the plan (`plan.json`)

Plan from the finish, under the technique's rules and step range (read `plan_lesson`'s prompt in `spike/run.py`).
Write `<lesson>/plan.json` with exactly these fields:

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
             "how": ["2 to 5 instructions, each naming its brush move"], "watch_out": ["1 or 2 beginner mistakes"],
             "regions": [[0.0, 0.0, 1.0, 0.62]], "protect": []}]
}
```

## Measure, don't guess
- Run `grid --percent` on the finish before writing any `looks_like`, and give positions as numbers ("the sun's
  center is 44% across and 40% down").
- Give edges as numbers too: when a step leaves white canvas, "a straight lower edge at 62% down".
- Spell out a subject's exact pattern (stripe colors in order, left to right) so a subject painted late matches
  the finish.
- Describe only what the finish shows. If later layers hide most of something (branches inside a crown), say how
  much shows.

## Fields
- Step `colors` and every diagram `paint` are names from `paints`. A tube used straight is added as a paint.
- The last step is the finished painting: `"looks_like": "The finished painting."`, `"covers_canvas": true`.
- Step ids are unique lowercase slugs.
- Recipes use only palette tubes (a first guess; `mix` computes the real ones in step 6).
- `sample_x`/`sample_y` (0-1) point at a flat patch of that paint in the finish; `publish` snaps each hex to the
  color there. The palette filter on the finish helps.
- `regions`: where the step paints, 1 to 4 boxes `[x0, y0, x1, y1]` (0-1, measured). Every step has them, the last
  one too. A full background is `[[0, 0, 1, 1]]`. Cover only what the step adds. `lock-steps` and `from-finish`
  depend on them.
- `protect`: boxes inside the regions over things already painted that must stay put (a vine's box over the
  pumpkins). Keep them tight. Details in step 5b.

## Read the plan as a painter would
- A background step lets the brush keep moving: run the sky to the bottom edge or well past the horizon, and let
  the ground paint over it. Don't stop it at a hill line.
- No step jumps from flat to dense texture. Dense texture (lavender rows, foliage, grass) is a base coat step,
  then pass steps (dark marks, then lighter marks), all with **identical `regions`**, so step 6a can cut them
  from the finish.
- A block-in step for a shaped object says how to build the shape from simple pieces in its `how` (a pumpkin: a
  center oval, then curved side segments like ( ) on each side).

Then decide per step how to make it (the tool order) and note it for `made_with` later. In a paint-along most
steps are "the finish with later parts not painted yet", which today is a render (or a from-finish cut for a
coat and its passes). A sketch step is the `edges` filter; a value or color-blocking step may be `value-study` or
`posterize`. Filter-made step images go at `<lesson>/NN_<id>.png` (NN from 01).
