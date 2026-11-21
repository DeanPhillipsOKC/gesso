# Decisions

Product and working-rule decisions the owner has made. Agents read this before proposing,
filing, or building anything, and don't re-propose what it rules out. Add new decisions here
with the date.

## Product

- **Name: Gesso (2026-10-19)**, renamed from PaintPath. A quick search found no painting app by
  that name (only an unrelated audio-tour app). Revisit before any app store listing.

- **The technique sets the rules; Claude plans the steps for each picture (2026-10-19, owner's
  call; replaces "the technique library decides the stages").** A fixed list of stages left empty
  steps (a "ground" step for a photo with no ground). A hand-checked technique per medium and
  level sets the rules: painting order, starting canvas, palette, brush moves, one thing per step,
  and a step-count range. Claude (not another provider) breaks the simplified reference into its
  parts and plans the steps within those rules, each with its colors as named mixes from the
  palette. The image model renders the plan, and Claude writes the final instructions from the
  rendered images so the words match the pictures. There's no limit on calls: add one when it
  measurably improves the lesson.
- **Real technique drives generation (2026-10-19).** Every stage image comes from a lesson plan
  built on real painting technique for the medium and level. Never ask an image model to invent
  the steps on its own; the steps come from Claude's plan under the technique's rules.
- **Acrylic only for the proof of concept (2026-10-19).** Oil comes after acrylic lessons are
  good. Other mediums wait longer. The first technique is the standard beginner method: block in
  the big shapes, then build up in layers (`techniques/acrylic-block-in-beginner.yaml`).
