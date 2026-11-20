# v4 cost (C3): the lesson writer, the arc call and the finisher (#267)

Wave 3, step 4 of `docs/design/pipeline-v4-plan.md`, under #240. Run on 2026-11-19. The code is
`spike/experiments/v4_writer_cost.py` (the bench, the words, the finisher, the cuts and the blind graders), with
three small additions elsewhere: `v4_loop.call_claude` takes a model and an effort, `v4_loop.py run --until checker`
stops a lesson after the chain's checker, and `v4_student.py --bench` reads another bench's lessons. Its test is
`spike/tests/test_v4_writer_cost.py`. The numbers are in `spike/experiments/v4_writer_cost.json` (`calls`: every
call; `words`, `finish`: what each variant wrote; `ab`: every grader; `report`: the sums below). The student test's
answers are in `spike/experiments/v4_writer_cost/<variant>.json`. None of the lessons is on the site.

**Verdict (accepted by the owner, 2026-11-20, `docs/decisions.md`): adopt the lean words (`lean`) and the lean finisher (`f-lean`); drop Sonnet on both sides, the split
finisher and the finisher at low effort; park the words at low effort.** With the two adopted, the words and the
finisher cost **$1.34 a lesson against $2.14** (−$0.80, −37%), and a whole lesson **about $3.06 of Claude at the
API's rates**, against **$3.86** for Wave 1's words made the same way (sums of the unrounded means). That is still about three times the $1 aim.

- **The lean words are no worse.** The student test scores them level (3.29 against 3.21, +0.08 ± 0.10), and the
  blind graders saw no difference in 5 of 6 reads, preferring the baseline in the sixth ("slight, close to a
  toss-up"). They cost $0.85 a lesson against $1.33.
- **The lean finisher is no worse.** The graders preferred it 4 times and the baseline none, with 2 ties, every win
  slight. It costs $0.50 against $0.80.
- **Sonnet is worse on both sides.** Its words fell 0.30 ± 0.11 on the student test (22 steps fell, 11 rose) and lost
  5 of 6 blind reads. Its finisher lost 5 of 6, with two diagrams that drew as error text. A smaller model would have
  been the owner's call anyway (`docs/decisions.md`, lessons are made on Opus); this says don't.

## What was run

The words and the finisher run on the pictures of C1's three lessons made with all of its cuts (the highland cow,
`output/highland-cow_v4loop_20261119-183415`; the sleeping cat, `-183421`; the birch grove, `-183427`). No chain was
rendered again, so a cut's two sides share every picture and only the words or the finisher differ (the owner's
call, 2026-11-19: about $3.70 of renders). C1's null round showed that two lessons made from scratch differ enough in
their pictures to decide a grader (`docs/spikes/v4-cost-cuts.md`); sharing the pictures takes that out. One new cat
lesson was made too, with C1's cuts up to the chain's checker, for #250 (below), and got the baseline's words and
finisher.

**The baseline** is Wave 1's adopted words as v4 will run them, on Opus at Claude Code's default effort (medium),
cached the API's way (C1's cut 2):

- **The writer**: `v4_teacher.py`'s lesson-slots, one conversation for the whole lesson. Its message is the brief,
  every step's header and card, plan.json, the fact sheet, and each step's before-and-after pair (784 pixels a half)
  and change picture, then the photo and finish at 1,024. check-text's failures go back once, and it writes the whole
  JSON again. What still fails is taken out.
- **The arc**: `v4_arc.py`'s arc-add-long, its own call after the writer. It gets the brief, plan.json, the headers,
  the cards, the finished words, the photo, the finish and each stage's last picture. Its checks' failures go back
  once.
- **The finisher**: `v4_loop.Run.finish`'s D4 and E2 on a copy of the lesson with the v4 words in text.json: run.md
  and step 8's three files, what the tools printed, plan.json, the words (opening, stage openers, steps), notes.json,
  every step picture at 768 pixels and the finish. It writes review.json, the construction diagrams and the notes in
  one reply. Then `publish` and `preview-diagrams`, and a second message to look at the diagrams. No seal:
  `publish --final` holds v3's text rules (a summary and a tip a step, 40 words a line), which the v4 words don't
  follow. That waits for v4's build.

**The cuts.** The words' cuts were run as sets, since the render budget allowed three student tests:

