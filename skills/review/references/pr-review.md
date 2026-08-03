---
tier: Heavy
---

# PR Review Procedure

Use for a single GitHub PR review after `review-pr` resolves the PR reference.

## Required Context

Read before grading: `rules/code-review.md` and `rules/severity.md`. Every lane
that dispatches from this file produces or triages severity-tagged code-review
findings, and the calibration in `rules/code-review.md` applies to every review
path — single-reviewer, adversarial, and multi-reviewer synthesis. The review
umbrella deliberately no longer supplies these (it is also carried by plan, PM,
and QA routes), so a lane whose closure contains no reviewer lens would
otherwise grade with no calibration contract at all.

## Gather Context

Fetch:

```bash
gh pr view <ref> --json title,body,author,baseRefName,headRefName,files,additions,deletions
gh pr diff <ref>
gh pr view <ref> --json files -q '.files[].path'
```

Read full contents of changed files. Review comments target changed lines, but the review must understand surrounding context.

## Complexity Gate

Classify the PR scope with the shared TRIVIAL / MODERATE / STANDARD gate and this review-specific routing:

| Signal | Trivial | Moderate | Standard |
|--------|---------|----------|----------|
| Files changed | 1-3 | 4-8 in one subsystem | 9+ or unclear ownership |
| Lines changed | < 100 | 100-400 | 400+ |
| Behavioral change | None / cosmetic | Contained functional change | Cross-cutting or contract change |
| Reviewer lanes | Code quality only | Triggered lanes only | Full triggered team, plus optional second opinion |

Emit the Complexity Gate block per `rules/complexity-gate.md`.

Trivial + confidence 8/10+: code quality review only, unless impact assessment escalates. Moderate: triggered reviewer lanes only, with no premise deep-dive unless impact or uncertainty escalates. Standard: premise validation plus full triggered team.

## Assess Impact and Premise

Run [../../qa/references/assess-impact.md](../../qa/references/assess-impact.md) on the PR diff to classify impact as CORE, STANDARD, or PERIPHERAL.

Impact escalation:
- TRIVIAL + CORE -> code quality plus only the lens matching why the workflow is
  CORE. Use the full team only when multiple CORE lenses apply or the relevant
  safety lens is ambiguous.
- MODERATE + CORE -> triggered reviewer lanes plus stricter severity calibration
- STANDARD + CORE -> full team + suggest adversarial review for security-sensitive areas

For Standard, CORE-impact, or low-confidence PRs, validate the premise before reviewing implementation details:
1. Read linked issue/ticket, PR description, author comments, and prior reviewer comments.
2. Investigate whether the stated problem exists.
3. For bug fixes, check whether the fix addresses the actual cause.
4. For features, check whether the feature solves the stated need and belongs in the chosen architecture.

If the premise is wrong, make that the primary finding and skip remaining review lanes. Still route it through the reasoning/confirmation flow before posting.

## Detect Review Team

Follow [classify-diff.md](classify-diff.md) with the diff and complexity tier. Pass the impact assessment to all reviewers so severity calibration can account for CORE workflows.

For Standard or CORE-escalated PRs, include pattern analysis:
- read 2-3 similar files in the same directory/module
- compare naming, error handling, imports, signatures, and local conventions
- flag convention deviations as `[minor]` with evidence

## Launch Review Lanes

`review.pr-moderate` and `review.pr-standard` are lens fan-out boundaries: they
declare a `lenses` menu, so each dispatch names exactly one lens with
`--lens <repo-relative lens path>` and resolving either without it fails closed.
One worker receives one reviewer contract, never the whole set the marker lists
below, so resolve a separate route per triggered lens rather than batching them.

Trivial:
- Single-pass code quality review.
- If clean, return a compact approve recommendation. Post/approve only when `--auto` or explicit user authorization grants that boundary.

Moderate:
<!-- aitk-model-route:review.pr-moderate -->
- Launch only the triggered reviewer lenses needed by the diff classification.
  Triggered lenses come from this set: [code-quality.md](code-quality.md),
  [deep-quality.md](deep-quality.md),
  [adversarial.md](adversarial.md),
  [../../testing/references/review-tests.md](../../testing/references/review-tests.md),
  [../../testing/references/review-testplan.md](../../testing/references/review-testplan.md),
  [../../plan-review/references/architecture.md](../../plan-review/references/architecture.md),
  [../../plan-review/references/frontend.md](../../plan-review/references/frontend.md),
  [../../plan-review/references/backend.md](../../plan-review/references/backend.md).
  Code-judo is not one of them — it dispatches at its own boundary below.
