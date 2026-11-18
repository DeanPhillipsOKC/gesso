# Pipeline v3: plan first, erase the finish back one stage at a time, write from what was measured

**The gate passed (2026-11-18, owner's call; `docs/decisions.md`): v3 replaces v2.** Until `/paint-lesson` runs v3
by default and v2 is removed, `--v3` still chooses it. Written as a draft (2026-11-17, #210), before the gate. This file is written from the spikes that ended in adopt
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

**The block-in was then tried four ways on the same three pictures (2026-11-18, #217,
`docs/spikes/v3-block-in.md`). Verdict: adopt the fourth, on one clear win and two ties. The grading rule asks
for most pictures; the owner said "Adopt stands" on 2026-11-18** (both of the cat's graders preferred it; the cow's split; the birch
grove's, where two steps of a small rock changed, said "none"; no grader chose #214's lesson). What this draft
changes because of it:

- **A block-in is made by its own render, asked for as one flat coat (section 6, changed).** The request that
  leaves it names its paint, says it is one color from edge to edge, and lists what the plan paints on the thing
  later. A second render for the block-in gave the same picture for one render more; a flat fill gave a slab.
- **Every "back" request lists what isn't painted yet (section 6, changed).** That took the cat's ears and eyes
  off its earlier steps and gave the blanket's stitches and the cat's fur their own steps.
- **A "back" render is kept over the whole thing, not only where it changed by a lot (section 6, changed).** The
  guard threw away a render that took the blanket's knit off, and kept a flat coat only in patches.
- **The step after a block-in is now the big jump (section 8, not solved).** It brings the thing's brush texture
  on a step that names one shading paint; it was among every cat and cow grader's worst steps of the new lessons.
- **Cost:** none. The same renders, asked differently.

**The requests were then made to name what stays, and two checks were tried (2026-11-18, #218,
`docs/spikes/v3-stays.md`).** What this draft changes because of it:

- **A "behind" and a "back" request list every other thing already painted, as what stays (section 6, changed).**
  The birch grove's chain, made again with no sentence written by hand, held: 18 renders, none made again.
- **No measure tells a stray change from the thing's own (section 6, not solved by measure).** Five were tried.
  Step 5 is now a checker in a fresh context with one look picture a unit and the list of what stays. Blind, it
  caught two of three known strays and found two more in #214's kept chain; it missed the cow's tall grass.
- **`erase` reports a thing left standing (section 6, new).** It sees a whole thing left, not a faint one in part.

**The build into `/paint-lesson` has started (#219, section 12, step 4).** Built so far, beside v2 and chosen by
`"plan_version": 3`: the plan file, its brief and `plan-check` (section 5); `erase` and the checker's brief (section 6); `paints`, `build-steps` and the bridge to `step-aids`,
`mix` and `draft-text` (sections 7 to 9); the fact sheet, the stage writers, `check-text`, `check`, the seal and
the run's instructions (sections 10 and 11; `.claude/skills/paint-lesson/v3/run.md`, chosen by `--v3`). **The first whole lesson (2026-11-18, #219's acceptance):** `floating-island_skill_20261118-044513`, from an
AI-made picture that isn't on the bench, sealed hands-off. 24 steps in 7 stages, 19 units, 10 mixes. The chain: 18
units, 19 renders (36 cents, 4 minutes); `erase` asked again by itself once, for clouds left standing; the checker
marked none of 18. The three checks read 0, 0 and a median of 12.4 Lab units. The words: 171 claims, 14 failed, one
fix round, one sentence taken out. 52 cents of renders in all, and about 35 minutes from the photo to the seal.
What it showed:

- **The paint fit read what was round a small thing, not the thing** (section 7, fixed): the moon's pale gold was
  fitted to the sky's blue. A pixel further than 30 Lab units from a paint no longer counts as that paint's.
  Seven of 20 paints were still fitted 26 to 36 units from the plan's rough color, and are on the page as known
  problems.
- **The run can't be one subagent** (the skill, fixed): a subagent can't start the helpers.
- **The sheet measures a thing too wide when a later unit lays on two things** (section 9, not fixed): the
  island's place took in the doorway, because the stone's shading is one unit on both and is filed under the
  island. It cost one sentence a writer had right.
- **A plan's `after` can disagree with its own `behind`** (section 5, not fixed): the sea was given the sky as
  what is behind it, so the sky runs to the bottom edge, and the first steps' `after` lines say the bottom third is
  bare. The writers wrote to the pictures.
- **Steps that change little remain** (section 14): the lighter blossom dabs and the water's streaks. The spikes' three plans, with what was
written by hand folded in, are `spike/tests/fixtures/plans3/`. A step v2's cutter showed flat is a block-in there
only when it is one by the plan's rule, so the cow has 14 units and the birch grove 17, where the spikes' chains
had 17 and 19 (the cow's clouds, bushes and nose and the birch grove's canopy and bushes start with dabs or
streaks, not a flat shape). The sleeping cat's 15 are the spike's.

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

The painter's plan from #172 (`spike/experiments/v3_plan_first_painter.md` was its brief), with additions.

- **things:** `id`, `name`, `element` (the element technique it follows), `why`, and `left_out`. No boxes, no points.
- **paints:** `name`, `looks` (in words), `things`.
- **stages**, each with **steps:** `id`, `name`, `lays` (one entry a thing: `thing`, `what`), `paints` (1 to 3
  names), `stroke` (a card's id), `brush`, `blend`, `after` (what the canvas shows when the step is done), `why`.

A step may lay paint on more than one thing when that is one move. These were 4 of 69 steps in the three plans
fitted, so they are allowed, not the point.

**What the plan carries beside #172's, as built (#219; `spike/plan3.py`, `tools.py plan-check`).** #210 and #214
wrote these by hand beside the plan (`spike/experiments/v3_combined_plan.json`). Now the writer writes them, from
the brief in `.claude/skills/paint-lesson/v3/plan-brief.md`:

- **`plan_version: 3`,** and v2's header: `photo`, `technique`, `technique_why`, `palette`.
- **`behind` on every thing:** the things already painted that it sits on, or `[]` for bare canvas. #204 worked
  this out from boxes (`is_bare`). Each must be first painted before the thing is.
- **`plain` on a thing painted in more than one unit:** how it looks after its first ("the plain gray cat shape").
  A request that keeps the thing while it is still plain calls it that (`early` in the spikes).
- **`called` on a thing (optional):** a name for it in a request, when its own would mislead a render ("The sky
  and trees through the window", when the trees are a thing of their own).
- **`color` on every paint:** a rough hex for the name. The paints are fitted from it in step 6.
- **`of` on a paint (optional):** it is a lighter or darker version of the paint named, and isn't counted as a mix.
  `plan-check` holds it to that by the rough colors: the same hue within 40 degrees (a gray stays a gray), and
  lighter or darker by 4 L or more (`plan3.HUE`, `LIGHTER`, starting values).
- **`block_in: true` on a step:** the thing's first coat, as one flat color. It must be the first step on each
  thing it lays, not a blend, and each thing needs a later step. It is a unit by itself. v2's "flat" isn't this (the birch grove's dark
  leaf dabs, the cow's nose): a block-in is what the request of #217 describes, a whole thing as a paper-flat shape.
- **`unit` on the first step of a unit** that isn't the start of one thing: a name for what the unit adds, as the
  page says it ("The cow's shaggy coat"). A unit that starts one thing takes the thing's id and name.

**Units** (`plan3.units`) are worked out from the plan, not written: section 6. A blend is a unit by itself, as a
block-in is: colors worked wet into each other can't be cut apart by paint. `plan-check` prints them, with
what each render will be asked for, so the writer sees which steps need a `unit` name.

**The rules the plan is held to** are v2's and the owner's, unchanged: paint-along on a white canvas, back to front,
12 to 24 steps in 4 to 9 stages, one move a step, technique from the element files and the cards, texture never in
one step.

**`plan-check` (step 3)** is #172's `painter-check` (ids, names, `lays`, paints, strokes, the technique's ranges),
the fields above, and:

- **A step's stroke is one its thing's element lists,** and for a step that crosses things, one every one of
  their elements lists. The brief said so and nothing checked it. All 69 steps of the three spike plans pass.
- **At most 10 mixes, as v2 holds it** (`docs/decisions.md`, 2026-11-12). Paints with `of` aren't counted. Above
  the technique's `max_mixes`, the plan fails while two counted paints are within Delta E 12 by their rough
  `color` (`plan3.CLOSE`), naming the closest pair: use one for both, or mark one `of` the other. With none that
  close it passes, and `plan-check` says so (`over_target`). The three spike plans (17, 22 and 13 paints, written
  before any count) all fail this, each with a close pair. **Not known:** whether a writer held to it lands near
  10, and whether rough colors are good enough to judge "close" before the paints are fitted.
- **A mix whose uses are far apart** is listed, not failed (`mix_again`): a paint used again three or more steps
  after its last use (`plan3.APART`, a starting value). A painter's order pulls a mix's uses apart (the cow's
  golden ochre is mixed in step 1 and wanted in steps 3, 14, 15 and 24), and the words say "mix it again".
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
  it. So v3 names it from the first try, not only on a redo. **It also names what stays** (#214, built in #218):
  all of the thing goes, "the dark, the faint and the small ones too", then every other thing already painted, by
  name, stays exactly as it is wherever it can be seen, and nothing new is added anywhere. A render that removes
  the bushes will otherwise repaint the woods behind them.
- **A later stage of a thing already there** (the cow's coat, its face, the tall grass over the meadow): take the
  thing back to how the plan's `after` describes it before this stage. The request is the `after` line of the step
  before the unit's first. It ends with the same list of what stays (#218): "Nothing else in the painting is
  touched."

**What a block-in is made from (#217).** A block-in is the first unit of a thing in front, and its picture is
what the "back" render of the thing's next unit leaves. So that request says what is left, from the plan: the
block-in's paint by name and look, "the same from edge to edge, like a shape cut from colored paper", no shading,
fold, texture, line or detail, and "None of this is painted yet, so none of it may show:" with the `what` of every
later `lays` on the thing. Every later "back" request on the thing carries the same list, from its own unit on. No
second render and no flat fill: both were tried (`docs/spikes/v3-block-in.md`). **Open:** a paper-flat coat leaves
the thing's whole brush texture to the next step; a coat brushed in one color wasn't tried. A step that takes a
thing's texture off (the blanket's knit) needed "what is left has no texture" written by hand.

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
  place to catch it is step 5. **#218 tried to catch it by measure and couldn't:** pieces apart from the main one,
  weak pieces, the paint that was there, and a change inside another unit's core all score good renders as high as
  the known bad ones. A stray is often one piece with the thing, in its colors, on things the request names as
  behind; only its size differs, and the plan gives no size.
- **A "back" render is kept over the whole thing (#217).** Keeping only the strong change is right for a thing
  that goes and wrong for a layer that comes off: a flat coat is close in color to the brushwork it replaces, so
  the guard kept it in patches, and it dropped a smooth blanket for a knitted one whole. The thing's shape is the
  solid core of what its block-in unit adds, holes filled, plus the render's strong change. That shape is known
  only once the chain has erased the thing, so `erase` lays each stage's render over it in a second pass, with no
  new render. **Known cost:** the thing is drawn again at every stage, so its outline and brushwork can shift
  between steps (the birch grove's rock narrows on its shade step).
- The guard's four numbers were set on three pictures. They need the bench.

**Step 5: look once (changed by #218).** Not Claude reading the chain sheet, where a cell is 256 pixels wide: a
checker in a fresh context reads one look a unit (before, after, the change tinted) with what the unit was asked
for and the list of what stays (`looks` in `v3_combined.py`, `v3_stays_checker.md`). A unit is asked for again, at
most twice, when the checker marks a stray change or a thing left standing, or when `erase` reports the thing left
standing (2% of the canvas or more beside the hole that still looks like what went). Read blind over 77 renders,
the checker marked two of three known strays, the one known thing left, and nine of 73 others, of which at least
two were real strays in #214's kept chain. **Open:** it missed the cow's bush rows, drawn again when the tall
grass came off; the hillside and the meadow are one unit, so nothing here can tell that change from the grass's. Known and not solved: gpt-image won't fully remove
faint, soft things on a sky (the cow's clouds 49% unchanged, the birch grove's far trunks 44%). What is left shows
in step 1. **Open:** a second edit model for those (it needs a host and a key), or a plan that folds a faint thing
into what it sits on.

**As built (#219; `spike/erase3.py`, `tools.py erase`, `.claude/skills/paint-lesson/v3/chain-check.md`).**

- **The requests of #217 and #218 are joined here for the first time.** Every request names what stays (#218).
  Every "back" request says "take all of that layer off" and lists what isn't painted yet from its own unit on
  (#217). The first unit to come back to a block-in also says what a block-in is. No sentence is written by hand.
  **Run by nobody yet:** the two spikes each ran with the other's wording off.
- **A thing's name in a request.** `called` when the plan gives one. A thing that has had only its first unit and
  has more to come is named by its `plain` name, in every kind of request. The spikes did this only where a thing
  went, and by a hand-kept list.
- **Kept over the whole thing, from the same renders.** The chain is laid twice. The first laying is the guard's
  alone, and finds each blocked-in thing's core when the chain erases it. The second lays every "back" render on
  such a thing over that core, holes filled, as well as where it changed by a lot. #217 rendered each of a thing's
  stages again, from the picture the kept-whole stage above it left. Here each render is made from the first
  laying's picture, where a flat coat may still be in patches. **Not graded.** Checked without a render: the
  sleeping cat's stored renders of #214 give #214's chain pixel for pixel from the first laying, and #217's
  renders of the blanket and the cat give a flat blanket and a flat cat from the second.
- **`erase` asks again by itself for a thing left standing** (2% of the canvas, `LEFT`), on the spot, before the
  units before it are rendered from its picture. So a miss costs one render, not a render for every earlier unit.
- **What is measured on which laying.** A thing left standing, and so `erase`'s own asking again, is measured on
  the first laying, where each render was made. The pictures kept, `erased_share` and the checker's looks are the
  second laying's. A unit between a block-in and a later stage of its thing (the cow's horns, between its block-in
  and its coat) is rendered from the first laying's picture and laid on the second's. **No test or spike covers
  how much those differ on a real chain.**
- **A run that stops partway loses nothing.** Each try is written to `chain/tries.json` before its render and
  ticked off after, so the next run asks for the same tries and pays for none twice. `chain.json` counts every
  render paid for, the tries thrown away too. A chain is refused by the later tools when the finish or any
  request has changed since it was made.
- **Asking again says why:** `--redo 8:stray` or `8:left`, at most twice a unit. Each adds a sentence. For a
  layer left on a thing it is #217's hand-written "what is left has no texture"; the other three are this build's
  own and no spike ran them. A redo is a fresh render, not the cache's.
- **The same picture and request cost nothing twice** (the render cache), so `erase` run again pays only for what
  changed, and a probe of the last unit is the chain's own render.
- **The guard's sizes follow the picture:** they are pixels of a picture 1536 on its long side, scaled.
- **The checker reads the second laying's pictures,** so a blocked-in thing drawn again without its layer shows
  as all changed. Its brief says that isn't a stray change, and it now answers "left" for a layer too.

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

**As built (#219; `steps3.fit`, `tools.py paints` and `build-steps`).** The fit is `fit_paints` of #207, a unit at a
time, over the unit's whole change. The lesson's one color for a paint is its fit in the unit that lays the most of
it (a tie goes to the earlier unit). `paints` on a version 3 lesson only reports; `build-steps` fits again and keeps
the colors. Two things are reported, not failed: a paint fitted more than 25 Lab units from the plan's rough color
(`far_from_name`: five of the sleeping cat's 22), and a paint fewer than 20 pixels came to (`not_in_finish`). A
plan's `color`, name or `looks` can be changed without a new chain. Two paints whose names differ only in
punctuation are refused by `plan-check`.

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

**As built (#219; `steps3.build`).** A block-in is always a unit by itself (section 5), so no step is a flat coat
cut by v2's rule: a unit's last step is P[u], and an earlier step shows the pixels nearest its own paints.

**The three checks** (`pipeline-v3-plan.md`), run on every lesson:

1. The last step picture is the finish (a pixel counts when it is more than 24 levels off).
2. No step changes a pixel outside what its unit adds.
3. Every pixel a step lays is within a set distance of a paint that step names. **Not measured by any spike.** It
   starts as a number that is reported, not a failure.

**Open after #217:** with a flat block-in, the cut between two steps of one unit by nearest paint shows. The
cat's shade step left the places its white goes as hard-edged flat gray, and both of its graders marked it down.

Two more, from faults the graders named:

4. **A step that changes almost nothing** (under 0.2% of the canvas, and not a small thing such as a nostril) is
   reported.
5. **A first step that shows too much:** step 1's picture is compared with the plan's first `after`. This one is
   Claude's eye at step 5, not a measure.

**As built:** checks 1 and 2 fail `build-steps` (they hold by construction, so a failure means the chain's files
don't belong together). Check 3, a paint far from its name and check 4 are `notes`: fixing one needs a new plan and
a new chain. Check 4 measures what a painter would see (`seen`: a change of 9 Lab units or more after the guard's
blur), because a thing drawn again by a render moves every pixel a little; the spikes counted any pixel 6 levels
off.

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

**As built (#219; `steps3.as_v2`, `spike/lesson3.py`), for the teaching pictures, the recipes and the drafted
lines.** `build-steps` keeps the plan in version 2's shape (`v3/plan.json`: a part a unit), which unit each pixel
belongs to (`parts/owner.png`), where each step lays paint and each unit's shape (`v3/masks.npz`), and the checks'
numbers (`v3/build.json`). `step-aids`, `mix` and `draft-text` are v2's own code reading those; they never cut a
version 3 step, and they refuse what was kept when the plan, the finish, the chain or a kept file has changed. What
the spikes kept by hand is worked out:

- a unit that comes back to a thing, and a new thing painted in several steps, is `marks`; its parent is the part
  that started the thing (or what is behind it), and never another `marks` part;
- a new thing that starts as a block-in on things already painted is an `object`, and the page offers its outline
  to chalk. Every other new thing is an `area`. **Differs from the spikes,** where every new thing on painted
  things was an object unless a hand-kept list said otherwise (the birch grove's path, sun and branches);
- a unit's box, and its shape for the fact sheet, is what it changed (core first), not only where it is still on
  top at the end (#214).

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

**As built (#219; `spike/facts.py`, `tools.py packets` and `check-text`, `v3/writer-brief.md`).** The sheet, the
checker and the writers' packets are #173's code, moved out of the experiments with its experiment commands left
behind. `packets` writes `words/stage-NN/` (each step's `meant` is the plan's `after`). `check-text` drafts the
lines again, lays every stage's `out.json` on them, and checks strictly; a failure goes to that stage's
`feedback.md`; `--final` takes out a sentence that still fails (`words/dropped.json`). A writer's file is read as
it comes: one that isn't JSON, or isn't the brief's shape, is a problem for that stage, never a crash. A writer
can't rewrite the measured Where line. On a version 3 lesson a part's place on the sheet is what its unit changed
as well as where it is on top at the end (section 9).

**`check`, the seal and the page for a version 3 lesson (as built).** `check` runs `plan-check`'s rules on the
plan, then v2's checks on the lesson in version 2's shape, less the ones that read an outline or v2's cutter
(outline confidence, `bs.problems`, a pass far from its paint, the element's `show` order, the count of top-level
parts). In their place: `build-steps`' two checks that must hold; and as notes, a paint far from its name, a step
that changes almost nothing, and a step that turns a tenth of the picture from flat to textured (the step after a
block-in, section 14: failing it would stop every lesson with a block-in). The seal asks for the chain checker's
`answers.json` and for `check-text --final` where v2 asks for the text review. `lesson.json` keeps
`"plan_version": 2`, which the page reads, and adds `"pipeline": 3`. The lessons site takes a sealed version 3 lesson like any other (owner, 2026-11-18: v3 is
POC 2.0.0; the site refused one for a day, by Claude's reading of the gate). `check` also checks the writers' words against the sheet as it is now, so words changed
after `check-text --final` can't be sealed. `erase` caps the chain's own renders at twice what the chain costs
once (5 cents a unit plus 7), whatever the lesson spent before it. Cards are shown as the general
cards: `card-adapt` works, and the run doesn't use it.

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

**Passed 2026-11-18 (owner's call).** Five hands-off v3 lessons (the cow, the cat and the birch grove from the
bench, then the chickadee and the lavender fields; #230 to #234). The owner: "Worlds better than v2", and yes to the
gate with known problems missed: 4 to 7 a lesson, not under 2, most of them paints fitted far from their names.

## 14. Known risks

- **Stages inside a thing** (section 6). The owner preferred v2 over rendered stages once.
- **No outlines** (section 9). Every Where line, close-up and sheet so far was measured from one.
- **The plan asks for what the finish doesn't have.** A shade the finish has no color for, a rim light the locks
  already brought. Erasing by stage may give the plan its order back; it can't add a color.
- **Faint things won't erase,** so a first step can still show too much.
- **A stray change can still get through** (#218): what stays is in every request and a checker reads every unit,
  and one of three known strays passed the checker. The requests were tried on one picture.
- **More renders:** 25 to 33 cents and 3 to 4 minutes of chain a lesson, one after another (#214), and more when a
  unit is asked again.
- **The step after a block-in is a big jump** (#217). #214's block-ins arrived finished; asked for flat, they
  leave the thing's texture and form to the next step. Small steps (a rim light, a nose highlight, a mouth line)
  still change almost nothing.
- **Claude's graders are not the owner.** Every adopt this draft rests on is Claude's grade. On S4 Claude liked the
  stages and the owner preferred v2.
- **Every spike score was 2 to 4 out of 5.** Each adopted piece was the better of two flawed lessons, not a good
  one.
