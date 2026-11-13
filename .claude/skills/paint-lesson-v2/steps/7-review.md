# Step 7: check, and the text review in a fresh context

## 7a. Check
`check --lesson <lesson>`. Fix every item in `problems` the way it says, at the skill step it belongs to, then run
the tools after that point again in order (SKILL.md rule 9). **Collect every problem first and fix them in one
pass**: each trip back through the tools costs minutes. The usual ones:

| It says | Fix |
|---|---|
| a `full` step turns too much of the picture from bare to textured | that part is finished in one step. Make it a `flat` coat and a pass per paint (`paints --add <its part>` if it has only one), then 5a on |
| more base mixes than the target and two are close enough to merge | run `paints --lesson <lesson>` again; never delete a paint by hand |
| step or stage count out of range | step 4: split the biggest steps, or merge stages |
| a stroke has no card, or the brush isn't one its card names | step 4: use a card's stroke and one of its brushes |
| a paint can't be mixed from these tubes | step 6b: a `paint_notes` line on a step that uses it |
| a line has a percentage, or is over 40 words | step 6: reword it; split a long line |
| a step has no summary or tip | step 6b |
| the drafted lines are out of date | `draft-text` again |

`notes` are things to know, not failures.

## 7b. Text review in a fresh context
You wrote the text, so you'll miss what you take for granted.
1. `publish --lesson <lesson>` (a draft), then `step-pairs --lesson <lesson>`.
2. Start a subagent (Agent tool, general-purpose) with only this: follow
   `.claude/skills/paint-lesson/step-review.md` for the lesson folder (it has a note for version 2 lessons), use
   only `trials/review/packet.json` and its sheets, write `trials/review/review.json`, and use the project's
   `.venv` Python if it needs to crop or zoom. Don't pass it your reasoning or the plan.
   **If you have no Agent tool,** do the review yourself, last, as strictly as you can: Read `step-review.md`
   fresh, then **every** sheet (not a sample), and write `trials/review/review.json` as it says. Then put
   `"review_context": "same"` at the top level of `<lesson>/review.json` (step 4 below), so the lesson page says
   the review wasn't a fresh one.
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
