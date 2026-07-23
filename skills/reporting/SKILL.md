---
name: reporting
description: Use for standardized end-to-end summaries and continuation checkpoints. Do NOT use as the source of workflow behavior or for transient progress updates.
---

# Reporting

## Before Starting

Read sibling rules, lessons, and gotchas when present.

This skill owns shared output shape only. Canonical workflow references own
procedure, fields, and stop conditions.

## Terminal Summary

1. Lead with the user-visible outcome, not rounds or process.
2. State results and evidence, not effort.
3. End with concrete next actions after the workflow.
4. Do not suggest phases the workflow already completed.
5. Put audit-only details in a collapsed details section.
6. Omit empty sections and scale length to remaining risk.

```markdown
## <Workflow Name> Complete
[Outcome in one or two lines]

### <Workflow-owned result section>
- ...

### What to do next
- ...
```

## Durable Checkpoint

The deterministic checkpoint API is the only writer of the machine block in
`PROJECT.md`. It renders [workflow-checkpoint.md](templates/workflow-checkpoint.md)
from the selected v2 contract, validates phase transitions, increments
generation, and records pending/applied effect operations.

Human-readable status follows the machine block:

```markdown
### Workflow Status
- Workflow: <name and arguments>
- Phase: <phase>
- Active plan: PLAN.md | none
- Next action: <bounded action>
- Blockers: <none or list>
```

Workflow-specific checkpoint templates may add compact human fields, but they
never redefine the machine block or command syntax. Timestamps use ISO format.

When adding a workflow, add a summary template only when it needs structured
domain output. Add human checkpoint details only when the generic status would
lose material resume context; the v2 contract and deterministic checkpoint API
remain authoritative.
