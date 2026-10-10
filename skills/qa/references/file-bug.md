---
tier: Heavy
---

# File Bug

Use this phase when QA execution has produced a strong failure signal and the workflow needs a clean bug handoff.

## Goal

Turn a failed scenario into a crisp bug report with reliable repro steps, expected versus actual behavior, and evidence.

## Core Steps

1. Reuse the latest validated repro steps from QA triage, validation, or test-plan execution instead of rewriting them from memory.
2. Confirm whether the bug is:
   - reproducible with steps, or
   - not fully reproduced but strongly supported by evidence
3. Write clean repro steps from a known starting state.
4. Record expected versus actual behavior without speculation.
5. Attach the strongest evidence and environment details:
   - URL or page
   - branch, build, or commit when relevant
   - browser/device
   - account, role, flags, or seed data
6. For UI or workflow bugs, prefer Playwright video as the primary artifact when available.
7. Identify one `Best proof` artifact or log line so later readers know what to open first.
8. Link the failure back to the originating scenario or parent work item when relevant.

## Severity Criteria

| Severity | Indicators |
|----------|-----------|
| **high** | Data loss, security bypass, crash, blocks a core user workflow, affects many users |
| **medium** | Incorrect behavior with a workaround, non-blocking regression |
| **low** | Cosmetic misalignment, rare edge case, minor impact |

This table is the single home of QA bug severity. Across domains, `[major]` =
`[High]` = high (must address); `[minor]` = `[Medium]` = medium (should
address); `[nitpick]` = `[Low]` = low (optional). The review tags themselves
are defined in `rules/severity.md`.

## Output

```markdown
## Bug Filing Handoff

- Title: <specific failure>
- Repro status: <reproduced / evidence-only>
- Environment: <url, branch/build, flags, browser/device, account/role>
- Repro steps:
  1. <step>
- Expected: <what should happen>
- Actual: <what happened>
- Evidence: <artifact links or paths>
- Best proof: <single artifact or log line to open first>
- Severity: <high / medium / low>
```

## Example

**Title**: Non-admin users see delete button on dataset page
**Repro status**: reproduced
**Environment**: localhost:8088, branch: main, Chrome 120, account: editor_user (non-admin), DATASET_MANAGEMENT=true
**Steps**:
1. Log in as editor_user
2. Navigate to Datasets → "Sales Data"
3. Observe: Delete button visible in toolbar
**Expected**: Delete button hidden for non-admin users
**Actual**: Delete button visible and clickable
**Best proof**: screenshot-delete-button.png
**Severity**: high (security boundary violation)

## Shortcut Integration

When the workflow requires posting results back to Shortcut:

1. Upload any required video or file evidence to the story.
2. Fetch the story again to retrieve the uploaded media URL.
3. Post one clean QA result comment that includes:
   - the actual repro steps or validation path used
   - expected versus actual behavior
   - the single best proof link first
   - the overall QA result
4. Apply any required Shortcut-specific state or custom-field updates.
