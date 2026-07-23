# Failure Postmortem

Use for `reflect failure`.

Record a structured postmortem after a workflow fails or produces a bad outcome. The output is a feedback memory with enough context to prevent recurrence.

## Gather

Ask or infer:
- which command or workflow failed
- expected outcome
- actual outcome
- whether it was a tooling issue, process gap, or knowledge gap

Investigate current state for evidence:
- recent git log for commits/reverts
- PROJECT.md for last recorded status
- conversation context for gate decisions, review scores, or errors

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

Update `MEMORY.md` index after writing.

If the postmortem points to a clear rule or skill fix, suggest the specific change. Do not auto-apply it.
