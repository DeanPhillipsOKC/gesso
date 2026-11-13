# Step 5: step pictures and teaching pictures

## 5a. Step pictures
`build-steps --lesson <lesson>`. No renders. **Read `trials/steps.jpg`**: every step should add one thing, and
nothing else should change.

- `problems` not empty: fix the plan as each says and run it again.
- **A step "changes almost nothing":** its paints aren't the part's colors there, or an earlier step already
  showed it. Merge it into its neighbor, or give it the right paint.
- **A step adds too much at once** (a flat shape becomes finished in one step): give the part another paint from
  `paints` and another pass.
- **Something looks wrong in an outline** (a part painted where it isn't, or a faint trace of an object before
  its own step): go back to step 2b, then `paints`, then here.

## 5b. The background picture, only when asked
If `build-steps` printed `"needs_background": true` (it does whenever there are objects in front of the
background), what's behind them needs one render, or a blurred ghost of each object shows in every step before
it's painted:
`background --lesson <lesson> --max-cost 0.40`, then `build-steps` again, and Read the sheet: no trace of the
objects before their own steps.
- `problems` from `background` (it changed the scene, or left the objects in): `background --lesson <lesson>
  --redo --max-cost 0.40` once. If that fails too, delete `98_background.png`, run `build-steps` again, and record
  it in `review.json` as `{"step_id": "<first step>", "problem": "what's behind the objects is a rough fill until
  they're painted", "action": "left: the background render failed twice"}` under `text_issues`.
- If a trace still shows after a clean background render, it's an outline that's too tight (step 2b's table),
  not the render.
- Don't run it when `needs_background` is false: there's nothing in front to take out.

## 5c. Teaching pictures
`step-aids --lesson <lesson>`. It makes, for every step, the outline of where it paints, a close-up when the area
is small, a paint map, the position in words, and one transfer outline for the lesson. Nothing to write here.
Run it again after any `build-steps`.

## 5d. Recipes
`mix --lesson <lesson>`. It computes every paint's recipe from the palette tubes. For a paint it lists as
unreachable, you'll add a `paint_notes` line in step 6 ("as close as these tubes get").
