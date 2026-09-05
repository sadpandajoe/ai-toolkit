# Validate Plan

One independent validator, one informed revision, then adjudicate. This
replaces the multi-reviewer, numeric-threshold plan loop: a plan is not
improved by a third round of the same reviewers.

## When

- Every COMPLEX decomposition (`decomposition` mode) before the first phase.
- Every COMPLEX phase plan or COMPLEX SINGLE_PHASE plan (`phase-plan` mode).
- Every COMPLEX bug-fix plan (`fix-plan` mode) against its accepted RCA.
- STANDARD plans skip validation; the verification loop is their gate. Run it
  anyway when the parent's own confidence is `LOW` or the user asked for a plan
  review.

## Dispatch

<!-- aitk-model-route:planning.validate -->
Launch one fresh validator worker on `review` (default) or `deep-review` (only
after a `review`-route validation returned `REPLAN`, or for security, migration,
or cross-service decompositions). Prefer the other provider. The prompt carries
the mode, the plan section verbatim, the accepted decomposition's invariants
for `phase-plan` mode, the accepted RCA for `fix-plan` mode, and the routing
snapshot line; never earlier validation rounds unless this is the informed
revision, in which case include the previous findings and what changed. The
worker receives its contract inline from the route runner.

## Consume the verdict

- `APPROVE` → gate `PASS`; record it and proceed to implementation.
- `CHANGES_REQUIRED` → the same planner makes one informed revision, then
  re-validate once. Editorial items are patched by the parent without a
  re-validation round.
- `REPLAN` → gate `ESCALATE`: restart the unit on a stronger or different
  route with the validator's evidence, or surface a `USER_DECISION` when the
  disagreement is a product or design choice.
- Second `CHANGES_REQUIRED` on the same reasoning failure → `ESCALATE`, per
  the retry budget in `rules/gates.md`. Do not iterate further.

Record the outcome with `bin/aitk project-state gate --gate plan --status
<PASS|RETRY|ESCALATE|USER_DECISION> --unit <decomposition|phase-name>` and
append the verdict and blocking findings to `PLAN.md` under
`## Validation: <unit>`. Findings, not scores, are the persistent artifact.
