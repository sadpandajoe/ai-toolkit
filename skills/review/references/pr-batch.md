# PR Review Batch

Use when `review-pr` receives multiple PR numbers or `--all-open`.

## Required Context

- [classify-diff.md](classify-diff.md) — the per-PR worker reads its own
  payload's domains and risk flags so it knows which risks to cover explicitly.

The reviewer contract the worker applies is declared on the `review.pr-batch`
boundary in `interfaces/model-routing.json`.

## Batch Contract

The main thread is a thin orchestrator: resolve the PR list, collect each PR's
evidence, run bounded single-PR reviews over it, collect compact results, and
post. It never accumulates every PR's full diff or review transcript.

**The main thread owns every side effect.** Review routes are read-only and
network-less, so a worker cannot run `gh` or post; fetching and posting stay
here.

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

Pass the diff by value in the payload, or as a scratch-file path when it is
large, and discard it once that worker returns.

## Dispatch

<!-- aitk-model-route:review.pr-batch -->
For each PR, dispatch a read-only subagent on `review`/`deep-review` with:
- PR number/ref, title, and base/head refs
- the PR diff and file list collected above — the worker reads, it does not fetch
- flags (draft/summary by default; pass `--auto` only when the user explicitly requested auto-posting)
- the literal line `Batch mode: Code-judo suppressed`, so a `^refactor` title
  does not fire the judo lane from inside the worker
- the compact return contract below

The worker returns findings and a recommendation. It does not post them.

**The worker is a single reviewer, not a nested orchestrator.** A review route
has no subagent capability, so the worker applies the independent reviewer
contract itself, covering the risks its classifier flags name. Deep lenses
(adversarial, deep-quality, architecture) carry a `deep-review` floor and do
not run inside a batch worker: it reports every flagged lens under
`Deferred lenses:` and the main thread escalates that PR to a single-PR review.

Concurrency: at most 3 PR reviews per wave, lower for large PRs.

## Post

The main thread renders each worker's `summary` and `findings` per
[pr-posting.md](pr-posting.md), posts with the draft/summary/`--auto` flag it
passed down, and records its own observation of that `gh` call in the wave
table's `Posted` column, never a value a worker reported.

Each worker's `Deferred lenses:` value goes in the `Deferred` column, and
every PR whose value is not `none` gets a *Needs Attention* line as a deep
review the batch could not run.

Batch mode never runs the Code-judo pass, even when `classify-diff` reports
`Code-judo lane: YES`; when a PR warrants one, run a single-PR deep review
([review-pr](../../workflows/references/review-pr.md)). The proposals slot of
every batch row reads `suppressed (batch)`, never `none`, which would imply a
judo pass ran and found no move.

## Per-Wave PROJECT.md Persistence (Hard Gate Before Handoff)

After each wave completes, before launching the next, append:

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

For batches of 4+ PRs, checkpoint after each wave block. A fresh session resumes
from the wave entries, not by replaying per-PR diffs; without them the posting
state and residual risks are lost.

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

`All PRs reviewed cleanly` describes findings, not coverage: a PR with a
non-`none` `Deferred` value still gets its *Needs Attention* line.
