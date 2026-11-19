# v4 spike (W2): the lesson has an arc

Spike for #255, under #240 (`docs/design/pipeline-v4-plan.md`, Wave 1). Code: `spike/experiments/v4_arc.py`, and
a stage opener the student test can read above a step (`v4_student.step_text`, a step's `intro`). Its test:
`spike/tests/test_v4_arc.py`. The arc, the checks, the blind graders and every writer's tokens:
`spike/experiments/v4_arc.json` (its `report` key holds the numbers below). The student test's answers:
`spike/experiments/v4_arc/<variant>.json`. Run on 2026-11-18.

**Verdict: park the arc added on top (`arc-add`), drop the arc written in with the steps (`arc-whole`).** Neither
raised a score. Both made the student test worse, and arc-whole made it worse on all three pictures. The blind
graders saw no difference in 10 of 12 reads, and the other 2 preferred the words without the arc. That is short of
the plan's rule for adopting a words spike (the student's score rises, and the graders prefer it on most pictures).
arc-add is parked rather than dropped for two reasons:

- **Neither test can see what an arc is for.** The owner's complaint was "the text isn't very exciting to read".
  The graders' rubric asks whether each step can be painted from its words and tells them not to reward polish.
  Every grader said, in its own words, that the arc is framing that "changes nothing a painter would see or do".
  Whether the opening makes a lesson better to read is the owner's call, and it needs a person reading one lesson
  (below).
- **arc-add's fall has a likely cause that's cheap to remove.** Its step lines are lesson-slots' own, word for
  word, so the student's drop comes from the new text. The steps that fell are mostly early in a stage, where the
  stage opener's "By its end: ..." sentence describes a canvas several steps ahead. The image model seems to paint
  toward that canvas.

**Second update: the owner asked for a longer opening and more callbacks (`arc-add-long`, below), called the result
"overall big improvement", and approved testing it. It scores level with lesson-slots on the student test (+0.05 ±
0.09), with 12 to 13 back lines a lesson and a stage's end on its last step.**

**Update, after the owner read the sleeping cat's lesson ("it looks good") and approved the rerun: the end sentence
was the cause.** With the stage's end sentence shown only above its last step (`arc-add-noend`), the 40 steps that
aren't last in their stage score exactly what lesson-slots' words do (0.00 ± 0.10; the cow's 14 steps 3.43 against
arc-add's 2.79). Over the whole lesson that comes to 3.39, 3.38 and 3.15 against 3.43, 3.38 and 3.20: level, inside
the spread. So **arc-add with the end sentence on the stage's last step is no worse to paint from**, the graders call
it a toss-up, and the owner liked how it reads. It still doesn't raise the student's score, which the plan's rule for
a words spike asks for. Whether that is enough to adopt it is the owner's call (the arc was never going to move a
test of one step at a time). See "The rerun" below.

## What was run

Both variants are built on the teacher spike's adopted writer (`lesson-slots`, `docs/spikes/v4-teacher.md`) and
measured against its words. Its carry scores, graded alone, are the baseline: 3.43 (cow), 3.38 (cat), 3.20 (birch).

The arc has three parts, and both variants write all three:

- **an opening**: the two or three skills the painting teaches, each one a stroke card the lesson uses, with the
  steps that use it and one sentence of what the painter learns doing it here; then the road to the finish, two to
  four sentences;
