# Create Feature Brief

Turn a raw request into a brief specific enough for technical planning.
Investigate rather than reformat: read the ticket and its comments, the code
area's current behavior and prior attempts; separate what the user needs from
what they literally said.

When the request has more than one valid reading, pick the most likely reading
and state the assumption. Surface an ambiguity too large to resolve as a
decision before planning.

Non-goals are required: without them, reviewers suggest additions left out on
purpose. Each acceptance criterion is verifiable (a testable assertion or
observable behavior); cover the happy path and at least one edge case. Add milestones with "users can X"
success conditions when rollout sequencing matters.

## Output

```markdown
## Feature Brief
### Goal
<what changes for the user or system, 1-2 sentences>
### Non-goals
- <what this does not include>
### Acceptance Criteria
- [ ] <happy path>
- [ ] <edge case>
### Milestones (only when rollout sequencing matters)
- <name>: users can <X>
### Assumptions
- <assumption and why>
### Dependencies and Risks
- <dependency or rollout risk and its mitigation, or "none">
### Open Questions
- <what needs user input before planning, or "none">
```

## Self-check

- Is the scope bounded, with goals and non-goals separated?
- Is every acceptance criterion testable?
- Are product assumptions stated and rollout, dependency and risk gaps covered?
- Does the brief stay out of code style, architecture and file layout?
