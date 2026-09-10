# Independent PR Review

> **When**: Asked to review someone else's GitHub PR.
> **Produces**: One independent review with validated findings, a recommendation, and optional posting.

## Effect Boundary

Effect: `external_effect`.

Use `--draft` to show the review locally without posting. Use `--auto` to skip
confirmations and authorize posting or approval for the reviewed PRs.

## Authorization Boundary

Authorization mode: `explicit`. Invocation alone does not authorize posting or
approval; `--auto` or a separate confirmation grants the bounded provider
effect after the PII scrub.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `review-pr` entry in
`interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Usage

```
review-pr <pr-number-or-url> [--deep] [--draft] [--adversarial] [--auto]
review-pr 101 102 103
review-pr --all-open
```

## Steps

1. **Resolve input.** Single PR, several, or `--all-open`. Batches follow
   [skills/review/references/pr-batch.md](../../review/references/pr-batch.md):
   one bounded reviewer per PR, compact results, the parent posts.
2. **Review one PR** with
   [skills/review/references/pr-review.md](../../review/references/pr-review.md):
   gather context, classify, validate the premise for COMPLEX or CORE-impact
   PRs, one independent review on the other provider, deep lenses only on
   flags, validate findings, recommend.
3. **Post or draft** with
   [skills/review/references/pr-posting.md](../../review/references/pr-posting.md)
   after the PII scrub from `feedback/references/reply-resolve.md`. Findings
   posted to GitHub carry severity and evidence only; model provenance stays in
   the local record.

## Contract

- Read full changed-file context, not only the diff.
- Emit the Complexity Gate for single-PR reviews; assess impact before
  calibrating severity.
- Show findings and severity reasoning before posting unless `--auto`.
- `--deep` (or a deep-tier phrase) pins complexity to at least COMPLEX and runs
  the independent review on `deep-review`. It is a route escalation, not a
  larger reviewer roster.
- Append `## PR Review — #N` to `PROJECT.md` for every reviewed PR before the
  chat summary; batches also write `## Review-PR Batch Wave N` per wave.
- Never describe a review as cross-provider when the same-provider fallback
  ran; the record names the lane.
