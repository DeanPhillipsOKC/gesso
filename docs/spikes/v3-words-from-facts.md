# Spike S8: words from a measured fact sheet (#173)

2026-11-16. Pipeline v3 plan, wave 3 (`docs/design/pipeline-v3-plan.md`). The code is
`spike/experiments/v3_facts.py`, the tests `spike/tests/test_v3_facts.py`. Nothing in the pipeline changed, and no
render was made.

**Verdict: open.** The fact sheet and the checker are built and tested. The checker catches every fault #159
lists, passes every measured Where line, and on the five sealed POC 1.12.1 lessons 9 of its 11 flags are real
faults. Whether writing from the sheet cuts placement and text faults is the A/B against #165's v2 baseline, which
doesn't exist yet. The writer isn't built; its prompt shape is below, ready for that run.

## What the sheet holds

One sheet per lesson (`sheet <lesson>`, about 100 KB of JSON), measured from the step pictures and the plan. It
uses the measure the Where lines use (`build_steps.visible`, cropped to the canvas, without stray specks), so a
sheet and its Where line can't disagree. All distances are inches on the painter's canvas.

Per part, as the finish shows it: its box (each side's distance from its own canvas edge), size, middle, the
canvas edges it reaches, where it meets each of them (two paths meet the bottom edge twice), its peak, the row
where it's widest, and which side of every other part it sits on (read locally: the sun is above the mountains
where they dip under it, though both sit in one band), whether they touch and the gap between them.

Per step:

- **its area**, measured as above: the thing the Where line describes;
- **its marks**: each piece of what the step changes, biggest first (up to 8), placed on the canvas and inside its
  part. For a part's last step, which shows everything left of the finish, the marks are read from the pixels
  near one of the step's own paints (within 25 Lab units), so a deck line isn't lost in the hull's texture;
- **crossings**: where the marks cross the part's middle row, and four more rows (25%, 40%, 55% and 70% down
  the part). Stripes joined at the top of a balloon are one mark but separate crossings, and "left of" and
  "inside" between stripes are read on these;
- **what it adds**: the median color of what changes, how far each named paint is from it, and how much of it
  lands in each half of the part;
- **the paints it names**, and a paint it lays over the same paint from the step before it on the part;
- **every other part**: which side this step sits on, touching or not, the gap across and down;
- the measured Where line, word for word.

The sheet's `tolerance`: a length within 1/8 in + 0.05 in under 2 in, and 1/4 in + 0.05 in from 2 in (half the
Where line's rounding step, plus a ruler read by eye; the step is taken from the larger of the two values, so
"about 2 in" is read on the half inch); a share of the way across within 0.06.

## What counts as a claim

The checker reads every number and every side or position word in a step's summary, tip, lines and paint notes.
Each one is either a claim, checked against that step's sheet, or one of the kinds of word that isn't, which are
counted and never failed.

| Claim | Example | Checked against |
|---|---|---|
| length | "about 2 in from the left edge", "3/4 inch across", "two inches wide", "half an inch" | the sheet's lengths on its axis: wide or from the left or right edge across, tall or from the top or bottom edge down, "across" either, "apart" the gaps between marks |
| edge | "at the right edge", "reaches the bottom edge", "all the way across", "stops short of" | the canvas edges its subject reaches; for a pass inside a painted part, also the part's own edge ("along the far left edge" of a balloon) |
| fraction | "a third of the way in", "two-thirds in", "halfway down" | its subject's places as shares of the canvas, and of the part ("widest a third of the way down") |
| center | "just left of the center" | the canvas's middle, or the part's for marks added inside a painted part; "just" is within 20% of its width |
| relation | "above the hull", "just inside the left red stripe", "on its right" | another part (local sides, gaps), or the crossings an earlier step put on this part, named by their paint's color |
| position | "at the upper right", "down the right side of the canvas" | its subject's middle; for a pass inside a part, which halves its paint lands in |
| side | "the olive goes on the left side", "down the post's left half" | at least half of the paint it adds in that half of the part (15% with "too", "also", "some") |
| agree | the Where line's "3 in wide" and the tip's "2 1/2 inches wide" | two sizes of the step's own thing on one axis in one step must agree |

