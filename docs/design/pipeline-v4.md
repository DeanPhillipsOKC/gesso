# Pipeline v4: a covered layer stops at a loose line

**A draft (2026-11-21, #292, for #287). Builds 1 to 4 of section 13 (the rule in `build-steps`, behind `--stops`;
the sheet's `stop` and `onto` and `check-text`'s line; the dashed stop line, the page's line and the stamp; the
briefs and the words' record of their pictures) are built on the branch `v4` (#295, #296, #297, #298); the rest
isn't.** The owner read it and merged it (#293), set the
gate as written (section 12) and the stamp at POC 2.2.0 (`docs/decisions.md`, 2026-11-21). The owner adopted the rule on 2026-11-21 after
spike #289 (`docs/decisions.md`; `docs/spikes/cover-margin.md`, sections "The owner's rule" and "The gap fixed"). It
lives in `spike/experiments/cover_margin.py` as the variant `line-1-next`, laid over step pictures after they are
built. This file says how it goes into the run so that every part of a lesson agrees with it. It changes
`pipeline-v3.md` and `pipeline-v3.1.md`; it doesn't replace them. Read those first: a section number below that
isn't this file's own is v3's.

Each piece is marked **proven** (the spike ran it, or it was measured for this design on the three bench chains), a
**guess** (this draft's own joining of the pieces, run by nobody yet), or **open**.

**The name.** `pipeline-v4-plan.md` is the plan whose spikes became v3.1; it keeps its name, and so do #240 and its
write-ups. This file is the pipeline called v4.

## Why this is v4, and why it is small

`docs/decisions.md` (2026-11-20) keeps a new pipeline version for "a change to how the step pictures are made or to
what a lesson is". This is the first: step pictures stop showing paint that the next stage covers. The owner said so
when he adopted it (2026-11-21). So a lesson made this way carries `"pipeline": 4`.

It is still written as changes to v3, as v3.1 was, because most of the run doesn't move:

- **Of the run's 13 rows (section 4), three change** (7, 8 and 11) **and one is told one more thing** (9, the
  writer's brief). The plan, the chain, the chain's checker, the paints and the recipes aren't touched.
- **No render and no Claude call is added.** The rule is arithmetic on masks the build already has.
- **Nothing has to run beside anything.** The rule runs after the chain, so one chain gives both lessons: `build-steps`
  with the rule and without it. That is a flag on one tool, not a second pipeline, and it is how the gate compares
  the two (section 12).

What follows from that:

- `plan.json` stays `plan_version: 3`. The writer writes the same file (section 9).
- A lesson is stamped **POC 2.2.0** (the owner's call, 2026-11-21; this draft had proposed 3.0.0).
- Going back is `build-steps --no-stops`, and every lesson on the site keeps the version that made it.

## 1. Why change

A step picture shows a whole layer, the part a later thing covers too, because each one is the finish erased
backward. A painter copies what they see. On the highland cow the sky step covers the whole canvas and the far hills
step four fifths of it, and the finish shows a strip of each. That is about 1.4 canvases of painting nobody sees
over the first four steps (#287).

The rule that fixes it exists, and only the step pictures know about it. In the spike the fact sheet still said the
sky reaches the bottom edge, the Where picture still outlined the whole canvas, and the words were held to the
pictures by one hand-made line a step and no check.

## 2. The rule (as adopted, widened once)

- **Which layers stop.** After each unit, a pixel is covered later when its owner at the finish is a later unit that
  shares no thing with the unit on top now. Of that, a unit stops only where all three hold:
  - the cover is from a later stage of the plan (work in the layer's own stage is one passage with it: the cow's
    clouds on its sky);
  - stopping leaves no bare canvas above paint already laid: nothing below it in its column is painted by an earlier
    stage than the one that covers it first (the birch grove's mist doesn't stop for undergrowth four steps away
    above a floor already painted). The cover may come any number of stages on (the owner's call, 2026-11-21, after
    the 2.2.0 cow; until then it had to be the stage right after, `line-1-next`). Specks under 1/4 in that a mask
    missed count as the paint around them;
  - the cover runs up from the canvas's bottom edge, at least 1 1/2 in up its column.
- **Where it stops.** In each column the layer is painted down to the deepest point it is needed within 2 in to
  either side. That line is smoothed, then moved about 1 in further down, with a small wobble and a ragged fade.
  Below it the canvas stays bare.
- **What it doesn't touch.** Flat layers stop too. Thin things (horns, trunks, grass) and subjects inside a layer
  are painted through: a flat placeholder under a subject lost every blind read.
- **What a step may change:** only where it lays paint.

The numbers are the spike's: 1 in past (`margin`), 2 in to either side (`LINE_REACH`), 1 1/2 in up (`LINE_RUN`), the
wobble 0.35 of the margin over 0.8 in, the fade 0.15 in, the seed 289. None was tuned; changing one needs a reason
the spike gives.

## 3. What's proven, and what isn't

| Piece | From | Proven | Not known |
|---|---|---|---|
| The rule's pictures | #289, 3 pictures | Blind reads: none, none on the cow and on the birch grove. The student test on the 12 changed steps: 2.92 against 3.12 (−0.21 ± 0.21), level within its noise. It skips 69%, 45%, 28% and 73% of the paint of the cow's steps 1 to 4 (1.42 canvases) and 28% of the birch grove's mist. The cat doesn't change. | No test can credit the saving. Adopted on the owner's judgement. Three pictures, all with a subject on land under a sky. |
| `build-steps`' checks 1 and 2 | #289; run again for this design | The last picture is the finish (0.003% off, the JPEG) and no step changes a pixel outside what its unit lays (0), on all three. | |
| The rule never hides paint the finish shows | this design, 3 chains | 0 pixels of any step's own unit, as `owner.png` gives it, are hidden. So `build_steps.visible` and everything measured on it don't move. | |
| Only the cover uncovers bare canvas | this design, 3 chains | The canvas a stopped layer leaves bare is painted only by the next stage's unit (the cow's steps 4, 7 and 8, the birch grove's step 4). No step that comes back to a stopped thing lays its covered part. | The rule's code allows it (section 5). No bench plan has the case. |
| Check 4 (a step that changes almost nothing) | this design, 3 chains | No step falls under its 0.2%. The smallest stopped step still changes 11% of the canvas. | A later stage of a layer that is mostly hidden. |
| The sheet follows when the masks follow | this design, 3 chains (below) | With the shown paint as each step's mask, `facts.make_sheet` gives the cow's sky step an area 4 1/4 in tall that reaches three edges, where today it gives 16 in and four. | The new facts (section 6) aren't built. |
| Words that say where a layer stops | #289, one writer call a picture | With one added sentence and one measured line a step, the writer wrote "Stop the sky about 3 1/2 in from the top edge, with a soft, wavy lower edge. Leave the canvas under it bare white, because the hills will cover it." | They never ran through `check-text`. The writer was sent only the changed steps. |
| The step after a stopped run | #289 | Left as written, the cow's step 8 said to fill purple stripes that were now bare canvas, and both graders named it. Rewritten, both reads were "none". | In a run every step is written from the new pictures. Whether a writer then leans on the plan's `after` isn't known. |

**Widened (2026-11-21).** With the rule widened (section 2), the cow's lines and its 1.42 canvases are as above,
and the birch grove's mist line rises at its left (its highest point 7 11/16 in to 7 5/16 in; 1.5% of the canvas
moves, 0.29 of a canvas skipped). The table holds the widened rule's numbers.

**Measured for this design** by running the experiment's `line-1-next` and `facts.make_sheet` over
`spike/experiments/bench/v31-gate/<picture>/chain/` (no render, no Claude call; the build's tests keep these numbers,
section 13):

| Layer | Its steps | Stops for | Its lower edge, from the top edge | Past the cover's top |
|---|---|---|---|---|
| cow: sky, then clouds | 1, 2, 3 | the far hills (step 4) | 3 5/16 in at its highest, 3 1/2 in for most of it, 4 1/8 in at its lowest (the left edge) | 1 in (11/16 to 1 7/16) |
| cow: far hills | 4 | the green hillside (step 7) | 4 5/8 in, 5 1/4 in, 6 1/16 in | 1 1/8 in (11/16 to 2) |
| birch grove: the mist | 1 | the forest floor (step 4) | 7 5/16 in, 8 3/16 in, 9 in | 1 1/8 in (11/16 to 2 1/2) |
| sleeping cat | none | | | |

The birch grove's far woods (steps 2 and 3) also stop, over 0.3% of the canvas.

## 4. The run: what changes

v3's table (section 4), with only the rows that change. Rows 0 to 6, 10 and 12 are as they are.

| # | v3.1 | v4 | From |
|---|---|---|---|
| 7 | `build-steps` lays each unit's change, a step at a time. | It lays them twice: once to learn where each step lays paint, then again with each stopped layer ending at its line. It keeps where each layer stops. | #289; section 5 |
| 8 | `step-aids` and `sheet` measure where each step lays paint. | They measure the paint the picture shows. The sheet gains two facts: where a layer stops and for what, and what a step's paint goes onto. | a guess; sections 6 and 7 |
| 9 | The lesson writer's brief. | Three more sentences: a layer that stops, the bare canvas under it, and a step painted onto bare canvas. | #289's sentence; section 8 |
| 11 | `check` | It also refuses words written for other step pictures, and holds a stopped step's distance to its line. | a guess; sections 6 and 10 |

## 5. Where the rule runs (`build-steps`)

**In `steps3.build`, as a second laying.** The rule needs to know where every step lays paint before it can say
what covers what, so the build lays the chain twice, as `erase` already does:

1. **First laying, as today.** It gives each step's mask (where it lays paint) and the paints. Nothing is written.
2. **The cover map**, from those masks, the units' stages and things (`plan3.units`), and which unit owns each
   pixel at the finish (`steps3.owner_from`, with the spike's correction: where the owning unit lays no paint on a
   pixel, the last unit that does).
3. **Each unit's line** (section 2), in inches.
4. **Second laying.** Inside the pixels a step lays, the picture takes that unit's line: bare canvas below it, the
   unit's picture above. Everywhere else it keeps what the step before showed.

The code moves out of the experiment into `spike/stops.py` (`covered`, `next_stage_paints` (since widened to
`no_gap_below`), `stop_line`, and the
part of `variant_steps` that `line` uses). The variants that lost stay in `spike/experiments/cover_margin.py` as the
record and are built nowhere.

**What it needs that the build doesn't have today:**

- **Inches.** `steps3.build` never reads the canvas. The rule is in inches, so `lesson3.make` passes the canvas box
  and size (`canvas.json`, or the default size picked as `step-aids` picks it), and `lesson3.digest` takes
  `canvas.json` in, so a changed canvas makes the step pictures stale.
- **The owner map before the pictures.** `lesson3.make` works it out after the build. It moves in front.
- Nothing from the chain. `chain/` is read as it is and no chain has to be made again: an older v3 lesson can be
  built this way from the chain it has.

**One thing the spike's code leaves open (a guess).** A unit's line is worked out from its own stage. A unit that
comes back to a stopped thing in a later stage (a glow added to the sky after the hills) is laid over the whole
thing, and could be judged not to stop where its first unit did. Its step would then lay the earlier layer's covered
part onto canvas that was bare, on a step that names a glow. So the build holds one more rule: **canvas left bare by
a stopped layer is uncovered only by a unit that shares no thing with that layer.** On the three bench chains no
step does otherwise, so their pictures are the spike's, pixel for pixel.

**What it keeps:**

- `v3/masks.npz`: `m<nn>` becomes the paint the step's picture shows. `step-aids`, `draft-text` and the sheet read
  it as they do now, and that alone moves most of what follows (sections 6 and 7). `f<nn>` is where the step lays
  paint in full, for the saving and for the tests.
- `v3/build.json`: `stops`, the rule's name and numbers, and a row for every stopped unit: its steps, the unit and
  first step that covers it, and its line as five distances from the top edge (its highest point, most of it, its
  lowest point, at the left edge, at the right edge). Each step's row gains `spared` (the share of its paint not
  shown). The lesson gains `spared_canvas`, those shares of the canvas added up. A unit that is covered from the
  bottom edge and doesn't stop is listed with why (the cover is two stages on; the cover is in its own stage), so
  a plan whose stages defeat the rule can be seen.

**The checks.** 1 and 2 must hold, as today, and are measured against the second laying. Check 3 isn't moved by bare
canvas, which no step lays. Check 4 is measured on the second laying. A new note, not a failure: a stopped unit
whose line leaves less than 1/2 in of it showing in some column that the finish shows it in (it can't happen by the
rule's arithmetic; the note is there to catch a fault in the masks).

**The flag and the stamp.** `build-steps --stops` while it is built, off by default, so the branch makes both
lessons from one chain. At the merge it is on by default and `--no-stops` stays for the bench. `publish` writes
`"pipeline": 4` when `build.json` has `stops`, whether or not any layer stopped, and 3 when it doesn't.
`site_lessons.kind` reads "3 or more".

## 6. The fact sheet and `check-text`

**Most of it follows from the masks (proven, measured).** `make_sheet` reads a step's area from its mask and "the
paint it adds" from what its picture changed inside the mask. With the pictures alone changed, the two disagree:

| Cow, step 1 (the sky) | Its area | The paint it adds |
|---|---|---|
| Today | 16 in tall, reaches all four edges | its middle 9 in from the top edge, reaches all four edges |
| Stopped pictures, today's masks | 16 in tall, reaches all four edges | its middle 1 1/2 in down, reaches the left, right and top edges |
| Stopped pictures, the shown paint as the mask | 4 1/4 in tall, reaches the left, right and top edges | the same |

On step 4 (the far hills) "the paint it adds" goes from "reaches the bottom edge, its middle 9 1/4 in down" to "its
middle 4 in down, reaches the left and right edges". So a sentence that takes the sky or the hills to the bottom
edge fails `check-text` with no new rule.

**Two new facts (guesses).**

1. **`stop`, on every step of a stopped unit,** copied from `build.json`. On the sheet:

   > It stops short. Its lower edge is a loose, uneven line: about 3 1/2 in from the top edge for most of its
   > width, 3 1/4 in at its highest and 4 1/4 in at its lowest (4 1/4 in at the left edge, 3 1/4 in at the right
   > edge). Below it the canvas stays bare. Step 4 (The far violet hills) paints there next, and its top covers
   > this edge by about 1 in.

   A box can't say this. The area's box ends at the line's lowest point, so the sheet alone would have the sky
   "4 1/4 in tall" while most of its edge is at 3 1/2 in, and the spike's own sentence ("about 3 1/2 in from the
   top edge") would fail by more than the 1/4 in allowed.

2. **`onto`, on every step:** of the paint the picture shows, the share laid on bare canvas and the share laid over
   each earlier part, read from which unit was on top before the step. On the sheet: "Of what it paints, about a
   fifth goes over The sky and the rest on bare canvas." The plan can't give this any more. The far hills' `after`
   was written for hills on a whole sky, and the cow's hillside now leaves bare canvas, not lavender, between its
   bands until step 8.

`lean` keeps both for the writer.

**What `check-text` holds (a guess).**

- A length from the top or bottom edge, said of a stopped step's own paint, passes when it lies between the line's
  highest and lowest points, with the usual tolerance. The five distances join the step's own places
  (`facts._positions`), in place of the area's box bottom.
- "Reaches the bottom edge" and "all four edges" already fail on a stopped step (above).
- No check reads `onto`. "Fill the purple gaps" has no number and no side word, so nothing catches it (section 14).

## 7. Teaching pictures (`step-aids`)

Each is drawn from the step's mask, so each follows (the cow, measured):

- **The Where picture** outlines the paint the step's picture shows. The sky's outline goes from 16 in tall to
  4 1/4 in, the clouds' from 9 3/4 and 6 in to 4 and 4 1/4 in, the far hills' from 13 3/4 in to 4 in. **A guess:**
  the stretch of the outline that is the stop line is drawn dashed, so it reads as "about here" and nobody copies
  its wobble. `aids.json` gives that stretch as a second path and the page draws it. If the page can't take a second
  path cheaply, the outline stays solid and the words carry it.
- **The Where words** measure what the finish shows of the step (`build_steps.visible`). The rule hides none of
  that, so they don't move, except where a part's children made the area the whole canvas (the sky's "reaches all
  four edges" becomes its real bottom). The writer isn't sent them (v3.1).
- **The paint map** covers the shown paint, for a step's map and for a part's. Its shares are of the shown paint.
- **The close-up** is cut from the pictures and needs nothing.
- **The transfer outline** doesn't change: it outlines things in front that start as a block-in, and the rule paints
  those through. A front thing that rises from the bottom edge now goes partly onto bare canvas, where its outline
  is the only guide, and the page already offers it.

## 8. The words

**Every step is written from the stopped pictures.** The spike wrote only the changed steps and found the next one
wrong. In a run there is one writer, one set of pictures, and no old words. `packets` cuts the pairs and the change
pictures from the stopped pictures, so the writer sees the bare canvas. Nothing is rewritten, because nothing was
written before.

**The brief (`v3/lesson-brief.md`) gains three sentences** in "What a step says". The first is the spike's, changed
to point at the sheet:

> Some layers stop short of where the picture will end: `facts.md` says "It stops short" on such a step. Say how far
> the layer goes, in the sheet's inches from the top edge, and that its lower edge is loose and uneven, not a ruled
> line. In Leave, say that the canvas below it stays bare and which step covers it. Never send the painter round
> the outline of a thing that isn't painted yet.
>
> A step's paint may go onto bare canvas where the plan's `after` says an earlier layer shows: `facts.md` says what
> it goes onto. Write to that and to the picture.

**The arc** is written from each stage's last picture and holds no number, so it follows. Its brief gains one
clause: the way there may say that the first layers stop where the next will cover them.

**Words belong to their pictures (a guess).** `packets` records what the step pictures were made from
(`build.json`'s `made_from` and whether it has `stops`) in `words/lesson/`. `check-text` and `check` refuse words
written for other pictures and say to run `packets` and the writer again. Today nothing stops a lesson rebuilt with
the rule from being sealed with the words it had, and the faults the spike found that way had no number in them.

## 9. The plan and the chain: unchanged

**`plan.json`, `plan-check`, `erase`, the chain's checker and their briefs stay as they are.**

The issue asks whether the `after` lines and the `behind` lists should change, since the sky's `after` says "the
whole canvas is sky" and the far hills now sit partly on bare canvas. They stay, for these reasons:

- **`behind` and `after` are what the chain is asked for,** and the chain still makes whole layers. A render that
  removes the hills has to paint something where they were. "The sky" is a request the model keeps; "the sky above
  a line and bare canvas below it" is one `erase` has no kind for, and soft covers drawn by the model are out of
  scope. The rule needs the whole layer under the cover to exist: the line is cut from it.
- **The plan's writer can't know where a layer will stop.** The line comes from masks that exist only after the
  chain.
- **It is what was tested.** Every picture the owner saw came from a chain made by a plan as written.
- **The one reader the `after` lines could mislead is the lesson's writer.** Its brief already says to write to the
  picture where the plan disagrees. Section 8 adds the fact that says what a step's paint goes onto.

**One sentence joins `plan-brief.md`** (a guess), under `behind`: write `behind` and the `after` lines as now, as
if each layer ran under what covers it; a later tool decides how much of a layer its step picture shows.

**The stages now decide more than headings.** A layer doesn't stop for a cover in its own stage, nor above paint a
stage between them has already laid. A plan that puts the far hills in the sky's stage stops nothing there. (Until
the rule was widened, a layer stopped only for the stage right after its own, and the 2.2.0 cow's sky didn't stop
at all: its chain showed sky, not hills, behind the hillside, two stages on.) The brief
doesn't ask the writer to arrange stages for the rule: on the two bench plans it changed, the stages as written
were right. `build.json` lists what didn't stop and why (section 5), so the gate's lessons show how often it
happens before anyone writes a rule for it.

## 10. `check`, the finisher, the seal, the page

- **`check`** holds the build's two checks on the second laying, the sheet as it is now (so section 6's facts), and
  section 8's refusal. It adds the note of section 5.
- **The finisher** (`steps/8-finish.md`) is told that bare canvas below a loose line in the early steps is meant,
  and isn't a known problem. Left untold, it would file the cow's first seven steps.
- **The seal and `publish`** need nothing but the stamp. `lesson.json` gains `spared_canvas` beside each step's
  `spared`.
- **The page** draws the dashed stretch (section 7). **A guess, and optional:** one line under the opening, "This
  lesson skips about 1 1/2 canvases of painting that later layers would cover." It is the owner's reason for the
  change, and it is the only place a painter would hear it.
- **Older lessons** have no `stops`, no dashed path and `"pipeline": 3`. The page shows what a lesson has.

## 11. What it costs

- **Renders:** none added. **Claude:** none added; the writer's facts grow by one or two lines on the steps that
  stop or paint onto bare canvas.
- **Time:** `build-steps` lays the chain twice and works out a line a unit. Seconds.
- **The gate** costs what three lessons cost, and half as much again for the second set of words (section 12).

## 12. The gate (set by the owner, 2026-11-21: "Default")

The spike tied on both tests, and neither can see the saving. A gate that asks for a win can't be met, so this one
asks for no loss and reports the saving.

Three hands-off bench lessons (the cow, the cat, the birch grove) from the build's branch. Each is run once to its
chain, then built twice from that chain, with `--stops` and without, and each build gets its own words, finisher and
seal. So the two sides differ by the rule and by one writer's run, and by nothing else.

- **Both builds seal,** and the build with the rule has no more known problems than the one without.
- **The pictures are right by construction:** checks 1 and 2 hold; a lesson where nothing stops (the cat) has the
  same step pictures byte for byte either way.
- **The student test doesn't lose:** over the steps whose picture changed and the step after each such run, on the
  three lessons together, the build with the rule isn't lower by 0.25 or more. Two carries a side; a third when the
  gap is between 0.15 and 0.25. Each picture's number is reported.
- **Claude's blind graders:** the build with the rule loses clearly on no picture. Ties are expected.
- **The saving is reported,** not passed or failed: `spared_canvas` for each lesson, which layers stopped, and
  which didn't and why.
- **The owner reads the cow** and says yes.

**Not in it:** the owner painting one (#252). It is the only test that can feel the saving, and what it shows is
fixed afterward.

## 13. Build order and tests

By Opus, on a branch, behind `--stops`. Each step is a pull request with its tests; the quick set while working and
the full suite before each merge (`docs/testing.md`).

1. **The rule in `build-steps`.** `spike/stops.py`, `steps3.build`'s second laying, `lesson3.make` and `digest`,
   `masks.npz` and `build.json` (section 5), `tools.py build-steps --stops`. Tests:
   - on a made-up scene (as `test_v3_cover_margin.py`'s): a band covered from the bottom edge by the next stage
     stops about 1 in past the cover's top; a cover in the same stage, one two stages on, a thin one, an island, and
     one shorter than 1 1/2 in each stop nothing; checks 1 and 2 hold; the bare canvas is uncovered only by a unit of
     another thing, with a made-up unit that comes back to the stopped thing after its cover;
   - without `--stops` a fixture lesson's pictures are today's, byte for byte, and with it a fixture where nothing
     stops gives the same;
   - on the three bench chains (a slow test): the pictures are the experiment's `line-1-next` pictures, and the
     lines are section 3's table.

   **Built (#295, `spike/tests/test_stops.py`).** As written, with these readings of what the design left loose:
   - A line's five distances are where the bare canvas starts in each column (past the fade), as section 3's table
     was measured; on the bench they come within 1/32 in of it. `past_cover` gives how far that is past the
     cover's top (most of it, the least, the greatest).
   - A stopped unit's row is kept only when its line hides some of its own paint. A unit with a line that hides
     none of it is listed under `not_stopped` ("its line hides none of its own paint"). `covered_by` is the first
     unit of a later stage that lays paint below the line (the next stage's, before the rule was widened).
   - A unit that doesn't stop is also listed when anything later covers it from the bottom edge (1 1/2 in up): "the
     cover is in its own stage", "stopping would leave bare canvas above paint already laid" (until the widening,
     "the cover is more than one stage on"), or "the cover is too narrow" (a trunk or a post: each column's depth is
     its neighbours' too). On the cow, the green hillside is listed (its cover is the tall grass, four stages on).
   - The rule beside the spike's keeps every layer that left a pixel bare until it is painted, so where the cow's
     sky and clouds both stop, a glow on the sky stays off the canvas the clouds left bare too.
   - Check 3 (`from_its_paints`) stays the first laying's, since bare canvas is laid by no step; the rows' `changed`,
     `seen` and `outside_unit` are measured again on the second laying for a step whose picture, or the one before
     it, changed.
   - `digest` takes `canvas.json` in only for a build with the rule, so a lesson built without it doesn't go stale.
   - The note of section 5 compares each column's line with the lowest pixel the finish shows of the unit there.
   - Of the fixtures, the lavender balloon and the red sailboat stop layers (0.92 and 0.39 of a canvas with the
     widened rule; 0.05 and none before it). The chickadee gives the same pictures either way.
2. **The sheet and `check-text`.** `stop` and `onto` (section 6), their sentences, `lean`, the line's range in the
   checker. Tests: section 6's table on the cow's chain; a sentence that puts the sky's edge 1 in below its lowest
   point fails, and one at "most of it" passes; "reaches the bottom edge" fails on a stopped step; a planted fault
   in a stop distance is caught at the rate #173's planted faults were.

   **Built (#296, `spike/tests/test_stop_facts.py`).** As written, with these readings:
   - `make_sheet` takes build.json's `stops` and the `f<nn>` masks (`lesson_sheet` and `check` pass them). `stop`
     is the line's five distances and `next` (the covering step, its name, and `past_cover` as `covers`). On the
     cow, section 6's table comes out as written, and steps 1 to 4 carry `stop`.
   - A stopped unit's part ("as the finish shows it") is its shape cut to what its pictures show, so the sky's part
     ends at its line too. A stopped step's own things leave its part out: the v2 shape files the cow's hillside
     under its sky, so the part's family still reached the bottom edge, and "the sky reaches the bottom edge" passed.
   - `onto` is read from which part's paint is on top before the step, the pictures as shown (bare where a step
     lays paint its picture doesn't show). On the cow the far hills go about two fifths over the gold cloud
     streaks, not the sky: the clouds' last step lays its unit over the whole sky. Shares under 5% aren't said.
   - The checker: a length from the top or bottom edge of a stopped step's own paint passes at the nearest point
     of the line's range, and the area's box bottom is dropped. When the sentence is about where it stops ("stop",
     "lower edge", "down to", "ends", ...) or names its bottom, the line is the only fact it's held to; otherwise
     the step's other places count as before. Without that, a mark's middle let 16 of 42 faults moved up 1 in pass.
   - Planted faults: each of the five distances, from the top and the bottom edge in three phrasings, moved ±1 in
     and ±1/2 in, counting only moves that leave the line (as #173 counted only mutants wrong by construction): 384
     of 384 caught on the cow and the birch grove, and no false alarm on the distances as measured.
   - Without `--stops` the fixtures' sheets are what they were before, byte for byte, with `onto` added.
3. **The teaching pictures and the page.** The dashed stretch in `aids.json` and on the page; `lesson.json`'s
   `spared`; the stamp; `site_lessons.kind`. The outline, the paint map and the close-up need no code: their tests
   hold section 7's sizes.

   **Built (#297, `spike/tests/test_stop_pictures.py`).** As written, with these readings:
   - `aids.stop_path` is the stretch of the Where outline that borders paint the step lays but its picture doesn't
     show (`f<nn>` less `m<nn>`), made of the outline's own points, as open "M x y L ..." paths; a stretch under
     3% of the long side (a corner) isn't kept. `step-aids` passes the `f<nn>` masks only for a build with the rule,
     so a lesson built without it gets the same aids.json, byte for byte. On the cow, steps 1 to 4 have one, and it
     lies along build.json's line.
   - The page masks the solid outline away along the stretch and draws it dashed, on the Where picture and on the
     close-up's Before. `page2.DASHED_STOP` turns it off; off, the Where picture is a lesson's without the stretch.
   - The page's line goes under the opening, at the top of Before you start: "This lesson skips about 1 1/2
     canvases of painting that later layers would cover", to the nearest quarter of a canvas, and "under an eighth of
     a canvas" below that (the lavender balloon's 0.05). No line when nothing stopped or for an older lesson.
     `page2.SPARED_LINE` turns it off, apart from the dashed line.
   - `publish` copies each build.json row's `spared` onto its lesson.json stage and `spared_canvas` onto the lesson
     only for a build with the rule, and stamps `"pipeline": 4` then (3 otherwise). `site_lessons.kind` reads any
     whole number of 3 or more.
   - Section 7's sizes on the cow, to 1/8 in: the sky's outline 16 to 4 1/4 in, the clouds' 9 3/4 and 6 to 4 and
     4 1/4 in, the far hills' 13 3/4 to 4 in; every later step's outline, map and close-up is as it was. The sky's,
     the clouds' and the far hills' paint maps are cut to the shown paint, and the transfer outline is the same
     bytes either way.
4. **The words and the checks.** The three briefs' sentences (the lesson's, the arc's, the plan's), the finisher's,
   `packets`' record and the refusal in `check-text` and `check`, `run.md` step C. `v4_loop.py` is brought into
   step.

   **Built (#298, `spike/tests/test_words_pictures.py`).** As written, with these readings:
   - The record is `words/lesson/pictures.json`, `{"made_from", "stops"}` from build.json and `pictures`, a hash
     of the files build-steps wrote (build.json's `files`), so a change to the rule's code that moves the lines on
     the same plan and chain makes the words stale too. `packets` writes it.
     `check-text --final` copies it into `rounds.json`'s `final` as what the words were written for. `check-text`
     (every round, `--final`, the arc) refuses a folder whose record isn't the build's now; `check` fails a
     text.json holding the writer's words whose last check recorded other pictures, or that has no last check in
     the folder at all (`packets` ran again after the words, which on its own leaves the old words in text.json).
     Both say whether the pictures were since built with `--stops`, without it, or from a changed plan, chain or
     canvas, and to run `packets` and the writer again.
   - A record from before #298 (a v3.1 lesson) counts as pictures built without the rule: its words stand while
     build.json has no `stops`, so no sealed lesson goes stale.
   - `check` already held checks 1 and 2 from build.json, measured on the second laying, and carried the note of
     section 5 (`steps3.problems`, since #295); the test holds both on a fixture built with `--stops`.
   - The briefs: the lesson brief's two paragraphs (section 8) go after "Say also" in "What a step says"; the arc's
     clause joins `road`, and says to give it without a number or a side word, which the arc's check fails; the
     plan brief's sentence closes its paragraph on `behind`; the finisher's paragraph goes at the end of 8a and
     also says what still is a known problem: words that send the painter to a layer where the picture shows bare
     canvas.
   - **The run (the design's guess to watch).** The cow's v3.1 gate lesson (`output/highland-cow_skill_20261120-193553`)
     copied and built again from its chain with `--stops`, then C2 and D, the writer an Opus subagent reading
     `words/lesson/`. Before `packets`, the old words were refused by `check-text` and by `check`, which also found
     5 numbers in them that the stopped pictures no longer have (the sky "5 1/4 in tall", the sky and the hills
     reaching the bottom edge); the old steps 7 and 8 still said to leave and then fill "purple stripes", which no
     check could see. With the new words:
     - Every stopped step (1 to 4) says that its lower edge is loose and that the rest of the canvas stays bare
       until the covering step, named. Steps 1 and 4 say how far in inches ("about 3 1/2 in from the top edge",
       "about 5 1/4 in"); steps 2 and 3, the clouds, say "keep to the sky's loose lower edge" with no number.
     - Steps 7 and 8 are written to bare canvas: "leave stripes of bare canvas between the bands: step 8 fills
       them", "fill the bare stripes between the bands", "no bare canvas is left on the hillside". No step names
       purple.
     - The rounds: round 1 sent back 12 of 52 claims; 5 were the brief's own sentence ("the canvas below it stays
       bare" fails: the tool looks for a part called "it stays bare"), so the brief now gives the sentence without
       a side word, and so does the sheet's stop fact ("The rest of the canvas stays bare", which said "Below it")
       and the arc brief's `end` line. Round 2 sent nothing. `--final` took out 1 sentence (step 1's "edge to edge", which the tool
       read as about "The cow's shadow side", a misreading that came before this build). The arc passed its round
       first time (0 sent back, 16 back lines), and its road says "the early layers stop short where the next one
       will cover them, so some bare canvas is expected for a while". `check` then printed no failures.
     - Not run: the finisher, the seal, the student test and the graders (build 5).
   - `run.md` C1 says when to pass `--stops` and that no other tool takes it; C7 builds again the same way; D1 says
     what `packets` records. `v4_loop.py run --stops` builds with the rule, and keeps the choice in its state so a
     run that goes on after a stop can't build the other way.
5. **One whole lesson, the cow, for the owner:** go, change or stop. This draft is then corrected by what it
   showed.
6. **The gate** (section 12), from the branch.
7. **Then** merge, turn `--stops` on by default, stamp the version, write the changelog entry, fold the as-built
   facts into `pipeline-v3.md` (sections 8 to 10) so one file still describes the run, and unblock #287 to be
   closed. Rerunning the site's lessons is the owner's call, as it was after v3.1. A lesson whose folder still has
   its chain needs no render for it: a build, new words and a seal.

**The guess to watch in step 4** is the writer. In the spike it was sent only the changed steps and a line written
by hand. Here it is sent the whole lesson and two new facts among many.

## 14. Known risks

- **No measured win.** The yardstick can't see painting skipped, and the student test was a little lower on
  average (−0.21 ± 0.21). The gate can fail on noise alone; that is why it allows a third carry.
- **Three pictures, one kind.** A sky, land rising from the bottom edge, a subject on the land. A cover that comes
  in from a side or from the top (a wall, a tree canopy, a cliff) stops nothing, by the rule as adopted. Whether it
  should is the owner's to say after a lesson shows one.
- **The stages and the chain decide** (section 9). The rule was fitted to two plans' stages after looking, and
  then widened after one more (the 2.2.0 cow), whose chain painted sky where the spike's had painted hills.
- **Words with no number aren't checked** (section 6). "Fill the purple gaps" passes on bare canvas. The writer has
  the picture and the `onto` fact, and the finisher is the only backstop.
- **A stopped layer's edge is the model's whole layer, cut.** Where the layer under the cover was drawn differently
  from the part that shows (a render paints back "what is behind" loosely), the inch above the line can look unlike
  the rest. It didn't on the three.
- **Every stopped layer in a lesson wobbles the same way,** because the wobble has one seed. The cow's sky and
  hills lines run 1 1/4 to 2 in apart, and no reader named it.
- **The dashed outline and the page's one line** have been seen by nobody.
- **A painter may want the whole layer.** Some teachers tone the whole canvas first so no white shows through
  later paint. The rule leaves white under the next layer, and a thin acrylic coat over white is brighter than
  one over a sky. #252 would show it.

## Not in this design

Building it. Changing the rule's numbers. Soft covers drawn by a model, and a chain that erases to bare canvas under
a line. Hiding a layer under a subject inside it (dropped in #289). Covers from a side or the top. A check on words
that have no number or side (v3.1's open item on the sheet's pieces of a thing covers the same ground). Rerunning
the site's lessons.
