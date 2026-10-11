# Communication Formatting

Internal helper for `$pgm create-status-report` and `$pgm
create-velocity-report`: turn report data, a status update or a risk summary
into one audience's format. The audience is `--audience <mode>`, else what the
request implies ("summarize for leadership" is executive, "this needs to be
escalated" is escalation), else `delivery`. Thresholds (stalled days, review
hours) are the `thresholds` values in `config.json` (`rules/pgm.md`).

## Audience Templates

### Executive

```markdown
**TL;DR**: [One sentence — what matters most right now]
**Status**: On Track / At Risk / Blocked
**Impact**: [What this means for the business/product/users]
**Decisions Needed**:
- [Decision — with recommendation]
**Timeline**: [Key dates or milestones]
```

If there is nothing to decide, say so.

### Cross-Functional Leadership

```markdown
## Summary
[2-3 sentences — what's happening across teams]
## Team Highlights
- **[Team]**: [Key accomplishment or focus area]
## Dependencies & Risks
- [Dependency/risk with owning team and status]
## Mitigation
- [How the team is reducing the risk or dependency]
## Asks
- [What you need from other teams/stakeholders]
```

Every risk names an owner and a mitigation, or says none exists yet.

### Delivery Team

```markdown
## Board Health
- **WIP**: [count] items in progress ([assessment])
- **Blocked**: [count] items ([brief details])
- **Stalled**: [count] items with no movement > [stalled_days] days
## Blockers
| Item | Owner | Blocked Since | Action Needed |
|------|-------|---------------|---------------|
## What Shipped
- [Item] — [who]
## What's Next
- [Item] — [who]
## Action Items
- [ ] [Action] — @[owner] — [due]
```

Every blocker and every next item names an owner.

### Eng+QA

```markdown
## Technical Status
[What's actively being built/tested]
## PR State
- **Open**: [count] ([count] awaiting review > [pr_review_hours]h)
- **Merged this period**: [count]
- **Review backlog**: [details]
## Test & Build Health
[CI status, flaky tests, coverage signals]
## Tech Debt / Risks
- [Risk with impact, and its mitigation or follow-up validation]
```

Link PRs and state CI and test results exactly.

### Broad Stakeholder

```markdown
## What Launched
- **[Feature/Fix]**: [User-facing impact in plain language]
## Coming Up
- [Milestone] — [expected timing]
## How This Helps
[Connect technical work to user/business value]
```

Translate everything to user impact, without hype.

### Escalation

```markdown
## What's At Risk
[One sentence — the thing at risk and why it matters]
## Business Impact
[Users affected, revenue impact, timeline slip]
## What We've Tried
1. [Action taken] — [result]
## The Ask
**[Specific decision or support needed]** [options with trade-offs]
## Timeline
- **If we act by [date]**: [outcome]
- **If not**: [consequence]
```

Never bury the ask; state the current mitigation or that it waits on the ask.

## Working Rules

Use real names and numbers, say what data is missing, and produce one output
for one audience. The calling report may adapt headings or omit empty sections.
