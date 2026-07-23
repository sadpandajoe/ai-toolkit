# Communication Formatting

Use this supporting file when a reporting command needs audience-specific formatting.

Transform the input report data, status update, or risk summary into audience-appropriate output.

## Usage

This is an internal helper for `$pgm create-status-report` and `$pgm create-velocity-report`.
Do not require a separate top-level formatting command when the reporting command can emit the requested audience format directly.

If no audience is specified, infer from context:
- "summarize for leadership" → executive
- "update the team" → delivery
- "this needs to be escalated" → escalation
- unclear → ask

## Audience Templates

### Executive

```markdown
**TL;DR**: [One sentence — what matters most right now]

**Status**: 🟢 On Track / 🟡 At Risk / 🔴 Blocked

**Impact**: [What this means for the business/product/users]

**Decisions Needed**:
- [Decision 1 — with recommendation]

**Timeline**: [Key dates or milestones]
```

Rules:
- no task lists
- no technical jargon
- no individual story details
- lead with impact
- if there's nothing to decide, say so
- if a material risk is mentioned, include the mitigation in one sentence

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

Rules:
- balance detail across teams
- flag cross-team dependencies explicitly
- every risk needs an owner
- every material risk should include a mitigation or explicitly state that no viable mitigation exists yet

### Delivery Team

```markdown
## Board Health
- **WIP**: [count] items in progress ([assessment])
- **Blocked**: [count] items ([brief details])
- **Stalled**: [count] items with no movement > 5 days

## Blockers
| Item | Owner | Blocked Since | Action Needed |
|------|-------|---------------|---------------|

## Mitigation
- [What is being done next, by whom, and by when]

## What Shipped
- [Item] — [who]

## What's Next
- [Item] — [who]

## Action Items
- [ ] [Action] — @[owner] — [due]
```

Rules:
- every blocker needs an owner and action
- every "what's next" needs a name attached
- no vague summaries
- risks and blockers should include mitigation or next action, not just diagnosis

### Eng+QA

```markdown
## Technical Status
[What's actively being built/tested]

## PR State
- **Open**: [count] ([count] awaiting review > 48h)
- **Merged this period**: [count]
- **Review backlog**: [details]

## Test & Build Health
[CI status, flaky tests, test coverage signals]

## Tech Debt / Risks
- [Technical risk or debt item with impact]

## Mitigation
- [What engineering or QA is doing next to reduce the risk]
```

Rules:
- include PR links where relevant
- be specific about CI/test state
- use precise technical language
- any material technical risk should include mitigation, containment, or follow-up validation

### Broad Stakeholder

```markdown
## What Launched
- **[Feature/Fix]**: [User-facing impact in plain language]

## Coming Up
- [Milestone] — [expected timing]

## How This Helps
[Connect technical work to user/business value]
```

Rules:
- no internal jargon
- translate everything to user impact
- show momentum without hype
- mention mitigation only if it materially affects launch confidence or timing

### Escalation

```markdown
## What's At Risk
[One sentence — the thing that's at risk and why it matters]

## Business Impact
[Quantify if possible — users affected, revenue impact, timeline slip]

## What We've Tried
1. [Action taken] — [result]
2. [Action taken] — [result]

## The Ask
**[Specific decision or support needed]**
[Options if applicable, with trade-offs]

## Timeline
- **If we act by [date]**: [outcome]
- **If not**: [consequence]
```

Rules:
- never bury the ask
- lead with what is at risk
- show what has already been tried
- include timeline and consequence
- always include current mitigation or explicitly state that mitigation is blocked pending the ask

## Working Rules

- follow the audience format closely
- the calling report command may adapt headings or omit empty sections if audience expectations are preserved
- use real names and real numbers
- if input data is incomplete, say what is missing
- keep it scannable
- one output, one audience
- if a risk or blocker is present, include mitigation unless that audience explicitly does not need it
