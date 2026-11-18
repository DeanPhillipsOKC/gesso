# Pipeline v3 plan: from cut-outs to layers

The plan for getting from pipeline v2 to v3 (owner approved, 2026-11-16). It is a series of spikes, not a
design: `docs/design/pipeline-v3.md` gets written from whatever the spikes adopt. Until then v2
(`pipeline-v2.md`) is the pipeline.

## Context

Pipeline v2 renders the finished painting once and cuts every step picture out of it. That fixed v1's drift
and cost, but it has stopped improving. The evidence from the issue history, the changelog and the 52 run
records:

- Known problems per lesson have stayed flat at about 2 to 7 from POC 1.0.0 to 1.12.1.
- The same fault comes back in a new form after each fix: #84 → #139 → #144 → #153 → #155 → #163 for step
  pictures, #154 → #158 for paints, #122 → #126 → #90 → #159 for placement.
- `spike/build_steps.py` now holds about 34 tuned numbers, most named after one past failure.
- Runs take 15 to 21 minutes. Renders are only 60 to 100 seconds of that. The rest is Claude's round trips
  through tools that each rebuild everything.

Four causes sit under almost all of it:

1. **A step picture is the finish with things taken away**, so whatever was hidden has to be invented by
   fill rules (rims, strays, row fills, borrowed texture).
2. **Every pixel has exactly one owner.** Each outline mistake shows up in the pictures, the Where lines and
   the paints at once.
3. **The picture comes first and the paints and words are fitted to it afterwards**, so they disagree.
4. **Checks react to one past fault each**, and each fix is confirmed on a fresh render, so a new finish
   brings new faults and nothing tells a regression from randomness.

Owner's answers for this plan: the weakest parts are **step pictures** and **teaching and text**; make runs
clearly faster where it's free but never trade quality; spikes may challenge four rules (more renders, other
models, one part per step, an image model helping make stages); the owner will do **blind A/B scoring**.

## The v3 idea

**A lesson is a stack of paint layers, and every picture is the first N layers put together.**

- Each layer is complete under whatever later covers it. Nothing behind anything is ever invented at build
  time, so the fill rules go away.
- Layers may overlap, with soft edges. A layer never changes once it's down, because a later picture only
  adds layers on top.
- A layer holds only the colors of the paints its step names, so pictures, paints and text agree because
  they are made from the same record, not checked into agreement afterwards.
- The plan is written as a painter's process first (whole-canvas steps allowed: toned ground, block-in,
  glaze), and the pixels follow it.

Three checks that hold for every photo replace the per-fault ones:

1. All layers together equal the finish, within a set tolerance.
2. No picture changes a pixel outside the layer its step adds.
3. Every pixel in a layer is within a set color distance of a paint that step names.

How the layers get made is the open question. That is what the spikes are for.

## Wave 0: the yardstick (before any experiment)

Nothing else starts until this exists, or v3 repeats v2's pattern.

Issue #165 covers all of Wave 0.

- **S0a. Frozen bench.** 8 pictures: the five on the site (chickadee, red sailboat, lavender balloon,
  sleeping cat, snow lantern) plus three picked to hurt (fur or hair, water with reflections, many thin
  overlapping things). Each has its photo, canvas fit and finish render **frozen**, so an experiment changes
  one thing. Lives in `spike/experiments/bench/`, built on the three-lesson fixtures in `spike/tests/`.
  This is for experiments only; site lessons still rerun from the photo.
  The three hard pictures (picked by Claude at the owner's request, 2026-11-16; AI-made with the image model at
  high quality, about 4 cents each):
  - `photos/highland-cow.jpg`: long shaggy hair over the face, loose strands against the sky, grass blades in
    front of the legs. Tests soft and furry edges.
  - `photos/lake-cabin.jpg`: pines, a peak and a cabin mirrored in still water, ripples breaking the reflection,
    reeds and pebbles in front. Tests reflections and what's behind the reeds.
  - `photos/birch-grove.jpg`: a dozen thin trunks at different distances, branches crossing each other, mist.
    Tests many thin overlapping things and the order they're painted in.
- **S0b. Blind A/B page.** Two lessons side by side, sides shuffled, a short rubric per lesson: step pictures
  look like a real half-done painting; I could paint each step from its words; pictures, paints and words
  agree; overall which would I paint from. About 15 minutes per experiment. Scores saved with the run.
- **S0c. Fault counter.** A fresh-context reviewer that counts faults by the eight classes found in the
  history (A step pictures, B outlines, C placement, D paints, E text, F teaching, G site, H tooling). Scored
  against the owner's A/B results until it agrees well enough to screen spikes alone. Today's reviewer
  agreed with the owner on 8 of 15 steps, and mostly ran in the same session that wrote the text.
