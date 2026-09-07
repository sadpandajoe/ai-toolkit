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
- [MULTI_PHASE: list the PRs per phase in delivery order, the prepared commits awaiting publish authorization, or the single-PR opt-out and its reason]

### Open risks
- [Anything uncertain or untested — omit section if none]

<details><summary>Technical details</summary>

- Files changed: [list]
- Review: per-unit gates [PASS ×N] | Integrated review [gate, lane | not applicable]
- Delivery: [PR per phase #… | single PR]

</details>
```
