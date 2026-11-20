# The combined v3.1 lesson: everything the design adopts, run together

`docs/design/pipeline-v3.1.md`, section 12, steps 1 and 2, under #240. Run on 2026-11-20. Code:
`spike/experiments/v31_combined.py`; its test: `spike/tests/test_v31_combined.py`; every call, the words and the
finisher's output: `spike/experiments/v31_combined.json`.

**Verdict: go (the owner, 2026-11-20: "Looks good").** The owner read the lessons below and said yes to building
v3.1 into `/paint-lesson`. Three things the run showed change the design (below).

## What was run

The lesson's writer in six lines with the lean cuts and the paint check (`v4_writer_cost.py`'s `lean-paints`), the
long arc as its next message, the design's three changes to the writer's brief, and, on the cat, the lean finisher
(`f-lean`). Every call was Claude Opus 5.5 at medium effort through the program loop's helper. No render was made:

| Picture | Its pictures | What it got |
|---|---|---|
| The sleeping cat | the lesson #267 made after #250 (`sleeping-cat_v4loop_20261119-215313`) | words, arc, finisher |
| The chickadee | the site's sealed v3 lesson (`chickadee_skill_20261118-091227`) | words, arc |
| The lavender balloon | the site's sealed v3 lesson (`balloon-lavender_skill_20261118-094526`) | words, arc |

The chickadee and the lavender balloon were the owner's ask: his partner means to paint one of them this weekend,
and not the cat. A sealed lesson keeps its own diagrams, notes and known problems.

The three changes to the brief (`BRIEF_CHANGES` and `FORM_CHANGE` in the code): an earlier step's marks are named by
their look and step, not their paint; no line is over 40 words; the writer is told the page shows a Where picture
and a transfer outline and may point at them.

## The lessons

- [The sleeping cat](v31-combined-sleeping-cat.md)
- [The chickadee](v31-combined-chickadee.md)
- [The lavender balloon](v31-combined-balloon-lavender.md)

Each is the whole lesson as a painter reads it: the opening, each stage's lines, and every step's words under its
picture. For painting, `v31_combined.py lesson --picture <picture>` makes a whole lesson page (the sealed lesson's
own page with the new words in place of the old) in `output/v31-trial/`, which git ignores. It is a quick fit, not
section 7's page: the opening sits under "Before you start", and a stage's two lines sit among its first and last
steps' lines. The owner has both files.

## Results

| | Cat | Chickadee | Lavender balloon |
|---|---|---|---|
| Steps | 22 | 24 | 24 |
| Words in the steps | 2,399 | 3,047 | 3,029 |
| Words in the arc | 652 | 717 | 644 |
| "As in step N" lines | 13 | 13 | 13 |
| check-text's failures, first | 14 | 1 | 4 |
| Left after its round, and taken out | 1 | 0 | 0 |
| Sentences naming a paint the step doesn't list, first | 2 | 3 | 0 |
| Left after the paint round | 0 | 0 | 0 |
| The arc's failures, first, and taken out | 1, 0 | 0 and 0 | 3, 0 |
| Lines over 40 words | 0 | 3 (42 to 46) | 4 (41 to 44) |
| The words, Claude at the API's rates | $0.83 | $1.05 | $1.11 |
| The finisher | $0.52: 7 diagrams written, 7 drawn, no second look | | |

- **The pieces fit.** Nothing failed to run, no step is missing its words, and the finisher's diagrams all drew.
- **Naming earlier marks by their look works.** #270 found 22 sentences on a cat that named a paint their step
  doesn't list. With the new rule the three lessons had 2, 3 and 0, and the paint round cleared them.
- **The cost is the spikes'.** The cat's words and finisher come to $1.35, against #267's $0.92 and $0.50. The two
  lessons of 24 steps wrote about a quarter more words and cost about a quarter more.

## What it changes in the design

1. **Telling the writer "40 words a line" isn't enough.** Seven lines on two lessons went over, all of them "Where
   the paint sits". The build has to count them and send them back, in the paint round's place and form. The design
   said `check` holds the limit; it now says where in the words' rounds (section 5).
2. **The writer never pointed at the Where picture or the outline:** not once in 70 steps, though it was told it
   may. The rule stays (it costs two sentences of the brief and stops the writer contradicting the page), but it
   isn't a lever.
3. **Words can pass every check and still disagree with their picture.** The cat's finisher, which sees the step
   pictures, listed three: the sill's "dark grain streaks" where the picture has pale ones; the cat's block-in
   "reaches the right edge" where it stops about 1 in short; a nose "about 3/4 in wide" that is nearer 1/3 in. Two
   are places and looks the sheet doesn't measure, and one is a number check-text passed. Today they end as known
   problems on the page. Sending them back to the writer once is the obvious fix and nobody has run it: a risk in
   the design (section 14), not a piece of it.

## Limits

- One run a picture, and no student test or blind grader: the yardstick is the gate's job (section 13).
- The chickadee and the lavender balloon had no finisher, so nobody compared their new words with their pictures.
- The whole lesson pages are a quick fit of the words into v3's page. Section 7's page isn't built.
- Still the program loop's helper, not the skill's (the design's section 12).

## Spend

No renders. Claude at the API's rates: $3.51 (the cat $1.35, the chickadee $1.05, the lavender balloon $1.11), all
through `claude -p` on the subscription.
