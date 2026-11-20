# v3.1's gate: three bench lessons from the branch (#279)

`docs/design/pipeline-v3.1.md`, section 13. Run on 2026-11-20 from the branch `v3.1` (builds 1 to 3, #276 to #278),
by `/paint-lesson` from this session, hands-off. The code that measures it is `spike/experiments/v31_gate.py` (the
bench and the blind folders) with `v4_student.py --bench`. The answers are in `spike/experiments/v31_gate.json`
(graders, the student test's summary) and `spike/experiments/v31_gate/student.json` (every pick, carry and grade).
The lessons, in the bench's shape, are `spike/experiments/bench/v31-gate/`.

**Verdict: pass on every measured line. The owner's read is the last line, and it is open.**

| Line of the gate | Needed | Result | |
|---|---|---|---|
| Three hands-off lessons, sealed | 3 | 3 | pass |
| Student test, each lesson | no lower than v3's words | 3.55 / 3.40 / 3.15 against 3.15 / 3.21 / 3.02 | pass |
| Student test, across the three | higher | 3.37 against 3.13 (+0.24) | pass |
| Blind graders | prefer on most pictures, no clear loss | 6 of 6 reads, both sides of every picture | pass |
| The owner reads one and says yes | yes | open: the highland cow | |
| Claude cost, beside the $1 aim | reported | about $3 (below) | not a pass or fail |

## The three lessons

| | Highland cow | Sleeping cat | Birch grove |
|---|---|---|---|
| Lesson folder (`output/`, not in the repo) | `highland-cow_skill_20261120-193553` | `sleeping-cat_skill_20261120-193553` | `birch-grove_skill_20261120-193553` |
| Canvas | 12 x 16 portrait, crop | 16 x 12 landscape, extend | 16 x 12 landscape, crop |
| Beginner version | made | not needed | made |
| Steps, stages | 22, 8 | 20, 7 | 20, 7 |
| Chain renders, asked again | 15, none | 12, none | 12, units 5 and 9, then 1, 4 and 9 (two rounds) |
| Changes `check` sent the plan's writer at C3 | two brushes a card doesn't take, one merge | none | one merge |
| Renders, the whole lesson | $0.37 | $0.38 | $0.72 |
| check-text round 1 sent back | 2 of 48 claims | 22 of 36 | 6 of 58 |
| Round 2 (paints, long lines) | none | 1 paint | none |
| Sentences `--final` took out, lines emptied | 1, Leave of step 21 | 1, Start of step 16 | 1, Leave of step 17 |
| Arc: back lines, words, round | 17, 635, none | 11, 614, one back line | 14, 622, none |
| Diagrams drawn | 2 of 2 | 5 of 5 | 2 of 2 |
| Known problems on the page | 2 | 5 | 4 |

Every helper was an Opus subagent in a fresh context: steps 0 and 1, the plan's writer, the chain's checker, the
lesson's writer (its rounds and its arc as messages to the same writer, as run.md says) and step E. The subagent
writer, the guess section 12 named, worked: it read `words/lesson/`, wrote the same JSON, and answered each round
with only the steps it changed. Two of three writers wrote to the pictures where they differed from the plan, and
said so.

## The student test

`v4_student.py` on the new bench, as #254 ran it: carry graded alone (the image model does the words on the before
picture; a grader who never sees the words scores the result against the real after, 1 to 5), and pick on the
words and on the header alone. The stage lines go above each step of the stage, the end line above its last, and the
"As in step N" line among the step's lines, as #267's packets had them. v3's numbers are its frozen bench's.

| | Cow | Cat | Birch | Across |
|---|---|---|---|---|
| v3 (bench/v3-words) | 3.15 | 3.21 | 3.02 | 3.13 |
| The spikes' teacher (#254, lesson-slots, on v3's pictures) | 3.43 | 3.38 | 3.20 | 3.34 |
| **v3.1, from the branch** | **3.55** | **3.40** | **3.15** | **3.37** |

The cow clears the 0.25 bar; the cat and the birch grove are higher by less than it. A lesson's mean moved 0.12
between two runs in #174.

