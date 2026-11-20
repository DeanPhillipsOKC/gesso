**Built (2026-11-20, POC 2.1.0).** The gate passed (section 13; `docs/spikes/v31-gate.md`) and the owner read the
highland cow and said "Looks good". `v3.1` merged into main; `pipeline-v3.md`, sections 4 and 10, describe the
pipeline as it now runs, and this file is the record of how it was designed and built. A draft (2026-11-20), built
on the branch `v3.1` (#276 to #278). The owner read it and merged it (#275), set the gate (section 13), and said go
on the combined lesson (section 12, steps 1 and 2; `docs/spikes/v31-combined.md`). It is the design the v4 plan's Order, step 5 asks for (`pipeline-v4-plan.md`),
written from the spikes that ended in adopt. It changes `pipeline-v3.md`; it doesn't replace it. Read that file
first: every section number below that isn't this file's own is v3's.

Each piece is marked **proven** (a spike ran it and its write-up has the numbers), a **guess** (this draft's own
joining of the pieces, run by nobody yet), or **open**.

## Why this is v3.1 and not v4

The owner asked (2026-11-20) whether the work is big enough to be another major version, and left the call to
Claude. It isn't:

- **v3's run has 13 rows (section 4). This replaces two of them** (9 and 10, the words), **changes how three are
  asked** (2 and 3, the plan's writer; 12, the finisher), **changes what one checks in the words** (11, `check`),
  **and leaves seven as they are.** No step picture changes. `plan.json` stays version 3. The chain, the paints,
  `build-steps`, the teaching pictures and the fact sheet aren't touched.
- **Nothing has to run beside anything.** v2 to v3 replaced how every picture is made, so v3 was built behind a
  flag, run beside v2, gated, and v2 removed (#238). Here the words stage is swapped in place. There is no `--v4`
  flag, no second pipeline to keep working, and no removal issue afterward.
- **What a major version would be:** a change to how the step pictures are made, or to what a lesson is. The two
  v4 ideas of that size were both parked: stroke maps (#256) and the easel coach (#257).

What follows from that:

- A lesson made this way is stamped **POC 2.1.0** (the changelog's rule: the minor number goes up when what a
  lesson contains changes). `lesson.json` keeps `"pipeline": 3`.
- **"v4" stays the name of the plan, its spikes and #240.** No file, issue or write-up is renamed: they are the
  record of how this was found. The plan's `pipeline-v4.md` is this file.
- Going back is one revert of the build, and every lesson on the site keeps the version that made it.

## 1. Why change

From the plan's Context, in short. v3's pictures are true and its words aren't taught:

- **A step's words don't say where the paint goes.** The cat's shading step gives a box 7 in wide (the whole cat)
  and the card's stock lines. The picture puts the dark under the belly and behind the head.
- **The data writes and the writer fills gaps.** `draft-text` writes most lines; a stage's writer adds a summary
  and a tip. Steps 14 and 15 of the cat share six lines.
- **A lesson is 21 separate forms.** Nothing says what the painter learns or ties a step to an earlier one.
- **The words were judged by readers who could see the answer.**
- **A lesson costs about $4.16 of Claude** at the API's rates, against an aim of $1.

## 2. The idea

1. **One teacher writes the whole lesson.** A writer who has seen every step's before and after picture, and a
   picture of only what the step changed, writes each step in the same six lines: First, Start, Strokes, Where the
   paint sits, Leave, Stop when.
2. **The fact sheet checks, and no longer writes.** `check-text` holds every number and side to the sheet, as in
   v3. `draft-text`'s lines stop being the step's words.
3. **The lesson has an arc.** The same writer then adds an opening, a line for each stage, and an "As in step N"
   line on a step that repeats an earlier stroke or paint.
4. **Every helper is sent less.** The plan's writer, the lesson's writer and the finisher get smaller pictures and
   only the files they use, and answer a check with what they change.
5. **A student test is the yardstick.** A reader with the before picture and the words, and no after picture, has
   to get to the after picture.

## 3. What's proven, and what isn't

| Piece | From | Proven | Not known |
|---|---|---|---|
| One writer for the lesson, six fixed lines (`lesson-slots`) | #254, 3 pictures | The student test: 3.43, 3.38, 3.20 against v3's 3.15, 3.21, 3.03 (+0.21 ± 0.11 over 64 steps). Blind graders preferred it 6 of 6. One word fault where v3 had four. Half v3's words. | The gain clears the 0.25 bar on the cow only. Neither test showed the page's outline and paint map, which v3's words lean on. |
| The arc, long form, added after the writer (`arc-add-long`) | #255, 3 pictures | Level on the student test (+0.05 ± 0.09). The owner read the cat's: "overall big improvement". 12 to 13 back lines a lesson. | It doesn't raise a score. The owner adopted it knowing that. |
| The lean words (`lean`) | #267, 3 pictures | $0.85 against $1.33. Level on the student test (+0.08 ± 0.10); 5 of 6 blind reads tied. | Four cuts tried together, one run a side. |
| The paint check on the words | #270, 3 pictures | 6, 22 and 2 sentences found; none left after one round. $0.07 a lesson. | The words weren't graded again after it. |
| The lean finisher (`f-lean`) | #267, 3 pictures | $0.50 against $0.80. Graders preferred it 4 of 6, none for the baseline. Every diagram drew. | It ran on the baseline's words, not the lean ones. |
| The plan's writer: changes, not the whole plan; picks its library files | #253, 3 pictures | The writer went from $1.68 to $1.03. Graders: no worse on the cow and the birch grove. | The cat lost all 4 reads. The owner judged that the loss wasn't the cuts'. |
| The student test | #174 | Its score falls when the words are made worse on purpose. A lesson's mean moves 0.12 between two runs. | Whether it finds the steps a real painter stumbles on (#252). It doesn't measure stroke direction. |

**What has run together:** the teacher, the arc, the lean cuts and the paint check, as `lean-paints` in #270, on
three pictures. **What hasn't:** those words with the lean finisher; the three changes to the brief in section 5;
a seal (`publish --final` refuses these words today); and any of it inside `/paint-lesson`. Every spike ran
through the program loop (`v4_loop.py`), where a helper is sent everything in one message and has no tools. The
skill's helpers are subagents that read a folder. That step is a guess (section 12).

## 4. The run: what changes

v3's table (section 4), with only the rows that change. Rows 0, 1 and 4 to 8 are as they are.

| # | v3 | v3.1 | From |
|---|---|---|---|
| 2 | The plan's writer is sent every element file, stroke card and the research. | It is sent the library's list, asks for the files it picks, then writes the plan. | #253, cut 4 |
| 3 | It answers `plan-check` and `check` with the whole plan again. | It answers with changes to the plan, which a tool applies. | #253, cut 3 |
| 9 | `draft-text` drafts the lines, then one writer a stage adds a summary and a tip. | `draft-text` still makes each step's header. One writer for the lesson writes six lines a step. | #254, #267 |
| 10 | `check-text`, one round of fixes a stage. | `check-text`, one round; the paint check, one round; then the arc as the writer's next message, with its own checks and one round. | #254, #270, #255 |
| 11 | `check` asks each step for a summary, a tip and lines under 40 words. | It asks for the six lines, and holds the arc's checks (section 7). | a guess |
| 12 | The finisher sees every step picture at 768 pixels and always looks at its diagrams. | It sees them at 384, and looks at the diagrams again only when one fails to draw. | #267 |

The chain's checker stays on Opus at medium effort (#268). Every helper stays on Opus (#267 dropped Sonnet).

## 5. The words

### What the writer is sent (proven, #254 and #267)

One writer, a fresh context, for the whole lesson:

- the brief;
- every step's header as the page shows it (name, paints with recipes, brush) and its stroke card;
- `plan.json`;
- the fact sheet, without what the lines don't use: the exact values in brackets, v3's Where line, the part as the
  finish shows it, and the neighbours not painted yet. `check-text` still reads the whole sheet;
- for every step, the before and after pictures side by side (512 pixels a half), and a picture of only what the
  step changed: the after picture where the step's color moved, the before picture washed pale everywhere else;
- the photo and the finish at 768 pixels.

`packets` writes this as one folder, `words/lesson/`, where it wrote a folder a stage.

### What a step says (proven, #254)

The same six lines for every step, one to three sentences each, about 130 words a step:

| Line | Says |
|---|---|
| First | What has to be dry first. Left empty when nothing does. |
| Start | Where the first strokes go, named by the thing and its parts. |
| Strokes | Which way to pull, and how, in this thing's terms. |
| Where the paint sits | Which parts of the thing get this paint and which don't, and why. |
| Leave | The earlier paint or bare canvas that has to stay. |
| Stop when | What it looks like when the step is done. |

How a stroke is done is still the card's. The teacher puts it in the subject's terms and doesn't change it
(`docs/decisions.md`, 2026-11-12 and 2026-11-13). The number and side rules are v3's, with one more: a place
inside a thing that the sheet doesn't measure is named by what it is ("where the belly meets the blanket"), not
with a side word pointing at it.

**The summary and the tip go.** v3's writers wrote both; the six lines hold what they held. The site's embed
already falls back to a step's first sentence when there is no summary (`lesson_embed.summary_of`). (Guess: no
spike sealed a lesson without them.)

### Three changes to the spike's brief (guesses, from #254's "Before it goes into a run" and #267)

1. **An earlier step's marks are named by their look and step, not their paint.** The spike's brief said both
   "name only the paints the step lists" and "name an earlier step's marks by their paint", and the writer then
   named the earlier paint on 12 of 64 steps ("The Wood brown must be dry"). The new rule: "the brown streaks from
   step 8". The paint's name is kept only where a side word needs it for `check-text` to find the thing. The paint
   check below is the backstop. The owner asked for this with no spike of its own (2026-11-20).
2. **A line is under 40 words,** as in v3. 20 of the spike's lines were over. The brief says it, and that isn't
   enough: in the combined lesson seven lines on two of three lessons were still over, all of them "Where the paint
   sits". So the words' rounds count them (below), and `check` holds the limit at the end.
3. **The writer is told what the page shows beside its words:** the transfer outline and the Where picture. It may
   point at them ("inside the outline"). The spike's writer didn't know they exist. In the combined lesson it
   never did, in 70 steps: the rule stays, and it changes nothing a painter reads.

### The checks and their rounds (proven, #254 and #270)

In the writer's one conversation, so each round reads what was sent from the cache:

1. `check-text`, strict, on every line. What fails goes back once, and the writer answers with only the steps it
   changes.
2. The paint check (`tools.paints_not_listed`, v3's own): a sentence that names a paint its step doesn't list goes
   back once. The writer names one of the step's own paints if that is the one meant, or says it without the name.
   A line over 40 words goes back in the same round, to be shortened. (A guess: the combined lesson counted them
   and sent none back.)
3. `check-text` again on the new words. A sentence that still fails either check is taken out, never reworded by a
   tool: a listed paint the writer didn't mean would have the painter load the wrong color.

A line emptied that way is left off the page and written into `review.json` as a known problem, as v3 does for an
emptied tip. (Guess: it didn't happen on the three lessons.)

### What the sheet can't check (open, and not in this design)

The teacher says more about place and the sheet checks less of it: 22 to 66 checkable claims a lesson against
v3's 100 to 115. "The crescent behind the head" has no side word, so it isn't a claim at all. To check it the
sheet would need a thing's pieces (the cat's head, ears, back, tail), each with its box, and the share of a step's
paint on each. That is a spike of its own, after the owner's painting (#252) shows whether a painter was misled.

## 6. The arc

**Proven (#255, `arc-add-long`; as the writer's next message, #267).** After the steps' words pass their checks,
the writer is asked for the arc in the same conversation, with each stage's last picture (480 pixels) added:

- **An opening,** read once before step 1: a welcome (what you're about to paint, its focal point, the mood); the
  light (where it comes from and what it does, named by its source, not a side); two or three skills, each a stroke
  card the lesson uses, with its steps and two or three sentences; and the road to the finish in four to six
  sentences.
- **A stage opener:** one sentence of what the stage is for, shown at the top of the stage. One sentence of what
  the canvas looks like at its end, shown **after the stage's last step**. Shown above every step, it made the
  student paint toward a canvas several steps ahead (the cow fell from 3.43 to 2.79).
- **An "As in step N" line** on every step that repeats an earlier step's stroke card or paint, where saying so
  helps: what is the same and what is different this time.

No step's own lines change. The arc's checks, with one round of feedback and then taken out:

- a back line points at an earlier step that shares this step's card or one of its paints;
- a skill is a card the lesson uses, on steps that use it;
- the opening and the stage openers hold no number and no side word (the sheet measures steps, not stages);
- a back line is a step's line: `check-text` and the paint check hold it.

Asked this way the arc took a feedback round on 3 of 3 lessons, against 1 of 3 as its own call, and still cost
less ($0.14 and $0.09 against $0.24 and $0.03). After the round none failed.

### As built (#276, build 1, on the branch)

`spike/lesson_words.py`, `tools.py packets` and `check-text`, `v3/lesson-brief.md` and `v3/arc-brief.md`, `run.md`
step D. The writer's folder is `words/lesson/`, and it answers through files there: `out.json`, then `fix-1.json`
and `fix-2.json` (only the steps it changes), then `arc.json` and `arc-fix.json` (the whole arc again, as #267's run
asked for it). `check-text` runs the next round each time and says which file to send the writer back for;
`--final` takes out what still fails; `--arc` and `--arc --final` do the same for the arc. `words/lesson/rounds.json`
keeps each round's counts. Beside the spikes:

- **`paint_notes` stays** in the writer's form, as v3's: the seal still asks a paint the tubes can only come close
  to for a note, and `steps.md` marks such a paint.
- **A stage's end picture is the after half of its last step's pair** (`stages.md` says which), as #267's
  `arc-same` sent it, not a 480-pixel picture of its own.
- **`draft-text` still runs** and makes each step's header; on a step the writer wrote it adds no lines.
- **Until build 2 (#277, section 7's as-built), `check` and the seal took the six lines in place of a summary and a
  tip** and asked nothing more of them: the smallest change that keeps a lesson sealable on the branch.
- **The real run on the cat** (`docs/spikes/v31-build1-cat.md`): the subagent helper worked. Round 1 sent back 20
  failures, 11 of them check-text reading "nearest the window" as the window's sky.

## 7. The lesson file, the page, `check` and the seal (guesses: no spike sealed a lesson)

- **`text.json`:** a step's `lines` are the six, each with its `kind` (`first`, `start`, `strokes`, `inside`,
  `leave`, `stop`), then `back` (`{"step": 8, "text": ...}`) where there is one. No `summary` and no `tip`. The
  file gains `opening` and `stages` (`for` and `end` by stage). The spike kept those two in a side file.
- **The page:** "Before you start" above step 1 (the welcome, the light, what this painting teaches, the way
  there). Each stage's `for` under its heading and its `end` after its last step. Each of a step's lines with its
  label in bold. The header, the outline, the Where picture, the cards and the recipes are as they are.
- **`check`:** asks for the six lines, with First allowed to be empty, where it asks for a summary and a tip. It
  keeps 40 words a line, the paint rule, and the check of the words against the sheet as it is now. It adds the
  arc's checks, so an arc changed after its round can't be sealed.
- **The seal** asks for `check-text --final` as today. `lesson.json` adds the opening and the stage lines.
- **Older lessons** have no opening and carry a summary and a tip. The page shows what a lesson has, so the site's
  history still opens.

### As built (#277, build 2, on the branch)

- **The page** (`page2.six_lines`, `opening`, `stage_line`): a step's lines in a list, each with its label in bold;
  the back line's label is "As in step N" with N a link to that step, and it sits after Start, where `check-text
  --arc` put it. "Before you start" opens with the welcome, then "The light", "What this painting teaches" (each
  skill's card linked to its card and its steps listed), and "The way there". A stage's `for` line is under its
  heading; its `end` line, marked "End of the stage", is just before the "good place to stop" mark. A lesson with
  no opening and drafted lines gets v3's numbered list and its tip, as before.
- **`lesson.json`** gains `opening` and `stage_lines` (by stage id), and a back line in a stage's `lines` keeps its
  `step`. Neither key is written for a lesson without them.
- **`check`** asks a step with the writer's lines for Start, Strokes, Where the paint sits, Leave and Stop when.
  A line `check-text --final` emptied (`rounds.json`'s `emptied`) may be missing: it is a known problem in
  `review.json`. A step with the six lines and a v3 summary or tip fails. The 40 words, the paint rule and the
  sheet check are as they were, and cover the back lines. The arc's checks (`lesson_words.arc_problems`) run on
  the arc as `text.json` holds it, so a number or side added to the opening, or a back line pointed at the wrong
  step, can't be sealed. A part the arc's last check took out (`arc-dropped.json`) may be missing.
- **The seal** also asks for `check-text --arc --final` on a lesson with the writer's lines.
- **The site's card line** (`lesson_embed.summary_of`) is the Start line's first sentence when there is no
  summary, not the first line: a First line ("Let the wall dry") says nothing about what the step does. On the
  build 1 cat all 22 read as instructions ("Start with the wide upright of the frame, ..."). The tiles never read a
  summary.

## 8. The plan's writer and the finisher

**The plan's writer (proven, #253).** Its first message was 92,000 tokens, most of it the library. Now:

1. It is sent what it was sent before, with the library's list in place of the library (23 element files, 28
   cards, the research's 64 sections by heading). It asks for what it wants. In the spike it took about half.
2. It is sent those and writes `plan.json`.
3. It answers `plan-check`, and a merge `check` asks for, with changes only. `v4_loop.apply_plan_changes` moves
   into the tools as the thing that applies them. A reply that is a whole plan is still taken as it is.

**The finisher (proven, #267).** Step pictures at 384 pixels and the finish at 512. It writes `review.json`, the
diagrams and the notes in one reply. It looks at the diagrams again only when `publish` draws fewer than it wrote.

### As built (#278, build 3, on the branch)

- **The picks** (`spike/plan_writer.py`, `tools.py library`): `library --lesson` prints what `elements` prints, every
  card in a line and the research's "For Gesso" with the other headings; the writer writes `picks.json` and runs
  `library --picks`, which copies what it picked into `<lesson>/library/` (`research.md` holds "For Gesso" and each
  section picked). A heading matches without its #s or number, in any case; a ### section inside a ## section also
  picked is sent once; a name it doesn't know is a problem, and what matched is kept. A second ask adds to the
  first: the brief says ask once, and a writer started again for a merge may still need a file.
- **The changes** (`plan_writer.apply_plan_changes`, moved from the loop; `tools.py plan-change`): the writer
  writes `plan-changes.json` in the brief's shape and runs `plan-change`, which makes them, keeps each in
  `<lesson>/plan-changes-log.json`, and prints what `plan-check` prints. Changes that don't apply are a problem and leave
  `plan.json` as it was. A whole plan is still taken.
- **The finisher** (`tools.py small-pictures`, `steps/8-finish.md`, `steps/diagrams.md`): the step pictures at 384
  pixels and the finish at 512 in `<lesson>/small/`. The look at the diagrams is asked for only when
  `preview-diagrams`' `drawn` is under `specced`. **Changed from #267:** that spike counted `publish`'s
  `diagrams`, which counts the specs and not what draws, so a spec drawn as error text still counted (#267's Sonnet
  cat). `preview-diagrams` now says which specs draw nothing (`broken`).
- **The loop** (`v4_loop.py`) follows this `run.md`: the three cuts of #253 are always on, its words are one
  writer's with `check-text`'s rounds and the arc as that writer's next messages, and its finisher is the one above.

## 9. What it costs

Claude a lesson at the API's rates, from the spikes' means:

| | Steps 0 to the chain's checker | Words | Finisher | Lesson |
|---|---|---|---|---|
| v3, the program loop's baseline, priced the API's way | | | | $4.16 |
| v3 with the plan's writer's two changes | $1.72 | $0.96 | $0.97 | $3.65 |
| v3.1 | $1.72 | $0.92 | $0.50 | **about $3.13** |

Renders are beside that: $0.55 to $0.95 a lesson, unchanged.

- **About three times the $1 aim.** The aim isn't a gate (`docs/decisions.md`). What is left, largest first: the
  plan's writer ($0.72 to $1.03), the words, the finisher, steps 0 and 1, the chain's checker.
- **These are the loop's numbers.** A `/paint-lesson` run is on the owner's subscription and logs no tokens. The
  first of #253's three cuts, pricing and caching each call as the API would, isn't something the skill builds: it
  holds for the loop now and for the app's Worker later.
- **So the loop is kept as the meter.** `v4_loop.py` follows `run.md` in code. After the build it follows the new
  `run.md`, and the cost of a v3.1 lesson is measured there.
- **Measured after build 3 (#278, `docs/spikes/v31-build3-cat.md`):** the sleeping cat, sealed by the loop on the
  new `run.md`, $2.98 at the API's rates ($1.36 to the chain's checker, $0.90 the words, $0.72 the finisher, which
  looked at its diagrams once because three drew nothing). One run.

## 10. The yardstick

**The student test joins the bench (proven, #174).** It isn't part of a lesson's run. It is run at the gate, and
for any later change to the words:

- **The score is carry:** the image model does each step's words on its before picture, and a grader who never
  sees the words scores the result against the real after, 1 to 5. A change counts only at about 0.25 or more on a
  lesson's mean. About $0.62 of Claude and $0.33 of renders a lesson.
- **The fault finder is pick:** a reader picks the after picture out of four. A step whose words score 0.25 or
  more below its header alone has words that point the wrong way. About $0.90 a lesson beside saved header runs.
- The blind A/B page and the graders' brief stay as they are.

`v4_student.py` stays under `spike/experiments/` with the bench it reads.

## 11. What goes, and what stays

**Goes from the run:** one writer a stage and `v3/writer-brief.md`; a step's summary and tip; `draft-text`'s body
lines as the step's words (the measured Where line, the outline lines, the card's motion and result lines). The
experiments' variants that lost (free prose, a writer a stage, `arc-whole`, Sonnet, low effort, the split
finisher) stay in `spike/experiments/` as the record and are built nowhere.

**Stays as it is:** steps 0 and 1; `plan.json` version 3, its brief's rules and `plan-check`; `erase`, the chain's
checker and its brief; `paints`, `mix`, `build-steps`, `step-aids`; the fact sheet and `check-text`'s rules;
`draft-text` for each step's header, and so that `check` can still run before the words are written (v3's step
C3); the cards and the research; diagrams, notes, the seal, `publish`, the history and the site; inches, never
percent; acrylic, beginner, 12 to 24 steps; lessons made on Opus.

## 12. Build order

1. **Done (2026-11-20, `docs/spikes/v31-combined.md`).** **One combined lesson, by experiment code:** the sleeping
   cat, with everything in sections 5 to 8 and the brief's three changes, as a page the owner can read. Most of it
   exists (`v4_writer_cost.py`'s `lean-paints` and `f-lean`). New: the brief's changes, and the two run together.
2. **Done: go (the owner, 2026-11-20, "Looks good").** **The owner reads it:** go, change or stop. This draft is then
   corrected by what it showed: the 40-word round and the writer's silence on the page's aids (section 5), and one
   more risk (section 14). The owner also had it run on the chickadee and the lavender balloon, which his partner
   means to paint.
3. **Built (#276 to #278): it is in `/paint-lesson` in place,** on the branch `v3.1`, with no flag (#276 the words, #277 the page,
   `check` and the seal, #278 the plan's writer, the finisher and the loop; by Opus):
   - the tools: `packets` for a lesson writer, `check-text` reading the six lines, the paint round, the arc's
     checks, the tool that applies the plan's changes;
   - the briefs: `v3/lesson-brief.md` and `v3/arc-brief.md` in place of `writer-brief.md`; the plan's brief for its
     picks and its changes; step 8's for the finisher;
   - `run.md`, steps A, D and E;
   - the page, `check` and `publish --final` (section 7);
   - `v4_loop.py` brought into step with the new `run.md`.
4. **Done: passed (2026-11-20, #279, `docs/spikes/v31-gate.md`).** The gate, run from that branch before it merged.
5. **Then** merge, stamp POC 2.1.0, write the changelog entry, and fold the as-built facts into `pipeline-v3.md`,
   sections 4 and 10, so one file still describes the pipeline. The site's lessons still wait to be rerun from
   v3's gate; rerun them once, after this.

**The guess to watch in step 3** is the helper. In the loop the writer is sent everything in one message, has no
tools, and its rounds are one conversation. In the skill it is a subagent that reads `words/lesson/` and is sent
back with a message. It should read the same files and write the same JSON, but nobody has run it.

## 13. The gate (set by the owner, 2026-11-20)

The v4 plan proposed four lines. With no second pipeline to choose between, the gate is what lets the build's
branch merge, so this draft changed one of them, and the owner took it as written ("Default",
`docs/decisions.md`):

- three hands-off bench lessons (the cow, the cat, the birch grove) made from the branch, sealed;
- the student test's score is no lower than v3's words on any of them, and higher across the three;
- Claude's graders prefer them to v3's lessons on most pictures and they lose clearly on none;
- **the owner reads one finished lesson and says yes;**
- the lesson's Claude cost, from the loop, is reported beside the $1 aim. It isn't a pass or fail.

**Changed from the plan:** "the owner paints one v4 lesson" becomes "the owner reads one". Painting one stays the
real test (#252), but it takes an afternoon and two people, and a branch shouldn't wait on it. What the painting
shows is fixed afterward, as changes to v3.1.

## 14. Known risks

- **The gain is small.** The teacher's +0.21 clears the bar on one picture of three, and the arc is level. The
  strongest evidence is the graders' 6 of 6 and the owner's reading of one lesson.
- **More is said about place and less of it is checked** (section 5). A wrong "behind the head" passes.
- **Words can pass every check and still disagree with their picture.** The combined cat's finisher found three
  (pale streaks called dark, a shape said to reach an edge it doesn't, a nose twice its size), and they ended as
  known problems on the page. Sending the finisher's finds back to the writer once would fix them at the cost of a
  round. Nobody has run it, so it isn't in this design.
- **Neither test showed the page's aids.** v3's words may do better on the real page than they scored.
- **One word fault is left:** the birch grove's step 20, where "most of it on the right side" is true by the
  sheet's halves and still misleads.
- **A student made of models is not a painter.** #252 is the check, and it hasn't happened.
- **Each cut ran once a picture,** and the four lean cuts only together.
- **The skill's helper isn't the loop's** (section 12).
- **No words fix a picture.** The faults the graders marked worst are in v3's pictures (the cat's leaf steps,
  #262), and they are still there.
- **Cost is still three times the aim.**

## Not in this design

Stroke maps (parked, #256). The sheet's pieces of a thing (section 5). The easel coach (parked, #257). A cheaper
chain checker or another provider's model (#268 dropped, #221 blocked). The words at low effort (parked). The two
unbuilt fixes for a late merge's cache (#253): #250 took most merges away.
