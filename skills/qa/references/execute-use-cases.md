---
tier: Heavy
---

# Execute Use Cases

Use this phase when a workflow already has a use-case matrix or confirmed repro steps and needs a generic QA execution pass.

## Goal

Run the relevant scenarios against a real environment, record the outcomes clearly, and hand the results back with reliable evidence and repro detail.

## Core Steps

1. Filter the matrix to scenarios that are testable in the current environment.
2. Confirm environment health, data, feature flags, and permissions.
3. Run each scenario through the right path:
   - Playwright MCP for UI workflows
   - direct HTTP or CLI calls for API-only paths
   - mark blocked scenarios clearly when prerequisites are missing
4. Record PASS, FAIL, BLOCKED, or SKIP for each scenario.
5. Hand the results back to the calling workflow with enough evidence for summary, reporting, or bug filing when needed.

## Evidence Capture

For UI execution, follow the canonical
[browser-recording recipe](browser-recording.md):

1. Start one linear full-flow recording before the first related scenario.
2. Save the final `.webm` under `~/qa-recordings/` using the canonical name.
3. Capture a screenshot at each scenario's decisive verification point.
4. Supplement with console logs or API output when they explain a failure that video alone doesn't capture.
5. Identify the single best proof artifact for each scenario.

## Output

```markdown
## QA Execution Result

- Scenario: <name>
  - Result: <pass / fail / blocked / skip>
  - Validation path: <playwright / api / manual>
  - Evidence: <screenshots, logs, video, or none>
  - Best proof: <single artifact or log line to reference first>
  - Follow-up: <summarize / rerun later / file bug / no action>
```
