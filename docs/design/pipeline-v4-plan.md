# Pipeline v4 plan: a lesson you can paint from

The plan for getting from pipeline v3 to v4 (owner approved the thesis, 2026-11-18). It is a series of spikes, not a
design: `docs/design/pipeline-v4.md` gets written from whatever the spikes adopt. Until then v3
(`pipeline-v3.md`) is the pipeline. The parent issue is #240.

## Context

v3 made the pictures true. The owner called its lessons "worlds better than v2", and then said of the words
(2026-11-18): "The text isn't very exciting to read, and I don't feel like it's very helpful ... the text doesn't
look like it's going to help us recreate the images." Nobody has painted from a Gesso lesson yet.

The evidence:

- **A step's words don't say where the paint goes.** Step 14 of the sleeping cat
  (`output/sleeping-cat_skill_20261118-080533`), "Shade the cat's shadow side": a box 7 in wide and 4 in tall (the
  whole cat), two stock lines about the outline, "Paint: Dark gray", "Brush: 1/2 inch flat", "Bend every stroke
  with the shape". The picture puts the shading under the belly where it meets the blanket and in the crease
  between the haunch and the body. The words name neither.
- **A step is a form filled in from data.** `draft-text` writes most lines from the stroke card and the measured
  box. The stage's writer may add a summary and a tip, and may reword a line (`v3/writer-brief.md`). So the words
  are accurate, and nothing in them is taught. Steps 14 and 15 of the cat share six of their lines.
- **A lesson is 21 separate forms.** Nothing says what the painter will learn, or ties one step to the next.
- **"Could I paint it" never scored well.** Every v3 spike scored 2 to 4 out of 5, and each adopted piece was the
  better of two flawed lessons (`pipeline-v3.md`, section 14). The graders read the words with the after picture
  in front of them, so they read knowing the answer.
- **Nothing measures the words alone.** `check-text` checks that a number or a side is true. It can't tell whether
  a step can be painted from.
- **Cost.** One v3 lesson made by a program costs $4.94 of Claude at the API's rates, about $3.50 through the API
  itself (`docs/spikes/v4-loop-baseline.md`, one run of one picture). The owner's aim is under $1, never at the
  price of a worse lesson (`docs/decisions.md`).

Three causes sit under it:

1. **The data writes and the writer fills gaps.** It should be the other way round.
2. **The pipeline knows where a step's pixels are, not what a painter does there:** where to start, which way to
   pull, where the dark sits and why, when to stop.
3. **The words are judged by readers who can see the answer.**

## The v4 idea

**A teacher writes the lesson, the data checks it, and a student who has only the words tests it.**

- One writer who has seen the whole painting writes each step as a person teaching it would. The fact sheet stops
  being the source of the lines and becomes their checker.
- The lesson has an arc: what you'll learn, said at the start, and steps that refer back to it.
- A step shows the motion as well as the result: where the first strokes go and which way they run.
- The yardstick is a student test. A reader with the before picture and the words, and no after picture, has to
  get to the after picture.

Cost is a track inside v4, not its headline. Every spike reports what its lesson costs in Claude, since the words
are where most of the cost is.

## Wave 0: the yardstick (before any experiment)

Nothing in Waves 1 and 2 starts until Y1 exists, or the words get judged the way v3's were.

