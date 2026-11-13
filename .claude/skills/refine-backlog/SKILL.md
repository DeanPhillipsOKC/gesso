---
name: refine-backlog
description: Refines Gesso's GitHub Issues backlog. Finds open issues that aren't scored yet (no effort/value labels, such as ones the owner filed from their phone), checks each against docs/ and the code, asks the owner only what they must decide, then rewrites the title and body as a spec (Problem / Scope / Out of scope / Acceptance) and adds effort, value, kind, and status labels so the next item can be picked. Use when the owner runs /refine-backlog, optionally with issue numbers (/refine-backlog #12 #14). Interactive; never implements anything.
---

# refine-backlog

Turns rough issues into specs an agent can build without guessing. The backlog is GitHub Issues on
`DeanPhillipsOKC/gesso`; the conventions are in `docs/backlog.md`.

**Use the REST API.** `gh issue` and `gh label` go through GraphQL, which cloud sessions can't reach. Every command
below is `gh api` with `REPO=DeanPhillipsOKC/gesso`.

Before you start, read `docs/backlog.md`, `docs/decisions.md`, and `docs/vision.md` if you haven't this session.
Read `docs/design/pipeline-v2.md` (all of it) before refining any pipeline v2 issue, and `docs/lessons-site.md`
before any issue about `site/`. If an issue asks for something `docs/decisions.md` rules out, flag it to the owner
instead of writing a spec.

This skill is interactive: the owner is here and wants to be asked when something really is theirs to decide.

## 1. Find issues that need refining

```bash
gh api "repos/$REPO/issues?state=open&per_page=100" --paginate \
  --jq '.[] | select(.pull_request | not) | [.number, .created_at[:10], ([.labels[].name] | join(",")), .title] | @tsv'
```

An issue **needs refining** if it is open, isn't a pull request or a tracking issue (a checklist of other issues),
and is missing an `effort:N` or a `value:N` label. That includes `human` issues, but for those only add the missing
labels and any "blocked by" links (step 4's label rules); don't rewrite their bodies unless the owner names them.
If the owner named issues (`/refine-backlog #12 #14`), refine exactly those, even if they're already scored.

If nothing needs refining, say so in one line and stop.

## 2. Research each one (before asking anything)

For each issue, oldest first:

1. Read the body and every comment. Later comments win.
   ```bash
   gh api repos/$REPO/issues/<N> --jq '.title, .body'
   gh api repos/$REPO/issues/<N>/comments --paginate --jq '.[] | "--- \(.user.login) \(.created_at[:10])\n\(.body)"'
   ```
2. **Check it against the code and docs.** Find what it touches: the tools in `spike/` (`tools.py` and the modules it
   calls), the skills in `.claude/skills/`, `techniques/`, `palettes/`, and `site/`. For a bug, work out the root
   cause where you can (which condition, which function, which input) and cite `path:line`. You may run free tools
   and the tests in `spike/tests/` on fixtures to confirm a cause. **Never run anything that costs money** (an image
   render or any other paid API call) while refining; say in the spec what a paid run would check instead. If a
   claim is wrong or already fixed (check `docs/changelog.md`), note that.
3. **Dedupe** against every issue, open or closed:
   ```bash
   gh api -X GET search/issues -f q="repo:$REPO is:issue <keywords>" --jq '.items[] | [.number, .state, .title] | @tsv'
   ```
   Also grep `docs/changelog.md`, `docs/skill-history.md`, and `docs/spikes/`. If it duplicates an open issue, plan to
   fold it in; if it already shipped or a spike already answered it, plan to say so.
4. Decide what only the owner can answer: a product choice, which of two readings they meant, a priority tradeoff,
   or information you can't get from the code or the lesson history (which lesson, what looked wrong, what they
   expected). Don't ask about things you can work out yourself or that have a sensible default; pick the default and
   state it in the spec.

## 3. Ask, once, in a batch

Start the message with the one-line status (what's refined so far), then a numbered **Asks** list covering every
issue in this run, one line each, tagged with the issue (`#14:`), with your recommended answer where you have one.
Below the list, a short note per issue on what you found (root cause, duplicate, already fixed). Then wait.

Issues with no open questions don't wait: refine them now (step 4) and list them in that message as done.

If the owner can't or doesn't want to answer yet, refine the issue anyway with the question under "Open questions"
and label it `status:needs-review`.

If an issue needs a visual decision (a lesson page layout, a card, a diagram), offer a mockup (a throwaway HTML page
screenshotted with Playwright, saved under `docs/design/`) rather than asking the owner to picture it. Build it only
if they say yes.

## 4. Rewrite the issue

Write the new body to a file in your scratchpad, then apply the title and body:

```bash
gh api -X PATCH repos/$REPO/issues/<N> -f title="<title>" -F body=@<file>
```

**Title:** short and specific to the outcome ("Lesson page: the tubes to get out first"), not the symptom's wording
from the report. A spike's title starts with "Spike:" and names the question.

**Body**, in this order (leave a section out only if it truly doesn't apply):

```markdown
## Problem
What the painter or the owner runs into and why it matters, in plain language. Which lesson or run showed it, if known.

## Evidence
What you checked: files and functions with `path:line`, the root cause for a bug, the lesson or run you looked at,
related or duplicate issues (#N), changelog and spike history.

## Scope
The change to make, concrete enough to build without guessing: which files, tools, or skill steps; the rule or
behavior; any text in quotes; defaults you chose and why. Decisions the owner made, marked "decided with the owner
<date>" so no later agent relitigates them.

## Out of scope
What not to touch, especially nearby things a builder might "helpfully" change.

## Acceptance
Checkable outcomes. For tool changes, the tests in `spike/tests/` to add or extend and what they assert. For changes
to what a lesson shows, which photo to run a new lesson from and what to look for (per `docs/decisions.md`, lessons
are rerun from their photos, never rebuilt from an old run). For bugs, the repro that must now pass.

## Design source
Only if there is one: `docs/design/<file>` or a mockup, "build true to it".

## Open questions
Only if something is still undecided (and then the issue gets `status:needs-review`).

<details><summary>Original report</summary>

<the issue's previous title and body, verbatim, so nothing the owner wrote is lost>
</details>
```

**A spike** is an experiment that answers a question before building. Its Scope says what to try (and on which
photos or runs), and its Acceptance is a write-up in `docs/spikes/<name>.md` with the answer, the evidence (pictures
where they help), and a recommendation the owner can decide on. The decision itself goes to the owner.

Write for an agent that has the repo but not this conversation: name exact files and identifiers, spell out rules
instead of implying them, and avoid "etc." and "as discussed". Keep the owner's own words for anything about how a
lesson should look or read.

**Labels.** Add with `gh api -X POST repos/$REPO/issues/<N>/labels -f 'labels[]=effort:3' -f 'labels[]=value:5' ...`
and remove stale ones with `gh api -X DELETE "repos/$REPO/issues/<N>/labels/<name>"`.
- `effort:N` and `value:N` on the Fibonacci scale (1, 2, 3, 5, 8, 13). Score them yourself; never ask the owner.
  Effort is implementation size including tests. Value is combined product and technical worth, weighted toward
  lessons a beginner can actually paint from.
- Exactly one kind: `feature`, `bug`, `tooling`, or `spike`.
- `status:needs-review` if a decision is still open; `status:blocked` plus a comment giving the reason if it's
  waiting on something outside the code (an account, money, a photo from the owner).
- `human` if only the owner can do it (accounts, money, decisions, reading cards, painting), **plus** effort and
  value, with effort meaning the owner's time.
- Keep any `model:<name>` label the issue has. Add one only when the owner asks for it.
- If it can't start until another open issue is done, add a GitHub "blocked by" link instead of `status:blocked`, so
  it unblocks itself when that issue closes:
  `gh api -X POST repos/$REPO/issues/<N>/dependencies/blocked_by -F issue_id=<id>`, where `<id>` is the blocker's
  database id (`gh api repos/$REPO/issues/<blocker> --jq .id`).

Then post one short comment, dated with `date +%Y-%m-%d`:

```bash
gh api -X POST repos/$REPO/issues/<N>/comments -f body="Refined by refine-backlog on <date>: <what changed and why, one or two sentences>"
```

**Duplicates:** don't close anything without the owner's OK. Ask in the batch; on a yes, move any new detail into
the surviving issue as a comment, then comment "Duplicate of #<N>" on the duplicate and close it:
`gh api -X PATCH repos/$REPO/issues/<dup> -f state=closed -f state_reason=not_planned`.

## 5. Report

Start with the one-line status, then a short summary: each issue refined (`#N title` with its effort, value, ROI,
and kind), anything labeled needs-review or blocked and why, duplicates closed, and what's now the next item. Pick it
by `docs/backlog.md`'s rule (highest ROI, then highest value, then oldest), skipping `human`, `status:blocked`,
`status:needs-review`, and issues with no scores:

```bash
gh api "repos/$REPO/issues?state=open&per_page=100" --paginate --jq '.[] | select(.pull_request | not)
  | {n: .number, t: .title, d: .created_at, l: [.labels[].name]}
  | select(.l | any(. == "human" or startswith("status:")) | not)
  | {n, t, d, e: (.l | map(select(startswith("effort:"))[7:] | tonumber) | first),
       v: (.l | map(select(startswith("value:"))[6:] | tonumber) | first)}
  | select(.e and .v) | "\(.v / .e)\t\(.v)\t\(.d)\t#\(.n) \(.t)"' | sort -t$'\t' -k1,1gr -k2,2nr -k3,3 | head -5
```

Mention it when the top item has a `model:<name>` label naming a different model from this session's.

## Hard rules

- Never implement, commit, or push anything. This skill only edits issues (and, if the owner approves a mockup,
  writes it under `docs/design/`; committing that is a normal docs pull request).
- Never run a paid render or other paid API call.
- Never drop anything from a report: the original always goes in the `<details>` block.
- Never invent product decisions. Ask, or record the question and label `status:needs-review`.
- On `human` issues, only add missing scores and "blocked by" links unless the owner names them.
- Never ask the owner to score anything.
