# Plan Output Template

## Rules

- The **Execution Table Row** is required for every cherry-pick — it is the tracking artifact that follows the cherry through apply → adapt → validate.
- For trivial changes, the Adaptation Strategy can be a single line ("Clean apply expected, no adaptation needed"). For non-trivial, use per-file detail.
- See [../examples/execution-table.md](../examples/execution-table.md) for the full 12-column batch table and field meanings.
- Do not re-litigate the gate's go/no-go — the plan is about *how*, not *whether*.

## Template

```markdown
## Cherry-Pick Plan: <sha-short> (<summary>)

### File Strategy
Include: [N files]
Exclude: [list with reasons or "none"]
Modify/delete expected: [list or "none"]

### Conflict Forecast
Expected conflicts: [list with resolution approach or "none expected"]
Unknown risks: [list or "none"]

### Adaptation Strategy
[For non-trivial: detailed per-file approach]
[For trivial: "Clean apply expected, no adaptation needed"]

### Validation Approach
Checks: [specific commands]
Tests: [specific test files/suites or "none identified"]
Gaps: [what can't be validated locally]

### Execution Table Row
| SHA | PR | Description | Risk | Confidence | Decision | Status | Adaptation | Validation | Notes |
|-----|----|-------------|------|------------|----------|--------|------------|------------|-------|
| `<sha>` | #NNN | <summary> | LOW/MED/HIGH | X/10 | Auto/Approval/Escalate | Planned | None/Minor/Medium/High | Not run | <notes> |

### Risk Summary
Overall risk: LOW / MED / HIGH
Key concern: [one line or "none"]
```