- **S0d. Run trace.** Wall time per phase split into Claude thinking, tool time and render time, read from
  the `seconds` field every tool already prints plus the session's timestamps.
- **S0e. Baseline.** v2 at POC 1.12.1 on the bench: A/B scores, fault counts, trace.

## Wave 1: where layers come from (step pictures)

Run side by side on the frozen bench. Each is judged on the three checks above, class A and B fault counts,
and the owner's A/B.

- **S1. Peel (#166).** Ask the image model to un-paint the finish backward: remove the front things, then the next
  ones back, and keep only the pixels inside what was removed (the same guard `background_problems` uses
  today). This is v2's one background render made general. Try chained against all-at-once-in-parallel, low
  against medium quality, and gpt-image against one other edit model. Guess: 3 to 5 low renders, about 8
  cents and 20 seconds in parallel. Run 2026-11-17: `docs/spikes/v3-peel.md` (verdict: park; the owner's A/B found no difference).
- **S2. Layer models (#167).** Models built to split one picture into see-through layers in one call (the
  Qwen-Image-Layered kind), and gpt-image's own transparent-background output for a single object. If one
  call gives clean complete layers, S1 isn't needed.
- **S3. Better edges (#168).** Outlines that follow what Claude means, not where Claude put a box: name-prompted
  segmenters (the SAM 3 kind) so "the branch" is the prompt, and a matting model for soft and thin edges
  (whiskers, fur, foliage). Also test outlining the photo against outlining the finish. Reuse the
  nine-model harness in `spike/experiments/issue85.py`. Run 2026-11-17: `docs/spikes/v3-edges.md` (verdict: drop the
  name prompts and the photo outlines, park the soft edges; Claude's blind graders preferred v2 over SAM 3's
  name-prompted outlines on 2 of 3 pictures, and tied soft edges with v2 on all 4, one chickadee grader preferring
  them slightly).
- **S4. Stages inside a part (#169).** Today a half-done part is a flat coat plus nearest-color passes, which the
  design doc itself lists as a risk. Test peeling detail instead of things: the same part "before the
  highlights", "before the texture", "blocked in", pixels locked outside the part. Compare with v2's
  flat/pass on the A/B. Run 2026-11-17: `docs/spikes/v3-part-stages.md` (verdict: drop; the owner's A/B
  preferred v2 on 2 of 3 pictures and saw no difference on the third).

- **S4b. Whole-picture stages (#204, added 2026-11-17 from the owner's ideas #203 and #204).** Erase things from the
  finish one at a time, chained, and show the erased pictures themselves as the pictures a lesson's stages end on.
  The guard needs no outline: of each render only what changed by a lot is kept. Steps inside a thing stay v2's.
  Run 2026-11-17: `docs/spikes/v3-whole-stages.md` (verdict: adopt; Claude's blind graders preferred it on all 3
  pictures, both graders each, five clearly and one slightly; the owner saw the lake cabin's sheet and said go. The
  birch grove needed three tries and still shows faint firs in step 1).

## Wave 2: wilder bets

- **S5. Paint it for real (#170).** A brush-stroke engine that carries out each step with that step's brush, paints
  and stroke card, aiming at the finish. Then a step picture is exactly what those paints and that stroke
  give, and the last picture is the finish. Risk: it looks computer-made. Fallback use: its output as the
  guide picture for a render in S4.
- **S6. Paints before picture (#171).** Lock the finish to the lesson's mixes: either push the finished render onto
  the named paints, or hand the render the paint swatches as an input. Measure the share of pixels no step
  names (#158 found 74% on one part) and whether the owner sees any loss. Run 2026-11-17:
  `docs/spikes/v3-paints-first.md` (verdict: drop; locking the finish to the paints lost the graders' A/B on 2 of 4
  pictures and tied the other 2, and the image model ignores a swatch card).
- **S7. Plan before pixels (#172).** Claude writes the lesson as a painter would teach it (ground, block-in, middle
  values, shadows, lights, details; steps that cross parts) from the photo and the element techniques, and
  the layers are made to fit that plan. v2 does the reverse. Measure class F faults and the "could I paint
  it" score. Run 2026-11-17: `docs/spikes/v3-plan-first.md` (verdict: adopt; Claude's blind
  graders preferred it on 2 of 3 pictures and split on the third).

## Wave 3: teaching and text

- **S8. Words from facts (#173).** Each step gets a fact sheet from its layer: sides, sizes and distances in inches,
  the paints, what's next to it. Claude may only use numbers and sides that are on the sheet, and a tool
  checks every one in the text (#159 can't happen). The writer sees the before and after pictures while
  writing. One writer per stage, in parallel. Run 2026-11-17: `docs/spikes/v3-words-from-facts.md` (verdict: adopt;
  Claude's blind graders preferred the writer's words on 3 of 4 pictures, mostly by a slight edge, and called the
  fourth a toss-up; one fault counter found fewer placement and text faults, inside the counters' spread; the text
  phase took minutes, not tens of minutes. The verdict covers the whole writer (sheet, checker, before and after
  pictures), not the sheet alone).
- **S9. The student test (#174).** A reviewer who has never seen the plan gets only the before picture and the
  words, and must say what the after picture will show, or pick it out of four. Where it can't, the words
  are at fault. A dearer form for the bench only: the image model carries out the words on the before
  picture and the result is compared with the real after.
- **S10. Cards that fit (#175).** Stroke cards and pictures still disagree (dry brush promised, solid coral shown).
  If S4 or S5 works, cut each card's example from the lesson's own layer.

## Speed (runs alongside, after S0d)

- **S11. One engine, not thirty tools (#176).** One long-lived process that holds the plan, knows what depends on
  what, and rebuilds only what changed. Today every tool is a new process and `build-steps`, `step-aids`,
  `draft-text`, `check` and `publish` each rebuild every picture; `outline` reloads the model and re-reads
  the picture every time (8 s). Start from the `_built` memo in `spike/build_steps.py` that only tests use.
- **S12. Fewer trips (#177).** Plan in one pass against a checker that answers in under a second; renders in
  parallel; text, diagrams and review as parallel subagents. The three checks above should leave far fewer
  problems to loop on, which is where the 3 to 10 minutes of check-and-review goes.

No fixed target. Report the trace before and after.

## How a spike runs

- Code in `spike/experiments/v3_<name>.py`, a write-up in `docs/spikes/v3-<name>.md` ending in one of
  **adopt, drop, park**, with numbers. Same pattern as `issue52.py`, `issue85.py`, `issue100.py`.
- One GitHub issue per spike under the parent issue #164, scored per `docs/backlog.md`. One pull
  request per spike. Spike code under `spike/experiments/` skips the adversarial review; a write-up that gives a
  verdict gets one verdict check in its place (numbers match the results file, the A/B was blind, the verdict
  follows), per `docs/decisions.md`.
- **Since 2026-11-17 the A/B is graded by Claude, not the owner** (`docs/decisions.md`): two fresh graders a
  picture who don't know which side is which, by `spike/experiments/bench/ab_grader.md`. The owner grades one
  finished lesson at the end (the gate in Order, step 5).
- A spike is dropped when it loses the A/B to the v2 baseline, or breaks one of the three checks on more than
  one bench picture with no clear fix.
- Render spend is expected to stay under about $2 per spike. Anything dearer gets asked first.
- Spikes that need a hosted model (S1's second model, S2, parts of S3) need a new host allowed and a key.
  That is asked for when the spike starts, not now.

## Order

1. Record the owner's answers in `docs/decisions.md` (the four rules open to challenge for v3 spikes, speed
   now counts where it's free, the frozen bench for experiments). File the parent issue and the spike issues.
2. Wave 0. Owner picks or approves the three hard pictures and does the baseline scoring.
3. S1, S2, S3 in parallel; S11 alongside. Then S4.
4. S6 and S7, then S8 and S9. S5 and S10 as time allows, since both depend on Wave 1's answer.
5. Write `docs/design/pipeline-v3.md` from what was adopted (a draft since 2026-11-17, #210; one combined lesson
   for the owner to look at comes before the gate: made on the highland cow, `docs/spikes/v3-combined.md`; the
   owner said go on 2026-11-17; two more bench pictures with blind graders followed, `docs/spikes/v3-combined-round2.md`,
   #214: adopt; the block-in was then tried four ways, `docs/spikes/v3-block-in.md`, #217: adopt the fourth). Gate: v3 beats v2 on the blind A/B for every
   bench picture's weakest stage, known problems per lesson drop below 2, and the trace is shorter.
6. Build v3 as `/paint-lesson` behind `plan_version: 3`, rerun the site lessons, remove v2.

## Kept as they are

Real technique drives the steps and comes from cited research. Acrylic, back to front, white canvas. 12 to
24 steps. Mixbox recipes and the mix rules. Inches, never percent. Claude plans. Hands-off runs only on the
site. No painting-order or depth tool, and no filter in place of the beginner render.

## Checking the work

- Wave 0 is done when the v2 baseline has A/B scores, fault counts and a trace for all 8 pictures, and
  running the same frozen bench twice gives the same pictures.
- Each spike is checked by its own write-up numbers plus `python spike/tests/suite.py --quick` after every
  change and the full suite before a merge (`docs/testing.md`).
- v3 itself is checked by the gate in step 5, on fresh hands-off runs from the photos.