**Word faults (pick):** a step whose words score 0.25 or more below its header alone. One: the birch grove's step
13 (0.14 against 0.55), where "fewer go near the fog, so the back stays calm" led the reader to the picture with
only half the leaves. v3 had four (the cow's 2, the cat's 2, the birch grove's 10 and 20). The words lift the
reader's chance on the real after over the header alone by 0.12, 0.17 and 0.09 (cow, cat, birch), against v3's
0.12, 0.18 and 0.09: about the same, from a higher start.

## The blind graders

`bench/ab_grader.md`, two a picture, the new lesson on side A for one grader and side B for the other, each in a
fresh Opus context with one folder.

| | Grader 1 | Grader 2 | real, paintable, agree (v3.1 / v3), both graders |
|---|---|---|---|
| Cow | v3.1, clear | v3.1, slight to clear | 4,4,4 / 3,2,2; 3,3,3 / 3,2,2 |
| Cat | v3.1, clear | v3.1, fairly sure | 3,3,3 / 2,2,2; 3,4,3 / 3,2,2 |
| Birch | v3.1, sure | v3.1, clear | 3,3,3 / 2,1,2; 3,4,3 / 2,2,2 |

**Read this with its limit.** v3's lessons and these were each made from scratch, so the pictures differ too, and
two lessons from scratch differ enough to decide a grader (`docs/spikes/v4-cost-cuts.md`). The graders' notes name
both: v3's words pointing at an outline and a paint map the folder doesn't have, and v3's sizes that don't fit
("a nose area 5 in tall"), but also pictures (v3's cat opens on four steps that show no leaves; its birch grove
grows a row of middle birches on a step that names five trunks). Where the two lessons' pictures share a fault
(the cow's hillside jump, the cat's shading jump), graders said so and decided on the words. So 6 of 6 is the
words and the new pictures together, not the words alone.

The faults the graders marked on the new lessons are in the pictures: the cat's blanket and shading jumps (steps 11
and 14), the birch grove's far birches going from blobs to finished trunks (step 7) and its cut-out bark shading
(step 15), the cow's coat going from shaded to locked in one step (14).

## What it costs

**Claude, from the loop:** $2.98 at the API's rates for the sleeping cat, sealed by `v4_loop.py` on the new
run.md after build 3 (`docs/spikes/v31-build3-cat.md`), against the design's "about $3.13". One run. About three
times the $1 aim. A `/paint-lesson` run is on the owner's subscription and logs no tokens, so these three lessons
have no Claude cost of their own; the loop wasn't run again on the cow and the birch grove.

**Renders:** $0.37, $0.38 and $0.72 a lesson. The birch grove's was the chain's checker's two redo rounds (9
renders each).

**The gate itself:** the student test's renders $0.98, its Claude calls $8.13 at the API's rates (210 calls); the
graders ran as subagents.

## What happened on the way

- **The cow's checker read a chain whose looks were then written again.** This session ran the cow's first
  chain's checker before C3 (run.md has it after). C3's three plan changes rendered nothing, but `erase` wrote the
  looks again without `answers.json`, so the seal refused. A second checker read the same chain, marked nothing,
  and the seal went through. The order in run.md is right; this run didn't follow it.
- **The disk filled** while the student test rendered (old spikes' work folders under `/tmp`). 19 carries and 13
  header picks failed and were run again; nothing was lost from the results file.
- **One grader wrote over 8 step pictures in its own copy** of the cat's blind folder (a `montage` with its
  arguments the wrong way round). It graded from the pair pictures, which were whole; the bench's pictures aren't
  touched.
- **packet.py looks for `photo.png`,** which a v3.1 run doesn't write; `v31_gate.py` puts the fitted photo in its
  place.
- **The lessons are stamped POC 2.0.2,** the branch's version: the bump to 2.1.0 comes with the merge.

## Limits

- The A/B was blind by label only. No file names a pipeline and the key sat outside the folders, but the step
  pictures kept their file dates (v3's from 2026-11-18, the new ones from today; `side_folder` now copies without
  them), and the new side's lesson has an opening and labeled lines, which is the lesson itself.
- One run of each lesson. The cat's and the birch grove's gains are inside what the test moves between runs; the
  cow's isn't.
- Carry compares the new words on the new pictures with v3's words on v3's pictures. The near misses and the grade
  are each lesson's own, so a lesson whose steps are easier to follow scores higher whatever the words.
- Neither test showed the page's outline and Where picture.
- A student made of models is not a painter (#252).
