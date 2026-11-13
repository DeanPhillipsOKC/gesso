---
name: paint-lesson-v2
description: Turns a photo into a step-by-step beginner acrylic painting lesson with pipeline v2. The finished painting is rendered once, and every step picture, close-up, and paint map is cut from it by free tools; Claude plans the parts and steps and writes what only this photo needs. Use when the owner runs /paint-lesson-v2 <photo>, or asks for a v2 lesson from a photo.
---

# paint-lesson-v2

You are the lesson pipeline. You look, plan, and write; `spike/tools.py` measures and draws. The finished painting
is rendered once and every step is cut from it, so step pictures can't drift and a step can be as small as a
beginner needs. The lesson has to stand on its own: once you seal it, nobody fixes it by hand.

The design behind this is `docs/design/pipeline-v2.md`. You don't need to read it to run the skill.

**How this skill is laid out.** This file is the spine. Each step's detail is in `steps/`. **Read a step's file when
you start that step**, even if you read it earlier. Don't read ahead.

## Arguments
- `<photo>` (required)
- `--canvas WxH` (optional, inches, e.g. `11x14`) with `--orientation portrait|landscape`
- `--technique <file>` (optional): force the whole-painting approach (a file in `techniques/` with version 2 keys:
  `v2_step_range`, `v2_rules`). Without it, choose the approach that fits the picture and the level and say why in
  `technique_why`. Today only `acrylic-paint-along-beginner.yaml` has version 2 keys.
- `--palette <name>` (optional): the painter's own tubes from `palettes/<name>.yaml`. Put `"palette": "<name>"` in
  plan.json.

Run every tool with the venv: `PY=.venv/Scripts/python.exe` (Windows) or `.venv/bin/python`.

## Rules for the whole run
1. **Renders:** the finished painting, and only when needed the beginner version, the canvas extend, and one
   background picture. No step is ever rendered. Pass `--max-cost 0.40` to every render.
2. **Measure, don't guess.** Boxes and points come from `grid --percent` on the finish. Colors come from
   `part-colors`.
3. **Every tool prints `problems`.** An empty list means go on. Otherwise each one says what to change: change it
   and run the tool again. The tools are free and take seconds, so loop until they're clean. Never edit a tool's
   output file by hand to make a problem go away.
4. **Technique comes from the technique file, the research file, the element techniques, and the cards**
   (`techniques/elements/`, `techniques/strokes/`, `techniques/basics/`), not from memory. Every part follows an
   element technique; when none fits, you draft one in the lesson folder and file it for the owner (step 2b).
   When you rely on something they don't cover, say so in `notes.json` under `learned`.
5. **One move per step.** One brush, one stroke, one to three paints. If a step needs "then", it's two steps.
6. **Don't flip a card's or an element's `checked`.** The owner does that after painting from it.
7. **Keep `notes.json` as you go,** not at the end.
8. **Stay in your lesson folder.** Don't edit code, skills, techniques, elements, cards, palettes, or docs during a
   run (a drafted element goes in `<lesson>/elements/`). If
   a tool is wrong, work within what the skill allows and report it. Scratch files and scripts go in
   `<lesson>/trials/`, nowhere else, and never keep the lesson's path in a shared file: other runs share the
   machine.
9. **The order is fixed, and going back means running forward again.** After any change to `parts`: `outline`,
   `paints`, `build-steps`, `step-aids`, `mix`, `draft-text`, `check`, in that order. After a change to `stages`
   only: from `build-steps` on. Don't skip one because it ran before.
10. **Seal last.** Your last command is `publish --lesson <lesson> --final`. It refuses until `check` is clean.
   After the seal, change nothing.

## Steps

| Step | File | Makes |
|---|---|---|
| 0. Set up, check the photo, fit the canvas, beginner version | `../paint-lesson/steps/0-setup.md` | lesson folder, `00_*.png` |
| 1. Reference and finished painting | `../paint-lesson/steps/1-reference-finish.md` | `00_reference.png`, `99_finish.png` |
| 2. Parts, their element techniques, and outlines | `steps/2-parts.md` | `plan.json` (parts), `parts/`, `elements/` when one is drafted |
| 3. Paints | `steps/3-paints.md` | `plan.json` (paints) |
| 4. Stages and steps | `steps/4-stages.md` | `plan.json` (stages) |
| 5. Step pictures and teaching pictures | `steps/5-pictures.md` | `NN_<id>.png`, `aids/` |
| 6. Text | `steps/6-text.md` | `text.json` |
| 7. Check, and the text review in a fresh context | `steps/7-review.md` | `review.json` |
| 8. Diagrams, notes, seal, report | `steps/8-finish.md` | the sealed lesson |

Steps 0 and 1 are the v1 skill's files, with these differences:
- every filter run with `--lesson` needs `--why "<what you want it to show you>"`;
- `notes.json`'s `beginner_version` is a dict: `{"made": true|false, "found": "...", "list": "...", "why": "..."}`;
- with `--palette`, name the painter's tube colors in the finish prompt in place of the technique's five;
- the finish is rendered at `--quality high` (it's the one picture everything is cut from);
- the lesson folder is `output/<photo stem>_skill_<YYYYMMDD-HHMMSS>/` as there (the history and the site find
  runs by that name);
- ignore anything they say about a tool order, `render-step`, regions, or `plan_lesson`;
- pass `--max-cost 0.40` to their renders.
