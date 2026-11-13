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
  its own step): go back to step 2c, then `paints`, then here.
- **A part "already shows ... before it's painted"** (in `problems`), or `advice` lists parts to look for: find the
  step on the sheet and the part in `parts/preview.jpg`. If the outline misses some of the part (a foot's toes left
  to the branch, a cloud outside the clouds' boxes), fix it in step 2c: what an outline leaves out is painted with
  the part behind. A part painted on another that shows in its parent's block-in coat is fine. If a part with no
  parent still shows after 2 rounds, drop it and paint it as a pass of the part behind, as step 2c says.

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
- If a trace still shows after a clean background render, it's an outline that's too tight (step 2c's table),
  not the render.
- Don't run it when `needs_background` is false: there's nothing in front to take out.

## 5c. Teaching pictures
`step-aids --lesson <lesson>`. It makes, for every step, the outline of where it paints, a close-up when the area
is small, a paint map, the position in words, and one transfer outline for the lesson. Nothing to write here.
Run it again after any `build-steps`.

## 5d. Recipes
`mix --lesson <lesson>`. It computes every paint's recipe from the palette tubes. For a paint it lists as
unreachable, you'll add a `paint_notes` line in step 6 ("as close as these tubes get").
