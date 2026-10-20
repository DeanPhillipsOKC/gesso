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

## How we work

- **Same approach as RepBunny (2026-10-19):** automate as much as possible, built up bit by bit.
  Skills first (`refine-backlog`, then `next-item`), routines and review agents later.
- **Backlog in GitHub Issues** with RepBunny's scoring labels (see `docs/backlog.md`).