- **a stage opener** for each stage: what the stage is for (`for`), and what the canvas looks like at its end
  (`end`, written from the stage's last picture);
- **a step that points back**: a line on a step that repeats a stroke or a paint from an earlier step ("As in step
  11: the same press-and-lift commas you used for the knit loops, now small with a little round"). The brief allowed
  about one step in four.

The two variants:

| | how | Claude calls a lesson |
|---|---|---|
| `arc-add` | One new call reads lesson-slots' words as they are (frozen), the plan, the cards, the photo, the finish and each stage's last picture, and adds the arc. No step's lines change. | 1, plus feedback if a check fails |
| `arc-whole` | The lesson-slots writer itself (the same message and brief) with the arc added to its brief, writing the whole lesson again. | 2 (words, feedback) |

**The checks**, beside check-text (which holds every number and side in a step's lines, the back line included):
a back line has to point at an earlier step that shares this step's stroke card or one of its paints; a skill has
to be a card the lesson uses, on steps that use it; and an opening or a stage opener may say no number and no side
word, because the sheet measures steps, not stages. A failure goes back to the writer once. What still fails is taken
out.

**How the arc reaches the tests** (the issue's comment asked for this decision):

- **The student (carry)** reads the stage opener above the step ("This stage, The blanket: ... By its end: ..."),
  on every step of the stage, since a painter has read it on the way. The back line sits among the step's lines,
  after Start. The student doesn't read the opening: it names skills and has nothing to paint.
- **The blind graders** (`bench/ab_grader.md`, two a picture, sides swapped, against lesson-slots) read everything:
  each lesson's opening first, then each stage's opener above the stage's first step. The side without an arc says
  "(no opening)" and "(no stage opener)". That shows which side is which, but the two can be told apart anyway.

## Results

### The student test, carry it out (graded alone)

| Words | cow | cat | birch | all 64 steps, against lesson-slots | steps rose / fell |
|---|---|---|---|---|---|
| lesson-slots (the baseline) | 3.43 | 3.38 | 3.20 | | |
| arc-add | **3.00** (−0.43) | 3.38 (0.00) | 3.20 (0.00) | −0.16 (± 0.09) | 8 / 18 |
| arc-whole | 3.13 (−0.30) | 3.24 (−0.14) | 3.00 (−0.20) | **−0.22 (± 0.10)** | 7 / 23 |

(± is one standard error of the mean step difference.)

- **Both fall on the cow past the 0.25 bar.** On the cat and the birch grove, arc-add is level and arc-whole is
  down, inside the spread.
- **arc-add's fall is on steps early in a stage.** Steps that aren't the last of their stage fell 0.20 on average (40
  steps). The last steps held level (−0.05, 22 steps), and those are the steps whose after picture is the opener's
  "By its end". On the cow, 9 of the 14 such steps fell, and so did step 1, the only step in its stage. The likely reading: the end sentence is a picture several
  steps ahead, and the image model paints toward it. A beginner might do the same.
- **Pointing back did nothing measurable.** On the steps with a back line, arc-add was −0.50, 0.00 and +0.25 against
  the baseline (cow, cat, birch; 4 to 7 steps a lesson), which is noise either way.
- **arc-whole is a fresh run of the writer, so its fall mixes two things:** the arc, and the writer's own
  run-to-run spread. Its first words failed check-text 4, 6 and 8 times, against lesson-slots' 1, 9 and 17, and none
  were left at the end.

### The blind graders

| Words against lesson-slots | cow | cat | birch | preferred |
|---|---|---|---|---|
| arc-add | 2 no difference | 2 no difference | 2 no difference | 0 of 6 |
| arc-whole | 2 no difference | 2 for lesson-slots | 2 no difference | 0 of 6 (2 against) |

On arc-add, the graders said the step words are word for word the same and the rest is "framing text, which the
rubric says not to reward". A few called it "slightly friendlier to read" or "a small comfort for a beginner",
then marked it no difference. `paintable` and `agree` were the same on both sides in all 6 reads. On the cat, both
graders preferred lesson-slots over arc-whole. One said its words "match the pictures more often and give a
beginner places and sizes to aim for". arc-whole's rewritten steps were a little vaguer about place, which fits its
fall in the student test.

### One lesson's arc in full (arc-add, the sleeping cat)

> **What this painting teaches:**
> - Building from pieces (steps 5, 6, 7, 9, 10, 13): Every big shape here starts as one simple rectangle, oval or
>   circle with the rest added in pieces, from the window frame's bars to the curled cat.
> - Press and lift (steps 11, 12, 17, 19): One touch, press and lift makes a comma: rows of them turn flat yellow
>   into chunky knit, and tiny ones fill the ears and the nose.
> - Curved strokes (steps 14, 15): Bending each stroke with the round of the body is what turns a flat gray shape
>   into a soft, curled, sleeping cat.
>
> **The way there:** You start with the far things a beginner can't spoil: the sky and leaves through the window,
> then the blue wall. Next come the window frame and the sill, which sit nearer, and then the blanket as the cat's
> bed. The cat goes on last as one plain gray shape, then gets its shading, white patches, stripes and fur. That way
> the final steps all go to its sleeping face.

The stage openers:

> - **The view through the window:** This stage paints the farthest thing in the picture, the soft sky and leaves
>   seen through the window. *By its end:* A small corner of soft blue sky and dappled leaves sits on otherwise bare
>   white canvas.
> - **The wall and the window frame:** This stage covers the bare canvas with the blue wall and stands the cream
>   window frame over it. *By its end:* A brushy blue wall fills the canvas, and a crisp cream frame with lavender
>   shadows stands over the leafy view.
> - **The windowsill:** This stage builds the wooden sill the blanket and cat will rest on, with the window light
>   falling across it. *By its end:* A warm brown sill runs the width of the canvas, streaky with grain and crossed
>   by bright peach patches of window light.
> - **The blanket:** This stage gives the cat its bed, a golden blanket made to look knitted with little commas of
>   dark and light. *By its end:* A chunky golden knit blanket lies on the sill, ochre in its dips and glowing at the
>   end nearest the window.
> - **The cat's shape:** This stage builds the cat as one gray shape and makes it look round with shading and white
>   patches. *By its end:* A plain gray curled cat sleeps on the blanket, darker on its far end and tail, with a white
>   muzzle, white paws and a white side patch.
> - **The stripes and ears:** This stage turns the gray cat into a tabby with tapered stripes and gives it pink ears.
>   *By its end:* Charcoal stripes wrap around the curled cat, and both ears are soft pink inside a gray rim.
> - **The fur:** This stage softens the smooth gray coat into fur with quick, light flicks. *By its end:* Light gray
>   flicks make the coat look soft and furry, the stripes still clear and the face still blank.
> - **The sleeping face:** This stage spends its last careful strokes on the sleeping face, the heart of the
>   painting. *By its end:* The finished painting: the tabby asleep on its knit blanket, eyes closed, with a pink
>   nose and white whiskers fanning out.

The steps that point back:

> - Step 4, Blend the blue wall. *As in step 1:* This is the same wet side-to-side blend you used for the sky. Now it
>   uses two blues and a wider brush.
> - Step 13, Block in the curled cat. *As in step 10:* Build the cat the way you built the blanket: one big oval
>   first, then the smaller pieces around it.
> - Step 17, Paint the pink inside the ears. *As in step 11:* These are the same press-and-lift commas you used for
>   the knit loops, now small with a little round.
> - Step 20, Line the closed eyes and mouth. *As in step 16:* This is the same Charcoal you used for the stripes, now
>   thinned with water for the liner.
> - Step 21, Pull the whiskers. *As in step 20:* Hold the liner upright as you did for the eye lines, now with thinned
>   Warm white.

The whole lesson, every step with its picture: [v4-arc-sleeping-cat.md](v4-arc-sleeping-cat.md). (`v4_arc.py show <picture>` prints any lesson's arc, both variants.)

### The checks

| | first failures, check-text / arc | taken out at the end | steps pointing back | arc words |
|---|---|---|---|---|
| arc-add (cow, cat, birch) | 0 / 0 on all three | 0 | 6, 5, 4 | 518, 450, 443 |
| arc-whole | 4 / 0, 6 / 0, 8 / 1 | 0 | 7, 4, 6 | 437, 387, 460 |

- Every skill named was a card the lesson uses, on steps that use it, and every back line pointed at an earlier
  step that shares its card or paint, both first time. The one arc failure was a stage end with a side word ("fills
  the lower canvas"), fixed in the feedback round.
- arc-add's back lines passed check-text first time: they name strokes and paints, not places.
- One back line breaks a rule from `docs/spikes/v4-teacher.md`, "Before it goes into a run": "the same Charcoal you
  used for the stripes" names an earlier step's paint, which `check` refuses. It is the same open question as there.

### Cost

| | Claude, a lesson (API rates) | on top of lesson-slots' $1.30 | renders, the carry run |
|---|---|---|---|
| arc-add | $0.28 | +$0.28 (a lesson's words $1.58) | $1.02 |
| arc-whole | $1.31 (the whole lesson's words) | about +$0.01 | $1.01 |

arc-whole writes the arc almost free: the writer already reads everything, and 400 more words of output cost little.
arc-add's one call costs a fifth of the writer, mostly to read the plan and the words again. Of this spike: **$2.03
of renders** (128, at the plan's $2 a spike) and $12.33 of Claude at the API's rates, through `claude -p` on the
subscription: the writers $4.79, the blind graders $3.74, carry's grader $3.80.

## The rerun (the stage's end sentence on its last step only)

The owner read the sleeping cat's whole lesson (`docs/spikes/v4-arc-sleeping-cat.md`) and approved $0.65 more of
renders. arc-add's words are unchanged. Above every step the student now reads only the stage's `for` sentence,
except on the stage's last step, which keeps "By its end" (its own after picture). The last steps' prompts are the
same as before, so only the 40 steps that aren't last were rendered again (`v4_arc.py packets` writes them as
`arc-add-noend`).

| The 40 steps not last in their stage | cow (14) | cat (13) | birch (13) | all 40, against lesson-slots |
|---|---|---|---|---|
| lesson-slots | 3.43 | 3.23 | 3.15 | |
| arc-add, end sentence on every step | 2.79 | 3.23 | 3.23 | −0.20 |
| arc-add, end sentence on the last step only | **3.43** | 3.23 | 3.15 | **0.00 (± 0.10)** |

The whole lesson with the rerun's 40 steps in place: 3.39 (cow), 3.38 (cat), 3.15 (birch), against lesson-slots'
3.43, 3.38 and 3.20. $0.63 of renders and $1.20 of carry's grader, so the spike's renders came to $2.66.

The caution: each is one render run, and on the cow a whole run's mean moves about 0.13 between runs. A recovery from
2.79 to exactly the baseline on 14 steps is far outside that, so the end sentence is the likely cause. It is still one
run.

What it means for the page: a stage opener says what the stage is for at its top, and its end goes with the stage's
last step (or as that step's picture, which the page already shows). Each step is about only that step.

## A longer opening and more callbacks (`arc-add-long`, the owner's ask)

The owner read the cat's whole lesson and asked: "Make the opening longer and add more step callbacks"
(2026-11-19). arc-add's brief got one more section (`LONG` in the code):

- the opening gains a **welcome** (what you're about to paint, its focal point, the mood) and **the light** (where it
  comes from and what it does, named by its source, not by a side). Each skill's sentence becomes two or three
  (what the stroke is, where it works in this painting, what to watch for), and the road four to six sentences;
- a **back line on every step that repeats a stroke or a paint**, where saying so helps, pointing to the step a
  painter would remember best. The old brief said about one step in four.

| | steps pointing back (cow, cat, birch) | arc words | Claude, a lesson |
|---|---|---|---|
| arc-add | 6, 5, 4 | 518, 450, 443 | $0.28 |
| arc-add-long | 13, 13, 12 | 829, 687, 702 | $0.43 |

The checks failed 1, 0 and 2 things first time (an opener's side word, two of check-text's), and everything passed
after feedback. The page now puts each stage's end after its last step, as the rerun found. The sleeping cat's whole
lesson in this form: [v4-arc-sleeping-cat.md](v4-arc-sleeping-cat.md) (`v4_arc.py page <picture>`).

**The student test (carry, graded alone, all 64 steps; the stage's end on its last step only):**

| | cow | cat | birch | all 64, against lesson-slots | steps rose / fell |
|---|---|---|---|---|---|
| lesson-slots | 3.43 | 3.38 | 3.20 | | |
| arc-add-long | 3.26 | 3.48 | 3.45 | **+0.05 (± 0.09)** | 12 / 12 |

Level: no picture moves past the 0.25 bar except the birch grove, which reaches it (+0.25), and the cow is down 0.17,
inside the spread. The 38 steps with a back line are +0.08 and the 26 without one are 0.00, so more callbacks cost
the painter nothing on this test. $1.02 of renders and $1.90 of carry's grader, which brings the spike's renders to
$3.68 (the owner said yes to more for testing).

**What the owner found reading it (2026-11-19):** "Overall big improvement." Steps 2 to 4 of the cat don't match
their pictures: the leaf steps show no green and the leaves arrive with the wall, whose strokes run diagonally. Those
are faults in v3's pictures and paints, not in the arc, and are filed as #262.

## What would settle it (written before the rerun)

1. **The owner reads one lesson's arc**, the sleeping cat's above, and says whether a lesson that opens this way is
   better to read or to learn from. No Claude test here measures that, and it was the reason for the spike.
2. **If yes, one cheap rerun of arc-add** with the stage opener's `end` sentence left out of what the student reads
   (or moved to the stage's last step, where it is the step's own after picture). Only the steps not last in their
   stage need it: about 40 renders, $0.65. That would show whether the opener's end sentence is what cost the cow.
   It is over this spike's $2, so it needs the owner's yes.
3. If the end sentence is the cause, the stage's end goes on the page as a picture (the stage's last step picture,
   which the page already has), not a sentence, and arc-add goes in as an extra call after the writer.

## Limits

- **Neither test credits an arc.** The student does one step at a time and never reads the opening. The graders'
  rubric is the owner's for paintable steps, and it tells them not to reward polish in the words. A lesson that is
  better to read and no worse to paint from would score a toss-up here. That is roughly what arc-add got on the cat
  and the birch grove.
- **The cause of the cow's fall is a reading, not a test.** It rests on where in the stage the steps fell (−0.20 on
  40 steps against −0.05 on 22). The rerun in step 2 above is what would test it.
- One run of each variant. arc-whole is a fresh run of the writer, so its words differ from lesson-slots' in more
  than the arc, and some of its fall may be the writer's spread.
- Pick (one picture out of four) wasn't run. carry is the score the plan names, and the back lines say nothing about
  place, which is what pick catches.
- As in W1, neither test shows the page's outline and paint map.
