# Validate

Use after a bug fix or a feature slice has passed code-level verification and
review, to confirm the behavior holds in the user-visible workflow.

Inputs: the confirmed repro steps (bug) or the acceptance criteria (feature),
the change summary, the review gate status, and the app URL or environment
state.

1. Bug: re-run the confirmed repro steps. Feature: map each relevant
   acceptance criterion to one validation action.
2. Drive UI paths with the available browser automation when the app is
   runnable; otherwise use API or CLI calls.
3. Exercise the primary path and the most important adjacent, edge, or
   permission/data-state path.
4. Capture evidence for material passes and failures.

Honesty rule: when browser automation, the app, data, flags or access are
unavailable, record the blocker instead of implying full validation.

## Output

Bug fix:

```markdown
## QA Validation

- Result: <pass / partial / fail / blocked>
- Validation path: <browser automation / api / manual / mixed / blocked>
- Primary repro: <resolved or still broken>
- Additional scenarios checked: <what was exercised>
- Remaining risks: <what still needs attention>
- Blockers: <env or setup gaps, if any>
```

Feature:

```markdown
## Feature Validation

- Result: <pass / partial / fail / blocked>
- Validation path: <browser automation / api / manual / mixed / blocked>
- Acceptance criteria:
  - <criterion>: <met / partial / failed / blocked> - <evidence>
- Evidence:
  - <screenshot/video/log path, or none>
- Remaining risks:
  - <risk or none>
- Blockers:
  - <env/setup/data gaps, if any>
```
