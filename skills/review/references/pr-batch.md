---
tier: Standard
---

# PR Review Batch

Use when `review-pr` receives multiple PR numbers or `--all-open`.

## Required Context

- [pr-review.md](pr-review.md) — the per-PR review procedure the worker applies
- [classify-diff.md](classify-diff.md) — the per-PR worker selects its own lens
  set from its own payload, so it needs the classifier in its own contract
  closure rather than inheriting a team choice. Selecting is not orchestrating:
  the worker then *applies* those lenses itself (see *Dispatch* below)

These are declared here rather than left to the dispatch prose below. A link in
running prose is navigation; this section is the contract the route runner inlines.

## What Is Not In The Worker's Closure

The posting contract is deliberately absent from the section above. That section
*is* the worker's closure, and the worker never posts — it has no `gh`, no
network, and no comment to render. Declaring a main-thread-only contract there
inlined it into every batch worker's prompt: wasted context, and a standing
invitation to a worker that reads it as an instruction. The main thread reads
this document with ambient loading, so the links under *Post* below reach it
normally, and `workflows.review-pr-fresh` — the lane that actually posts —
declares it in its own boundary `contracts`.

The lens procedures the worker applies are declared on the `review.pr-batch`
boundary in `interfaces/model-routing.json` rather than in *Required Context*,
because they are this lane's contract and not the document's: the main thread
reading this file has no use for six reviewer lenses.

## Batch Contract

The main thread is a thin orchestrator:
- resolve the PR list
- collect each PR's evidence
- dispatch bounded single-PR reviews over that evidence
- collect compact results
- post per-PR and aggregate comments

The main thread must not accumulate full diffs or full review transcripts for every PR.

**Every side effect belongs to the main thread.** Review routes are read-only by
construction — no `Write`/`Edit`, `plan` permission mode on Claude, and a
network-less `read-only` sandbox on Codex. A worker therefore cannot run
`gh pr view` and cannot post a comment. A dispatch that tells it to do either
fails on one provider and silently does nothing useful on the other, so the fetch
and post steps stay here where the capability actually exists.

## Resolve PRs

- `--all-open`: run `gh pr list --json number,title --state open`
- Multiple numbers: parse provided refs

## Collect Per-PR Evidence

For each PR, before dispatching, the main thread gathers and holds the payload for
exactly one worker at a time:

```bash
gh pr view <N> --json number,title,body,baseRefName,headRefName,author,files
gh pr diff <N>
```

Pass the diff by value in the dispatch payload, or write it to a scratch file and
pass the path when it is large. Discard it once that worker returns — holding every
PR's diff is the accumulation this procedure exists to avoid.

## Dispatch

<!-- aitk-model-route:review.pr-batch -->
For each PR, dispatch a read-only subagent on `review`/`deep-review` with:
- PR number/ref, title, and base/head refs
- the PR diff and file list collected above — the worker reads, it does not fetch
- flags (draft/summary by default; pass `--auto` only when the user explicitly requested auto-posting)
- the literal line `Batch mode: Code-judo suppressed` — a per-PR review sees only
  its own payload plus its inlined contract closure, so this suppression must
  travel in the payload; without it the default `Code-judo lane: YES` rule applies
- the compact return contract below

The worker returns findings and a recommendation. It does not post them.

**The worker is a single reviewer, not a nested orchestrator.** A review route
has no subagent capability — `plan` permission mode on Claude, a network-less
`read-only` sandbox on Codex — so where [pr-review.md](pr-review.md) says
*launch* the triggered lenses in parallel, that instruction belongs to a main
thread. A batch worker instead **applies** each triggered lens procedure itself,
sequentially, in its own single context, and returns one merged result. This is
the whole reason the classifier is in its closure: it selects the lens set the
worker then works through, not a fan-out it dispatches. A dispatch that tells
the worker to fan out describes a lane no provider can run.

**The applied set is the batch set, not the full menu.** The worker applies only
the lenses inlined in its own closure — code quality, deep quality, test review,
test-plan review, frontend, and backend. The two lenses that carry a
`deep-review` route floor, **adversarial** and **architecture**, are excluded
here for the same reason Code-judo is: batch runs on `review` as often as not,
and a floored lens applied on the cheap route is the floor defeated rather than
honoured. The exclusion is enforced, not merely written down: a lane with no lens
menu never passes `--lens`, so the resolver's per-lens floor cannot see it, and
the manifest check instead rejects any menu-less boundary that inlines a floored
lens on a route below that lens's floor. Restricting the lane to `deep-review`
would not lift the exclusion either — the closure is the same 16 contracts on
both routes, so a costlier batch would still be a batch without those two lenses.

`classify-diff` still reports both truthfully, so **a worker that sees either
triggered names it in the `Deferred lenses:` line** rather than skipping it or
improvising the pass from the classifier's one-line description. That line is
the escalation signal: the main thread routes those PRs to a single-PR deep
review ([review-pr](../../workflows/references/review-pr.md)), where the fan-out
dispatches the lens on the route its own contract requires. Without the line, an
excluded-but-triggered lens is indistinguishable from a lens that never
triggered — the same failure `suppressed (batch)` exists to prevent for
Code-judo.

Return contract — a routed worker returns the **generic worker envelope**
(`status`, `summary`, `findings`, `verification`) and nothing else. There is no
per-boundary result shape: the route runner validates every result against that
schema with `additionalProperties: false`, so a boundary that declares its own
Markdown hand-back describes a dispatch that always fails. The batch fields
travel inside the envelope:

