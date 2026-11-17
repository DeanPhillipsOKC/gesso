# Spike S8: words from a measured fact sheet (#173)

2026-11-16, revised the same day after the adversarial review of PR #182; the writer and the A/B on the frozen bench
2026-11-17. Pipeline v3 plan, wave 3 (`docs/design/pipeline-v3-plan.md`). The code is
`spike/experiments/v3_facts.py`, the writer's brief `spike/experiments/v3_facts_writer.md`, the tests
`spike/tests/test_v3_facts.py`. The words and fault counts are in `spike/experiments/bench/facts/<picture>/`, the
graders' scores in `spike/experiments/bench/scores/s8-facts.json`. Nothing in the pipeline changed, and no render was
made.

**Verdict: adopt** writing each step's words from its measured fact sheet, one writer per stage, checked by the tool,
for the v3 design. Blind graders preferred the fact-sheet words on the highland cow, the lake cabin and the lavender
balloon (both graders each) and called the chickadee a toss-up (both); they lost on none (section "The A/B"). These
are Claude's grades (`docs/decisions.md`, 2026-11-17), not the owner's. The edges are small: the pictures are the same
on both sides, and both sides share their faults.

- **The words agree with the pictures better.** Every grader who chose a side scored the fact-sheet words a point
  higher on "the pictures, paints and words agree" (6 of 6). "I could paint each step from its words" rose for 2 of 8.
- **Fewer placement and text faults:** 27 distinct C and E faults on the four lessons against 37 and 37 from v2's two
  counters (about 27% fewer), lower on three pictures and inside the counters' spread on the balloon. 6 of the 8
  placement faults left are the measured Where lines, the same words on both sides.
- **Faster:** the 26 stage writers ran in 2 1/2 minutes for all four lessons, and the whole text phase (writers,
  checker, one round of fixes, the lesson's own `check`) in about 12. v2's step 6 alone took 1 1/2 to 12 minutes a
  lesson, and its step 7 review another 3 1/2 to 11.
- **The checker holds the writers to the sheet.** 35 of 551 claims failed on the first pass; one round of fixes left 1,
  which was taken out. v2's step-6 words, checked the same way, fail or don't resolve on 35 of 78 claims.

The fact sheet and the checker, from the first half of the spike:
- **Planted faults:** a fault put into a measured Where line is caught 97 to 100% of the time, depending on the
  kind. A fault put into Claude's written tips is caught 41 to 94% of the time.
- **#159 on the sealed run it came from:** 5 of #159's 8 items are caught there as text faults, and a sixth (the
  paint) by the sheet. One more is caught only on a made-up scene, and one isn't caught.
- **The five sealed 1.12.1 lessons:** 9 of 12 distinct flagged faults are real.

## What the sheet holds

One sheet per lesson (`sheet <lesson>`, about 100 KB of JSON), measured from the step pictures and the plan. It
uses the measure the Where lines use (`build_steps.visible`, cropped to the canvas, without stray specks), so a
sheet and its Where line agree. All distances are inches on the painter's canvas.

**Per part, as the finish shows it:**
- its box: each side's distance from its own canvas edge;
- its size and its middle;
- the canvas edges it reaches, and where it meets each of them (two paths meet the bottom edge twice);
- its peak, its width at its foot, and the row where it's widest;
- which side of every other part it sits on, read locally (the sun is above the mountains where they dip under it),
  whether they touch, and the gap between them.

**Per step:**
- **its area**: the thing the Where line describes;
- **its marks**: each piece of what the step changes, up to 8. For a part's last step, which shows everything left
  of the finish, they're read from the pixels within 25 Lab units of one of the step's own paints;
- **crossings**: where the marks cross the part's middle row, and four more rows. Stripes joined at the top of a
  balloon are one mark but separate crossings;
- **what it adds**: the median color, how far each named paint is from it, and how much of it lands in each half
  of the part;
- **the paints it names**, and whether it lays one over the same paint id from the part's step before;
- **every other part**: which side this step sits on, touching or not, and the gaps;
- **its Where line**, word for word.

**Tolerance:** a length must be within half the Where line's rounding step, plus 0.02 in:
- 0.145 in under 2 in;
- 0.27 in from 2 in.

The first version allowed 0.05 in of slack, and a Where line moved 1/2 in then got through 9% of the time. A share
of the way across must be within 0.06.

