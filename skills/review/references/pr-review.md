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
| Ensemble ([ensemble.md](ensemble.md)) | `trivial` | `moderate` | `standard` (`deep` in deep review mode) |

Emit the Complexity Gate block per `rules/complexity-gate.md`.

`review-pr --deep` (and the phrase "deep review PR #N") pins the tier to at
least STANDARD before this table is read — size signals can raise that floor but
never lower it.

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
<!-- aitk-model-route:review.pr-trivial -->
- Dispatch exactly one fresh code-quality reviewer on `review`. That single lane **is** the independent review — never zero, never a second lane, and never an orchestrator self-review in its place.
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
- Launch triggered reviewer lenses in parallel on the origin provider, bounded by
  the ensemble's lens lane budget and the priority order in
  [classify-diff.md](classify-diff.md).
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

<!-- aitk-model-route:review.pr-cross-provider-cold -->
Standard and deep PR reviews also dispatch the ensemble's cross-provider cold reviewer as a separate stage: resolve the roster with `bin/aitk review-ensemble <tier> --provider <origin> --available <reachable>`, then run `bin/aitk model-run --provider <cross-provider>` on the resolved cross lane route with PR scope and diff only — never the origin lanes' findings. It does not consume the lens lane budget. Verify each `[major]`/`[minor]` with a lane from a different family than the one that raised it (a different provider at `deep`/`security`), and keep `provider/family` provenance on every finding through dedup into the report.

**Deep review mode.** When `classify-diff` reports **Deep-tier escalation: YES**
(`ultra`/`max` effort, `--deep`, or a deep-tier phrase — `classify-diff` owns
the phrase list), follow the review SKILL's *Deep review mode* section: pin the
tier to at least STANDARD, route every triggered lens through `deep-review` —
both `review.pr-moderate` and `review.pr-standard` permit it — and run the
cross-provider cold lane on `deep-review`.

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

If the cross provider is unreachable, the `deep` ensemble **blocks**: report the
resolver's disclosure and stop, or continue only on explicit user override with
the disclosure retained in the output. A single-provider run is never reported as
a deep review.

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
- team selected, with each lane's route and `provider/family`
- ensemble name, resolved `Model coverage:` level, and the resolver's disclosure sentence whenever it returns one (below floor, dropped lane, or no diverse verifier)
- component scores
- finding counts, each finding carrying raiser and verifier `provider/family`
- posting mode needed (`draft`, `confirm`, `auto`)

Findings posted to GitHub carry severity and evidence only. Model provenance
stays in the local report and PROJECT.md record — it is orchestration detail,
not review-comment content.
