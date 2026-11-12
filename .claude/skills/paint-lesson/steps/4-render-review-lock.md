# Steps 4 to 5b: render, review in a fresh context, lock

## 4. Render the remaining steps
`render-step --lesson <lesson> --steps <ids...> --why-not-filter "<reason>" --quality <quality>` renders every
listed step at once, each from the finish. Leave out steps made with filters. A step with `"refused"` in the JSON
is recorded as `left`, not retried.

## 5. Review in a fresh context
Don't grade your own images. Start a subagent (Agent tool, general-purpose) with only:
- the step image paths in order (last is `99_finish.png`), and for each its id, what it adds (`paints`), and
  `looks_like`;
- this checklist. Each image is the canvas after that step: everything earlier stays in the same place and
  shape, plus only what this step adds. Flag only clear problems a painter following along would notice:
  - something appears before the step that paints it;
  - something painted earlier is missing, moved, or clearly a different shape or size (paths, rows, and
    horizons keep their shape to the end);
  - the image doesn't match `looks_like` (white canvas where it should be covered, or the reverse);
  - the main subject (an animal, a person, a boat, a balloon) changes outline, size, position, posture, or
    markings from the step that paints it to the finish: a shape problem, not small drift;
  - a step breaks the technique's painting order;
  - a step jumps from flat to dense texture (the fix is passes in the plan, not a redo). A split is by passes
    over the whole area, never by cutting one render into areas: a straight line across a texture, dabbed above
    and flat below, is a problem;
  - ignore small differences in brushwork, texture, and exact color. Never flag the last step for being the
    finish, but flag the step before it when the two disagree on the main subject;
  - when two neighbors disagree, compare both with the finish and flag the one that differs from it;
- ask it to Read every image (with the project's `.venv` Python if it needs to zoom) and answer with JSON only:
  `{"issues": [{"step_id", "problem", "fix"}]}`, `fix` phrased as an instruction for redrawing that image.

Check each issue yourself against the finish before redoing: if the flagged step matches the finish and its
neighbor doesn't, redo the neighbor and say so. Redo with `render-step --steps <id> --fix "<fix>"
--why-not-filter "<reason>"` (one step per call; several can run in parallel).

Two rounds: review, redo, review again in a new subagent, redo what that flags, stop. Save every issue in
`review.json`:

```json
{"finish_issues": ["..."],
 "review_issues": [{"step_id": "moon", "problem": "...", "fix": "...", "round": 2,
                    "action": "redone | redone neighbor <id> | left: <why>"}]}
```

`left` is for anything not redone (a cap, or not worth a redo). A mismatch you notice later (writing text,
diagrams, or after locking) goes in too, as `left` with `"round": 2`, and the step's words tell the painter what
to do about it. Every `left` shows on the lesson page under Known problems.

## 5b. Lock finished areas (`lock-steps`)
The image model doesn't hold earlier work still, so once renders and redos are done, lock them.
1. Check every step's `regions` against the images and correct them. Add `protect` boxes where a step's region
   overlaps things that must stay (a vine's box over the pumpkins). Inside a protect box only the step's own
   `colors` may change anything. Don't protect what the step changes on purpose, and keep them tight: one that
   covers the step's new marks can leave them see-through.
2. `lock-steps --lesson <lesson>`. Outside each step's regions, changes go back to the previous step's pixels.
   Then a backward pass from the finish: where no later step paints, a step already shows the finish. The raw
   renders stay in `trials/raw/`, so the lock can be rerun.
3. Read the locked images: no white holes, no seams where a box edge cuts an object (widen the box and rerun),
   nothing the step should paint removed, no new patches or specks the raw render didn't have. Record any lock
   artifact you can't fix as `left`.
4. Lock again after any later redo.
