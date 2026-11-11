---
name: paint-lesson
description: Turns a photo into a step-by-step beginner acrylic painting lesson (Gesso #10). Claude Code plans the lesson, picks a tool for each step (free filters first, paid gpt-image renders only when no filter can do it), reviews every step in a fresh subagent, and writes lesson.html. Use when the owner runs /paint-lesson <photo> [technique] [quality], or asks for a lesson from a photo.
---

# paint-lesson

You are the lesson pipeline. You do the planning, checking, and writing yourself (no Anthropic API calls), and
call `spike/tools.py` for images. Filters are free; renders cost money, so they come last
(`docs/decisions.md`, 2026-11-10). Read `docs/decisions.md` and the technique file before starting.

Arguments: `<photo>` (required, e.g. `photos/sleeping-cat.jpg`), technique (default
`techniques/acrylic-paint-along-beginner.yaml`), quality for steps (default `low`). Per-photo technique choice
(#12) isn't built yet: use the technique given.

Run every tool with the venv: `PY=.venv/Scripts/python.exe` (Windows) or `.venv/bin/python`. `$PY spike/tools.py --help`
lists every tool and what it's for; read it at the start, since filters get added over time.

## Tool order for every image

For each image the lesson needs, take the first of these that does the job, and write down which one and why:

1. **A filter** from `tools.py --help` (value study, notan, palette, simplify, posterize, edges, grid, ...).
2. **A composite** (masks of the finish, #8), once that tool exists.
3. **A throwaway filter** (#11): a one-off script in `<lesson>/filters/`, tried before renders, 2 tries at most.
   Until #11 adds filing filter requests, list each throwaway in the report to the owner. Example from the trees
   run: the first step (sky only) came from masking the dark trees in the finish, inpainting the holes, and
   blurring; it left a mark the review caught, and a render seeded by it fixed that for $0.018.
4. **A render seeded by a filter or composite** (pass its output as an input image).
5. **A plain render** (`render` or `render-step`), with `--why-not-filter` saying why 1 to 4 can't do it.

Renders are capped per lesson (`--max-cost`, default $1.00) and per step (`--max-redos`, default 2). A refusal
means stop rendering that step: flag it in the lesson for the owner, don't try to get around the cap. The same
render with the same inputs comes back free from the cache, so rerunning a lesson to change the text costs $0.

## Steps

### 0. Set up
- Lesson folder: `output/<photo stem>_skill_<YYYYMMDD-HHMMSS>/`. Pass it as `--lesson` to every tool.
- Read the technique YAML: `rules`, `brush_moves`, `palette`, `step_range`, `ground`, `framing`, `simplify`, `finish`.

### 1. Simplified reference (`00_reference.png`)
The reference is what the painting is made from: fewer shapes, clear values, colors a beginner can mix
(decisions: "Simplify the photo first").
- Try `simplify --strength 2` or `3` on the photo, then look at it. If small clutter is still there, try a
  higher strength or `--method meanshift`. Write the result to `<lesson>/00_reference.png` (`--out`).
- Also make, for the painter and for you: `value-study --tones 3`, `palette --colors 6` (their outputs go in the
  lesson folder with `--lesson`).
- Only if no filter result reads as a clean reference (for example the photo is too busy for any strength),
  render it with the technique's `simplify.prompt` (`render --step reference`, reason required).

### 2. Finished painting (`99_finish.png`)
No filter turns a reference into an acrylic painting on canvas, so this is a render:
`render --step finish --inputs <reference> <photo> --prompt "<finish.prompt> The second image is the original photo: take every area's colors from it. <framing>" --quality high --out <lesson>/99_finish.png`
with a reason. Every step copies from the finish, so it gets high quality (as in the spike). Pass the photo too:
on the trees photo (2026-11-10) a Kuwahara reference alone turned a cream-gold sky into blue and purple patches,
and the finish needed a paid repaint.

Then check it against the photo yourself (Read both images). Simplifying is expected; flag only what the owner
would notice and mind: an area changed color or hue, something added, removed, or turned into something else, a
texture changed character, the mood or time of day changed. If anything is flagged, render once more with
`--inputs <finish> <photo>`, a prompt listing the fixes ("Repaint it with these fixes so it matches the second
image: ... Keep everything else the same"), and `--fresh` not needed (the prompt differs). Save the flagged list
for `review.json` as `finish_issues`.

### 3. Plan (`plan.json`)
Plan the lesson the way `plan_lesson` in `spike/run.py` does (read its prompt), from the finish, under the
technique's rules and step range. Write `<lesson>/plan.json` with exactly these fields (the spike's `LessonPlan`
plus three):

```json
{
  "photo": "photos/<file>", "technique": "techniques/<file>.yaml", "quality": "low",
  "subject": "...", "focal_point": "...", "light": "...",
  "components": ["farthest part first", "..."],
  "paints": [{"name": "Sunset orange", "recipe": "2 parts yellow, 1 part red, a touch of white",
              "hex": "#e8903a", "used_for": "...", "sample_x": 0.4, "sample_y": 0.2}],
  "steps": [{"id": "sky-gradient", "name": "Paint the sunset sky", "paints": "which parts this step adds",
             "looks_like": "the WHOLE canvas after this step, including what is still white canvas",
             "covers_canvas": false, "colors": ["Sunset orange"], "brushes": "...",
             "how": ["2 to 5 instructions, each naming its brush move"], "watch_out": ["1 or 2 beginner mistakes"]}]
}
```

The last step is the finished painting: `"looks_like": "The finished painting."`, `"covers_canvas": true`. Step
ids are unique lowercase slugs. Use only palette tubes in recipes. `sample_x`/`sample_y` (0-1 from the top left)
point at a flat patch of that paint in the finish; `publish` snaps each hex to the painted color there. The palette
filter output on the finish helps you pick hexes.

Then decide, per step, how to make it (the tool order above), and note it for `text.json` later. For a paint-along
lesson most steps are "the finish with later parts not painted yet", which only compositing (#8) or a render can
make today; a sketch or tracing step (block-in technique) is the `edges` filter, and a value or color-blocking
step may be `value-study` or `posterize`. Put filter-made step images at `<lesson>/NN_<id>.png` (NN from 01).

### 4. Render the remaining steps
`render-step --lesson <lesson> --steps <ids...> --why-not-filter "<reason>" --quality <quality>` renders every
listed step at once, each from the finish, with the spike's step prompt (`--mode parallel`, the spike's default).
Leave out steps you made with filters. Check the JSON: any step with `"refused"` is flagged, not retried.

### 5. Review in a fresh context
Don't grade your own images. Start a subagent (Agent tool, general-purpose) with only this:
- the paths of the step images in order (last is `99_finish.png`) and, for each, its id, what it adds (`paints`),
  and `looks_like` from the plan;
- this checklist, from `review_steps` in `spike/run.py`: each step is the canvas after that step, so everything
  from earlier steps is still there in the same place and shape, plus only what this step adds. Flag only clear
  problems a painter following along would notice: something appears before the step that paints it; something
  painted earlier is missing, moved, or a clearly different shape or size; the image doesn't match `looks_like`
  (white canvas showing where it should be covered, or covered where it should be white). Ignore small differences
  in brushwork, texture, and exact color. Never flag the last step. Also check the technique's painting order.
- ask it to Read every image and answer with JSON only: `{"issues": [{"step_id", "problem", "fix"}]}`, `fix`
  phrased as an instruction for redrawing that image.

Redo each flagged step: `render-step --steps <id> --fix "<fix>" --why-not-filter "<reason>"` (one step per call;
run them in parallel as separate commands if there are several). Then review again in a new subagent. Two review
rounds at most. A step still flagged after that, or refused by the caps, stays as it is and is listed for the
owner. Save all issues, with their round, in `review.json` as `review_issues`.

### 6. Write the steps (`text.json`)
Read the final images in order and write each step's instructions from what its image actually shows, like
`write_steps` in `spike/run.py`: name the real shapes and areas, give the mixes by paint name, keep the planned
advice that still applies, plain words, 2 to 5 short steps. Write `<lesson>/text.json`:

```json
{"steps": [{"stage_id": "sky-gradient", "what_to_do": ["..."], "mixes": ["Sunset orange"], "watch_out": ["..."],
            "paint_notes": [], "made_with": "render", "reason": "why this tool"}]}
```

`made_with` is `filter:<name>`, `composite`, `throwaway:<script>`, `render+filter:<name>`, or `render`.

### 7. Publish and report
`publish --lesson <lesson>` writes `lesson.json` and `lesson.html`. Then tell the owner, starting with anything that
needs them:
- steps flagged and left as they are, with the reason;
- image cost for the lesson (`image_cost_usd`), paid and cached renders, and steps by source (filter, render, ...);
- compared with the spike's low-quality baseline: $0.26 for a whole lesson on the trees photo (`docs/decisions.md`);
- the path to `lesson.html`, and send it to them (SendUserFile) when that tool is available.
