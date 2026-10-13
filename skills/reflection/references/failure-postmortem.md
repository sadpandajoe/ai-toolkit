# Failure Postmortem

Use for `reflect failure`.

Record a structured postmortem after a workflow fails or produces a bad outcome. The output is a feedback memory with enough context to prevent recurrence.

## Gather

From the user, git log, `PROJECT.md` and the session: what failed, what was
expected and what happened, and whether it was a tooling, process or knowledge
gap.

## Memory Shape

Filename: `feedback_failure_{snake_case_topic}.md`

```markdown
---
name: {descriptive name}
description: {one-line summary of what went wrong}
type: feedback
---

## What happened
{Factual description: command, inputs, expected vs actual outcome}

## What the system decided
{Which gate, skill, or step made the wrong call — with evidence}

## What it should have decided
{The correct action and why}

## Prevention
**Why:** {Root cause — process gap, missing signal, wrong threshold, etc.}
**How to apply:** {Specific rule, gate, or skill to adjust — reference by file path}
```

Update `MEMORY.md` index after writing, and queue the failure for `reflect
observations` with `bin/aitk observe --kind user-correction --detail "<one
sentence>" --evidence <memory file>`.

If the postmortem points to a clear rule or skill fix, suggest the specific change. Do not auto-apply it.
