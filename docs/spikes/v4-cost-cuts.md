# v4 cost: the baseline on three bench pictures, then the cuts that don't touch the words (#253)

Y3 and C1 of `docs/design/pipeline-v4-plan.md`, under #240. Run on 2026-11-19. The code is `spike/experiments/v4_loop.py`
(the cuts, each behind `--cuts`), and `spike/experiments/v4_cost_cuts.py` (the sums and the blind graders). Its
test is `spike/tests/test_v4_loop.py`. The numbers are in `spike/experiments/v4_cost_cuts.json` (`runs`: every run's
cost by helper, and each call of the plan's writer; `ab`: every grader's answer). The lessons are in `output/*_v4loop_20261119-*`. None of them is on the
site, since none was made by `/paint-lesson`.

**Verdict: adopt all three cuts, with the cat left to the owner.** With the three, a lesson costs **$3.65 of Claude at
the API's rates, against $5.35 as the baseline is charged and $4.16 priced as the API would charge it.** That's 32%
off the bill as charged, and 12% off once the baseline is priced the API's way too. That 12% ($0.51) is less than
the spread between two runs of the cow or the birch grove ($0.67 and $1.16). The plan's writer, where cuts 3 and 4 act, went from $1.68 to $1.03.
All three of its runs came in under every baseline run. The blind graders preferred the cut lessons 7 times and the
baseline 5, and they preferred the baseline on the cat in all 4 of its reads. The acceptance rule says a cut that makes a lesson
worse is dropped. But the same graders, given two baseline lessons made exactly the same way, preferred one of them in 2 of 2 reads on
two of the three pictures. So a 2-of-2 split between two runs isn't evidence that the method differs (below). The
graders' reasons for the cat are a paint merge that `check` asked for and the chain's pictures, not the plan's
writer.

The $1 aim is still a long way off. What's left is the stage writers (about $1.00), the finisher (about $0.95) and
the merges `check` asks for. Those are C3's and the loop's to cut, not these.

## What was run