## The checker: what counts as a claim

The checker reads every number and every side or position word in a step's summary, tip, lines and paint notes.
Each claim is checked against **the one fact it names** on that step's sheet. A Where line is about the step's
area only. Other words are about the part the clause names first (not one after a preposition), or the piece a
label picks ("the right one"), or else the step's area, its part and its marks, one value each.

| Claim | Example | Checked against |
|---|---|---|
| length | "its top is about 2 in from the top edge", "3/4 inch across", "1-1/2 in wide", "2 to 3 inches" | the value the clause names: "its top" against the top, "wide" against the width, "from the right edge" with no anchor against the near side or the middle. A length with no axis, edge or size named is unresolved |
| edge | "at the right edge", "reaches the bottom edge", "all the way across", "its bottom is at the top edge" | the canvas edges the thing reaches, and the named side's distance from that edge. A part's own edge only when the words name it ("along its left edge", "the left edge of the mast": that half gets the paint) or a stripe runs "along the far left edge" of an object. Never for a Where line |
| fraction | "a third of the way in", "two-thirds in", "halfway down" | the thing's places as shares of the canvas, or of the part |
| center | "just left of the center" | the stripe nearest the part's middle (or the labeled one) for marks inside a painted part; the thing's middle otherwise |
| relation | "above the hull", "just inside the left red stripe", "on its right" | another part (local sides and gaps), or an earlier step's stripes named by their paint's color: each reference stripe judged by this step's stripe nearest it, on the middle row |
| position | "at the upper right", "down the right side of the canvas" | the thing's middle; for a pass inside a part, which halves its paint lands in |
| side | "the olive goes on the left side" | at least half of the paint it adds in that half of the part (15% with "too", "also", "some") |
| agree | the Where line's "3 in wide" and the tip's "2 1/2 inches wide" | two widths (or heights) of the step's own thing in one step |

These aren't claims; they're counted and never failed:
- stroke directions ("left to right", "pulled to the lower left");
- brush sizes and step numbers;
- counts ("two in this corner");
- labels ("the left path", which picks the piece a claim is checked on);
- the light's direction;
- the edge of another thing;
- "outside" meaning out of doors;
- a side within a thing's own shape on its first step.

A claim is **unresolved**, and fails only with `--strict`, when:
- its reference isn't on the sheet ("below it", "the horizon");
- a length has nothing named to measure against;
- it's about what's left showing;
- it puts a thing to a side of a part that surrounds it (the balloon is "right of the sky").

Each failure names the step and field, quotes the words, says what they claim and what the sheet says:

    step 22 (balloon-blue), tip: "on its right" says just right of step 21's red (center one); sheet: step 21's
    red (center one) at 3.81-4.03 in; this step's touching stripes: 3.36-3.81 in (inside, left of)

## Planted faults: the catch rate

`mutate <lessons>` plants one fault at a time and counts a sentence as caught when it then has more failed claims
than before. The faults:
- each length moved by ±1 in and ±1/2 in;
- left and right swapped in a sentence with a side claim;
- up and down swapped (but not inside "top to bottom");
- inside and outside, and left and right, swapped in a stripe or center claim;
- an edge moved: "at the right edge" becomes 1 1/2 in from it, and a distance of 1 in or more becomes "at the edge".

In Where lines every mutant is wrong by construction, except a thing symmetric about the middle, or a value within
a hair of the rounding point. In tips, faults are planted only in sentences the checker accepts as they are.

| Planted fault | Fixture Where lines | Sealed Where lines | Sealed tips, summaries and edited lines |
|---|---|---|---|
| length +1 in | 133/133 (100%) | 265/265 (100%) | 14/19 (74%) |
| length −1 in | 108/108 (100%) | 234/234 (100%) | 10/11 (91%) |
| length +1/2 in | 124/133 (93%) | 257/265 (97%) | 12/19 (63%) |
| length −1/2 in | 126/126 (100%) | 250/256 (98%) | 15/16 (94%) |
| left/right swapped | 34/34 (100%) | 67/67 (100%) | 20/36 (56%) |
| up/down swapped | 50/51 (98%) | 97/99 (98%) | 20/44 (45%) |
| edge moved | 44/44 (100%) | 90/90 (100%) | (none planted) |
| stripe or side mirrored | | | 7/17 (41%) |
| **false alarms on the words as they are** | 0 of 171 claims | 0 of 332 | 14 flags in 124 claims (below) |

