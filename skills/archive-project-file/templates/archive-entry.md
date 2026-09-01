# Archive Entry Template

Append this block to PROJECT_ARCHIVE.md. Preserve any earlier entries above; do not rewrite history.

```markdown
---

## Archive: [Phase Name] — [YYYY-MM-DD]

### Summary
- **Timeline**: [Start] to [End]
- **Goal**: [What we tried to accomplish]
- **Outcome**: [What actually happened]
- **Key Commits**: [sha1, sha2]

### v2 State
- **Workflow**: [workflow name from the `aitk-checkpoint:v1` block]
- **Final gate states**: [gate: PASS/RETRY/ESCALATE/... per `aitk-gate:v1`, or "none recorded"]
- **reasoning_attempts**: architecture=[n] phase_plan=[n] implementation=[n]
- **Reclassifications**: [old → new complexity/size + reason, or "none"]

### Key Decisions
- [Decision 1 and why]
- [Decision 2 and why]

### Lessons Learned
- [Learning 1]
- [Learning 2]

---

### Full Details

[Paste archived sections here verbatim]
```

## Rules

- Date in `YYYY-MM-DD` format for sort/grep friendliness.
- Summary fields are short — one line each. Detail goes in "Full Details".
- "Key Decisions" should capture *why*, not just *what*. Future readers care about the reasoning.
- Preserve archived sections verbatim under "Full Details" — don't paraphrase, don't trim.
- "v2 State" comes from `aitk project-state --file PROJECT.md` (per `skills/archive-project-file/SKILL.md`'s step 2), not from re-reading the raw markers by hand.
