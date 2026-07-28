---
name: review
description: "Use for reviewing implemented code through orchestration, classification, reviewer lenses, and PR helpers. Do NOT use for plan review, root-cause investigation, or implementation."
---

# Review

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

## Required Context

Read before starting: `rules/code-review.md`, `rules/stop-rules.md`. Every lane
on a review route shares these two; the severity scale belongs to the individual
findings lenses, so the generative Code-judo lane does not inherit it.

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
| Deep quality | Refactor-shaped or STANDARD diff, deep review mode, or a bare "deep quality" lens ask. Strict structural **findings**. Routed by `classify-diff`. | [references/deep-quality.md](references/deep-quality.md) | review (deep-review in deep review mode) |
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
- [../testing/references/review-tests.md](../testing/references/review-tests.md)
- [../testing/references/review-testplan.md](../testing/references/review-testplan.md)
- [../plan-review/references/architecture.md](../plan-review/references/architecture.md)
- [../plan-review/references/frontend.md](../plan-review/references/frontend.md)
- [../plan-review/references/backend.md](../plan-review/references/backend.md)

Code-judo is not in that fan-out: it dispatches at the `review.code-judo`
boundary, which carries its own contract closure.

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

Deep review mode is entered on `ultra`/`max` effort or a **deep-tier phrase** — `classify-diff` owns that phrase list (see its *Deep-tier phrases* section) and reports the verdict as `Deep-tier escalation: YES`. Do not re-derive the phrase set here. Note that a bare "deep quality" ask is *not* one of those phrases: it requests the cheap deep-quality lens, not this tier override.

Deep review mode is an explicit **escalation**, not a route name. In this mode, route *every* triggered lens through the `deep-review` route instead of the tier's default route, and add the Code-judo lane below. Escalation is *sufficient* to add that lane but not necessary — the lane also fires on a `^refactor` title or an explicit Code-judo ask with escalation `NO`, so dispatch it on `Code-judo lane: YES`. The Complexity Gate still decides *which* lenses trigger; deep review mode only changes the route they run on. The lens dispatch boundaries (`review.local-primary-lanes`, `review.pr-standard`, `review.pr-moderate`, `review.code-quality-final`, `review.pr-lenses`) all permit `deep-review` in their allowlists, so this is a route selection, not a new binding. The independent second-opinion / independent-review *capability* lanes are external capabilities rather than lenses — they stay on their own `review` route and do not escalate.

### Code-judo (deep tier)

The `code-judo` lens is the one exception to tier-routing: it is pinned to the deep tier regardless of the diff's complexity **and regardless of whether deep review mode is active**. Whenever `classify-diff` reports `Code-judo lane: YES` — including on an otherwise standard-tier `^refactor`-titled change with `Deep-tier escalation: NO` — it runs on the `deep-review` route per [references/code-judo.md](references/code-judo.md) — the generative restructuring pass always runs on the deepest reasoning tier, never the standard `review` route. The `review.code-judo` boundary allows only `deep-review`, so a mistaken standard-route request fails closed rather than silently downgrading the model.

**Batch exception.** Multi-PR batch review ([references/pr-batch.md](references/pr-batch.md))
is the one documented exception: it runs the findings lenses only and suppresses
the judo pass even on `Code-judo lane: YES`. Because each per-PR review sees only
its own payload, the batch orchestrator must include the literal line
`Batch mode: Code-judo suppressed` in that payload; a payload without it follows
the default rule above. `classify-diff` still reports the lane truthfully — the
exception lives in the caller, not the classifier.

Run Code-judo **outside** the six-lane findings fan-out (see [references/workflow-review.md](references/workflow-review.md)): its output is unscored restructuring *proposals*, not severity-tagged findings, so it bypasses the dedup + adversarial-verification pipeline and lands in a dedicated **Restructuring Proposals** section of the Review Record rather than the findings table.

## Notes

- `classify-diff` has a different shape from the reviewer references (it's a classifier, not a reviewer). Grouped here because reviewer dispatch is the head of the review workflow.
- Reviewer lens descriptions declare their own reasoning-load hints in frontmatter for subagent spawning.
