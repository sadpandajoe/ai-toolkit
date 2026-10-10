# PR Review Batch

Use when `review-pr` receives multiple PR numbers or `--all-open`.

## Required Context

- [classify-diff.md](classify-diff.md) — the per-PR worker reads its own
  payload's domains and risk flags so it knows which risks to cover explicitly.

The reviewer contract the worker applies is declared on the `review.pr-batch`
boundary in `interfaces/model-routing.json`.

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
  travel in the payload; without it a `^refactor` title would fire the judo lane
- the compact return contract below

The worker returns findings and a recommendation. It does not post them.

**The worker is a single reviewer, not a nested orchestrator.** A review route
has no subagent capability, so the worker applies the independent reviewer
contract itself, in one context, covering the risks its payload's classifier
flags name. Deep lenses (adversarial, deep-quality, architecture) carry a
`deep-review` route floor and do not run inside a batch worker; when a PR's
classification flags any of them, the worker reports every flagged lens under
`Deferred lenses:` (deep-quality included) and the main thread escalates that
PR to a single-PR review instead.

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

Batch mode never runs the Code-judo pass, even when `classify-diff` reports
`Code-judo lane: YES` for a PR: proposals have no slot in the compact per-PR
return contract, and the classifier still reports the field truthfully. When a
specific PR warrants a Code-judo pass, run a single-PR deep review
([review-pr](../../workflows/references/review-pr.md)) instead. The main thread
records the proposals slot of every batch row as `suppressed (batch)`, never
`none`, which would imply a judo pass ran and found no move.

Concurrency: run PR reviews in waves of up to three; use smaller waves when PRs are unusually large, share code ownership, or the machine is resource constrained.

## Per-Wave PROJECT.md Persistence (Hard Gate Before Handoff)

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

For batches of 4+ PRs, checkpoint after each wave block is written; a fresh session or worker resumes from it. The main thread resumes by reading the wave entries in PROJECT.md, not by replaying per-PR diffs. Without this write, the per-PR posting state and residual risks are lost.

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

If no PR drew findings, write `All PRs reviewed cleanly`. That describes
findings, not coverage, so every PR with a non-`none` `Deferred` value still
gets a *Needs Attention* line.

## Notes

Reviews are read-only. No worktrees are needed unless an optional external reviewer requires checkout isolation.