- **Paint back to front (2026-10-19, owner's correction).** Acrylic lessons go background first
  (sky, distant things), painted straight through where silhouettes like branches will go, then
  whatever is in front on top of it, back to front. Not "darks first." The sketch is traced from
  the finished painting so it outlines everything.
- **Paint-along for acrylic, wet-on-wet for oil (2026-10-19, owner's pick).** The owner follows
  YouTube-style tutorials, which skip toning, sketching, and block-in. Acrylic beginner lessons use
  paint-along: white canvas, sky, far shapes, ground, main shapes, texture, shadows, highlights,
  each step naming its brush move (`techniques/acrylic-paint-along-beginner.yaml`). Block-in stays
  in the library as an option. When oil comes, its beginner technique is wet-on-wet.
- **Simplify the photo first (2026-10-19, owner's idea).** Every lesson starts by turning the
  photo into a simplified reference matched to the skill level (fewer shapes, three values, a
  palette the painter can mix), and the painting is made from that, not the raw photo. It's shown
  to the painter next to their photo.
- **Beginners first (2026-10-19).** The owner and their partner are beginners, so the Beginner
  level gets the most care. Intermediate and Advanced follow.
- **Quality first, then cost (2026-10-19).** Until there's a measured baseline, use the best
  models and settings: Claude Opus 5.5 for text and vision, and the highest-quality setting of
  OpenAI's current gpt-image model. Record the cost and time of every call. Cost work starts only
  after the baseline exists, and every cheaper option gets compared against it on the reference
  photos before it's adopted.
- **Low image quality while experimenting (2026-10-19).** The baseline exists: on the trees photo,
  a lesson cost $0.26 and 2.4 min at low, $0.30 at medium, $0.52 at high, and $1.39 and 9.8 min
  at max. Every quality level followed the back-to-front instructions, and differences between
  runs were about as big as differences between levels. So experiments run at low. Bump the
  quality up if a run stops following directions (painting order, coverage, continuity between
  steps), and judge final picture quality separately.
- **Slow is fine (2026-10-19).** Quality beats speed. A lesson can take minutes to generate as long
  as progress is visible and a finished lesson is saved.
- **Photos stay private (2026-10-19).** No public gallery or sharing by default, and lessons are
  easy to delete. This is for the app's users. For the POC (2026-11-12, owner's call), the lessons site and the
  repo show the source pictures, so they're only AI-generated images or ones the owner has the rights to; the
  owner picks sources with that in mind. Never put a personal photo (people, homes, anything private) in a lesson
  that goes on the site or in the repo.
- **Image model: OpenAI's gpt-image family first (2026-10-19)**, behind a small interface so the
  provider can change. Claude does the planning, instructions, and checks.

- **Stack: Vue PWA, local storage, and a small Cloudflare Worker (2026-10-19).** A Vue 3 +
  TypeScript PWA, like RepBunny. Lessons are stored on the device (SQLite in the browser or
  IndexedDB for lesson data, browser file storage for images), with no accounts. A Cloudflare
  Worker holds the Anthropic and OpenAI keys and runs generation in the background, since keys
  can't live in the PWA and phones suspend tabs mid-lesson. The Worker keeps nothing once a
  lesson is downloaded. Sharing lessons between phones waits until after real use.

- **Filters first, image generation as the fallback (2026-11-10, owner's call).** Image costs add
  up while experimenting, and much of a lesson (value studies, palette, simplified shapes, the
  sketch, back-to-front steps built from masks of the finish) can come from ordinary filters and
  compositing for free. Claude picks a tool for each step and uses gpt-image only when no filter
  or composite does the job, giving a reason for each render. Renders have a dollar cap per
  lesson and a redo cap per step. The finish is still rendered. Cheaper lessons still get compared
  against the low-quality baseline before the approach is adopted (#7 to #10). When no filter
  fits a step, Claude writes a throwaway filter script and tries it before rendering, and files
  a filter request (with the script) for anything a filter could have done (#11).
- **Claude chooses the techniques for each photo and level (2026-11-10, owner's call; updates
  "the technique sets the rules").** One fixed technique may not fit the subject or the level,
  and most pictures mix parts painted differently. The library becomes hand-checked building
  blocks: whole-painting approaches (painting order, ground, step range) and element techniques
  (sky, foliage, water, fur, ...). Claude picks an approach and an element technique per part,
  with a reason for each. Real technique still drives generation: when nothing in the library
  fits, Claude drafts one from real painting practice, marks those steps as not checked yet, and
  files the draft for the owner to check (#12).
- **A picture too busy for the level gets a beginner version first (2026-11-11, owner's call).**
  Every step is copied from the finished painting, so its detail decides what the steps must
  paint. The balloon lesson kept a village of tiny houses and every lavender stalk, and one step
  jumped from flat rows to thousands of stalks. When a picture has tiny separate things, textures
  made of hundreds of items, or more parts than the technique's detail budget, Claude first makes
  a loose, impressionist beginner version: it drops the extras, merges what's busy, and turns
  textures into one repeated mark. The lesson is made from that version. No step may jump from
  flat to dense texture; dense texture is split into passes.
- **Mix recipes are computed, not written by eye (2026-11-11, owner's call, #22).** A pigment
  mixing model (Mixbox) solves each paint's recipe from the palette tubes and reports how far it
  lands (Delta E). Mixbox is CC BY-NC: free while Gesso isn't sold. If it ever is, swap in
  Spectral.js (MIT) or buy a license; only `spike/mixing.py` touches it. Every step lists its own
  paints and recipes, because beginners mix as they go and acrylics dry on the palette.
- **Technique comes from cited research, not from the model's memory (2026-11-11, owner's call).** Each
  medium gets a research file in `docs/research/` (acrylic first: `acrylic-paint-along.md`, 38 sources), and
  its "For Gesso" rules and stroke results go into the technique YAML. The lesson skill reads both. Acrylic
  only for the POC; oils or pastels would each get their own research file and techniques later.
- **Lessons can use the painter's own paints (2026-11-11, owner's call).** The owner has about 30 acrylics, so
  a lesson can mix from `palettes/owner.yaml` instead of the five-tube teaching palette. The tube colors are
  approximate until calibrated from swatches. The five-tube palette stays the default for mixing practice.
- **The lessons site is open, not locked (2026-11-11, owner's call).** gesso-lessons.pages.dev holds only
  painting lessons, so there's no sign-in, just a noindex header. Keep anything personal off it.

- **Keep every lesson run, never overwrite (2026-11-12, owner's call).** So much of a lesson's quality is a
  judgment call that a change can make lessons worse without anyone noticing when. Every publish that changes a
  lesson is kept with the version and commit that made it (`site/history/`), the owner's scores sit next to each
  run, and the history page lists what changed between runs, so a regression can be traced to a version and rolled
  back.

- **The lessons site shows only hands-off lessons (2026-11-12, owner's call).** Once Gesso is an app, nobody can
  tweak a lesson after it's made, so the tool has to stand on its own. A lesson goes on the site only if the skill
  made it and sealed it (`publish --final`) and nothing changed after. The skill's own fixes (step review redos,
  split-texture) count as the tool; recuts, hand composites, relocks, and text edits after the seal don't. Those
  runs stay in the lesson history, marked with a ribbon. A lesson that needs a fix gets a fixed tool and a new run.
  After a tool fix, the site's lessons are rerun from their photos, never rebuilt from an old run's saved finish or
  plan (2026-11-13, owner: "I don't trust intermediate fixes because I'm only interested in things that actually
  fix the tool"). Don't plan or file a no-render rebuild of an old run.
  **Every hands-off run goes on the site (2026-11-13, owner's call).** A sealed hands-off lesson is added to the
  site as soon as it's made, as a version on its picture's tile (a new picture gets a new tile); nobody has to pick
  it. A run that needed changing is kept only in the history. Owner: "I would like the default to be anytime a
  complete lesson is generated, we capture it on the main site, unless we need to modify it, then we don't capture
  it there, only in the history record. The only things that show up on the main page should be unmodified runs
  from the tool end to end. If it would make things easier and less confusing, we could capture everything, even
  modified runs, but give them a sticker that says modified." Claude took the first way: the site tools already
  refuse a modified run, and the history already marks one with a ribbon.
  **A tile opens its newest untouched run (2026-11-13, owner's call).** Owner: "Should use newest untouched run."
  `site-refresh` makes each tile's newest hands-off run its default; the older ones stay as versions.

- **The repo is public (2026-11-12, owner's call).** It was private only by default ("meant as a portfolio piece
  later"); an audit found no secrets, personal details, or real photos in its history. Public, the issue links on
  lesson pages work for everyone. Keep it that way: no keys (`.env` stays ignored), no personal photos or names,
  commits with the GitHub noreply address. There's no license file, so the code is look-but-don't-reuse.

- **Pipeline v2: render the finish once, cut every step from it (2026-11-12, owner's call).** The owner found the
  lessons short on detail for new painters, too dependent on inference and image generation, and too dear ($0.40
  to $0.51 and over 20 minutes a run). Each step picture is now cut from the one finished painting, inside real
  outlines of its parts, by free local tools (`docs/design/pipeline-v2.md`; proven on three lessons in
  `docs/spikes/outlines.md`). This replaces three earlier decisions where they conflict:
  - "The image model renders the plan" (2026-10-19): it renders the finish, and when needed the beginner version,
    the canvas extend, and one background picture. No step is rendered.
    **Loosened 2026-11-13 (owner's call):** a step may be re-rendered (an image-model edit of that one step) when
    the free tools give a bad result and nothing better works. Owner: "If we need to do a re-render for a step
    because the free technique is producing bad results, I'm not opposed to it, but if there's a better way
    that's fine too." A preference, not a hard rule (owner: "Don't want you to think it's a hard and fast rule"):
    lean toward free tools, and re-render when it's the better way to a good step. Record each re-render in the
    ledger with its cost (#100).
  - "Filters first" (2026-11-10): there's no per-step ladder of filter, composite, throwaway script, render, and
    no throwaway filter scripts or filter requests (#11 closed).
  - "Claude writes the final instructions from the rendered images" (2026-10-19): the lines that are data (paints,
    brush, stroke, where, drying) are drafted by a tool from the plan and hand-checked cards; Claude adds what only
    this photo needs and corrects the draft against the pictures.
  v1 stays in the repo, and nothing is removed, until three hands-off v2 lessons pass the gate in the design and
  the owner agrees.
  **Done 2026-11-13 (owner's call, #82):** the gate passed, and v1 was removed rather than kept as a fallback ("I
  don't see us ever going back to V1"). The site's versions from before POC 1.0.0 went too; every run stays in the
  lesson history.
- **Don't raise the image model's quality (2026-11-12, owner's call).** Higher settings made no clear difference to
  how well a lesson teaches, and the cost wasn't sustainable. Fix a problem with tools or the plan, not a dearer
  render.
- **More, smaller steps (2026-11-12, owner's call).** One move per step, grouped into stages: 12 to 24 steps in 4 to
  9 stages for the beginner paint-along, up from 5 to 12 steps. Not more than that: mixes dry on the palette between
  distant steps and the last stages matter most. A step has no word limit; detail that doesn't fit a short line
  goes one tap away (a stroke card, a close-up, a paint map), not in the bin.
- **Whatever helps a beginner most, including an optional chalk outline (2026-11-12, owner's call).** The
  paint-along stays sketch-free, except that the stage that starts an object may open with "lightly chalk its
  outline first", from a transfer picture the tool makes. Placement is shown (an outline on the picture, a grid of
  quarters, inches from the canvas edges), never given as percentages.
- **Inches are ruler fractions, never decimals (2026-11-18, owner's call).** An inch ruler is marked in quarters,
  eighths and sixteenths, so a length anyone reads (the page, the writers' fact sheet, the checker's messages,
  Claude's replies) is the nearest of those marks, in lowest terms ("2 13/16 in", "4 1/4 in"), not "2.82 in". The
  steps' Where lines still say the quarter or the half inch, as "about" (`facts.ruler`, `facts.mark`).
- **At most 10 mixes in a beginner lesson (2026-11-12, owner's call).** Paints are measured from the finish and
  the closest are merged to the limit, even if the finish loses a little color nuance. An accent (a sun, an eye
  light) is never merged away. A lighter or darker version of a part's main paint ("plus white") isn't counted as
  a mix of its own (owner confirmed, 2026-11-12). The owner confirmed on 2026-11-12 that 10 is a target: two paints
  far enough apart for a painter to see the difference (Delta E 12) are never merged, so the three test lessons
  land at 10 (chickadee), 13 (red sailboat), and 14 (lavender balloon).
- **How to do a stroke is written once and checked, not written fresh each lesson (2026-11-12).** One card per
  stroke (and a few basics cards), built from the research file with sources, read by the owner before it counts
  as checked. Same rule as technique: from cited research, never from the model's memory.
  **Changed 2026-11-13 (owner's call):** a lesson may show a card written for what's being painted (the same
  technique in the subject's words, and pictures from this painting), marked as not checked, when it helps.
  Owner: "I would be good with untested text and images showing up if they're helpful." The checked cards stay
  the source of the technique: a per-lesson card changes the words and pictures, not the technique (#96).
- **Pipeline v2 is POC 1.0.0 (2026-11-12, owner's call).** The major number goes up when v2 replaces v1: with the
  first sealed v2 lesson after the gate passes, not before. Until then the v2 tools sit beside v1 and the version
  stays on 0.26.x.
- **The gate passed; v2 is the pipeline (2026-11-13, owner's call).** "The pics look good. Publish them as
  1.0.0." The three gate runs are the site's default lessons and carry the 1.0.0 name, with the commit that made
  them. Two targets were missed and accepted: time (16 to 20 minutes against 15) and a fresh-context text review.
- **No painting-order tool; a busy measure helps Claude judge (2026-11-13, owner's call, after the spike for #52).**
  Claude keeps choosing the painting order when it lists the parts. A depth model only confirmed it in 18 plans
  and got a close subject wrong on its own (`docs/spikes/tools-before-plan.md`); owner: "Drop the painting order
  tool". Don't re-propose one unless a lesson ships with parts in the wrong order. The fine-texture measure from
  the same spike gets built as an aid Claude reads, not a gate (#109).
- **The beginner version stays a render (2026-11-13, owner's call, after the spike for #52).** Six painterly filters
  were tried in its place. One strong enough to drop a village also drops the sun and the balloon's basket, and
  blurred stalks don't become dabs (`docs/spikes/tools-before-plan.md`). The render costs about 2.4 cents, only on a
  busy picture. Owner: "Keep the paid beginner render". Don't re-propose a filter for it.
- **Pipeline v3 is explored by spikes, and four rules are open to challenge inside them (2026-11-16, owner's call).**
  v2 has stopped improving: known problems per lesson have stayed at about 2 to 7 from 1.0.0 to 1.12.1, and each fix
  is followed by the same fault in a new form. The plan is `docs/design/pipeline-v3-plan.md`. The owner's weakest
  parts of a v2 lesson are the step pictures and the teaching and text. A v3 spike may test, without asking again:
  more or dearer renders (cost stays low); image and vision models beyond gpt-image and SAM-HQ; steps that cross
  parts or cover the whole canvas, and parts that overlap as layers; and an image model painting a stage the plan
  already describes. The plan still comes from technique, never from the image model. Every other decision here
  stands, and nothing a spike tries becomes the pipeline until its write-up says adopt and the v3 gate passes.
- **Speed counts where it's free (2026-11-16, owner's call; adds to "Slow is fine").** Quality still beats speed in
  any trade, and there's no time target. v3 should be clearly faster where that costs no quality.
- **Experiments run on a frozen bench and are scored blind by the owner (2026-11-16, owner's call).** A fixed set of
  pictures with their finish renders frozen, so an experiment changes one thing. The owner scores two lessons side
  by side without knowing which is which, about 15 minutes an experiment. This is for experiments only: site
  lessons still rerun from the photo after a tool fix.
- **No noise floor; spikes count only clear wins (2026-11-17, owner's call).** Measuring how much two v2 runs on the
  bench differ would take eight more lesson runs, too much of the owner's weekly usage. A spike beats v2 only when the
  owner prefers it on at least 6 of 8 pictures (or most of a smaller round) and it loses clearly on none; a borderline
  picture gets one targeted v2 rerun. Spikes start on the 3 or 4 bench pictures most likely to show their effect,
  screen with one fault counter per lesson, and the owner hears a batch's rough size before it starts
  (`docs/spikes/v3-yardstick.md`, Limits).
- **Claude grades the experiments; the owner grades one finished result at the end (2026-11-17, owner's call;
  replaces "scored blind by the owner" above for v3 spikes).** Scoring a round step by step took too long and wore
  the owner out. Owner: "This is taking way too long to grade. Can't you do the grading and then take all of the
  research and create a pic for me to grade at the end? ... I think you would be better at grading. When I got
  overwhelmed I get irritated and picky." So each spike's A/B round is scored by graders in a fresh context who
  don't know which side is which, with the owner's rubric (`spike/experiments/bench/ab_grader.md`): two graders a
  picture, sides swapped for the second. A spike beats v2 when the graders prefer it on most pictures and it loses
  clearly on none; a split between the two graders of one picture is a tie. Their scores are saved the way the
  owner's were (`spike/experiments/bench/scores/<round>.json`, marked as graded by Claude). The owner still decides
  the v3 gate, on one finished lesson put in front of them when the research is done, not on every spike. Known
  risk, kept in view: a Claude grader is not the owner (on S4 Claude liked the stages and the owner preferred v2;
  the fault counter agreed with the owner at rho 0.43), so the brief lists what the owner has marked down before,
  and a spike the graders pass can still fail at the end.
- **v3's combined lesson gets a go (2026-11-17, owner's call, #210).** The owner looked at the first lesson made the
  v3 way (the highland cow: plan first, the finish erased backward a stage at a time, words from facts;
  `docs/spikes/v3-combined.md`) and said: "Go, fix those two things first." The two things: a unit's last step
  brought more than its words, and two steps that shared a paint couldn't be told apart. Both were fixed by giving
  such a step its own render (16 renders a lesson on the cow, about 29 cents, where the first lesson used 10 and
  18 cents). Next is the same on two more bench pictures with blind graders against v2, then building it into
  `/paint-lesson` (#214). The gate is unchanged: the owner still grades one finished lesson at the end.
  **About 29 cents of renders a lesson is fine (2026-11-17, owner's call):** "29 cents is fine." This answers the
  design's open question on whether a chain's cost is low enough.
  **The flat block-in is adopted on one win and two ties (2026-11-18, owner's call, #217):** "Adopt stands." The
  spike's graders preferred the new lesson on the sleeping cat only and tied on the cow and the birch grove, which
  is short of the grading rule (most pictures). The owner adopted it anyway: a block-in is asked for as one flat
  coat, every "back" request lists what isn't painted yet, and a thing's render is kept over the whole thing
  (`docs/spikes/v3-block-in.md`). It goes into the v3 build (#219). The step after a block-in is now the big jump,
  and that is not solved.
- **Pipeline v3 lessons go on the site, as POC 2.0.0 (2026-11-18, owner's call, after #219).** The first whole v3
  lesson (the floating island) was kept off the site by Claude's reading of "nothing a spike tries becomes the
  pipeline until the v3 gate passes". Owner: "Just publish it as 2.0.0 please. That way I don't have to republish it
  again." So a sealed hands-off v3 lesson goes on the site like any other, and v3 is POC 2.0.0. The floating island
  was sealed by the 1.12.1 code that first held v3 (commit 9d0a377) and carries the 2.0.0 name with that commit, as
  the three v2 gate runs carried 1.0.0. Not decided by this: v2 is still what `/paint-lesson` runs without `--v3`,
  and the gate (the bench, the owner's grade) still decides when v3 replaces it.
- **The v3 gate passed; v3 replaces v2 (2026-11-18, owner's call).** Five v3 lessons were made hands-off from this
  session and put on the site: the highland cow, the sleeping cat and the birch grove (the bench), then the chickadee
  and the lavender fields (#230 to #234). The owner looked at them and said: "Worlds better than v2." Asked whether
  that passes the gate with the known-problems target missed, the owner said yes. Missed and accepted: known problems
  per lesson stayed at 4 to 7, not under 2 (most are paints fitted far from their names, which the pictures don't
  show). What follows from the gate (`docs/design/pipeline-v3.md`, section 13): `/paint-lesson` runs v3 by default,
  the site's lessons are rerun from their photos, and v2 is removed. Those are separate changes, not done by this
  decision.
- **v4 is a lesson you can paint from; cost is a track inside it (2026-11-18, owner's call; replaces #240's "v4 is
  the loop at a measured cost").** The owner on v3's lessons: "I feel like the images have come a long way, but the
  text has kind of lagged. The text isn't very exciting to read, and I don't feel like it's very helpful. I haven't
  got a chance to paint with these tutorials yet, but the text doesn't look like it's going to help us recreate the
  images." Asked whether v4 should be "a lesson you can actually paint from" (a teacher writes each step and the
  fact sheet checks it, the lesson has an arc, a step shows where the strokes go, and a student test with only the
  before picture and the words is the yardstick), with cost as a track inside it, the owner said yes. Asked to
  paint one lesson with their partner, the owner said yes too (#252). The plan is
  `docs/design/pipeline-v4-plan.md`. It is spikes first, then a design written from what they adopt, as v3 was:
  the owner's order is spikes, their results, a design document by Fable, the build by Opus. v3's step pictures
  stay. Not decided by this: v4's gate (the plan proposes one), and the easel coach (#257), which is parked.
- **v4 aims at under $1 of Claude a lesson, and it isn't a gate yet (2026-11-18, owner's call, after #241).** The
  baseline is $4.94 a lesson at the API's rates, about $3.50 through the API itself (`docs/spikes/v4-loop-baseline.md`).
  Asked for a cost target, the owner said: "Reluctant to set a target because I don't want to sacrifice quality so
  early in a POC. But I think if we could get text inference costs under $1 per lesson plan, that would be ideal.
  But again, not a hard-fast limit because I want to see how far we can take this thing. I want to see how capable
  we can make it before we find ways to save costs and make it marketable." So $1 of Claude a lesson (text, not
  renders) is what a cost cut aims for, never a reason to make a lesson worse. Quality first still stands: a cut
  counts only when the graders find the lesson no worse. #240's gate stays open until the owner sets one.
- **A teacher writes v4's steps: one writer for the whole lesson, in fixed lines (2026-11-18, owner's call, after
  #254).** The writer sees each step's before and after pictures, a picture of only what it changed, the fact sheet,
  the stroke card and the whole plan, and fills the same lines for every step: First, Start, Strokes, Where the paint
  sits, Leave, Stop when. check-text still holds every number and side to the sheet (`docs/spikes/v4-teacher.md`).
  The owner accepted the verdict knowing the student test's gain clears its 0.25 bar on the cow only, and that
  neither test showed the page's outline and paint map. A writer a stage and free prose were dropped. W2 builds on
  this writer.
- **A v4 lesson has an arc, added by its own call after the writer (2026-11-19, owner's call, after #255).** One
  Claude call reads the teacher's finished words, the plan, the cards, the photo, the finish and each stage's last
  picture, and adds: an opening (a welcome, the light, two or three skills, each a stroke card the lesson uses with
  its steps, and the road to the finish), a stage opener (what the stage is for, and where it ends, said after the
  stage's last step rather than above every step), and an "As in step N" line on each step that repeats an earlier
  step's stroke or paint. No step's own lines change, and the checks hold the arc to the cards and the sheet
  (`docs/spikes/v4-arc.md`, `arc-add-long`). The owner asked for the longer opening and the callbacks after reading
  the cat's lesson ("Overall big improvement"), and adopted it knowing the student test scores it level with the
  teacher's words (+0.05 ± 0.09), short of the plan's rule that a words spike raise the score. It costs $0.43 of
  Claude a lesson. The arc written into the writer's own call (`arc-whole`) was dropped.
- **Stroke maps are parked; arrows from the change alone are dropped (2026-11-19, owner accepted the verdict of
  #256).** No map raised the student test's score (`docs/spikes/v4-stroke-maps.md`). Arrows traced from what a step
  changed lost 6 of 6 blind reads: the change gives a stroke's line but not which end it starts, so they drew strokes
  backwards. Don't re-propose them as a map's source. The writer's arrows checked against the change (`both`) are
  parked: level on the student test, 2 of 6 graders for and 4 ties, $1.33 of Claude a lesson as a call a step. Bring
  them back only with the write-up's three changes (arrows from the lesson's writer, none for a dabbed stroke, the
  direction from the card) and after the owner's painting (#252) shows a painter guessed where strokes go.
- **The three cost cuts that don't touch the words are adopted (2026-11-19, owner's call, after #253).** Calls are
  cached as the API would cache them (the five-minute cache where a conversation goes on, none for a one-message
  helper). The plan's writer answers `plan-check` and `check` with changes to the plan, not the whole file. It is sent
  the library's list and asks for the files it picks. With all three a lesson is $3.65 of Claude at the API's rates,
  against $4.16 for the baseline priced the same way, and the plan's writer goes from $1.68 to $1.03
  (`docs/spikes/v4-cost-cuts.md`). The blind graders preferred the baseline on the cat in all 4 reads. The owner kept
  the cuts anyway, on the write-up's reading: the cat's faults were a merge `check` asked for and the chain's
  pictures, and two baseline runs made the same way also split 2 of 2 on two pictures. Owner: "Go with your
  recommendations." They live in `spike/experiments/v4_loop.py` (`--cuts`) until v4 is built.
- **The lesson writer and the finisher are sent less, and stay on Opus (2026-11-20, owner accepted the verdict of
  #267).** The writer gets its pictures at 512 pixels and a fact sheet without what its lines don't use, answers
  check-text with only the steps it changes, and is asked for the arc as its conversation's next message. The finisher
  gets the step pictures at 384 pixels and looks at its diagrams again only when one fails to draw. The words then
  cost $0.85 a lesson against $1.33 and score level on the student test; the finisher $0.50 against $0.80, and the
  blind graders found neither worse. A lesson is about $3.06 of Claude at the API's rates
  (`docs/spikes/v4-writer-cost.md`). Claude Sonnet 5.5 made both worse (the words −0.30 on the student test, 5 of 6
  blind reads for Opus on each), so don't re-propose it for writing or finishing. The finisher split in two or at low
  effort is dropped; the words at low effort are parked (no student test, 2 of 6 reads against). Owner: "Yes. Accept
  the verdict." They live in `spike/experiments/v4_writer_cost.py` until v4 is built.
- **The chain's checker stays on Opus 5.5 at medium effort (2026-11-20, owner's call, after #268).** Opus low,
  Sonnet 5.5 at medium and low, and Haiku 5.5 at medium and high each missed 4 to 7 of the 29 marks most Opus reads
  made on the bench's 23 checker rounds, where the loop's own Opus read missed 2 (`docs/spikes/v4-checker-cost.md`). A
  miss leaves a thing in a step picture where it doesn't belong. Sonnet medium came closest, for $0.14 a lesson
  against $0.29. Owner: "Default." Don't re-propose a cheaper checker without a larger bench and the owner's answers
  on the faint looks (the birch grove's pale trunks). Other providers' models stay with #221.
- **What v4's spikes adopted ships as changes to v3, not as a new pipeline version (2026-11-20, the owner left the
  call to Claude).** Owner: "if v4 isn't a significant overhaul, it might be better to turn this into a design doc to
  enhance v3 so that we're not having to transition from another major version. But if you think it's significant
  enough, we can make it v4." Claude's call: it isn't. Of the 13 rows of v3's run it replaces two (the words) and
  changes how four are asked or checked; no step picture changes and `plan.json` stays version 3. So the design is
  `docs/design/pipeline-v3.1.md`, the words stage is swapped in place with no flag and no second pipeline beside
  it, and lessons are stamped POC 2.1.0 with `"pipeline": 3`. "v4" stays the name of the plan, its spikes and #240;
  nothing is renamed. A new pipeline version is for a change to how the step pictures are made or to what a lesson
  is. Not decided by this: the gate, which the design proposes (the owner reads a lesson, where the v4 plan said
  paints one).
- **v3.1's gate: the owner reads one finished lesson; painting one isn't in it (2026-11-20, owner's call).** Asked
  whether the gate should keep the v4 plan's "the owner paints one v4 lesson" or the design's "the owner reads one",
  so that the build's branch doesn't wait on an afternoon of painting, the owner said "Default" (the design's). The
  gate (`docs/design/pipeline-v3.1.md`, section 13): three hands-off bench lessons from the build's branch, sealed;
  the student test no lower than v3's words on any and higher across the three; Claude's graders prefer them on
  most pictures with a clear loss on none; the owner reads one and says yes; the Claude cost reported beside the $1
  aim, not a pass or fail. Painting one stays #252, and what it shows is fixed afterward.
- **The v3.1 gate passed; v3.1 is the pipeline, POC 2.1.0 (2026-11-20, owner's call, #279).** Three hands-off
  lessons from the branch (the highland cow, the sleeping cat, the birch grove) were sealed; the student test scored
  them 3.55, 3.40 and 3.15 against v3's 3.15, 3.21 and 3.02, and Claude's blind graders preferred them 6 of 6
  (`docs/spikes/v31-gate.md`). The owner read the highland cow: "Looks good merge in the site." So `v3.1` merges
  into main as POC 2.1.0 and the three lessons go on the site. Not decided by this: rerunning the site's other
  lessons from their photos, which #279 says to ask about before the renders are spent.
- **Go on v3.1's build (2026-11-20, owner's call, after the combined lesson).** The owner read the combined lessons
  (the sleeping cat, then the chickadee and the lavender balloon, which he asked for because his partner means to
  paint one of those this weekend): "Looks good." So v3.1 is built into `/paint-lesson` as the design's section 12
  says, by Opus (the owner's order: the design by Fable, the build by Opus). The lesson's words in a trial run are
  written by Opus too: the owner said so when the combined lesson started. A whole lesson page with the new words
  was made for painting from (`docs/spikes/v31-combined.md`); it isn't on the site.
- **A covered layer stops at a loose line, a bit past where the next stage covers it (2026-11-21, owner's call, after
  #289; for #287).** A layer that a big area from the next stage will cover is painted down to a loose line a bit past
  the lowest point it is needed nearby, and the canvas below stays bare until that stage paints it (`line-1-next`,
  `docs/spikes/cover-margin.md`). Flat layers stop too. Thin things and subjects sitting inside a layer are painted
  through: a flat placeholder shape under a subject was marked down by every blind read. The tests tie (the blind
  reads none on both pictures, the student test −0.21 ± 0.21, level within its noise), and neither can credit the
  painting it saves: about 1.4 canvases on the highland cow. The owner raised #287 for that saving, so it is adopted
  on his judgement, not on a measured win. Owner, on the pictures: "Yea that's right. I like it"; on the gap fixed:
  "This is the way." It changes how step pictures are made, so it is a new pipeline version: a design by Fable
  first (the facts, the Where picture, and the words of the step after a changed run have to follow), then the
  build. It lives in `spike/experiments/cover_margin.py` until then.
- **Pipeline v4's design is merged; its gate asks for no loss, and its lessons are POC 2.2.0 (2026-11-21, owner's
  call, #292 and #293).** The owner merged `docs/design/pipeline-v4.md` and said "Default" to its gate (section 12):
  three hands-off bench lessons, each built twice from one chain, with the rule and without; both seal; the student
  test on the changed steps and the step after isn't lower by 0.25 or more; Claude's graders show a clear loss on no
  picture; the painting saved is reported, not passed or failed; the owner reads the cow and says yes. The stamp is
  POC 2.2.0 with `"pipeline": 4` (the design had proposed 3.0.0). Not decided by this: the dashed stop line on the
  Where picture and the page's line about painting skipped, both guesses in the design. Next is the build, by Opus.
- **A covered layer stops for a cover any number of stages on (2026-11-21, owner's call, during #299; widens the rule
  above).** The first 2.2.0 cow's chain painted sky, not far hills, behind the hillside, so under `line-1-next` its
  sky ran to the bottom edge (only the far hills stopped, 0.02 of a canvas). Owner: "I'm trying to avoid wasted time
  so if it gets mostly covered eventually by any step we should only paint it part way." Asked whether to keep the
  birch grove's fix (no white patch left floating over paint already laid), he said yes. So a layer stops wherever a
  later stage covers it from the bottom edge, except above paint a stage between them has already laid
  (`line-1-any`, `spike/stops.py`); on that cow it skips about 1 canvas. The spike's cow and birch grove come out as
  before within 1/16 in, apart from the mist's line rising a little at its left.
- **Go on pipeline v4 after the owner read the cow (2026-11-21, owner's call, #299 step 1).** The first 2.2.0 cow
  (`output/highland-cow_skill_20261121-102810`, the widened rule: its sky, clouds and far hills stop, about 1 canvas
  skipped) was sealed and read. Owner: "Go." On the two guesses the design left open: the dashed stop line ("Didn't
  see a dashed line so should be fine") and the page's line about painting skipped ("Didn't notice it so keep or not
  doesn't matter"), both stay as built. Next is the gate (`docs/design/pipeline-v4.md`, section 12).
- **Building the painting forward is parked (2026-11-17, owner's call, after stage 1 of the spike for #207).** The image
  model painted the highland cow onto a bare canvas a thing at a time, with no finish to cut from
  (`docs/spikes/v4-forward.md`). Owner: "A lot of the steps look the same in that one. Might be worth tweaking in the
  future but I think the v3 solution is better." v3 keeps whole-picture stages (#204). Don't re-propose a forward
  build unless it comes with an answer to steps that look the same and to a finish that wanders from the photo.
- **The lessons site stays on Cloudflare Pages (2026-11-12, owner asked).** It's static pages, so the owner's
  partner browses and opens lessons on her phone exactly as before. The outline model runs only where a lesson
  is made.

## How we work

- **Same approach as RepBunny (2026-10-19):** automate as much as possible, built up bit by bit.
  Skills first (`refine-backlog`, then `next-item`), routines and review agents later.
- **The proof of concept runs as a Claude Code skill (2026-11-10, owner's call).** The
  `paint-lesson` skill (#10) has Claude Code do the planning and reviews under the owner's
  subscription instead of paying for API calls, with filters and renders as command-line tools.
  The pipeline moves into the app once the lessons look right.
- **Backlog in GitHub Issues** with RepBunny's scoring labels (see `docs/backlog.md`).
- **An issue closes when its pull request merges, into any branch (2026-11-21, owner's call).** GitHub closes an
  issue on its own only for a merge into `main`, so a build merged into a working branch (such as `v4`) left its issue
  open. Claude closes it by hand when the merge is done. A parent issue stays open until its own work is done. Owner:
  "Why do we need to keep prs and issues open?"
- **The pipeline v4 builds are POC 2.2.0 updates (2026-11-21, owner's call).** Issues, pull requests and messages to
  the owner name them by the version a lesson is stamped with ("2.2.0 build 4"), not "v4": "v4" is also the v4 plan
  (#240) and the yardstick. The design file (`pipeline-v4.md`), the branch `v4` and the stamp `"pipeline": 4`
  keep their names (owner: "Leave them as v4").
- **Every piece of work gets a pull request (2026-11-13, owner's call).** When work on an issue is done and pushed,
  Claude opens a pull request without asking (owner: "Always want a pull request. No need to ask").
- **Claude merges its own pull requests during the proof of concept (2026-11-13, owner's call).** The owner works mostly
  from a phone and was merging without a full review, so the wait only slowed things down. Once the tests pass and the
  adversarial review (below) has signed off, Claude merges and tells the owner what went in (a merge to `main` deploys
  the lessons site). Still wait for the owner on anything labeled `human` and on any change to a decision in this file
  other than the owner's own words. This ends with the proof of concept: production code gets a different process
  (owner: "When we get into production code it'll be different, but for now I'd like to keep things moving along").
- **Every pull request gets an adversarial review before it merges (2026-11-13, owner's call; adds to "Claude merges
  its own pull requests").** Once a pull request is open, Claude has an Opus model review it adversarially and post
  its findings as comments on the pull request, each rated high, medium, or low. Medium and high findings block the
  merge: Claude fixes each one (or answers it on the pull request when it disagrees), and the reviewer looks again
  until it signs off on every one. If nothing is medium or higher, there's no second review. Either way, Claude fixes
  the low findings it agrees with and merges once the tests pass and nothing blocks (owner: "If there are medium or
  high findings those are blockers").
  **Only high findings block (2026-11-18, owner's call, during #219).** Three build pull requests each went through
  two to four review rounds on medium findings. Owner: "This is taking a long time and consuming a lot of usage. If
  the reviewer is being picky let's just not block on anything but high." So a high finding blocks the merge and
  gets a second look; medium and low findings are fixed when Claude agrees with them, without another look.
  **Only when code changed (2026-11-16, owner's call; narrowed 2026-11-17).** Code means program files only: the
  Python and JavaScript under `spike/` (tests included). Docs, the skills' instructions, techniques, elements, stroke
  cards, palettes, bench results under `spike/experiments/bench/` (frozen pictures, traces, fault counts, scores,
  keys), lesson runs, `site/` and the lesson history are not code. A pull request that changes no code merges without
  the adversarial review and without the test suite. The one exception: a change to a file the tools load
  (techniques, elements, cards, palettes) runs only the test for that loader (`test_elements`, `test_yaml_files`, a
  second or two), since a malformed file there could stop lessons loading. Owner: "No need to a review unless code was
  changed"; "they're not code please update the rules to say code only"; "I really need tests ran only when there is a
  chance of regression. They take time and tokens and both are limited resources right now."
  **New renders of lessons need no review (2026-11-17, owner's call, said again).** A pull request that holds new
  lesson runs or renders, and no change to program files, merges without the adversarial review. Owner: "My
  consumption is on trajectory to hit my weekly limit and I can't pay for inference on pointless things."
  **Spike code gets a verdict check, not the adversarial review (2026-11-17, owner's call).** Code under
  `spike/experiments/` and its tests (`spike/tests/test_v3_*.py`) is experiment code, so a pull request that changes only that (and docs) skips the adversarial
  review and its second looks. In its place, a spike whose write-up gives a verdict (adopt, drop or park) gets one
  pass by an Opus model, limited to three questions: do the numbers in the write-up match the results file, was the
  A/B blind, and does the verdict follow from them. It runs once; Claude fixes what it finds and merges. A spike
  pull request with no verdict (a first stage, a probe) gets neither. The past spike reviews' findings that mattered
  were of this kind (an edge called a win that was slight, grading folders that weren't blind); the rest was polish
  an experiment doesn't need. Spike code that later moves into the lesson tools gets the full review then. Owner:
  "These are experiments not production code."
- **Lessons are generated on Opus, not Fable (2026-11-17, owner's call).** A `/paint-lesson` run, hands-off or not,
  runs on an Opus model, whatever model the session that starts it is on (`CLAUDE_MODEL` in `spike/run.py` is what a
  lesson is stamped with). A `model:fable` label is for the issue's own work (a spike's code and write-up), not for
  making lessons inside it.
