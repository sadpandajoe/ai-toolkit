---
tier: Standard
---

# PR Smoke Scenarios

Derive a focused, runnable smoke-test scenario list from a PR diff and description. Produces 3–7 scenarios that directly verify the PR's stated changes and protect the most critical adjacent behavior.

## When to Use

- Called by `test-pr` before browser execution
- When you need a quick, targeted scenario set for a specific change — not a full QA matrix

## Input

The caller provides:
- PR title, description, and author notes
- List of changed files and a diff summary
- Impact assessment (CORE / STANDARD / PERIPHERAL) from [assess-impact.md](assess-impact.md)

## Steps

### 1. Extract the PR's Claims

Read the PR title and description to identify:
- What the PR claims to fix or add
- Any explicit acceptance criteria or "how to test" notes from the author
- The "before" state and expected "after" state

If the PR links to an issue or ticket, treat that as additional context for expected behavior.

### 2. Trace Changed Behavior

For each changed file in the diff:
- Identify what user-facing action triggers this code path
- Identify what the expected new behavior is
- Note adjacent behavior that could regress

Prioritize:
- Entry points (UI actions, API calls, route changes) over internal helpers
- CORE workflows over STANDARD over PERIPHERAL
- What the PR claims to fix/add over generic smoke coverage

### 3. Write Scenarios

Write 3–7 scenarios. Scale by impact:
- PERIPHERAL: 3 scenarios (happy path + 1 regression guard)
- STANDARD: 4–5 scenarios (happy path + 1 edge case + regression guards)
- CORE: 6–7 scenarios (happy path + 2 edge cases + 2–3 regression guards on adjacent CORE flows)

Each scenario must be:
- **Action-first** — starts with a concrete navigation or interaction ("Go to X", "Click Y", "Submit form Z with values A, B")
- **Outcome-clear** — states exactly what constitutes a pass ("Assert no error banner", "Verify value shown is Y", "Confirm redirect to /dashboard")
- **Independent** — can run without relying on another scenario's side effects
- **Targeted** — directly verifies the PR's change OR protects an adjacent flow likely to regress

Tag each scenario:
- `[new]` — verifies new behavior this PR adds
- `[fix]` — verifies the bug this PR claims to fix (include what the broken behavior was)
- `[guard]` — protects adjacent behavior that could regress from this change

### 4. Note Setup Requirements

Identify any prerequisites the executor will need:
- Auth state (logged in as what role?)
- Required seed data or fixtures
- Feature flags that must be enabled
- Environment-specific constraints

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

## Notes
- Favor specificity over breadth — 4 sharp scenarios beat 7 vague ones
- `[guard]` scenarios should cover the most-traveled adjacent path, not every possible regression
- If the PR description includes "how to test" or "steps to reproduce" notes, translate those directly into scenarios — the author knows where to look
- For bug fixes, the `[fix]` scenario should describe what the broken state looked like so the executor can confirm it no longer occurs
