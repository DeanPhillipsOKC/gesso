# Spike: one engine that rebuilds only what changed (#176, v3 S11)

2026-11-17. Pipeline v3 plan, "Speed": one long-lived process in place of thirty one-shot tools. The engine is
`spike/engine.py` (`tools.py engine ...`). The proof and the timings are `spike/experiments/v3_one_engine.py`, with
today's hashes in `spike/experiments/v3_one_engine.json`. No renders.

**What it showed:** through the engine, every file the tools write is the same, byte for byte, as today, on all
three fixtures, after a stages edit, and after a parts edit. The tools spend about 60% less time: 268 seconds
against 666 for the three fixtures' three scenarios together (medians of 3 runs each). A stages edit reruns in 8 to
13 seconds where it took 44 to 67. The first full pass gains least (27 to 48%), because the first outline and the
first build cost the same as today.

## What was built

The engine is opt-in. `/paint-lesson` doesn't use it, and `tools.py <tool>` works exactly as before whether an
engine runs or not.

    python spike/tools.py engine serve                      # leave it running in the background
    python spike/tools.py engine call <tool> <arguments>    # prints what `tools.py <tool> <arguments>` prints
    python spike/tools.py engine chain --lesson <lesson>    # the skill's tools in order, from what changed
    python spike/tools.py engine status | stop

`engine call` runs the tool inside the engine (`tools.main`, in the caller's folder and environment) and prints
its one JSON line and exit code. The client starts in about 0.1 seconds: it loads nothing but `engine.py`. The
engine listens on 127.0.0.1 with a random token kept in `output/.engine/engine.json`.

What the engine keeps between calls, each keyed by exactly what goes into it:

| Kept | Keyed by | Saves |
|---|---|---|
| Python modules, stroke cards, element files | (loaded once; cards by file time, as `yaml_files` already did) | about 0.3 s a call |
| Every step picture build (`build_steps._built`, the memo only tests used) | the plan, finish, outlines, background, tuned numbers | the build in step-aids, draft-text, check, publish |
| What's behind the objects, and each part's prepared paint and flat coat (`build_steps.remember_parts`) | the parts and pictures; for a part, also its paints' ids and colors | most of a rebuild after a stages edit |
| The outline model, loaded once | | 1 to 2 s an outline |
| The model's reading of the picture, in memory and in `output/.embed-cache/` (about 70 MB each, newest 6) | the picture's bytes, the encoder file's SHA-256, the onnxruntime version | the 8 s read, on every outline after the first, even in a new engine |
| Decoded step pictures, a page's inlined pictures, the embed's webp files, encoded step PNGs, the texture check, the drafted text check and publish draft again | each file's bytes, or each array's bytes and every argument | most of check and publish |

`engine chain` holds each lesson's plan as the last call left it: a change to `parts` runs from `outline`, to
`paints` or `stages` from `build-steps`, otherwise from `check` (skill rule 9). It stops at the first refusal.

Code changes outside the engine, all only refactors on the default path:
- `build_steps._build`: `prepare` moved out of the closure into `_prepare(...)`, and what's behind the objects into
  `_behind(...)`, so each can be kept. With the memo off (the default) they run every time, as before.
- `outline.Sam(keep=...)`: an optional folder for readings. Without it, `embed` is unchanged.
- `tools.py`: a hook for the engine's kept outline model, `save_png` for the step pictures, and the `engine`
  subcommand.

## How byte-identity was proven

The harness sets up each fixture as `spike/tests/lessons.py` does (fixture plan, finish, saved outlines), then runs
three scenarios in one folder, the way a run loops, each tool as its own process exactly as the skill calls it:

- **full:** outline, paints, build-steps, step-aids, mix, draft-text, card-adapt, check, publish (a draft);
- **stage:** the last two neighboring passes of one part swap places in plan.json (chickadee's wing passes, the
  lavender's tree passes, the sailboat's reflection passes), then build-steps on;
- **part:** the first single-box object's box grows by 0.005 on every side (each fixture's sun), then outline on.

After every tool it hashes every file in the lesson folder (sha256) and what the tool printed. 75 tool runs per
fixture, 225 in all, each compared on its exit code, its printed result, and every file it changed.

