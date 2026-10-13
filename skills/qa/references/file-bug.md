# File Bug

Use when QA execution produced a strong failure signal and the workflow needs
a clean bug handoff.

1. Reuse the latest validated repro steps from triage, validation, or
   test-plan execution instead of rewriting them from memory, and say whether
   the bug reproduced or is evidence-only.
2. Write repro steps from a known starting state, and expected versus actual
   behavior without speculation.
3. Record the environment: URL or page, branch/build/commit when relevant,
   browser/device, and account, role, flags or seed data.
4. Attach the strongest evidence (a recording for UI or workflow bugs) and
   name one `Best proof` artifact or log line to open first. Link the
   originating scenario or work item when there is one.

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

## Shortcut

When the result goes back to a Shortcut story, follow
`skills/shortcut/references/report.md` in this order: upload the evidence,
refetch the story for the uploaded media URL, then post one comment with the
repro or validation path, expected versus actual, the best proof link first,
and the overall result.
