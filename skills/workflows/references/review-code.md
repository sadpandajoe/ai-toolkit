# Independent Code Review

> **When**: You have local changes and want them reviewed and, by default, fixed ("review this branch and fix anything important"). "Review this; don't change anything" sets review-only.
> **Produces**: One independent review, validated findings, applied fixes with verification, an optional delta pass, a `PROJECT.md` review record, and a review gate.

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `review-code` entry
in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Usage

```bash
review-code                  # branch-wide: committed + uncommitted vs base
review-code src/api/         # filter to path
review-code --committed | --uncommitted
review-code --review-only    # findings and record, no fixes
```

## Procedure

Follow [skills/review/references/local-review.md](../../review/references/local-review.md)
end to end: gather and record the base, classify with
[classify-diff.md](../../review/references/classify-diff.md) and
`qa/references/assess-impact.md`, preflight, one independent review on the other
provider, conditional deep lenses on flagged risk, validate every finding before
fixing, fix accepted findings, verify with `skills/verification-loop/SKILL.md`,
run one delta review only after substantive remediation, emit the review gate,
and write the Review Record to `PROJECT.md`.

## Contract

- Review judgment comes only from fresh lanes; the parent validates, fixes, and
  verifies. It never reviews its own work inline.
- The review gate is a reasoning unit under `rules/gates.md`: one full review
  plus one delta pass. A finding class surviving the delta pass is `ESCALATE`
  (a deep lens or a user decision), never a third round.
- Zero-logic and micro-fix diffs may take the review exception; anything with
  logic gets the independent lane, even at TRIVIAL.
- Remediation is on by default when the user asked to review and fix; a
  review-only request records findings and the gate without editing.
- Suggest `review-code-adversarial` when the classifier flags security
  sensitivity and the user did not already ask for it.
- Internal callers (`create-feature`, `fix-bug`, `fix-ci`, `create-tests`,
  `update-tests`) own the next step after the gate; standalone runs end with
  the Review-Code Complete summary in the orchestration reference.
