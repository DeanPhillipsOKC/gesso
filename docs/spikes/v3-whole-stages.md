# Spike: whole-picture stages (#204), stage 1

2026-11-17. Stage 1 of the issue: one picture (the lake cabin), one step sheet beside v2's, for the owner to look at
and say go or stop. This is a short note, not a write-up, and it gives **no verdict**. The code is
`spike/experiments/v3_whole_stages.py`, its tests `spike/tests/test_v3_whole_stages.py`. It is experiment code: no
lesson tool, the skill, or the site changed.

## What was tried

- **Erase backward from the frozen finish, chained.** Rocks, reeds, the three reflections, the lake, the dock, the
  cabin, the forest, the mountain: eight low renders, each made from the last picture. The lake has nothing behind it
  but canvas, so its render is asked for bare white canvas; the others paint what's behind.
- **A guard with no outline.** Of each render only the patches that changed by a lot are kept (they must start inside
  the plan's loose box for the thing). Every other pixel stays as it was. Canvas once bare stays bare. The baseline
  run's outlines are read only to measure.
- **Steps inside a thing are v2's** flat coat and nearest-paint passes, cut from the thing's own whole picture. A
  thing's last step is the whole erased picture, exactly.

Same plan, paints and steps as the baseline run. The words weren't touched.

## The pictures

v2 above, whole stages below, all 23 steps:

![The lake cabin's 23 steps: v2 above, whole stages below](v3-whole-stages-cabin.jpg)

The chain itself: top row, bare canvas and then the picture after each thing is added; bottom row, the raw renders.

![The chain of erased pictures and the raw renders](v3-whole-stages-cabin-chain.jpg)

What the sheet shows, by Claude's eye (the owner's look decides):

- **Steps 1 to 4.** v2 has a gray band for the sky and a tiled pattern on the mountain. Here step 1 is a painted sky
  and the mountain goes flat coat, shade, snow.
- **Steps 11 to 17.** v2's water has a pale hole where the reeds will go and arrives in patches. Here step 12 is a
  whole lake with no reflections, and the reflections go on over it.
- **Nothing of a later thing shows early.** No slivers or holes on any step.
- **Fault: the reeds' flat coat (step 18) is too big.** Erasing the reeds also erased their reflection, so the
  guard counts both as "the reeds" and the flat coat covers both. Step 19 inherits it.
- **Fault: stray dots under the forest's dark pass (step 5),** as in v2.
- **The sky ends in a straight white edge** where the lake's canvas begins. That is what a half-done canvas looks
  like, but it is the model's line, not the plan's.

## Numbers

| Thing erased | Share of the picture the guard kept as changed | Same place as v2's outline (IoU) | Render moved outside the change |
|---|---|---|---|
| rocks | 5.3% | 0.88 | 5.0% |
| reeds | 10.7% | 0.39 | 3.9% |
| reflections | 48.0% | 0.41 | 5.1% |
| lake (to bare canvas) | 54.5% | 0.46 | 3.7% |
| dock | 0.7% | 0.44 | 4.1% |
| cabin | 1.0% | 0.54 | 7.1% |
| forest | 25.8% | 0.84 | 3.3% |
| mountain | 24.6% | 0.27 | 2.4% |

- **Was each thing truly gone?** By eye on the chain, yes for all eight; no render was made twice. A low IoU here
  mostly means the change is bigger than v2's outline for a good reason: the reeds and reflections take their
  shimmer with them, the lake is the whole lower canvas, the mountain is whole behind the forest.
- **Does anything move outside what a step adds?** No, by construction: 0.00% on every step, and the last picture is
  the finish. The raw renders moved 2 to 7% of the pixels outside the change; the guard threw that away.
- **Redos.** No render was redone. The guard was changed once: the plan's box for the mountain stops short of the
  mountain's left end, and the first rule (keep nothing outside the box) left that end standing. The box now says
  where a change must start, not where it must end.
- **Cost and time.** 8 low renders, 14 cents, 115 seconds one after another.

## Not done (stage 2, on the owner's go)

The birch grove and the highland cow, the blind A/B, the forward and "inspired, not a copy" arms, a second edit
model, a fix for a thing's flat coat taking in its reflection, and the full write-up with a verdict.

## Running it

    python spike/experiments/v3_whole_stages.py units lake-cabin     # the things, in order; no render
    python spike/experiments/v3_whole_stages.py erase lake-cabin     # PAID: one low render a thing, chained
    python spike/experiments/v3_whole_stages.py build lake-cabin     # step pictures and the sheet beside v2's

It reads the baseline runs from `/home/user/gesso-baseline/output` and writes under
`spike/experiments/bench/runs/whole/` (git-ignored). A render already in its folder is kept.
