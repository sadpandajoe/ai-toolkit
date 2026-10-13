# Independent Code Review

> **When**: You have local changes and want them reviewed and, by default, fixed ("review this branch and fix anything important"). "Review this; don't change anything" sets review-only; `--adversarial` stress-tests them for security holes, races and failure modes.
> **Produces**: One independent review (or the adversarial lanes), validated findings, applied fixes with verification, an optional delta pass, a `PROJECT.md` review record, and a review gate.

## Effect Boundary

Effect: `git_mutation`.

## Usage

```bash
review-code                  # branch-wide: committed + uncommitted vs base
review-code src/api/         # filter to path
review-code --committed | --uncommitted
review-code --review-only    # findings and record, no fixes
review-code --adversarial [--allow-degraded]   # red-team lanes instead of the independent review
```

## Procedure

Ensure a routing snapshot exists before any gate is recorded: `bin/aitk
project-state init --workflow review-code --complexity <classified> --size
<S|M|L|XL>` when none exists; an owning workflow's snapshot stays as it is
(`init` refuses a different workflow without `--replace`). This is
also the standalone entry for a change that fits no other workflow, such as a
chore, when the user asks for a PR: the classifier decides between the review
exception (zero-logic or micro-fix diffs) and the independent lane, and the
recorded gate is what lets `create-pr` proceed.

Follow [skills/review/references/local-review.md](../../review/references/local-review.md)
end to end: record the base, classify with
[classify-diff.md](../../review/references/classify-diff.md), preflight, run
the lanes `bin/aitk review plan` prints, validate every finding before fixing, fix accepted
findings, verify with `skills/verification-loop/SKILL.md`, run one delta
review only after substantive remediation, record the review gate with the
reviewer envelopes (`project-state gate --gate review --result <envelope>
--format block`) and paste the block it prints, and write the Review Record
to `PROJECT.md`.

## Adversarial Mode

`--adversarial` (and `review plan --adversarial`) replaces the independent
review with red-team lanes on the
[adversarial.md](../../review/references/adversarial.md) lens; scope, base,
validation, fixes, the delta pass and the gate are as above.

<!-- aitk-model-route:workflows.adversarial-primary -->
Launch the primary adversarial reviewer on `deep-review`, preferring the other
provider, with the scope, diff and full files only. With the other provider
unreachable the gate is `BLOCKED (degraded)`; only `--allow-degraded`,
recorded as `USER_DECISION`, lets a same-provider lane stand in, and the
report names it.
<!-- aitk-model-route:workflows.adversarial-second-opinion -->
For a security-sensitive diff or an explicit ask, launch the second vote on
`deep-review` on the provider the primary did not use, with the scope and diff
only, never the primary's findings. Under `--allow-degraded` with one provider
it is skipped and the report says so. Never claim two-lane coverage when one
lane ran.

Every finding needs a concrete failure scenario; drop findings whose
`file:line` is outside the diff. The gate block carries `Adversarial rating`,
which the parent derives from the accepted findings: `Critical` for an
accepted security `[major]`, `Vulnerable` for any other accepted `[major]`,
`Adequate` for `[minor]` only, `Hardened` for none.

## Contract

- Review judgment comes only from fresh lanes; the parent never reviews its
  own work (`rules/specialist-handoff.md`).
- Retry budget and review exceptions: `rules/gates.md`.
- Remediation is on by default when the user asked to review and fix; a
  review-only request records findings and the gate without editing.
- Suggest `--adversarial` when the classifier flags security sensitivity and
  the user did not already ask for it.
- Internal callers (`create-feature`, `fix-bug`, `fix-ci`, `tests`) own the
  next step after the gate; standalone runs end with the Review-Code Complete
  summary in `review/references/local-review.md`.
