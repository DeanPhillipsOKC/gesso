# v4 spike (W1): a teacher writes the step, and the fact sheet checks it

Spike for #254, under #240 (`docs/design/pipeline-v4-plan.md`, Wave 1). Code: `spike/experiments/v4_teacher.py`, and
an option added to the student test (`v4_student.py --words-from <folder> --results <file>`). Its test:
`spike/tests/test_v4_teacher.py`. The words, the checker's findings, the blind graders and every writer's tokens:
`spike/experiments/v4_teacher.json` (its `report` key holds the numbers below). The student test's answers for each
variant: `spike/experiments/v4_teacher/<variant>.json`. Run on 2026-11-18.

**Verdict: adopt one writer for the whole lesson, writing a fixed set of lines (`lesson-slots`), as the writer W2
builds on. Drop the other three.** Its words scored higher than v3's on all three bench pictures in the student test
(+0.21 over the 64 steps, about two standard errors), and every blind grader preferred them (6 of 6, none for v3).
They fix three of v3's four words that point the wrong way, use half as many words, and cost less than v3's stage
writers. Choosing it over one writer a stage in free prose (`stage-free`) rests on cost and the graders, not on the
student test: stage-free scored about the same (+0.18, a third of a standard error less), did better on the cow, and
by the 0.25 rule fixed all four of v3's word faults. It costs $2.19 a lesson against $1.30, and the graders preferred
it 5 of 6 against 6 of 6. Lesson-free gained nothing on the student test, and stage-slots was no better than
stage-free and cost more. Two cautions come with it. The gain clears the 0.25 bar on one lesson only (the cow): on the cat and the birch
grove it is inside the run-to-run spread. And both tests read the words without the outline and paint map the
real page shows, which v3's words lean on (see Limits). Three things are needed before it goes into a lesson run (see
"Before it goes into a run").

## What was run

The three v3 lessons frozen in `spike/experiments/bench/v3-words/` (the highland cow, 23 steps; the sleeping cat, 21;
the birch grove, 20), on their own pictures. Only the words change. The header (step name, paints with recipes,
brush) stays v3's.

**The writer** is one fresh Claude conversation (Opus, `claude -p` with no tools, through `v4_loop.call_claude`). It
gets, in one message:

- the brief (`BRIEF` in the code): write each step as you would say it beside a beginner at the easel. Say where to
  start, which way to pull, where the paint sits inside the thing and why, what to leave showing, and what it looks
  like when you stop. Cover everything the step changed, and no more. The card's technique stays as it is, put in
  the subject's terms. The number-and-side rules are v3's, plus one: name a place inside a thing that the sheet
  doesn't measure by what it is ("where the belly meets the blanket"), not with a side word pointing at it;
- every step's header and stroke card (load, motion, result, then, mistakes);
- the whole plan (`plan.json`) and the fact sheet (the stage writers' `facts.md`, all of them for a lesson writer);
- for every step, the before and after pictures side by side, and **a picture of only what the step changed**: the
  after picture where the step's colour moved (the student test's own change mask, at 480 pixels), and the before
  picture washed pale everywhere else;
- the photo and the finish.

**Four variants**, two by two:

| | one writer a stage (as v3) | one writer for the whole lesson |
|---|---|---|
| free prose (two to five short paragraphs) | `stage-free` | `lesson-free` |
| a fixed set of lines (First, Start, Strokes, Where the paint sits, Leave, Stop when) | `stage-slots` | `lesson-slots` |

Both forms are held to about 130 words a step.

