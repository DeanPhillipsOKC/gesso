# Steps 6 and 6a: write the steps (`text.json`), fix texture jumps

## 6a first: base coats and texture passes
For a base coat followed by texture passes over the same area (planned with identical `regions`), run:
`from-finish --lesson <lesson> --steps <coat and pass ids> --in-place --why "<area>"`.
It cuts those steps from the finish (a flat coat, then passes darkest first) and keeps the other steps rendered.
Always `--in-place`: without it, it makes a recut in a new folder, which can never be sealed. Then `lock-steps`.

Any other step that turns more than 10% of the canvas from flat to textured shows in `texture_jumps` (from
`publish` and `step-pairs`). Fix every one before the text is final:
`split-texture --lesson <lesson> --step <id> --ids <new ids...> --names "<names>"...` inserts in-between pictures
(the step's new marks arriving darkest first) as new steps before it. Use two for a dense texture. Give each new
step its colors in plan.json and its own text (only the marks it adds), trim the original step's text, then
`lock-steps`, `publish`, and check `texture_jumps` is empty. Never leave a jump.

## 6. Write the steps
1. Run `mix --lesson <lesson>`. It computes every paint's recipe from the palette tubes and prints how far each
   lands (Delta E). The computed recipes replace yours on the page, so never write amounts in the text: name
   paints only. For a paint in `unreachable`, say so in that step's `paint_notes` ("as close as these tubes get")
   or move its sample spot.
2. Read the final images in order and write each step from what its image actually shows: the real shapes and
   areas, the mixes by paint name, the planned advice that still applies, plain words, 2 to 5 instructions.

### Keep it short
A beginner reads this with a wet brush in hand: each step's `what_to_do` under about 100 words, each instruction
under about 35.
- Don't repeat what the page shows: recipes, brush chips, `strokes`, and the drying line. Name the paint, brush,
  and stroke; don't explain them again.
- The drying cue in about four words ("Let the sky dry."), paint load in one or two ("creamy", "nearly dry").
- Once-per-lesson notes (colors dry darker, the ugly stage, a test stroke) go in `paint_notes` or `watch_out`.
- **Never trim a size, a position, or a count.** Where, how big, and how many are the instruction. Give them as
  grid numbers ("centered 28% across, about 15% wide") or in a diagram.

When `publish` lists `long_steps` or `long_instructions`, ask why:
- it repeats the page or explains a stroke or drying: cut the repeat;
- it describes something that could be shown: use a diagram or a `values` table and cut the description;
- it's one instruction doing two moves: split it into two;
- the step has a lot to do: split the step in the plan if its pictures allow, move how-to into `strokes` or a
  diagram, or keep it and record why in `notes.json` under `long_steps_kept` (`{"<step id>": "why"}`). A clear long
  step beats a short vague one.

### Show, don't tell
When something takes more than a sentence to say (a shape, a stroke's path, where things go, the order of
values), show it and keep the words to a pointer ("build the hull as in the diagram"):
- a construction diagram (step 7) for shapes, stroke paths, and order of moves;
- a `values` table for depth: one row per value, dark first, each with its paint and where it goes;
- the step picture for placement: "where the picture shows the gold glow", plus a grid percentage.

`values` (optional, per step): `[{"value": "dark", "paint": "Cloud shadow", "where": "tops and far sides"}, ...]`.
Use it whenever a step builds depth on one thing from more than one value. Two limits:
- A table adds to the instructions, never replaces them. Each instruction still names its paints.
- A color sequence isn't a table of values. A sunset going blue, coral, red-orange, gold is hues in order: name
  the bands in the instruction, in order, with where each sits.

### Every step also has
- the light: the first step's first instruction says where the light comes from, and every highlight after it
  stays on that side;
- `colors` in plan.json holding every paint an instruction or table names (`publish` lists misses in
  `paints_not_listed`). A mix used only in one step still goes in that step's `colors`;
- `brushes`: each by its usual name and size (`1 inch flat`, `#8 round`, `Liner (#1 or #0)`) and what it's for;
- `strokes`: the named strokes from the technique's `brush_moves` (X stroke, wet blending, dabbing, ...), each with
  one or two sentences on doing it with that brush, for this picture;
- `summary`: one sentence under about 90 characters saying what the step paints;
- `made_with`: `filter:<name>`, `composite:from-finish`, `throwaway:<script>`, `render+throwaway:<script>`,
  `render+filter:<name>`, or `render`, for the image the lesson ends up with, and `reason`.

`publish` also lists `duplicate_recipes`: two paints that mix the same. Merge them, or move one's sample spot.

```json
{"steps": [{"stage_id": "sky-gradient", "summary": "Blend the sunset sky from blue at the top to orange.",
            "what_to_do": ["..."], "mixes": ["Sunset orange"], "watch_out": ["..."], "values": [],
            "paint_notes": [], "made_with": "render", "reason": "why this tool",
            "brushes": [{"brush": "1 inch flat", "use": "covering and blending the sky"}],
            "strokes": [{"name": "X stroke", "how": "Criss-cross the flat in overlapping X shapes so the paint blends."}]}]}
```
