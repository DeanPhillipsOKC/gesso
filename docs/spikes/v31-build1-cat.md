# v3.1 build 1: step D run for real on the sleeping cat (#276)

`docs/design/pipeline-v3.1.md`, section 12, step 3, the guess to watch: the lesson's writer as a subagent that reads
`words/lesson/` and is sent back with a message, in place of the program loop's helper, which is sent everything in
one message. Run on 2026-11-20 by the new tools (`packets`, then `check-text`'s rounds and `--arc`) on the pictures
of `docs/spikes/v31-combined.md`'s cat (`sleeping-cat_v4loop_20261119-215313`, copied to
`output/sleeping-cat_v31build_20261120-1`). One Opus subagent wrote every message. No render.

**Verdict: the helper works.** It read the folder, wrote `out.json` with all 22 steps and every line, answered each
round with only the steps it changed (12 of 22 in `fix-1.json`), and wrote the arc as its next message. After the
rounds, `check` had no problems.

## The rounds, beside the combined lesson's cat

| | This run (a subagent) | Combined lesson (the loop) |
|---|---|---|
| Steps with all their lines | 22 of 22 | 22 of 22 |
| Words in the steps | 2,714 | 2,399 |
| Words in the arc | 606 | 652 |
| "As in step N" lines | 13 | 13 |
| check-text's failures, first (of 64 claims) | 20 | 14 |
| Left after its round, and taken out | 1 | 1 |
| Sentences naming a paint the step doesn't list, first | 0 | 2 |
| Lines over 40 words | 0 (the longest 38) | 0 |
| The arc's failures, first, and taken out | 1, 0 | 1, 0 |
| Lines left empty by a take-out | 1 (step 13's Leave) | not counted |
| Claude | on the subscription: no tokens logged | $0.83 at the API's rates |

The round with nothing to send (round 2: no paint the step doesn't list, no long line) was passed by, as the
design says it may be.

## What it showed

- **Eleven of round 1's 20 failures were the checker's, not the writer's.** A sentence that names "the window" (the
  ear "nearest the window", the blanket's end "nearest the window", "the sky through the window") had its numbers
  checked against the window's sky, not the step's own marks: "its middle about 2 1/4 in from the left edge" on
  the ear step was failed by the sky's 1 1/2 in. The writer then took the numbers out ("where the window light
  falls across the sill"), so the cat's steps say fewer measured places than the writer first wrote. This is
  check-text's reader (`facts.Reader`), which this build doesn't change. It is worth an issue of its own.
- **The writer told the pictures from the plan,** as it was asked to. Its first reply named six places where a
  picture does more or less than its step's paints (the far trees arrive with the wall, the frame step adds a
  lavender post, the sill's dark band comes a step early, step 8's streaks read paler, not darker). These are v3's
  pictures, and the words went with the pictures.
- **One line was emptied:** step 13's Leave ("next to the light ones" isn't on the sheet). The page leaves the line
  off, and `review.json` carries it as a known problem (run.md, D5).

## Limits

- One run, one picture, and no student test or grader: that is the gate's job (#279).
- The subagent's cost isn't logged (`/paint-lesson` runs on the owner's subscription). The loop is still the meter,
  and it isn't yet in step with the new run.md (#278).
