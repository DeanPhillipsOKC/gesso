# The v3 yardstick: a frozen bench, a blind A/B page, a fault counter, and a run trace (#165)

2026-11-16, revised 2026-11-17 after the adversarial review of #183. Wave 0 of `docs/design/pipeline-v3-plan.md`.
Every v2 fix was confirmed on a fresh render, so a new finish brought new faults and nothing told a regression from
randomness. This is the measure every v3 spike is judged by. The code is in `spike/experiments/bench/`. It is
experiment code: no lesson tool, the skill, or the site changed.

Four parts, each with its own command:

| Part | What it answers | Command |
|---|---|---|
| Frozen bench | Did the experiment change only what it meant to? | `bench.py freeze`, `bench.py build` |
| Blind A/B page | Which lesson does the owner like better, and why? | `ab_page.py make`, `ab_page.py import` |
| Fault counter | How many faults, of which kind, in which step? | `packet.py`, then a fresh reviewer with `fault_counter.md`; `agreement.py` |
| Run trace | Where does a run's time go? | `run_trace.py` |

All commands run from the repo root with `.venv/bin/python`. The tests are `spike/tests/test_bench*.py`.

**Status (2026-11-17).**
- Done: the bench is frozen for all 8 pictures (skill steps 0 and 1) and builds to the same bytes on any machine;
  the 8 v2 baseline runs are made, each has a trace, and each was fault-counted twice, by two independent
  fresh-context counters with the final brief (section 5). The counter's repeatability is measured (section 5).
- Superseded: the first fault counts, made with a brief whose examples came partly from the bench pictures' own past
  faults (it told the counter where to look). They're kept as `faults-v1.json` beside each picture's new counts, for
  the record only.
- Done (2026-11-17): the owner scored all 8 baseline lessons (section 5, Owner scores), and the counter was compared
  with those scores (Counter against owner). It agrees only moderately (rho 0.43 on 8 lessons), so the fault counts
  still don't screen a spike alone: the owner's A/B stays the deciding measure.
- Not measured, by choice: the noise floor. Spikes count only clear wins instead (Limits, at the end).

## 1. The frozen bench

Eight pictures, by photo stem: the five on the site (`chickadee`, `red-sailboat`, `balloon-lavender`,
`sleeping-cat`, `snow-lantern`) and three picked to be hard (`highland-cow`, `lake-cabin`, `birch-grove`).

**What the bench holds fixed, and what still varies.** It holds everything the skill makes in steps 0 and 1, from
one sealed baseline run. `spike/experiments/bench/pictures/<picture>/` has, byte for byte:
- `photo.jpg` or `photo.png`, the photo the run started from;
- `00_canvas_frame.png`, and `00_canvas_fit.png` when the run extended the canvas with a render;
- `00_beginner.png` when the run made a beginner version;
- `00_reference.png`, and the palette and value study the run made (`00_reference_palette.*` and
  `00_reference_value-study.png`; the highland cow's were made from its beginner version, `00_beginner_*`);
- `99_finish.png`, the finish every step is cut from;
- `canvas.json` with the run's own paths taken out; `notes0.json`, the run's step 0 and 1 notes (`photo_prep`,
  `canvas_fit`, `beginner_version` with its `busy` numbers, `technique`); `review0.json`, step 1's `finish_issues`;
- `manifest.json`: the sha256 and size of every file, the source run, its version and commit, and the renders
  that made the frozen pictures (seconds and cost).

Not carried: `busy/` (the busy tool's outlined pictures; the notes keep the numbers), `trials/`, the notes'
`filters` list (it points into `trials/`), and the run's ledger (its renders are in the manifest).

Everything from step 2 on still varies from run to run: Claude's parts, outlines, paints, stages, text and review,
and **step 5's background render** (`98_background.png`, what's behind large objects), which is a new paid render in
every experiment. That render is behind the ghosts and the patches behind objects, the most common class A faults
in section 5. So a step-picture fault can still come from a new render, and a spike that wins or loses on one
picture can't yet be told from noise (Limits, at the end).

The frozen files come from the v2 baseline runs (section 5), so the baseline and every experiment share the same
finishes. Nothing is recompressed: an experiment sees the real finish.

**Freeze** a sealed run:

    python spike/experiments/bench/bench.py freeze /home/user/gesso-baseline/output/chickadee_skill_<stamp>

It refuses a run with no `sealed.json`, one marked edited, and a picture that's already frozen (`--force`
replaces it). It finds the photo from `canvas.json`'s input in the checkout the run was made in; `--photo`
overrides.

