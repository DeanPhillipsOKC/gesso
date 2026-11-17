# Spike: the three adopted v3 pieces in one lesson (#210)

2026-11-17. Step 5 of `docs/design/pipeline-v3-plan.md`: the first lesson made the way `docs/design/pipeline-v3.md`
describes, on one picture, the highland cow's frozen finish. The code is `spike/experiments/v3_combined.py`, its
numbers `spike/experiments/v3_combined.json`, its tests `spike/tests/test_v3_combined.py`. It is experiment code: no
lesson tool, the skill, or the site changed.

**No verdict yet: this is for the owner to look at** (go, change, or stop). No graders ran. What follows is what
was made, the numbers, and what Claude saw.

## What was run

1. **The plan** is the plan-first painter's plan (#172): 24 steps in 7 stages, written before any outline.
2. **The chain** erases the finish backward by that plan's 11 units, one low render a unit, each made from the
   last. The guard keeps only what a render changed by a lot, with no box (the plan has none).
3. **Paints** are the plan's 17, each fitted to the color it has in its unit's change.
4. **Step pictures** are cut from the chain: a unit's last step lays all of its change; an earlier step is a flat
   coat or a pass of the pixels nearest its paints.
5. **Shapes come from the changes.** A lesson folder is made in which a part is a unit and its shape is the core
   of what its render changed. No outline model ran. v2's own tools then read it unchanged: Where lines,
   close-ups, paint maps, the transfer outline, drafted lines, recipes, the page.
6. **Words** are #173's: a fact sheet measured on these pictures, 7 stage writers on Opus in parallel, each with
   its before and after pictures and the plan's `after` line for every step, then the checker and one round of
   fixes.

