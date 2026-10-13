# Plan Output Template

## Rules

- The plan is about *how*, not *whether*: do not re-litigate the gate. A plan
  may note disagreement with the gate for the user, never override it.
- For trivial changes, the Adaptation Strategy can be one line ("Clean apply
  expected, no adaptation needed"); for non-trivial, give per-file detail.
- List modify/delete files explicitly; they need `git rm` during apply.
- For a bundled PR, list each sub-fix and its applicability, recommend which to
  include, treat entangled sub-fixes atomically, and state "N of M sub-fixes
  planned for inclusion".
- Record the plan's outcome in the row of `CHERRY_PICK.md`
  ([../templates/cherry-pick-manifest.md](../templates/cherry-pick-manifest.md)),
  which owns the row schema and the adaptation severity definitions.

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
[For non-trivial: per-file approach, API and import changes, what to include and drop]
[For trivial: "Clean apply expected, no adaptation needed"]

### Validation Approach
Checks: [specific commands]
Tests: [specific test files/suites or "none identified"]
Gaps: [what can't be validated locally]

### Risk Summary
Overall risk: LOW / MED / HIGH
Key concern: [one line or "none"]
```
