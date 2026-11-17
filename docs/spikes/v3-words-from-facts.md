# Spike S8: words from a measured fact sheet (#173)

2026-11-16, revised the same day after the adversarial review of PR #182. Pipeline v3 plan, wave 3
(`docs/design/pipeline-v3-plan.md`). The code is `spike/experiments/v3_facts.py`, the tests
`spike/tests/test_v3_facts.py`. Nothing in the pipeline changed, and no render was made.

**Verdict: open.** The fact sheet and the checker are built and tested.
- **Planted faults:** a fault put into a measured Where line is caught 97 to 100% of the time, depending on the
  kind. A fault put into Claude's written tips is caught 41 to 94% of the time.
- **#159 on the sealed run it came from:** 5 of #159's 8 items are caught there as text faults, and a sixth (the
  paint) by the sheet. One more is caught only on a made-up scene, and one isn't caught.
- **The five sealed 1.12.1 lessons:** 9 of 12 distinct flagged faults are real.

Whether writing from the sheet cuts placement and text faults is the A/B against #165's v2 baseline, which
doesn't exist yet. The writer isn't built; its prompt shape is below.

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

## The writer, for the A/B run

Not built: it waits on #165's frozen bench. The writer would be one Claude call per stage, in parallel, each given:

1. **The pictures:** the picture before and after each step of the stage, cropped to the canvas.
2. **The sheet's rows for those steps,** as short plain facts in the Where line's ruler steps:

       Step 21 (balloon-red), the balloon, a pass in Deep balloon red.
       It adds 2 stripes. At the balloon's middle row: stripe 1 from 2.67 to 2.97 in from the left edge (0.16 of
       the way across the balloon), stripe 2 from 3.81 to 4.03 in (0.55). The balloon's middle is 3.77 in.
       The balloon: 2 1/2 in from the left edge, 1/2 in from the top edge, 3 in wide, 3 1/2 in tall, inside the
       sky.
       Under it: Sunset orange from step 20.
       Where line (keep as is): Inside the outlined area. Its top is about 1/2 in from the top edge, ...

3. **The rules:**
   - Write each step's `summary` and `tip`, and fix any drafted line that reads wrong, as skill step 6 says today.
   - Use only numbers and sides that are on the sheet, each with what it measures ("its top is ... from the top
     edge", "... wide").
   - Name parts by the sheet's names, and earlier marks by their paint ("the Deep balloon red stripe"), so every
     claim resolves.
   - When the picture shows something the sheet doesn't (a piece of a part, a gap), describe it without a number or
     a side, or say "as the Where picture shows".
4. **The check:** the stage's tips and summaries go through `check_text(..., strict=True)`. Each failure, in the
   form above, goes back to the same writer once, with the sheet's fact. A stage that still fails keeps its failing
   sentences out, and the run records them.

The A/B writes the same frozen bench lessons twice: once by today's skill step 6 and once by this writer. It
measures:
- placement and text faults (classes C and E), from #165's fault counter and the owner's blind scores;
- the time of the text phase: one writer per stage in parallel, against one pass over all steps.

## Verdict: open

It waits on #165's v2 baseline for the placement and text fault-count comparison.

**Settled now:**
- the sheet can be measured for any lesson the tools build;
- a fault planted in a Where line is caught 97 to 100% of the time, and there are no false alarms on the
  unmutated Where lines;
- 5 of #159's 8 items are caught as text faults on its own run, plus the paint by the sheet;
- 9 of 12 distinct faults flagged on the sealed lessons are real.

**Not settled:**
- In tips, planted faults are caught only 41 to 94% of the time, depending on the kind.
- The main gap is facts for the pieces of a part. If the A/B goes ahead, that's the first thing to add: it would
  also clear the three false alarms.
