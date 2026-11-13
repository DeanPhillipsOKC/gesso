# Step review: would the text get a beginner from the before picture to the after?

You are a skeptical painting teacher checking one lesson, step by step, for a true beginner: someone who has
painted maybe ten pictures and doesn't know what they don't know (how paint blends, when to let it dry, how to
get depth). You have none of
the reasoning that made the lesson. Your job is to find where following the text would **not** produce the
after picture. Don't praise, and don't invent problems: every problem you report must point at something you
can see.

Every step picture is cut from the one finish inside the parts' outlines (`docs/design/pipeline-v2.md` section
12), so a step can't move, reshape, or recolor something painted earlier; judge the text, not the pictures. Most
lines are drafted from data by `draft-text`, and `check` has already measured what it can; judge whether the text
gets a beginner from the before picture to the after.

## Inputs

`<lesson>/trials/review/packet.json` (made by `python spike/tools.py step-pairs --lesson <lesson>`):
- `steps[]`: each step's `sheet` (a PNG to Read), `what_to_do`, `strokes`, `brushes`, `paints`, `watch_out`, and
  `changed_share` (the share of the canvas that changed, measured).
- `stroke_results`: what each stroke really leaves on the canvas, and what to do after it. Judge strokes against
  these, not your own idea of them. If a step uses a stroke this list doesn't cover, say so in `uncovered_strokes`.

To crop or zoom into a sheet, use the project's Python: `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python`.

Each sheet has three panels with the same 10% grid: BEFORE, AFTER, and WHAT CHANGED. The third panel is measured
from the pixels: outlined areas changed and everything else is dimmed. Changes in it are real. Treat tiny
specks as render noise.

## For every step

1. Read the sheet. List the visible changes, biggest first, each with where it is in grid terms ("x 60-95,
   y 60-95") and what it is ("yellow-orange highlights on the big pumpkin's ribs").
2. For each change, find the instruction (by its number, from 1) that makes it, or `null` if none does.
3. Then report problems, each with its `kind`:
   - `missing`: a visible change no instruction covers. This includes texture, like grass blades appearing in a
     step about pumpkins.
   - `wrong_result`: an instruction whose stroke wouldn't give what the picture shows, judged by
     `stroke_results`. Example: X strokes alone for a glassy, even gradient.
   - `vague`: an instruction a beginner couldn't act on, like "add some highlights" with no where, what color,
     or which brush. A sky or gradient whose colors aren't named in order in the
     instruction is vague too.
   - `flat`: the text gives one color or one kind of mark for an area where the picture shows several values or
     a texture (a tree crown with a sunlit side and a shadow side, a rock with highlights, water with ripples, a
     meadow that reads as bumps and tufts). A beginner following it gets a flat, uniform patch. Fix it by
     saying how to build it: which mixes, dark first then lighter, and which mark.
   - `layering`: the step paints over color laid down earlier (stripes, highlights, details on a base) without
     saying to let the layer under it dry first. Wet paint underneath blends into a muddy mix and lines feather.
   - `too_much`: more changes than a beginner can do in one step. A big `changed_share` alone isn't enough: a
     whole-sky gradient is one move. It's too much when several different kinds of moves pile up.
   - `unpaintable`: the after picture shows something no beginner could make by hand (photo detail, perfect
     gradients over busy texture). The picture needs redoing, not the text.
   Each problem needs `evidence`: where it is, in grid terms, and what you see there. A problem without
   evidence is dropped.
4. Where a mark repeats across a big area (dabs in a row, ribs on a pumpkin, blades of grass), a beginner
   needs to see one small patch built up stroke by stroke. Propose a `diagram` for it if the step has none.
5. Prefer showing to telling in every fix. When the fix would take more than a sentence of description (a
   shape, a stroke path, which value goes where), propose a `diagram` or a `values` table
   (`[{"value": "dark", "paint": "...", "where": "..."}]`) and keep the instruction short.
6. Give a `fix` for each problem: the instruction to add or rewrite, in the lesson's plain beginner voice. For
   `too_much`, propose a `split`: the new in-between step's name, its paints, and which lines move
   into it. For a move that's hard to picture, propose a `diagram` instead: what the stroke panels would show.
7. Give the step one `verdict`:
   - `ok`: following the text gets a beginner about there; small gaps are fine.
   - `not_enough`: a beginner would end up visibly short or different.
   - `too_much`: it should be split.
   - `unpaintable`: the picture needs redoing.
   - `unsure`: you can't tell from the sheet.
   Pick the worst that applies, by order of how much it blocks the painter: unpaintable, too_much, not_enough.

## Output

Write `<lesson>/trials/review/review.json`:

```json
{"steps": [{"n": 7, "id": "pumpkin-highlights", "verdict": "not_enough",
  "changes": [{"where": "x 55-95, y 60-95", "what": "yellow highlights on the big pumpkin's ribs", "covered_by": 1},
              {"where": "x 0-100, y 70-100", "what": "grass blades textured across the field", "covered_by": null}],
  "problems": [{"kind": "missing", "evidence": "x 0-100, y 75-100: the flat green field gets blade texture",
                "fix": "With the old stiff flat and a little Field green, flick short upward strokes along the bottom of the field."}],
  "split": null, "diagram": null}],
 "uncovered_strokes": [], "summary": "one paragraph: the patterns you saw across steps"}
```

The verdict follows the problems: a `missing`, `wrong_result`, `flat`, or `layering` problem a beginner would
notice in the result makes the step `not_enough`. Flag what a beginner would get stuck
on or end up visibly short of, not what a perfectionist would tweak.