Only these fields are normalized, everything else is compared byte for byte:
- **publish's stamp** (`version.stamp`): the commit, the dirty flag, and the date. In `lesson.json` and
  `embed/lesson.json` as `gesso.commit`, `gesso.dirty`, `gesso.published`, `gesso.made.commit`,
  `gesso.made.published`; in `lesson.html`, `lesson-artifact.html` and `lesson-standalone.html` as the footer
  "(&lt;commit&gt;) on &lt;date&gt;" (two places each); in publish's printed `gesso`. They change with the code's
  commit and the day, not with what the tools do.
- **the lesson folder's absolute path**, only in what the tools print (`seconds` is left out there too). No file
  holds it.

The golden hashes come from today's code: main at bb39e54, unpacked from `git archive`, so it has no git and its
stamp says "unknown", against this branch's real commit and dirty flag. That is how the stamp fields were found.

| | chickadee | lavender balloon | red sailboat |
|---|---|---|---|
| Today's code, 7 runs (the golden, then 6 timed) | same every run | same every run | same every run |
| This branch, default path (one process per tool) | same as golden | same as golden | same as golden |
| This branch, engine, a new readings folder (9 runs) | same as golden | same as golden | same as golden |
| This branch, engine, readings from disk (1 run) | same as golden | same as golden | same as golden |

Each row covers all three scenarios, so the stages edit and the parts edit are compared with today's code given the
same edit. The tests (`spike/tests/test_one_engine.py`) check the same on a smaller scale: the per-part memo against
a fresh build on a made-up scene and after a stages and a paint edit, the readings kept and read back, the
engine's call against `tools.main`, the client and server as processes, and the sailboat fixture through
build-steps to check and a stages edit, against the tools run without the engine.

## Before and after

Measured on 4 cores shared with other agents' tests, so each pair took turns, fixture by fixture, before then
engine, three times. Medians of the 3 runs, lowest to highest in brackets. "Tool seconds" is the sum of the `seconds`
each tool prints; wall includes starting each process (or the client). Every engine run started a new engine with
an empty readings folder.

| Fixture | Scenario | Before, tool seconds | Engine, tool seconds | Before, wall | Engine, wall | Wall saved |
|---|---|---|---|---|---|---|
| chickadee | full | 95.6 (78.5 to 104.7) | 52.8 (40.4 to 64.8) | 102.3 (80.4 to 106.8) | 53.5 (41.0 to 65.5) | 48% |
| chickadee | stage | 65.2 (63.8 to 70.0) | 13.0 (12.8 to 13.3) | 66.7 (65.2 to 71.8) | 13.4 (13.2 to 13.7) | 80% |
| chickadee | part | 92.4 (90.7 to 107.2) | 31.9 (28.2 to 32.3) | 94.3 (92.7 to 109.2) | 32.5 (28.9 to 32.9) | 65% |
| lavender balloon | full | 67.0 (66.0 to 68.6) | 49.4 (46.0 to 52.1) | 68.7 (67.7 to 70.4) | 50.1 (46.6 to 52.6) | 27% |
| lavender balloon | stage | 54.1 (52.9 to 54.1) | 12.0 (11.7 to 12.2) | 55.4 (54.3 to 55.6) | 12.5 (12.1 to 12.7) | 77% |
| lavender balloon | part | 80.4 (69.3 to 88.0) | 25.8 (23.5 to 26.3) | 82.3 (71.2 to 90.9) | 26.4 (24.1 to 27.0) | 68% |
| red sailboat | full | 71.9 (69.0 to 76.3) | 43.8 (41.8 to 52.8) | 73.8 (70.7 to 78.5) | 44.4 (42.4 to 53.4) | 40% |
| red sailboat | stage | 43.1 (42.5 to 45.2) | 8.4 (8.1 to 9.0) | 44.5 (44.0 to 46.6) | 8.8 (8.6 to 9.5) | 80% |
| red sailboat | part | 69.9 (55.4 to 70.3) | 19.3 (15.6 to 19.5) | 71.9 (57.2 to 72.2) | 19.9 (16.1 to 20.1) | 72% |
| All nine | | | | 666 (617 to 682) | 268 (240 to 275) | 60% |

