# Pipeline v4's gate: three bench lessons built both ways (#299)

`docs/design/pipeline-v4.md`, section 12. Run on 2026-11-21 from the branch `v4` (2.2.0 builds 1 to 4, and the rule
as the owner widened it the same day, #306), by `/paint-lesson` from this session, hands-off. The code that measures
it is `spike/experiments/v4_gate.py` (the bench, the tested steps, the blind folders and the report) with
`v4_student.py --bench`. The answers are in `spike/experiments/v4_gate.json` (the tested steps, the graders, the
student test's summary) and `spike/experiments/v4_gate/student-on.json` and `student-off.json` (every carry and
grade). The six lessons, in the bench's shape, are `spike/experiments/bench/v4-gate/on/` and `off/`.

**Verdict: every measured line passes but one, which fails as written on noise from the words: the build with the
rule has one more known problem than the one without on the cat and on the birch grove. The owner said yes to the
cow. Whether the gate passes is the owner's call.**

| Line of the gate | Needed | Result | |
|---|---|---|---|
| Both builds of each lesson seal | 6 | 6 | pass |
| The rule's build has no more known problems | ≤ | cow 4 / 4, cat 5 / 4, birch grove 9 / 8 | **fails as written** (below) |
| Checks 1 and 2 hold; nothing-stops is the same byte for byte | yes | yes; the cat's 21 step pictures are the same files | pass |
| Student test, the three together | not lower by 0.25 or more | 3.02 against 3.23 (−0.21 ± 0.18, 16 steps, three carries a side) | pass |
| Blind graders | a clear loss on no picture | the rule preferred 4 of 4 on the cow and birch grove (all slight), none 2 of 2 on the cat | pass |
| The saving | reported | cow 1.01 canvases, cat 0, birch grove 0.41 | not a pass or fail |
| The owner reads the cow and says yes | yes | "Go" (2026-11-21) | pass |

## The six lessons

Each picture was run once to its chain (`<photo>_skill_<time>`, built with `--stops`), then copied and built again
from the same chain without it (`<photo>_gate-off_<time>`). Each build had its own lesson writer (an Opus subagent in
a fresh context), its own rounds, finisher and seal. So the two sides differ by the rule and by one writer's run.

| | Highland cow | Sleeping cat | Birch grove |
|---|---|---|---|
| Lesson folders (`output/`, not in the repo) | `highland-cow_skill_20261121-102810`, `highland-cow_gate-off_20261121-102810` | `sleeping-cat_skill_20261121-141536`, `sleeping-cat_gate-off_20261121-141536` | `birch-grove_skill_20261121-141536`, `birch-grove_gate-off_20261121-141536` |
| Canvas | 12 x 16 portrait, crop | 16 x 12 landscape, extend | 16 x 12 landscape, crop |
| Beginner version | made | not needed | made |
| Steps, stages | 22, 8 | 21, 8 | 22, 7 |
| Chain renders, asked again | 14, none | 12; unit 2 twice (stays marked) | 13, then 10 again after `check`'s merge; units 1 and 2 twice (stay marked) |
| Renders, the whole lesson | $0.42 | $0.36 | $0.70 |
| check-text round 1 sent back (rule / no rule) | 9 of 50 / 15 of 61 | 29 of 53 / 19 of 39 | 12 of 53 / 12 of 55 |
| Lines `--final` emptied (rule / no rule) | 0 / 0 | 2 / 1 | 1 / 0 |
| Known problems on the page (rule / no rule) | 4 / 4 | 5 / 4 | 9 / 8 |

The cow with the rule is the lesson the owner read.

## What stopped, and what didn't

From `v3/build.json` on the rule's side (`v4_gate.json`, `steps`):

| | Stopped (its steps, where its lower edge is for most of it, what covers it) | Didn't, and why | Spared |
|---|---|---|---|
| Cow | the sky (1) and the clouds (2, 3), 3 3/4 in, the far hills (step 4); the far hills (4, 5), 5 1/4 in, the hillside (step 7) | the loch: its line hides none of its own paint; the hillside and the bushes: the cover is too narrow (the tall grass) | 1.01 canvases |
| Cat | nothing | nothing is covered from the bottom edge | 0 |
| Birch grove | the glow (1) and the far trunks (2), 6 3/16 in, the pines (step 4); the pines (4, 5) and the bushes (6, 7, 8), 8 11/16 in, the ground (step 9) | the mist: its line hides none of its own paint; the ground, the rock, the birches, the canopy: the cover is too narrow | 0.41 of a canvas |

The tested steps (each changed step, and the step after each run of them) are the cow's 1 to 7 and the birch grove's
1 to 9. The cat has none.

## The known-problems line

The design asks that the rule's build have no more known problems than the other. It has one more on the cat and on
the birch grove. In both, the extra one is a line `check-text --final` took out of the words, which is a writer's run,
not the pictures:

- **The cat:** its step pictures are the same files either way, so the rule can't have added a problem there. Its
  rule-side writer lost two lines (the wall's Start, the sill's shading) and the other side one (the ears' Start).
- **The birch grove:** the rule's side lost the rock's light step's Stop line. Its other eight problems are the
  same on both sides (the chain's units 1, 2 and 12, the pine's top, three paints, the finish).
- **The cow:** both sides have 4. Step 4's holes in the far hills are white on the rule's side and orange on the
  other; it is one problem on each.

Counted on the pictures alone (leaving out lines the words lost), the sides tie on all three: cow 4 / 4, cat 3 / 3,
birch grove 8 / 8.

## The student test

`v4_student.py` on the gate's bench, as #289 and the v3.1 gate ran it: the image model carries out each tested step's
words on its before picture, and a grader who never sees the words scores the result alone against the lesson's own
after picture, 1 to 5. Two carries a side; the two came out exactly 0.25 lower on the rule's side (2.97 against
3.22), the gate's edge, so each side got a third.

| Step | Cow, rule | Cow, no rule | Birch grove, rule | Birch grove, no rule |
|---|---|---|---|---|
| 1 | 4, 4, 4 | 4, 4, 3 | 2, 2, 2 | 3, 3, 3 |
| 2 | 4, 3, 4 | 3, 2, 3 | 3, 2, 3 | 2, 3, 3 |
| 3 | 2, 2, 2 | 2, 1, 2 | 5, 4, 5 | 4, 3, 4 |
| 4 | 3, 3, 3 | 3, 2, 3 | 2, 2, 2 | 3, 3, 2 |
| 5 | 3, 3, 3 | 4, 5, 4 | 3, 3, 3 | 3, 3, 3 |
| 6 | 3, 3, 3 | 3, 3, 4 | 3, 2, 3 | 4, 4, 4 |
| 7 | 4, 3, 3 | 4, 4, 4 | 4, 4, 4 | 4, 4, 4 |
| 8 | | | 1, 2, 2 | 3, 3, 2 |
| 9 | | | 4, 3, 4 | 4, 3, 4 |
| **Mean** | **3.14** | **3.19** | **2.93** | **3.26** |

Across the 16 steps: **3.02 against 3.23, −0.21 ± 0.18.** The cow is level (−0.05); the loss is the birch grove's
(−0.33), and most of it is steps 1, 4, 6 and 8. The spike's own number was −0.21 ± 0.21.

**What the birch grove's step 8 shows (a fault of the rule, filed below).** The bushes' render also repaints the fog
under them, so the bushes' own masks reach into the glow's bare canvas. With the glow stopped above, each bushes step
lays a band of blue fog onto that canvas, a little wider every step, with no paint of its own for it; the ground
covers it at step 9. One grader named it: "in step 8 a band of blue fog appears under the bushes that the Sunlit
lemon taps don't explain." It is the design's risk "a stopped layer's edge is the model's whole layer, cut", from the
other side: a later layer's render paints part of the stopped one.

## The blind graders

`bench/ab_grader.md`, two a picture, the rule's lesson on side A for one grader and side B for the other, each in a
fresh Opus context with one folder.

| | Grader 1 | Grader 2 |
|---|---|---|
| Cow | rule, "slight, not clear" | rule, "slight but real ... not a toss-up" |
| Cat | none (the pictures are the same files) | none |
| Birch grove | rule, "slight, close to a toss-up" | rule, "close to a toss-up" |

What they said. Of the cow without the rule: "the whole canvas below the hills is a streaky sunset sky with diagonal
bands that slope like the hillside still to come", which "reads as a ghost of the hillside"; "a lot of wasted streaky
blue-and-orange sky that the land then covers". Of the cow with it: "Steps 1-6 stop each layer at a loose line, and
the words say so and give where the edge sits, so bare canvas is never a surprise"; "The odd domed lower edge in steps
1 to 3 is a small cost"; "Step 4 still has blotchy holes in the violet, some of them bare white". Of the birch grove
with the rule: "its bare-canvas edge is a big smooth swoop that shifts from step to step"; "the pines and bushes then
sit half on white with hard white holes, and in step 8 a band of blue fog appears under the bushes that the Sunlit
lemon taps don't explain". Without it: "the mottled fog on the lower canvas looks blotchy"; "cell-like mottled
blotches no brush makes for eight steps before the ground buries them". Both birch graders decided mostly on the
words, whose placements garbled more on the side without the rule ("the left side of the blue-green pines on the
right"). Every grader said where the two sides' pictures stop differing, and that the faults after that are shared.

## The saving

Cow 1.01 canvases (its sky, clouds and far hills, steps 1 to 5), birch grove 0.41 (its glow, far trunks, pines and
bushes, steps 1 to 8), cat 0. The spike's chains spared 1.42 on the cow and 0.28 on the birch grove under
`line-1-next`; this cow's chain under `line-1-next` spared 0.02.

## Found along the way

- **The chain decides what stops, as much as the plan.** The first cow's hillside render showed sky behind it, so
  under `line-1-next` only the far hills stopped. The owner widened the rule (#306, `docs/decisions.md`).
- **Holes in a cover's render show bare canvas.** On the cow's step 4, specks inside the far hills that their render
  didn't change are white (sky without the rule). Step 5 covers them.
- **A later layer's render can paint the stopped layer back.** The birch grove's bushes (above).
- **The arc brief's clause about stopping layers was used on the cat,** where nothing stopped, to explain early bare
  canvas the chain left; it reads true there.

## Cost

- **Renders:** the three chains and finishes, $1.48 (cow $0.42, cat $0.36, birch grove $0.70); the student test's
  96 carries, $1.54.
- **Claude:** grading the carries, $3.09; six lesson writers, two plan writers (and one change), three chain checkers
  (five rounds), six blind graders and the #306 review ran as subagents in this session, whose cost isn't metered
  here.

## Not run

The owner painting one (#252). Rerunning the site's other lessons (#288).
