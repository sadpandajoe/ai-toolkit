---
name: review
description: "Use for reviewing implemented code through orchestration, classification, reviewer lenses, and PR helpers. Do NOT use for plan review, root-cause investigation, or implementation."
---

# Review

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

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
| Deep quality | Refactor-shaped or STANDARD diff, or deep review mode (`max`/`ultra` effort / "deep review" / "deep quality" ask). Strict structural **findings**. Routed by `classify-diff`. | [references/deep-quality.md](references/deep-quality.md) | review (deep-review in deep review mode) |
| Code-judo | Deep review mode (`ultra`/`max` effort, "deep review" / "deep quality" / "thermonuclear" ask), `^refactor`-titled change, or explicit ask. Generative restructuring **proposal** (runs outside the findings fan-out). Pinned deep tier — see Invocation. | [references/code-judo.md](references/code-judo.md) | deep-review |
| Adversarial | Security-sensitive diffs; `review-code-adversarial` workflow | [references/adversarial.md](references/adversarial.md) | deep-review |

## Distinction vs Other Umbrellas

- **review/** (this skill) — reviews code (post-implementation)
- **plan-review/** — reviews plans (pre-implementation)
- **testing/** — includes `review-tests` + `review-testplan` (test-harness-specific reviewers)
- **qa/** — scenario-level critique (bug triage, validation)

The `review-code` workflow dispatches through `classify-diff`, which chooses lenses from this umbrella **and** the `testing/` umbrella when tests are in scope.

<!-- aitk-model-route:review.pr-lenses -->
The `review-pr` workflow uses `pr-review`, `pr-batch`, and `pr-posting` for PR-specific context gathering and GitHub interaction, then dispatches the same reviewer lenses on `review`/`deep-review` as `review-code`.

## Invocation

Reviewer lens references are subagent prompts. Orchestration and posting references are read by the main thread.

Dispatch mode is tier-routed:

- **TRIVIAL / MODERATE** — use `fresh_subagent` for each required independent
  lens; the provider binding chooses concrete syntax.
- **STANDARD** (or ≥3 triggered lanes) — use `parallel_fanout` per
  [references/workflow-review.md](references/workflow-review.md): lens fan-out →
  dedup → adversarial verify; only confirmed findings return to the session.

Map the tier to the current runtime's actual model or reasoning-effort controls at dispatch time.

### Deep review mode (tier override)

"Deep review", "deep quality review", or "thermonuclear" — and `ultra`/`max` effort — are an explicit **escalation**, not a route name. In this mode, route *every* triggered lens through the `deep-review` route instead of the tier's default route, and add the Code-judo lane below. The Complexity Gate still decides *which* lenses trigger; deep review mode only changes the route they run on. The lens dispatch boundaries (`review.local-primary-lanes`, `review.pr-standard`, `review.pr-moderate`, `review.code-quality-final`, `review.pr-lenses`) all permit `deep-review` in their allowlists, so this is a route selection, not a new binding. The independent second-opinion / independent-review *capability* lanes are external capabilities rather than lenses — they stay on their own `review` route and do not escalate.

### Code-judo (deep tier)

The `code-judo` lens is the one exception to tier-routing: it is pinned to the deep tier regardless of the diff's complexity. When `classify-diff` triggers the Code-judo lane, it runs on the `deep-review` route per [references/code-judo.md](references/code-judo.md) — the generative restructuring pass always runs on the deepest reasoning tier, never the standard `review` route. The `review.code-judo` boundary allows only `deep-review`, so a mistaken standard-route request fails closed rather than silently downgrading the model.

Run Code-judo **outside** the six-lane findings fan-out (see [references/workflow-review.md](references/workflow-review.md)): its output is unscored restructuring *proposals*, not severity-tagged findings, so it bypasses the dedup + adversarial-verification pipeline and lands in a dedicated **Restructuring Proposals** section of the Review Record rather than the findings table.

## Notes

- `classify-diff` has a different shape from the reviewer references (it's a classifier, not a reviewer). Grouped here because reviewer dispatch is the head of the review workflow.
- Reviewer lens descriptions declare their own reasoning-load hints in frontmatter for subagent spawning.