- Keep the main thread compact: collect findings, recommendation, confidence, and any premise uncertainty.
- Escalate to Standard only when reviewers find cross-cutting risk, unclear ownership, or security-sensitive behavior.

Standard:
<!-- aitk-model-route:review.pr-standard -->
- Launch triggered reviewer lenses in parallel.
  Triggered lenses come from this set: [code-quality.md](code-quality.md),
  [deep-quality.md](deep-quality.md),
  [adversarial.md](adversarial.md),
  [../../testing/references/review-tests.md](../../testing/references/review-tests.md),
  [../../testing/references/review-testplan.md](../../testing/references/review-testplan.md),
  [../../plan-review/references/architecture.md](../../plan-review/references/architecture.md),
  [../../plan-review/references/frontend.md](../../plan-review/references/frontend.md),
  [../../plan-review/references/backend.md](../../plan-review/references/backend.md).
  Code-judo is not one of them — it dispatches at its own boundary below.
- Use `review` for bounded PR lanes and `deep-review` for architecture,
  security-sensitive, adversarial, or substantial multi-system lanes.
- Optional second opinion when available.
- Adversarial lane only with `--adversarial` or security-sensitive detection.
  It is one of the fan-out lenses above, so dispatch it like any other — its own
  `--lens` selection, on `deep-review` per the route rule above. That rule is a
  manifest constraint, not just orchestrator guidance: the boundary's `routes`
  list permits both routes for the lane as a whole, but `lens_routes` declares a
  per-lens floor, so `--lens adversarial` on `review` is rejected at resolve time
  rather than buying a cheaper pass than the lane is worth. On a
  TRIVIAL PR the flag escalates the tier to Moderate, because TRIVIAL runs a
  single pass with no fan-out boundary to launch it from; security-sensitive
  detection escalates to Standard under the existing rule. Its findings are
  severity-tagged, so they merge with the other lanes rather than getting their
  own section — that split belongs to Code-judo alone.

**Deep review mode.** When `classify-diff` reports **Deep-tier escalation: YES**
(`ultra`/`max` effort or a deep-tier phrase — that skill owns the phrase list),
follow the review SKILL's *Deep review mode* section and route every triggered
lens through `deep-review`; both `review.pr-moderate` and `review.pr-standard`
permit it.

**Code-judo lane.** Dispatch the code-judo generative pass separately via
`review.code-judo` whenever `classify-diff` reports **Code-judo lane: YES** *and*
the dispatching caller did not pass `Batch mode: Code-judo suppressed` — which a
`^refactor` PR title or an explicit ask can set on its own, with
`Deep-tier escalation: NO`. Do not gate judo dispatch on the escalation field.
Code-judo returns unscored restructuring **proposals**; surface them in their own
section, not the scored findings/component table.

When the payload carries `Batch mode: Code-judo suppressed` (set by the batch
orchestrator in [pr-batch.md](pr-batch.md)), skip the judo lane even
on `Code-judo lane: YES`,
run the findings lenses only, and record the proposals slot as
`suppressed (batch)` rather than `none`.

## Synthesize and Score

Merge findings, deduplicate, and score:

| Component | Meaning |
|-----------|---------|
| Root Cause | Why was this change needed? |
| Solution | Is it efficient, maintainable, and scoped? |
| Tests | Are tests realistic and meaningful? |
| Code | Is it readable, consistent, and correct? |
| Docs | Are docs/comments sufficient? |

Use `rules/code-review.md` and `rules/severity.md`.

Before posting findings, show the user:
- issue and proposed severity
- why this severity
- confidence
- evidence

Clean reviews skip the reasoning review and proceed to posting rules.

## Recommendation

- **Approve**: overall 8/10+, zero `[major]`
- **Request Changes**: any `[major]`, or overall below 6/10
- **Comment**: overall 6-7/10, no `[major]` but notable `[minor]`

## Output

Return the synthesized review plus:
- recommendation
- team selected
- component scores
- finding counts
- posting mode needed (`draft`, `confirm`, `auto`)
