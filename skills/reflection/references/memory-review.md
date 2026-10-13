# Memory Review

Use for `reflect review` and `reflect prune`.

## Review Flow

Read every memory file and check each against current rules and the codebase:
does it duplicate or contradict a rule, has a newer memory superseded it, and
does every path it names still exist?

```markdown
## Memory Review

### Keep
- `feedback_summary_style.md` — still relevant, no conflicts

### Update
- `reference_shortcut_api.md` — path changed to `skills/shortcut/references/fetch.md`

### Prune candidates
- `feedback_old_pattern.md` — superseded by `rules/universal.md`
```

Ask for confirmation before applying updates or deletions.

## Prune Flow

Present the prune candidates from the review with reasons, and ask for
confirmation per deletion. For each confirmed deletion, delete the memory file
and remove its entry from `MEMORY.md`.

Do not delete memories just because they are old. They must also be inaccurate, redundant, contradictory, or no longer useful.
