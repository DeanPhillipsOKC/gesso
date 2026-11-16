# The v3 yardstick: a frozen bench, a blind A/B page, a fault counter, and a run trace (#165)

2026-11-16. Wave 0 of `docs/design/pipeline-v3-plan.md`. Every v2 fix was confirmed on a fresh render, so a new
finish brought new faults and nothing told a regression from randomness. This is the fixed measure every v3 spike
is judged by. The code is in `spike/experiments/bench/`. It is experiment code: no lesson tool, the skill, or the
site changed.

Four parts, each with its own command:

| Part | What it answers | Command |
|---|---|---|
| Frozen bench | Did the experiment change only what it meant to? | `bench.py freeze`, `bench.py build` |
| Blind A/B page | Which lesson does the owner like better, and why? | `ab_page.py make`, `ab_page.py import` |
| Fault counter | How many faults, of which kind, in which step? | `packet.py`, then a fresh reviewer with `fault_counter.md`; `agreement.py` |
| Run trace | Where does a run's time go? | `run_trace.py` |

All commands run from the repo root with `.venv/bin/python`. The tests are `spike/tests/test_bench*.py`.

## 1. The frozen bench

Eight pictures, by photo stem: the five on the site (`chickadee`, `red-sailboat`, `balloon-lavender`,
`sleeping-cat`, `snow-lantern`) and three picked to be hard (`highland-cow`, `lake-cabin`, `birch-grove`).

For each picture, `spike/experiments/bench/pictures/<picture>/` holds, byte for byte from one sealed v2 run:
- `photo.jpg` or `photo.png`, the photo the run started from;
- `00_canvas_frame.png`, and `00_canvas_fit.png` when the run extended the canvas with a render;
- `00_beginner.png` when the run made a beginner version;
- `99_finish.png`, the finish every step is cut from;
- `canvas.json` with the run's own paths taken out, and `notes0.json`, the run's step 0 notes (`photo_prep`,
  `canvas_fit`, `beginner_version` with its `busy` numbers);
- `manifest.json`: the sha256 and size of every file, the source run, its version and commit, and the renders
  that made the frozen files (seconds and cost).

The frozen files come from the v2 baseline runs (section 5), so the baseline and every experiment share the same
finishes. Nothing is recompressed: an experiment sees the real finish.

**Freeze** a sealed run:

    python spike/experiments/bench/bench.py freeze /home/user/gesso-baseline/output/chickadee_skill_<stamp>

It refuses a run with no `sealed.json`, one marked edited, and a picture that's already frozen (`--force`
replaces it). It finds the photo from `canvas.json`'s input in the checkout the run was made in; `--photo`
overrides.

**Build** a lesson folder for an experiment:

    python spike/experiments/bench/bench.py build chickadee            # or all
    export GESSO_HISTORY=output/bench/history

It makes `output/bench/<picture>_skill_<stamp>/` with the frozen pictures, `canvas.json`, `notes.json` (the step 0
notes), `ledger.json` (the frozen renders listed as `"tool": "frozen"` at no cost, with the baseline's seconds and
cost beside them), an empty `trials/`, and `bench.json`. The folder is the skill after step 1: start at step 2
(parts), with plan.json's `"photo"` set to `bench.json`'s `plan_photo` (a path into the bench, the same for every
build). Don't render the finish, the beginner version, or the canvas again.

Set `GESSO_HISTORY` as above before any tool runs on a bench folder. The folder is under `output/`, and without it
`publish` records the lesson in `site/history/`.

**Same bytes every build.** Nothing a build writes names the folder, a time, or an absolute path, and JSON is
written with sorted keys. `bench.py verify` checks every frozen file against its manifest, and `build` refuses to
run when one changed. The test `test_bench.FrozenBenchTests` builds every frozen picture twice into two folders
and compares every file's sha256; `test_bench.FreezeBuildTests` does the same on a made-up run, and
`test_bench.BenchToolsTests` runs `build-steps` on a built folder with the chickadee fixture's plan and outlines.

