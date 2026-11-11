# Changelog

What each Gesso version added to the lessons it makes. Every lesson is stamped with the version that made it
(page footer, receipt, `lesson.json`), so an older lesson is missing whatever came after its version.

While Gesso is a proof of concept (POC), the minor number goes up for anything that changes what a lesson looks
like or contains, and the patch number for fixes. The numbers before 0.9.0 were given afterward, from the history.

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
