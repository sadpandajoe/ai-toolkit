---
name: review
description: "Use for reviewing implemented code through orchestration, classification, reviewer lenses, and PR helpers. Do NOT use for plan review, root-cause investigation, or implementation."
---

# Review

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

## Required Context

Read before starting: `rules/stop-rules.md`. That is the only contract *every*
lane on a review route shares. The grading contracts (code-review, severity,
scoring) belong to the individual findings lenses and are named in each lens
file's own Required Context — deliberately not here, and deliberately without
backticked paths, because anything this section names is inlined into every lane
that resolves through this umbrella. That includes the generative Code-judo lane
and the non-code-review routes (QA validation, PM brief review, plan review)
that also carry this file.

Umbrella for code-review work — review of *shipped code*, not plans. References
are grouped by role so workflows load only the phase they are entering.

## Orchestration

| Reference | Role |
|-----------|------|
| [references/local-review.md](references/local-review.md) | Local `review-code` orchestration |
| [references/pr-review.md](references/pr-review.md) | Single GitHub PR review procedure |
| [references/pr-batch.md](references/pr-batch.md) | Batch PR review orchestration |
| [references/adversarial-orchestration.md](references/adversarial-orchestration.md) | `review-code-adversarial` orchestration |
| [references/workflow-review.md](references/workflow-review.md) | Standard-tier capability orchestration (lens fan-out → dedup → adversarial verify) |
| [references/ensemble.md](references/ensemble.md) | Tiered model/provider rosters, verifier diversity, and coverage reporting |

## Classifiers

| Reference | Role |
|-----------|------|
| [references/classify-diff.md](references/classify-diff.md) | Read diff + complexity tier, return which reviewer domains should activate |

## Posting Helpers

| Reference | Role |
|-----------|------|
| [references/pr-posting.md](references/pr-posting.md) | GitHub review posting and summary rules |

## Reviewer Lenses

| Lens | When | Reference | Route |
|------|------|-----------|-------|
| Code quality | Always (every complexity tier) | [references/code-quality.md](references/code-quality.md) | review |
| Deep quality | Refactor-shaped or STANDARD diff, deep review mode, a bare "deep quality" lens ask, **or** whenever the tier's mandatory `deep-review` route would otherwise carry no lane (see [references/ensemble.md](references/ensemble.md)). Strict structural **findings**. Routed by `classify-diff`. | [references/deep-quality.md](references/deep-quality.md) | deep-review |
| Code-judo | `classify-diff` reports `Code-judo lane: YES` — deep review mode, a `^refactor`-titled change, or an explicit Code-judo ask. Generative restructuring **proposal** (runs outside the findings fan-out). Pinned deep tier — see Invocation. | [references/code-judo.md](references/code-judo.md) | deep-review |
| Adversarial | Security-sensitive diffs; `review-code-adversarial` workflow | [references/adversarial.md](references/adversarial.md) | deep-review |

## Distinction vs Other Umbrellas

- **review/** (this skill) — reviews code (post-implementation)
- **plan-review/** — reviews plans (pre-implementation)
- **testing/** — includes `review-tests` + `review-testplan` (test-harness-specific reviewers)
- **qa/** — scenario-level critique (bug triage, validation)

The `review-code` workflow dispatches through `classify-diff`, which chooses lenses from this umbrella **and** the `testing/` umbrella when tests are in scope.

<!-- aitk-model-route:review.pr-lenses -->
The `review-pr` workflow uses `pr-review`, `pr-batch`, and `pr-posting` for PR-specific context gathering and GitHub interaction, then dispatches the same reviewer lenses on `review`/`deep-review` as `review-code`:

- [references/code-quality.md](references/code-quality.md)
- [references/deep-quality.md](references/deep-quality.md)
- [references/adversarial.md](references/adversarial.md)
- [../testing/references/review-tests.md](../testing/references/review-tests.md)
- [../testing/references/review-testplan.md](../testing/references/review-testplan.md)
- [../plan-review/references/architecture.md](../plan-review/references/architecture.md)
- [../plan-review/references/frontend.md](../plan-review/references/frontend.md)
- [../plan-review/references/backend.md](../plan-review/references/backend.md)

Those lanes grade shipped code, so they read `rules/code-review.md` and
`rules/severity.md` before scoring. The lens files that carry code-review tags
name both themselves; the two plan-review lenses above are reused here on code
rather than on a plan, so this boundary supplies the calibration they would
otherwise lack. Naming it in this span rather than in Required Context above
keeps it out of the non-code-review routes that also carry this umbrella.

Code-judo is not in that fan-out: it dispatches at the `review.code-judo`
boundary, which carries its own contract closure.

## Invocation

Reviewer lens references are subagent prompts. Orchestration and posting references are read by the main thread. Tier routing, deep review mode's three-effect escalation, and the Code-judo deep-tier exception are detailed in [references/dispatch.md](references/dispatch.md) — read it before dispatching.

## Notes

- `classify-diff` has a different shape from the reviewer references (it's a classifier, not a reviewer). Grouped here because reviewer dispatch is the head of the review workflow.
- Reviewer lens descriptions declare their own reasoning-load hints in frontmatter for subagent spawning.