Not claims: stroke directions ("left to right", "side to side", "top to bottom" as a stroke, "pulled to the lower
left"), brush sizes ("1/2 inch flat", "#6 round"), step numbers, counts ("two coats", "three stripes"), side
words that name one of several things ("the left path", "the right-hand triangle": the label picks which marks a
number or relation is checked on), the light's direction, the edge of a thing rather than of the canvas ("its top
edge", "the edges of the balloon"), "outside" meaning out of doors, and a side within a thing's own shape on its
first step ("the head on its upper right").

The subject of a claim is the first part named in its clause that isn't the object of a preposition ("a lumpy
shape on the top of the big hill at the right edge" is about the crown, not the hill), or a part named as a place
("around where the sun will go"); otherwise the step's own area, marks and part. A claim whose reference names
nothing on the sheet ("below it", "the horizon", "each ear") is **unresolved**: reported, failed only with
`--strict`. Something said of what's left showing ("leave two gold patches showing a quarter of the way in") is
unresolved too: gaps aren't on the sheet.

Each failure names the step and the field, quotes the words, says what they claim and what the sheet says:

    step 22 (balloon-blue), tip: "on its right" says just right of step 21's red (center one); sheet: step 21's
    red (center one) at 3.81-4.03 in; this step's touching stripes: 3.36-3.81 in (inside, left of)

## Results

### The three fixture lessons

After `draft-text` (the fixtures have no tips, so their written lines are the drafted card lines):

| Fixture | Where-line claims | Passed | Claims in the other lines | Flags | Unresolved | Words that aren't claims |
|---|---|---|---|---|---|---|
| Chickadee | 56 | 56 | 0 | 0 | 0 | 97 |
| Lavender balloon | 62 | 62 | 0 | 0 | 0 | 111 |
| Red sailboat | 52 | 52 | 1 | 0 | 1 ("paint below it") | 76 |

Every Where line passes, as it must. The card lines hold no placement claims, and their side words ("strokes long,
left and right") aren't flagged.

### The faults in #159

Each is a test case. The run's own words are checked against small made-up scenes built to the run's measured
geometry (the run is in `output/`, not in the repo); a second test runs on the sealed run itself when it's there.

| #159 fault | Words | Caught by |
|---|---|---|
| Step 21, center stripe mirrored | "one just left of the center" | center: the center red's middle is 3.92 in, the balloon's 3.77 |
| Step 22, first blue stripe mirrored | "one just inside the left red stripe" | relation: the touching blue is outside it |
| Step 22, second blue stripe mirrored | "right beside the center red stripe, on its right" | relation: the touching blue is on its left ("beside" alone passes) |
| Step 20, sizes disagree | the Where line's "3 in wide ... 3 1/2 in tall", the tip's "2 1/2 inches wide and 3 inches tall" | agree, twice; and length, for "3 inches tall" (measured 3.55) |
| Step 16, crown "at the right edge", 0.9 in short | "its right side is at the right edge" | edge, on a made-up crown 0.9 in short |
| Step 11, right path "about two-thirds in" | "the right one about two-thirds in" | fraction: it meets the bottom edge 0.81 of the way across |
| Step 13, a pass in the base coat's paint | (no words) | the sheet: Shadow violet over Shadow violet from step 10 |

All 7 are caught. Two notes on the sealed run itself:

- **Step 16 isn't a fault in the painter's canvas.** #159's 0.9 in matches the gap to the edge of the image
  model's frame (the crown stops 86 px, about 1 in, short of it). In the canvas (`canvas_box` [0.07, 0, 0.96, 1])
  the crown stops 0.26 in from the right edge, and the Where measure calls
  anything within 2% of the width (0.32 in on 16 in) the edge. So the sealed line passes; the case is a made-up
  crown, as #159 describes it. Whether 1/4 in should count as the edge is a question for the Where measure, not
  this checker.
- **Step 11's "about 9 1/2 in wide" is the Where line itself.** By the Where measure the paths are 9.3 in across;
  #159's 8.3 in was another measure. The sheet agrees with the Where line by construction, so this can't be a flag.

### The sealed POC 1.12.1 lessons

All five sealed hands-off runs of 1.12.1 in `output/*_skill_20261116-*` (the 1.12.0 lavender run, 153316, no
longer rebuilds to its pictures, so it's left out; the five below rebuild byte for byte). Read only.

| Lesson | Where-line claims (all pass) | Claims in tips, summaries, other lines | Flags | True faults | False alarms | Unresolved |
|---|---|---|---|---|---|---|
| balloon-lavender 171639 | 84 | 43 | 7 | 7 | 0 | 3 |
| chickadee 191619 | 53 | 24 | 1 | 1 | 0 | 5 |
| red-sailboat 191627 | 61 | 26 | 1 | 0 | 1 | 8 |
| sleeping-cat 191623 | 59 | 8 | 0 | 0 | 0 | 5 |
| snow-lantern 191628 | 75 | 26 | 2 | 1 | 1 | 4 |
| **All five** | **332** | **127** | **11** | **9** | **2** | **25** |

Precision 9 of 11 (82%). Plus one paint fault from the sheet (the lavender's step 13). The flags, sorted by hand
against the step pictures:

- **Lavender, true (7):** the five #159 faults above that the sealed run still has (step 11's "two-thirds in";
  step 20's "3 inches tall" and both size disagreements; step 21; step 22 twice).
- **Chickadee step 10, true (small):** "one patch about 1 1/2 in across" for a shading patch 2.7 by 1.85 in.
- **Snow lantern step 10, true (the Where line is the one that's off):** the tip says the post is "about 2 inches
  wide", the Where line 2 1/2 in. The post's body is about 2 in across; the Where box takes in its ragged top. A
  painter is still told two widths.
- **Red sailboat step 1, false alarm:** "the setting sun, low on the horizon just left of the middle". The sun
  is just left of the middle; the checker read the sky as the subject, since the sun is named after "from".
- **Snow lantern step 17, false alarm:** "a bell-shaped glass about 2 inches wide". The glass is one piece of
  the lantern part; the sheet only has the whole lantern (2.45 in).

The 25 unresolved are references the sheet doesn't hold: 15 are "it" or "its" with nothing named before them in
the sentence (8 of those in how and result lines, such as "paint below it"), and 10 are things that aren't parts
("the horizon", "the dark shoreline band", "each ear", "the shape above", and "the big hill", which is one of the
part "Golden hills" and named in the singular). None is a fault.

Besides the claims, 871 side words and numbers were read and sorted as not claims: 386 labels, 155 counts, 102
step numbers, 76 brush sizes, 39 stroke directions, 7 light directions, and 106 other ("the edge" of a thing, "on
top", "the middle of the glass").

**What it can't see.** A claim about a piece of a part (the glass of a lantern, the head of a bird, the far
ridge of the mountains) is checked against the whole part, or the step's marks; that's both false alarms above.
Recall beyond #159 wasn't measured: there's no hand count of faults in these lessons to measure it against. That's
what #165's fault counter is for.

**Cost.** No renders. The sheet took about 20 seconds for the lavender run (24 steps, on a busy 4-core machine)
on top of building the steps, which every tool already does; the checker 0.05 seconds.

## The writer, for the A/B run

Not built: it waits on #165's frozen bench. The writer would be one Claude call per stage, in parallel, each given:

1. **The pictures:** for each step of the stage, the picture before it and after it, cropped to the canvas.
2. **The sheet's rows for those steps,** as short plain facts, every number already in the Where line's ruler
   steps:

       Step 21 (balloon-red), the balloon, a pass in Deep balloon red.
       It adds 2 stripes. At the balloon's middle row: stripe 1 from 2.67 to 2.97 in from the left edge (0.16 of
       the way across the balloon), stripe 2 from 3.81 to 4.03 in (0.55). The balloon's middle is 3.77 in.
       The balloon: 2 1/2 in from the left edge, 1/2 in from the top edge, 3 in wide, 3 1/2 in tall, touching the
       sky on all sides.
       Under it: Sunset orange from step 20.
       Where line (keep as is): Inside the outlined area. Its top is about 1/2 in from the top edge, ...

3. **The rules:** write each step's `summary` and `tip` (and fix any drafted line that reads wrong, as skill step
   6 says today). Use only numbers and sides that are on the sheet. Name parts by the sheet's names, and earlier
   marks by their paint ("the Deep balloon red stripe"), so every claim resolves. When the picture shows
   something the sheet doesn't (a piece of a part, a gap), describe it without a number or a side, or say "as
   the Where picture shows".
4. **The check:** the stage's text goes through `check_text(..., strict=True)` for its tips and summaries; each
   failure, in the form above, goes back to the same writer once with the sheet's fact. A stage that still
   fails keeps its failing sentences out, and the run records them.

The A/B: the same frozen bench lessons written twice, once by today's skill step 6 and once by this writer;
placement and text faults (classes C and E) counted by #165's fault counter and the owner's blind scores, and the
text phase timed (one writer per stage in parallel against one pass over all steps).

## Verdict: open

It waits on #165's v2 baseline for the placement and text fault-count comparison. What's settled now: the sheet
can be measured for any lesson the tools build, it agrees with every Where line, and the checker catches all of
#159's faults with 2 false alarms in 11 flags on the five sealed lessons. If the A/B goes ahead, the two false
alarms point at the one gap worth closing first: facts for the pieces of a part (a lantern's glass, a bird's
head), which the sheet doesn't have.