Each tool, wall seconds summed over the three fixtures (median of 3):

| Tool | full: before | full: engine | stage: before | stage: engine | part: before | part: engine |
|---|---|---|---|---|---|---|
| outline | 76.3 | 86.0 | | | 84.2 | 13.6 |
| paints | 2.8 | 1.4 | | | 2.9 | 1.4 |
| build-steps | 31.0 | 28.5 | 31.4 | 10.1 | 31.7 | 27.7 |
| step-aids | 25.6 | 5.3 | 25.1 | 4.7 | 24.3 | 5.6 |
| mix | 2.0 | 1.5 | 2.3 | 0.2 | 2.1 | 0.3 |
| draft-text | 24.2 | 5.0 | 24.8 | 4.8 | 24.5 | 4.8 |
| card-adapt | 1.2 | 0.2 | 1.2 | 0.2 | 1.1 | 0.2 |
| check | 28.2 | 7.4 | 28.4 | 7.5 | 27.9 | 7.3 |
| publish | 53.1 | 18.3 | 53.2 | 7.3 | 53.0 | 15.4 |

What the numbers say:
- **The first outline is no faster** (76 against 86 seconds over three fixtures, and single runs went from 13 to
  39 seconds either way, so that difference is noise or the 70 MB written to disk). The engine reads the picture
  like today the first time. After that: 13.6 seconds for the three part-edit outlines, against 84.
- **A finish already read, in a new engine:** with the readings folder kept from an earlier run, the first outline
  took 3.9 to 6.0 seconds against 12.3 to 14.5 with an empty folder (one run each, the machine quiet).
- **build-steps gains only when something is kept.** The first build and a build after a parts edit (new outlines)
  are the same work as today. After a stages edit it's 10 seconds against 31: only the parts whose steps changed are
  prepared again.
- **Every tool after build-steps** stops rebuilding the steps: step-aids, draft-text and check drop to about a
  fifth, publish to a third the first time and a seventh after a stages edit.

Memory: the engine's peak was 3.7 to 3.9 GB serving one fixture's three scenarios (`status` prints it; the outline
model is most of it, as in today's `outline`, which peaks at about 3.2 GB but only while it runs). The per-part memo is
capped at 1 GB and the build memo keeps 4 builds, as in the tests. On a real finish (twice the fixtures' pixels) a
lesson's memos take about twice as much. One engine serves one call at a time.

## Not tried, or not known

- **Calls in parallel.** The engine takes one call at a time; a run that calls two tools at once waits.
- **The trace.** These are tool seconds and wall times on the three test fixtures, not a run's phases on the
  frozen bench, and Claude's own time (most of a run) isn't in them. #165's run trace
  (`spike/experiments/bench/run_trace.py`) reached main while this ran; it wasn't used here.
- **A real run.** No `/paint-lesson` run used the engine. The skill would need a step that starts it and swaps
  `tools.py <tool>` for `tools.py engine call <tool>`, which changes the skill: that's for the verdict.
- Windows: the engine uses only a TCP socket on 127.0.0.1 and a state file, but it was run only on Linux.

## Verdict: open

The build is done and proven byte for byte, and on the fixtures the tools spend 60% less time. The verdict waits on
#165's run trace: before and after numbers on the frozen bench, split into Claude's time, tool time and render time,
to say whether the tool time saved is a real share of a run. Until then nothing in `/paint-lesson` changes.

## To run it again

```
git archive --format=tar bb39e54 spike techniques palettes photos docs .claude > main.tar   # today's code
mkdir main && tar -xf main.tar -C main && ln -s $PWD/.venv main/.venv && ln -s $PWD/models main/models
python spike/experiments/v3_one_engine.py run --mode default                 # this branch, against the golden
python spike/experiments/v3_one_engine.py run --mode engine
python spike/experiments/v3_one_engine.py bench --before main --repeat 3 --out bench.json
python spike/experiments/v3_one_engine.py table bench.json
```

Each run takes about 4 minutes a fixture before and 2 with the engine on a quiet machine. The outline model must be
in `models/`.
