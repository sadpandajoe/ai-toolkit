# Gates

One gate contract for every quality checkpoint in a workflow: verification,
RCA, plan validation, review, phase exit. Safety and effect gates (publish,
destructive, production, PII scrub, failed preflight) are separate, hard, and
live in `interfaces/contracts.json`; a passing quality gate never satisfies one
of those.

## Outcomes

| Status | Meaning | Default action |
|---|---|---|
| `PASS` | Exit criteria met with evidence | Advance |
| `RETRY` | Current owner can still solve it | Same owner continues; attempt counted |
| `ESCALATE` | Current route or model is insufficient | Fresh or stronger specialist; possibly reclassify |
| `RECLASSIFY` | New evidence changed complexity, size, or shape | Update the routing snapshot upward, then re-enter the loop |
| `USER_DECISION` | A product, design, or scope choice only the user can make | Ask, with the compact adjudication package below |
| `BLOCKED` | Environment or external dependency prevents progress | Record evidence and stop this path |

Only `USER_DECISION`, `BLOCKED`, and the hard safety gates involve the user.
`RETRY`, `ESCALATE`, and `RECLASSIFY` are automatic.

## Retry Budget

Each reasoning unit (an RCA, a plan, a phase plan, an implementation slice, a
review round) gets one initial attempt plus one informed retry. Record every
failed attempt with `bin/aitk project-state gate --status RETRY --unit <unit>`;
the runtime turns the request into `ESCALATE` when the unit is exhausted or the
same failure repeats. Never keep revising the same artifact past that point.

- Same gate fails once for a reason → `RETRY`.
- Same gate fails twice for the same reason → `ESCALATE`.
- Editorial fixes (a missing path, a wording gap, a rollback note) do not
  consume the budget. Reasoning failures (invalid architecture, disproven
  assumption, competing designs, incompatible contract) do.
- Escalate one dimension at a time: more effort when depth is missing, a
  different model when perspective is missing, `xhigh` only when both stayed
  unresolved.

## Evidence Rule

A failed verification never becomes `PASS` from code inspection alone. `PASS`
names the command or check that ran and its result. When the check cannot run
locally and a downstream verifier will exercise the change (CI on the PR), say
`PASS (downstream: <verifier>)` and keep the no-push-after-failed-verification
invariant.

## Review Exceptions

A review gate may `PASS` without a reviewer only for a zero-logic diff
(formatting, import order, whitespace) or a micro-fix of three lines or fewer
whose relevant checks pass. Anything with logic gets one independent review.

## Block Shape

```markdown
## Gate: <verification | rca | plan | review | phase-exit>
Status: PASS | RETRY | ESCALATE | RECLASSIFY | USER_DECISION | BLOCKED
Attempt: <n>/2 on <unit>
Evidence: <command or check and result, one line>
Next: <bounded next action, or the decision the user must make>
```

For `USER_DECISION`, add the adjudication package: the two or three options,
what each costs, the evidence that could not settle it, and a recommendation.
