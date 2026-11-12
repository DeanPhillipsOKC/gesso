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
  easy to delete.
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

## How we work

- **Same approach as RepBunny (2026-10-19):** automate as much as possible, built up bit by bit.
  Skills first (`refine-backlog`, then `next-item`), routines and review agents later.
- **The proof of concept runs as a Claude Code skill (2026-11-10, owner's call).** The
  `paint-lesson` skill (#10) has Claude Code do the planning and reviews under the owner's
  subscription instead of paying for API calls, with filters and renders as command-line tools.
  The pipeline moves into the app once the lessons look right.
- **Backlog in GitHub Issues** with RepBunny's scoring labels (see `docs/backlog.md`).
