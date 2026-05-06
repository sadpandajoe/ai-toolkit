# /run-test-plan - Standalone QA Validation

@{{TOOLKIT_DIR}}/rules/input-detection.md
@{{TOOLKIT_DIR}}/rules/preset-environments.md
@{{TOOLKIT_DIR}}/skills/testing/references/review-testplan.md

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

   Review the matrix with the shared test-plan reviewer.
   Revise the plan until it reaches `8/10`, or stop early only if blockers or unresolved ambiguities make execution unsafe or misleading.

4. **Execute the Plan**

   Run only the scenarios that are actually testable in the current environment.

   Execution defaults:
   - Playwright MCP for UI and workflow checks
   - API or CLI calls for non-UI validation
   - clear `BLOCKED` or `SKIP` outcomes when prerequisites are missing

5. **Capture Evidence**

   For UI scenarios, drive the browser via Playwright MCP and record the run as a single video artifact via macOS `screencapture` — follow the canonical recipe in [skills/qa/references/browser-recording.md](../skills/qa/references/browser-recording.md). One recording per logical flow, saved under `~/qa-recordings/<source-id>-<short-name>-<UTC-timestamp>.mov`. Real Chrome with the real OS cursor — no `recordVideo`, no synthetic-cursor scaffolding.

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