The review's run of the first version had Where lines catching 63% of +1 in shifts and 53% of side swaps.

**Where-line misses:**
- The 1/2 in misses are values about 1/4 in from a ruler step: 4.73 in is said as "4 1/2", and "5" is then 0.27 in
  off, inside the tolerance.
- The two up/down misses are a post whose top and bottom are each about 1 3/4 in from their edges, so the swapped
  line is still true.

**Tip misses:**
- **Words that aren't claims or don't resolve:** "the moon, upper left" has no preposition; there's "the light from
  the right"; there's "below it".
- **A piece of a part:** "a taller peak on the right" of the mountains.
- **A plural part named in the singular:** "the big hill" of "Golden hills".
- **A sentence about the step's whole area,** which reaches both edges.

The full lists are in `mutate`'s output.

**Fixed after the second review:**
- **Two relations joined by "and" with no comma** ("just outside the left red stripe and one just left of the center
  red stripe"): the first reference used to run on and swallow the second claim. A reference now ends at and, or,
  then, while and but, so each relation is checked. The #159 step-22 sentence shape is tested both ways.
- **A pass's tip about an edge** is now read from the marks the pass adds, not from the whole part it's painted on.
  Before, "dab the dark marks at the right edge" passed when the dabs were all in the left third, and "keep the dark
  marks short of the right edge" was a false alarm when it was true. After the third review, those edges come from
  all the paint the pass adds (`adds.edges` on the sheet), not its 8 biggest marks, so 13 equal dabs from edge to
  edge still reach both edges.

`FixtureTests` fails if the fixtures' Where-line catch rate drops below these floors:
- 100% for ±1 in, side swaps and edge moves;
- 95% for −1/2 in and up/down;
- 90% for +1/2 in.

## Results

### The three fixture lessons

After `draft-text`: 56, 62 and 52 Where-line claims, all passing. The drafted card lines have no other claims. The
red sailboat has one unresolved claim ("paint below it").

### The items in #159

#159 lists 8 items. On the sealed run itself (`balloon-lavender_skill_20261116-171639`, which rebuilds byte for
byte):

