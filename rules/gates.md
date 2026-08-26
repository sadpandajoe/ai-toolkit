# Gates

Unified six-state gate contract for any workflow checkpoint that can pass,
fail, need a repeat attempt, need the user, or need reclassification. This
consolidates the behavior currently split across `skills/action-gate/SKILL.md`
(execution gate), `rules/review-gate.md` (review status), `rules/stop-rules.md`
(iteration stop conditions), and `rules/scoring.md` (numeric iteration
threshold) into one vocabulary and one counting rule.

**Status: dual-run.** Nothing currently routes through this rule. The four
files above remain authoritative until each caller migrates and the old
mechanisms are deleted (see the plan's Wave 8). This file exists so the
contract can be reviewed and cited before anything depends on it.

## Canonical Vocabulary

The six states, and the pure function that decides RETRY vs ESCALATE, are
defined in `aitk/gates.py` (`GATE_STATES`, `decide_failure`). This rule is the
prose contract for that module; the module is the source of truth for the
state names and the counting rule.

| State | Meaning |
|-------|---------|
| `PASS` | Gate satisfied — proceed. |
| `RETRY` | Gate failed once for this reason. Make one fix attempt, then re-run the same gate. |
| `ESCALATE` | The same reason failed twice consecutively. Do not iterate again on the same approach — stop and surface the repeated failure to the user instead of silently retrying. |
| `USER_DECISION` | Not a failure — a trade-off, scope question, or ambiguity only the user can resolve. |
| `BLOCKED` | Unresolved required findings remain and there is no ambiguity to ask about. Cannot proceed until they're fixed. |
| `RECLASSIFY` | Evidence gathered during the gate shows the workflow's complexity classification (`rules/complexity-gate.md`) was wrong. Return to the Complexity Gate before continuing. |

## Block Format

Every gate checkpoint emits this block:

```markdown
## Gate
State: PASS / RETRY / ESCALATE / USER_DECISION / BLOCKED / RECLASSIFY
Reason: [one line]
Repeat count: N
```

`Repeat count` is the value `decide_failure()` returns alongside the state —
how many consecutive times this same reason has failed this gate. It is `0`
or omitted when `State` is `PASS`.

## Repeat-Failure Counting Rule

A gate failing does not automatically mean stop. Track the previous failure
reason and repeat count for this gate:

- No prior failure, or a different reason than last time → `RETRY`, count resets to `1`.
- Same reason as last time → count increments; `1` is `RETRY`, `2` or higher is `ESCALATE`.

This is exactly `aitk.gates.decide_failure()` — do not reimplement the
counting logic in prose elsewhere; call the function or replicate its exact
semantics.

## Mapping From the Old Mechanisms

For migration reference, once a caller moves onto this contract:

- `skills/action-gate/SKILL.md`'s `Recommendation: Proceed automatically` → `PASS`; `Ask for approval` → `USER_DECISION`; `Stop and escalate` → `BLOCKED` (or `ESCALATE` if this is a repeat of the same escalation reason).
- `rules/review-gate.md`'s `Status: clean` / `micro-fix` → `PASS`; `Status: skipped` → `PASS` with the skip reason in `Reason`; `Status: blocked` → `BLOCKED`; `Status: user decision` → `USER_DECISION`.
- `rules/stop-rules.md`'s "same issue persists across two consecutive rounds" → `ESCALATE`; its other two stop conditions map to `PASS` (nitpicks only) and `USER_DECISION` (user decision required).
- `rules/scoring.md`'s 8/10 iteration threshold → superseded by the repeat-failure count, not a numeric score: a review that would have scored below 8 becomes `RETRY` on its first pass and `ESCALATE` only if the *same* deficiency recurs, rather than iterating indefinitely toward a number.

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
