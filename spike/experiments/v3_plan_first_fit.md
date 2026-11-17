# Brief: fit the layers to the painter's plan (spike S7, #172)

A painter's plan for one picture was written before anything was outlined (`painter.json` in your lesson folder: the
things, the stages, and what each step lays down, sometimes on several things at once). Your job is to make the lesson
that plan describes, with the `/paint-lesson` skill's own tools. **The plan leads.** You don't reorder, merge, split
or reword the painter's steps to suit the parts; you change the parts, paints and passes to suit the plan.

You were given a lesson folder. Call it `$L`. Stay inside it: don't edit code, skills, techniques, elements, cards or
docs, don't commit, don't seal, and don't read other runs or `docs/spikes/`.

## What's in the folder

- The skill's steps 0 and 1, frozen (`bench.json` says what): photo, canvas, reference, `99_finish.png`. Never render
  these again.
- `painter.json`: the plan you carry out.
- `plan.json` with no `stages`, and as material: `parts` (with their outlines in `parts/`), `paints` (measured from
  the finish, already named) and `98_background.png` (what's behind the things in front). They come from an earlier
  lesson cut from this same finish, made part by part. They're a start, not a constraint.

## The tools

Run everything from the repo root, with `export GESSO_HISTORY=spike/experiments/bench/runs/history` and
`PY=.venv/bin/python`. The skill's step files say how each tool works; read a step's file when you get to it:
`.claude/skills/paint-lesson/steps/2-parts.md` (2c only), `3-paints.md`, `4-stages.md`, `5-pictures.md`,
`6-text.md` (6a, 6b and 6d only). Where this brief and a step file disagree, this brief wins.

- `outline` uses a lot of memory and other runs share the machine. Always run it as
  `flock /tmp/gesso-outline.lock $PY spike/tools.py outline --lesson $L`. At most 4 runs of it in all.
- Use `$PY spike/experiments/v3_plan_first.py check $L` wherever the skill says `check`. It runs the same checks and
  adds the ones below.
- Don't run `background` unless you add or remove a thing in front of the background (an `object`, a `thin` part, or
  `marks` listed after the first object) and `build-steps` then shows a ghost. `--max-cost 0.40`, once.
- Skip: `card-adapt` and step 6c, diagrams, notes, the seal, `publish --final`.

## How the painter's plan becomes a plan.json

A version 2 step paints inside one part. So a painter's step that lays paint on k parts becomes k v2 steps in a row.

1. **Parts.** Give every part `"thing": "<the painter's thing id it belongs to>"`. A thing can have several parts
   (the cat and its white chest); every thing needs at least one. Where the painter's plan lays paint on something
   the parts can't show yet:
   - one more color on a part (a nose on a face, a shadow under a thing): `paints --add <part>` and a pass. Try this
     first, it costs nothing;
   - a thing with its own edge and its own steps: a new part (skill step 2a's table), then `outline`, then `paints`.
   A part the painter's plan has no use for can be dropped: the part behind it carries its paint.
2. **Stages.** `plan.json`'s stages are the painter's stages: same ids, same names, same order.
3. **Steps.** For each painter's step, in the painter's order, one v2 step per part it lays paint on:
   ```json
   {"id": "shadows-cat", "of": "cast-shadows", "name": "Shade under the cat", "part": "cat", "show": "pass",
    "paints": ["cat-1"], "stroke": "glazing", "brush": "1/2 inch flat"}
   ```
   - `of` is the painter's step id. The v2 steps of one painter's step sit together, and share its stroke and brush
     (it is one move).
   - `show` follows the skill's step 4 table. For each part, its v2 steps in order must still follow the part's
     element technique (`$PY spike/tools.py elements --lesson $L` shows the fit).
   - `paints`: the measured paints of that part that match what the painter's step names. To use a paint on a part it
     wasn't measured in, add the part to that paint's `parts`. Rename a paint to the painter's name for it when it's
     the same color; the painter's `looks` says what was meant.
   - **A part's last v2 step shows everything of the part that's left.** So the painter's step that finishes a thing
     must be the last v2 step on each of its parts. If that step's words add only a small light and the picture would
     jump (a flat cat becomes a finished cat), the part needs a pass earlier, in the painter's step that lays that
     paint: find which painter's step names it, give that step's v2 step the right paint (`paints --add`), and let the
     picture catch up there. Never add a painter's step.
4. **When the layers can't show what the painter wrote,** do the nearest thing and say so in `plan.json`, each with
   one line of why:
   - `"painter_dropped": {"<painter step id>": "why no v2 step can show it"}`;
   - `"lays_dropped": {"<painter step id>": "which thing it doesn't paint here, and why"}`;
   - `"things_dropped": {"<thing id>": "why it has no part, and which part carries it"}`.
   These are counted as the fit's failures to follow the plan. Use them only after trying a pass and a part.

## The run

1. Read `painter.json`, `99_finish.png`, `parts/preview.jpg` (the parts' outlines on the finish), and `plan.json`'s
   parts and paints.
2. Write the parts' `thing`, any new parts, and the stages. If you changed `parts`: `outline`, then `paints`.
3. `build-steps`, and Read `trials/steps.jpg`. Each painter's step should add what its `lays` and `after` say and
   nothing else. Fix the plan, not the painter's plan. `step-aids`, `mix`.
4. `draft-text`. Then text, as the skill's 6b and 6d say, with these changes:
   - Write `summary` and `tip` **once per painter's step, on its first v2 step**, for the whole painter's step: all
     the things it paints. Leave them empty on its other v2 steps. For a step that crosses things, the tip says the
     order to go round them and what stays the same (the brush, the mix).
   - The painter's `after` and `what` are your source for what the step is for. The words must match the picture you
     built: read it.
   - **No step numbers** in a summary or tip (yours would be v2 numbers). Name the paint or the thing instead.
   - A drafted "Let ... dry" line that names a thing painted in the same painter's step: set its text to `""` with
     `"edited": true`.
5. `v3_plan_first.py check $L` until `problems` is empty. Collect every problem and fix them in one pass.
6. `$PY spike/tools.py publish --lesson $L` (a draft, no `--final`), then
   `$PY spike/experiments/v3_plan_first.py fold $L`. It writes `$L-folded/`: the lesson in the painter's steps.
7. **One review pass, as a beginner.** Read `$L-folded/lesson.json` step by step with its picture
   (`$L-folded/canvas/NN_<id>.png`) and the one before it. For each step ask: could I paint this from the words?
   Does the picture show anything the words and paints don't cover? Fix the tip or an edited line in `text.json` (or
   the plan, when the picture is wrong), then run the tools forward again from what you changed, `check`, `publish`,
   `fold`. One round.

## Report

Reply with: the folded folder; the painter's steps, v2 steps and how many cross things; every part you added, changed
or dropped and why; everything under `painter_dropped`, `lays_dropped` and `things_dropped`; what `check` still
lists, if anything; what's still wrong in the folded lesson that you could not fix; any tool that misbehaved; and how
many times you ran `outline` and `background`.
