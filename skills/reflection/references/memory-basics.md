# Memory Basics

Use for `reflect`, `reflect add`, and `reflect list`.

## Add Flow

If no inline content is provided, ask what should be remembered.

Classify memory type:
- `feedback` — behavioral correction or confirmed approach
- `reference` — external resources or operational patterns
- `project` — project-specific context, deadlines, team decisions
- `user` — personal role, preferences, knowledge level

Filename: `{type}_{snake_case_topic}.md`, in the provider's `memory_store`
directory (Claude's auto-memory directory, or `.ai-toolkit/memory/` on Codex).

Before writing, read `MEMORY.md` and scan existing memory files for overlap. If a duplicate exists, ask whether to update the existing memory or create a new one.

Use the frontmatter and body shape in
[failure-postmortem.md](failure-postmortem.md) with `type` set to the class
above: a statement of the pattern, fact or preference, then **Why:** and
**How to apply:**. Update the `MEMORY.md` index after writing.

## List Flow

Read `MEMORY.md`, then each linked memory file.

Show each memory's age from its file modification time:

```markdown
| File | Type | Description | Age |
|------|------|-------------|-----|
| feedback_example.md | feedback | Example description | 12d |
```

List is read-only.