`v4_loop.py run` on the highland cow, the sleeping cat and the birch grove (the bench's three, from `photos/`), on
Opus 5.5 through Claude Code's one-shot mode, as #241 ran it (`docs/spikes/v4-loop-baseline.md`).

- **The baseline:** no cuts, two runs a picture. One cow run stopped at the lesson's render cap ($0.93) after its
  merge and three chain-checker rounds re-rendered the chain three times. It is in the json, left out of every
  average, and the cow was run a third time.
- **Cut 3:** `--cuts api-cache,plan-changes`, one run a picture.
- **Cuts 3 and 4:** `--cuts api-cache,plan-changes,plan-picks`, one run a picture.

Cut 2 didn't get runs of its own: it changes how calls are cached, not what any helper is sent, so the baseline's own
calls priced the API's way give its number. It's switched on in both sets of cut runs. The cuts build on one
another, so each set has the ones before it.

**The cuts**, as built:

- **Cut 2, `api-cache`:** a call is cached as the API would cache it, through two of Claude Code's own switches,
  `FORCE_PROMPT_CACHING_5M` (the five-minute cache, at $5 a million tokens rather than the hour's $8) and
  `DISABLE_PROMPT_CACHING` (plain input at $4). A helper with one message (the chain's checker) isn't cached, and
  every other message uses the five-minute cache. The report prices every run both ways: as charged, and as the
  API would charge (`api_costs`). In that second figure, input is written to the five-minute cache only when the
  conversation's next message reads it within five minutes, and is plain input otherwise. A read more than five
  minutes after the write counts as sending it again.
- **Cut 3, `plan-changes`:** the plan's writer answers `plan-check` and the merges `check` asks for with changes to
  plan.json in a fixed shape (`CHANGES_FORMAT`: fields to set on a thing, paint, stage or step by its id, paints to
  rename or merge, steps to add or move), which the program makes (`apply_plan_changes`). A whole plan is still
  taken if it sends one. The merge isn't sent the plan again, since the conversation holds it.
- **Cut 4, `plan-picks`:** the plan's writer is first sent the brief, the two pictures, canvas.json, the technique,
  what `elements` prints, every stroke card in one line (id, name, result), the research's "For Gesso" section and the
  list of its other headings. It answers with the elements, cards and sections it wants, and they are sent in a
  second message. It can ask once.

A bug was found and fixed during the cut runs. Claude Code's no-cache switch also stops a message reading what earlier
messages cached. Cut 2 had used it on every conversation's last message, so those messages sent the whole
conversation again at full price. Now only a one-message helper goes uncached. The API's figure for the six cut runs
counts those messages as reading the cache, as the API would. Their "as charged" figure keeps the bug, so it reads
about $0.50 to $1.30 high on those runs.

## Cost

In dollars of Claude a lesson at Opus 5.5's published rates. "API" is the run priced as the API would charge it.

| Run | Cut | As charged | API | API without Claude Code's 1,400 tokens | Renders | Steps |
|---|---|---|---|---|---|---|
| Cow 1 | baseline | 5.38 | 4.43 | 4.35 | 0.78 | 22 |
| Cow 3 | baseline | 5.05 | 3.76 | 3.68 | 0.79 | 19 |
| Cat 1 | baseline | 5.52 | 4.52 | 4.45 | 0.65 | 22 |
| Cat 2 | baseline | 5.64 | 4.15 | 4.06 | 0.61 | 22 |
| Birch 1 | baseline | 4.68 | 3.46 | 3.40 | 0.56 | 21 |
| Birch 2 | baseline | 5.81 | 4.62 | 4.55 | 0.95 | 22 |
| Cow | 3 | 5.08* | 3.76 | 3.69 | 0.82 | 20 |
| Cat | 3 | 5.39* | 4.06 | 3.98 | 0.62 | 21 |
| Birch | 3 | 3.96* | 3.53 | 3.45 | 0.45 | 20 |
| Cow | 3 and 4 | 4.03* | 3.54 | 3.46 | 0.55 | 22 |
| Cat | 3 and 4 | 4.46* | 3.74 | 3.66 | 0.77 | 24 |
| Birch | 3 and 4 | 4.97* | 3.68 | 3.59 | 0.58 | 20 |

\* With the cache bug above.

| | As charged | API | Spread between two runs of a picture (API) |
|---|---|---|---|
| Baseline, 6 runs | **$5.35** | **$4.16** | cow $0.67, cat $0.37, birch $1.16 |
| Cut 2 (the baseline priced the API's way) | | $4.16, −$1.19 | |
| Cut 3, 3 runs | | $3.78, −$0.38 | |
| Cuts 3 and 4, 3 runs | | **$3.65**, −$0.13 more | |

The cat's #241 run, $4.94 charged and $3.58 at the API's rates, is inside this spread. Most of a run's spread comes
from things none of the cuts touch: how many merges `check` asks for (1 to 3 a run), how many rounds the chain's
checker needs (1 to 3), and how long the finisher's conversation runs.

**By helper, the API's way (mean):**

| | Steps 0 and 1 | Plan's writer | Chain's checker | Stage writers | Finisher |
|---|---|---|---|---|---|
| Baseline | $0.35 | $1.68 | $0.28 | $0.90 | $0.95 |
| Cut 3 | $0.35 | $1.29 | $0.29 | $0.97 | $0.87 |
| Cuts 3 and 4 | $0.35 | $1.03 | $0.34 | $0.96 | $0.97 |

Only the plan's writer moves by more than its spread. Its calls, the API's way:

| Call | Baseline | Cut 3 | Cuts 3 and 4 |
|---|---|---|---|
| The plan's first message (92,000 tokens sent) | $0.81 to $0.98 | $0.76 to $0.90 | picks $0.17 + plan $0.43 to $0.47 (30,000 + 25,000 tokens) |
| A plan-check round | $0.25 to $0.29, 7,400 to 8,500 tokens written | $0.09 to $0.12, 160 to 750 written | $0.09 to $0.11, 200 to 1,400 written |
| The merge `check` asks for | $0.25 to $0.71 | $0.47 to $0.57 | $0.31 |

- **Cut 3** takes the writer's plan-check answer from the whole plan to a few changes: about $0.16 a round off, and
  about 18,000 fewer output tokens a run (93,000 to 75,000).
- **Cut 4** takes the first message from 92,000 tokens to 55,000 over two messages, about $0.25 off. The writer
  asked for 9 to 11 of the 23 element files, 16 to 19 of the 28 cards and 16 to 22 of the research's 64 sections, so
  it reads about half the library. One name it asked for didn't match a heading because it left out the section's
  number. That is fixed (`heading`).
- **The merge got dearer under cut 2.** It comes after the chain, more than five minutes after the plan, so the
  five-minute cache is gone and the writer's whole conversation (75,000 to 113,000 tokens) is sent again. Priced
  the API's way, the baseline's merges pay the same where they came late ($0.65 to $0.71). Two fixes, neither built:
  the API's hour-long cache on the plan's first message only ($8 rather than $5 on about 30,000 tokens with cut 4,
  about $0.09), or a short fresh call for the merge with only the brief, the plan and the ask.

## The blind graders

`ab_grader.md`'s rubric, two graders a picture with the sides swapped, on two whole lessons (each its own finish,
plan, chain and words, since the plan can change). Each cut set was graded against the first baseline run of the
cow and the birch grove and the second of the cat (the cat's sealed one). A third round, `null`, graded two baseline
runs of each picture against each other, to see what the graders find when the method is the same on both sides.

| Round | Cow | Cat | Birch | For the cut / for the baseline / none | Paintable (cut, baseline) |
|---|---|---|---|---|---|
| Cut 3 | cut, cut | baseline, baseline | cut, baseline | 3 / 3 / 0 | 2.67, 2.83 |
| Cuts 3 and 4 | cut, cut | baseline, baseline | cut, cut | 4 / 2 / 0 | 3.00, 2.50 |
| Null (baseline against baseline) | run 3, run 3 | run 1, none | run 2, run 2 | | |

- **The null round:** both graders picked the same side on the cow and on the birch grove, though both sides were made
  the same way. Run to run, a lesson's chain and merges vary enough to decide a grader. So one run a side can't show a
  small effect of a cut in either direction. It also shows the cow and birch baselines the cuts were graded
  against were the weaker run of their two. Some of the cuts' wins there are that draw.
- **The cat, cut 3:** `check` asked to merge the ears' and nose's pink into the cat's gray (the mix fitter found they
  mixed the same), and the writer did, so those steps name a gray their pictures don't show. The graders marked
  that. It is #241's finding again: merges `check` asks for make known problems. The baseline's writer obeys the
  same asks.
- **The cat, cuts 3 and 4:** the graders' reasons are the chain's pictures: face features showing two or three steps
  early, a blotch on the wall, a jump on the blanket. The plan had 24 steps, the most of any run.

So nothing the graders said points at the plan's writer being sent less or answering with changes. Whether the cat
counts as "worse" is the owner's call (`docs/decisions.md`: a cost cut is adopted when the graders find it no worse).

The 18 graders cost $4.27 of Claude.

## Found on the way

- **A lesson's renders cost $0.55 to $0.95, not $0.35.** Every merge `check` asks for changes the plan, so the whole
  chain is rendered again, and a third chain-checker round adds its redos. One cow run hit the render cap. The 13 runs
  came to $8.98 of renders, on the owner's raised budget.
- **8 of the 13 runs didn't seal** (one is the cow that stopped). The loop handles one merge round, and `check` asked for a second in the others.
  Each is published, so the graders could read it. The loop should answer a second ask the way it answers the first.
- **`publish` writes a run into `site/history/`.** The test lessons were cleaned out of it before each commit.

## What's next

- C3 (the stage writers and the finisher, about $1.95 between them) once Wave 1's writer is settled.
- The merge: fewer asks (#241's finding, now on two cat lessons) and a cheaper way to make the one that comes. It
  costs Claude, renders and known problems.
- C2 (#221): a cheaper model for the chain's checker, $0.28 to $0.34.
