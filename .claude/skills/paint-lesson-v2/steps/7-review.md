# Step 7: check, and the text review in a fresh context

## 7a. Check
`check --lesson <lesson>`. Fix every item in `problems` the way it says, at the step it belongs to, and run the
tools after that step again in order (`outline`, `paints`, `build-steps`, `step-aids`, `mix`, `draft-text`,
`check`). The usual ones:

| It says | Fix |
|---|---|
| a step turns too much from flat to textured | step 4: split that pass into two (darker paint first), then 5a on |
| step or stage count out of range | step 4: split the biggest steps, or merge stages |
| a stroke has no card, or the brush isn't one its card names | step 4: use a card's stroke and one of its brushes |
| a paint can't be mixed from these tubes | step 6b: a `paint_notes` line on a step that uses it |
| a line has a percentage, or is over 40 words | step 6: reword it; split a long line |
| a step has no summary or tip | step 6b |
| the drafted lines are out of date | `draft-text` again |

`check_notes` are things to know, not failures.

## 7b. Text review in a fresh context
You wrote the text, so you'll miss what you take for granted.
1. `publish --lesson <lesson>` (a draft), then `step-pairs --lesson <lesson>`.
2. Start a subagent (Agent tool, general-purpose) with only this: follow
   `.claude/skills/paint-lesson/step-review.md` for the lesson folder (it has a note for version 2 lessons), use
   only `trials/review/packet.json` and its sheets, write `trials/review/review.json`, and use the project's
   `.venv` Python if it needs to crop or zoom. Don't pass it your reasoning or the plan.
3. Route each problem by its `kind`:
   - `missing`, `vague`, `wrong_result`, `flat`, `layering`: check it against the sheet. If it holds, fix the tip
     or the line in `text.json` (mark an edited line `"edited": true`). If the fix is really "this is two steps",
     split the step in the plan and rebuild.
   - `too_much`: split the step in the plan (step 4), rebuild (5a on). Splitting is free; never just record it.
   - `unpaintable`: the finished painting has more detail there than a beginner can make. Record it as `left`.
   - a `diagram` proposal goes to step 8 as a candidate.
4. One review round. Write `<lesson>/review.json`:
   ```json
   {"finish_issues": ["from step 1's finish check, or an empty list"],
    "text_issues": [{"step_id": "...", "kind": "...", "problem": "...", "fix": "...",
                     "action": "fixed | split | left: <why> | skipped: <why> | diagram"}]}
   ```
   Every `left` shows on the lesson page under Known problems.
5. `check` again. It must be clean before step 8.
