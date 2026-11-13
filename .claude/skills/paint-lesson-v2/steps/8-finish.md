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

## 8b2. File each drafted element technique
For each file in `<lesson>/elements/` (step 2b), before the seal:
1. Search first: `gh api -X GET search/issues -f q="repo:DeanPhillipsOKC/gesso is:issue element technique <what it's for>"`.
   If an open issue already asks for this technique, comment on it with your draft and this lesson's folder name.
2. Otherwise file one: title "Element technique: <name>", labels `feature` and `status:needs-review`, and in the
   body what it's for, why no library element fit, the draft's YAML, which parts of it came from the research and
   which didn't, and the lesson folder. Use `gh api repos/DeanPhillipsOKC/gesso/issues -f title=... -f body=...
   -f "labels[]=feature" -f "labels[]=status:needs-review"`.
3. Put the issue's url in the draft as `filed: <url>`. `check` refuses to seal while a draft used by the plan has
   no `filed`.
If you can't reach GitHub, say so in the report, leave `filed` empty, and stop before the seal: the owner decides.

## 8c. Seal
`publish --lesson <lesson> --final`. It runs `check` and refuses with a list until it's clean. Fix what it lists
and run it again. After the seal, change nothing.

Unless whoever started you said they'll handle it, publish `lesson-artifact.html` with the Artifact tool when it's
available (copy it to the scratchpad as `<photo stem>-lesson.html`, `icon: "paint"`, a one-sentence `description`,
private). It's a page this run just generated from your own text and pictures; if the tool won't take it, skip
this and say so in the report. Don't run `site-add` or `site-refresh`; the owner decides what goes on the site.

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