- **Y1. The student test (#174).** A reader in a fresh context who has never seen the plan gets a step's before
  picture and its words. Two forms to try: it picks the after picture out of four, or the image model carries the
  words out on the before picture and the result is compared with the real after. The spike says which form
  agrees with the graders and what each costs. Its baseline is v3's words on the three bench pictures v3's gate
  used (the highland cow, the sleeping cat, the birch grove).
  **Done 2026-11-18 (`docs/spikes/v4-student-test.md`): both forms are adopted.** Carry it out, graded, is the
  score (v3's words: 3.15, 3.21 and 3.03 of 5, graded alone). Pick one of four, beside the step's header alone, finds words that
  point the wrong way. Neither measures stroke direction yet.
- **Y2. The owner paints one (`human`, #252).** The owner and their partner paint the sleeping cat from its v3
  lesson and note each step where the words left them guessing. This is the only test that isn't a stand-in. It
  doesn't block the spikes. Its notes are checked against Y1's scores, to see whether the student test finds the
  steps a real painter stumbles on.
- **Y3. The cost baseline on the bench (#253).** `spike/experiments/v4_loop.py` on the three bench pictures, twice
  each, so a cut of 30 cents can be told from the spread between runs.
  **Done 2026-11-19 (`docs/spikes/v4-cost-cuts.md`): $5.35 a lesson as charged, $4.16 priced as the API would charge
  it.** Two runs of one picture differ by $0.37 to $1.16, mostly in how many merges `check` asks for and how many
  rounds the chain's checker takes. A lesson's renders came to $0.55 to $0.95, not $0.35, since every merge renders
  the chain again.

The frozen bench, the blind A/B page and the graders' brief (`spike/experiments/bench/`) stay as they are. Y1 adds
to them.

## Wave 1: the words

Run on the frozen bench, on v3's pictures, so only the words differ between the two sides.

- **W1. A teacher writes the step (#254).** The writer gets the before and after pictures, a picture of only what
  the step changed, the fact sheet, the stroke card and the whole plan, and writes the step whole: where to start,
  which way to pull, where the paint sits inside the thing and why, what to leave, and what it looks like when you
  stop. `check-text` still holds every number and side to the sheet. Variants to try: one writer for the whole
  lesson against one a stage; a fixed set of line slots against free prose.
  **Done 2026-11-18 (`docs/spikes/v4-teacher.md`): adopt one writer for the whole lesson, in fixed lines** (First,
  Start, Strokes, Where the paint sits, Leave, Stop when). Carry: 3.43, 3.38, 3.20 against v3's 3.15, 3.21, 3.03
  (+0.21 over the 64 steps, clearing the 0.25 bar on the cow only). The blind graders preferred it 6 of 6. One word
  fault left of v3's four. Half v3's words, $1.30 a lesson against $1.42. A writer a stage in free prose scored about
  the same (+0.18) for $2.19, so the choice between them is cost, not score. The sheet can't check where inside a thing
  the paint goes: it would need a thing's pieces (ears, back, tail) and the share of a step's paint on each.
- **W2. The lesson has an arc (#255).** An opening that names the two or three skills this painting teaches and
  shows the road to the finish, stage openers that say what the stage is for, and steps that point back ("the
  same dry brush as the sill"). After W1, since it builds on W1's writer.
  **Done 2026-11-18 (`docs/spikes/v4-arc.md`): park the arc added by a second call on top of the writer's words
  (`arc-add`, +$0.28 a lesson); drop the arc written in with the steps (`arc-whole`).** Neither raised a score.
  Carry against lesson-slots: arc-add −0.16 (± 0.09; the cow −0.43, the cat and the birch grove level), arc-whole
  −0.22 (± 0.10, down on all three). The blind graders saw no difference in 10 of 12 reads and preferred the words
  without the arc in the other 2: their rubric scores whether a step can be painted, and it doesn't reward polish.
  arc-add's fall is on steps early in a stage, where the stage opener's "By its end" sentence describes a canvas
  several steps ahead. The owner read the cat's lesson ("it looks good") and approved a rerun with the end sentence
  on the stage's last step only: those 40 steps then score exactly lesson-slots' (0.00 ± 0.10), so arc-add in that
  form is no worse to paint from. The owner then asked for a longer opening and a callback on every step that repeats
  a stroke or a paint (`arc-add-long`, $0.43 a lesson): "overall big improvement", and level on the student test
  (+0.05 ± 0.09). **Adopted 2026-11-19 (owner's call, `docs/decisions.md`): the arc in its long form, added by its
  own call after the writer.**

## Wave 2: showing the motion

- **P1. Stroke maps (#256).** A few arrows drawn on the step's picture: where the first strokes go and which way
  they run. The chain already holds exactly which pixels each step changed. To find out: whether the arrows come
  from the change alone, from the writer naming them, or from both, and whether the student test reads them.
  **Done 2026-11-19 (`docs/spikes/v4-stroke-maps.md`): drop arrows from the change alone, park the writer's arrows
  checked against the change (`both`).** No map raised the student's score (`both` 0.00 ± 0.08, `change` −0.06,
  `writer` −0.13): the image model already runs its strokes the way the after picture does (0.78 on a new grain
  measure), so a map had little to fix. The blind graders preferred the lesson without change-only maps 6 of 6 (the
  change gives a stroke's line, not which end it starts, so grass, trunks and ears were drawn backwards), and `both`
  2 of 6 with 4 ties: it helps with place and misleads on dabbing steps. $1.33 of Claude a lesson as a call a step.
  If it comes back: arrows from the lesson's writer (a few cents a lesson, estimated), none for a dabbed stroke, the direction from the card.

## Wave 3: cost

- **C1. The cuts that don't touch the words (#253, with Y3).** Price and cache each call as the API would (about
  $1.40 of the baseline); have the plan's writer answer `plan-check` and `check` with changes to the plan, not the
  whole file again (about $0.45); send the plan's writer the library's list and let it ask for the files it picks.
  These are built, not spiked, and each is measured against Y3.
  **Done 2026-11-19 (`docs/spikes/v4-cost-cuts.md`): all three built (`v4_loop.py --cuts`); adopt all three (owner's
  call; the graders preferred the baseline on the cat).** With them a lesson is $3.65 at the API's rates
  (−$1.19 for the caching, −$0.37 for the changes, −$0.13 more for the picks). The plan's writer went from $1.68 to $1.03. The blind graders preferred the cut lessons
  7 times and the baseline 5, all 4 of the baseline's on the cat (a merge `check` asked for, and the chain's
  pictures). Two baseline runs made the same way split 2 of 2 on two of the three pictures, so one run a side can't
  show a small effect.
- **C2. A cheaper model or lower effort for the yes/no helpers** (the chain's checker, the feedback rounds). #221
  is the spike. It ends in a recommendation for the owner, since it changes "Claude does the checks".
  **Run 2026-11-20 for the chain's checker, Claude only (#268, `docs/spikes/v4-checker-cost.md`): drop proposed, the
  owner's call.** The 23 checker rounds of 13 loop runs were laid again from the render cache, with no renders, and
  each cheaper setting was asked them once. Every setting missed some of the 29 marks most of three Opus reads made:
  Opus low 4, Sonnet medium 5, Sonnet low 7, Haiku medium 6, Haiku high 7. The loop's own Opus read missed 2. Sonnet
  medium came closest (24 of the 25 marks all three Opus reads made, as often as a second Opus read) for $0.14 a
  lesson against Opus's $0.29. A miss leaves a thing in a step picture where it doesn't belong. #221 (other
  providers) stays blocked.
- **C3. The writers and the finisher** ($2.35 of the $4.94). Left until Wave 1 says what a writer is sent: cutting
  a shape that is about to change is work done twice.
  **Run 2026-11-19 (#267, `docs/spikes/v4-writer-cost.md`): adopt the lean words and the lean finisher, drop Sonnet,
  the owner's call 2026-11-20.** With Wave 1's words a lesson is $3.86 at the API's rates; with the two cuts, $3.06. The lean
  words (smaller pictures, a shorter fact sheet, feedback answered with only the changed steps, the arc as the
  writer's next message) cost $0.85 against $1.33 and score level on the student test (+0.08 ± 0.10), with 5 of 6
  blind reads tied. The lean finisher (smaller pictures, the diagram look only when one fails to draw) costs $0.50
  against $0.80, and the graders preferred it 4 of 6, none for the baseline. Sonnet lost on both sides (the words
  −0.30 ± 0.11, 5 of 6 reads for the baseline). Low effort and a split finisher were a little worse. After #250 a new
  cat had no merge asked for. #270 added v3's paint check to the words (a paint a step doesn't list goes back to the
  writer once): $0.07 a lesson, and none left on C1's three lessons.
  **For `pipeline-v4.md` (the owner's call, 2026-11-20): fix the brief's contradiction that causes them, with no spike
  of its own.** W1's brief says both "Name only the paints the step lists" and "name an earlier step's marks by
  their paint", so the writer names the earlier paint ("The Wood brown must be dry"). v4's brief names an earlier
  step's marks by their look and step ("the brown streaks from step 8"), keeping the paint's name only where a side
  word needs it for check-text to find the reference; if the earlier paint has to be named there, the check's
  round handles it. The paint check stays as the backstop.

## The later bet: an easel coach (#257, parked)

The painter photographs their own canvas mid-step, and Gesso says what is off and what to do next. No tutorial can
do that. It needs the app (milestone 3) and a paid call each time it's used, so it waits behind the waves above.
One cheap probe can run earlier, on Y2's photos of the owner's own canvas.

## How a spike runs

Same as v3 (`pipeline-v3-plan.md`, "How a spike runs"), with these changes:

- Code in `spike/experiments/v4_<name>.py`, a write-up in `docs/spikes/v4-<name>.md` ending in **adopt, drop or
  park**, with numbers. One issue a spike under #240, one pull request a spike.
- Each write-up reports three things: the student test's score against v3's words, the blind graders' A/B
  (`ab_grader.md`, two graders a picture, sides swapped), and the lesson's Claude cost from the loop's log.
- A words spike is adopted when the student test's score rises and the graders prefer it on most pictures and it
  loses clearly on none. A cost cut is adopted when the graders find the lesson no worse.
- Lessons and spikes run through the program loop, so every call's tokens are logged.
- Render spend stays under about $2 a spike. Anything dearer gets asked first.

## Order

1. Record the owner's yes in `docs/decisions.md`. Rewrite #240 and file the spikes (done with this plan).
2. Y1 and Y3 with C1. Y2 whenever the owner has an afternoon.
3. W1, then W2. P1 alongside W2.
4. C2 and C3.
5. Write `docs/design/pipeline-v4.md` from what was adopted (Fable), then one combined lesson for the owner.
6. The gate, then build v4 as `/paint-lesson` (Opus).

## The gate (proposed; the owner sets it)

- The student test's score beats v3's words on every bench picture.
- Claude's graders prefer v4 on most bench pictures and it loses clearly on none.
- **The owner paints one v4 lesson** and says the words helped.
- The lesson's Claude cost is reported beside the $1 aim. It is not a pass or fail.

## Kept as they are

- v3's pictures: the plan, the chain, the paints and `build-steps`. v4 changes what is said and shown about a
  step, not the step pictures.
- Technique comes from cited research, and how to do a stroke comes from the checked card. A teacher's words may
  put a card in the subject's own terms; they don't change the technique (`docs/decisions.md`, 2026-11-12 and
  2026-11-13).
- Every number and side is checked against the measured sheet. Inches, never percent.
- Acrylic, beginner, 12 to 24 steps, one move a step. Claude plans and writes. Lessons are made on Opus.
- No video or animated stages (`docs/vision.md`). A stroke map is arrows on a still picture.
- Quality before cost and before speed.

## Known risks

- **A student made of models is not a painter.** Y2 is the check on that, and it is one afternoon by two people.
- **Free prose is harder to check.** A teacher who writes more makes more claims the sheet can't measure (the
  crease between the haunch and the body). The sheet may need to measure where inside a thing a step's paint lands.
- **Better words may cost more,** against the $1 aim. The owner's order is quality first.
- **The image model as a student** may paint the after picture from the step's name alone, whatever the words
  say. Y1 has to show the score moves when the words are made worse on purpose.
