---
name: verification-loop
description: Use when a workflow needs to run a verification command (tests, build, lint, reproduction) and turn its pass/fail outcome into a PASS/RETRY/ESCALATE gate decision per rules/gates.md. Do NOT use for gates whose decision comes from judgment rather than a command's exit status (classification, review findings, RCA confidence) — this skill only covers the run-a-command-and-decide-RETRY-vs-ESCALATE case.
---

# Verification Loop

## Before Starting

Read `rules/gates.md` first — it defines the six-state vocabulary, the block
format, and the repeat-failure counting rule this skill applies to a real
verification command. This skill is the thin bridge between "a command
passed or failed" and that contract; it does not redefine the rule.

## Required Context

The calling workflow provides:

- `gate` — the gate name to persist history under (e.g. `verify`, `ci-verify`). Reuse the same name across calls for the same checkpoint so the repeat count is accurate; use a different name per distinct checkpoint (verification vs review vs RCA) so their histories don't overwrite each other.
- `command` — the verification command to run.
- `project_file` — path to the PROJECT.md carrying gate history (defaults to `PROJECT.md` in the current directory).

## Steps

1. Run `command`.
2. If it passes, persist a clean state and stop iterating — a `PASS` here is
   a checkpoint, not the end of the calling workflow (see `rules/gates.md`'s
   Continuation Rule):
   ```
   aitk gate-state set --file <project_file> --gate <gate> --state PASS --reason "<summary>" --count 0
   ```
3. If it fails, read this gate's prior recorded history before deciding
   anything:
   ```
   aitk project-state --file <project_file>
   ```
   Take `.gates.<gate>` from the payload. If absent, `previous_reason` is
   `None` and `previous_count` is `0`.
4. Decide the next state using `rules/gates.md`'s counting rule (implemented
   in `aitk.gates.decide_failure`): the same failure reason as last time
   increments the count (`1` = `RETRY`, `2` or higher = `ESCALATE`); a new or
   first-time reason resets the count to `1` (`RETRY`).
5. Persist the decision:
   ```
   aitk gate-state set --file <project_file> --gate <gate> --state <state> --reason "<reason>" --count <count>
   ```
6. Emit the Gate block from `rules/gates.md`:
   ```markdown
   ## Gate
   State: PASS / RETRY / ESCALATE
   Reason: [one line]
   Repeat count: N
   ```
7. On `RETRY`: make one fix attempt, then re-run this skill against the same
   `gate`. On `ESCALATE`: stop iterating on the same approach — surface the
   repeated failure to the user instead of retrying again.

## Output

```markdown
## Gate
State: PASS / RETRY / ESCALATE
Reason: [one line]
Repeat count: N
```

## Notes

- This skill only ever decides `PASS`, `RETRY`, or `ESCALATE` — a command's
  exit status can't produce `USER_DECISION`, `BLOCKED`, or `RECLASSIFY`.
  Those come from workflow-specific judgment; the calling workflow decides
  and persists them directly against `aitk gate-state set`, not through this
  skill.
- Gate history is per `gate` name, not per workflow — a workflow with more
  than one verification checkpoint (e.g. a fast local run and a slower CI
  run) should give each its own `gate` name.
