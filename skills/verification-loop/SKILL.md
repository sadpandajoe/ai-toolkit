---
name: verification-loop
description: Use when a workflow needs to verify a phase, slice, or checkpoint against required/conditional criteria and turn the outcome into a PASS/RETRY/ESCALATE/USER_DECISION/BLOCKED/RECLASSIFY gate decision per rules/gates.md. Covers command-exit-status verification (tests, build, lint, reproduction) and judgment-based verification (review findings, RCA confidence, plan validation) through the same contract. Do NOT use for the Complexity Gate itself (rules/complexity-gate.md) or for a workflow's terminal summary (skills/metrics-emit's workflow-summary event).
---

# Verification Loop

## Before Starting

Read `rules/gates.md` first — it defines the six-state vocabulary, the block
format, the mechanical/reasoning counting rule, and the autonomous ESCALATE
ladder this skill applies at a real checkpoint. This skill is the contract
between "a workflow reached a checkpoint" and that rule; it does not
redefine the rule, and it never returns a different vocabulary.

## Required Context (inputs)

The calling workflow provides:

- `workflow` — the calling workflow's canonical identifier (e.g. `fix-bug`,
  `create-feature`) — passed through to `skills/metrics-emit`'s `gate` event
  as its `command` field.
- `phase` — the phase or slice this checkpoint belongs to (e.g. `implement`,
  `create-feature-phase-2-verify`). Distinct gate history per phase, per
  `create-feature`'s phase-scoping pattern — a fresh phase starts fresh
  history, it does not inherit the previous phase's repeat count.
- `gate` — the gate name to persist history under (e.g. `verify`, `review`,
  `rca-confidence`). Reuse the same name across calls for the same
  checkpoint so the repeat count is accurate; use a different name per
  distinct checkpoint so their histories don't overwrite each other.