**Build** a lesson folder for an experiment:

    python spike/experiments/bench/bench.py build chickadee            # or all
    export GESSO_HISTORY=spike/experiments/bench/runs/history

It makes `spike/experiments/bench/runs/<picture>_skill_<stamp>/` (git-ignored by `spike/experiments/bench/.gitignore`)
with the frozen pictures, `canvas.json`, `notes.json` (the step 0 and 1 notes), `review.json` (step 1's finish
issues, for step 7 to keep), `ledger.json` (the frozen renders listed as `"tool": "frozen"` at no cost, with the
baseline's seconds and cost beside them), an empty `trials/`, and `bench.json` (what's fixed, what varies, what isn't
carried). The folder is the skill after step 1: start at step 2 (parts), with plan.json's `"photo"` set to
`bench.json`'s `plan_photo` (a path into the bench, the same for every build). Don't render the finish, the beginner
version, the reference or the canvas again.

The default folder is outside `output/`, so `publish` doesn't record a bench lesson in `site/history/` even if
`GESSO_HISTORY` isn't set (tested). Set it anyway, as above, so the history of bench runs is kept apart.

**Same bytes every build, on any machine.** Nothing a build writes names the folder, a time, or an absolute path;
JSON is written with sorted keys and LF line ends; paths are POSIX. `spike/experiments/bench/.gitattributes` keeps
git from converting frozen files (PNG and JPG are binary, JSON is LF), and frozen JSON is hashed and copied with LF
line ends, so a Windows checkout that turned it into CRLF still verifies and builds the same bytes (tested).
`bench.py verify` checks every frozen file against its manifest, lists any file the manifest doesn't, and exits 1
on any problem; `build` refuses to run when a file changed. The tests:
- `test_bench.FrozenBenchTests` builds every frozen picture twice into two folders and compares every file's sha256,
  and compares a chickadee build's JSON files with pinned hashes, so a machine isn't only compared with itself;
- `test_bench.FreezeBuildTests` does the same on a made-up run, plus a simulated CRLF checkout;
- `test_bench.BenchToolsTests` runs `build-steps` on a built folder with the chickadee fixture's plan and outlines.

Size: 70 MB for the 8 pictures, from 5.4 MB (chickadee, snow lantern) to 14.9 MB (birch grove, with a beginner
version and a canvas extend). They're plain git files, not Git LFS: every clone carries them, so if the bench grows,
move `pictures/` to LFS first.

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

**Blind.** The page never holds a lesson folder's name, the seed, or anything that maps a side to a lesson. Each
side is an opaque token (a hash of the seed, round, picture, side and folder), and the page, the scores it copies,
its localStorage and its database records carry only tokens. The token-to-folder map is the answer key,
`<page>.key.json`, written beside the page and never into it; keep it out of the owner's sight until the round is
scored. In pair mode, which lesson is A is drawn from the seed and balanced: half the pictures (one more or less)
swap. Without `--seed` a random seed is drawn and kept only in the key. The same inputs and seed give the same page,
byte for byte. A test opens a pair page in Chromium, taps a score and a worst step, copies with the clipboard blocked,
and checks that the copy box, localStorage and the database record hold no folder name, run time or seed.

**Saving.** Every change goes through one function, `saveScores(scores)`. It writes the phone's localStorage (in
try/catch, so a private window still works), which the page reloads, and, when the page runs as a claude.ai artifact
with a database, one record per device: collection `scores`, document id `<round>__<device>`, with a `device` field
(the device id is random and kept in localStorage). A second phone, or a tab reopened after the browser dropped its
storage, writes its own record, so it never replaces another's scores. "Copy scores" is always in the bottom bar and
copies the scores JSON; when the clipboard is blocked it shows the JSON in a box to copy by hand.

**The scores JSON** (`ab_page.py format` prints it):

```json
{"format": "gesso-ab-scores/1", "round": "s1-peel", "mode": "pair",
 "saved_at": "2026-11-17T21:00:00.000Z", "device": "d4k2x9q1a",
 "pictures": [{"picture": "chickadee",
               "lessons": {"A": "L3f9a0c1d2e7b", "B": "L81c2d0e4a9f3"},
               "scores": {"A": {"real": 4, "paintable": 3, "agree": 4,
                                "worst_steps": [{"n": 5, "id": "branch-dark"}], "note": "",
                                "at": {"real": "2026-11-17T20:58:10.000Z", "worst_steps": "2026-11-17T20:59:02.000Z"}},
                          "B": {"real": 2, "paintable": 3, "agree": 2, "worst_steps": [], "note": "", "at": {}}},
               "prefer": "A", "note": "", "at": {"prefer": "2026-11-17T21:00:00.000Z"}}]}
```