**The check** is v3's: `facts.check_text` on the sheet, strict, as `merge` runs it. The first failures go back to
the writer once (the same conversation, v3's feedback wording). A sentence that still fails is taken out.

**The scores** are the student test's, unchanged (`docs/spikes/v4-student-test.md`):

- **carry, graded alone**: the image model does each step's words on its before picture (one low-quality edit), and a
  grader who never sees the words scores the result 1 to 5 against the real after. All 64 steps, one run a variant.
- **pick**, beside v3's header-only answers (reused): a step whose words score 0.25 or more below the header alone is
  a word fault. Run on all 64 steps for `lesson-slots`, and on v3's four fault steps for the other three.
- **the blind graders** (`bench/ab_grader.md`, two a picture, sides swapped, one call each). The two lessons share
  every picture, so each step's picture went in once with both lessons' words under it.

## Results

### The student test, carry it out (graded alone)

| Words | cow | cat | birch | all 64 steps, against v3 | steps rose / fell |
|---|---|---|---|---|---|
| v3 | 3.15 | 3.21 | 3.03 | (3.13) | |
| stage-free | **3.48** | 3.29 | 3.15 | +0.18 (± 0.10) | 22 / 14 |
| stage-slots | 3.39 | 3.24 | 3.20 | +0.15 (± 0.11) | 23 / 15 |
| lesson-free | 3.13 | 3.10 | 3.10 | −0.02 (± 0.11) | 15 / 18 |
| lesson-slots | **3.43** | 3.38 | 3.20 | **+0.21 (± 0.11)** | 24 / 14 |

(± is one standard error of the mean step difference.) Carry's measure, which needs no Claude, agrees on the order
except for lesson-slots: v3 0.64, stage-free 0.70, stage-slots 0.70, lesson-free 0.63, lesson-slots 0.67.

- **Three of the four variants beat v3 on every picture**, and lesson-free beats it on none. The 0.25 bar is twice
  the run-to-run spread of one lesson's mean, and only the cow clears it (stage-free +0.33, lesson-slots +0.28).
  Pooled over the 64 steps, lesson-slots' +0.21 is about two standard errors.
- **The slots help a lesson writer, and not a stage writer.** Free prose from one writer for the whole lesson came
  out shortest (2,270 words a lesson) and lost what the slots make it say. The stage writers did about as well either
  way.
- **The steps v3 did worst on rose most.** On the 17 steps v3's words got 2 or less, lesson-slots got 2.7 and
  stage-free 2.8, against 1.8. Part of that is regression to the mean (a step picked for a low score in one run scores
  higher in the next), so read it as a direction only.

### The blind graders

| Words | cow | cat | birch | preferred over v3 |
|---|---|---|---|---|
| stage-free | 2 | 2 | 1, and 1 no difference | 5 of 6 |
| stage-slots | 2 | 1, and 1 no difference | 2 | 5 of 6 |
| lesson-free | 2 | 2 | 2 | 6 of 6 |
| lesson-slots | 2 | 2 | 2 | 6 of 6 |

No grader preferred v3's words, in 24 reads. Their notes say the same thing in different words: v3's are "an outline
template with several wrong sizes", "outline-and-map boilerplate", and the teacher's "tell a beginner what to do,
where and in what order". Most called the preference slight to moderate, because the faults they mark worst are in
the shared pictures (cow 8, cat 4, birch 9 and 15). Over the 24 reads, `paintable` went from 2.1 for v3 to 3.4 (every
teacher's lesson got 3 or 4), `agree` from 2.4 to 2.9, and `real` stayed at 2.9, as it should with the same pictures.

The graders preferred lesson-free on all six reads while the student test gave it no gain. Clear words aren't enough:
the student test also asks where the paint goes, and lesson-free said that least.

### Words that point the wrong way (pick, beside the header alone)

| Step (v3's fault) | header | v3 | stage-free | stage-slots | lesson-free | lesson-slots |
|---|---|---|---|---|---|---|
| cow 2, cloud streaks | 0.60 | 0.12 | 0.50 | 0.55 | 0.55 | 0.52 |
| cat 2, dark leaves | 0.55 | 0.15 | 0.62 | 0.66 | 0.78 | 0.75 |
| birch 10, golden leaves | 0.65 | 0.35 | 0.75 | 0.68 | 0.68 | 0.82 |
| birch 20, sunlit leaves | 0.45 | 0.12 | 0.22 | 0.22 | 0.14 | 0.18 |

(The chance the reader gave the real after. A word fault is 0.25 or more below the header.)

- **Three of v3's four faults are fixed by every variant.** v3's measured box said the paint covered less than the
  picture (cow 2's streaks "about 2 in from the top edge", cat 2's leaves "about 1/4 in wide"). The teacher, seeing
  the change picture, says where the streaks run down the sky and where the leaves hang.
- **Birch 20 is still a fault for the lesson writers**, and only just not one for the stage writers (0.22 against the
  header's 0.45: 0.23 below it, against the 0.25 rule). By the rule the stage writers fixed all four. In every variant
  the reader still picked the half-done picture first. The teacher says "most of it goes on the right side of the
  canvas" (true by the sheet's halves, so the check passes it) and "leave the very front clear". The change spreads
  across the whole band of ground, left side too. The reader picked the half-done picture, as it did for v3.
- **On all 64 steps, lesson-slots has that one fault, where v3 had four.** Its pick score is 0.70 against v3's 0.66
  on the same steps.

### The same step, in v3's words and the teacher's (lesson-slots)

**Sleeping cat, step 14, Shade the cat's shadow side** (the step the plan opens with). The page also shows the
paint (Dark gray) and the brush (1/2 inch flat).

> *v3:* 1. Let the sleeping tabby cat and the blanket dry to the touch first. A hair dryer on low speeds it up.
> 2. Inside the outlined area. Its bottom is about 3 1/2 in from the bottom edge, and its left side is about 3 1/2 in
> from the left edge; it's about 7 in wide and 4 in tall. 3. The outline also runs under where the cat's stripes and
> pink ears, and the cat's sleeping face will go: paint straight through there. 4. The outline also reaches onto the
> sleeping tabby cat and the blue wall, painted already: there, only soften this paint into their edge and leave
> them showing. 5. Paint: Dark gray. 6. Brush: 1/2 inch flat. 7. Bend every stroke with the shape: from the top of
> each bump down along its curve, and around a round shape. 8. It should leave marks that bend with the shape, which
> is what makes it look round or sloped. *Tip:* The after picture puts Dark gray over almost all of the sleeping
> tabby cat, not only inside the outlined area: leave the first gray showing only for the muzzle, the two front paws
> and the patch on its side, where the after picture has them. Pull a darker curved line where the head meets the
> body and along the tail wrapped in front of the body. Bend the strokes over the back, from the top of each curve
> down, and keep them off the blue wall.

> *Teacher:* 1. First: Let the Mid gray dry. 2. Start: Start with Dark gray in the deep curve behind the head, where
> the head tucks against the body. 3. Strokes: Pull curved strokes down that crescent, from the top of the body
> toward the blanket. Then sweep around the round end of the body and along the tail, bending every stroke with the
> shape. 4. Where the paint sits: Dark gray goes on the far round end of the body, along the tail lying in front,
> where the chin meets the blanket, and in the crescent behind the head. These are the parts turned away from the
> window light. 5. Leave: Leave the head, the ears and the top of the body Mid gray. Also leave the muzzle, the paws
> and a patch on the side plain gray, ready for the white. 6. Stop when: Stop when the cat looks round: light on its
> head and top, dark around its back end and tail, with a few soft gray flecks where the two meet.

Carry graded v3's 4 and the teacher's 3 on this step: one step is inside the 0.54-point spread of a single grade.

**Highland cow, step 15, Pull the honey-gold locks** (carry: v3 2, the teacher 4).

> *v3:* eleven lines: the drying line, the outlined area "about 2 in wide and 4 in tall", two outline lines, the
> paint, "Mix enough Honey gold for this step and step 18", the brush, the card's motion and result, "Leave the
> ginger locks from step 14 ... showing", "Step back, squint". *Tip:* the light comes from the right, so the locks go
> on the fringe and down the right side of the coat; one Honey gold dab in the meadow, "its middle about 11 1/4 in
> from the left edge".

> *Teacher:* 1. First: Let the ginger locks dry. 2. Start: Start with a small lock about 3/4 in wide on the top of the
> back, its top about 6 in from the top edge. 3. Strokes: Use short thick-to-thin strokes: full width at the top, then
> onto the edge and lighter as you pull down. 4. Where the paint sits: Add only a handful: a few down the shade side of
> the coat, one on the ear at the end of the fringe, and a couple of small touches in the grass past the chest.
> 5. Leave: Leave nearly all the ginger locks and dark gaps as they are. 6. Stop when: A few honey-gold locks catch
> the light, and the coat still reads mostly ginger.

**Birch grove, step 10, Dab the golden leaves everywhere** (one of v3's word faults; pick: v3 0.35, the teacher 0.82).

> *v3:* ten lines: the drying line, "Inside the outlined area, top to bottom. Its left side is about 1/2 in from the
> left edge and its right side is about 2 1/2 in from the right edge", two outline lines, the paint, the brush and
> load, the card's tap and result, "Leave what step 9 painted showing", the card's watch-out. *Tip:* most of it in
> the left half, the big bush nearest the sun built into a golden mound, leaves hanging from the top edge, scattered
> leaves elsewhere.

> *Teacher:* 1. First: Let the dark leaves dry. 2. Start: Start in the treetops at the top edge. Most of this step is
> on the left side of the canvas. 3. Strokes: Tap the same way, light and dry, building leafy clusters through the
> treetops. 4. Where the paint sits: Golden yellow fills the treetop leaves across the top and the big bush on the
> left side of the canvas. That bush patch is about 7 in wide, and its top is about 2 in from the top edge. Scatter
> separate dabs over the ground and path, with a few on the bushes in front of the firs. 5. Leave: Leave the orange
> and brown dabs showing between the gold ones on the ground, and the firs clear. 6. Stop when: Stop when the canopy
> and the left bush glow gold and the ground has gold leaves dotted through the darker ones.

(`v4_teacher.py compare <picture> <step>` prints any step in v3's words and every variant's.)

### What the check found, and what the sheet would need

| | check-text's first failures (cow, cat, birch) | taken out at the end | claims it could check |
|---|---|---|---|
| v3 | | 0, 2, 2 | 103, 115, 101 |
| stage-free | 6, 15, 12 | 0, 1, 1 | 64, 43, 45 |
| stage-slots | 6, 18, 15 | 0, 0, 1 | 55, 59, 62 |
| lesson-free | 12, 9, 6 | 0 | 44, 22, 43 |
| lesson-slots | 1, 9, 17 | 0 | 43, 40, 66 |

- **One round of feedback fixes nearly everything.** At most one sentence a lesson was taken out (v3's writers had two taken out on the cat and two on the birch grove). About
  half of the first failures were numbers the sheet contradicts (a distance from the wrong edge, a size of the wrong
  thing). The rest were references the sheet can't find.
- **What it can't find is where inside a thing the paint goes.** The references it failed to find, across all 12
  lessons: pronouns ("it" 8 times, "them", "that"), and pieces of a thing the sheet doesn't name: each ear, the
  muzzle, the nose, the chin, the back, the body, the tip, the fringe, the blanket's roll, the gold glow, the bands,
  the far peaks, the second dark fir. A place named without a side word isn't a claim at all, so "where the chin
  meets the blanket" or "the crescent behind the head" goes unchecked. That is why the teacher's lessons make 22 to
  66 checkable claims against v3's 100 to 115. The words now say more about place, and the sheet checks less of it.
- **To check a teacher, the sheet would need:**
  1. **the pieces of a thing**, named the way a painter names them (the cat's head, ears, back, belly, tail, paws;
     a trunk's lit and shadow sides; the blanket's roll), each with its box on the finish. The plan's `lays` already
     names many of them ("the far round end of the body"). A cut of each part into those pieces, by the image model or
     by hand-free segmentation, would give the boxes;
  2. **where a step's paint lands among those pieces**: the share of what it adds on each piece, the way it gives the
     halves now ("0.6 of it on the back end and the tail"), so "Dark gray goes on the far round end of the body"
     can be held to the picture;
  3. **a pronoun read as the sentence's subject** ("tap it" is the thing the sentence is about), which the checker
     doesn't try.
  Until then, the brief's rule (a side word only against a part on the sheet) keeps the checker honest, and the
  teacher's places inside a thing go unchecked.

### Cost

The Claude cost of the words, from the writers' log, a lesson (first words and the feedback round, at the API's
rates):

| Words | calls | pictures sent | words written | Claude, a lesson | of it, the feedback |
|---|---|---|---|---|---|
| v3's stage writers (the loop baseline, the cat) | 12 | | about 5,240 on the page | $1.42 | $0.21 |
| stage-free | 13 | 59 | 2,990 | $2.19 | $0.24 |
| stage-slots | 14 | 59 | 3,630 | $2.37 | $0.34 |
| lesson-free | 2 | 45 | 2,270 | $1.09 | $0.20 |
| **lesson-slots** | 2 | 45 | 2,650 | **$1.30** | $0.28 |

A stage writer costs more than v3's because it is sent the whole plan, the photo and the finish, and two pictures a
step. One writer for the lesson reads those once. Its longest call took three minutes, against 70 seconds for a
stage writer, so a lesson's words take about as long either way.

Of this spike: **$3.93 of renders** (256, under the owner's $5 for this issue), and $45.73 of Claude at the API's
rates, all through `claude -p` on the subscription: the writers $20.83, a stage-slots run lost to a full disk $5.73,
the blind graders $8.29, carry's grader $7.70, pick $3.17.

## Before it goes into a run

Each is small. None is needed for W2, which builds on the writer as it is here.

1. **`check` refuses an earlier step's paint by name.** The teacher names the paint already on the canvas ("leave
   the Mid gray showing") on 12 of lesson-slots' 64 steps, and `check` sends a step back when its words name a paint
   it doesn't list (`tools.paints_not_listed`). Either the rule lets a paint from an earlier step be named, or the
   brief says to name earlier marks some other way.
2. **Lines over 40 words**: 20 of lesson-slots' lines, against v3's limit (`v4_loop`'s writers are told it, and
   `check` sends them back). The brief should give the limit.
3. **The page's aids.** v3's words point at the transfer outline and the Where picture, and the teacher's don't know
   they exist. The writer should be told what the page shows beside its words, so it can point there too.

## Limits

- **Neither test shows the page's aids.** The student and the graders read the words with the step's header, not the
  outline or the paint map the lesson page shows. v3's words lean on those ("Inside the outlined area"), and the
  graders marked them down for it. Since #174 scored v3 the same way, the baseline is consistent with it, but the
  gap may be smaller on the real page. The owner's painting (#252) is the check that has the page.
- One run of each variant a step. The gain clears the 0.25 bar on one lesson (the cow). On the cat and the birch
  grove lesson-slots is up by 0.17, inside the spread.
- A blind grader sees the two lessons' words step by step under one picture, not as two folders, so they read
  closer together than the brief's two-folder form. The graders saw only each step's after picture, not the
  before-and-after pair. The A/B was blind (no side was named, and v3 was A for one grader and B for the other on
  every picture), but the two styles are easy to tell apart, and v3's numbered lines with a tip and outline lines
  read as the template the graders marked down.
- The writers ran once each. A second run of lesson-slots would show how much of the free-prose-against-slots
  difference is the writer's spread.
- Pick ran on all 64 steps for lesson-slots only. The other variants' faults were checked on v3's four steps.
- The words were written for v3's pictures as they are, including the faults the graders marked worst (cow 8, cat 4,
  birch 9 and 15). No words fix a big jump in the pictures.
- The disk filled twice (an 11 GB folder of earlier spikes' runs in `bench/runs/`, and Claude Code's transcripts of
  every call). The first stage-slots run was lost and made again. Nine lesson-slots renders failed and were made
  again, and any of those charged before failing aren't in the $3.93. Results files are now written whole and then
  moved into place, so a full disk can't cut one short.