| Set | What changes |
|---|---|
| `lean` | `pics-small`: the pair halves and change pictures at 512 pixels (from 784), the photo and finish at 768, the arc's stage pictures at 480. `facts-lean`: the fact sheet without what the lines don't use (the exact values in brackets the brief forbids, v3's Where line, the part as the finish shows it, the neighbours not painted yet; check-text still reads the whole sheet). `feedback-changes`: the writer answers check-text with only the steps it changes. `arc-same`: the arc is the writer's conversation's next message, so it reads the plan, the cards and the pictures from the cache. |
| `lean-low` | `lean`, at low effort |
| `lean-sonnet` | `lean`, on Claude Sonnet 5.5 |

| Finisher | What changes |
|---|---|
| `f-lean` | the step pictures at 384 pixels (from 768), the finish at 512; the second message (look at the diagrams) only when `publish` draws fewer diagrams than were written |
| `f-split` | `f-lean`, with review.json and the notes from one call with no pictures, and the diagrams from a second call sent only diagrams.md, plan.json, the words and the pictures |
| `f-lean-low` | `f-lean`, at low effort |
| `f-lean-sonnet` | `f-lean`, on Claude Sonnet 5.5 |

Every finisher variant ran on the baseline's words, so the two sides of its A/B differ only in the diagrams and the
Known problems list.

## Cost

In dollars of Claude at the API's rates (`v4_loop.api_costs`, Opus 5.5 at $4 / $20 a million tokens, Sonnet 5.5 at
$2 / $10). One run a variant a picture.

**The words:**

| Set | Cow | Cat | Birch | Mean | Words a lesson |
|---|---|---|---|---|---|
| baseline | 1.34 | 1.31 | 1.36 | **1.33** | 2,870 |
| `lean` | 0.81 | 0.91 | 0.81 | **0.85**, −0.49 | 2,590 |
| `lean-low` | 0.68 | 0.66 | 0.59 | 0.64, −0.69 | 1,870 |
| `lean-sonnet` | 0.43 | 0.41 | 0.43 | 0.42, −0.91 | 2,710 |

Where the lean set's $0.49 comes from, call by call (means over the three pictures):

| Call | Baseline | `lean` |
|---|---|---|
| The writer's message | $0.83: 92,800 tokens sent (42,600 of them pictures), 18,500 written (12,300 thinking) | $0.49: 59,900 sent (21,700 pictures), 9,600 written (3,700 thinking) |
| check-text's round | $0.23: the whole JSON again, 6,700 written | $0.12: the changed steps, 2,700 written |
| The arc | $0.24 sent fresh (28,800 tokens), and a feedback round on 1 of 3 ($0.03 a lesson) | $0.14, 70,600 tokens read from the writer's cache, and a feedback round on all 3 ($0.09) |

The writer's thinking fell by two thirds on smaller pictures and a shorter sheet. That is one run a side, so how
much of it is the cut and how much the run isn't known. The arc as the writer's next message saved $0.10 but took
a feedback round every time (3 of 3 against 1 of 3), which gave back $0.06 of it.

**The finisher:**

| Finisher | Cow | Cat | Birch | Mean | Diagrams (cow, cat, birch) |
|---|---|---|---|---|---|
| baseline | 0.78 | 0.87 | 0.75 | **0.80** ($0.63 the reply, $0.17 the look) | 7, 9, 5 |
| `f-lean` | 0.50 | 0.50 | 0.48 | **0.50**, −0.31 | 7, 9, 5 |
| `f-split` | 0.51 | 0.63 | 0.52 | 0.55, −0.25 | 3, 8, 4 |
| `f-lean-low` | 0.35 | 0.60 | 0.31 | 0.42, −0.38 | 7, 9, 5 |
| `f-lean-sonnet` | 0.21 | 0.21 | 0.18 | 0.20, −0.60 | 7, 9, 5 |

- **`f-lean` never sent the look.** Every diagram it wrote drew, on all three, so the second message ($0.17) was
  left out each time. The smaller pictures took the reply from 12,100 picture tokens to 3,100 and from $0.63 to $0.50.
- **Splitting the finisher cost more than not splitting it.** Two calls each sent their own instructions, and
  between them wrote about as much as one.
- **`f-lean-low` needed its JSON asked for again on the cat** ($0.21 of its $0.60).

**The whole lesson**, the rest of it from C1's runs with all its cuts (steps 0 and 1 $0.35, the plan's writer $1.03,
the chain's checker $0.34):

| | Steps 0 to the checker | Words | Finisher | Lesson |
|---|---|---|---|---|
| C1's lesson (v3's stage writers) | $1.72 | $0.96 | $0.97 | $3.65 |
| Wave 1's words, made as v4 runs them (the baseline here) | $1.72 | $1.33 | $0.80 | **$3.86** |
| With `lean` and `f-lean` | $1.72 | $0.85 | $0.50 | **$3.06** |
| The new cat (below), made as the baseline | $1.33 | $1.42 | $0.64 | $3.39 |

Against the $1 aim, $3.06 is about three times over. What's left, largest first: the plan's writer ($0.72 to
$1.03), the words ($0.85), the finisher ($0.50), steps 0 and 1 ($0.30 to $0.35) and the chain's checker ($0.31 to
$0.34, #221's). Output is the biggest single part of the words: their calls write about 32,000 tokens a lesson in the
baseline (half of it thinking) and 19,000 in `lean` (30% thinking). Lower effort is the obvious lever left there,
but it made both the words and the finisher a little worse (below).

