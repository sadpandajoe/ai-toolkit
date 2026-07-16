# Adversarial Red-Team Review


> **When**: You want to stress-test changes for security holes, edge cases, race conditions, and failure modes.
> **Produces**: Merged adversarial findings, fixes, verification, and an adversarial Review Gate block.

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the
`review-code-adversarial` entry in `interfaces/contracts.json`; use `bin/aitk
checkpoint` for every durable transition and effect record.

## Usage

```bash
review-code-adversarial
review-code-adversarial --committed
review-code-adversarial src/api/
```

## Step Routing

Load [skills/review/references/adversarial-orchestration.md](../../review/references/adversarial-orchestration.md) when the review starts. It coordinates changed-file discovery, reviewer launch, finding merge, fixverify, and re-review.

Within that flow:

- Use [skills/review/references/adversarial.md](../../review/references/adversarial.md) for the primary adversarial reviewer.
- Use an optional second-opinion adversarial reviewer only when available.
- Use `review-code` style Review Gate semantics for final status.

## Gates

- Every finding needs a concrete failure scenario.
- Do not claim second-opinion coverage unless both lanes ran.
- Run `verify` or equivalent pre-flight checks before final Review Gate when fixes are applied.
- Fix, reject with evidence, or surface each finding as a user decision.
- Emit the adversarial Review Gate before the final summary.

## PROJECT.md Discipline

Adversarial review is expensive by definition (dual-lane reasoning, often security-sensitive). For STANDARD runs, follow `rules/context-management.md`:

- After finding merge (before fixes): append `## Adversarial Findings` to PROJECT.md (per-finding scenario, severity, both-lane attribution, fix/reject/discuss verdict).
- After each fix wave: append `## Adversarial Fix Round N` (findings fixed, files changed, verification result, residual risk).
- After re-review: update the adversarial Review Gate status in PROJECT.md.

These writes are **hard gates before any checkpoint + context_reset** — the per-finding scenarios are exactly the thing that's expensive to reconstruct and must not be lost to chat-only state.

## Summary Contract

End with:

```markdown
## Review-Code-Adversarial Complete
Rating: [Hardened/Adequate/Vulnerable/Critical] | Rounds: [N] | Status: [clean/blocked]
Reviewers: [primary + second opinion | primary only]

### Findings
- [...]

### Fixed
- [...]

### Accepted Risks
- [...]
```
