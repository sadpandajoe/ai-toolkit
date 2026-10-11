---
name: reporting
description: Use for standardized end-to-end summaries and continuation checkpoints. Do NOT use as the source of workflow behavior or for transient progress updates.
---

# Reporting

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

The CLI renders workflow status (`bin/aitk project-state show`) and
`bin/aitk checkpoint` writes the machine block; do not hand-edit either.