- `status` — `completed`, or `blocked`/`failed` when the payload was unusable
- `summary` — three labelled lines:

  ```
  PR: #<N> <title>
  Recommendation: approve | request-changes | comment
  Residual risk: <one line, or none>
  Deferred lenses: <names, or none>
  ```

  `Deferred lenses` names the lenses `classify-diff` triggered for this PR that
  are not in the worker's closure — adversarial, architecture, or both — and
  `none` when it triggered neither. A worker never writes `none` for a lens it
  simply chose not to apply.

- `findings` — canonical `[major]`/`[minor]`/`[nitpick]` findings, highest
  severity first. The top finding is the first entry; the counts are the array.
- `verification` — the checks the worker actually ran (pre-verdict gate, test
  evidence), one per entry.

All four of those `summary` lines and the severity tag on every finding are
**checked by the route runner**, not just requested here. The boundary declares
`lens_domain: "code"` and `summary_form: "pr-batch"`, so a `completed` result
whose findings do not *open* with a canonical tag, or whose summary is missing
the PR line, the recommendation, the residual-risk line, or the deferred-lens
line, fails the dispatch.
Before this was checked, the batch lane declared no domain at all: a worker could
return a paragraph with no PR number and no recommendation, pass the generic
envelope schema, and leave the main thread rendering a comment out of nothing.
A worker that genuinely cannot review returns `blocked`/`failed` instead — those
statuses are not held to the grammar, because an explanation of why a review was
impossible has no recommendation to give.

The worker returns no comment body. The main thread renders the comment from
`summary` and `findings` per [pr-posting.md](pr-posting.md), which is in the main
thread's context and not the worker's — a worker-authored body would be the one
artifact of the review that the posting contract never saw.

## Post

The main thread renders each worker's `summary` and `findings` into a comment per
[pr-posting.md](pr-posting.md) and posts it, honouring the draft/summary/`--auto`
flag it passed down, and records the result in the wave table's `Posted` column. `Posted` is the main thread's own observation of
its own `gh` call — never a value a worker reported.

It also carries each worker's `Deferred lenses:` value into the wave table's
`Deferred` column, and every PR whose value is not `none` goes in the aggregate's
*Needs Attention* list as a deep review the batch could not run. That escalation
is the main thread's, not the worker's: a review route has no subagent
capability, so the worker can report the gap but cannot close it.

Batch mode runs the **findings** lenses only — the Code-judo generative pass is
suppressed here unconditionally, including when `classify-diff` reports
`Code-judo lane: YES` for a PR in the batch (a `^refactor` title alone sets that
field, so expect it routinely). Its unscored restructuring *proposals* have no slot in the compact
per-PR return contract above, and the `deep-review` route is too expensive to fan
out across a batch. When a specific PR warrants a Code-judo pass, run a single-PR
deep review ([review-pr](../../workflows/references/review-pr.md)) instead.

This is the **one** documented exception to the umbrella rule "dispatch judo on
`Code-judo lane: YES`" (see the review SKILL's *Code-judo* section). It holds only
because the dispatch above passes `Batch mode: Code-judo suppressed` explicitly —
the exception belongs to the caller, not to the lane classifier, which still
reports the field truthfully.

The suppression is the main thread's own decision, so the main thread also owns
recording it: when it writes the per-PR `## PR Review — #N` entry (or folds it
into the wave block below, whose `Proposals` column exists for exactly this), the
proposals slot reads `suppressed (batch)`, never `none` — the latter falsely implies a judo pass ran and found no move. The
compact return contract above needs no proposals slot for this; a batch-mode
review never produces proposals to report.

Concurrency: run up to 3-5 PR reviews in parallel. Lower concurrency if PRs are unusually large, share code ownership, or the repo is resource constrained.

## Per-Wave PROJECT.md Persistence (Hard Gate Before Clear)

After each wave of ≤3 PRs completes, before launching the next wave, append a `## Review-PR Batch Wave N` block to PROJECT.md:

```markdown
## Review-PR Batch Wave N
PRs: [#101, #102, #103]
| PR | Recommendation | Posted | Top Finding | Proposals | Deferred | Residual Risk |
|----|----------------|--------|-------------|-----------|----------|---------------|
| #101 | approve | draft | none | suppressed (batch) | none | none |
| #102 | request-changes | no | [...] | suppressed (batch) | adversarial | [...] |
| #103 | comment | yes | [...] | suppressed (batch) | none | [...] |
Next wave: [PR numbers OR "aggregate"]
```

For batches of 4+ PRs, checkpoint + context_reset after each wave block is written. The main thread resumes by reading the wave entries in PROJECT.md, not by replaying per-PR diffs. Without this write, the per-PR posting state and residual risks are lost.

## Aggregate

```markdown
## Review Batch Complete — <N> PRs

| PR | Title | Recommendation | Key Finding | Posted |
|----|-------|----------------|-------------|--------|
| #1 |  | approve | Clean — no issues | draft |

### Needs Attention
- PR #<N>: <why it needs manual follow-up>
- PR #<N>: deferred <lens> — run a single-PR deep review
```

If no PR drew findings, write `All PRs reviewed cleanly`. That is a statement
about findings, not about coverage: Code-judo is suppressed batch-wide and
`Deferred` may name a lens this lane could not run, so a clean batch is one that
found nothing on the axes it *did* review. A non-`none` `Deferred` value
therefore still earns a *Needs Attention* line even under `All PRs reviewed
cleanly` — it names a PR whose own classifier asked for an axis the batch has no
procedure for, which is a gap in coverage rather than an absence of findings.
Code-judo needs no such line: its suppression is unconditional here and the
`suppressed (batch)` cell already records it on every row.

## Notes

Reviews are read-only. No worktrees are needed unless an optional external reviewer requires checkout isolation.
