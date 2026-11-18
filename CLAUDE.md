# Gesso

Turns a photo into a step-by-step painting lesson (acrylic or oil) at the painter's skill level.
Proof of concept: lessons are made by the `/paint-lesson` skill (pipeline v3) and its tools in `spike/`; no app
code yet.

Project knowledge lives under `docs/`. Read it before making changes:

- `docs/vision.md`: what we're building and why, how the pipeline works, and the milestones.
- `docs/design/pipeline-v2.md`: history. Pipeline v2 (render the finish once, cut every step from it) was removed
  in #238, as v1 (a render per step) was in #82. Its later tools (step-aids, draft-text, check, publish) still run,
  reading a v3 plan in v2's shape, so its sections on them still describe that code.
- `docs/design/pipeline-v3-plan.md`: the plan for pipeline v3 (a frozen bench, then spikes). Read it before any
  issue labeled for v3.
- `docs/design/pipeline-v3.md`: the pipeline (a painter's plan, the finish erased back a unit at a time, words from a
  measured fact sheet). Its gate passed on 2026-11-18 and `/paint-lesson` runs it. Read all of it before any
  pipeline issue.
- `docs/design/pipeline-v4-plan.md`: the plan for pipeline v4, a lesson you can paint from (a student test as the
  yardstick, then spikes on the words, stroke maps and cost). Read it before any issue under #240.
- `docs/decisions.md`: decisions the owner has already made. Read it before proposing or filing
  anything, and don't re-propose what it rules out.
- `docs/backlog.md`: how the GitHub Issues backlog works (labels, scoring, `human` tasks).
- `docs/lessons-site.md`: the lessons site (site/) and its Cloudflare setup.
- `docs/changelog.md`: what each Gesso version added. Lessons are stamped with the version that made them.
- `docs/testing.md`: which tests to run when (only when code changes: the quick set while working, the full suite before merging).
- **GitHub Issues** (https://github.com/DeanPhillipsOKC/gesso/issues, via the `gh` CLI) is the
  backlog. Check open issues before starting new work. Issues labeled `human` aren't yours to do.

Keep this file a thin pointer to `docs/`. Put new project knowledge there.

## Replies

The owner has ADHD. Put anything he has to do or answer at the very top of the reply, as a numbered list, before any
explanation. Number it even when there is only one item. If nothing is needed, say that first.
