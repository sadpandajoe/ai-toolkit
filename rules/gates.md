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

## When a Decision Is the User's

Answer `USER_DECISION` instead of choosing when any of these hold:

- Two or more root causes or fix interpretations are plausible and the fix
  differs materially between them.
- The fix changes product or runtime behavior in a way a user would notice.
- Continuing would widen scope beyond the failing surface or the accepted
  slice.
- Branch, environment, or validation assumptions are ambiguous and the
  evidence cannot settle them.
- A finding survived its delta review and the remaining disagreement is a
  trade-off, not a fact.

Confidence below 8/10 on the current hypothesis is not by itself a user
decision; it is a `RETRY` or an `ESCALATE` to a specialist.

## Retry Budget

Each reasoning unit (an RCA, a plan, a phase plan, an implementation slice, a
review round) gets one initial attempt plus one informed retry per owner.
Record every failed attempt with `bin/aitk project-state gate --status RETRY
--unit <unit>`; the runtime turns the request into `ESCALATE` when the unit is
exhausted or the same failure repeats. Never keep revising the same artifact
past that point.

- Same gate fails once for a reason → `RETRY`.
- Same gate fails twice for the same reason → `ESCALATE`.
- Editorial fixes (a missing path, a wording gap, a rollback note) do not
  consume the budget: record them with `--editorial`. Reasoning failures
  (invalid architecture, disproven assumption, competing designs, incompatible
  contract) do.
- `USER_DECISION` and `BLOCKED` are recorded but never charged; waiting is not
  an attempt.

### The escalation ladder

An `ESCALATE` hands the unit to the next owner and gives that owner a fresh
budget; the snapshot records the step in `escalations`. Escalate one dimension
at a time: more effort when depth is missing, a different model when
perspective is missing, `xhigh` only when both stayed unresolved. The runtime
caps the ladder at three escalations per unit and answers `USER_DECISION`
after that, so the RCA ladder (parent retry → RCA specialist `REVISE` →
`deep-rca` → the user) is recorded on one unit without ever overflowing it.

`RECLASSIFY` resets the named unit's counters (every unit when none is named)
because the problem itself changed; then the classification moves upward in the
snapshot and the loop re-enters.

## Verification Strength

Every verification gate names its strength. The strength decides what the
outcome permits, and it is the one vocabulary every workflow uses:

| Strength | What ran | Gate outcome | Permits |
|---|---|---|---|
| `STRONG` | The failing or acceptance command itself (or a close equivalent) ran locally and passes | `PASS` | Everything, including an authorized auto-commit and push |
| `PARTIAL` | Related checks that exercise the changed code, not the exact command | `PASS (downstream: <verifier>)` when a downstream verifier such as CI on the PR will run the exact check; otherwise `RETRY` | Continue to review and present the diagnosis; never an auto-push |
| `WEAK` | Inspection only, no local execution | `PASS (downstream: <verifier>)` only with a downstream verifier and only in `fix-ci` and `watch-pr`; otherwise `BLOCKED` | Present the diagnosis with the gap named; never an auto-push |

`--gate-strict` removes the `WEAK` carve-out: `WEAK` is `BLOCKED` even with a
downstream verifier. Callers that commit or push on their own authority
(`fix-bug`, `fix-ci`, `watch-pr`) require `STRONG`; a downstream `PASS` is a
reason to keep working, not a reason to publish.

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
The exception is unavailable when the impact assessment is CORE: a TRIVIAL diff
on a CORE path (auth, payment, data integrity, the toolkit's routing or
installer) is reviewed as STANDARD.

## Independent Judgment

- **Single-source majors are verified before they block.** A `[major]` that
  only one lane raised is worth investigating but never blocks on the parent's
  reading alone. Before it is accepted past `[minor]`, either a second
  independent lane converged on it (the second-family lane runs by default on
  COMPLEX and CORE-impact diffs), or one fresh verifier on the other model
  family confirmed it with a concrete failure scenario
  (`review/references/local-review.md`, Validate). A refuted finding is
  recorded as rejected with the verifier's evidence.
- **Degraded lanes block security work.** When the independent or adversarial
  lane cannot run on the other provider, a non-security diff proceeds on the
  same-provider fallback with `Independent review: same-provider` disclosed.
  A security-sensitive diff, a `--deep` review, or `review-code-adversarial`
  does not: the gate is `BLOCKED (degraded)` until the other provider is
  reachable or the user overrides with `--allow-degraded`, which is recorded
  as a `USER_DECISION`.

## Continuation

A `PASS` gate is a phase transition, not a stop signal. The workflow continues
to its next step without asking whether to continue; a passing review, RCA, or
verification gate never ends the turn. The only pauses are `USER_DECISION`,
`BLOCKED`, and the hard safety and authorization gates in
`interfaces/contracts.json`.

## Two Records, One Truth

The routing snapshot (`bin/aitk project-state gate`) records every gate
outcome and owns the attempt budget and ladder. The checkpoint machine block
(`bin/aitk checkpoint`) records phase edges and effect reservations for
durable workflows and lists `verification` and `review` as preconditions for
effects. They never disagree by construction: a workflow records the outcome
in the snapshot first, and an effect that `interfaces/contracts.json` gates on
`verification` or `review` may be reserved only while the snapshot shows that
gate `PASS`. A workflow without a snapshot has no gate history, so every
workflow that records a gate runs `project-state init` first, including
standalone `review-plan` and `fix-ci`.

## Block Shape

```markdown
## Gate: <verification | rca | plan | review | phase-exit>
Status: PASS | RETRY | ESCALATE | RECLASSIFY | USER_DECISION | BLOCKED
Attempt: <n>/2 on <unit> (escalation <k>/3 when > 0)
Strength: STRONG | PARTIAL | WEAK          # verification gates only
Evidence: <command or check and result, one line>
Next: <bounded next action, or the decision the user must make>
```

For `USER_DECISION`, add the adjudication package: the two or three options,
what each costs, the evidence that could not settle it, and a recommendation.
