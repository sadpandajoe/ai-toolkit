# fix-bug Summary Template

Follow the structural rules in [../SKILL.md](../SKILL.md). Lead with whether the user's reported symptom is fixed — answer the ticket question, not the workflow detail.

```markdown
## Fix-Bug Complete
[1–2 lines answering the user's original question: what's fixed, confidence level]

### What was fixed
- [Specific behavior change — what the user or system does differently now]

### Verify manually
- [Things automated tests can't cover — live integration, UI rendering, environment-specific behavior]
- [Omit section entirely if everything is covered by automated tests]

### Key decisions
- [Non-obvious choices during investigation or fix — fix layer, scope boundary, alternatives rejected]
- [Omit for straightforward fixes with no meaningful alternatives]

### What to do next
- [Specific next action — PR link, CI re-run, merge step]

### Open risks
- [Anything uncertain or untested — omit section if none]

<details><summary>Technical details</summary>

- Root cause: [brief]
- Fix: [what changed]
- Files changed: [list]
- Review: Rounds [N] | Status [clean/blocked]

</details>
```