## The student test

`v4_student.py`'s carry it out, graded alone (`docs/spikes/v4-student-test.md`), on all 66 steps of the three
lessons, with each variant's words as the page shows them (a stage's opener above its steps, its end on the last).
Its baseline is this spike's own words on these pictures, not v3's: the pictures differ from the frozen bench's, so
Wave 1's scores (3.43, 3.38, 3.20) don't compare.

| Words | Cow | Cat | Birch | All 66 steps | Against the baseline | Steps rose / fell |
|---|---|---|---|---|---|---|
| baseline | 3.36 | 3.00 | 3.30 | 3.21 | | |
| `lean` | 3.41 | 3.21 | 3.25 | 3.29 | **+0.08 (± 0.10)** | 22 / 16 |
| `lean-sonnet` | 3.27 | 2.67 | 2.80 | 2.91 | **−0.30 (± 0.11)** | 11 / 22 |

(± is one standard error of the mean step difference.) `lean` is level, inside one standard error. `lean-sonnet`
fell on all three pictures, most on the birch grove (−0.50) and the cat (−0.33), about 2.7 standard errors in all.
`lean-low` had no student test: the render budget allowed three sets.

## The blind graders

`ab_grader.md`'s rubric, two graders a picture with the sides swapped, one call each. The two lessons share every
picture, so each step's picture went in once with both lessons' words under it (the words' rounds), or once with both
lessons' diagrams and Known problems after the steps (the finisher's rounds).

| Round | Cow | Cat | Birch | For the cut / for the baseline / none |
|---|---|---|---|---|
| `lean` words | none, none | none, none | baseline, none | 0 / 1 / 5 |
| `lean-low` words | none, none | none, baseline | none, baseline | 0 / 2 / 4 |
| `lean-sonnet` words | baseline, baseline | baseline, cut | baseline, baseline | 1 / 5 / 0 |
| `f-lean` finisher | cut, cut | none, none | cut, cut | **4 / 0 / 2** |
| `f-split` finisher | baseline, baseline | none, baseline | none, none | 0 / 3 / 3 |
| `f-lean-low` finisher | baseline, baseline | none, baseline | none, none | 0 / 3 / 3 |
| `f-lean-sonnet` finisher | baseline, baseline | baseline, baseline | baseline, none | 0 / 5 / 1 |

- **`lean`'s one loss** is on the birch grove: the baseline "tells the painter where the birches go in step 15 and
  describes the bark shading the way the picture shows it", and the grader called it "slight, close to a toss-up".
  `paintable` was 3 for both sides in every read but that one (4 against 3).
- **`lean-sonnet`'s words** describe "something the picture doesn't show" more often, in every grader's note: steps
  5, 13, 15 and 16 of the birch grove, step 3 of the cow. That is the student test's finding too.
- **`lean-low`'s two losses** say the baseline "locates each mark more concretely" and "covers more of what each
  picture shows". At low effort the writer wrote a third fewer words (1,870 a lesson against 2,590).
- **`f-lean`'s wins are all slight.** On the cow both graders preferred its Known problems, which tell "a
  beginner how to fix each wrong paint in plain words" where the baseline's leave two paints "unfixed and talk in
  pipeline jargon". On the birch grove both said its diagrams agree with the words, where the baseline's "path and
  bark diagrams would steer a beginner wrong on two steps". It listed fewer problems (cow 8, cat 12, birch 8,
  against 12, 25 and 8). Why smaller pictures would make a better finisher isn't known: with one run a side, the win
  may be the run's draw, so read it as no worse.
- **`f-lean-sonnet`'s cat** showed two diagrams as error text on the blanket steps, though `publish` counted all
  nine as drawn. So `f-lean`'s test for skipping the look (fewer drawn than written) can miss a diagram that draws
  badly. On Opus it didn't happen in three lessons.
- **`lean-low` is parked, not dropped,** because it had no student test (the budget allowed three) and lost only 2 of
  6 reads, both slight. `f-lean-low` is dropped: the finisher has no other test, and 3 of 6 reads went against it.
- **`f-split` and `f-lean-low`** lost on the diagrams: fewer of them (`f-split` drew 3 on the cow against 7), and a
  Known problems list that "points to a nose diagram it doesn't have".

The 42 graders cost $7.22 of Claude.

## The new cat and #250

