# Standalone QA Validation


> **When**: You want to validate a feature area, story, PR, or existing test-plan doc without fixing code in the same workflow.
> **Produces**: A reviewed runnable test plan, execution results, evidence for material failures, and a local findings summary.

## Effect Boundary

Effect: `local_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `run-test-plan` entry
in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Usage
```
run-test-plan ./docs/test-plan.md
run-test-plan sql-lab
run-test-plan sc-12345
run-test-plan apache/superset#28456
run-test-plan https://github.com/owner/repo/pull/123
```

## Goal

Validate a feature area, story, PR, or existing test-plan doc without fixing
code: a reviewed runnable matrix, executed where the environment allows,
evidence for material failures, and a findings report. This workflow validates
only; it does not file bugs or route into `fix-bug`. Prefer a small runnable
matrix over a broad exploratory sweep, and keep findings factual and
local-first.

The main thread owns test design, scenario execution and state, diagnosis,
evidence paths, and reporting destinations. The `operations` route only
summarizes evidence already collected, the `review` route judges results
independently, and any subagent returns a compact scenario or review handoff.

1. **Plan.** Accept a test-plan doc or matrix, a feature or product area, a
   Shortcut story ID or URL, or a GitHub issue or PR reference, and pull in
   the external context it points to. Normalize a provided plan into a compact
   runnable matrix, or derive one from the target and its context.
2. **Review the plan once.** Load
   [skills/testing/references/review-testplan.md](../../testing/references/review-testplan.md)
   and review the matrix with a fresh test-plan reviewer after material revisions.
   Revise once on the reviewer's blocking findings (one informed retry under
   `rules/gates.md`), then execute; stop early only when blockers or
   unresolved ambiguities would make execution unsafe or misleading.
3. **Execute** only the scenarios the current environment can test: browser
   automation for UI and workflow checks, API or CLI calls otherwise, and
   `BLOCKED` or `SKIP` with the reason when a prerequisite is missing. For UI
   scenarios, capture evidence with
   [skills/qa/references/browser-recording.md](../../qa/references/browser-recording.md)
   and its platform recorder: one recording per logical flow when recording
   is available, plus screenshots for high-value states and failures. Add
   console logs or API output only when the video does not explain a failure.
4. **Report.** Body shape, tone, and evidence rules come from
   [skills/qa/references/write-report.md](../../qa/references/write-report.md);
   attachment size limits from `browser-recording.md`. When a Shortcut story
   is known (input or PROJECT.md), upload the recording through the Shortcut
   `/files` endpoint and post the report as a story comment
   ([skills/shortcut/references/report.md](../../shortcut/references/report.md)).
   When a GitHub PR is given, run the PII scrub in
   `feedback/references/reply-resolve.md` over the report body and attachment
   names first (a PR comment is public; a Shortcut comment is not), attach the
   recording inline if it fits under GitHub's size limit (transcode to MP4 if
   needed) or note the local path, and post the report as a PR comment.
   Otherwise show the report locally with the recording path.

## Exit Criteria

- The matrix passed its one review, or the reason execution stopped is
  recorded.
- Every scenario is `PASS`, `FAIL`, `BLOCKED`, or `SKIP`, and every material
  failure has evidence.
- PROJECT.md has a `## Test Plan Results` entry before the chat summary, so a
  fresh session or [`archive-project-file`](../../archive-project-file/SKILL.md)
  after `run-test-plan` keeps the QA record:

  ```markdown
  ## Test Plan Results
  Source: [plan path / Shortcut / PR / area]
  Scenarios: [N run, N passed, N failed, N blocked, N skipped]
  Evidence: [recording path or "none"]
  Reported: [link or "local only"]
  ```

  When execution or reporting runs in a fresh worker, write `## Test Plan`
  (final matrix, plan source, review verdict) before execution, and this
  entry with per-scenario results and evidence paths before reporting: the
  worker and any later session resume only from PROJECT.md.

## Summary

Always display locally, whether or not a report was posted:

```markdown
## Run-Test-Plan Complete

### Outcome
- [Executed plan / stopped on blocker before execution]

### Source
- [Plan doc, area, story, or PR]

### Plan Quality
- [Reviewer verdict or blocker]

### Results
- [PASS / FAIL / BLOCKED / SKIP by scenario]

### Evidence
- [Video files with paths]
- [Best proof for failures or high-value passes]

### Reported To
- [Shortcut story link / GitHub PR link / local only]

### Risks / Blockers
- [What could not be executed or remains unclear]

### Follow-Up
- [Manual next steps only]
```
