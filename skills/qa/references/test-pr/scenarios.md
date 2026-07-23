---
tier: Heavy
---

# Test PR Scenarios

## Impact Assessment

Read [../assess-impact.md](../assess-impact.md) against the PR diff and changed files. Classify touched workflows as CORE, STANDARD, or PERIPHERAL.

## Scenario Derivation

Read [../pr-smoke-scenarios.md](../pr-smoke-scenarios.md) with:

- PR title, body, author notes, and "how to test" section.
- Changed files and relevant diff hunks.
- Impact assessment.

Produce 3-7 focused scenarios. With `--smoke`, cap at 3.

Scenario mix:

- New behavior introduced by the PR.
- Bug fix path or regression path.
- Guard/edge path that could break from the changed files.
- One adjacent core workflow when impact is CORE.

## Selection Boundary

Show the scenario list before execution, then proceed by default; invoking the
workflow delegates non-destructive scenario selection on local or staging
environments. When `--step` was supplied, pause here and accept user edits before
running the browser.

For very small or mechanical PRs, a 1-2 scenario smoke is acceptable when the impact assessment supports it.
