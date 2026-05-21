# /run-test-plan - Standalone QA Validation

@{{TOOLKIT_DIR}}/rules/input-detection.md
@{{TOOLKIT_DIR}}/rules/preset-environments.md

> **When**: You want to validate a feature area, story, PR, or existing test-plan doc without fixing code in the same workflow.
> **Produces**: A reviewed runnable test plan, execution results, evidence for material failures, and a local findings summary.

## Usage
```
/run-test-plan ./docs/test-plan.md
/run-test-plan sql-lab
/run-test-plan sc-12345
/run-test-plan apache/superset#28456
/run-test-plan https://github.com/owner/repo/pull/123
```

## Command Contract

- The main thread owns scenario state, evidence paths, and reporting destinations. Subagents return compact scenario/review handoffs only.
- For STANDARD or expensive runs (large scenario matrix, multi-flow validation, repeated plan-review rounds), follow `rules/context-management.md`: write durable state to PROJECT.md at each phase boundary, then `/checkpoint --clear` before the next expensive phase.
- Required PROJECT.md updates on STANDARD/expensive runs:
  - After step 3 (plan at 8/10): `## Test Plan` (final scenario matrix, plan source, review score).
  - After step 4 (execution): `## Test Plan Results` (per-scenario PASS/FAIL/BLOCKED/SKIP, evidence paths).
  - After step 6 (report): `## Test Plan Reported` (where posted: Shortcut story link, PR comment, or local only).
- These writes are **hard gates before any `/checkpoint --clear`** on STANDARD/expensive runs — chat-only scenario state is unrecoverable after clear.
- The plan matrix and per-scenario evidence paths must land in PROJECT.md before clear regardless of whether the run is reactive or proactive checkpoint.
- **Every run** (including TRIVIAL/MODERATE) writes at least a `## Test Plan Results` entry to PROJECT.md before the chat summary so `/clear` or `/archive-project-file` after `/run-test-plan` does not lose the QA record. TRIVIAL/MODERATE runs may fold plan + results + report into a single end-of-run entry; STANDARD/expensive runs follow the per-phase cadence above.

  Minimum entry shape for TRIVIAL/MODERATE:

  ```markdown
  ## Test Plan Results
  Source: [plan path / Shortcut / PR / area]
  Scenarios: [N run, N passed, N failed, N blocked, N skipped]
  Evidence: [recording path or "none"]
  Reported: [link or "local only"]
  ```

  Emit before the chat summary:

  ```markdown
  ## PROJECT.md Updated — Test Plan Results
  Scenarios recorded: [count]
  ```

## Steps

1. **Resolve the Starting Point**

   Accept:
   - an existing test-plan doc or matrix
   - a feature or product area
   - a Shortcut story ID or URL
   - a GitHub issue or PR reference / URL

   Pull in external context when references are provided.

2. **Create or Resolve the Test Plan**

   If a plan is provided:
   - read it and normalize it into a compact runnable matrix

   If no plan is provided:
   - derive a compact use-case matrix from the target area or external context

3. **Iterate the Plan to 8/10**

   Load [skills/testing/references/review-testplan.md](../skills/testing/references/review-testplan.md) and review the matrix with a fresh test-plan reviewer after material revisions.
   Revise the plan until it reaches `8/10`, or stop early only if blockers or unresolved ambiguities make execution unsafe or misleading.

4. **Execute the Plan**

   Run only the scenarios that are actually testable in the current environment.

   Execution defaults:
   - Available browser automation for UI and workflow checks
   - API or CLI calls for non-UI validation
   - clear `BLOCKED` or `SKIP` outcomes when prerequisites are missing

5. **Capture Evidence**

   For UI scenarios, drive the available browser automation and capture evidence using [skills/qa/references/browser-recording.md](../skills/qa/references/browser-recording.md). Choose the platform-specific recorder from that reference. Capture one recording per logical flow when recording is available, plus screenshots for high-value states or failures.

   Supplement with console logs or API output only when video alone doesn't explain a failure.

6. **Report Findings**

   Body shape, tone, and evidence rules come from [skills/qa/references/write-report.md](../skills/qa/references/write-report.md). Destination-specific upload + post mechanics live in the matching reference (e.g. [skills/shortcut/references/report.md](../skills/shortcut/references/report.md) for Shortcut). For attaching the recording, follow the size-limit guidance in [skills/qa/references/browser-recording.md](../skills/qa/references/browser-recording.md).

   **If a Shortcut story is known** (provided as input, or from PROJECT.md):
   - Upload the recording to the story via the Shortcut `/files` endpoint
   - Post the report as a story comment

   **If a GitHub PR is known** (provided as input):
   - Attach the recording inline if it fits under GitHub's size limit (transcode to MP4 if needed); otherwise note the local path
   - Post the report as a PR comment

   **Otherwise**:
   - Display the report locally using the same template, with the recording path

   Do not auto-file bugs or auto-route into `/fix-bug`.

7. **Summary**

   Always display locally, regardless of whether external reporting happened:

   ```markdown
   ## Run-Test-Plan Complete

   ### Outcome
   - [Executed plan / stopped on blocker before execution]

   ### Source
   - [Plan doc, area, story, or PR]

   ### Plan Quality
   - [Final review score or blocker]

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

## Notes
- `/run-test-plan` is validation-only in v1
- Prefer a small runnable matrix over a broad exploratory sweep
- Keep findings factual and local-first
- The command should keep tightening and executing the plan automatically until the matrix reaches threshold or a real blocker stops it
- The main thread owns scenario state, evidence paths, and reporting destinations; any subagent returns compact scenario/review handoffs only
