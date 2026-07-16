# Memory Review

Use for `reflect review` and `reflect prune`.

## Review Flow

Read all memory files.

Assess each memory:
- Is it still accurate given current rules and codebase state?
- Does it duplicate or contradict a rule in `rules/`?
- Has it been superseded by a newer memory?
- Is any referenced file/path/resource still valid?

Present findings:

```markdown
## Memory Review

### Keep
- `feedback_summary_style.md` — still relevant, no conflicts

### Update
- `reference_shortcut_api.md` — path changed to `skills/shortcut/references/fetch.md`

### Prune candidates
- `feedback_old_pattern.md` — superseded by `rules/context-management.md`
```

Ask for confirmation before applying updates or deletions.

## Prune Flow

Identify candidates:
- stale entries (> 30 days without update)
- duplicates
- contradictions with current rules
- references to missing files/paths

Present the prune list with reasons. Ask for confirmation per deletion.

For confirmed deletions:
1. Delete the memory file.
2. Remove its entry from `MEMORY.md`.

Do not delete memories just because they are old. They must also be inaccurate, redundant, contradictory, or no longer useful.
