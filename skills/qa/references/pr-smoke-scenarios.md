# PR Smoke Scenarios

Derive a focused, runnable smoke-test scenario list from a PR diff and
description: scenarios that verify the PR's stated changes and protect the
most critical adjacent behavior. `test-pr` calls it before browser execution.

Input: the PR title, description, author notes and any "how to test" section;
the changed files and diff summary; and the impact from
[assess-impact.md](assess-impact.md).

## Count

Scale to impact: about 3 for PERIPHERAL, 4-5 for STANDARD, 6-7 for CORE (with
guards on adjacent CORE flows). `--smoke` caps the list at 3, and 1-2 is fine
for a mechanical PERIPHERAL change. Four sharp scenarios beat seven vague ones.

## Scenarios

Prefer entry points (UI actions, API calls, routes) over internal helpers, and
what the PR claims over generic coverage; translate the author's "how to test"
notes directly. Each scenario is action-first ("Go to X", "Click Y"),
outcome-clear ("Verify value shown is Y"), independent of the others, and
tagged:

- `[new]` — verifies new behavior this PR adds
- `[fix]` — verifies the bug this PR claims to fix, describing the broken state
  so the executor can confirm it no longer occurs
- `[guard]` — protects the most-traveled adjacent path that could regress

## Output

```markdown
## PR Smoke Scenarios

PR: #<number> — <title>
Impact: CORE / STANDARD / PERIPHERAL
Scenarios: <N>

### Scenario 1 [new/fix/guard]: <short name>
- **Goal**: <one sentence — what this verifies and why it matters>
- **Steps**: <concrete navigation + actions>
- **Pass if**: <exactly what to see or not see>

### Scenario 2 ...

### Setup Notes
- Auth: <role required, or "any logged-in user">
- Data: <required seed data or "use existing dev data">
- Flags: <feature flags, or "none">
```
