# create-feature Summary Template

Follow the structural rules in [../SKILL.md](../SKILL.md). Lead with whether acceptance criteria are met (especially when the user provided a ticket).

```markdown
## Create-Feature Complete
[1–2 lines: what was built, whether acceptance criteria are met]

### What was built
- [Specific behavior/UX flow — what the user or system does differently now]

### Verify manually
- [Things automated tests can't cover — live integration, UI rendering, permissions]
- [Omit section entirely if everything is covered by automated tests]

### Key decisions
- [Decisions made during planning that shaped the implementation]

### What to do next
- [Specific next action — the next phase's PR in roadmap order, deploy step, remaining slices]
- [Draft PR link and, when ready, promotion to review (the user's call); MULTI_PHASE: the shared draft PR (or one per phase branch, in delivery order), or the pushed commits awaiting a PR (`--no-pr`)]

### Open risks
- [Anything uncertain or untested — omit section if none]

<details><summary>Technical details</summary>

- Files changed: [list]
- Review: per-unit gates [PASS ×N] | Integrated review [gate, lane | not applicable]
- Delivery: [draft PR #n | draft PR per phase branch #… | no PR (--no-pr) | pushed — awaiting PR request]

</details>
```
