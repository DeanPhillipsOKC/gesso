# The run after steps 0 and 1 (`/paint-lesson <photo>`)

This is the pipeline (version 3; its gate passed on 2026-11-18, `docs/decisions.md`), with v3.1's changes
(`docs/design/pipeline-v3.1.md`): one writer for the lesson's words, a plan's writer that picks its library files
and answers with changes, and a finisher sent smaller pictures. SKILL.md's steps 0 and 1 come first, then this file.

A version 3 lesson is planned first, by a painter's eye, and the pictures are made to fit the plan: the finished
painting is erased backward by the image model, one piece of the plan at a time, and every step picture comes from
that chain. No outlines are drawn. You run the tools and start the helpers; you write none of the plan, the
requests or the step words yourself.

SKILL.md's rules for the whole run stand. Rule 9's order is this file's: after any change to `plan.json`,
`plan-check`, `erase`, `build-steps`, `step-aids`, `mix`, `draft-text`, `check`, then the chain's checker and its
redos, then `packets`, the lesson's writer and its rounds (`check-text`), its arc, and `check` again. A chain request that didn't change costs
nothing the second time.

**Lessons are made on Opus** (`docs/decisions.md`, 2026-11-17). Every helper below (the plan's writer, the chain's
checker, the lesson's writer) is a subagent on Opus in a fresh context, given only what its step names. **Run this
from the session the owner started, not from inside a subagent:** a subagent can't start the helpers (the first
real run stopped at step A for that, #219). If you aren't an Opus model, you still run the tools and start the
helpers yourself, and hand what takes a painter's judgment to one more Opus subagent: steps 0 and 1 before the
plan, and E2 (diagrams, notes, the seal) at the end, with what happened in between written out for it.

## Steps

| Step | Makes |
|---|---|
| 0, 1 | as `steps/0-setup.md` and `steps/1-reference-finish.md`: the lesson folder, the canvas, the finish |
| A. The painter's plan | `plan.json` (`"plan_version": 3`) |
| B. The chain | `chain/` |
| C. Step pictures, teaching pictures, recipes, drafted lines, the first check, the chain's checker | `NN_<id>.png`, `aids/`, `mixes.json`, `text.json`, `chain/looks/answers.json` |
| D. The words | `words/`, `text.json` |
| E. Check, diagrams, notes, seal, report | the sealed lesson |

### A. The painter's plan

1. Start one writer with: "Follow `.claude/skills/paint-lesson/v3/plan-brief.md`. Lesson folder: `<lesson>`. Photo:
   `<the photo's path, as step 0 left it>`. Technique: `techniques/acrylic-paint-along-beginner.yaml`." Add the
   palette's name when the painter uses their own tubes. With `--kit`, add: "Kit lesson: yes." Don't pass it your read of the picture.
   The writer reads the library's list (`library`), asks once for the files it picks (`library --picks`, into
   `<lesson>/library/`), and reads only those.
2. When it replies, run `plan-check --lesson <lesson>` yourself. `problems` must be empty. If it isn't, send the
   list back to the same writer once: "Fix these with a changes file and `plan-change`, as your brief says:" and the
   list. It answers with only what changes, never the plan again. If it still isn't empty, fix what is left
   yourself the same way: a changes file and `plan-change --lesson <lesson> --changes <file>`, which prints
   `plan-check`'s output.
   With `--kit`, what `plan-check` printed must also hold `kit` (the brushes and the count of paints). If it
   doesn't, the plan isn't a kit lesson: send the writer "Put `\"kit\": true` at the top of the plan, with a changes
   file and `plan-change`, and fit the plan to the kit's limits." and run `plan-check` again. Check this again after
   every later change to the plan (C3).
3. Read `units` and `renders` in what `plan-check` printed: that is the chain's size.

### B. The chain

1. **Say the size before you spend it.** One line to whoever started you: how many renders, about how many cents
   (2 a render) and minutes (a quarter of a minute a render). Go on without waiting, unless `renders` is over 20:
   then stop and ask.
2. `erase --lesson <lesson>`. It renders every unit, last first, and asks again by itself for a thing a render
   left standing. If it stops on a network error, run it again the same way, **without `--redo`**: what is already
   rendered costs nothing. If it is refused at its cost cap, don't run it again: the cap is twice the chain. A
   refused run leaves the chain before it as it was. So when `chain/chain.json` exists, go on with that chain and
   its `answers.json`, and record each unit whose redo didn't run (D5). When there is no `chain/chain.json`, stop
   and tell whoever started you what was spent and why.

Don't Read the renders yourself to second-guess the chain's checker (C4), and never edit a file in `chain/`.

### C. Pictures, recipes, drafted lines, the first check, the chain's checker

1. `build-steps --lesson <lesson>`. It builds pipeline v4's pictures (POC 2.2.0; `docs/design/pipeline-v4.md`): a
   layer a later stage covers from the bottom edge stops at a loose line about 1 in past the cover, and the canvas
   below stays bare until the cover is painted. Pass `--no-stops` only when whoever started you asks for the old
   pictures (the bench does); `v3/build.json`'s `stops` says where each layer stops, and every later tool reads that, so no
   other tool takes the flag. Run it the same way every time in a run: words written for pictures built the other
   way are refused by `check-text` and `check` until `packets` and the writer run again (D). `problems` must be
   empty (it only isn't when the chain's files don't belong together: run `erase` again). `notes` are faults that would need a new plan and a new chain: a paint fitted far
   from its name, a color the finish doesn't have, a step that changes almost nothing. Change nothing for them (a
   paint's name is in the chain's requests, so even a rename renders part of the chain again): record each (D5).