In single mode `lessons` and `scores` have only `A`, each lesson has `would_paint` (yes, maybe or no), and there's no
`prefer`. A score not given yet is `null`. `at` holds when each item was last set or cleared, on this device.
`device` is only in database records.

**Import** a round's scores onto the bench, from the copied JSON or the database records (one file each, or a list):

    python spike/experiments/bench/ab_page.py import scores-phone.json scores-laptop.json [--key page.key.json]

It checks each record and merges the devices' records item by item: for each score, worst-step list and note of
each picture and side, the latest change wins, by the item's own time in `at`. A record that times an item counts
even when it cleared it (a worst step un-tapped), so a later clear wins. The baseline-1.12.1 page's records have no
`at`: for them an item's time is the record's `saved_at`, and only a set value counts. Any item two records hold
differently is listed as a conflict, with the value kept. Then it joins the tokens to lesson folders through the answer key (default
`spike/experiments/bench/scores/<round>.key.json`) and refuses a token the key doesn't know. It saves
`spike/experiments/bench/scores/<round>.json` with the folders, the tokens, the seed, the records merged and the
conflicts. It won't overwrite different scores for the same round without `--force`.

**The baseline round** (`baseline-1.12.1`, 8 lessons, 147 steps, 10.2 MB at JPEG quality 72, pictures shuffled with
`--order-seed 165`) is published as a claude.ai artifact, https://claude.ai/artifact/NAyrBrgoeab8sF2jJs6ZG3, with the
per-device database records above. Scores come back that way: the coordinator reads the round's records
(`baseline-1.12.1__<device>`) and runs `ab_page.py import` on them; "Copy scores" stays as the fallback. That page
was made before the tokens, so its scores carry folder names. It's single mode, with nothing to hide, and its
answer key (`spike/experiments/bench/scores/baseline-1.12.1.key.json`, folder names only) still joins: the importer
matches folder names when a key has no tokens.

A phone-size screenshot (390 px wide: `NODE_PATH=$(npm root -g) node spike/experiments/bench/ab_screenshot.js <page>
<prefix>`, Playwright with Chromium) showed no sideways scroll, 1-5 buttons about 60 px wide, and the bottom bar
always in reach.

## 3. The fault counter

