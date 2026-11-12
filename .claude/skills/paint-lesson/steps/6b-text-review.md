# Step 6b: text review in a fresh context

A fresh reviewer checks your text against measured before-and-after pictures, because you wrote it and miss what
you take for granted.

1. `publish --lesson <lesson>` (a draft). Deal with `long_steps` and `long_instructions` first (step 6), publish
   again, then run `step-pairs --lesson <lesson>`.
2. Start a subagent (Agent tool, general-purpose) with only this: follow
   `.claude/skills/paint-lesson/step-review.md` for the lesson folder, use only `trials/review/packet.json` and its
   sheets, write `trials/review/review.json`, and use the project's `.venv` Python if it needs to crop or zoom.
   Don't pass it your reasoning or the plan.
3. Route each problem by its `kind`, not by the verdict:
   - `flat`, `missing`, `vague`, `wrong_result`, `layering`: fix the text in `text.json` from the reviewer's `fix`.
     Check each against the sheet first; skip one whose evidence doesn't hold up, and say why.
   - `shape_change` on the main subject: fix the pictures now, free first:
     - the finish disagrees with the steps before it: `finish-from-step --add "<only what the last step adds>"`;
     - an earlier step disagrees with a later one that's right: `carry-forward --from <later> --to <earlier> --box
       ...` copies the later step's subject onto it;
     - rendering the earlier step again rarely works.
     Then `mix`, `lock-steps`, `publish`, `step-pairs`, and look at the subject across all its steps.
   - `shape_change` on a path, row, horizon, or branch, or a `split_edge`: the pictures are wrong. Fix them within
     the caps: redo the later step with `render-step --fix` so it keeps the earlier shape (or re-plan a split
     texture as passes), then lock again. If the caps stop you, record it as `left`.
   - `drift`: leave the text alone and record it.
   - `too_much`: a texture arriving all at once is fixed with `split-texture` (step 6a). Otherwise record the
     reviewer's proposed split.
   - `unpaintable`: record it as `left`.
   - a `diagram` proposal goes to step 7 as a candidate.
4. **Check the reviewer's `ok` steps too.** For every step whose main shapes come back in later steps (a branch,
   a trunk, a hull, a subject), compare its picture with the finish yourself: thickness, bends, and where it
   joins. The reviewer only compares neighbors, so a step that's wrong against the finish in the same way as its
   neighbor slips through.
5. One review round. Save what happened in the lesson's `review.json` under `text_issues`:
   `{"step_id", "kind", "problem", "fix", "action": "fixed | left: <why> | skipped: <why> | diagram"}`.
