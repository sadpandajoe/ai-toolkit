# Gates

One contract for every quality checkpoint: verification, RCA, plan
validation, review, phase exit. Safety and effect gates (publish, destructive,
production, PII scrub, failed preflight) are separate and hard, live in
`interfaces/contracts.json`, and no quality gate satisfies one.

## Outcomes

| Status | Meaning | Default action |
|---|---|---|
| `PASS` | Exit criteria met with evidence | Advance |
| `RETRY` | Current owner can still solve it | Same owner continues; attempt counted |
| `ESCALATE` | Current route or model is insufficient | Fresh or stronger specialist; possibly reclassify |
| `RECLASSIFY` | New evidence changed complexity, size, or shape | Update the routing snapshot upward, then re-enter the loop |
| `USER_DECISION` | A product, design, or scope choice only the user can make | Ask, with the adjudication package below |
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

An RCA passes when the mechanism is at file:line, no live alternative would
change the fix, and the regression check is named; otherwise it is `RETRY` or
`ESCALATE`, not a user decision.

## Retry Budget

Each reasoning unit (an RCA, a plan, a phase plan, an implementation slice, a
review round) gets one initial attempt plus one informed retry per owner.
`bin/aitk project-state gate` (and `bin/aitk verify --run`) enforces the
budget and the escalation ladder: record every failed attempt with `--status
RETRY --unit <unit>` (`--same-failure` when the reason repeats, `--editorial`
for an uncharged wording or path fix) and follow what it prints. An
`ESCALATE` goes to a fresh specialist on the other model family when
perspective is missing, or to the deep route when depth is missing; never keep
revising the same artifact past it.

## Verification Strength

Every verification gate names its strength:

| Strength | What ran | Gate outcome | Permits |
|---|---|---|---|
| `STRONG` | The failing or acceptance command itself, or a close equivalent, through `bin/aitk verify --run` (CI: `npm run lint`, `pytest tests/...`, `npm run build`) | `PASS` | Everything, including an authorized auto-commit and push |
| `PARTIAL` | Related checks on the changed code, not the exact command (CI: a type-check for a build failure, targeted unit tests for an integration failure) | `PASS (downstream: <verifier>)` when a downstream verifier such as CI on the PR will run the exact check; otherwise `RETRY` | Review and the diagnosis; never an auto-push |
| `WEAK` | Inspection only, no local execution (CI: an infra-only change, an env var that needs CI secrets) | `PASS (downstream: <verifier>)` only in `fix-ci` and `watch-pr`; otherwise `BLOCKED` | The diagnosis with the gap named; never an auto-push |

`--gate-strict` makes `WEAK` `BLOCKED` even with a downstream verifier.
Callers that commit or push on their own authority (`fix-bug`, `fix-ci`,
`watch-pr`) require `STRONG`: a `verify --run` record of the command, its exit
code, the output tail and the tree it ran on. `bin/aitk deliver` refuses
without one, and refuses a tree that changed after the run. A failed
verification never becomes `PASS` from code inspection alone, and a
downstream `PASS` is a reason to keep working, not to publish.

## Review Exceptions

A review gate may `PASS` without a reviewer only for a zero-logic diff
(formatting, import order, whitespace) or a passing micro-fix of three lines or
fewer; anything with logic gets one independent review. CORE impact disables
the exception: a TRIVIAL diff on a CORE path (auth,
payment, data integrity, the toolkit's routing or installer) is reviewed as
STANDARD.

## Independent Judgment

- **Single-source majors are verified before they block.** A `[major]` one
  lane raised passes `[minor]` only on a converging second lane, a reproduced
  failure or failing locking assertion, or a fresh other-family verifier's
  confirmation (`review/references/local-review.md`, Validate). That verifier
  also hears a `[major]` the parent wants to reject: the rejection stands only
  on `REFUTED` or `UNVERIFIABLE`, and `CONFIRMED` overrides it. A clean verdict
  counts only when the lane's verification list covers every changed file
  except generated files and lockfiles; skipped files get one coverage rerun.
- **Degraded lanes block security work.** When a lane cannot run on the other
  provider, a non-security diff proceeds on the same-provider fallback with
  `Independent review: same-provider` disclosed; a security-sensitive diff, a
  `--deep` review, or an adversarial review is `BLOCKED (degraded)` until the
  other provider is reachable or the user overrides with `--allow-degraded`
  (a recorded `USER_DECISION`).
- **A refusal is not an outage.** `model-run` reports a refusal as `refused`,
  with its category, apart from `unavailable`. A refused security or
  adversarial lens may reroute once to the other provider, recorded in the
  result and disclosed in the review record; it is not a downgrade. Any other
  refusal, or a second one, is `BLOCKED`.

## Continuation

A `PASS` gate is a phase transition, not a stop signal: the workflow continues
without asking, and a passing gate never ends the turn. The only pauses are
`USER_DECISION`, `BLOCKED`, and the hard safety and authorization gates.

## Block Shape

Paste the block the CLI prints: `bin/aitk verify --run` prints `## Gate:
verification`, and `bin/aitk project-state gate --format block` (with
`--evidence`, `--next`, `--strength`) prints the others. A review `PASS`
counts only with its evidence: `--result <model-run envelope>` for the
reviewer lanes, or `--exception zero-logic|micro-fix` on a passing
verification run. A `USER_DECISION` adds the adjudication package: the two or
three options, what each costs, the evidence that could not settle it, and a
recommendation.