A reviewer in a fresh context counts faults in eight classes, from the issue history: A step pictures, B outlines,
C placement, D paints, E text, F teaching, G site, H tooling. The brief is
`spike/experiments/bench/fault_counter.md`: a definition of each class, tie-break rules, the severity scale (blocker
3, major 2, minor 1), and examples of each class. The classes and their kinds come from the issues (#84, #139, #153,
#155, #163 and #56 for A; #100, #129, #144 for B; #159, #126, #90, #122 for C; #154, #158, #136 for D; #96, #155 for E;
#98, #99 for F; #83, #141, #135 for G; #91, #89, #136 for H), but the brief's examples are made up for pictures that
aren't on the bench (pumpkins, a barn, a fox, a lighthouse, pears), with no issue numbers. The first brief used
the bench pictures' own past faults as examples, which told the counter where to look on exactly the lessons it
scores. Its counts are superseded (kept as `faults-v1.json`); section 5's counts use the final brief.

The reviewer never sees the plan, the run, or this write-up. It gets a packet, made by:

    python spike/experiments/bench/packet.py --lesson <run 1> --lesson <run 2> ...     # [--out DIR outside the repo]

The packets go in a new temp folder (`--out` must be outside the repository: it refuses one inside, so a counter
never sits next to `spike/experiments/bench/baseline/<picture>/faults.json` or `known_problems.json`, the answers
for the same picture). Each lesson becomes `p01`, `p02`, ... (numbered in a seeded shuffle, so the name says nothing
about the run), with the photo and finish cropped to the canvas, every step picture at 1200 px, each step beside the
one before it, and `lesson.md` / `packet.json` with each step's name, paints, brush, words and tip. Beside the packets
are a copy of the brief and `key.json`, which maps each packet to its lesson folder; it stays out of the reviewer's
hands. Nothing from plan.json, notes.json, review.json, the ledger, or the transcript goes in.

**Running it.** One fresh session per packet (a subagent with no history is enough), given only the brief and the
packet folder:

> Read `<packets>/fault_counter.md` and follow it for the lesson in `<packets>/p03/`. Read nothing else. Write
> `faults.json` in that folder.

Classes G and H are mostly about the site and the run, which a packet can't show. The reviewer counts only the
symptoms it can see (a missing step picture, a tool's note in the words, a `None` where a name should be) and
says in `not_visible` what the packet can't show, so a zero there isn't read as none.

**Keeping the results.** Count each lesson twice, by two fresh counters, each in its own copy of the packets. Copy
the results to `<round folder>/<picture>/faults-a.json` and `faults-b.json` (the baseline's are in
`spike/experiments/bench/baseline/`) and the packets' `key.json` beside them. The key holds packet ids, picture names,
lesson folder names and step counts, no lesson content.

**The two counters against each other** (repeatability):

    python spike/experiments/bench/agreement.py --packets spike/experiments/bench/baseline \
        --compare faults-a.json faults-b.json

Per lesson: distinct faults from each and their spread (the difference over their mean), weighted counts, how many of
their top-3 worst steps match, and the Jaccard index of the steps each flags with a major or blocker fault, counted
two ways: every step a fault shows in, and only the step where it first shows. Across lessons: the rank correlation
of their weighted counts per step.

**Agreement with the owner,** on what's committed, with the two counters' mean:

    python spike/experiments/bench/agreement.py --packets spike/experiments/bench/baseline \
        --name faults-a.json --name faults-b.json --scores spike/experiments/bench/scores/baseline-1.12.1.json

It reads the packet key and each lesson's result files (`--name`, default `faults.json`; in `<packet>/` as packet.py
lays them out, or in `<picture>/` as the bench keeps them), checks each against the brief's format, takes the
counters' mean for each lesson (every count averaged; a step is flagged when at least half of them flag it), and matches lessons to the owner's
scores through the key, refusing a key that names a folder twice. Per lesson it reports faults by class, weighted,
and weighted per step (so a lesson with more, smaller steps doesn't score worse for it), beside the owner's three
scores and worst steps. Across lessons, Spearman's rank correlation of the per-step weighted count (sign turned so 1
means full agreement): all faults against the mean score, class A against (a), classes C, E and F against (b),
classes A, C, D and E against (c). Per step, the owner's worst-step taps against the steps the counter gives a major
or blocker fault, over the lessons where the owner tapped at least one (no taps means unknown, not "no bad step"):
agreement with Cohen's kappa beside it (most steps are flagged by neither, so raw agreement alone flatters), recall,
precision, and how many owner worst steps are in the counter's own `worst_steps`. The plan's number to beat:
today's step reviewer agreed with the owner on 8 of 15 steps. Before the owner scores, every line says "not scored
yet". With 8 lessons, one rank swap moves rho by about 0.05, so read it with the per-step numbers.

The counter can screen spikes alone once it agrees well enough with the owner and with itself (two runs per packet).
What counts as enough is the owner's call after the baseline.

## 4. The run trace

    python spike/experiments/bench/run_trace.py <lesson folder> [--out trace.json]

It finds the transcript that made the run by the lesson folder's name: every `*.jsonl` under `~/.claude/projects`,
subagent transcripts in `<session>/subagents/` too, keeping the one whose tool calls name the folder most often
(the parent session that started a subagent names it only in its report). It warns when that transcript is a main
session's, or when another names the folder about as often. It reports wall time per skill step, 0 to 8, split
into:
- **Claude**: time with no tool running: thinking, writing, waiting for the model.
- **Tools**: from each tool call to its result, with calls that ran at once counted once, less render time. A
  fresh-context review run as a subagent counts here, labeled `subagent`.
- **Render**: the `seconds` each render prints (`render` and `background` print a JSON line with `cached` and
  `seconds`), checked against the ledger's renders.
- **Background**: a Bash call run in the background returns at once; it's counted from the call to its task
  notification, apart from the three above (`background_s`), with a warning.

A step starts when the run reads its file (`.claude/skills/paint-lesson/steps/<N>-*.md`); going back to a step adds
to it again. A transcript that reads no step file falls back to the tools it runs. In a subagent's transcript the run
is the whole transcript. In a main session's it starts at the last `/paint-lesson` launch before the folder is first
named and ends at the run's seal (`publish --final` into its folder), or with no seal, at its last call into the
folder before a gap of over 15 minutes; later calls that name the folder (a freeze, a trace) aren't counted and are
listed in a warning. The sum of every tool's printed `seconds` is in the JSON too, and the lesson folder's file
times give rough marks for each step, which is all there is when no transcript is found. The JSON names the
transcript relative to `~/.claude/projects` (`<project>/<session>[/subagents/<agent>].jsonl`).

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
| Slowest step | 7, check and review (7.3) | 5, step pictures (7.3) |
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

Two independent fresh-context counters per lesson (A and B), each in its own copy of the packets outside the repo,
each given only the final `fault_counter.md` and one packet (no key, no plan, no run). Their files are
`spike/experiments/bench/baseline/<picture>/faults-a.json` and `faults-b.json`, with the packet key in
`spike/experiments/bench/baseline/key.json`. All 16 fit the format (`agreement.py` checks it): every step listed,
classes and severities valid, ids unique, `same_as` pointing at a real fault, and `counts` and `distinct` matching
the faults listed. The files are the record. A counter's chat reply sometimes gave different numbers, so only the
files are used.

These replace the first counts (`faults-v1.json`, one counter per lesson), which are superseded: that brief's
examples came partly from the bench pictures' own past faults, so it told the counter where to look.

Each cell is all / distinct: all counts a fault once in every step a painter meets it in; distinct counts it once.
Weighted is blocker 3, major 2, minor 1, over all. "Run left" is what the run's own same-session review found and
left as it was (`review.json`, `left` items): the number the lesson page's Known problems shows today.

| Picture | Counter | A | B | C | D | E | F | G | H | Total | Weighted | Run left | Worst steps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| chickadee | A | 11/6 | 15/6 | 0 | 4/4 | 10/10 | 2/2 | 0 | 0 | 42/28 | 70 | 1 | 1, 8, 6 |
| | B | 31/13 | 14/5 | 1/1 | 4/4 | 7/7 | 1/1 | 0 | 0 | 58/31 | 86 | | 1, 6, 13 |
| red-sailboat | A | 34/17 | 7/3 | 2/2 | 3/3 | 3/3 | 5/2 | 0 | 0 | 54/30 | 90 | 1 | 9, 12, 5 |
| | B | 27/14 | 2/1 | 2/2 | 5/5 | 3/3 | 4/1 | 0 | 0 | 43/26 | 78 | | 13, 9, 5 |
| balloon-lavender | A | 52/22 | 24/5 | 4/4 | 5/5 | 8/8 | 11/3 | 0 | 0 | 104/47 | 177 | 2 | 4, 8, 19 |
| | B | 42/20 | 26/7 | 1/1 | 2/2 | 6/6 | 10/2 | 0 | 0 | 87/38 | 161 | | 3, 8, 7 |
| sleeping-cat | A | 43/11 | 18/6 | 2/2 | 6/6 | 3/3 | 8/3 | 0 | 0 | 80/31 | 150 | 3 | 2, 1, 11 |
| | B | 35/12 | 11/2 | 3/3 | 5/5 | 3/3 | 7/2 | 0 | 0 | 64/27 | 128 | | 2, 11, 1 |
| snow-lantern | A | 12/10 | 7/5 | 1/1 | 3/3 | 3/3 | 4/3 | 0 | 1/1 | 31/26 | 46 | 3 | 20, 1, 19 |
| | B | 22/9 | 6/4 | 1/1 | 3/3 | 3/3 | 2/2 | 0 | 0 | 37/22 | 69 | | 7, 19, 1 |
| highland-cow | A | 19/8 | 5/5 | 3/3 | 3/3 | 6/6 | 1/1 | 0 | 0 | 37/26 | 71 | 2 | 1, 13, 7 |
| | B | 29/10 | 1/1 | 4/4 | 3/3 | 10/7 | 1/1 | 0 | 0 | 48/26 | 78 | | 7, 13, 1 |
| lake-cabin | A | 30/12 | 6/3 | 2/2 | 4/4 | 7/4 | 2/2 | 0 | 0 | 51/27 | 95 | 4 | 3, 12, 6 |
| | B | 36/14 | 3/3 | 6/4 | 6/6 | 8/7 | 2/2 | 0 | 0 | 61/36 | 103 | | 3, 12, 6 |
| birch-grove | A | 39/15 | 13/4 | 2/2 | 3/3 | 4/3 | 1/1 | 0 | 0 | 62/28 | 123 | 3 | 1, 11, 9 |
| | B | 51/15 | 16/4 | 0 | 3/3 | 8/7 | 2/2 | 0 | 0 | 80/31 | 162 | | 1, 9, 7 |
| all 8 | A | 240/101 | 95/37 | 16/16 | 31/31 | 44/40 | 34/17 | 0 | 1/1 | 461/243 | 822 | 19 | |
| | B | 273/107 | 79/27 | 18/16 | 31/31 | 48/43 | 29/13 | 0 | 0 | 478/237 | 865 | | |

Each counter found about 240 distinct faults (243 and 237) where the runs' own same-session reviews left 19: about
12 times as many. Distinct blockers: 15 for A (13 A, 1 C, 1 D) and 19 for B (18 A, 1 B). G and H are 0 but for one
H (a tool's note in the words): every counter said in `not_visible` that the packet can't show the site or the run.

### Repeatability: the two counters against each other

From `agreement.py --compare faults-a.json faults-b.json`:

| Picture | Distinct A / B | Spread | Weighted A / B | Top-3 worst steps in common | Flagged steps, Jaccard (every step / first step) |
|---|---|---|---|---|---|
| balloon-lavender | 47 / 38 | 21% | 177 / 161 | 1 of 3 | 0.83 / 0.65 |
| birch-grove | 28 / 31 | 10% | 123 / 162 | 2 of 3 | 0.93 / 0.90 |
| chickadee | 28 / 31 | 10% | 70 / 86 | 2 of 3 | 0.67 / 0.67 |
| highland-cow | 26 / 26 | 0% | 71 / 78 | 3 of 3 | 0.80 / 0.54 |
| lake-cabin | 27 / 36 | 29% | 95 / 103 | 3 of 3 | 0.88 / 0.79 |
| red-sailboat | 30 / 26 | 14% | 90 / 78 | 2 of 3 | 0.93 / 0.73 |
| sleeping-cat | 31 / 27 | 14% | 150 / 128 | 3 of 3 | 0.79 / 0.62 |
| snow-lantern | 26 / 22 | 17% | 46 / 69 | 2 of 3 | 0.47 / 0.64 |

- **Totals:** distinct faults differ by 0 to 29% per picture (mean 14%); weighted counts by 8 to 40% (mean 18%).
- **Worst steps:** their top-3 worst steps share 18 of 24.
- **Flagged steps:** the steps each flags with a major or blocker fault overlap with a mean Jaccard index of 0.79
  (0.47 to 0.93) over every step a fault shows in. Over only the step where a fault first shows, it's 0.69 (0.54 to
  0.90).
- **Ranking:** across the 8 lessons, the two counters rank them almost the same by weighted faults per step (Spearman
  0.95).
- **By class:** totals agree closely (A 101 / 107, D 31 / 31, E 40 / 43), but one picture's class count can differ by
  half or more (the chickadee's A: 6 against 13).

**What it means for screening.** The counter ranks lessons consistently and mostly agrees on the worst steps, but its
per-picture totals move by up to about 30% between two counters on the same packet. So a per-picture change smaller
than about that spread isn't a signal from the counter alone. Count every lesson twice and use the mean of the two
counters (`agreement.py --name faults-a.json --name faults-b.json`). Judge a spike on changes larger than the A-B
spread, or on the same direction across most of the 8 pictures. These are one pair of counters on 8 lessons; a third
counter would tighten them.

**What the counter found most** (distinct faults, sorted by keyword from the counters' `sees` lines, so the counts
are approximate; given as counter A / counter B). These are the counters' findings, not yet checked against
the owner:
- **Ghosts**, something showing before its step paints it (class A): about 29 / 36, on all 8 pictures. The cow's
  place, the sun's path, the boat's reflection, reeds in the water.
- **Steps that add colors their paints don't name, or a color far from the named paint** (class D, often a part's
  last step): 26 / 28, on all 8 pictures. The step names one paint while most of what it adds is another
  color: a sail turning near-white on a step that names a gray, brass bars named "Deep night blue".
- **Pictures with no brush marks**, flat or smeared like a filter (A): about 17 / 12, on 7 or 8 pictures.
- **Words ask for texture, and the picture shows one flat, hard-edged shape** (E): about 14 / 14, on 5 or 6
  pictures. Tapped clumps shown as a solid slab, curved pieces shown as a smooth silhouette.
- **Tiled, mirrored patterns** no brush makes (A), the fill behind objects borrowing texture: 13 / 17, on 7 of the 8
  pictures. They look like kaleidoscope diamonds, lace, chevrons, or a dot lattice.
- **Load words a beginner isn't told the meaning of** (F): "creamy", "a light load", 11 / 10, on 7 pictures.
- **Jumps** from a flat coat to finished detail in one step (A): 9 / 7, on 5 pictures.
- **Recipes whose mix doesn't match the swatch** (D): 5 / 3, on 5 pictures between them. "Bark brown" from red and
  ultramarine with no burnt sienna mixes a purple-gray; "Mossy green" mostly ultramarine mixes a gray-blue.

A step-picture fault a counter met once is usually met again in the following steps, which is why A's all counts
(240, 273) are more than twice their distinct counts (101, 107).

### Trace (minutes)

| Picture | Wall | Claude | Tools | Renders | Calls | Slowest step |
|---|---|---|---|---|---|---|
| chickadee | 21.0 | 10.0 | 9.7 | 1.4 | 94 | 7, check and review (4.2) |
| red-sailboat | 22.1 | 10.8 | 9.8 | 1.4 | 98 | 5, step pictures (6.1) |
| balloon-lavender | 32.7 | 15.2 | 16.1 | 1.5 | 135 | 6, text (10.3) |
| sleeping-cat | 20.2 | 10.4 | 7.6 | 2.2 | 99 | 8, diagrams, notes, seal (3.7) |
| snow-lantern | 33.5 | 12.0 | 20.8 | 0.7 | 131 | 7, check and review (13.4) |
| highland-cow | 27.6 | 12.0 | 14.5 | 1.1 | 119 | 5, step pictures (7.3) |
| lake-cabin | 47.5 | 14.0 | 32.3 | 1.2 | 138 | 6, text (12.1) |
| birch-grove | 34.5 | 12.1 | 20.4 | 2.0 | 123 | 5, step pictures (9.2) |

Four runs had background calls (an `outline` left running while Claude did other things): the snow lantern 61 s,
the highland cow 60 s, the lake cabin 73 s, and the birch grove 2 calls for 8.3 minutes. That time is in each
trace's `background_s`. It overlaps the other columns: while a background call ran, the run was doing something else,
and that time counts as whatever it was. Claude thinking is Claude time, but a wait with a `sleep` call (the lake
cabin's did) is tool time. So read the birch grove's 12.1 minutes of Claude time as including some waiting, not as
12.1 minutes of thinking.

### Owner scores

| Picture | (a) real | (b) paintable | (c) agree | Would paint | Worst steps | Note |
|---|---|---|---|---|---|---|
| chickadee | 4 | 3 | 4 | yes | none tapped | |
| red-sailboat | 4 | 3 | 3 | yes | none tapped | |
| balloon-lavender | 3 | 3 | 4 | yes | none tapped | |
| snow-lantern | 3 | 3 | 3 | yes | none tapped | |
| lake-cabin | 2 | 3 | 3 | no | none tapped | |
| sleeping-cat | 2 | 2 | 2 | no | none tapped | |
| highland-cow | 2 | 2 | 2 | no | none tapped | |
| birch-grove | 1 | 2 | 1 | no | none tapped | |

Scored on the phone page on 2026-11-17 (round `baseline-1.12.1`, single mode), saved in
`spike/experiments/bench/scores/baseline-1.12.1.json`. The artifact database record and the Copy scores text were the
same. Every lesson scored 3 or under on (b), "I could paint each step from its words". The owner would paint from the
four site pictures that score best and from none of the three hard pictures; the sleeping cat, a site picture, is a no
too.

### Counter against owner

`agreement.py --packets spike/experiments/bench/baseline --name faults-a.json --name faults-b.json --scores
spike/experiments/bench/scores/baseline-1.12.1.json` (the mean of the two counters; weighted faults per step; rho's
sign turned so that higher means the counter agrees):

| Faults | Against | rho (8 lessons) |
|---|---|---|
| all classes | the mean of (a), (b), (c) | 0.43 |
| A, step pictures | (a) real | 0.52 |
| C, E, F, placement, text, teaching | (b) paintable | 0.28 |
| A, C, D, E | (c) agree | 0.53 |

Worst steps: the owner tapped none, so worst-step agreement and kappa can't be measured this round (`unknown`).

| Picture | Weighted faults per step (mean of 2) | Owner mean of (a)–(c) | Would paint |
|---|---|---|---|
| birch-grove | 10.2 | 1.3 | no |
| sleeping-cat | 8.7 | 2.0 | no |
| balloon-lavender | 7.0 | 3.3 | yes |
| red-sailboat | 5.3 | 3.3 | yes |
| highland-cow | 4.7 | 2.0 | no |
| chickadee | 4.3 | 3.7 | yes |
| lake-cabin | 4.3 | 2.7 | no |
| snow-lantern | 2.9 | 3.0 | yes |

What it shows:
- **The counter finds the worst lessons.** Its two highest, the birch grove and the sleeping cat, are the owner's two
  lowest.
- **It misses two lessons the owner won't paint from.** The highland cow and the lake cabin have few faults per step
  but score 2.0 and 2.7. Whatever the owner dislikes there, the counter doesn't count as a fault, or doesn't weigh
  enough.
- **It over-counts one the owner likes.** The lavender balloon has the third most faults per step, but scores 3.3 and
  is a yes.
- **(b) is where it agrees least** (0.28). The counter judges words against pictures; the owner judges whether a
  painter could follow them, and gave every lesson 3 or under.
- **Eight lessons is few.** A rho of 0.43 on 8 is well within what chance gives, so it's a direction, not a measure.
  It's also below the counter's agreement with itself (0.95 on weighted faults per step, section 5), so the gap is in
  what it counts, not in its noise.

So the counter can rank lessons coarsely and flag the worst, but not screen a spike alone. A spike still needs the
owner's A/B. Two things would help: worst-step taps in the next round (the page has them), which allow the per-step
comparison and kappa; and a look at what the owner sees in the cow and the cabin that the counter misses.

What the owner saw (2026-11-17, from memory, after scoring): "The cow had artifacts in every step and some of the
steps had magical things happen like the cow's face suddenly coming into focus even though the step did not have the
right paints or instructions to make it happen. The lake had lots of artifacts." Both counters did find these on the
cow (step 13 finishing the face with no paint or line for it; the blotches where the cow goes, through step 10), rated
major. The owner kept them major rather than blockers ("Major issues seems reasonable"), so the brief is unchanged.
Read the miss as weighting, not blindness: a lesson-wide artifact or one "magic" step can sink a lesson for the owner
however few other faults it has, and a count per step doesn't capture that.

## Limits

- **No noise floor, by choice (owner's call, 2026-11-17).** No v2 lesson is rebuilt from the bench, so the spread
  between two v2 runs from the same frozen folder is unknown, and it won't be measured: eight more lesson runs cost
  too much of the owner's weekly usage. The excluded highland cow pair (section 5) is the only look at it: the same
  step count and cost, a similar number of known problems of different kinds. In its place:
  - **Clear wins only.** A spike beats v2 only when the owner prefers it on at least 6 of 8 pictures (or on most of a
    smaller round) and it loses clearly on none. A smaller margin is a tie.
  - **Targeted reruns.** When a result is borderline on a picture, rebuild v2 from the bench on that one picture and
    compare again, rather than measuring all 8.
  - The v3 gate (beat v2 on every bench picture's weakest stage) already rules out an average win carried by noise.
- **Keeping spikes affordable.** A full round (8 lesson runs plus two fault counters per lesson) is about a 5-hour
  usage window. A spike starts on the 3 or 4 bench pictures most likely to show its effect and goes to all 8 only if
  it looks promising; screening uses one fault counter per lesson; and the owner is told a batch's rough size before
  it starts.
- **Step 5's background render isn't frozen.** Every bench build still makes a new paid `98_background.png`, the
  render behind the ghosts and patches behind objects (section 1). A step-picture fault can come from it.
- **The counter's repeatability is one pair of counters on 8 lessons** (section 5, Repeatability). Two counters'
  distinct totals differ by up to about 30% on one picture; a smaller per-picture change isn't a signal from the
  counter alone.
- Pair rounds that reuse the same 8 baseline lessons: the owner will have scored them step by step in single mode,
  and may start to recognise the baseline side. A fresh v2 control per round would avoid it.
- The A/B page shows step pictures, paints and words, not the close-ups, paint maps, diagrams or stroke cards a
  lesson page has. A lesson that leans on those for a step scores lower on (b) here than on the site.
- The photo on the page and in a packet is the lesson's own (`photo.png`, the plan's photo), so for a picture with
  a beginner version it's the beginner version.
- A bench folder built somewhere under `output/` (with `--into`) is recorded in `site/history/` by `publish` unless
  `GESSO_HISTORY` is set. The default, `spike/experiments/bench/runs/`, isn't.
- The bench's 70 MB of pictures are plain git files, not Git LFS.
- The trace splits by the step files the run reads. A run that reads two step files in one call starts the later
  step there.