2. `step-aids`, then `mix`, then `draft-text`, each with `--lesson <lesson>`.
3. **`check --lesson <lesson>` now, before the chain's checker and before any words are written.** Act now only on
   a problem that changes `plan.json`, such as two paints fitted to the same color that it asks you to merge: send
   that problem alone to the plan's writer (A1's, if you can still reach it, else a new one with the same brief):
   "Make only this change, with a changes file and `plan-change`:" and the problem. Then run forward from
   `plan-check` (rule 9). A merge that leaves the chain's requests as they were renders
   nothing. Leave the rest of what `check` prints (the words, `review.json`, the seal's asks) for E1. Why: in the
   gate runs a merge asked for after the words threw away every stage writer's work, and one asked for after the
   chain's checker threw away its answers (#230 to #234).
4. Start one checker with: "Follow `.claude/skills/paint-lesson/v3/chain-check.md`. Folder:
   `<lesson>/chain/looks`." It writes `answers.json` there.
5. For every unit it marked, in **one** run: `erase --lesson <lesson> --redo <unit>:stray,<unit>:left`
   (the unit's number is the digits of its `look`; `left` when it answered left, else `stray`). Every unit before
   a redone one is rendered again. Then the checker again, on the new looks.
6. At most two rounds of step 5. `erase` refuses a unit that has had two more tries. What is still marked after
   that, and everything `erase` lists under `left`, stays: write each into `review.json` as step D5 says.
7. After any redo, run C1 to C3 again (`build-steps`, with `--no-stops` if C1 had it, `step-aids`, `mix`,
   `draft-text`, `check`) before D.

### D. The words

One writer writes the whole lesson, in one conversation: the steps' words, two rounds of fixes, then the arc. Every
round goes back to **that same writer** (send it a message; don't start a new one), so it reads what it already read
from its own context.

1. `packets --lesson <lesson>`. It writes the writer's folder, `words/lesson/`, and records in it what the step
   pictures were made from (`pictures.json`), so words written for other pictures can't be sealed.
2. Start **one writer** with: "Follow `brief.md` in `<lesson>/words/lesson`. Read only that folder. Write `out.json`
   there. Name only the paints each step lists for itself, and keep every line under 40 words." (`brief.md` says
   both too; saying them up front saved a round in the gate runs.)
3. `check-text --lesson <lesson>`. While it prints a `send_back` file, send the writer: "Read `feedback.md` in your
   folder and write `<send_back>`." and run `check-text --lesson <lesson>` again. There are two rounds at most
   (check-text's failures, then paints a step doesn't list and lines over 40 words); a round with nothing to send
   is passed by. When it prints `"done": true`, run `check-text --lesson <lesson> --final`, which takes out every
   sentence that still fails. If `problems` names an unusable `out.json` or a step with no words, send the writer
   back once with the problem; if the writer is lost, start a new one from D2 (a new `out.json` starts the rounds
   again).
4. **The arc**, as the same writer's next message: "Follow `arc-brief.md` in your folder and write `arc.json`." Then
   `check-text --lesson <lesson> --arc`. If it prints a `send_back`, send the writer: "Read `arc-feedback.md` in your
   folder and write `arc-fix.json`." Then `check-text --lesson <lesson> --arc --final`, which takes out what still
   fails and writes the opening, the stages' lines and the back lines into `text.json`. After any later
   `check-text --final`, run `check-text --arc --final` again (the arc is laid on the final words).
5. Write `<lesson>/review.json`:
   ```json
   {"finish_issues": ["from step 1's finish check, or an empty list"],
    "text_issues": [{"step_id": "<the step it shows on>", "kind": "chain | paint | step | words",
                     "problem": "what a painter will see", "action": "left: <why it stays>"}]}
   ```
   One entry for each: a unit the checker still marks or `erase` lists under `left` (on that unit's first step);
   a `notes` line of `build-steps` or `check` you left; each line `check-text --final` lists under `emptied` (every
   sentence of it was taken out, so the page leaves it off). Every `left` shows on the page under Known problems.

### E. Check, diagrams, notes, seal, report

1. `check --lesson <lesson>` again. Fix each problem as it says and run the tools after that point again (rule 9).
   A line it finds over 40 words goes back to the lesson's writer: "Shorten these lines to under 40 words and write
   `fix-3.json` with only the steps you change." Then `check-text`, `check-text --final` and
   `check-text --arc --final` again.
2. `steps/8-finish.md` from 8a: diagrams, notes (`steps/notes.md`; `merged_parts` is `{}`, and every helper you
   started goes in `learned` with what it was given), then `publish --lesson <lesson> --final`. Look at the step
   pictures `small-pictures` makes (384 pixels, the finish at 512), and at the diagrams again only when
   `preview-diagrams` draws fewer than were written.
3. Put the sealed lesson on the lessons site as `steps/8-finish.md` 8c says (owner, 2026-11-18: a version 3
   lesson goes on the site like any other).
4. Report as 8d says, and add: the units and renders; what the chain cost and how many renders were asked again
   and why; what the checker marked each round; the mixes count against 10; what each of the words' rounds sent back
   (`words/lesson/rounds.json`) and how many sentences `check-text` took out; every Known problem.
