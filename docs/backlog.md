# Backlog

The backlog lives in GitHub Issues: https://github.com/DeanPhillipsOKC/gesso/issues. Use the
`gh` CLI to read and change it. This file holds the conventions, which follow RepBunny's.

## Conventions

- **Check `docs/decisions.md` before filing.** Don't file an issue for an idea it rules out.
- **One issue per item.** GitHub assigns the number.
- **Scores are labels:** `effort:N` and `value:N` on the Fibonacci scale (1, 2, 3, 5, 8, 13).
  Effort is implementation size; value is combined technical and product worth. ROI = value /
  effort, computed when picking, never stored. Whoever files an item scores it.
- **Kind:** `feature`, `bug`, `tooling`, or `spike` (an experiment to answer a question before
  building).
- **Skip markers** (agents never pick these): `status:blocked` and `status:needs-review`. Put the
  reason in a comment.
- **`human`:** only the owner can do it (accounts, money, decisions, devices). Scored like any
  other issue, with effort meaning the owner's time.
- **`model:<name>`** (e.g. `model:fable`): the owner wants that Claude model to work the issue. A session on
  another model doesn't pick it; if asked to, it says which model the label names first.
- **Rough issues are fine.** An issue with no labels stays invisible to agents until
  `/refine-backlog` (`.claude/skills/refine-backlog/`) turns it into a spec (Problem / Scope / Out of scope /
  Acceptance) and scores it.
- **Picking the next item:** highest ROI first, then highest value, then oldest.
- **Dedupe before filing:** `gh api -X GET search/issues -f q="repo:DeanPhillipsOKC/gesso is:issue <keywords>"`
  (`gh issue` uses GraphQL, which cloud sessions can't reach).
