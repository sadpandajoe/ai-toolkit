# Phase Handoff Record

Written by the parent (control-plane) session into PROJECT.md's human-readable
section when one phase of a `MULTI_PHASE` plan closes and the next begins
(`skills/planning/references/plan-phase.md`'s completed-phase checkpointing
step). Unlike [workflow-checkpoint.md](workflow-checkpoint.md), this is not
rendered by the deterministic checkpoint API — the parent writes it directly,
so it carries no `{{placeholder}}` fields and no `aitk-checkpoint` marker.

```markdown
## Phase Handoff

- Phase: <N> — <phase name>
- Goal skill: <workflow>
- Closing gate: <gate name> — State: PASS | Evidence: <pointer, e.g. verify
  command output, commit range>
- Accepted artifact(s): <commit SHA(s) and/or files this phase landed>
- Next phase must know:
  - Decisions: <durable choices made this phase that constrain later phases>
  - Invariants: <global invariants from decompose-work.md still holding>
  - Open risks: <anything deferred or watched, or "none">
- Reclassification: <old → new complexity/size + reason, or "none">
- reasoning_attempts consumed: architecture=<n> phase_plan=<n> implementation=<n>
- Next step: <the exact bounded action that starts the next phase>
```

## Rules

- One record per phase transition; append, don't overwrite prior handoffs —
  they form the phase-by-phase history a resumed session reads.
- `Closing gate` cites the same gate name and state
  `skills/verification-loop/SKILL.md` already recorded — this is a pointer
  to that evidence, not a re-derivation of it.
- `Next phase must know` is the whole reason this template exists: keep it
  short but concrete enough that a fresh session (no memory of this phase)
  can resume from PROJECT.md and PLAN.md alone.
- `Reclassification` only has content when `rules/complexity-gate.md`'s
  `RECLASSIFY` fired during this phase; otherwise write `none`.
- Timestamps and phase numbering follow `PROJECT_TEMPLATE.md`'s frontmatter
  (`current_phase`) — a human-readable companion, not a replacement.
