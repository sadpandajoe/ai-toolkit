# Memory Basics

Use for `reflect`, `reflect add`, and `reflect list`.

## Add Flow

If no inline content is provided, ask what should be remembered.

Classify memory type:
- `feedback` — behavioral correction or confirmed approach
- `reference` — external resources or operational patterns
- `project` — project-specific context, deadlines, team decisions
- `user` — personal role, preferences, knowledge level

Filename: `{type}_{snake_case_topic}.md`.

Before writing, read `MEMORY.md` and scan existing memory files for overlap. If a duplicate exists, ask whether to update the existing memory or create a new one.

Memory shape:

```markdown
---
name: {descriptive name}
description: {one-line description}
type: {feedback|reference|project|user}
---

{Statement of the pattern, fact, or preference}

**Why:** {Rationale}

**How to apply:** {Concrete guidance}
```

Update `MEMORY.md` index after writing.

## List Flow

Read `MEMORY.md`, then each linked memory file.

Compute staleness from file modification time:
- Fresh: < 7 days
- Aging: 7-30 days
- Stale: > 30 days

Display:

```markdown
| File | Type | Description | Age | Status |
|------|------|-------------|-----|--------|
| feedback_example.md | feedback | Example description | 12d | Aging |
```

List is read-only.