#250 (POC 2.0.2) stopped `check` asking to merge a shading paint into its block-in's. One cat made after it with C1's
cuts (`output/sleeping-cat_v4loop_20261119-215313`, up to the chain's checker) had **no merge asked for**, where C1's
four cat runs had 1, 2, 3 and 2. Its plan's writer cost $0.72, against $1.03 to $1.79 for those four, since there
was no merge to answer. Its renders were $0.61, inside the four's $0.61 to $0.77: what renders the chain again now is
the chain's checker, whose second round asked for two units again (10 renders, $0.19). One run, so the merges are
shown gone on this cat, not on every picture. Its steps 0 to the checker cost $1.33 and the lesson $3.39 with the
baseline's words and finisher.

## Found on the way

- **The teacher's words name paints a step doesn't list.** The baseline finisher's Known problems for the cat list
  nine: "the words name Cat gray, which isn't one of this step's paints" (the shading steps point back at the
  block-in's paint). v3's `check` catches that (`isn't one of its paints`) and sends the stage's writer back; W1's
  check-text doesn't. Fixed by the paint check below (#270).
- **The arc as the writer's next message failed its checks more often**: a feedback round on 3 of 3 lessons (7
  failures in all), against 1 of 3 as its own call (2). After the round none was left. Which checks failed first
  wasn't saved.
- **`v4_loop.py` can't publish a v4 lesson whole**: `publish --final` holds v3's text rules. None of this spike's
  lessons is sealed.

## The paint check (#270)

Run on 2026-11-20. W1's check-text tests numbers and sides, not paint names, so the lesson writer's words named
paints their step doesn't list, and the page then shows no recipe for them there. Read the same way as v3's `check`
(`tools.paints_not_listed`, a sentence at a time), the words already made had **34 such sentences in `lean`** (cow 5,
cat 12, birch 17) and 24 in the baseline. Nearly all point at paint already on the canvas: "The Wood brown must be
dry", "Leave the Leaf green dots showing".

The cut `paint-check` (variant `lean-paints`, `lean` with it) adds v3's check to the word flow:

- **The writer**: after check-text's round, the check runs on the lines. What it finds goes back to the writer in
  the same conversation as its own round (`W1 paints`), answered with only the steps that change (`feedback-changes`).
  The brief for it: name one of the step's own paints if that is the one meant, or say it without the paint's name
  ("the gray from step 5"). Then check-text runs again on the new words, and what fails either check is taken out.
- **The arc**: its back lines are checked the same way, and what fails joins the arc's own round, so it costs no
  extra call. A back line that still names one goes whole, as a back line check-text fails does.
- **What still fails is taken out, not renamed** to a paint the step lists. A listed paint the writer didn't mean
  would tell the painter to load the wrong color, which is worse than a sentence missing. Taking it out is also
  what both checks already do with what fails. On these three lessons it never came to that.

| | Cow | Cat | Birch | Mean |
|---|---|---|---|---|
| Sentences found after check-text | 6 | 22 | 2 | |
| Left after the round | 0 | 0 | 0 | |
| In the arc's back lines | 0 | 0 | 0 | |
| **The paint round** | $0.07 | $0.10 | $0.04 | **$0.07** |
| `lean-paints`, all the words | $0.96 | $1.24 | $0.97 | $1.05 |
| `lean` (above) | $0.81 | $0.91 | $0.81 | $0.85 |

**The round costs $0.07 a lesson** beside the lean words' $0.85, so the words come to about **$0.92**. The rest of
the $1.05 is the writer's first call drawing differently (the cat's $0.71 against $0.52 in `lean`): one run a side,
and none of it comes from the check, which runs after that call. The final words of all three have no step whose
lines name a paint it doesn't list. The words were not graded again: the round only rewords the steps it names.

## Limits

- **One run a variant a picture.** Sharing the pictures takes out the chain's draw that decided C1's graders, but a
  writer's run still varies. `lean`'s level score and 5 ties are no worse; they don't show it better.
- **`lean` is four cuts together**, so how much each one saves is read from the calls (above), not measured alone.
  Whether one of them costs quality on its own isn't known.
- **The student test reads only the steps' words.** The finisher's cuts were graded by the blind graders alone.
- **The graders read the words with the picture in front of them**, as before (`pipeline-v4-plan.md`).

## Spend

Renders: **$3.75** (the new cat's chain $0.61, and the student test's three sets at $1.05 each), against the
owner's ~$3.70. Claude, as charged: the new cat $1.35, the words and the finishers $19.81 (the new cat's included), the blind
graders $7.22, the student test's graders $5.99: about $34.

## What's next

- Build `lean` and `f-lean` into v4 (`docs/design/pipeline-v4.md`), with the paint check (`paint-check`, #270).
- The plan's writer is now the largest helper ($0.72 to $1.03). C1's two unbuilt fixes for its merge are moot where
  #250 removes the merge.
- C2 (#221), the chain's checker on a smaller model, is the one model change still open. This spike's Sonnet result
  is for writing; a yes/no look may be different.
