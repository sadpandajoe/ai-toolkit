# Gates

Unified six-state gate contract for any workflow checkpoint that can pass,
fail, need a repeat attempt, need the user, or need reclassification. This
consolidates the execution-gate vocabulary previously split out into
`skills/action-gate/SKILL.md` (deleted in Wave D — folded into this contract
outright, not left dual-run) plus the review-status/iteration-stop/numeric-
threshold split still remaining in `rules/review-gate.md` (review status),
`rules/stop-rules.md` (iteration stop conditions), and `rules/scoring.md`
(numeric iteration threshold), into one vocabulary and one counting rule.

**Status: dual-run.** `skills/goals/{fix-bug,fix-ci,code-review,
address-feedback,test-pr}` and `skills/goals/cherry-pick` — this file's complete
set of migrated citers — now cite this contract's vocabulary at their own
checkpoints, translating their existing domain-specific verdicts into these
six states rather than reimplementing them. `review-gate.md`, `stop-rules.md`,
and `scoring.md` remain the ones actually enforcing review/iteration behavior
today for their own remaining callers — none of the citer goal skills invoke
`aitk.gates.decide_failure()` or replace their own gate/verdict logic with
this file's — so this is citation, not yet behavioral migration.

**Permanently out of scope.** Every other consumer of `rules/review-gate.md`
/`stop-rules.md`/`scoring.md` — this reaches well beyond the ensemble review
layer and the old workflow router (both separately dual-run pending their
own replacements): it includes the plan-domain reviewers
(`skills/review/references/{architecture,frontend,backend}.md`, read with
`lens_domain=plan`, plus `agents/codex/plan-validator.md`'s
implementation-feasibility lens), `skills/planning`'s plan-iteration and
finalize helpers, and `skills/testing`'s test-review helpers, several of
which are also called from code that already migrated (e.g. the Wave 5
planning helpers still route plan-level review through the old scoring
threshold). None of this is scheduled for migration by this rebuild. Deleting
`review-gate.md`/`stop-rules.md`/`scoring.md` is not safe while any
non-listed consumer depends on them, and given how broadly they're woven
through plan- and test-review, that may never fully clear under this plan's
current scope — treat the Wave 8 deletion bullet for these three files as
conditional on a future, separately-scoped migration of that surface, not as
a deletion this rebuild will necessarily reach.

## Canonical Vocabulary

The six states, and the pure function that decides RETRY vs ESCALATE, are
defined in `aitk/gates.py` (`GATE_STATES`, `decide_failure`). This rule is the
prose contract for that module; the module is the source of truth for the
state names and the counting rule.

