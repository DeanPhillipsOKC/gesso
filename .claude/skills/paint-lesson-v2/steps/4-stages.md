# Step 4: stages and steps

Read the technique's `v2_rules`, `v2_step_range`, `v2_stage_range`, and `stroke_results`. List the stroke cards:
`ls techniques/strokes/` (a step's `stroke` is a card's file name without `.yaml`). Read the cards you expect to
use.

## The shape
```json
"stages": [
  {"id": "bird", "name": "The chickadee", "steps": [
    {"id": "bird-body", "name": "Block in the body", "part": "bird", "show": "flat",
     "paints": ["bird-2"], "stroke": "build-from-pieces", "brush": "1/2 inch filbert"},
    {"id": "bird-chest", "name": "Light the chest", "part": "bird", "show": "pass",
     "paints": ["bird-3"], "stroke": "curved-strokes", "brush": "#6 round"}
  ]}
]
```
A stage is one thing the painter finishes before stopping ("The sky", "The far woods", "The chickadee"). A step
paints inside **one** part, with one stroke and one brush.

| `show` | The picture shows | Use for |
|---|---|---|
| `flat` | the part as flat color in the step's paints, no texture | a base coat or block-in, in the part's dark or main paint |
| `pass` | the finished painting wherever its color is nearest this step's paints; the rest stays as it was | each layer over the coat: one paint, or two close ones |
| `full` | the part exactly as finished | a part one move makes: a hill, a sun, a small one-color part |
| `blend` | the same as `full` | colors blended wet in one go (a sunset sky). May use more than 3 paints |

## How to build a part's steps
- **A sky, or any background blended wet, is one `blend` step** with all its paints, never a flat coat and
  passes: a blend cut into passes comes out as ragged patches nobody could paint. Clouds, glow, and haze that sit
  on it as their own parts get their own steps after it.
- Follow the research's core pattern (section 4): the whole shape in a darker or middle value (`flat`), then the
  lighter value on the lit side (`pass`), then the lightest on a small area (`pass`). Each covers less than the one
  before. A part's last step shows everything of it that's left.
- A part's paints are the ones `paints` listed with that part in `parts`. A step uses only its own part's paints.
  When the part needs a value it doesn't have (a shadow side, a lighter top), `paints --add <part id>` (step 3)
  and give the new paint its own pass.
- A pass shows where its paint is. If `build-steps` says a pass "changes almost nothing", that paint covers
  little of the part: fold it into the pass before it, or make the part's last step the one with the widest paint.
- Texture is never one step: a base coat, then a pass per paint. `check` fails a step that turns more than 10% of
  the picture from flat to textured; the fix is one more pass, not a different stroke.
- A parent's steps cover its children's places until the child's own step. So the order inside a stage is free:
  body coat, wing coat, cap, cheek, then the chest pass.
- When the stroke's card names brushes, the step's brush is one of those kinds; when it names none, choose by the
  area. Sizes follow the canvas (step 0): the biggest brush for the biggest areas, a liner only for lines.
- Paint order inside the picture follows the technique: back to front, and what's nearest last. Something painted
  on a part (paths on a field) comes after that part's base coat, never before it on bare canvas.
- The step's `name` is a short instruction: "Dab the rust foliage", not "Foliage".
- Aim for the technique's `v2_step_range` and `v2_stage_range`. More small steps beat fewer big ones, up to the
  top of the range.
- **No card fits a stroke you need:** use the closest card, say in that step's tip how this stroke differs, and
  list the missing stroke in `notes.json` (`learned`) and in your report so the owner can add a card. Don't use a
  stroke with no card, and don't write a card yourself during a run.

`build-steps` (step 5) and `check` (step 7) will tell you what's wrong with the plan. Write the steps a teacher
would, then let the tools argue.