| #159 item | Caught on the sealed run? |
|---|---|
| Step 21, center stripe "just left of the center" (it's right) | yes: center |
| Step 22, blue stripe "just inside the left red stripe" (it's outside) | yes: relation |
| Step 22, blue stripe "on its right" of the center red (it's on its left) | yes: relation |
| Step 20, the tip's 2 1/2 × 3 in against the Where line's 3 × 3 1/2 in | yes: length, twice (2.5 against 2.82 wide, 3 against 3.55 tall), and agree, twice |
| Step 11, the right path "about two-thirds in" | yes: fraction (it meets the bottom edge 0.81 of the way across) |
| Step 13, Shadow violet stamped on Shadow violet | yes, by the sheet (`paint_faults`), not as a text claim |
| Step 16, "its right side is at the right edge", 0.9 in short | **no, and it's not a fault in the canvas.** In the painter's canvas the crown stops 0.26 in from the edge, which the Where measure calls the edge (within 2% of 16 in). #159's 0.9 in matches the gap to the image model's frame (86 px, about 1 in). Caught on made-up scenes: the crown 0.9 in short, on its first step and on a later pass (the case H1 of the review let through); a frame test shows a crown 0.25 in short of the canvas at the edge |
| Step 11, the paths "about 9 1/2 in wide" | **no.** It's the Where line itself, and by the Where measure the paths' box is 9.3 in. The sheet agrees with the Where line by design, so it can't flag it. #159's 8.3 in came from another measure, and which one is right is a question for the Where measure |

So: 5 text items caught on the real run, plus the paint by the sheet; 1 caught only on made-up scenes; 1 not caught.
Each item is also a test on a made-up scene built to the run's geometry. The tests include the same faults worded
without "just" (which the first version let through), with the center red named as a stripe, and with each item
corrected (which must pass). `SealedLavenderTests` asserts the exact set of flags on the run, so a new false alarm
fails it.

### The sealed POC 1.12.1 lessons

All five sealed hands-off runs of 1.12.1 (`sealed` with no arguments lists them by name). The 1.12.0 lavender run
(153316) is left out because it no longer rebuilds to its pictures. They were only read.

Precision is counted per distinct fault: one wrong statement about one thing. Step 20's four flags are two faults,
the width and the height; the two `agree` flags restate them.

| Lesson | Where claims (all pass) | Other claims | Flags | Distinct faults flagged | True | False alarms | Unresolved |
|---|---|---|---|---|---|---|---|
| balloon-lavender 171639 | 84 | 43 | 8 | 6 | 6 | 0 | 3 |
| chickadee 191619 | 53 | 24 | 1 | 1 | 1 | 0 | 6 |
| red-sailboat 191627 | 61 | 26 | 1 | 1 | 0 | 1 | 8 |
| sleeping-cat 191623 | 59 | 8 | 1 | 1 | 0 | 1 | 5 |
| snow-lantern 191628 | 75 | 26 | 3 | 3 | 2 | 1 | 4 |
| **All five** | **332** | **127** | **14** | **12** | **9** | **3** | **26** |

**Precision: 9 of 12 distinct faults (75%).** Sorted by hand against the step pictures:

**True faults:**
- **Lavender (6):** step 11's "two-thirds in"; step 20's width and height; step 21; step 22 twice.
- **Chickadee step 10 (small):** "one patch about 1 1/2 in across" for a shading patch 2.7 × 1.85 in.
- **Snow lantern step 8 (small):** the lower rail "about 3 inches below" the top one. Measured: 2.4 to 2.5 in
  between them.
- **Snow lantern step 10:** the tip says the post is "about 2 inches wide", the Where line 2 1/2 in. The post's body
  is about 2 in; the Where box takes in its ragged top. Either way the painter is told two widths.

**False alarms:**
- **Red sailboat step 1:** "the setting sun, low on the horizon just left of the middle". The sun is named after
  "from", so the sky was taken as the subject.
- **Sleeping cat step 5:** "the upright post first, about 2 1/2 inches in from the left edge". The post is part of
  a wide gray frame block (1.2 to 4.3 in). No crossing or mark of the step is the post alone, and by eye its middle
  is about 2.7 in.
- **Snow lantern step 17:** "a bell-shaped glass about 2 inches wide". The glass is one piece of the lantern part.

The 26 unresolved:
- 15 are "it" or "its" with nothing named before them (8 in how and result lines);
- 10 are things that aren't parts ("the horizon", "each ear", "the shape above", and "the big hill", which is in the
  part "Golden hills");
- 1 is a length with no axis named.

**What it can't see:**
- **Facts about a piece of a part** (a lantern's glass, a frame's post, a bird's head) aren't on the sheet. That's
  all three false alarms, and most of the tip misses.
- **The paint check is narrow.** It compares paint ids (two ids with the same name pass), looks only at the part's
  last earlier step, and doesn't read the picture.

**Cost:** no renders. The sheet takes about 20 seconds for a 24-step lesson on a busy 4-core machine, on top of
building the steps. The checker takes 0.05 seconds; a full `mutate` of one lesson, a few seconds.
## The writer and the A/B run

Run 2026-11-17 on the four bench pictures with the most placement and text faults in v2's counts (highland cow,
chickadee, lavender balloon, lake cabin), against their v2 baseline lessons (`docs/spikes/v3-yardstick.md`, section 5).
The owner was told the batch's size before it started and said go.

### What was done

1. **`start <pictures>`** copies each baseline lesson to `spike/experiments/bench/runs/facts/` (git-ignored) and takes
   out everything skill step 6 wrote: summaries, tips, paint notes, and edited lines. `draft-text` then redrafts the
   lines. The adapted stroke cards (step 6c) are kept from v2: they're out of this spike's scope. The pictures, plan,
   paints and Where lines are the baseline's, byte for byte.
2. It writes one packet per stage under `<lesson>/trials/facts/stage-NN/`:
   - each step's before and after picture side by side, cropped to the canvas;
   - its drafted lines, numbered;
   - the light, and the whole lesson's step list;
   - the photo and the finish;
   - `facts.md`, the sheet's rows as plain sentences. Each length is given in the ruler value to say first, with
     the measure after it ("2 3/4 in (2.82)"), and each part and earlier mark by the name the checker finds.
3. **One writer per stage, in parallel:** 26 Opus subagents, each given only its packet and
   `v3_facts_writer.md`, which holds step 6b's rules plus the sheet's: use only its numbers and sides, say what each
   measures, name parts by the sheet's names, and say what the sheet doesn't measure without a number.
4. **`merge`** puts every stage's `out.json` into `text.json` and checks it strictly (`check_text(..., strict=True)`).
   Only failures in the writer's own words count: summaries, tips, paint notes, and lines it edited. Each stage with
   a failure gets `feedback.md` with the checker's line, and goes back to the same writer once.
5. **The lesson's own `check`.** The v2 lessons had been through skill step 7's loop, so this side got one round of
   it too: it named 7 problems in 7 stages (a paint named that the step doesn't list, two lines over 40 words, a
   missing paint note), sent to those writers once.
6. **`merge --final`** takes out any sentence still failing (`dropped.json`: 1, "inside it" on the balloon's step 12),
   then `publish`. Both sides pass `check` clean.

v2's step 7b text review in a fresh context wasn't run on this side: the checker is in its place.

### Cost and time

| | Fact-sheet words, four lessons | v2, per lesson (from the baseline traces) |
|---|---|---|
| Writing | 2 min 21 s for all 26 stage writers (20 at a time, the session's limit); 26 to 76 s each | step 6: 1.6, 2.3, 10.3 and 12.1 min |
| Checker fixes | 16 writers, 6 to 15 s each | |
| `check` fixes | 7 writers, 5 to 11 s each | |
| Tools | `start`, about 45 s a lesson; each `merge`, about 15 s a lesson, and the final one with `publish` about a minute | (in step 6's time) |
| Review | none | step 7: 3.4 to 11.3 min, check loop and fresh review |
| Renders | $0 | $0 |

From the first writer to the last fix took about 12 minutes of wall time for all four lessons, most of it the
merges and `publish`. A writer reads about 70,000 to 90,000 tokens, mostly the pictures.

### The checker on both sides

The same strict check on the words each side's writer owns (summaries, tips, paint notes, edited lines), against the
same sheet:

| Picture | v2's step-6 words: claims, failed, unresolved | Fact-sheet words, first pass: failed or unresolved, of claims | After one round of fixes |
|---|---|---|---|
| highland cow | 14, 1, 2 | 4 of 107 | 0 of 104 |
| chickadee | 21, 4, 5 | 9 of 137 | 0 of 130 |
| lavender balloon | 22, 10, 2 | 13 of 134 | 1 of 121, taken out |
| lake cabin | 21, 2, 9 | 9 of 173 | 0 of 163 |
| **All four** | **78, 17, 18** | **35 of 551** | **1** |

The fact-sheet writers make about 7 times as many checkable claims and fail 6% of them at first; v2's words fail or
don't resolve on 45%. Not every flag on v2's words is a fault: on the balloon's step 21, "4 1/2 in up from the bottom
edge" is right (the lavender's top), but the checker read it against the marks' bottoms. So the checker's own numbers
aren't the measure; the counters and graders are.

### Fault counts

One fresh fault counter per fact-sheet lesson (`spike/experiments/bench/fault_counter.md`), on Opus, given only the
brief and the lesson's packet. The v2 side is the baseline's two counters. Each cell is distinct faults (all, counting
each step a painter meets one in, in brackets where it differs); weighted is blocker 3, major 2, minor 1, over all.

| Picture | Lesson | C placement | E text | C + E | F teaching | Weighted | Per step |
|---|---|---|---|---|---|---|---|
| highland cow | v2, counter A | 3 | 6 | 9 | 1 | 71 | 4.4 |
| | v2, counter B | 4 | 7 (10) | 11 | 1 | 78 | 4.9 |
| | fact sheet | 3 | 4 | **7** | 1 | 51 | 3.2 |
| chickadee | v2, counter A | 0 | 10 | 10 | 2 | 70 | 3.9 |
| | v2, counter B | 1 | 7 | 8 | 1 | 86 | 4.8 |
| | fact sheet | 1 | 6 | **7** | 1 | 83 | 4.6 |
| lavender balloon | v2, counter A | 4 | 8 | 12 | 3 (11) | 177 | 7.4 |
| | v2, counter B | 1 | 6 | 7 | 2 (10) | 161 | 6.7 |
| | fact sheet | 2 | 7 | **9** | 4 (12) | 144 | 6.0 |
| lake cabin | v2, counter A | 2 | 4 (7) | 6 | 2 | 95 | 4.1 |
| | v2, counter B | 4 (6) | 7 (8) | 11 | 2 | 103 | 4.5 |
| | fact sheet | 2 (4) | 2 | **4** | 2 | 82 | 3.6 |
| **All four** | v2, A / B | 9 / 10 | 28 / 27 | **37 / 37** | | | |
| | fact sheet | 8 | 19 | **27** | | | |

- **C and E fell on three pictures and held on the balloon,** inside its two v2 counters' spread (7 and 12). On one
  packet two counters differ by up to about 30% (`docs/spikes/v3-yardstick.md`, Repeatability), so only the total is
  past that, and only just.
- **Most of the placement faults left are the Where lines,** which are measured and the same on both sides: the cow's
  three (the streaks' height, the grass top twice), the balloon's two (the sky's bottom, the hills' width), and the
  cabin mountain's size. The Where measure takes in only what the step's picture shows of the part, so a part that a
  later or earlier coat hides in places reads smaller than it looks. That is a question for the Where measure, not the
  writer. Two of the eight are the writer's, both from a mark on the sheet (below).
- **The weighted totals** are mostly step-picture faults (class A), the same pictures on both sides; they move with
  the counter, not the words.
- **F didn't move:** most of it is the load words ("creamy", "a light load") that come from the stroke cards, the same
  on both sides.

### The A/B

Round `s8-facts`: the four baseline lessons against the same lessons with the fact-sheet words. Two graders a
picture in fresh contexts, each given only `spike/experiments/bench/ab_grader.md` and a folder with the two lessons as
`A/` and `B/`, sides drawn from seed 173 and swapped for the second; the key is
`spike/experiments/bench/scores/s8-facts.key.json`. Every grader found the pictures byte for byte the same, so this
is a grade of the words alone, and `real` is the same on both sides for every grader.

Scores are (a) real / (b) paintable / (c) agree, 1 to 5.

| Picture | Grader | v2 | Fact sheet | Prefers | How sure |
|---|---|---|---|---|---|
| highland cow | 1 | 2 / 2 / 2 | 2 / 3 / 3 | fact sheet | fairly sure |
| | 2 | 2 / 3 / 2 | 2 / 3 / 3 | fact sheet | slight |
| chickadee | 1 | 3 / 3 / 3 | 3 / 3 / 3 | no difference | a toss-up |
| | 2 | 3 / 3 / 3 | 3 / 3 / 3 | no difference | a toss-up |
| lavender balloon | 1 | 2 / 3 / 2 | 2 / 3 / 3 | fact sheet | slight |
| | 2 | 2 / 2 / 2 | 2 / 3 / 3 | fact sheet | slight to moderate |
| lake cabin | 1 | 2 / 3 / 2 | 2 / 3 / 3 | fact sheet | slight |
| | 2 | 2 / 3 / 2 | 2 / 3 / 3 | fact sheet | slight |

**By the rule** (most pictures, and a clear loss on none; two graders who split are a tie): the fact-sheet words win
the cow, the balloon and the cabin, tie the chickadee, and lose none. They beat v2 on this round.

What decided it, in the graders' words:
- **The fact-sheet words describe the picture that's there.** v2's drafted card lines promise "curved segments with
  small gaps" for a balloon, a cabin and rocks the pictures show as one solid shape, "loose clumps with gaps of sky"
  for a solid tree, "small circles" for long streaks. The writers, looking at each before and after, rewrote those
  lines; v2's step 6 had left most of them.
- **They say what the picture adds beyond the step's paints:** the ghost blotches where the cow will stand, the tiled
  mountain, the olive mound where the cabin goes, the nose on a step that names one gold, the brown trunk. Graders
  credited this on every picture. It warns the painter but can't fix a faulty picture, so (a) didn't
  move.
- **Where it lost points:** on the chickadee both graders marked down the step 10 shade put on "the right side of
  the chickadee" (below), the cheek the step 15 tip says is covered when the picture leaves it gold, and tips
  "crowded with measurements". On the cow, step 16 puts "most of the gold on the left" against its own light from the
  right; that is what the picture shows (the bigger horn), but the words don't say why.

**Read it with these in mind.**
- The graders are Claude, grading words Claude wrote. On S4 Claude liked a side the owner didn't.
- Five of the six graders who chose a side called it "slight" or "slight to moderate". The words move a lesson less
  than its pictures do, and all four pictures score 2 or 3 on (a) on both sides.
- The fact-sheet side had no fresh-context review; the v2 side did. If anything that favours v2.

### What the sheet got wrong, through the writer

The writer says what the sheet says, and the checker passes it, so a fact that's true by the measure but misleading
on the canvas goes straight to the painter. Three kinds showed up:
- **Halves of a part with a long piece.** The chickadee's belly shade is in "the right half of the chickadee" by the
  sheet (0.92 of it), because the part's box takes in the tail far to the left; on the canvas it sits at the lower
  middle of the round body, a little left of the body's own middle. Both chickadee graders marked it down. The same
  halves gave step 9's "most of it on the right side of the chickadee" for the step that paints the whole bird.
- **A mark's size beside the area's.** The chickadee's step 10 tip gives the patch as 3 1/4 in wide (its mark); the
  Where line gives 4 1/2 in (the step's area). Both are measured; the painter is told two sizes. The `agree` check
  compares only sizes said of the step's own area.
- **The Where line itself.** Writers noticed the Where line and the sheet's ruler value differing by a quarter inch
  (the Where line rounds to the half inch from 2 in, the sheet's ruler value to the quarter), and on the balloon's
  hills a Where line that stops at 13 1/2 in where the picture runs to the right edge. They left the Where lines as
  they were, as the brief says.

The writers' other habit: when the sheet has no number, the brief says "as the after picture shows". The counters
called three of those vague (the leaf veins, the belly feathers, the eye and beak): fine for placement, not for
saying what to paint.

## What it means for v3

- **Write the words from a sheet, one writer per stage, in parallel, with the checker in the loop.** It's cheaper
  and faster than step 6 plus step 7's review, the words track the pictures better, and #159's kind of fault can't
  get through unflagged. In v3 the sheet would be measured from each layer, which is what this sheet stands in for.
- **The writer must see the before and after.** Most of what the graders credited came from the pictures, not the
  numbers: rewriting card lines that promise a result the picture doesn't show, and naming what a picture adds.
- **Fix the sheet before adopting it as is:**
  - halves and middles of a part measured on its main body, or of the mark, not the box of the whole part;
  - an `agree` check across a mark's size and the area's, or a sheet that gives the writer only the area's size and
    says when a mark is what the step adds;
  - facts for the pieces of a part (the first half's main gap, and all three of its false alarms).
- **The Where measure** is now the main source of placement faults left: what's covered or not yet painted makes a
  part read smaller than it looks. That's for the Where lines (`aids.where_words`), not the writer.
- **The stroke cards' words** are where most of the rest comes from (F, and the card lines the writers had to
  rewrite). That's S10's (#175).

## Not done

- **The other four bench pictures.** By the plan, a spike goes to all 8 only if this round looks promising; it does,
  but every v3 spike after this changes the pictures, so a second round on v2's pictures says little more.
- **A second fault counter per fact-sheet lesson.** The total is just past the counters' own spread.
- **The sheet fixes above,** and a writer for the stroke cards' adapted text.
- **One writer per lesson** in place of one per stage, to see what the split itself buys. Per stage was fast enough
  that it wasn't worth the extra round.

## Running it

    python spike/experiments/v3_facts.py sheet <lesson> [--out facts.json]
    python spike/experiments/v3_facts.py check <lesson> [--strict]
    python spike/experiments/v3_facts.py mutate [<lesson> ...]
    python spike/experiments/v3_facts.py start picked                      # copies, redrafts, one packet a stage
    # one subagent per stage folder: "follow brief.md in <stage folder>, read only that folder, write out.json"
    python spike/experiments/v3_facts.py merge picked                      # checks; feedback.md for each failing stage
    python spike/experiments/v3_facts.py merge picked --final              # takes out what still fails, publishes
    python spike/experiments/v3_facts.py grade picked --out <a folder outside the repo>

`start` reads the baseline runs from `/home/user/gesso-baseline/output` (they aren't in the repo) and writes under
`spike/experiments/bench/runs/facts/` (git-ignored). `picked` is highland-cow, chickadee, balloon-lavender and
lake-cabin.