| State | Meaning |
|-------|---------|
| `PASS` | Gate satisfied — proceed. |
| `RETRY` | First failure of this `kind` at this gate (or any mechanical failure — see below). Make one fix attempt, then re-run the same gate. |
| `ESCALATE` | A second consecutive **reasoning** failure at this gate. Autonomous, not user-facing: escalate one cost dimension (`rules/model-assignment.md`'s ladder — effort tier, then model tier, then XHigh) and retry once at the new tier before considering this checkpoint stuck. Only exhausting that ladder turns into `BLOCKED` or `USER_DECISION`. |
| `USER_DECISION` | Not a failure — a trade-off, scope question, or ambiguity only the user can resolve. |
| `BLOCKED` | Unresolved required findings remain, there is no ambiguity to ask about, and the cost-dimension ladder is exhausted. Cannot proceed until they're fixed. |
| `RECLASSIFY` | Evidence gathered during the gate shows the workflow's complexity classification (`rules/complexity-gate.md`) was wrong. Return to the Complexity Gate before continuing. |

Only `USER_DECISION` and `BLOCKED` are ever surfaced to the user as a stop.
`RETRY` and `ESCALATE` are internal to the workflow — `ESCALATE` changes how
the next attempt is made (higher cost tier), not who makes it.

## Block Format

Every gate checkpoint emits this block:

```markdown
## Gate
State: PASS / RETRY / ESCALATE / USER_DECISION / BLOCKED / RECLASSIFY
Reason: [one line]
Kind: mechanical / reasoning
Repeat count: N
```

`Repeat count` is the value `decide_failure()` returns alongside the state —
how many consecutive **reasoning** failures this gate has accumulated. It is
`0` for `PASS`, for `BLOCKED`/`USER_DECISION` (workflow-decided, not
`decide_failure`-decided), and for every `mechanical` failure, which never
advances the count. `Kind` is omitted when `State` is `PASS`, `BLOCKED`, or
`USER_DECISION`.

## Telemetry

Every gate checkpoint that emits the block above must also emit a `gate`
event via `skills/metrics-emit` (`gate` = this checkpoint's name, `state`,
`reason`, `kind`, and `repeat_count` = the same values just printed in the
block). This is not optional for a `rules/gates.md` citer, even though
`skills/metrics-emit` itself documents mid-run event types as additive — the
Gate Reliability signal in `rules/rule-maintenance.md` depends on every
checkpoint reporting, not a sample of them, and `skills/reflection` groups by
`(gate, reason)` — an omitted `reason` breaks that grouping. Emit it
immediately after the block, in the same step, not deferred to the
workflow's terminal summary.

When the same `(gate, reason)` pair produces a second consecutive
`RETRY`/`ESCALATE`, or the user explicitly redirects a gate's outcome, also
emit an `observation` event (`kind: gate-repeat` or `kind: user-correction`)
per `skills/metrics-emit` — this is the one signal `skills/reflection`
clusters on to propose a rule or skill change. A single first-time gate
failure does not warrant one; only a repeat or an explicit correction does.

## Repeat-Failure Counting Rule

A gate failing does not automatically mean stop. Every failure has a `kind`:

- **`mechanical`** — flaky infra, transient tooling, an environment hiccup;
  the approach wasn't wrong, the attempt just didn't run cleanly. Always
  `RETRY`. Never advances the reasoning-attempt count — retrying a
  mechanical failure is free.
- **`reasoning`** — the approach itself was wrong. The count advances on
  every reasoning failure regardless of whether this failure's reason
  matches the last one; there is no same-reason comparison. `1` is `RETRY`,
  `2` or higher is `ESCALATE`.

This is exactly `aitk.gates.decide_failure(previous_count, reason, kind=...)`
— do not reimplement the counting logic in prose elsewhere; call the
function or replicate its exact semantics. Judgment calls, not the workflow
guessing: classify a failure `mechanical` only when re-running the identical
attempt with no change could plausibly succeed (flaky test, network blip,
rate limit); anything that required or would require changing the approach
is `reasoning`.

## ESCALATE Is Autonomous

`ESCALATE` does not mean "ask the user." It means: the same reasoning
approach failed twice in a row, so retrying it a third time unchanged is not
useful — spend more, don't ask sooner. The calling workflow, on `ESCALATE`:

1. Escalate exactly one cost dimension per `rules/model-assignment.md`'s
   ladder — reasoning effort first, then model tier, then `XHigh` as the
   last rung. Never skip a rung or jump straight to the top.
2. Make one attempt at the new tier and re-run the same gate.
3. If that attempt also fails and the ladder is exhausted (already at the
   top rung), the gate resolves to `BLOCKED` (unresolved, no ambiguity to
   ask about) or `USER_DECISION` (a real trade-off or scope question) —
   whichever the failure actually is. If the ladder has a rung left,
   `ESCALATE` again and climb one more rung; do not surface to the user
   while a rung remains.

`ESCALATE` is a repeat count value from `decide_failure()`, not a separate
stop condition the workflow invents — the ladder-climbing above is what a
workflow does *in response to* seeing `ESCALATE`, not part of the function.

## Mapping From the Old Mechanisms

For migration reference, once a caller moves onto this contract:

- The now-deleted `skills/action-gate/SKILL.md`'s `Recommendation: Proceed automatically` → `PASS`; `Ask for approval` → `USER_DECISION`; `Stop and escalate` → `BLOCKED` (or `ESCALATE` if this is a repeat of the same escalation reason).
- `rules/review-gate.md`'s `Status: clean` / `micro-fix` → `PASS`; `Status: skipped` → `PASS` with the skip reason in `Reason`; `Status: blocked` → `BLOCKED`; `Status: user decision` → `USER_DECISION`.
- `rules/stop-rules.md`'s "same issue persists across two consecutive rounds" → `ESCALATE`; its other two stop conditions map to `PASS` (nitpicks only) and `USER_DECISION` (user decision required).
- `rules/scoring.md`'s 8/10 iteration threshold → superseded by the repeat-failure count, not a numeric score: a review that would have scored below 8 becomes `RETRY` on its first pass and `ESCALATE` on any second consecutive reasoning failure (not only a recurrence of the same deficiency), rather than iterating indefinitely toward a number.

## Continuation Rule

A `PASS` gate marks the completion of that checkpoint, not the end of the
workflow. The calling workflow must continue to its remaining steps —
further phases, commit, summary. Do not treat a passing gate as a signal to
stop or ask the user whether to continue.

## Scope

This rule defines the state vocabulary and block format. It does not define
per-workflow signal tables for what triggers each state — those stay owned by
the calling workflow reference, same as `rules/review-gate.md` and
`rules/complexity-gate.md` today.