- `required_criteria` — the checks that must all be satisfied for `PASS`
  (e.g. a command's exit status, "no HIGH/CRITICAL findings unresolved").
- `conditional_criteria` — checks that only apply given some condition the
  workflow already evaluated (e.g. "no regression in touched call sites" only
  when the diff touches a shared interface). Omit rather than force a
  criterion that doesn't apply this run.
- `accepted_artifact` — the plan, RCA, or decomposition this checkpoint
  verifies against, when one exists (path or identifier). A checkpoint with
  no accepted artifact (e.g. a first-pass lint gate) omits this.
- `changed_scope` — the files/areas actually touched this attempt, so
  verification stays scoped to what changed rather than re-litigating
  already-passed ground.
- `evidence` — whatever the workflow already gathered relevant to this
  checkpoint (command output, reviewer findings, RCA confidence signals).
  This skill does not re-derive evidence the calling workflow already has.
- `verification_command` — optional; when the checkpoint reduces to a single
  command's exit status, provide it and skip straight to Steps 1a below
  instead of judgment-based evaluation.
- `project_file` — path to the PROJECT.md carrying gate history (defaults to
  `PROJECT.md` in the current directory).

## Steps

1. Determine the checkpoint's outcome against `required_criteria` (and any
   applicable `conditional_criteria`), using `evidence` and, if given,
   `verification_command`:
   - **1a. Command-backed checkpoint:** run `verification_command`. Exit 0
     with `required_criteria` satisfied → `PASS`. Nonzero, or criteria
     unmet → a failure (continue to step 2).
   - **1b. Judgment-backed checkpoint:** evaluate `evidence` against
     `required_criteria`/`conditional_criteria` and `accepted_artifact`
     directly (e.g. review findings validated per `rules/severity.md`, RCA
     confidence against the RCA's own evidence bar). All required criteria
     satisfied → `PASS`. Any unresolved required criterion, with no
     ambiguity to ask about → `BLOCKED`. A real trade-off, scope question, or
     ambiguity only the user can resolve → `USER_DECISION`. Evidence
     surfaced during evaluation that contradicts the workflow's complexity
     classification (`rules/complexity-gate.md`) → `RECLASSIFY`, and stop —
     return to the Complexity Gate before continuing this checkpoint.
   - `BLOCKED`, `USER_DECISION`, and `RECLASSIFY` skip the retry machinery
     below entirely; go straight to Step 5 with that state.
2. On `PASS`: persist and stop iterating — a `PASS` here is a checkpoint, not
   the end of the calling workflow (`rules/gates.md`'s Continuation Rule):
   ```
   aitk gate-state set --file <project_file> --gate <gate> --state PASS --reason "<summary>" --count 0
   ```
   Go to Step 5.
3. On a failure, classify its `kind` (`rules/gates.md`'s Repeat-Failure
   Counting Rule): `mechanical` only if re-running the identical attempt with
   no change could plausibly succeed (flaky test, transient timeout, rate
   limit); otherwise `reasoning`. Then read this gate's prior recorded
   history, scoped to the current `phase`:
   ```
   aitk project-state --file <project_file>
   ```
   Take `.gates.<gate>` from the payload. If absent (including at the start
   of a new `phase`), `previous_count` is `0`.
4. Decide the next state via `aitk.gates.decide_failure(previous_count,
   reason, kind=<kind>)` and persist it:
   ```
   aitk gate-state set --file <project_file> --gate <gate> --state <state> --reason "<reason>" --count <count> --kind <kind>
   ```
   - `RETRY`: make one fix attempt scoped to `changed_scope`, then re-run
     this skill against the same `gate` and `phase`.
   - `ESCALATE`: this is autonomous, not a stop — apply `rules/gates.md`'s
     ESCALATE Is Autonomous ladder (bump effort → move to the deep-tier
     route → xhigh on the deep-tier route, one rung per `ESCALATE`), make one
     attempt at the new tier, and re-run this skill against the same `gate`
     and `phase`. Only once the ladder is exhausted and the retried attempt
     still fails does the checkpoint become `BLOCKED` or `USER_DECISION` —
     re-enter at Step 1b's judgment path to decide which.
5. Emit the Gate block from `rules/gates.md`:
   ```markdown
   ## Gate
   State: PASS / RETRY / ESCALATE / USER_DECISION / BLOCKED / RECLASSIFY
   Reason: [one line]
   Kind: mechanical / reasoning   [omit for PASS, BLOCKED, USER_DECISION]
   Repeat count: N
   Evidence: [pointer to the evidence this decision was made from]
   Next action: [what happens next: re-run gate <gate>; escalate to <route>; surface to user; return to Complexity Gate]
   ```
   Immediately after, in this same step, emit the `gate` event via
   `skills/metrics-emit` per `rules/gates.md`'s Telemetry section —
   `command: <workflow>`, `gate: <gate>`, `state: <state>`, `reason:
   <reason>`, `kind: <kind>` (omit `reason`/`kind`/`repeat_count` for
   `PASS`), `repeat_count: <count>`. Do not defer this to the calling
   workflow's terminal `workflow-summary` event; it is a separate event per
   checkpoint, not a substitute for one.

## Output

```markdown
## Gate
State: PASS / RETRY / ESCALATE / USER_DECISION / BLOCKED / RECLASSIFY
Reason: [one line]
Kind: mechanical / reasoning
Repeat count: N
Evidence: [pointer]
Next action: [what happens next]
```

## BATCHED shape

For `BATCHED` execution (`rules/complexity-gate.md`'s execution shapes),
each slice or wave runs this loop on its own scope and records its own
gate — same as any other checkpoint above. After the last wave, run one
additional AGGREGATE verification over the whole change set (a full test
run plus review of the combined diff, not just the final wave's diff) using
its own `gate` name (e.g. `<workflow>-verify-aggregate`) — never the same
name a per-wave call already used, per this skill's own Notes on gate
naming ("a fast local run and a slower CI run still gives each its own
`gate` name"); reusing a wave's gate name would make the aggregate inherit
that wave's repeat-count history instead of starting its own. A slice or
wave `PASS` never substitutes for the aggregate — only the aggregate's own
`PASS` closes the implementation gate for a `BATCHED` unit.

## Notes

- Only `USER_DECISION` and `BLOCKED` are ever handed back to the user as a
  stop. `PASS` continues the workflow; `RETRY` and `ESCALATE` are both
  resolved autonomously by the calling workflow before this skill is called
  again — `ESCALATE` changes cost tier, it does not change who acts.
  `RECLASSIFY` returns control to the Complexity Gate, still without a user
  stop unless the Complexity Gate itself requires one.
- Gate history is per `(gate, phase)`, not just per `gate` name — a
  multi-phase workflow's phase 2 does not inherit phase 1's repeat count
  (`skills/goals/create-feature/SKILL.md`'s phase-scoping pattern). A
  workflow with more than one verification checkpoint within a phase (e.g. a
  fast local run and a slower CI run) still gives each its own `gate` name.
- This skill decides all six states, not just three — a judgment-backed
  checkpoint (review findings, RCA confidence, plan validation) is as much
  in scope as a command's exit status. The `verification_command` input is
  an optional shortcut for the command-backed case, not the boundary of the
  skill.
