---
name: paint-lesson
description: Turns a photo into a step-by-step beginner acrylic painting lesson (Gesso #10). Claude Code plans the lesson, picks a tool for each step (free filters first, paid gpt-image renders only when no filter can do it), reviews every step in a fresh subagent, and writes lesson.html. Use when the owner runs /paint-lesson <photo> [technique] [quality], or asks for a lesson from a photo.
---

# paint-lesson

You are the lesson pipeline. You plan, check, and write yourself (no Anthropic API calls), and call
`spike/tools.py` for images. Filters are free; renders cost money, so they come last. The lesson has to stand on
its own: once you seal it, nobody fixes it by hand.

**How this skill is laid out.** This file is the spine: the arguments, the rules that hold the whole way through,
and the steps in order. Each step's detail is in `steps/`. **Read a step's file when you start that step**, even if
you read it earlier, so its rules are fresh when you use them. Don't read ahead.

## Arguments
- `<photo>` (required, e.g. `photos/blog/chickadee.png`)
- technique (optional; otherwise you choose one, step 0)
- quality for steps (default `low`)
- `--canvas WxH` (optional, inches, e.g. `11x14`) with `--orientation portrait|landscape` (optional; by default it
  follows the picture)
- `--palette <name>` (optional): the painter's own tubes from `palettes/<name>.yaml` (the owner's is `owner`). Put
  `"palette": "<name>"` in plan.json, and name the painter's colors in every render prompt that names the
  technique's five tubes.

Run every tool with the venv: `PY=.venv/Scripts/python.exe` (Windows) or `.venv/bin/python`. Read
`$PY spike/tools.py --help` at the start; tools get added over time.

## Rules for the whole run
1. **Tool order for every image:** a filter, then a composite, then a throwaway filter script (2 tries), then a
   render seeded by one of those, then a plain render with `--why-not-filter`. Write down which and why. Details:
   `steps/tools.md`, read it now.
2. **Caps:** renders are capped per lesson (`--max-cost`, default $1.00) and per step (`--max-redos`, default 2:
   one render plus two redos, so three paid renders). A refusal means stop rendering that step and record it as
   `left`. Never work around a cap.
3. **Measure, don't guess.** Positions and edges come from `grid --percent` ("44% across, 40% down").
4. **Technique comes from the technique YAML and `docs/research/acrylic-paint-along.md`, not from memory.** When
   you rely on something they don't cover, say so in `notes.json` under `learned`.
5. **No texture arrives all at once.** Dense texture goes on in passes (base coat, then dark, mid, light marks).
6. **Lines laid in early keep their shape** (paths, rows, horizons), and **the main subject keeps its outline,
   size, posture, and markings** from the step that paints it to the finish.
7. **Record every problem you leave** as `"action": "left: <why>"` in `review.json`. Those show on the lesson
   page under Known problems. Name the lesson folder in anything you report as a bug.
8. **Keep `notes.json` as you go,** not at the end.
9. **Stay in your lesson folder.** Don't edit code, the skill, techniques, palettes, or docs during a run. If a
   tool is wrong, work within what the skill allows and report it.
10. **Seal last.** Your last command is `publish --lesson <lesson> --final`. It refuses to seal until the checks
    pass; fix what it lists. After the seal, change nothing: any change marks the lesson edited.

## Steps
Read each file when you start the step.

| Step | File | Makes |
|---|---|---|
| 0. Set up, check the photo, fit the canvas, beginner version | `steps/0-setup.md` | lesson folder, `00_canvas_fit.png`, `00_beginner.png` |
| 1-2. Reference and finished painting | `steps/1-reference-finish.md` | `00_reference.png`, `99_finish.png` |
| 3. Plan | `steps/3-plan.md` | `plan.json` |
| 4-5b. Render, review in a fresh context, lock | `steps/4-render-review-lock.md` | step images, `review.json` |
| 6-6a. Write the steps, fix texture jumps | `steps/6-text.md` | `text.json` |
| 6b. Text review in a fresh context | `steps/6b-text-review.md` | `text_issues` in `review.json` |
| 7. Beginner check and diagrams | `steps/7-diagrams.md` | `construct` specs |
| 8. Notes | `steps/8-notes.md` | `notes.json` (complete) |
| 9. Seal, publish, report | `steps/9-publish.md` | the sealed lesson |

Why the rules are what they are (the runs that taught them): `docs/skill-history.md`. You don't need it to run
the skill.
