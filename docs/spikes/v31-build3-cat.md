# v3.1 build 3: the loop on the new run.md, the sleeping cat sealed (#278)

`docs/design/pipeline-v3.1.md`, section 9: the loop is the meter. After build 3 it follows the new `run.md`: the
plan's writer is sent the library's list and the files it picks (`library`) and answers with changes
(`plan-change`); one writer writes the lesson, its rounds and its arc; the finisher sees the step pictures at 384
pixels and looks at its diagrams again only when fewer draw than it wrote. Run on 2026-11-20 with
`spike/experiments/v4_loop.py run photos/sleeping-cat.jpg`, on Opus 5.5 through Claude Code's one-shot mode.

**Verdict: sealed, $2.98 of Claude at the API's rates** ($3.02 as charged), against the design's "about $3.13".
Renders $0.86. One run, so read it as the design's number holding, not beating it.

## Cost by helper, beside the design's table

| | Steps 0 to the chain's checker | Words | Finisher | Lesson |
|---|---|---|---|---|
| The design (section 9, the spikes' means) | $1.72 | $0.92 | $0.50 | about $3.13 |
| This run | $1.36 | $0.90 | $0.72 | **$2.98** |

| Helper | Calls | API $ | What it did |
|---|---|---|---|
| Steps 0 and 1 | 4 | 0.30 | the photo check, the canvas, the reference and the finish |
| The plan's writer | 4 | 0.74 | the picks (0.19), the plan (0.43), one plan-check round as a 286-token change (0.09), the merge `check` asked for as a change (0.04) |
| The chain's checker | 2 | 0.31 | two rounds, 14 looks each |
| The lesson's writer | 3 | 0.90 | the words (0.62), round 1's fixes (0.16), the arc (0.13); round 2 and the arc's round had nothing to send |
| The finisher | 2 | 0.72 | review, 10 diagrams and the notes in one reply (0.58); one look, because 3 diagrams drew nothing (0.14) |

Where it went: words written $1.38, instructions and data $1.20, pictures $0.40.

## What the lesson is

22 steps in 9 stages, 15 units, 14 renders, 9 mixes. The writer picked 11 of the 23 element files, 18 of the 28 cards and
24 research sections. Round 1 sent back 12 of 36 checkable claims; none was left for `--final` to take out, and no
line was emptied. 16 "As in step N" lines, 670 words of arc, none failing its checks. 10 diagrams, all drawing
after the look. 7 known problems and 2 finish issues on the page, among them the checker's two units still marked
after its second round (strays on the blanket and the cat's tail), left when `erase` reached the lesson's render
cap ($0.86 of $0.93): the merge renamed paints, which renders part of the chain again.

The lesson is `output/sleeping-cat_v4loop_20261120-183042` (not on the site: the loop isn't `/paint-lesson`).

## What the run showed, and what changed

- **A first run didn't seal** (`output/sleeping-cat_v4loop_20261120-175905`, $3.62, renders $0.53). `check` named a
  step whose round brush its card (thick-to-thin) doesn't take, right after `draft-text`. run.md's C3 sends a
  problem that changes `plan.json` to the plan's writer then, but the loop only sent those that name `plan.json`,
  so the fault reached the seal, where the finisher can't fix it, and three seal rounds were spent on it. **Fixed
  in the loop** (`PLAN_ASK`): the brush a card doesn't take goes back at C3 too, up to two rounds. `plan-check`
  doesn't hold a step's brush to its card; it could, a step earlier, but the design keeps `plan-check` as it is.
- **A late merge reads a cold cache.** The first run's merge came five and a half minutes after the writer's
  last message, just past the five-minute cache, so it sent the writer's 80,000 tokens again ($0.41); the second's
  came in time ($0.04). That is #253's known cost of a late
  merge.
- **The look at the diagrams paid for itself here.** `publish` counted all 10 specs; `preview-diagrams`' new
  `drawn` count found 3 drawing nothing (the blanket's), and the one look fixed them. #267's test, `publish`'s
  count, would have skipped it.
- **The loop wrote into `site/history/`.** `publish` records every run under `output/`. The loop now points
  `GESSO_HISTORY` at the lesson's `v4/history/`, and the two runs' entries were taken out of `site/`.

## Limits

One run of one picture, so no spread: #253's cow and birch grove each moved $0.67 to $1.16 between two runs. No
student test or grader: that is the gate's (#279).