Size: about 5 MB a picture with no extra renders, 7 MB with a canvas extend, more with a beginner version.

## 2. The blind A/B page

One self-contained HTML page the owner scores on a phone, about 15 minutes for 8 lessons.

    # single mode, the baseline: one lesson per picture
    python spike/experiments/bench/ab_page.py make --round baseline-1.12.1 --order-seed 165 \
        --out output/bench/ab/baseline.html --lesson <run 1> --lesson <run 2> ...
    # pair mode, an experiment against the baseline: two lessons of one picture per --pair
    python spike/experiments/bench/ab_page.py make --round s1-peel --out output/bench/ab/s1.html \
        --pair <baseline run> <experiment run> ...

Pictures go in bench order, or in an order shuffled by `--order-seed` (recorded in the answer key), so a round
doesn't always start, and tire, on the same picture.

The page shows one picture at a time (Back and Next at the bottom), the photo as a thumbnail that taps to full
size, then each lesson one step at a time: the step picture (swipe it, or tap the arrows above or below the words),
the stage it belongs to, its name, its paints with swatch and recipe, its brush, its numbered words and tip. Step
pictures are JPEGs at 720 px on the long side; when the page would pass 11.5 MB, the generator lowers the JPEG
quality, then the size, and refuses past 480 px (split the round into two pages). Close-ups, paint maps,
diagrams and stroke cards aren't on it: the rubric scores the steps. That is a caveat on (b): a step that leans on
its close-up or stroke card for how to paint it can score lower here than it would on the site.

Per lesson, 1 to 5 each:
- (a) the step pictures look like a real half-done painting;
- (b) I could paint each step from its words;
- (c) the pictures, paints and words agree;

then, in single mode, "Would you paint from this lesson?" (yes, maybe, no), and in pair mode, per picture, "Which
would you paint from?" (A, B, no difference). Any step can be tapped "Worst step". Each lesson and each picture
takes an optional note.

