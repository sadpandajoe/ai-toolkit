---
name: review
description: "Use for reviewing implemented code: one independent review of a local diff or PR, conditional deep lenses on flagged risk, delta re-review after fixes, batch PR review, and PR posting. Do NOT use for plan validation, root-cause investigation, or implementation."
---

# Review

Umbrella for review of shipped code. The model is one fresh independent review
by default, validated by the orchestrator before anything is changed, one
delta pass after substantive fixes, and deep lenses only where the classifier
flagged risk. See `rules/code-review.md` for the contract and calibration.

## References

| Reference | Role |
|---|---|
| [references/local-review.md](references/local-review.md) | `review-code` orchestration: scope, classify, independent review, validate, fix, delta |
| [references/pr-review.md](references/pr-review.md) | Single GitHub PR review procedure |
| [references/pr-batch.md](references/pr-batch.md) | Batch PR review: one bounded reviewer per PR |
| [references/pr-posting.md](references/pr-posting.md) | Posting rules and voice |
| [references/classify-diff.md](references/classify-diff.md) | Domains, impact, and risk flags that select deep lenses |
| [references/adversarial.md](references/adversarial.md) | Deep lens: security, edge cases, races, integrity (`deep-review`) |
| [references/deep-quality.md](references/deep-quality.md) | Deep lens: strict structural findings (`deep-review`) |
| [references/architecture.md](references/architecture.md) | Deep lens: architecture changes (`deep-review`) |
| [references/code-judo.md](references/code-judo.md) | Generative restructuring proposals, explicit ask only (`deep-review`) |

The independent reviewer's contract is `agents/specialists/reviewer.md`. Cold
review and never self-review are owned by `rules/specialist-handoff.md`
(Critic profile).

## Sibling umbrellas

`planning/` validates plans; `testing/` owns test authoring; `qa/` owns
scenario-level critique. The `review-code`, `review-pr`, and
`review-code-adversarial` workflows are the public entry points.
