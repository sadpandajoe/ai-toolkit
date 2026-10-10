# Manual PR Testing via Browser


> **When**: You want to manually verify a PR's user-visible behavior in a running local or staging app.
> **Produces**: Scenario-by-scenario pass/fail results with screenshot and optional video evidence.

## Effect Boundary

Effect: `external_effect`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `test-pr` entry in
`interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Usage

```bash
test-pr <pr-number>
test-pr apache/superset#28456
test-pr https://github.com/owner/repo/pull/123
test-pr <pr-number> --url http://localhost:3000
test-pr <pr-number> --checkout
test-pr <pr-number> --smoke
test-pr <pr-number> --post
test-pr <pr-number> --post sc-12345
test-pr <pr-number> --post pr
test-pr <pr-number> --no-record
```

## Prerequisite

The app must already be running unless `--url` points to staging. This command verifies the PR against the current app; it does not start the dev server.

Use `--checkout` when you need the command to switch to the PR branch first. After checkout, pause so the user can restart the app.

## Authorization Boundary

Authorization mode: `explicit`. Local/staging scenario execution follows the
declared gates; posting requires `--post`, checkout requires `--checkout`, and
destructive or production actions remain refused.

## Routing

Use the `qa` skill and load only the needed references:

1. Resolve PR, checkout, URL, and auth with [skills/qa/references/test-pr/setup.md](../../qa/references/test-pr/setup.md).
2. Assess impact and derive smoke scenarios with [skills/qa/references/test-pr/scenarios.md](../../qa/references/test-pr/scenarios.md).
3. Execute browser scenarios with [skills/qa/references/test-pr/execute.md](../../qa/references/test-pr/execute.md).
4. Report or post results with [skills/qa/references/test-pr/report.md](../../qa/references/test-pr/report.md).

The main thread owns PR identity, app URL, scenario selection, evidence paths, posting decisions, and final summary. Do not load execution/reporting references until setup and scenario selection are complete.

## PROJECT.md Record

Every run appends a `## Test-PR Results` entry to PROJECT.md before the chat
summary, so a fresh session or [`archive-project-file`](../../archive-project-file/SKILL.md)
immediately after `test-pr` keeps the QA record:

```markdown
## Test-PR Results — PR #[number]
App: [url]
Impact: [tier]
Scenarios: [N run, N passed, N failed]
Evidence: [recording path or "none"]
Posted: [link or "local only"]
```

When execution or posting runs in a fresh worker (a CORE-impact PR, a broad
scenario set, repeated re-validation), first write `## Test-PR Scenarios` (PR
identity, app URL, impact tier, scenario list): the worker and any later
session resume only from PROJECT.md.

## Gates

- Stop if the app URL cannot be resolved.
- Stop on production URLs.
- Print the selected scenarios and proceed — invoking the command delegates scenario selection, and execution is non-destructive on local/staging (prod is already gated above). With `--step`, confirm before execution.
- Run scenarios sequentially; do not parallelize browser evidence gathering.
- Record by default; skip only with `--no-record`.
- Stop before posting unless `--post` was passed and evidence paths are available. Before a PR comment, run the PII scrub in `feedback/references/reply-resolve.md` over the posted text and attachment names; a PR comment is public.

## Summary Contract

End with:

```markdown
## Test-PR Complete

PR: #<number> - <title>
Branch: <head-branch>
App: <url>
Impact: CORE / STANDARD / PERIPHERAL

### Results
| # | Scenario | Tag | Result | Notes |
|---|----------|-----|--------|-------|

### Evidence
- Recording: ...
- Screenshots: ...

### Next Steps
- ...
```

## Notes

- For full curated validation, use `run-test-plan`.
- For existing automated Playwright specs, route to [skills/superset-local/references/run-playwright.md](../../superset-local/references/run-playwright.md) when this is a Superset repo.
- This command does not modify code or file bugs.
