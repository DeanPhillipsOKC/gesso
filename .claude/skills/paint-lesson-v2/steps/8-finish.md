# Step 8: diagrams, notes, seal, report

## 8a. Construction diagrams
Follow `../paint-lesson/steps/7-diagrams.md` as written: go through every step as someone who has never painted
and give a `construct` diagram to each step that blocks in a shaped object. It goes on the step's entry in
`text.json`. The Where picture and the paint map already show where and which paint, so a diagram is for **how to
build the shape**, nothing else. `publish`, then `preview-diagrams` to look at them.

## 8b. Notes
Follow `../paint-lesson/steps/8-notes.md` for `notes.json` (its schema wins over anything step 0 said about field
names), with these differences:
- no `filters` entries for step pictures and no `throwaways` (there are none);
- add `"merged_parts": {"<part id>": "why"}` for any part dropped in step 2c (an empty object if none);
- `steps` still has one entry per step id: why this step, and why now;
- `learned`: anything the cards, the research, or this skill didn't cover, and any drafted line you had to rewrite
  (which card, which subject), so the card can be improved.

## 8b2. Drafted element techniques
Each file in `<lesson>/elements/` was filed in step 2b. If you changed a draft since, comment the new version on its
issue. `check` has already confirmed every used draft has `filed`.

## 8c. Seal
`publish --lesson <lesson> --final`. It runs `check` and refuses with a list until it's clean. Fix what it lists
and run it again. After the seal, change nothing.

Unless whoever started you said they'll handle it, publish `lesson-artifact.html` with the Artifact tool when it's
available (copy it to the scratchpad as `<photo stem>-lesson.html`, `icon: "paint"`, a one-sentence `description`,
private). It's a page this run just generated from your own text and pictures; if the tool won't take it, skip
this and say so in the report.

**Put it on the lessons site** (owner, 2026-11-13: every sealed hands-off run goes there). Only after the seal, and
only if nothing changed after it. Skip this, and say why in the report, when any of these holds:
- **The photo isn't one the public site may show.** Every lesson page shows the source photo, and the site and repo
  are public. Go on only when the photo is in `photos/site/`, or whoever started you said it's AI-made or the
  owner's to share, and it shows no people, homes, or anything personal (`docs/decisions.md`, "Photos stay private").
- **The checkout isn't clean and current.** First run `git fetch origin main`. Then `git status --porcelain site/`
  must be empty and `git rev-parse HEAD` must equal `origin/main`, or you must be able to get there with
  `git switch -c lesson-<run folder> origin/main` without forcing anything. A stale `site/lessons.json` would drop
  tiles and versions added since. Never force a checkout or a merge to get past this.
- **Other runs share your checkout** and are writing to `site/` too.

Then, on that new branch:
- The picture already has a tile when an entry in `site/lessons.json` has a `source`, or a version `id`, from a run
  of the same photo stem (`<photo stem>_skill_...`); the tile's slug may differ (`lavender-balloon` for
  `balloon-lavender`). If so, run `site-refresh`. It adds this run as a version and leaves the tile's default alone.
  It also adds any other hands-off runs it finds in `output/`. That's the rule too; name them in the pull request.
- If it's a new picture, run `site-add --lesson <lesson> --slug <photo stem>`, which makes its tile. Never run
  `site-add` for a picture that has a tile: it would change the tile's default.
- Both tools refuse a run that isn't hands-off; don't work around that.
- Commit `site/` (the lesson pages and `site/history/`), push, and open a pull request named for the run. The repo's
  pull request rules (`docs/decisions.md`, How we work) take it from there.

## 8d. Report to the owner
Start with anything that needs them:
- problems left as they are (they're on the page under Known problems);
- anything you'd report as a bug, naming the lesson folder;
- cards you drafted, or card lines you had to rewrite;
- the numbers: steps and stages; base mixes (and why, if over 10); renders and image cost
  (`image_cost_usd`); minutes from start to seal, and roughly how long each skill step took;
- how many fix rounds the outlines took, and any part you dropped;
- the technique picks: each part's element and why (from `plan.json`), and every element you drafted, with its issue;
- anything in this skill that confused you or that you had to work around.
