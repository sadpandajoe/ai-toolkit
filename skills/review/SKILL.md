---
name: review
description: "Use for reviewing implemented code: one independent review of a local diff or PR, conditional deep lenses on flagged risk, delta re-review after fixes, batch PR review, and PR posting. Do NOT use for plan validation, root-cause investigation, or implementation."
---

# Review

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

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
| [references/pr-posting.md](references/pr-posting.md) | Posting rules, PII scrub, voice |
| [references/classify-diff.md](references/classify-diff.md) | Domains, impact, and risk flags that select deep lenses |
| [references/adversarial.md](references/adversarial.md) | Deep lens: security, edge cases, races, integrity (`deep-review`) |
| [references/deep-quality.md](references/deep-quality.md) | Deep lens: strict structural findings (`deep-review`) |
| [references/code-judo.md](references/code-judo.md) | Generative restructuring proposals, explicit ask only (`deep-review`) |

The architecture lens for code lives in
`plan-review/references/architecture.md` and fires as a deep lens when the
classifier flags an architecture change.

## Who reviews

- **Independent reviewer**: the specialist contract in
  `agents/specialists/reviewer.md`, run on the `review` route on the other
  provider when reachable, otherwise the toolkit's same-provider reviewer agent
  with the disclosure `Independent review: same-provider`.
- **Deep lenses**: at most two per review, on `deep-review`, one lens per
  worker, only on classifier flags or an explicit ask.
- **Delta reviewer**: the same contract in delta mode, after substantive
  remediation only.

The orchestrator never reviews its own work and never substitutes its judgment
for the independent lane; it validates findings, applies fixes, and runs the
verification loop.

## Sibling umbrellas

`planning/` validates plans; `testing/` owns test authoring and test-suite
review knowledge; `qa/` owns scenario-level critique. The `review-code`,
`review-pr`, and `review-code-adversarial` workflows are the public entry
points.
