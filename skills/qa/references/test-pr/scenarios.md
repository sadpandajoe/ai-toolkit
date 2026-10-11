# Test PR Scenarios

Run [../assess-impact.md](../assess-impact.md) against the PR diff, then derive
the list with [../pr-smoke-scenarios.md](../pr-smoke-scenarios.md), which owns
the count rule and the scenario format.

## Selection Boundary

Show the scenario list before execution, then proceed by default; invoking the
workflow delegates non-destructive scenario selection on local or staging
environments. When `--step` was supplied, pause here and accept user edits before
running the browser.
