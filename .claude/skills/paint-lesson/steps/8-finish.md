# Step 8: diagrams, notes, seal, report

## 8a. Construction diagrams
Follow `steps/diagrams.md`: go through every step as someone who has never painted
and give a `construct` diagram to each step that blocks in a shaped object. It goes on the step's entry in
`text.json`. The Where picture and the paint map already show where and which paint, so a diagram is for **how to
build the shape**, nothing else. `publish`, then `preview-diagrams` to look at them.

## 8b. Notes
Follow `steps/notes.md` for `notes.json` (its schema wins over anything step 0 said about field names).

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
- **`site/` has changes that aren't this run's.** `publish` always records the run in `site/history/`, so
  `git status --porcelain site/` may list only `site/history/<photo stem>/<run folder>/` and
  `site/history/index.html`. Anything else under `site/` means another run or someone's edit is in progress.
- **Other runs share your checkout** and are writing to `site/` too.

Otherwise, in this order, never forcing anything:
1. `git fetch origin main`.
2. `git checkout -- site/history/index.html` (a generated page, rebuilt in step 4; your run's history folder stays).
3. `git switch -c lesson-<run folder> origin/main`. If git refuses, stop here: skip the site and say why in the
   report.
4. Rebuild the history page so it holds `main`'s runs plus yours:
   `$PY -c "import sys; sys.path.insert(0, 'spike'); import history; history.build_page()"`.
5. The picture already has a tile when an entry in `site/lessons.json` has a `source` that starts with
   `<photo stem>_skill_` (the tile's slug may differ: `lavender-balloon` for `balloon-lavender`). Then run
   `site-refresh`: it adds this run, and makes the picture's newest hands-off run in `output/` (usually this one)
   what the tile opens (owner, 2026-11-13); the old default stays as a version. It also adds any other hands-off runs it finds in `output/`,
   which is the rule too; name them in the pull request. For a new picture, run
   `site-add --lesson <lesson> --slug <photo stem>`, which makes its tile. Both tools refuse a run that isn't
   hands-off; don't work around that.
6. Unless whoever started you said they'll handle it (say, to put several runs in one pull request): commit
   `site/`, push the branch, and open a pull request named for the run. The repo's pull request rules
   (`docs/decisions.md`, How we work) take it from there.
7. `git switch -`, back to the branch you started on, so the next run doesn't start on this one.
If step 4, 5, or 6 fails (a tool error, a refused push), stop there: leave the branch and `site/` as they are, and
put the failure and the branch name in the report for whoever started you.

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
