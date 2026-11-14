# Changelog

What each Gesso version added to the lessons it makes. Every lesson is stamped with the version that made it
(page footer, receipt, `lesson.json`), so an older lesson is missing whatever came after its version.

While Gesso is a proof of concept (POC), the minor number goes up for anything that changes what a lesson looks
like or contains, and the patch number for fixes. The numbers before 0.9.0 were given afterward, from the history.

## POC 1.9.0 (2026-11-14)
- A step's Where line places what the finished painting shows, not paint a later part covers (#126). A sky painted
  past the horizon gives the visible horizon and adds "paint a little past its bottom, under where ... will go", and
  an outline that runs behind an object not painted yet says to paint straight through there. On the red sailboat
  fixture the water's top read "4 1/2 in from the top" where it starts about 5.9 in down; it now reads 5 in from
  the bottom. The drawn outline doesn't change.
- `elements` and `check`: when a step's paint clashes on value only because its show put it on the wrong element
  step (a "Darken" step set to `full` lands on the light texture step), the message says to change the show and
  names the one to use, instead of pointing at the paints (#140).
- A sealed run's history entry shows the sealed lesson's numbers (#135). When the seal has the same step pictures,
  lines, and paints as its draft publish, its entry now takes the seal's metrics, version stamp, and provenance
  instead of keeping the draft's. On `chickadee_skill_20261114-022627` the entry said 0 text problems and 12.6
  minutes where the sealed lesson had 6 and 17.9. Publishing the same lesson again still records nothing.

## POC 1.8.1 (2026-11-14)
- `check` fails on a paint no step uses, naming it and saying to take it out of `paints` or use it in a step (#136),
  so a lesson can't seal with a mix in "Your paints" the painter never uses. On `chickadee_skill_20261114-022627`,
  `bird-2` (made by `paints --add bird` for a shade pass that was then dropped) stayed in the lesson. A base that
  only a used tint or shade is made from counts as used.

## POC 1.8.0 (2026-11-14)
- A `busy` tool measures how much of a picture is fine texture (#109): the share of the canvas covered by hundreds
  of small items, like lavender stalks. It writes a picture of where that texture is, and records the number in the
  lesson's notes. Step 0c runs it on the photo before Claude decides whether the picture is too busy for a
  beginner, and the drop list names where the texture is. It's an aid, not a threshold: Claude still decides.
- When a beginner version is made, `busy` checks it and the finish: fine texture has to come down from the photo's
  (the lavender went from 10.3% to 0.2% and under). If it didn't, that's a reason for the one redo. The seal wants
  the numbers, and the page's "Beginner version" notes show them.

## POC 1.7.0 (2026-11-14)
- A beginner card, "Paint thickness and how much is on the brush" (#99), in Before you start. It explains the six
  words a lesson uses for loading the brush. How thick: thick, creamy, or thin. How much: a full load, a light load,
  or wiped nearly dry. Each has a picture of the dab on the palette or the loaded brush, the stroke it leaves over a
  dark line, and one line of how to get there. "Creamy" means how thick the paint is, not how much of it.
- Every stroke card's load uses only those words ("Creamy paint, a full load", then anything else about loading),
  and `cards` reports a card that uses another. A step's Load line links each word to the card and shows its two
  small pictures under the line, so the painter doesn't scroll back. The stroke card's own Load row links the words
  too, without repeating the pictures.

## POC 1.6.1 (2026-11-14)
Fixes to the thin-part outlines (#129, from PR #133's review):
- `outline` tells a thin part the model is unsure of to add points and a path per limb, not to tighten a box it
  doesn't have.
- A plan with an empty path, or a point that isn't `[x, y]`, in a thin part's `paths` is refused with what to fix,
  where `outline` crashed on it.
- The skill's fix table says what to do when a branch takes the top of a leaf its stem runs into: end that path short
  of the leaf.
- In the lesson history, `chickadee_skill_20261114-022627` says POC 1.6.0 but was made by another build of #129
  (PR #133, commit ff98b7b): limbs asked only for a path the first answer missed, and SAM ViT-B kept for areas and
  objects. The 1.6.0 lines below describe the build that merged (#132), not that run.

## POC 1.6.0 (2026-11-14)
- Thin parts (a branch, a mast and its boom, a rail) get clean outlines (#129). They used to be found by color
  alone, which left blobs of misty background stuck to the chickadee's branch (#100) and a lumpy mast with a boom
  twice too thick. Now the outline model finds them: asked once for the whole part and once for each limb, with
  the color rule checking each limb. Tried on all 18 thin parts in the saved runs and fixtures: every branch keeps its twigs and every mast its
  boom, with small faults left on three (a few specks of foliage on one branch; on two sailboats the boom takes
  the deck line its path runs along). Before and after: docs/spikes/outline-models-join.jpg.
- The outline model is SAM-HQ ViT-L in place of SAM ViT-B: a 345 MB download the first time, and about 4 seconds
  more per `outline`. Still free, local, and the same bytes for the same finish and plan.
- A small thing with a clear edge (a bird's feet) is planned as an `object`, not `marks`, so it no longer takes a
  slab of what it sits on. Mist, clouds, reflections, and foliage stay `marks`.
- Marks painted on an area are still found when the model outlines the area without them (hedges on a field).

## POC 1.5.0 (2026-11-14)
- "Before you start" holds only the basics every painter needs before the first stroke (#95): setting up, keeping
  colors clean, how much water, and keeping paint wet, as open cards under "Getting started", with fixing a mistake
  folded as "If something goes wrong". The other six basics cards are open in the step where they first matter: let
  each layer dry where paint first goes over paint, colors dry darker at the first big coat, light over dark at the
  first coats line, lighter or darker at the first tint, one light direction at the first lighter pass, and the ugly
  stage at the stage start nearest halfway (never the last step). Each shows once; a card whose moment never comes
  isn't shown. `check` notes a lesson with no step for let it dry.

## POC 1.4.1 (2026-11-14)
Nothing a lesson shows changes. The tests are fast again (#87), and publish is faster.
- publish parses the stroke cards and element files once instead of about 60 times a lesson (that was about half
  its time), and when several tools run in one process the step pictures are built once.
- `python spike/tests/suite.py --quick` runs the quick set after a change, and `python spike/tests/suite.py` the full
  suite on every core before a merge (docs/testing.md).

## POC 1.4.0 (2026-11-13)
- Every step says where in inches from the canvas edges, never by tape marks (#122). Every lesson now has a canvas
  size: without `--canvas`, the lesson takes the standard size closest to the picture's shape (8x10, 9x12, 11x14,
  12x16, or 16x20; 11x14 when two fit as well) and "What you need" names it, with "Using another size? Scale every
  measurement" and a ruler. The tape-marking card is gone from "Before you start"; the transfer outline stays in its
  closed fold, marked optional, and is placed by measuring from the edges. Close-ups give their grid in inches. `check`
  flags step text that places things by tape marks. A photo whose subject won't survive the crop to the default size
  gets the canvas-extend render, as with `--canvas`.

## POC 1.3.2 (2026-11-13)
- A construction diagram can give a paint by its id as well as its name (#91). Before, a diagram given paint ids
  drew every shape gray. A shape whose paint is no paint's name or id, or a #hex, is now one of `check`'s problems,
  naming the step, the diagram, the panel and the shape, instead of drawing gray with nothing said.

## POC 1.3.1 (2026-11-13)
Nothing a lesson shows changes. Pipeline v1 is removed (#82): the owner passed the v2 gate and won't go back to v1.
- `/paint-lesson` runs pipeline v2 (it was `/paint-lesson-v2` until now). The v1 skill and its tools are gone:
  `lock-steps`, `carry-forward`, `finish-from-step`, `split-texture`, `render-step`, `from-finish`, the throwaway
  filters, the v1 spike in `run.py`, and `publish` for a version 1 plan (it's refused with what to do instead).
- The lessons site's tiles hold versions from POC 1.0.0 on. The 13 versions before it (one 0.20.0, two 0.25.0, one
  0.26.0, nine 0.26.1) were taken off the site; they stay in the lesson history with every other run.
- `site-refresh` keeps a tile's known-problems count when its run isn't on the machine (a fresh checkout has no
  `output/`); before, it set the count to 0.

## POC 1.3.0 (2026-11-13)
- The top of a lesson page is shorter, and the steps start much higher (#94). Right after the finished painting,
  "Tubes to get out" lists each tube with its color, in the order the steps first need it ("first in step 2"), so
  it works as a checklist. "What you need" no longer lists the tubes. "Your paints", every paint and its recipe,
  is folded closed, because each step already lists the paints it needs and mixing them all at the start leaves
  them drying on the plate. In "Before you start", the tape marks and the transfer outline sit in one closed fold
  marked optional, and the masking tape moved there from the canvas line. Version 1 pages are unchanged.

## POC 1.2.0 (2026-11-13)
- Six more element techniques in the library, drafted by the first 1.1.0 runs and approved by the owner: a feathered
  bird's body, soil strips between rows, a night sky with stars, snow, a glowing light in a frame, and a furry animal
  (#112 to #117). Lessons with these parts use them as library techniques, no longer marked "technique not checked
  yet" on their steps.

## POC 1.1.0 (2026-11-13)
- Every part follows an element technique (#12): how that kind of thing is painted, step by step, from the
  research file (`techniques/elements/`, 15 to start: skies, clouds, far hills, fields, foliage, pines, trunks and
  branches, round and shaped objects, flower rows, water, reflections, the sun path, fine lines). The plan names
  one per part with a reason, its steps follow it in order, and `check` says when they don't. The lavender rows
  are always laid flat, then stamped dark, mid, and light.
- A part nothing in the library fits gets a technique drafted for that lesson, marked "Technique not checked
  yet" on its steps, and filed for the owner to check.
- A step's watch-out line comes from its element technique when the element has one for that step.

## POC 1.0.1 (2026-11-13)
- Things no longer show before their step (#84: clouds, a ridge, and bands of hill color in the lavender's first
  sky step; hills under the sailboat's sky; the chickadee's feet as dark patches on the branch). What's painted
  under a thing is now taken from clean paint away from that thing's rim, a sky or water is carried on row by row
  from its own clean rows, and a flat coat no longer stays where another part will cross.
- `build-steps` and `check` measure it: a part that plainly shows before its step is a failure, and one that shows
  faintly is a note. The three lessons on the site are 1.0.1 runs (2026-11-13, hands-off); the 1.0.0 gate runs
  stay in each tile's version list.
- `site-refresh` and `site-add` only add versions to the lessons site (#83). A listed version stays even when its run
  folder isn't on this machine, and `site-add` keeps the old default as a version; `site-refresh --remove` takes one
  off by name.

## POC 1.0.0 (2026-11-13)
Pipeline v2: the finished painting is rendered once and every step picture is cut from it. The owner passed the
gate on 2026-11-13 ("The pics look good. Publish them as 1.0.0"). The first three 1.0.0 lessons on the site (red
sailboat, chickadee, lavender balloon) are the gate runs themselves. They were made at commit `a2a6d61`, just
before the number changed, and carry the 1.0.0 name at the owner's word; the commit on each page says exactly
which code made it. The lavender run predates the fix for stray pieces of an area, and lists that fault under
Known problems. The v1 skill and tools are still in the repo until their removal (#69).
- Version 2 lessons go through `publish`, `mix`, the seal, the page (stage headings), and the history (#65).
- `paints` measures a version 2 lesson's paints from the finish, marks tints and shades of a part's main paint, and
  merges the rest toward the technique's `max_mixes` (10 for the beginner paint-along), never an accent and never
  two colors a painter can tell apart (#66).
- Teaching pictures (`step-aids`) and the version 2 lesson page: each step's Where outline over the picture before
  it, close-ups, paint maps, stroke cards, "Before you start" with the tape marks and the transfer outline (#68).
- `draft-text` drafts every step's lines from data (dry, rinse, where, paints in order, mix once, brush and load and
  motion from the stroke card, what it leaves, coats, watch out, step back), and `check` gathers every measured
  check in one list that `publish --final` must clear for a version 2 lesson (#51). `publish` records a lesson in
  `site/history/` only when its folder is under `output/` (or `GESSO_HISTORY` is set), so a scratch or test publish
  no longer writes into the real history.
- Fixes from three real v2 runs (2026-11-13): `outline` and `part-colors` need only the parts; `paints` measures
  with no steps, keeps every id on a rerun, never merges a paint a step uses, and `paints --add <part>` adds one
  color; the background render is asked for above 2% objects; an area's hole that fell behind it, and a marks part
  on a marks part, are reported; `publish` tolerates odd notes, matches `check`'s texture jumps, names step 7b, and
  lists a same-session text review under Known problems; `check` prints `problems`.

## POC 0.26.1 (2026-11-12)
- The lock's backward pass no longer tints a clean step with something a later step paints (#56: the sun path's
  warm glow showed as faint bands in the plain water step of both hands-off sailboat runs). Its tone shift still
  matches a whole area to the finish's shade, but may stray only 4 RGB levels from that broad shift locally.

## POC 0.26.0 (2026-11-12)
- The paint-lesson skill is a short spine (`SKILL.md`, about 700 words: arguments, the rules for the whole run,
  the steps in order) plus one file per step in `steps/`, read when that step starts, so each step's rules are
  fresh when they're used. The runs behind each rule moved to `docs/skill-history.md`.
- `publish --final` checks before it seals: the reviews ran, notes are complete, every step has its summary,
  brushes, strokes, `made_with`, and regions, and the publish checks are clean (or a long step is explained in
  `long_steps_kept`). It refuses with a list until they pass.
- The skill gaps two hands-off runs reported are fixed: the redo cap is spelled out, diagram previews need a
  publish first, `long_steps_kept` is in the notes schema, the text review checks `ok` steps' main shapes against
  the finish, and reviewers use the venv to zoom.
- The "uncommitted code" flag on a lesson's stamp works again (it never fired since 0.23.1).
- From the first run on the split skill: `photo_prep` is a dict from step 0 (the page also accepts a sentence),
  the lock runs between the two image review rounds (`fixed by lock-steps` is an action), the plan's `photo` is the
  fitted picture, and text doesn't point at diagrams before step 7 adds them.

## POC 0.25.2 (2026-11-12)
- Lesson pages on the site have a Known problems section: what the run's reviews found and left as they are, by
  step, and links to the issues filed about the run (open, or fixed in a later version). The tile says how many.
  `site-refresh` updates it as issues are filed and closed, without touching the lesson, so it stays hands-off.

## POC 0.25.1 (2026-11-12)
- `from-finish --in-place` is the skill's own step 6a inside its run, so the lesson can still be sealed hands-off; a
  copy without it is a recut. Once a run is sealed, its draft publishes leave the lesson history (they were work in
  progress). The history shows a Hands-off, Recut, Edited, or Unsealed tag on every run, and a band across the strip
  of each one that isn't hands-off.

## POC 0.25.0 (2026-11-12)
- Hands-off lessons: the skill's last publish is `publish --final`, which seals the lesson as made by the tool on
  its own. Every lesson records its provenance (hands-off, recut, edited after the seal, or unsealed), and only
  hands-off lessons go on the lessons site and its version lists. `from-finish` copies are recuts. The lesson
  history shows a Recut, Edited, or Unsealed ribbon across each run that isn't hands-off. `provenance-mark` records
  what's known about runs from before seals.

## POC 0.24.1 (2026-11-12)
- Each lesson's tile on the lessons site has a version pick list: every kept run of that picture, newest first,
  labeled with the Gesso version, the time it ran, and how its steps were made. Pick one and open it. Each version's
  page is written once to `lessons/<slug>/v/<run>/` and never rewritten; `site-refresh` adds new runs.

## POC 0.24.0 (2026-11-12)
- Spike (#8): `from-finish` cuts every step picture from the finished painting instead of rendering it, in a copy of
  the lesson. Each pixel goes to the step whose region and paints fit it (things in their own small box, like the
  balloon, are cut out whole with GrabCut), earlier steps paint straight through where later ones go, the first of
  several steps over one area is a flat coat, and the passes after it go on by value, darkest first, in equal
  shares. No renders, so nothing drifts and no lock is needed. `--steps` cuts only a group of passes and keeps
  the rest rendered (the hybrid). Findings: `docs/spikes/from-finish.md`.

## POC 0.23.2 (2026-11-12)
- Lesson history: every publish that changes a lesson's pictures or text is kept (`site/history/`: a strip of every
  step and a record of the version, commit, cost, redos, and checks; the full lesson in `<lesson>/versions/<n>/`),
  and `site/history/index.html` shows each picture's runs newest first, what changed between runs, the owner's
  scores (`history-rate`), and two runs side by side. `history-backfill` recorded the runs from before.

## POC 0.23.1 (2026-11-11)
- A lesson keeps the version it was made with (`gesso.made`) when it's republished; the footer says "republished
  with" the newer one, and the lessons site's tiles show the made-with version.
- The dirty flag only counts code that shapes a lesson (spike, techniques, palettes, the skill), not site/ or docs/.

## POC 0.23.0 (2026-11-11)
- A private lessons site (`site/`, deployed with Cloudflare Pages and locked with Cloudflare Access): `publish`
  also writes `lesson-standalone.html`, one self-contained page per lesson, and `site-add` puts it on the site.

## POC 0.22.0 (2026-11-11)
- The main subject keeps its shape: both reviews flag a subject whose outline, size, posture, or markings change
  between steps (the finish included) as a shape problem, never as drift, and the skill fixes it.
- `finish-from-step` rebuilds the finish from the last step, adding only its details; `carry-forward` copies a
  later step's subject onto an earlier step, free.

## POC 0.21.0 (2026-11-11)
- Research on flower masses and water reflections (23 more sources, 61 in all), with rules and seven new stroke
  results in the paint-along technique.
- `split-texture`'s new steps start blank (their own colors and text, not the parent's copy).
- `canvas-view` takes full paths and refuses missing files; old crops are dropped after steps are renumbered.
- A paint one tube already gives (within the slack) uses that tube straight; `publish` lists `duplicate_recipes`.

## POC 0.20.0 (2026-11-11)
- No texture arrives all at once: `publish` and `step-pairs` measure `texture_jumps` (a step turning over 10% of
  the canvas from flat to textured), and the skill fixes each one with `split-texture`, which inserts free
  in-between passes (the step's marks arriving darkest first) and renumbers the step images.

## POC 0.19.0 (2026-11-11)
- `--palette <name>`: lessons mix from the painter's own tubes (`palettes/owner.yaml`, 30 tubes) instead of the
  technique's five, and "What you need" lists only the tubes the recipes use. Big palettes are searched with a
  shortlist so a recipe still takes under a second.
- A lesson from a big palette shares a small set of tubes: the 8 most useful, plus one more at a time only when
  a paint can't get close without it (the lavender lesson went from 28 tubes to 12).
- A painter's own tubes are called by their labels ("dark ultramarine" isn't shortened to "ultramarine").

## POC 0.18.0 (2026-11-11)
- Values tables add to the instructions, never replace them, and are for depth on one thing. Color sequences like a
  sunset sky are named in the instruction, in order. The table now sits right under the instructions.
- `publish` lists paints an instruction or table names that aren't in the step's colors (`paints_not_listed`).
- Dense texture is split into passes over the whole area, never cut along a line. The step review flags
  `split_edge` and `shape_change` (a path or row changing shape), and the skill fixes both instead of leaving them.

## POC 0.17.1 (2026-11-11)
- The backward pass shifts the broad tone of matching areas inside later boxes to the finish's, keeping the
  brushwork, so box edges don't show as straight tone steps (sailboat run: a lighter rectangle in the water).
- `lock-steps` keeps a step redone after a lock as its new raw render, instead of locking the stale one.

## POC 0.17.0 (2026-11-11)
- `lock-steps` runs a backward pass from the finish when every step has regions: wherever no later step paints,
  a step already shows the finished painting, so the last step only shows what it adds (#30).

## POC 0.16.0 (2026-11-11)
- `protect` boxes: inside a step's regions, things already painted that must stay put. There only the step's own
  paints may change anything (matched mostly by hue, so shaded strokes count), with a crisp edge (#30).

## POC 0.15.0 (2026-11-11)
- Step pictures no longer repaint earlier work (#30): each step says where it paints (`regions` in plan.json),
  and `lock-steps` puts back any change outside them, free. Raw renders stay in trials/raw/.

## POC 0.14.1 (2026-11-11)
- Canvas crops split the cut evenly between both sides, shifting only as far as the subject needs.
- No band-fill render when the photo already has the frame's shape: the cut-off edges fill the bands for free.
- `grid --percent`: lines at every 10% of width and height, so measurements match the page's percentages on any
  canvas shape.
- A stroke result for horizontal dashes on water (ripples, sun paths, reflections).

## POC 0.14.0 (2026-11-11)
- `--canvas WxH` (inches): the picture is fitted to the painter's canvas before planning, cheapest first: no
  change, a free crop that keeps the subject, or one render that extends the scene. A rectangular canvas hangs
  either way, so it follows the picture unless `--orientation` says otherwise.
- Renders stay in the image model's nearest frame; every step picture the painter sees is cropped to the canvas.
- Canvas size scales the lesson: the detail budget (fewer parts on a 10x10, more on a 24x30) and brush sizes.
- The page shows the canvas size and how many inches each 10% is, so grid positions can be marked with a ruler.

## POC 0.13.0 (2026-11-11)
- Show, don't tell: when something takes more than a sentence to explain (a shape, a stroke path, which value
  goes where), the lesson shows it with a diagram, a `values` table, or the step picture, and the words point at it.
- Steps can carry a `values` table (dark, mid, light: paint and where), shown with swatches on the page and in
  the walkthrough export.
- `publish` also lists single instructions over about 40 words in `long_instructions`.
- The word budget is a signal, not a cap: a long step is trimmed only where it repeats the page; an instruction
  doing two moves is split; a step that really has a lot to do is split in the plan, moved into strokes or a
  diagram, or kept long with a reason. Length is checked before the step review, so the reviewer catches any
  instruction trimming made vague.

## POC 0.12.0 (2026-11-11)
- A word budget for step text (about 100 words a step), with `publish` listing steps over it in `long_steps`.
  The page already shows recipes, brushes, strokes, and drying, so the text doesn't repeat them.
- The first step says where the light comes from.
- Paints used straight from a tube keep a one-tube recipe instead of a computed three-tube mix.
- Two more stroke results: strokes toward a vanishing point (rows, paths) and horizontal strokes for flat ground.
- `preview-diagrams` says when lesson.json has no diagrams yet, instead of blaming the browser.

## POC 0.11.0 (2026-11-11)
- Technique rules and stroke results now come from cited research (`docs/research/acrylic-paint-along.md`):
  three values per 3D object, a stated light direction, distance and edges, stroke direction, paint load in
  every instruction, drying before layering, coats for light over dark, and test strokes.

## POC 0.10.0 (2026-11-11)
- A fresh reviewer checks each step's text against a measured map of what its picture changed, and the skill
  fixes flat, missing, vague, and wrong-stroke instructions from it, shown under "What the reviewer caught" (#24).
- New technique rules: let a layer dry before painting over it, and give each area the values the picture shows
  (dark, middle, light) instead of one flat mix.
- The technique records what each stroke really leaves on the canvas (`stroke_results`).

## POC 0.9.0 (2026-11-11)
- Each lesson is stamped with the Gesso version, commit, and date (#27).

## POC 0.8.0 (2026-11-11)
- `publish` also exports `embed/`, so a blog post can show the lesson as a step-by-step walkthrough, with a
  one-line summary per step (#26).

## POC 0.7.0 (2026-11-11)
- A drawing of each brush and the mark it makes, in "What you need" and on every step (#25).

## POC 0.6.0 (2026-11-11)
- Paint recipes are computed with a pigment mixing model (Mixbox) instead of written by eye, with a "closest
  you can get" note for colors the tubes can't make (#22).
- Every step lists the paints it uses with their recipes, so you can mix as you go.

## POC 0.5.0 (2026-11-11)
- Busy pictures get a simpler beginner version first, and the lesson is made from it (PR #21).

## POC 0.4.0 (2026-11-11)
- Construction diagrams for shapes a beginner needs broken down, and a beginner check that decides where they
  go and says why (PRs #19, #20).
- Screenshots are cropped to the picture automatically.

## POC 0.3.0 (2026-11-11)
- "How this lesson was made": technique, step order, filters, review notes, and the receipt, folded away
  (PR #17).
- The sky runs past what covers it, and shapes are built from simple pieces (PR #18).

## POC 0.2.0 (2026-11-10)
- The `paint-lesson` skill: Claude Code runs the lesson, free filters first, paid renders only when needed,
  published as a Claude artifact with brushes and strokes per step (#7, #9, #10).

## POC 0.1.0 (2026-10-19)
- The pipeline spike: a lesson as a folder of step images from one script (#3).
