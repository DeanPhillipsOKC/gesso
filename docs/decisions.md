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