![The cow's steps: v2, whole-picture stages (#204), combined](v3-combined-cow.jpg)

Three rows a thing: v2, whole-picture stages (#204, on v2's plan), and the combined lesson. The rows are lined up
by the thing being painted, each picture under its own step number.

The chain: top row, the picture after each unit; bottom row, the raw renders.

![The cow's chain](v3-combined-cow-chain.jpg)

## What it showed

**The untested request works.** Taking a thing back a stage (the design's third kind of request) was the main
guess. It ran on three units:

- **The face** (probe, then the chain): the nose, nostrils and mouth come off and plain coat is left. The cow keeps
  its place and outline.
- **The coat:** the locks and the gold come off and a smooth, shaded brown cow is left, as the plan's step 10 says.
- **The tall grass:** the first request took off only the gold blades and left the green ones, so steps 20 to 22
  had nothing to show. Asking again in stricter words gave the same. A third wording that says what is left ("a
  first coat: smooth, flat and softly blended, with no separate strokes, blades, dabs or texture") worked. The whole
  chain was then made again from that render.

**The step pictures follow the plan.** Claude's read of the sheet above:

- Step 1 is a sky with faint streaks, not the finished sunset. The clouds arrive in steps 2 and 3.
- The ground goes in as one smooth green (step 6), the bushes after it, the cow over it.
- The cow is a flat shape (9), then shaded (10), then horns (11, 12), then copper locks, gold locks and the rim
  (13 to 15), then the face in its own four steps (16 to 19). In v2 and in #204 the cow went from a flat shape to
  nearly finished in one step, and the face had no step.
- The tall grass builds over the cow's legs in four visible passes (20 to 23).
- No blotches, pale holes or hard boxes: nothing is filled in by a rule.

**What is still wrong,** most of it found by the stage writers comparing each picture with the plan:

- **Inside a unit the steps are still v2's cuts.** A unit's last step lays everything left, so it can bring more
  than its words: step 8 (sun on the bushes) also brings dark bush rows; step 10 (shade the cow) also brings
  hair-like strokes and lighter streaks; step 3 (cloud tops) lays gold across the whole sky.
- **Two steps with one paint can't be told apart.** Steps 18 and 19 both use Dark umber, so step 18's pass takes
  the mouth too and step 19 changes nothing you can see.
- **Small last steps change little.** Step 24 (brightest tips) changes 0.04% of the canvas. Step 15 (the rim)
  changes 1.3%, mostly on the fringe; the horns' light isn't seen.
- **Flat coats read as blobs** where the plan describes texture: step 2's clouds are solid apricot shapes with no
  violet, and step 7's bushes are solid dark shapes.
- **With no box, a stray change is kept.** The tall-grass render also smoothed a few bush rows on the hillside,
  which come back on step 24. The face render moved a horn tip a little.
- **Step 6 has a dark strip under the mountains** where the plan says lighter and yellower.
- **Some paints aren't in the finish.** Fitted to the picture, Pale rose came out gold (52 Lab units from the
  plan's color), Copper orange a dark brown (29), Horn taupe a gray (23), Rosy brown a plain brown (22).
- **17 paints,** against the target of 10. Nothing merges them.

## The numbers

| Unit | Request | Steps | Erased (share of canvas) | Raw render moved the rest |
|---|---|---|---|---|
| tall grass | back (third wording) | 20 to 24 | 38.7% | 2.6% |
| cow, face | back | 16 to 19 | 2.3% | 2.5% |
| cow, coat (and the horns' rim) | back | 13 to 15 | 23.4% | 0.4% |
| horns | behind | 11, 12 | 2.4% | 0.4% |
| cow, shape | behind | 9, 10 | 22.9% | 0.7% |
| bushes | behind | 7, 8 | 10.7% | 0.3% |
| hillside and meadow | bare | 6 | 72.2% | 1.7% |
| loch | bare | 5 | 0.2% | 0.7% |
| mountains | behind | 4 | 9.9% | 0.7% |
| clouds | behind | 2, 3 | 9.6% | 4.3% |

- **The three checks.** The last step picture is the finish (0.00% of pixels off). No step changes a pixel outside
  what its unit adds (0.00%). What a step lays is a median 14.2 Lab units from the nearest paint it names; the worst
  are the last steps of units (the rim 42.8, the brightest tips 38.0, the sun on the bushes 37.0).
- **Steps that change under 0.2% of the canvas:** one, step 24.
- **Renders:** 10 kept, at 18.1 cents and 127 seconds one after another. All spent: 40.0 cents (the first chain,
  18.1 cents, thrown when the tall grass was asked for again; two probes not used, 3.8 cents).
- **Words:** 7 writers, each back in under a minute. 138 checkable claims; 9 failed the strict check, all a side
  word with nothing named ("below it"). After one round of fixes: 0 failures, nothing taken out.
- **Teaching pictures from the changes:** 24 Where lines, 7 close-ups, 10 paint maps and a transfer outline were
  made with no change to v2's tools. One fault seen: the face's sheet lists a second mark up by the right horn
  (the stray change above).

## What the design gets from this

- A step's `after` line describes the whole canvas, so it can't be handed to a render as it is: "no cow yet" in
  the meadow's line would ask for the cow to go. The request drops the sentences about what isn't there yet. A
  plan should give each thing a line for how it looks after each of its stages.
- A thing needs a name for its first stage ("the plain green meadow"), and each unit a name ("the cow's coat").
  Here they were written by hand (`spike/experiments/v3_combined_plan.json`), with `behind`.
- The "back" request should say what is left, not only what goes.
- A redo of a late unit throws the whole chain after it. A probe of one unit first costs 2 cents.
- The stage writers are a good check of pictures against the plan. Their notes are the list above.

## Limits

- One picture, one run, read by Claude and by the writers. No graders, no fault counter, and the owner hasn't
  looked yet.
- The plan's extras (`behind`, the names, the rough paint colors) were written by hand for this picture.
- v2's own `check` wasn't held to: it reads numbers only v2's cutter makes, and the plan's units break two of its
  part rules (a coat that starts with a pass).

## Running it

    python spike/experiments/v3_combined.py units highland-cow --prompts   # the requests, last first; no render
    python spike/experiments/v3_combined.py probe highland-cow 9           # PAID: one unit alone
    python spike/experiments/v3_combined.py erase highland-cow --redo 10:2 # PAID: the chain
    python spike/experiments/v3_combined.py build highland-cow             # step pictures, the three-row sheet
    python spike/experiments/v3_combined.py lesson highland-cow            # the lesson folder, aids, writers' packets
    python spike/experiments/v3_combined.py merge highland-cow [--final]   # the writers' words in, checked
    python spike/experiments/v3_combined.py page highland-cow              # the lesson as a page
    python spike/experiments/v3_combined.py results highland-cow           # writes v3_combined.json

It writes under `spike/experiments/bench/runs/combined/` (git-ignored). A render already in its folder is kept.
