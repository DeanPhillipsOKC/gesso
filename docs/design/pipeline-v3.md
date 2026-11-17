# Pipeline v3: plan first, erase the finish back one stage at a time, write from what was measured

**A draft (2026-11-17, #210). Not approved, and not the pipeline.** v2 (`pipeline-v2.md`) is the pipeline until the
gate in section 13 passes and the owner agrees. This file is written from the spikes that ended in adopt
(`pipeline-v3-plan.md`, Order, step 5). Each section says what is **proven** (a spike ran it and its write-up has the
numbers), what is a **guess** (this draft's own joining of the pieces, run by nobody yet), and what is **open**.

The three adopted spikes were each graded alone, against v2, by Claude's blind graders. They have never been run
together. The first job of this design is one combined lesson that shows whether they fit (section 12).

**The combined lesson ran on the highland cow (2026-11-17, `docs/spikes/v3-combined.md`), and the owner said go**
("Go, fix those two things first"). Next: the same on two more bench pictures, with blind graders against v2
(section 12, step 3; #214). The owner also said about 29 cents of renders a lesson is fine. What it showed, against this draft's guesses, and what changed because of it:

- **Units are smaller than section 6 says (changed on the owner's call).** A block-in is a unit by itself, and so
  is a step whose paints its unit has all used already. Each gets its own render, so no block-in is a slab cut from
  the next step's picture and no two steps share pixels by paint. The cow has 17 units, not 11: 16 renders, about
  29 cents and 3 1/2 minutes of chain, where sections 6 and 14 say 20 cents and 2 1/2 minutes.

- **Taking a thing back a stage works** (section 6, the main guess), on the coat, the face and the tall grass. The
  request has to say what is left ("a smooth first coat"), not only what goes.
- **A chain with no boxes holds going backward,** with two stray changes kept (a few bush rows, a horn tip).
- **Shapes from changes are enough for v2's teaching pictures and #173's sheet** (section 9): all were made with
  no outline and no change to those tools.
- **Smaller units did remove the big jumps** (section 8). In the first lesson a unit's last step still brought
  more than its words and two steps that shared a paint couldn't be told apart; the units rule above fixed both.
  Inside a unit that still has several steps, each pixel goes to the step whose paint it is nearest.
- **A step's `after` line can't be given to a render as it is** (section 6): it describes the whole canvas. The
  plan needs a line a thing a stage, a name for a thing's first stage, and a name a unit (section 5).
- **Not solved:** 17 paints against a target of 10, and four of them fitted to colors far from their names.

**The same was then made on the sleeping cat and the birch grove, and the three were graded blind against v2
(2026-11-17, #214, `docs/spikes/v3-combined-round2.md`). Verdict: adopt.** Claude's graders preferred the combined
lesson on the cow and the birch grove (both graders each) and split on the cat (a tie); none preferred v2. Next is
section 12, step 4. What it showed, and what this draft changes because of it:

- **No ghost, tiled patch or hard box of v2's kind, on any of the three.** That is what the graders preferred it
  for; v2 had one on every picture. Smaller faults of that family remain: a pale patch on the cat's sill, and
  things a step early or late (the cat's whiskers, the birch grove's sun).
- **The block-in is the weakest step (section 6, not solved).** Erased only by "remove the thing", it is whatever
  the "back" render before it left: the cat's blanket arrives knitted, the cat with ears and eyes, the rock
  shaded. The steps after it then change almost nothing. No grader gave paintable or agree more than 3.
- **A "behind" request has to say what stays (section 6, changed).** On the birch grove, removing the bushes
  repainted the far woods, and removing the leaves took the rock. Each needed a sentence naming what stays.
- **With no box, a change far from the thing is kept (section 6, open).** Step 5's look is the only catch today.
- **The plan must mark its block-ins, and may need another name for a thing in a request (section 5).** v2's
  "flat" isn't a block-in (the birch grove's dark leaf dabs), and a name like "The sky and trees through the
  window" misleads a render.
- **A returning unit's shape was too small for the sheet (section 9):** it is only where the unit is still on top
  at the end. The sheet should measure what the unit changed.
- **Cost:** 14 to 18 renders, 25 to 33 cents and 3 to 4 minutes a lesson; the birch grove made 10 renders again.

## 1. Why change

v2 renders the finished painting once and cuts every step picture from it inside outlines. It stopped improving:
known problems per lesson stayed at 2 to 7 from POC 1.0.0 to 1.12.1, and each fix was followed by the same fault in
a new form (`pipeline-v3-plan.md`, Context). The owner's weakest parts of a v2 lesson are the step pictures and the
teaching and text. What the spikes found under those:

- **The outlines decide the lesson.** v2 lists parts by what outlines well, then fits steps to the parts. A cow's
  face that has no outline gets no step, and arrives on a step that names a gold.
- **A step picture is the finish with things cut away,** so what was hidden is invented by fill rules. That is where
  the blotches, tiled patterns, hard boxes and pale holes come from.
- **The words are written before anyone compares them with the picture,** and nothing checks a side or a size.

## 2. The idea

1. **The plan comes first, and it is a painter's.** A writer who sees no outline writes the lesson as a teacher
   would: the things, the stages, and what each step lays down. The pictures are made to fit it.
2. **The finish is still rendered once.** Then the image model erases it backward, one stage of the plan at a time,
   each render made from the last. The erased pictures themselves are what the lesson's stages end on.
3. **A guard with no outline.** Of each render only what changed by a lot is kept. Everything else stays as it was,
   so nothing moves between steps and the last picture is the finish.
4. **A thing's shape is what its render changed.** No outline model runs. The teaching pictures, the paints and the
   fact sheet are measured from those changes.
5. **The words are written from the before and after pictures and a measured fact sheet,** one writer a stage, in
   parallel, and a checker holds every number and side to the sheet.

Kept from v2: the finish is the one picture every step ends on, so the painting is the painter's photo as closely
as v2's is. The forward build (#207), which has no finish, was parked for wandering from the photo and for steps
that looked the same (`docs/decisions.md`, 2026-11-17).

## 3. What's proven, and what isn't

| Piece | From | Proven | Not known |
|---|---|---|---|
| A painter's plan written before any outline | #172, 3 pictures | 22 to 24 steps where v2 planned 14 to 16, the extra ones on the subject (the cow's nose, nostrils and eye, mouth). Two writers of one picture agree about as well as two v2 runs. Graders preferred it on 2 of 3 and split on the third. 3.5 to 4.2 minutes, no render. | Whether it can be written from the photo alone. The writers saw the finish. |
| Erasing backward, chained, guarded by the change | #204, 3 pictures | 21 kept renders. No step changes a pixel outside what its thing adds, and the last picture is the finish (both 0.00%). Graders preferred it on all 3, both graders each. | It ran on **v2's plan**, with one render a thing and v2's loose boxes. |
| Words from a fact sheet, with before and after pictures | #173, 4 pictures | Graders preferred the words on 3 of 4 and called the fourth a toss-up. All 26 stage writers ran in 2 1/2 minutes. A fault planted in a Where line is caught 97 to 100% of the time. | It ran on **v2's pictures and outlines**. The edges were small: the pictures were the same on both sides. |
| A chain with no boxes | #207 (parked) | `diff_mask` with no box held on 11 renders of the cow, forward: nothing already painted moved. | Backward, where the change is the whole thing going, not a thing arriving. |
| One render for each run of steps in a stage | #207 (parked) | The units rule works on the plan-first cow: 11 units from 24 steps. | Erasing by those units. See section 6. |
| One engine | #176 | Same files byte for byte, tool time 60% less on the fixtures. | Its verdict is open, waiting on a run trace. Not part of this design until it has one. |

## 4. The run, start to end

| # | What | Who | Writes | v2 |
|---|---|---|---|---|
| 0 | Set up, check the photo, fit the canvas, beginner version | Claude + tools | `00_*.png`, `notes.json` | as is |
| 1 | Reference and finish | filters + 1 render | `00_reference.png`, `99_finish.png` | as is |
| 2 | The painter's plan | a writer in a fresh context | `plan.json`, version 3: things, paints, stages, steps | new (#172) |
| 3 | Check the plan | `plan-check` | problems, each saying what to change | new |
| 4 | Erase backward | `erase`: one low render a unit, chained | `chain/P<nn>.png`, `chain/D<nn>.png` | new (#204) |
| 5 | Look at the chain once; ask again for a unit that failed | Claude | at most 2 tries a unit | new |
| 6 | Fit the paints, then the recipes | `paints`, `mix` | `plan.json`: each paint's color; recipes | changes |
| 7 | Step pictures | `build-steps` | `NN_<id>.png` | changes |
| 8 | Teaching pictures and the fact sheet | `step-aids`, `sheet` | `aids/`, `facts.json` | changes |
| 9 | Draft the lines, then one writer a stage, in parallel | `draft-text`, then writers | `text.json` | changes (#173) |
| 10 | Check the words against the sheet; one round of fixes | `check-text`, the same writers | `text.json` | new (#173) |
| 11 | Checks | `check` | problems | changes |
| 12 | Diagrams, notes, seal, publish | as v2 | the sealed lesson | as is |

What goes: listing parts with boxes and points, `outline` and its fix rounds, the background render, `part-colors`,
and the text review in a fresh context (the checker is in its place, as in #173's run).

## 5. The plan file (`plan.json`, version 3)

The painter's plan from #172 (`spike/experiments/v3_plan_first_painter.md` is its brief), with three additions.

- **things:** `id`, `name`, `element` (the element technique it follows), `why`, and `left_out`. No boxes, no points.
- **paints:** `name`, `looks` (in words), `things`.
- **stages**, each with **steps:** `id`, `name`, `lays` (one entry a thing: `thing`, `what`), `paints` (1 to 3
  names), `stroke` (a card's id), `brush`, `blend`, `after` (what the canvas shows when the step is done), `why`.

A step may lay paint on more than one thing when that is one move. These were 4 of 69 steps in the three plans
fitted, so they are allowed, not the point.

**Added by this draft (guesses):**

- **`behind` on every thing:** the things already painted that it sits on, or none for bare canvas. #204 worked
  this out from boxes (`is_bare`), and its redo sentence names what is behind. A plan with no boxes has to say it.
- **`color` on every paint:** a rough hex for the name. The paints are fitted from it in step 6. In #207 these
  were written by hand.
- **`plan_version: 3`.**

**The rules the plan is held to** are v2's and the owner's, unchanged: paint-along on a white canvas, back to front,
12 to 24 steps in 4 to 9 stages, one move a step, technique from the element files and the cards, texture never in
one step.

**`plan-check` (step 3)** is #172's `painter-check` plus:

- **At most 10 mixes.** The cow's plan names 17 paints. `docs/decisions.md` has 10 as a target, with lighter and
  darker versions not counted and two paints a painter can tell apart never merged. **Open:** the writer isn't
  held to it today, and nothing counts a plan's mixes before the paints are fitted.
- **A mix whose uses are far apart.** A painter's order pulls a mix's uses apart (the cow's golden ochre is mixed
  in step 1 and wanted in steps 3, 14, 15 and 24). The check lists them so the words can say "mix it again".
- **A step that changes nothing can't be told from the plan.** That is checked on the pictures (section 9).

## 6. The chain (`erase`)

**Units.** One render for each run of steps in one stage on the same thing (`units` in
`spike/experiments/v4_forward.py`). A thing the plan comes back to in a later stage is a new unit. The cow's plan
gives 11:

sky; clouds; mountains; loch; hillside and meadow; bushes; the cow's shape; the horns; the cow's coat; the cow's
face; the tall grass.

**Backward, chained.** The last unit is erased first, each render made from the last picture. P[u] is the picture
with every unit after u erased. P[last] is the finish.

**What a render is asked for** depends on what the unit is on:

- **A thing on bare canvas** (`behind` is empty): remove it and leave bare white canvas. Canvas once bare stays bare.
- **A thing with things behind it:** remove it and paint what is behind, named from `behind` ("Behind them there is
  only this: ..."). #204 found that "continue what is around" invites new things, and naming what is behind stops
  it. So v3 names it from the first try, not only on a redo. **It also names what stays** (#214): a render that
  removes the bushes will otherwise repaint the woods behind them.
- **A later stage of a thing already there** (the cow's coat, its face, the tall grass over the meadow): take the
  thing back to how the plan's `after` describes it before this stage. The request is the `after` line of the step
  before the unit's first.

**The third kind is this draft's main guess.** #204 erased whole things only. Its write-up names this as the next
thing to try ("a chain that erases a thing's detail before the thing ... is the same tool pointed one level down").
S4 (#169) tried rendered stages inside a part, with separate renders and no guard of this kind, and the owner
preferred v2. If it fails here too, the fallback is #204 as it ran: units that come back to a thing are joined into
one, and the steps inside are v2's cuts.

**The guard.** Of each render keep only the patches that changed by a lot (`diff_mask` in
`spike/experiments/v3_whole_stages.py`: every patch that changed by 9 Lab units or more and holds a pixel that
changed by 20 or more). D[u] is that change. Every other pixel stays as it was.

- #204 also required the strong change to start inside the plan's loose box. v3's plan has no box. **Guess:** the
  guard holds without one, as it did going forward in #207. If a render changes something far from its thing, the
  place to catch it is step 5.
- The guard's four numbers were set on three pictures. They need the bench.

**Step 5: look once.** Claude reads the chain sheet. A unit is asked for again, at most twice, when it painted a
new thing where the old one was, or left the thing standing. Known and not solved: gpt-image won't fully remove
faint, soft things on a sky (the cow's clouds 49% unchanged, the birch grove's far trunks 44%). What is left shows
in step 1. **Open:** a second edit model for those (it needs a host and a key), or a plan that folds a faint thing
into what it sits on.

**Cost and time.** 1.8 cents and about 14 seconds a render in #204, one after another. A plan-first plan makes
about 11 units where v2's plan made 6 to 8: about 20 cents and 2 1/2 minutes a lesson, where v2 spends about
2 cents on one background render. The owner opened "more or dearer renders (cost stays low)" to v3 spikes; whether
20 cents a lesson is low enough for the pipeline is the owner's call at the gate.

## 7. Paints (`paints`, then `mix`)

v2 measures each part's colors inside its outline and Claude names them. v3 turns that around: the plan names the
paints, and each is fitted to the finish.

- For each unit, the pixels of its change go to the nearest of the unit's paints (starting from each paint's
  `color`), and each paint moves to the middle of its pixels (`fit_paints` in `v4_forward.py`). **Guess:** this ran
  on one picture, per unit. A paint used by several units needs one color for the lesson; the draft takes it from
  the unit that lays the most of it.
- A paint with no pixels near it is reported: the plan names a color the finish doesn't have. #172 met this (no
  gray darker than the cat's coat, no paint as pale as the plan's "Pale gold"). The plan is changed, not the finish.
- Recipes are computed as in v2 (`mix`, Mixbox), and every step lists its own paints and recipes.

## 8. Step pictures (`build-steps`)

For each unit, in painting order, from P[u] and D[u]:

- **The unit's last step** lays all of D[u]. The picture after it is P[u] exactly.
- **An earlier step** is v2's cut inside the change: a flat coat for a block-in, or a pass that shows the pixels
  nearest that step's paints. Flat coats go on the solid core of the change (`core_mask`), so a coat doesn't cover
  a thing's reflection or the ground under fallen leaves.

Because units are smaller than things, fewer steps are cut this way: on the cow's plan 4 of 11 units have one
step, and no unit has more than 5. The big jumps the graders marked down in #204 (flat to finished in a step, a
face on a step that names a gold) were inside units that were whole things. **Guess:** smaller units remove most of
them. The combined lesson is the test.

**The three checks** (`pipeline-v3-plan.md`), run on every lesson:

1. The last step picture is the finish (a pixel counts when it is more than 24 levels off).
2. No step changes a pixel outside what its unit adds.
3. Every pixel a step lays is within a set distance of a paint that step names. **Not measured by any spike.** It
   starts as a number that is reported, not a failure.

Two more, from faults the graders named:

4. **A step that changes almost nothing** (under 0.2% of the canvas, and not a small thing such as a nostril) is
   reported.
5. **A first step that shows too much:** step 1's picture is compared with the plan's first `after`. This one is
   Claude's eye at step 5, not a measure.

## 9. Teaching pictures and the fact sheet

v2 draws these from outlines. In v3 a step's area is what the step laid, and a thing's shape is the core of its
unit's change. **All of this section is a guess:** no spike measured a Where line or a sheet from a change.

- **Where, close-up, paint map, Where in words:** as v2 (`pipeline-v2.md`, section 10), from the step's area.
- **Transfer outline:** the edge of the core of each unit that starts a thing in front.
- **The fact sheet** (`sheet`): what #173 built, measured from the step pictures and the units' changes: each
  thing's box, size and middle in inches, the edges it reaches, which side of every other thing it is on, and for
  each step its marks, what it adds, and its paints.
- **Known trouble:** a change is often bigger than the thing (it takes its reflection or its shadow with it; the
  IoU with v2's outlines ran from 0.17 to 0.88 in #204). So places are measured on the core, not the whole change.
- **The sheet's own fixes,** from #173: halves and middles measured on a thing's main body; one size for a step's
  area, not two that can disagree; facts for the pieces of a thing.

## 10. Words

As #173 ran it:

1. `draft-text` drafts the lines that are data (paints, brush, stroke, where, drying) from the plan and the cards.
2. **One writer a stage, in parallel,** each in a fresh context with: its steps' before and after pictures side by
   side, the drafted lines, the sheet's rows as plain sentences, the light, the step list, the photo and the finish.
3. **Added here (guess):** each step's `after` line from the plan, as what the step is meant to do. The writer
   describes the picture, and says so where the picture and the `after` disagree.
4. `check-text` checks every number and side in the writer's words against the sheet, strictly. A stage that fails
   goes back to its writer once. A sentence that still fails is taken out.

The writer must see the pictures: most of what the graders credited in #173 came from them (card lines rewritten
to match the picture, extras named), not from the numbers.

**Not solved:** the stroke cards' own words, where most teaching faults come from (a load word such as "creamy"
that the step never explains). That is #175.

## 11. What goes, and what stays

**Goes from the run** (the code stays until the gate passes, as v1's did):

- parts with boxes and points, `outline`, the outline model, and the fix rounds;
- what's-behind fills: rims, strays, row fills, borrowed texture, and the background render;
- `part-colors` and paints named after measuring;
- the text review in a fresh context.

**Stays as it is:** photo check, canvas fit, the beginner version, the reference and the finish render; the element
techniques, stroke cards and research; Mixbox recipes; inches, never percent; construction diagrams; notes, seal,
publish, the history and the site; hands-off runs only on the site; lessons made on Opus.

**`build_steps.py` holds about 34 tuned numbers,** most named after one past failure. v3's step pictures need the
guard's four and the core's one.

## 12. Build order

1. **One combined lesson, by experiment code** (#210): the highland cow's frozen finish, its plan-first plan, a
   backward chain by the units of section 6, paints fitted, step pictures, a fact sheet from the changes, words
   from stage writers. A step sheet beside v2's and #204's.
2. **The owner looks at that one lesson:** go, change, or stop. This draft is then corrected by what it showed.
3. On a go: the same on two more bench pictures, with blind graders against v2, to see it isn't the cow alone.
   **Done (#214): adopt.** Preferred on two of three pictures, a tie on the third, a loss on none.
4. Build it into `/paint-lesson` behind `plan_version: 3`, tool by tool, v2 untouched beside it.
5. The gate.

## 13. The gate

From `pipeline-v3-plan.md`, with the 2026-11-17 change to who grades:

- v3 beats v2 on the blind A/B on the bench (Claude's graders: most pictures, a clear loss on none);
- known problems per lesson drop below 2;
- the run trace is shorter;
- **the owner grades one finished lesson** and agrees.

Then the site's lessons are rerun from their photos, and v2 is removed.

## 14. Known risks

- **Stages inside a thing** (section 6). The owner preferred v2 over rendered stages once.
- **No outlines** (section 9). Every Where line, close-up and sheet so far was measured from one.
- **The plan asks for what the finish doesn't have.** A shade the finish has no color for, a rim light the locks
  already brought. Erasing by stage may give the plan its order back; it can't add a color.
- **Faint things won't erase,** so a first step can still show too much.
- **More renders:** 25 to 33 cents and 3 to 4 minutes of chain a lesson, one after another (#214), and more when a
  unit is asked again.
- **Block-ins that arrive finished,** and the near-empty steps after them (#214).
- **Claude's graders are not the owner.** Every adopt this draft rests on is Claude's grade. On S4 Claude liked the
  stages and the owner preferred v2.
- **Every spike score was 2 to 4 out of 5.** Each adopted piece was the better of two flawed lessons, not a good
  one.