**Blind.** In pair mode, side A is drawn from the seed (`random.Random(f"{seed}:{picture}")`; the seed is
`--seed`, or one made from the round's name). The page says only A and B. The lesson folders are in the answer
key, which is base64 inside the page and in `<page>.key.json` beside it, and come back only inside the copied
scores. The same inputs and seed give the same page, byte for byte.

**Saving.** Every change goes through one function, `saveScores(scores)`. Today it writes the phone's
localStorage (in try/catch, so a private window still works) and the page reloads it. To publish the page as an
artifact with a storage backend, change that one function. "Copy scores" is always in the bottom bar and copies
the scores JSON; when the clipboard is blocked it shows the JSON in a box to copy by hand.

**The scores JSON** (`ab_page.py format` prints it):

```json
{"format": "gesso-ab-scores/1", "round": "baseline-1.12.1", "mode": "single", "seed": null,
 "saved_at": "2026-11-16T21:00:00.000Z",
 "pictures": [{"picture": "chickadee",
               "lessons": {"A": "chickadee_skill_20261116-203451"},
               "scores": {"A": {"real": 4, "paintable": 3, "agree": 4, "would_paint": "maybe",
                                "worst_steps": [{"n": 5, "id": "branch-dark"}], "note": ""}},
               "prefer": null, "note": ""}]}
```

In pair mode `lessons` and `scores` have `A` and `B`, `seed` is the number the sides were drawn from, `prefer` is
`A`, `B` or `same`, and there's no `would_paint`. A score not given yet is `null`.

**Import** the copied scores onto the bench:

    python spike/experiments/bench/ab_page.py import scores.json

It checks the format and saves `spike/experiments/bench/scores/<round>.json`. It won't overwrite different scores
for the same round without `--force`.

A phone-size screenshot (390 px wide: `NODE_PATH=$(npm root -g) node spike/experiments/bench/ab_screenshot.js <page> <prefix>`, Playwright with Chromium) showed no sideways scroll,
1-5 buttons about 60 px wide, and the bottom bar always in reach.

## 3. The fault counter

A reviewer in a fresh context counts faults in eight classes, from the issue history: A step pictures, B outlines,
C placement, D paints, E text, F teaching, G site, H tooling. The brief is
`spike/experiments/bench/fault_counter.md`: a definition of each class, two to four real faults per class from the
issues (#84, #139, #153, #155, #163 and #56 for A; #100, #129, #144 for B; #159, #126, #90, #122 for C; #154, #158,
#136 for D; #96, #155 for E; #98, #99 for F; #83, #141, #135 for G; #91, #89, #136 for H), tie-break rules, and the
severity scale (blocker 3, major 2, minor 1).

The reviewer never sees the plan, the run, or this write-up. It gets a packet, made by:

    python spike/experiments/bench/packet.py --out output/bench/packets/baseline --lesson <run 1> --lesson <run 2> ...

Each lesson becomes `p01`, `p02`, ... (numbered in a seeded shuffle, so the name says nothing about the run), with
the photo and finish cropped to the canvas, every step picture at 1200 px, each step beside the one before it, and
`lesson.md` / `packet.json` with each step's name, paints, brush, words and tip. `key.json` beside the packets
maps them back to the runs; it stays out of the reviewer's hands. Nothing from plan.json, notes.json, review.json,
the ledger, or the transcript goes in.

**Running it.** One fresh session per packet (a subagent with no history is enough), given only the brief and the
packet folder:

> Read `spike/experiments/bench/fault_counter.md` and follow it for the lesson in `output/bench/packets/baseline/p03/`.
> Read nothing else in the repository. Write `faults.json` in that folder.

Classes G and H are mostly about the site and the run, which a packet can't show. The reviewer counts only the
symptoms it can see (a missing step picture, a tool's note in the words, a `None` where a name should be) and
says in `not_visible` what the packet can't show, so a zero there isn't read as none.

**Agreement with the owner:**

    python spike/experiments/bench/agreement.py --packets output/bench/packets/baseline \
        --scores spike/experiments/bench/scores/baseline-1.12.1.json

It matches lessons by folder name and reports, per lesson, faults by class and weighted, beside the owner's
three scores and worst steps. Across lessons, Spearman's rank correlation (sign turned so 1 means full agreement):
all faults against the mean score, class A against (a), classes C, E and F against (b), classes A, C, D and E
against (c). Per step, the owner's worst-step taps against the steps the counter gives a major or blocker fault:
agreement over every step, recall, precision, and how many owner worst steps are in the counter's own
`worst_steps`. The plan's number to beat: today's step reviewer agreed with the owner on 8 of 15 steps. Before
the owner scores, every line says "not scored yet". With 8 lessons, one rank swap moves rho by about 0.05, so read
it with the per-step numbers.

The counter can screen spikes alone once it agrees well enough. What counts as enough is the owner's call after
the baseline.

## 4. The run trace

    python spike/experiments/bench/run_trace.py <lesson folder> [--out trace.json]

It finds the transcript that made the run by the lesson folder's name: every `*.jsonl` under `~/.claude/projects`,
subagent transcripts in `<session>/subagents/` too, keeping the one whose tool calls name the folder most often
(the parent session that started a subagent names it only in its report). It reports wall time per skill step, 0
to 8, split into:
- **Claude**: time with no tool running: thinking, writing, waiting for the model.
- **Tools**: from each tool call to its result, with calls that ran at once counted once, less render time. A
  fresh-context review run as a subagent counts here, labeled `subagent`.
- **Render**: the `seconds` each render prints (`render` and `background` print a JSON line with `cached` and
  `seconds`), checked against the ledger's renders.

A step starts when the run reads its file (`.claude/skills/paint-lesson/steps/<N>-*.md`); going back to a step adds
to it again. A transcript that reads no step file falls back to the tools it runs. The sum of every tool's printed
`seconds` is in the JSON too, and the lesson folder's file times give rough marks for each step, which is all
there is when no transcript is found.

On the 1.12.1 chickadee run (`chickadee_skill_20261116-191619`, a subagent): 15.9 minutes, 6.8 of Claude, 7.9 of
tools, 1.2 of renders (72.4 s, the same as its ledger), 87 tool calls. On the sleeping cat
(`sleeping-cat_skill_20261116-191623`): 20.6 minutes, 10.0 Claude, 8.8 tools, 1.8 renders, 108 calls.

## 5. Baseline: v2 at POC 1.12.1

Eight hands-off runs of the unchanged `/paint-lesson` at POC 1.12.1 (commit bb39e54), one per picture, Opus,
with `GESSO_HISTORY` set aside. Their photos, canvas fits, beginner versions and finishes are the frozen bench.
`spike/experiments/bench/baseline/<picture>/` holds each run's trace (`trace.json`) and what it left
(`known_problems.json`: the review's `left` items, the finish issues, the page's known problems, and any issues
filed about the run).

The runs went four at a time, with other sessions on the same 4 cores and 16 GB, so tool time is longer than a run
alone would take. All eight did their text review in the same session that wrote the text
(`review_context: same`), not a fresh one.

The snow lantern's run had three of its `outline` runs killed for lack of memory (exit 137) under that load. The run
didn't count them toward the skill's limit on tries. Most of its 13.4 minutes in step 7 is a loop back to the parts
after the review: outline again (two of the kills fall here), then every tool forward from there. The birch
grove's run had one `outline` run killed the same way, and the lake cabin's two.

Three runs went past step 2c's limit of 5 `outline` runs: the balloon ran it 7 times, the lake cabin 6 (after
making the cabin a child of the forest to get `check` clean), and the highland cow 6 (after dropping the front grass
part and running forward again, as rule 9 says). All three were the model's own call under the unchanged skill, so
they stay in the baseline; the runs table lists them. Counting `outline` commands in the transcripts, the
birch grove (8 launches, 1 killed) and the snow lantern (about 9, 2 killed) may have gone past it too; not
confirmed, since some of those may be reruns after going back from a later step.

Two runs drafted an element technique: the birch grove `elements/birch-trunks.yaml` (#180), the highland cow
`elements/shaggy-animal.yaml` (#181). Neither is frozen: the bench holds what the skill makes in steps 0 and 1, and
picking or drafting an element is step 2, which an experiment does again. An experiment that wants the same element
can read it from the baseline run or its issue.

The highland cow's run noted a possible tool fault: after it dropped the front grass, `build-steps` gave the pixels
behind the cow to the sky, with `problems` empty and `far` 0. It's the first of its known problems: steps 1 to 10
show pale blue blotches with dark green centers where the cow will stand.

**An extra run, left out of the baseline.** `highland-cow_skill_20261116-205600` is not the highland cow's baseline:
the prompt that started it said the element technique would be filed for it, so the run didn't draft one, and its
element choices weren't the skill's own. The baseline is the rerun, `highland-cow_skill_20261116-212627`. The extra
run is kept as a record in `spike/experiments/bench/baseline/excluded/highland-cow_skill_20261116-205600/`. Beside
the rerun it's a first look at how much two runs of one picture differ (one pair, so a hint, not a measure):

| | Extra run (205600) | Baseline (212627) |
|---|---|---|
| Element for the cow | none drafted (steered) | drafted `shaggy-animal` (#181) |
| Steps | 16 | 16 |
| Cost | $0.11 | $0.11 |
| Wall, minutes | 30.1 | 27.6 |
| Claude / tools / renders | 11.1 / 18.0 / 1.1 | 12.0 / 14.5 / 1.1 |
| Tool calls | 110 | 119 |
| Slowest step | 7, check and review (7.3) | 2, parts and outlines (7.0) |
| Problems left | 2 | 2 |

The problems left differ in kind but share one: in both, the gold rim step shows something no step paints (the pink
nose in 205600; the chin's shadow and the nose's light top in 212627). 205600's other problem is the clouds' orange
undersides with only a gold paint named; 212627's is the blotches behind the cow above. Each run has its own
finish render, so the same picture gave a different finish, a different plan, and different faults.

### Runs

| Picture | Run | Beginner version | Canvas extend | Steps | Cost | Skill rules the run went past |
|---|---|---|---|---|---|---|
| chickadee | `chickadee_skill_20261116-203451` | no | no | 18 | $0.15 | |
| red-sailboat | `red-sailboat_skill_20261116-203450` | no | no | 16 | $0.15 | |
| balloon-lavender | `balloon-lavender_skill_20261116-203450` | yes | no | 24 | $0.13 | `outline` 7 times (step 2c: at most 5) |
| sleeping-cat | `sleeping-cat_skill_20261116-203502` | no | yes | 16 | $0.21 | |
| snow-lantern | `snow-lantern_skill_20261116-205524` | no | no | 20 | $0.08 | |
| highland-cow | `highland-cow_skill_20261116-212627` | yes | no | 16 | $0.11 | `outline` 6 times (step 2c: at most 5) |
| lake-cabin | `lake-cabin_skill_20261116-205703` | yes | no | 23 | $0.11 | `outline` 6 times (step 2c: at most 5) |
| birch-grove | `birch-grove_skill_20261116-210750` | yes | yes | 14 | $0.20 | |

### Fault counts

| Picture | A | B | C | D | E | F | G | H | Total (weighted) | Worst steps |
|---|---|---|---|---|---|---|---|---|---|---|
| chickadee | | | | | | | | | | |
| red-sailboat | | | | | | | | | | |
| balloon-lavender | | | | | | | | | | |
| sleeping-cat | | | | | | | | | | |
| snow-lantern | | | | | | | | | | |
| highland-cow | | | | | | | | | | |
| lake-cabin | | | | | | | | | | |
| birch-grove | | | | | | | | | | |

### Trace (minutes)

| Picture | Wall | Claude | Tools | Renders | Calls | Slowest step |
|---|---|---|---|---|---|---|
| chickadee | 21.0 | 10.0 | 9.7 | 1.4 | 94 | 7, check and review (4.2) |
| red-sailboat | 22.1 | 10.8 | 9.8 | 1.4 | 98 | 5, step pictures (6.1) |
| balloon-lavender | 32.7 | 15.2 | 16.1 | 1.5 | 135 | 6, text (10.3) |
| sleeping-cat | 20.2 | 10.4 | 7.6 | 2.2 | 99 | 8, diagrams, notes, seal (3.7) |
| snow-lantern | 33.5 | 12.0 | 20.8 | 0.7 | 131 | 7, check and review (13.4) |
| highland-cow | 27.6 | 12.0 | 14.5 | 1.1 | 119 | 2, parts and outlines (7.0) |
| lake-cabin | 47.5 | 14.0 | 32.3 | 1.2 | 138 | 6, text (12.1) |
| birch-grove | 34.5 | 12.1 | 20.4 | 2.0 | 123 | 5, step pictures (9.2) |

### Owner scores

| Picture | (a) real | (b) paintable | (c) agree | Would paint | Worst steps | Note |
|---|---|---|---|---|---|---|
| chickadee | | | | | | |
| red-sailboat | | | | | | |
| balloon-lavender | | | | | | |
| sleeping-cat | | | | | | |
| snow-lantern | | | | | | |
| highland-cow | | | | | | |
| lake-cabin | | | | | | |
| birch-grove | | | | | | |

### Counter against owner

_To fill from `agreement.py`: rho for each group, and worst-step agreement against the 8 of 15 to beat._

## Known limits

- The A/B page shows step pictures, paints and words, not the close-ups, paint maps, diagrams or stroke cards a
  lesson page has. A lesson that leans on those for a step scores lower on (b) here than on the site.
- The photo on the page and in a packet is the lesson's own (`photo.png`, the plan's photo), so for a picture with
  a beginner version it's the beginner version.
- A bench folder lives under `output/`. Without `GESSO_HISTORY`, `publish` records it in `site/history/`.
- The trace splits by the step files the run reads. A run that reads two step files in one call starts the later
  step there.
