# Step 9: seal, publish, report

## Seal
Your last command is `publish --lesson <lesson> --final`. It checks the lesson and seals it as hands-off: made by
the tool on its own. It refuses, with a list, when something is missing or a check fails:
- `review.json` with the finish issues, both image review rounds, and the text review (`text_issues`);
- `notes.json` complete (step 8);
- every step's text with `summary`, `brushes`, `strokes`, and `made_with`, and every step with `regions`;
- the checks empty: `texture_jumps`, `paints_not_listed`, `duplicate_recipes`, `undocumented_diagrams`,
  `long_instructions`, and `long_steps` (unless the step is in `long_steps_kept`). An `unreachable_paints` entry
  needs a `paint_notes` line on a step that uses it.

Fix what it lists and run it again. After the seal, change nothing: any later change marks the lesson edited, and
only hands-off lessons go on the lessons site. A lesson that needs a fix gets a fixed tool and a new run.

## What publish makes
`lesson.json`, `lesson.html` (local), `lesson-artifact.html` (images inlined), `lesson-standalone.html` (one
self-contained page for the site), and `embed/` (a walkthrough for a blog post). Every lesson is stamped with the
Gesso version (`spike/VERSION`, the commit, the date). Every publish that changes the pictures or text goes in the
lesson history (`site/history/`); drafts are dropped once the run is sealed.

## Artifact
Unless whoever started you said they'll handle it, publish `lesson-artifact.html` with the Artifact tool when it's
available: copy it to the scratchpad as `<photo stem>-lesson.html`, `icon: "paint"`, a one-sentence `description`
(steps, subject, level), the same URL for a rerun of the same photo. Keep it private.

Don't run `site-add` or `site-refresh`; the owner decides what goes on the site.

## Report to the owner
Start with anything that needs them:
- steps left as they are, with the reason (they're on the page under Known problems);
- anything you'd report as a bug, naming the lesson folder;
- the artifact link, if you made one;
- the Gesso version, image cost (`image_cost_usd`), paid and cached renders, and steps by source;
- any throwaway filters;
- anything in the skill that confused you or that you had to work around.
